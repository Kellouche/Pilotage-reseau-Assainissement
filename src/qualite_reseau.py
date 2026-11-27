"""
================================================================================
Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
Auteur : Dr Abdelhakim KELLOUCHE
Date de création : 2026-04-20
Date de modification : 2026-11-27
Objet : Audit de qualité topologique, détection d'inversions de pente et anomalies
================================================================================
"""

import os
import math
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session
from typing import Dict, List, Any, Tuple
from pathlib import Path
import pandas as pd
from datetime import datetime

import sys
from src.validateurs.topologie import ValidateurTopologie

_is_test = (
    "pytest" in sys.modules
    or any("pytest" in arg for arg in sys.argv)
    or os.getenv("TESTING") == "true"
    or os.getenv("PYTEST_CURRENT_TEST") is not None
)

if _is_test or os.getenv("DATABASE_URL", "").startswith("sqlite"):
    DATABASE_URL = "sqlite:///./swmm_platform.db"
    engine = create_engine(DATABASE_URL, echo=False, future=True, connect_args={"check_same_thread": False})
    USE_POSTGRESQL = False
else:
    DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+psycopg2://swmm_user:swmm_password_2026@localhost:5010/swmm_platform")
    try:
        engine = create_engine(DATABASE_URL, connect_args={"connect_timeout": 2} if "postgres" in DATABASE_URL else {})
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        print("Connexion PostgreSQL etablie")
        USE_POSTGRESQL = True
    except Exception as e:
        DATABASE_URL = "sqlite:///./swmm_platform.db"
        engine = create_engine(DATABASE_URL, echo=False, future=True, connect_args={"check_same_thread": False})
        USE_POSTGRESQL = False

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

_cache_report: dict | None = None
_cache_timestamp: float = 0.0
_cache_ttl = 300  # seconds


from src.qualite_reseau_connectivite import QualiteReseauConnectivite
from src.qualite_reseau_detecteurs import QualiteReseauDetecteursPhysiques


