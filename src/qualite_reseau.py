"""
Module de qualité des données réseau - Phase 2
Détection et analyse des anomalies dans le réseau d'assainissement
"""

import os
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from typing import Dict, List, Any, Tuple
from pathlib import Path
import pandas as pd
from datetime import datetime

# Configuration base de données
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+psycopg2://swmm_user:swmm_password_2026@localhost:5010/swmm_platform")

# Fallback vers SQLite si PostgreSQL indisponible
try:
    engine = create_engine(DATABASE_URL)
    # Test de connexion
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    print("✅ Connexion PostgreSQL établie")
    USE_POSTGRESQL = True
except Exception as e:
    print(f"⚠️ PostgreSQL indisponible ({e}), fallback vers SQLite")
    DATABASE_URL = "sqlite:///swmm_platform.db"
    engine = create_engine(DATABASE_URL)
    USE_POSTGRESQL = False

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class QualiteReseau:
    """
    Module principal pour l'analyse de la qualité des données réseau.
    Détecte les anomalies, calcule les scores de qualité, et génère des rapports.
    """

    def __init__(self, db_url: str = None):
        """Initialise la connexion à la base de données."""
        self.db_url = db_url or DATABASE_URL
        self.engine = create_engine(self.db_url)
        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)

    def analyser_reseau_complet(self) -> Dict[str, Any]:
        """
        Analyse complète de la qualité du réseau.
        Retourne un rapport détaillé avec toutes les anomalies détectées.
        """
        print("🔍 Analyse de la qualité du réseau d'assainissement...")

        rapport = {
            "date_analyse": datetime.now().isoformat(),
            "statistiques_globales": self._get_statistiques_globales(),
            "anomalies": {
                "conduites_sans_regards": self.detecter_conduites_sans_regards(),
                "troncons_orphelins": self.detecter_troncons_orphelins(),
                "champs_manquants": self.detecter_champs_manquants(),
                "geometries_invalides": self.detecter_geometries_invalides(),
                "pentes_suspectes": self.detecter_pentes_suspectes(),
                "incoherences_amont_aval": self.detecter_incoherences_amont_aval()
            },
            "scores_qualite": self.calculer_scores_qualite()
        }

        print(f"✅ Analyse terminée - {len(rapport['anomalies'])} catégories d'anomalies détectées")
        return rapport

    def _get_statistiques_globales(self) -> Dict[str, Any]:
        """Récupère les statistiques globales du réseau."""
        stats = {}

        with self.SessionLocal() as session:
            # Nombre d'éléments par type
            for table in ['regards', 'conduites', 'rejets']:
                result = session.execute(text(f"SELECT COUNT(*) as count FROM {table}"))
                stats[f"nb_{table}"] = result.fetchone()[0]

            # Statistiques géographiques
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

    def detecter_conduites_sans_regards(self) -> List[Dict[str, Any]]:
        """
        Détecte les conduites dont les regards amont ou aval n'existent pas dans la base.
        """
        anomalies = []

        with self.SessionLocal() as session:
            # Récupérer tous les codes de regards existants (avec strip pour éviter les espaces)
            result = session.execute(text("SELECT code FROM regards"))
            codes_regards = {str(row[0]).strip() for row in result.fetchall() if row[0] is not None}

            # Conduites avec problèmes de connexion
            result = session.execute(text("""
                SELECT c.id, c.fid, c.id_amont, c.id_aval, c.nom_voie
                FROM conduites c
                WHERE c.id_amont IS NOT NULL OR c.id_aval IS NOT NULL
            """))

            for row in result.fetchall():
                # Nettoyer les IDs de la conduite pour comparaison
                id_amont = str(row[2]).strip() if row[2] else None
                id_aval = str(row[3]).strip() if row[3] else None

                manque_amont = id_amont and id_amont not in codes_regards
                manque_aval = id_aval and id_aval not in codes_regards

                if manque_amont or manque_aval:
                    anomalie = {
                        "type": "conduite_sans_regard",
                        "id_conduite": row[0],
                        "fid": row[1],
                        "nom_voie": row[4],
                        "id_amont_manquant": id_amont if manque_amont else None,
                        "id_aval_manquant": id_aval if manque_aval else None,
                        "severite": "majeure",
                        "description": f"Regard amont ({id_amont}) ou aval ({id_aval}) introuvable"
                    }
                    lon, lat = self._get_coords_for_anomalie(session, anomalie)
                    if lon is not None and lat is not None:
                        anomalie["longitude"] = lon
                        anomalie["latitude"] = lat
                    anomalies.append(anomalie)

        print(f"🔍 Conduites sans regards: {len(anomalies)} détectées")
        return anomalies

    def detecter_troncons_orphelins(self) -> List[Dict[str, Any]]:
        """
        Détecte les tronçons qui ne sont connectés à aucun autre élément.
        """
        anomalies = []

        with self.SessionLocal() as session:
            # Récupérer les connexions existantes
            result = session.execute(text("SELECT DISTINCT id_amont FROM conduites WHERE id_amont IS NOT NULL"))
            connexions_amont = {row[0] for row in result.fetchall()}

            result = session.execute(text("SELECT DISTINCT id_aval FROM conduites WHERE id_aval IS NOT NULL"))
            connexions_aval = {row[0] for row in result.fetchall()}

            result = session.execute(text("SELECT code FROM regards"))
            codes_regards = {row[0] for row in result.fetchall()}

            # Trouver les tronçons orphelins
            result = session.execute(text("""
                SELECT c.id, c.fid, c.id_amont, c.id_aval
                FROM conduites c
            """))

            for row in result.fetchall():
                id_amont = row[2]
                id_aval = row[3]

                # Vérifier si le tronçon est connecté
                est_connecte_amont = id_amont and (id_amont in connexions_aval or id_amont in codes_regards)
                est_connecte_aval = id_aval and (id_aval in connexions_amont or id_aval in codes_regards)

                if not est_connecte_amont and not est_connecte_aval:
                    anomalie = {
                        "type": "troncon_orphelin",
                        "id_conduite": row[0],
                        "fid": row[1],
                        "id_amont": id_amont,
                        "id_aval": id_aval,
                        "severite": "mineure"
                    }
                    # Ajouter les coordonnées (utilisant id_amont ou id_aval comme regard)
                    lon, lat = self._get_coords_for_anomalie(session, anomalie)
                    if lon is not None and lat is not None:
                        anomalie["longitude"] = lon
                        anomalie["latitude"] = lat
                    anomalies.append(anomalie)

        print(f"🔍 Tronçons orphelins: {len(anomalies)} détectés")
        return anomalies

    def detecter_champs_manquants(self) -> List[Dict[str, Any]]:
        """
        Détecte les champs obligatoires manquants.
        """
        anomalies = []

        with self.SessionLocal() as session:
            # Champs manquants dans conduites
            result = session.execute(text("""
                SELECT id, fid, diametre, longueur, materiau, prof_fe_am, prof_fe_av
                FROM conduites
                WHERE diametre IS NULL OR diametre = 0
                   OR longueur IS NULL OR longueur = 0
                   OR materiau IS NULL OR materiau = ''
                   OR prof_fe_am IS NULL
                   OR prof_fe_av IS NULL
            """))

            for row in result.fetchall():
                champs_manquants = []
                if row[2] is None or row[2] == 0: champs_manquants.append("diamètre")  # diametre
                if row[3] is None or row[3] == 0: champs_manquants.append("longueur")  # longueur
                if row[4] is None or row[4] == '': champs_manquants.append("matériau")  # materiau
                if row[5] is None: champs_manquants.append("profondeur amont")  # prof_fe_am
                if row[6] is None: champs_manquants.append("profondeur aval")  # prof_fe_av

                if champs_manquants:
                    anomalie = {
                        "type": "champs_manquants_conduite",
                        "id_conduite": row[0],
                        "fid": row[1],
                        "champs_manquants": champs_manquants,
                        "severite": "majeure" if "diamètre" in champs_manquants else "mineure"
                    }
                    # Pour les coordonnées, essayer de trouver un regard lié
                    # Pour POC, on pourrait utiliser une requête pour le centroïde, mais pour simplifier, utiliser id_amont/id_aval si disponibles
                    # Ici, on laisse la fonction _get_coords_for_anomalie gérer
                    lon, lat = self._get_coords_for_anomalie(session, anomalie)
                    if lon is not None and lat is not None:
                        anomalie["longitude"] = lon
                        anomalie["latitude"] = lat
                    anomalies.append(anomalie)

            # Champs manquants dans regards
            result = session.execute(text("""
                SELECT id, code, profondeur, diametre
                FROM regards
                WHERE profondeur IS NULL OR diametre IS NULL
            """))

            for row in result.fetchall():
                champs_manquants = []
                if row[2] is None: champs_manquants.append("profondeur")  # profondeur
                if row[3] is None: champs_manquants.append("diamètre")    # diametre

                if champs_manquants:
                    anomalie = {
                        "type": "champs_manquants_regard",
                        "id_regard": row[0],
                        "code": row[1],
                        "champs_manquants": champs_manquants,
                        "severite": "mineure"
                    }
                    lon, lat = self._get_coords_for_anomalie(session, anomalie)
                    if lon is not None and lat is not None:
                        anomalie["longitude"] = lon
                        anomalie["latitude"] = lat
                    anomalies.append(anomalie)

        print(f"🔍 Champs manquants: {len(anomalies)} éléments affectés")
        return anomalies

    def detecter_geometries_invalides(self) -> List[Dict[str, Any]]:
        """
        Détecte les géométries invalides (coordonnées nulles, hors limites, etc.)
        """
        anomalies = []

        with self.SessionLocal() as session:
            # Coordonnées invalides dans regards
            result = session.execute(text("""
                SELECT 'regard' as type_element, id, code as identifiant,
                       longitude, latitude
                FROM regards
                WHERE longitude IS NULL OR latitude IS NULL
                   OR longitude < -180 OR longitude > 180
                   OR latitude < -90 OR latitude > 90
                   OR (longitude = 0 AND latitude = 0)
            """))

            for row in result.fetchall():
                anomalie = {
                    "type": "geometrie_invalide",
                    "type_element": row[0],
                    "id": row[1],
                    "identifiant": row[2],
                    "longitude": row[3],
                    "latitude": row[4],
                    "probleme": "coordonnées nulles ou hors limites" if row[3] is None else "coordonnées à zéro",
                    "severite": "majeure"
                }
                anomalies.append(anomalie)

            # Coordonnées invalides dans rejets
            result = session.execute(text("""
                SELECT 'rejet' as type_element, id, nom as identifiant,
                       longitude, latitude
                FROM rejets
                WHERE longitude IS NULL OR latitude IS NULL
                   OR longitude < -180 OR longitude > 180
                   OR latitude < -90 OR latitude > 90
                   OR (longitude = 0 AND latitude = 0)
            """))

            for row in result.fetchall():
                anomalie = {
                    "type": "geometrie_invalide",
                    "type_element": row[0],
                    "id": row[1],
                    "identifiant": row[2],
                    "longitude": row[3],
                    "latitude": row[4],
                    "probleme": "coordonnées nulles ou hors limites" if row[3] is None else "coordonnées à zéro",
                    "severite": "majeure"
                }
                anomalies.append(anomalie)

        print(f"🔍 Géométries invalides: {len(anomalies)} éléments affectés")
        return anomalies

    def detecter_pentes_suspectes(self) -> List[Dict[str, Any]]:
        """
        Détecte les pentes suspectes (négatives, trop fortes, etc.)
        """
        anomalies = []

        with self.SessionLocal() as session:
            result = session.execute(text("""
                SELECT id, fid, prof_fe_am, prof_fe_av, longueur
                FROM conduites
                WHERE prof_fe_am IS NOT NULL AND prof_fe_av IS NOT NULL
                  AND longueur IS NOT NULL AND longueur > 0
            """))

            for row in result.fetchall():
                prof_am = row[2]  # prof_fe_am
                prof_av = row[3]  # prof_fe_av
                longueur = row[4]  # longueur

                if longueur > 0:
                    pente = ((prof_am - prof_av) / longueur) * 100

                    # Pente négative (contre le sens de l'écoulement)
                    if pente < 0:
                        anomalie = {
                            "type": "pente_negative",
                            "id_conduite": row[0],
                            "fid": row[1],
                            "pente_pourcent": pente,
                            "severite": "critique"
                        }
                        lon, lat = self._get_coords_for_anomalie(session, anomalie)
                        if lon is not None and lat is not None:
                            anomalie["longitude"] = lon
                            anomalie["latitude"] = lat
                        anomalies.append(anomalie)
                    # Pente trop forte (> 50%)
                    elif pente > 50:
                        anomalie = {
                            "type": "pente_trop_forte",
                            "id_conduite": row[0],
                            "fid": row[1],
                            "pente_pourcent": pente,
                            "severite": "majeure"
                        }
                        lon, lat = self._get_coords_for_anomalie(session, anomalie)
                        if lon is not None and lat is not None:
                            anomalie["longitude"] = lon
                            anomalie["latitude"] = lat
                        anomalies.append(anomalie)

        print(f"🔍 Pentes suspectes: {len(anomalies)} conduites affectées")
        return anomalies

    def _get_coords_for_anomalie(self, session, anomalie: Dict[str, Any]) -> Tuple[float, float]:
        """Récupère les coordonnées pour une anomalie donnée."""
        if anomalie["type"] == "incoherence_profondeur":
            # Pour incoherence_profondeur, utiliser le point_connexion (regard)
            point_connexion = anomalie.get("point_connexion")
            if point_connexion:
                result = session.execute(text("SELECT longitude, latitude FROM regards WHERE code = :code"), {"code": str(point_connexion)})
                row = result.fetchone()
                if row and row[0] is not None and row[1] is not None:
                    return row[0], row[1]
        elif anomalie["type"] == "conduite_sans_regard":
            # Utiliser id_amont_manquant ou id_aval_manquant
            regard_id = anomalie.get("id_amont_manquant") or anomalie.get("id_aval_manquant")
            if regard_id:
                result = session.execute(text("SELECT longitude, latitude FROM regards WHERE code = :code"), {"code": str(regard_id)})
                row = result.fetchone()
                if row and row[0] is not None and row[1] is not None:
                    return row[0], row[1]
        elif anomalie["type"] in ["troncon_orphelin", "champs_manquants_conduite", "pente_negative", "pente_trop_forte"]:
            # Utiliser id_conduite ou fid pour centroïde de la conduite
            conduite_id = anomalie.get("id_conduite") or anomalie.get("fid")
            if conduite_id:
                # Pour simplifier, prendre les coordonnées de l'amont ou aval s'ils existent
                # Sinon, on pourrait calculer le centroïde, mais pour POC, utiliser un regard lié
                if anomalie["type"] == "troncon_orphelin":
                    # Essayer id_amont ou id_aval comme regard
                    regard_id = anomalie.get("id_amont") or anomalie.get("id_aval")
                    if regard_id:
                        result = session.execute(text("SELECT longitude, latitude FROM regards WHERE code = :code"), {"code": str(regard_id)})
                        row = result.fetchone()
                        if row and row[0] is not None and row[1] is not None:
                            return row[0], row[1]
                # Sinon, on pourrait faire une requête plus complexe pour le centroïde
        elif anomalie["type"] == "champs_manquants_regard":
            code = anomalie.get("code")
            if code:
                result = session.execute(text("SELECT longitude, latitude FROM regards WHERE code = :code"), {"code": str(code)})
                row = result.fetchone()
                if row and row[0] is not None and row[1] is not None:
                    return row[0], row[1]
        elif anomalie["type"] == "geometrie_invalide":
            if anomalie.get("type_element") == "regard":
                identifiant = anomalie.get("identifiant")
                if identifiant:
                    result = session.execute(text("SELECT longitude, latitude FROM regards WHERE code = :code"), {"code": str(identifiant)})
                    row = result.fetchone()
                    if row and row[0] is not None and row[1] is not None:
                        return row[0], row[1]
        return None, None

    def detecter_incoherences_amont_aval(self) -> List[Dict[str, Any]]:
        """
        Détecte les incohérences entre connexions amont/aval.
        """
        anomalies = []

        with self.SessionLocal() as session:
            # Vérifier que les conduites connectées ont des profondeurs cohérentes
            result = session.execute(text("""
                SELECT c1.id as id_conduite1, c1.fid as fid1, c1.id_aval,
                       c2.id as id_conduite2, c2.fid as fid2, c2.id_amont,
                       c1.prof_fe_av as prof_c1_aval, c2.prof_fe_am as prof_c2_amont
                FROM conduites c1
                JOIN conduites c2 ON c1.id_aval = c2.id_amont
                WHERE c1.prof_fe_av IS NOT NULL AND c2.prof_fe_am IS NOT NULL
                  AND ABS(c1.prof_fe_av - c2.prof_fe_am) > 0.5
            """))

            for row in result.fetchall():
                anomalie = {
                    "type": "incoherence_profondeur",
                    "id_conduite1": row[0],
                    "fid1": row[1],
                    "id_conduite2": row[3],
                    "fid2": row[4],
                    "point_connexion": row[2],
                    "prof_aval_c1": row[6],
                    "prof_amont_c2": row[7],
                    "difference": abs(row[6] - row[7]),
                    "severite": "majeure"
                }
                # Ajouter les coordonnées
                lon, lat = self._get_coords_for_anomalie(session, anomalie)
                if lon is not None and lat is not None:
                    anomalie["longitude"] = lon
                    anomalie["latitude"] = lat
                anomalies.append(anomalie)

        print(f"🔍 Incohérences amont/aval: {len(anomalies)} connexions problématiques")
        return anomalies

    def calculer_scores_qualite(self) -> Dict[str, Any]:
        """
        Calcule les scores de qualité par commune, bassin, et type d'objet.
        """
        scores = {}

        with self.SessionLocal() as session:
            # Score par commune
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
                score = (row[2] / row[1]) * 100 if row[1] > 0 else 0  # regards_complets / total_regards
                scores['par_commune'].append({
                    "commune": row[0],
                    "score_qualite": round(score, 1),
                    "regards_complets": row[2],
                    "total_regards": row[1]
                })

        # Score global (calculé après avoir détecté toutes les anomalies)
        total_anomalies = sum(len(anomalies) for anomalies in [
            self.detecter_conduites_sans_regards(),
            self.detecter_troncons_orphelins(),
            self.detecter_champs_manquants(),
            self.detecter_geometries_invalides(),
            self.detecter_pentes_suspectes(),
            self.detecter_incoherences_amont_aval()
        ])

        stats_globales = self._get_statistiques_globales()
        total_elements = (
            stats_globales.get('nb_regards', 0) +
            stats_globales.get('nb_conduites', 0) +
            stats_globales.get('nb_rejets', 0)
        )

        score_global = ((total_elements - total_anomalies) / total_elements) * 100 if total_elements > 0 else 0

        scores['global'] = {
            "score_qualite": round(score_global, 1),
            "total_elements": total_elements,
            "total_anomalies": total_anomalies
        }

        print(f"📊 Scores de qualité calculés - Score global: {scores['global']['score_qualite']}%")
        return scores

    def exporter_rapport_csv(self, rapport: Dict[str, Any], fichier_sortie: str = "rapport_qualite_reseau.csv"):
        """
        Exporte le rapport d'anomalies au format CSV.
        """
        anomalies = []

        # Aplatir toutes les anomalies
        for categorie, liste_anomalies in rapport['anomalies'].items():
            for anomalie in liste_anomalies:
                anomalie['categorie'] = categorie
                anomalies.append(anomalie)

        if anomalies:
            df = pd.DataFrame(anomalies)
            df.to_csv(fichier_sortie, index=False, encoding='utf-8-sig')
            print(f"💾 Rapport exporté: {fichier_sortie} ({len(anomalies)} anomalies)")
        else:
            print("✅ Aucune anomalie détectée - pas d'export nécessaire")

    def fermer_connexion(self):
        """Ferme la connexion à la base de données."""
        if hasattr(self, 'engine'):
            self.engine.dispose()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.fermer_connexion()


def analyser_qualite_reseau(exporter_csv: bool = True):
    """
    Fonction principale pour analyser la qualité du réseau.
    Utilisable en ligne de commande ou import.
    """
    try:
        with QualiteReseau() as analyseur:
            rapport = analyseur.analyser_reseau_complet()

            print("\n" + "="*60)
            print("RAPPORT DE QUALITÉ DU RÉSEAU D'ASSAINISSEMENT")
            print("="*60)
            print(f"Date d'analyse: {rapport['date_analyse']}")
            print(f"Score global: {rapport['scores_qualite']['global']['score_qualite']}%")
            print(f"Total éléments: {rapport['scores_qualite']['global']['total_elements']}")
            print(f"Total anomalies: {rapport['scores_qualite']['global']['total_anomalies']}")

            print("\nDÉTAIL DES ANOMALIES:")
            for categorie, anomalies in rapport['anomalies'].items():
                print(f"- {categorie}: {len(anomalies)} anomalies")

            if exporter_csv:
                analyseur.exporter_rapport_csv(rapport)

            return rapport

    except Exception as e:
        print(f"❌ Erreur lors de l'analyse: {e}")
        return None


if __name__ == "__main__":
    # Analyse en ligne de commande
    analyser_qualite_reseau()