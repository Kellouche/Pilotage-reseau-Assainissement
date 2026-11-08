"""
================================================================================
Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
Auteur : Dr Abdelhakim KELLOUCHE
Date de création : 2026-04-20
Date de modification : 2026-11-08
Objet : Validateur de cohérence topologique et connectivité hydraulique
================================================================================
"""

from typing import Dict, List, Any, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import text
import math


class ValidateurTopologie:
    """Validateur des connexions topologiques du réseau."""

    TOLERANCE_PROFONDEUR = 0.50
    DISTANCE_DOUBLONS = 2.0
    
    def __init__(self, session: Session):
        self.session = session

    def valider_coherence_profondeurs(self) -> List[Dict[str, Any]]:
        anomalies = []
        
        query = """
        SELECT 
            c.id as id_conduite, c.fid as fid_conduite, c.id_amont, c.id_aval,
            c.prof_fe_am, c.prof_fe_av, c.nom_voie,
            r_aval.profondeur as prof_noeud_aval,
            r_amont.profondeur as prof_noeud_amont
        FROM conduites c
        LEFT JOIN regards r_amont ON CAST(r_amont.code AS TEXT) = CAST(c.id_amont AS TEXT)
        LEFT JOIN regards r_aval ON CAST(r_aval.code AS TEXT) = CAST(c.id_aval AS TEXT)
        WHERE c.prof_fe_av IS NOT NULL AND c.prof_fe_am IS NOT NULL
          AND (r_aval.profondeur IS NOT NULL OR r_amont.profondeur IS NOT NULL)
        """
        
        result = self.session.execute(text(query))
        
        for row in result.fetchall():
            id_conduite, fid, id_amont, id_aval, prof_am, prof_av, nom_voie, prof_noeud_av, prof_noeud_am = row
            
            if id_aval and prof_noeud_av is not None and prof_av is not None:
                diff_aval = abs(float(prof_av) - float(prof_noeud_av))
                if diff_aval > self.TOLERANCE_PROFONDEUR:
                    anomalies.append({
                        "type": "incoherence_profondeur_topologie",
                        "severite": "majeure",
                        "id_conduite": id_conduite,
                        "fid": fid,
                        "id_noeud": id_aval,
                        "nom_voie": nom_voie,
                        "description": f"Dénivellation excessive au nœud aval : {diff_aval:.2f}m",
                        "details": {
                            "profondeur_fin_conduite": float(prof_av),
                            "profondeur_noeud": float(prof_noeud_av),
                            "difference": diff_aval,
                            "tolerance": self.TOLERANCE_PROFONDEUR
                        }
                    })
            
            if id_amont and prof_noeud_am is not None and prof_am is not None:
                diff_amont = abs(float(prof_am) - float(prof_noeud_am))
                if diff_amont > self.TOLERANCE_PROFONDEUR:
                    anomalies.append({
                        "type": "incoherence_profondeur_topologie",
                        "severite": "majeure",
                        "id_conduite": id_conduite,
                        "fid": fid,
                        "id_noeud": id_amont,
                        "nom_voie": nom_voie,
                        "description": f"Dénivellation excessive au nœud amont : {diff_amont:.2f}m",
                        "details": {
                            "profondeur_fin_conduite": float(prof_am),
                            "profondeur_noeud": float(prof_noeud_am),
                            "difference": diff_amont,
                            "tolerance": self.TOLERANCE_PROFONDEUR
                        }
                    })
        
        print(f"Coherence profondeurs : {len(anomalies)} anomalies detectees")
        return anomalies

    def valider_chevauchements_geometriques(self) -> List[Dict[str, Any]]:
        anomalies = []
        
        query = """
        SELECT 
            c.id, c.fid, c.nom_voie,
            ST_X(ST_StartPoint(ST_GeomFromGeoJSON(c.geom_json))) as start_x,
            ST_Y(ST_StartPoint(ST_GeomFromGeoJSON(c.geom_json))) as start_y,
            ST_X(ST_EndPoint(ST_GeomFromGeoJSON(c.geom_json))) as end_x,
            ST_Y(ST_EndPoint(ST_GeomFromGeoJSON(c.geom_json))) as end_y
        FROM conduites c
        WHERE c.geom_json IS NOT NULL
        """
        
        try:
            result = self.session.execute(text(query))
            conduites = list(result.fetchall())
        except Exception:
            print("PostGIS non disponible pour chevauchements, fallback WKT utilise")
            query_fallback = """
            SELECT id, fid, nom_voie, geometry_wkt
            FROM conduites
            WHERE geometry_wkt IS NOT NULL
            """
            result = self.session.execute(text(query_fallback))
            conduites = []
            import re
            for row in result.fetchall():
                id_c, fid_c, nom_c, wkt = row
                if wkt:
                    coords = re.findall(r'([-+]?\d*\.\d+|\d+)\s+([-+]?\d*\.\d+|\d+)', wkt)
                    if len(coords) >= 2:
                        try:
                            sx, sy = float(coords[0][0]), float(coords[0][1])
                            ex, ey = float(coords[-1][0]), float(coords[-1][1])
                            conduites.append((id_c, fid_c, nom_c, sx, sy, ex, ey))
                        except ValueError:
                            pass
        
        GRID_SIZE = 0.0001
        grid = {}
        
        for c in conduites:
            id_c, fid_c, nom_c, sx, sy, ex, ey = c
            key = (int(sx / GRID_SIZE), int(sy / GRID_SIZE))
            if key not in grid:
                grid[key] = []
            grid[key].append((sx, sy, ex, ey, id_c, fid_c, nom_c))
        
        checked_pairs = set()
        
        for (gx, gy), items in grid.items():
            for dx in [-1, 0, 1]:
                for dy in [-1, 0, 1]:
                    neighbor_key = (gx + dx, gy + dy)
                    if neighbor_key not in grid:
                        continue
                    for c1 in items:
                        sx1, sy1, ex1, ey1, id1, fid1, nom1 = c1
                        for c2 in grid[neighbor_key]:
                            sx2, sy2, ex2, ey2, id2, fid2, nom2 = c2
                            pair_key = (min(id1, id2), max(id1, id2))
                            if pair_key in checked_pairs or id1 >= id2:
                                continue
                            checked_pairs.add(pair_key)
                            
                            dist_start = self._distance_euclidienne(sx1, sy1, sx2, sy2)
                            dist_end = self._distance_euclidienne(ex1, ey1, ex2, ey2)
                            dist_cross = self._distance_euclidienne(sx1, sy1, ex2, ey2)
                            
                            if dist_start < 0.01 or dist_end < 0.01 or dist_cross < 0.01:
                                anomalies.append({
                                    "type": "chevauchement_geometrique",
                                    "severite": "majeure",
                                    "id_conduite_1": id1,
                                    "id_conduite_2": id2,
                                    "nom_voie_1": nom1,
                                    "nom_voie_2": nom2,
                                    "description": f"Chevauchement géométrique détecté entre {nom1} et {nom2}",
                                    "distance_min": round(min(dist_start, dist_end, dist_cross), 3),
                                    "longitude": (sx1 + sx2) / 2,
                                    "latitude": (sy1 + sy2) / 2
                                })
        
        print(f"Chevauchements geometriques : {len(anomalies)} anomalies detectees")
        return anomalies

    def detecter_doublons_regards(self) -> List[Dict[str, Any]]:
        anomalies = []
        
        query = """
        SELECT id, code, profondeur, commune, latitude, longitude
        FROM regards
        WHERE latitude IS NOT NULL AND longitude IS NOT NULL
        """
        
        result = self.session.execute(text(query))
        regards = list(result.fetchall())
        
        GRID_SIZE_DEGREES = 0.0001
        grid = {}
        
        for r in regards:
            id_r, code_r, prof_r, comm_r, lat_r, lon_r = r
            grid_key = (int(lon_r / GRID_SIZE_DEGREES), int(lat_r / GRID_SIZE_DEGREES), comm_r or '')
            if grid_key not in grid:
                grid[grid_key] = []
            grid[grid_key].append(r)
        
        checked_pairs = set()
        
        for (gx, gy, comm), items in grid.items():
            for r1 in items:
                id1, code1, prof1, comm1, lat1, lon1 = r1
                for dx in [-1, 0, 1]:
                    for dy in [-1, 0, 1]:
                        neighbor_key = (gx + dx, gy + dy, comm)
                        if neighbor_key not in grid:
                            continue
                        for r2 in grid[neighbor_key]:
                            id2, code2, prof2, comm2, lat2, lon2 = r2
                            pair_key = (min(id1, id2), max(id1, id2))
                            if pair_key in checked_pairs or id1 >= id2:
                                continue
                            checked_pairs.add(pair_key)
                            
                            dist = self._distance_euclidienne(float(lon1), float(lat1), float(lon2), float(lat2))
                            
                            if dist < self.DISTANCE_DOUBLONS and code1 != code2:
                                anomalies.append({
                                    "type": "doublon_regards",
                                    "severite": "mineure",
                                    "id_regard_1": id1,
                                    "code_1": code1,
                                    "profondeur_1": float(prof1) if prof1 else None,
                                    "id_regard_2": id2,
                                    "code_2": code2,
                                    "profondeur_2": float(prof2) if prof2 else None,
                                    "commune": comm1,
                                    "description": f"Doublons suspects : {code1} et {code2} à {dist:.1f}m",
                                    "distance": round(dist, 2),
                                    "longitude": (float(lon1) + float(lon2)) / 2,
                                    "latitude": (float(lat1) + float(lat2)) / 2
                                })
        
        print(f"Doublons regards : {len(anomalies)} anomalies detectees")
        return anomalies

    @staticmethod
    def _distance_euclidienne(x1: float, y1: float, x2: float, y2: float) -> float:
        try:
            x1, y1, x2, y2 = float(x1), float(y1), float(x2), float(y2)
            return math.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2) * 111.32 * 1000
        except (ValueError, TypeError):
            return float('inf')

    @staticmethod
    def _distance_haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        try:
            R = 6371000
            lat1_rad = math.radians(float(lat1))
            lat2_rad = math.radians(float(lat2))
            delta_lat = math.radians(float(lat2) - float(lat1))
            delta_lon = math.radians(float(lon2) - float(lon1))
            a = math.sin(delta_lat / 2) ** 2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lon / 2) ** 2
            c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
            return R * c
        except (ValueError, TypeError):
            return float('inf')
