# -*- coding: utf-8 -*-
"""
================================================================================
Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
Auteur : Dr Abdelhakim KELLOUCHE
Date de création : 2026-11-27
Date de modification : 2026-11-27
Objet : Detecteurs qualite reseau — geometrie, pente, capacite, amont/aval — mixin de src/qualite_reseau.py (règle modularité ≤600 lignes)
================================================================================
"""

import math
from typing import Any, Dict, List, Tuple

from sqlalchemy import text


class QualiteReseauDetecteursPhysiques:
    """Détecteurs geométrie/pente/capacité (mixine de QualiteReseau)."""

    def detecter_geometries_invalides(self, ids_conduites: List[int] = None) -> List[Dict[str, Any]]:
        anomalies = []

        with self.SessionLocal() as session:
            sql = """
                SELECT 'regard' as type_element, id, code as identifiant, longitude, latitude
                FROM regards
                WHERE longitude IS NULL OR latitude IS NULL
                   OR longitude < -180 OR longitude > 180
                   OR latitude < -90 OR latitude > 90
                   OR (longitude = 0 AND latitude = 0)
            """
            params = {}
            if ids_conduites:
                placeholders = ",".join([f":id_{i}" for i in range(len(ids_conduites))])
                sql += f" AND id IN ({placeholders})"
                for i, cid in enumerate(ids_conduites):
                    params[f"id_{i}"] = cid

            result = session.execute(text(sql), params if params else {})

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

            where_geom = "WHERE (geometry_wkt IS NULL OR geometry_wkt = '')"
            try:
                session.execute(text("SELECT geom_json FROM conduites LIMIT 1"))
                where_geom += " AND (geom_json IS NULL OR geom_json = '')"
            except Exception:
                pass

            result = session.execute(text(f"""
                SELECT 'conduite' as type_element, id, fid as identifiant, NULL as longitude, NULL as latitude
                FROM conduites
                {where_geom}
            """))
            for row in result.fetchall():
                anomalies.append({
                    "type": "geometrie_invalide",
                    "type_element": row[0],
                    "id": row[1],
                    "identifiant": row[2],
                    "probleme": "géométrie absente",
                    "severite": "majeure"
                })

            result = session.execute(text("""
                SELECT 'rejet' as type_element, id, nom as identifiant, longitude, latitude
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

        print(f"Géométries invalides: {len(anomalies)} éléments affectés")
        return anomalies

    def detecter_pentes_suspectes(self, ids_conduites: List[int] = None) -> List[Dict[str, Any]]:
        anomalies = []

        with self.SessionLocal() as session:
            sql = """
                SELECT id, fid, prof_fe_am, prof_fe_av, longueur, nom_voie
                FROM conduites
                WHERE prof_fe_am IS NOT NULL AND prof_fe_av IS NOT NULL
                  AND longueur IS NOT NULL AND longueur > 0
            """
            params = {}
            if ids_conduites:
                placeholders = ",".join([f":id_{i}" for i in range(len(ids_conduites))])
                sql += f" AND id IN ({placeholders})"
                for i, cid in enumerate(ids_conduites):
                    params[f"id_{i}"] = cid

            result = session.execute(text(sql), params if params else {})

            for row in result.fetchall():
                id_conduite, fid, prof_am, prof_av, longueur, nom_voie = row

                if longueur > 0:
                    pente = ((prof_am - prof_av) / longueur) * 100

                    if pente < 0:
                        anomalie = {
                            "type": "pente_negative",
                            "id_conduite": id_conduite,
                            "fid": fid,
                            "nom_voie": nom_voie,
                            "pente_pourcent": round(pente, 3),
                            "severite": "critique",
                            "description": f"Pente négative ({pente:.2f}%) : inversion de sens hydraulique"
                        }
                        lon, lat = self._get_coords_for_anomalie(session, anomalie)
                        if lon is not None and lat is not None:
                            anomalie["longitude"] = lon
                            anomalie["latitude"] = lat
                        anomalies.append(anomalie)
                    elif pente > 50:
                        anomalie = {
                            "type": "pente_trop_forte",
                            "id_conduite": id_conduite,
                            "fid": fid,
                            "nom_voie": nom_voie,
                            "pente_pourcent": round(pente, 3),
                            "severite": "majeure",
                            "description": f"Pente excessive ({pente:.2f}%) : risque d'érosion et de décantation insuffisante"
                        }
                        lon, lat = self._get_coords_for_anomalie(session, anomalie)
                        if lon is not None and lat is not None:
                            anomalie["longitude"] = lon
                            anomalie["latitude"] = lat
                        anomalies.append(anomalie)
                    elif pente < 0.1:
                        # Pente trop faible pour l'auto-curage (< 0.1%)
                        anomalie = {
                            "type": "pente_trop_faible",
                            "id_conduite": id_conduite,
                            "fid": fid,
                            "nom_voie": nom_voie,
                            "pente_pourcent": round(pente, 3),
                            "severite": "majeure",
                            "description": f"Pente insuffisante ({pente:.2f}% < 0.1%) : risque de stagnation et de dépôts"
                        }
                        lon, lat = self._get_coords_for_anomalie(session, anomalie)
                        if lon is not None and lat is not None:
                            anomalie["longitude"] = lon
                            anomalie["latitude"] = lat
                        anomalies.append(anomalie)

        print(f"Pentes suspectes: {len(anomalies)} conduites affectées")
        return anomalies

    def detecter_sauts_pente(self, ids_conduites: List[int] = None) -> List[Dict[str, Any]]:
        """Détecte les sauts de pente brutaux (> 2m de dénivellation) entre
        conduites consécutives connectées (amont/aval)."""
        anomalies = []

        with self.SessionLocal() as session:
            sql = """
                SELECT c.id, c.fid, c.id_amont, c.id_aval, c.prof_fe_am, c.prof_fe_av, c.nom_voie
                FROM conduites c
                WHERE c.prof_fe_am IS NOT NULL AND c.prof_fe_av IS NOT NULL
            """
            params = {}
            if ids_conduites:
                placeholders = ",".join([f":id_{i}" for i in range(len(ids_conduites))])
                sql += f" AND c.id IN ({placeholders})"
                for i, cid in enumerate(ids_conduites):
                    params[f"id_{i}"] = cid

            result = session.execute(text(sql), params if params else {})

            conduites = {}
            conduites_par_amont = {}
            for row in result.fetchall():
                id_c, fid, id_amont, id_aval, prof_am, prof_av, nom_voie = row
                conduites[id_c] = {
                    'fid': fid,
                    'id_amont': id_amont,
                    'id_aval': id_aval,
                    'prof_am': float(prof_am),
                    'prof_av': float(prof_av),
                    'nom_voie': nom_voie
                }
                if id_amont is not None:
                    conduites_par_amont.setdefault(str(id_amont).strip(), []).append(id_c)

            # Pour chaque conduite, vérifier la connexion avec la suivante
            for id_c, c in conduites.items():
                id_aval = c['id_aval']
                ids_suivantes = conduites_par_amont.get(str(id_aval).strip(), []) if id_aval is not None else []
                for id_suivante in ids_suivantes:
                    c_suivante = conduites[id_suivante]
                    # Saut de pente = différence entre prof_av de c1 et prof_am de c2
                    saut = abs(c['prof_av'] - c_suivante['prof_am'])

                    if saut > 2.0:
                        anomalie = {
                            "type": "saut_pente",
                            "id_conduite_amont": id_c,
                            "fid_amont": c['fid'],
                            "id_conduite_aval": id_suivante,
                            "fid_aval": c_suivante['fid'],
                            "nom_voie": c['nom_voie'],
                            "prof_aval_amont": c['prof_av'],
                            "prof_amont_aval": c_suivante['prof_am'],
                            "saut_m": round(saut, 2),
                            "severite": "majeure" if saut > 5.0 else "mineure",
                            "description": f"Saut de pente de {saut:.2f}m entre conduites {c['fid']} et {c_suivante['fid']}"
                        }
                        # Positionner au point de connexion (regard aval de c1 / amont de c2)
                        lon, lat = self._get_coords_saut_pente(session, id_c, id_suivante)
                        if lon is not None and lat is not None:
                            anomalie["longitude"] = lon
                            anomalie["latitude"] = lat
                        anomalies.append(anomalie)

        print(f"Sauts de pente: {len(anomalies)} détectés")
        return anomalies

    def _get_coords_saut_pente(self, session, id_amont: int, id_aval: int) -> Tuple[float, float]:
        """Récupère les coordonnées du regard de connexion entre deux conduites."""
        try:
            result = session.execute(text("""
                SELECT r.longitude, r.latitude
                FROM regards r
                JOIN conduites c ON CAST(c.id_aval AS TEXT) = CAST(r.code AS TEXT)
                WHERE c.id = :cid
                LIMIT 1
            """), {"cid": id_amont})
            row = result.fetchone()
            if row and row[0] is not None and row[1] is not None:
                return row[0], row[1]
        except Exception:
            pass
        return None, None

    def detecter_capacite_debit(self, ids_conduites: List[int] = None) -> List[Dict[str, Any]]:
        """Détecte les conduites sous-dimensionnées selon la formule NP 650.

        Formule : Q_nominal = 3.1 * D^2.2  (D en mm, Q en L/s)
        Vérifie également la vitesse d'écoulement : 0.3 < V < 3.0 m/s
        """
        anomalies = []

        with self.SessionLocal() as session:
            sql = """
                SELECT id, fid, diametre, longueur, prof_fe_am, prof_fe_av, nom_voie
                FROM conduites
                WHERE diametre IS NOT NULL AND diametre > 0
                   AND prof_fe_am IS NOT NULL AND prof_fe_av IS NOT NULL
                   AND longueur IS NOT NULL AND longueur > 0
            """
            params = {}
            if ids_conduites:
                placeholders = ",".join([f":id_{i}" for i in range(len(ids_conduites))])
                sql += f" AND id IN ({placeholders})"
                for i, cid in enumerate(ids_conduites):
                    params[f"id_{i}"] = cid

            result = session.execute(text(sql), params if params else {})

            for row in result.fetchall():
                id_conduite, fid, diametre, longueur, prof_am, prof_av, nom_voie = row
                d_mm = float(diametre)
                d_m = d_mm / 1000.0
                l_m = float(longueur)

                # Formule NP 650 : Q_nominal (L/s) = 3.1 * D^2.2
                q_nominal_ls = 3.1 * (d_mm ** 2.2)

                # Section mouillée pour conduite circulaire pleine
                section_mouillee = (math.pi / 4.0) * (d_m ** 2)

                # Vitesse d'écoulement (m/s) = Q (m3/s) / section (m2)
                q_m3s = q_nominal_ls / 1000.0
                vitesse = q_m3s / section_mouillee if section_mouillee > 0 else 0

                # Pente (%)
                pente = ((float(prof_am) - float(prof_av)) / l_m) * 100 if l_m > 0 else 0

                severite = "mineure"
                problemes = []

                if vitesse < 0.3:
                    problemes.append(f"vitesse trop faible ({vitesse:.2f} m/s < 0.3 m/s)")
                    severite = "majeure"
                elif vitesse > 3.0:
                    problemes.append(f"vitesse trop forte ({vitesse:.2f} m/s > 3.0 m/s)")
                    severite = "majeure"

                if pente < 0.1:
                    problemes.append(f"pente insuffisante ({pente:.2f}% < 0.1%)")
                    if severite != "majeure":
                        severite = "majeure"

                if problemes:
                    anomalie = {
                        "type": "capacite_debit",
                        "id_conduite": id_conduite,
                        "fid": fid,
                        "nom_voie": nom_voie,
                        "diametre_mm": d_mm,
                        "longueur_m": l_m,
                        "q_nominal_ls": round(q_nominal_ls, 2),
                        "vitesse_mps": round(vitesse, 3),
                        "pente_pct": round(pente, 3),
                        "problemes": problemes,
                        "severite": severite
                    }
                    lon, lat = self._get_coords_for_anomalie(session, anomalie)
                    if lon is not None and lat is not None:
                        anomalie["longitude"] = lon
                        anomalie["latitude"] = lat
                    anomalies.append(anomalie)

        print(f"Capacite debitaire: {len(anomalies)} conduites sous-dimensionnees")
        return anomalies

    def _get_coords_for_anomalie(self, session, anomalie: Dict[str, Any]) -> Tuple[float, float]:
        if anomalie["type"] == "incoherence_profondeur":
            point_connexion = anomalie.get("point_connexion")
            if point_connexion:
                result = session.execute(text("SELECT longitude, latitude FROM regards WHERE code = :code"), {"code": str(point_connexion)})
                row = result.fetchone()
                if row and row[0] is not None and row[1] is not None:
                    return row[0], row[1]
        elif anomalie["type"] == "conduite_sans_regard":
            regard_id = anomalie.get("id_amont_manquant") or anomalie.get("id_aval_manquant")
            if regard_id:
                result = session.execute(text("SELECT longitude, latitude FROM regards WHERE code = :code"), {"code": str(regard_id)})
                row = result.fetchone()
                if row and row[0] is not None and row[1] is not None:
                    return row[0], row[1]
        elif anomalie["type"] in ["troncon_orphelin", "champs_manquants_conduite", "pente_negative", "pente_trop_forte", "pente_trop_faible", "capacite_debit"]:
            conduite_id = anomalie.get("id_conduite") or anomalie.get("fid")
            if conduite_id:
                if anomalie["type"] in ["troncon_orphelin", "capacite_debit"]:
                    # Pour capacite_debit, essayer de récupérer les coordonnées du regard amont ou aval
                    result = session.execute(text("""
                        SELECT c.id_amont, c.id_aval, r_am.longitude, r_am.latitude, r_av.longitude, r_av.latitude
                        FROM conduites c
                        LEFT JOIN regards r_am ON CAST(r_am.code AS TEXT) = CAST(c.id_amont AS TEXT)
                        LEFT JOIN regards r_av ON CAST(r_av.code AS TEXT) = CAST(c.id_aval AS TEXT)
                        WHERE c.id = :cid OR c.fid = :fid
                        LIMIT 1
                    """), {"cid": conduite_id, "fid": str(conduite_id)})
                    row = result.fetchone()
                    if row:
                        lon, lat = row[2], row[3]
                        if lon is None or lat is None:
                            lon, lat = row[4], row[5]
                        if lon is not None and lat is not None:
                            return lon, lat
                else:
                    regard_id = anomalie.get("id_amont") or anomalie.get("id_aval")
                    if regard_id:
                        result = session.execute(text("SELECT longitude, latitude FROM regards WHERE code = :code"), {"code": str(regard_id)})
                        row = result.fetchone()
                        if row and row[0] is not None and row[1] is not None:
                            return row[0], row[1]
        elif anomalie["type"] == "sauts_pente":
            # Récupérer les coordonnées du regard de connexion entre les deux conduites
            id_amont = anomalie.get("id_conduite_amont")
            id_aval = anomalie.get("id_conduite_aval")
            if id_amont:
                lon, lat = self._get_coords_saut_pente(session, id_amont, id_aval)
                if lon is not None and lat is not None:
                    return lon, lat
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
        anomalies = []

        with self.SessionLocal() as session:
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
                lon, lat = self._get_coords_for_anomalie(session, anomalie)
                if lon is not None and lat is not None:
                    anomalie["longitude"] = lon
                    anomalie["latitude"] = lat
                anomalies.append(anomalie)

        print(f"Incohérences amont/aval: {len(anomalies)} connexions problématiques")
        return anomalies