class QualiteReseau(QualiteReseauConnectivite, QualiteReseauDetecteursPhysiques):
    """Module principal pour l'analyse de la qualité des données réseau."""

    def __init__(self, db_url: str = None):
        self.db_url = db_url or DATABASE_URL
        self.engine = create_engine(self.db_url)
        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)

    def fermer_connexion(self):
        if self.engine:
            self.engine.dispose()

    def analyser_reseau_complet(self) -> Dict[str, Any]:
        """Analyse le réseau et renvoie le rapport.
        Le résultat est mis en cache pendant 5 minutes afin d'éviter de
        recalculer à chaque appel HTTP (opération lourde)."""
        import time
        global _cache_report, _cache_timestamp, _cache_ttl
        # Si le cache est encore valable, on le renvoie immédiatement
        if _cache_report is not None and (time.time() - _cache_timestamp) < _cache_ttl:
            print("Retour du rapport qualite depuis le cache (%.1f s)" % (time.time() - _cache_timestamp))
            return _cache_report

        print("Lancement d'une analyse complete (pas de cache)")
        print("Analyse de la qualite du reseau d'assainissement...")
        print("Phase 0 : Detectons basiques (geometrie, pentes)")
        print("Phase 1 : Validations topologiques (fondations)")
        print("Phase 2 : Analyse pente et profil (sauts, courbes)")
        print("Phase 3 : Capacite debitaire (NP 650)")

        session = self.SessionLocal()
        validateur_topo = ValidateurTopologie(session)

        anomalies = {
            "conduites_sans_regards": self.detecter_conduites_sans_regards(),
            "troncons_orphelins": self.detecter_troncons_orphelins(),
            "champs_manquants": self.detecter_champs_manquants(),
            "geometries_invalides": self.detecter_geometries_invalides(),
            "pentes_suspectes": self.detecter_pentes_suspectes(),
            "sauts_pente": self.detecter_sauts_pente(),
            "incoherences_amont_aval": self.detecter_incoherences_amont_aval(),
            "incoherence_profondeur_topologie": validateur_topo.valider_coherence_profondeurs(),
            "chevauchement_geometrique": validateur_topo.valider_chevauchements_geometriques(),
            "doublon_regards": validateur_topo.detecter_doublons_regards(),
            "capacite_debit": self.detecter_capacite_debit()
        }

        rapport = {
            "date_analyse": datetime.now().isoformat(),
            "statistiques_globales": self._get_statistiques_globales(),
            "anomalies": anomalies,
            "scores_qualite": self.calculer_scores_qualite(anomalies)
        }

        session.close()
        print(f"Analyse terminee - {len(rapport['anomalies'])} categories d'anomalies detectees")
        # Mémoriser le résultat dans le cache
        _cache_report = rapport
        _cache_timestamp = time.time()
        return rapport

    def valider_incremental(self, ids_conduites: List[int]) -> Dict[str, Any]:
        """Validation incrémentale sur un sous-ensemble de conduites.

        Analyse uniquement les conduites dont les IDs sont fournis, ainsi que
        leurs voisins directs, pour un diagnostic ciblé et rapide.
        """
        if not ids_conduites:
            return {"anomalies": {}, "scores_qualite": {}, "statistiques_globales": {}}

        with self.SessionLocal() as session:
            # Récupérer les voisins directs (amont/aval) pour élargir le contexte
            ids_str = ",".join(str(i) for i in ids_conduites)
            result = session.execute(text(f"""
                SELECT DISTINCT id_amont, id_aval
                FROM conduites
                WHERE id IN ({ids_str})
                  AND (id_amont IS NOT NULL OR id_aval IS NOT NULL)
            """))
            voisins = set()
            for row in result.fetchall():
                if row[0]:
                    voisins.add(row[0])
                if row[1]:
                    voisins.add(row[1])

        ids_etendus = list(set(ids_conduites) | voisins)

        # Construire un analyseur dédié pour ne pas polluer le cache global
        analyseur = QualiteReseau()
        try:
            anomalies = {
                "conduites_sans_regards": analyseur.detecter_conduites_sans_regards(ids_conduites=ids_etendus),
                "troncons_orphelins": analyseur.detecter_troncons_orphelins(ids_conduites=ids_etendus),
                "champs_manquants": analyseur.detecter_champs_manquants(ids_conduites=ids_etendus),
                "geometries_invalides": analyseur.detecter_geometries_invalides(ids_conduites=ids_etendus),
                "pentes_suspectes": analyseur.detecter_pentes_suspectes(ids_conduites=ids_etendus),
                "sauts_pente": analyseur.detecter_sauts_pente(ids_conduites=ids_etendus),
                "incoherences_amont_aval": analyseur.detecter_incoherences_amont_aval(ids_conduites=ids_etendus),
                "capacite_debit": analyseur.detecter_capacite_debit(ids_conduites=ids_etendus)
            }
            scores = analyseur.calculer_scores_qualite(anomalies)
            stats = analyseur._get_statistiques_globales()
            return {
                "anomalies": anomalies,
                "scores_qualite": scores,
                "statistiques_globales": stats,
                "nb_conduites_analysees": len(ids_etendus)
            }
        finally:
            analyseur.fermer_connexion()

    def _get_statistiques_globales(self) -> Dict[str, Any]:
        stats = {}

        with self.SessionLocal() as session:
            for table in ['regards', 'conduites', 'rejets']:
                result = session.execute(text(f"SELECT COUNT(*) as count FROM {table}"))
                stats[f"nb_{table}"] = result.fetchone()[0]

            result = session.execute(text("""
                SELECT
                    COUNT(DISTINCT commune) as nb_communes,
                    MIN(longitude) as lon_min, MAX(longitude) as lon_max,
                    MIN(latitude) as lat_min, MAX(latitude) as lat_max
                FROM regards
                WHERE longitude IS NOT NULL AND latitude IS NOT NULL
            """))
            geo_stats = result.fetchone()
            if geo_stats:
                stats.update({
                    'nb_communes': geo_stats[0],
                    'lon_min': geo_stats[1],
                    'lon_max': geo_stats[2],
                    'lat_min': geo_stats[3],
                    'lat_max': geo_stats[4]
                })

        return stats


    def calculer_scores_qualite(self, anomalies: Dict[str, List] = None) -> Dict[str, Any]:
        scores = {}

        with self.SessionLocal() as session:
            result = session.execute(text("""
                SELECT commune,
                       COUNT(*) as total_regards,
                       SUM(CASE WHEN profondeur IS NOT NULL AND diametre IS NOT NULL THEN 1 ELSE 0 END) as regards_complets
                FROM regards
                WHERE commune IS NOT NULL
                GROUP BY commune
            """))

            scores['par_commune'] = []
            for row in result.fetchall():
                score = (row[2] / row[1]) * 100 if row[1] > 0 else 0
                scores['par_commune'].append({
                    "commune": row[0],
                    "score_qualite": round(score, 1),
                    "regards_complets": row[2],
                    "total_regards": row[1]
                })

        if anomalies is None:
            anomalies = {}

        # Déduplication : un même élément ne doit être compté qu'une fois,
        # même s'il présente plusieurs types d'anomalies.
        elements_affectes = set()
        for categorie, liste in anomalies.items():
            for anomalie in liste:
                eid = (
                    anomalie.get("id_conduite")
                    or anomalie.get("id_regard")
                    or anomalie.get("id")
                    or anomalie.get("fid")
                )
                if eid is not None:
                    elements_affectes.add((categorie, str(eid)))

        total_elements_uniques = len(elements_affectes)

        stats_globales = self._get_statistiques_globales()
        total_elements = (
            stats_globales.get('nb_regards', 0) +
            stats_globales.get('nb_conduites', 0) +
            stats_globales.get('nb_rejets', 0)
        )

        # Score borné entre 0 et 100 pour éviter les valeurs négatives
        if total_elements > 0:
            score_global = ((total_elements - total_elements_uniques) / total_elements) * 100
            score_global = max(0.0, min(100.0, score_global))
        else:
            score_global = 100.0

        scores['global'] = {
            "score_qualite": round(score_global, 1),
            "total_elements": total_elements,
            "total_elements_uniques_affectes": total_elements_uniques,
            "total_anomalies_brutes": sum(len(v) for v in anomalies.values()) if anomalies else 0
        }

        print(f"Scores de qualité calculés - Score global: {scores['global']['score_qualite']}%")
        return scores

    def exporter_rapport_csv(self, rapport: Dict[str, Any], fichier_sortie: str = "rapport_qualite_reseau.csv"):
        anomalies = []

        for categorie, liste_anomalies in rapport['anomalies'].items():
            for anomalie in liste_anomalies:
                anomalie['categorie'] = categorie
                anomalies.append(anomalie)

        if anomalies:
            df = pd.DataFrame(anomalies)
            df.to_csv(fichier_sortie, index=False, encoding='utf-8-sig')
            print(f"Rapport exporte: {fichier_sortie} ({len(anomalies)} anomalies)")
        else:
            print("Aucune anomalie détectée - pas d'export nécessaire")

    def fermer_connexion(self):
        if hasattr(self, 'engine'):
            self.engine.dispose()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.fermer_connexion()


def analyser_qualite_reseau(exporter_csv: bool = True):
    try:
        with QualiteReseau() as analyseur:
            rapport = analyseur.analyser_reseau_complet()

            print("\n" + "="*60)
            print("RAPPORT DE QUALITE DU RESEAU D'ASSAINISSEMENT")
            print("="*60)
            print(f"Date d'analyse: {rapport['date_analyse']}")
            print(f"Score global: {rapport['scores_qualite']['global']['score_qualite']}%")
            print(f"Total elements: {rapport['scores_qualite']['global']['total_elements']}")
            print(f"Total anomalies: {rapport['scores_qualite']['global']['total_anomalies']}")

            print("\nDETAIL DES ANOMALIES:")
            for categorie, anomalies in rapport['anomalies'].items():
                print(f"- {categorie}: {len(anomalies)} anomalies")

            if exporter_csv:
                analyseur.exporter_rapport_csv(rapport)

            return rapport

    except Exception as e:
        print(f"Erreur lors de l'analyse: {e}")
        return None


if __name__ == "__main__":
    analyser_qualite_reseau()
