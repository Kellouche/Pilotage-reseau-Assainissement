# -*- coding: utf-8 -*-
"""
================================================================================
Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
Auteur : Dr Abdelhakim KELLOUCHE
Date de création : 2026-11-27
Date de modification : 2026-11-27
Objet : Detecteurs qualite reseau — connectivite et champs — mixin de src/qualite_reseau.py (règle modularité ≤600 lignes)
================================================================================
"""

from typing import Any, Dict, List

from sqlalchemy import text


class QualiteReseauConnectivite:
    """Détecteurs de connectivité/topologie (mixine de QualiteReseau)."""

    def detecter_conduites_sans_regards(self, ids_conduites: List[int] = None) -> List[Dict[str, Any]]:
        anomalies = []

        with self.SessionLocal() as session:
            result = session.execute(text("SELECT code FROM regards"))
            codes_regards = {str(row[0]).strip() for row in result.fetchall() if row[0] is not None}

            sql = """
                SELECT c.id, c.fid, c.id_amont, c.id_aval, c.nom_voie
                FROM conduites c
                WHERE c.id_amont IS NOT NULL OR c.id_aval IS NOT NULL
            """
            params = {}
            if ids_conduites:
                placeholders = ",".join([f":id_{i}" for i in range(len(ids_conduites))])
                sql += f" AND c.id IN ({placeholders})"
                for i, cid in enumerate(ids_conduites):
                    params[f"id_{i}"] = cid

            result = session.execute(text(sql), params if params else {})

            for row in result.fetchall():
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

        print(f"Conduites sans regards: {len(anomalies)} detectees")
        return anomalies

    def detecter_troncons_orphelins(self, ids_conduites: List[int] = None) -> List[Dict[str, Any]]:
        anomalies = []

        with self.SessionLocal() as session:
            result = session.execute(text("SELECT DISTINCT id_amont FROM conduites WHERE id_amont IS NOT NULL"))
            connexions_amont = {str(row[0]).strip() for row in result.fetchall() if row[0] is not None}

            result = session.execute(text("SELECT DISTINCT id_aval FROM conduites WHERE id_aval IS NOT NULL"))
            connexions_aval = {str(row[0]).strip() for row in result.fetchall() if row[0] is not None}

            result = session.execute(text("SELECT code FROM regards"))
            codes_regards = {str(row[0]).strip() for row in result.fetchall() if row[0] is not None}

            sql = "SELECT c.id, c.fid, c.id_amont, c.id_aval FROM conduites c"
            params = {}
            if ids_conduites:
                placeholders = ",".join([f":id_{i}" for i in range(len(ids_conduites))])
                sql += f" WHERE c.id IN ({placeholders})"
                for i, cid in enumerate(ids_conduites):
                    params[f"id_{i}"] = cid

            result = session.execute(text(sql), params if params else {})

            for row in result.fetchall():
                id_amont = str(row[2]).strip() if row[2] is not None else None
                id_aval = str(row[3]).strip() if row[3] is not None else None

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
                    lon, lat = self._get_coords_for_anomalie(session, anomalie)
                    if lon is not None and lat is not None:
                        anomalie["longitude"] = lon
                        anomalie["latitude"] = lat
                    anomalies.append(anomalie)

        print(f"Troncons orphelins: {len(anomalies)} detectes")
        return anomalies

    def detecter_champs_manquants(self, ids_conduites: List[int] = None) -> List[Dict[str, Any]]:
        anomalies = []

        with self.SessionLocal() as session:
            sql = """
                SELECT id, fid, diametre, longueur, materiau, prof_fe_am, prof_fe_av
                FROM conduites
                WHERE diametre IS NULL OR diametre = 0
                   OR longueur IS NULL OR longueur = 0
                   OR materiau IS NULL OR materiau = ''
                   OR prof_fe_am IS NULL
                   OR prof_fe_av IS NULL
            """
            params = {}
            if ids_conduites:
                placeholders = ",".join([f":id_{i}" for i in range(len(ids_conduites))])
                sql += f" AND id IN ({placeholders})"
                for i, cid in enumerate(ids_conduites):
                    params[f"id_{i}"] = cid

            result = session.execute(text(sql), params if params else {})

            for row in result.fetchall():
                champs_manquants = []
                if row[2] is None or row[2] == 0: champs_manquants.append("diamètre")
                if row[3] is None or row[3] == 0: champs_manquants.append("longueur")
                if row[4] is None or row[4] == '': champs_manquants.append("matériau")
                if row[5] is None: champs_manquants.append("profondeur amont")
                if row[6] is None: champs_manquants.append("profondeur aval")

                if champs_manquants:
                    anomalie = {
                        "type": "champs_manquants_conduite",
                        "id_conduite": row[0],
                        "fid": row[1],
                        "champs_manquants": champs_manquants,
                        "severite": "majeure" if "diamètre" in champs_manquants else "mineure"
                    }
                    lon, lat = self._get_coords_for_anomalie(session, anomalie)
                    if lon is not None and lat is not None:
                        anomalie["longitude"] = lon
                        anomalie["latitude"] = lat
                    anomalies.append(anomalie)

            result = session.execute(text("""
                SELECT id, code, profondeur, diametre
                FROM regards
                WHERE profondeur IS NULL OR diametre IS NULL
            """))

            for row in result.fetchall():
                champs_manquants = []
                if row[2] is None: champs_manquants.append("profondeur")
                if row[3] is None: champs_manquants.append("diamètre")

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

        print(f"Champs manquants: {len(anomalies)} elements affectes")
        return anomalies
