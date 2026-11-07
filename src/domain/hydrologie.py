"""
Module de modélisation hydrologique pour SWMM 5.2.
Fichier : src/domain/hydrologie.py

Génère les sous-bassins versants élémentaires (Subcatchments) par décomposition
spatiale (Voronoï / Thiessen), calcule les paramètres physiques (surface, imperméabilisation,
largeur hydraulique, pente, infiltration selon Horton) et formate les sections SWMM .inp.
"""

import os
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")
os.environ.setdefault("OMP_NUM_THREADS", "1")

import re
from typing import Dict, Any, List, Optional
import math
import geopandas as gpd
import pandas as pd
from shapely.geometry import Point, Polygon, MultiPolygon, MultiPoint, mapping
from shapely.ops import voronoi_diagram, unary_union
from shapely import STRtree


def _identifiant_propre(val: Any, fallback: str = "N") -> str:
    """Normalise un identifiant pour SWMM sans espace ni nan."""
    if val is None or (isinstance(val, float) and (math.isnan(val) or pd.isna(val))):
        return fallback
    txt = str(val).strip()
    if txt.endswith('.0'):
        txt = txt[:-2]
    txt = re.sub(r'[\s;\'",]+', '_', txt).strip('_')
    if not txt or txt.lower() in ('nan', 'none', 'null'):
        return fallback
    return txt


class GenerateurHydrologie:
    """Générateur de sous-bassins versants et paramètres hydrologiques SWMM."""

    def __init__(
        self,
        tampon_buffer_m: float = 35.0,
        imperv_defaut: float = 70.0,
        f0_horton: float = 75.0,
        fc_horton: float = 10.0,
        k_horton: float = 4.0,
        n_imperv: float = 0.015,
        n_perv: float = 0.25,
        d_store_imperv: float = 1.5,
        d_store_perv: float = 5.0,
        pct_zero_imperv: float = 25.0
    ):
        self.tampon_buffer_m = tampon_buffer_m
        self.imperv_defaut = imperv_defaut
        self.f0_horton = f0_horton
        self.fc_horton = fc_horton
        self.k_horton = k_horton
        self.n_imperv = n_imperv
        self.n_perv = n_perv
        self.d_store_imperv = d_store_imperv
        self.d_store_perv = d_store_perv
        self.pct_zero_imperv = pct_zero_imperv

    def generer_sous_bassins(
        self,
        noeuds_gdf: gpd.GeoDataFrame,
        canalisations_gdf: gpd.GeoDataFrame,
        emprise_bassin: Optional[Polygon] = None,
        rain_gage: str = "RG1"
    ) -> gpd.GeoDataFrame:
        """
        Découpe le bassin en sous-bassins versants élémentaires autour de chaque regard.
        Optimisé avec index spatial STRtree et découpage local O(N log N).
        """
        if noeuds_gdf.empty:
            return gpd.GeoDataFrame()

        crs_source = noeuds_gdf.crs or "EPSG:32631"

        # 1. Extraction et validation des points de regards
        valid_rows = []
        points_list = []
        for idx, row in noeuds_gdf.iterrows():
            pt = row.geometry
            if isinstance(pt, Point) and not pt.is_empty:
                valid_rows.append((idx, row))
                points_list.append(pt)

        if not points_list:
            return gpd.GeoDataFrame()

        # 2. Construction instantanée du diagramme de Voronoï
        multipoints = MultiPoint(points_list)
        diagramme = voronoi_diagram(multipoints)
        cellules_voronoi = list(diagramme.geoms) if hasattr(diagramme, 'geoms') else [diagramme]

        # Calcul de l'Enveloppe Convexe Globale (Impluvium étendu total)
        convex_hull_globale = multipoints.convex_hull
        surface_globale_convexe_ha = round(float(convex_hull_globale.area) / 10000.0, 2) if convex_hull_globale else 0.0

        buf_m = float(self.tampon_buffer_m)

        # Construction de l'Enveloppe Urbaine Fermée (avec comblement automatique des îlots/cours intérieurs)
        emprise_urbaine = emprise_bassin
        if emprise_urbaine is None or emprise_urbaine.is_empty:
            raw_buffers = []
            if canalisations_gdf is not None and hasattr(canalisations_gdf, 'geometry') and not canalisations_gdf.empty:
                for g in canalisations_gdf.geometry:
                    if g is not None and not g.is_empty:
                        raw_buffers.append(g.buffer(buf_m))
            for pt in points_list:
                raw_buffers.append(pt.buffer(buf_m))

            if raw_buffers:
                try:
                    u_buf = unary_union(raw_buffers)
                    # Comblement des vides intérieurs (fermeture des pâtés de maisons)
                    if isinstance(u_buf, Polygon):
                        emprise_urbaine = Polygon(u_buf.exterior)
                    elif isinstance(u_buf, MultiPolygon):
                        emprise_urbaine = MultiPolygon([Polygon(p.exterior) for p in u_buf.geoms if p.area > 50.0])
                    else:
                        emprise_urbaine = u_buf
                except Exception:
                    emprise_urbaine = None

        # 3. Index spatial STRtree pour appariement 1-à-1 ultra-rapide (< 0.1s pour 10 000 points)
        cell_tree = STRtree(cellules_voronoi)
        pt_indices, cell_indices = cell_tree.query(points_list, predicate='intersects')
        pt_to_cell: Dict[int, Polygon] = {}
        for p_idx, c_idx in zip(pt_indices, cell_indices):
            if p_idx not in pt_to_cell:
                pt_to_cell[p_idx] = cellules_voronoi[c_idx]

        # 4. Découpage et enrichissement vectoriel (Voronoï fermé sans trous)
        sous_bassins_records = []
        seen_sb_ids = set()

        for i, (idx, row) in enumerate(valid_rows):
            pt = points_list[i]
            code_val = None
            for k in ['Code', 'code', 'id_noeud', 'swmm_id', 'id']:
                if k in row and row[k] is not None and not (isinstance(row[k], float) and pd.isna(row[k])):
                    code_val = row[k]
                    break
            noeud_id = _identifiant_propre(code_val, fallback=f"REG_{idx+1}")

            cell = pt_to_cell.get(i)
            if cell is not None and not cell.is_empty:
                if emprise_urbaine is not None and not emprise_urbaine.is_empty:
                    try:
                        clipped_cell = cell.intersection(emprise_urbaine)
                        if isinstance(clipped_cell, MultiPolygon):
                            sub_parts = [p for p in clipped_cell.geoms if p.contains(pt)]
                            clipped_cell = sub_parts[0] if sub_parts else max(clipped_cell.geoms, key=lambda p: p.area)
                        if clipped_cell.is_empty:
                            clipped_cell = pt.buffer(buf_m)
                    except Exception:
                        clipped_cell = cell.intersection(pt.buffer(buf_m))
                else:
                    clipped_cell = cell.intersection(pt.buffer(buf_m))
                if clipped_cell.is_empty:
                    clipped_cell = pt.buffer(5.0)
            else:
                clipped_cell = pt.buffer(buf_m)

            aire_m2 = round(float(clipped_cell.area), 2)
            aire_ha = max(round(aire_m2 / 10000.0, 4), 0.0001)
            largeur_m = max(round(math.sqrt(aire_m2), 2), 5.0)
            pente_pct = 0.5  # Pente minimale conventionnelle d'assainissement

            base_sb_id = f"SB_{noeud_id}"
            subcatchment_id = base_sb_id
            if subcatchment_id in seen_sb_ids:
                c_dup = 2
                while f"{base_sb_id}_{c_dup}" in seen_sb_ids:
                    c_dup += 1
                subcatchment_id = f"{base_sb_id}_{c_dup}"
            seen_sb_ids.add(subcatchment_id)

            sous_bassins_records.append({
                "subcatchment_id": subcatchment_id,
                "outlet": noeud_id,
                "rain_gage": rain_gage,
                "area_ha": aire_ha,
                "area_m2": aire_m2,
                "imperv_pct": self.imperv_defaut,
                "width_m": largeur_m,
                "slope_pct": pente_pct,
                "curblen_m": 0.0,
                # Infiltration Horton
                "f0": self.f0_horton,
                "fc": self.fc_horton,
                "decay_k": self.k_horton,
                "dry_time": 7.0,
                "max_infil": 0.0,
                # Subareas
                "n_imperv": self.n_imperv,
                "n_perv": self.n_perv,
                "d_store_imperv": self.d_store_imperv,
                "d_store_perv": self.d_store_perv,
                "pct_zero_imperv": self.pct_zero_imperv,
                "subarea_route": "OUTLET",
                "geometry": clipped_cell
            })

        gdf_res = gpd.GeoDataFrame(sous_bassins_records, crs=crs_source)
        total_urbaine_ha = round(float(gdf_res["area_ha"].sum()), 2) if not gdf_res.empty else 0.0
        gdf_res.attrs["total_urbaine_ha"] = total_urbaine_ha
        gdf_res.attrs["convexe_globale_ha"] = surface_globale_convexe_ha
        gdf_res.attrs["ratio_drainage_pct"] = round((total_urbaine_ha / surface_globale_convexe_ha) * 100.0, 1) if surface_globale_convexe_ha > 0 else 100.0
        return gdf_res

    @staticmethod
    def formater_sections_swmm(
        subcatchments_gdf: gpd.GeoDataFrame,
        rain_gage_name: str = "RG1"
    ) -> Dict[str, List[str]]:
        """
        Formate les sections [SUBCATCHMENTS], [SUBAREAS], [INFILTRATION] et [POLYGONS]
        conformément à la grammaire officielle EPA SWMM 5.2.
        """
        sections = {
            "SUBCATCHMENTS": [
                ";;Name           Rain Gage        Outlet           Area     %Imperv  Width    Slope    CurbLen  SnowPack",
            ],
            "SUBAREAS": [
                ";;Subcatchment   N-Imperv   N-Perv     S-Imperv   S-Perv     PctZero    RouteTo    PctRouted ",
            ],
            "INFILTRATION": [
                ";;Subcatchment   MaxRate    MinRate    Decay      DryTime    MaxInfil  ",
            ],
            "POLYGONS": [
                ";;Subcatchment   X-Coord            Y-Coord           ",
            ]
        }

        if subcatchments_gdf.empty:
            return sections

        for _, row in subcatchments_gdf.iterrows():
            sb_id = row['subcatchment_id']
            outlet = row['outlet']
            area_ha = row['area_ha']
            imperv = row['imperv_pct']
            width = row['width_m']
            slope = row['slope_pct']

            # 1. SUBCATCHMENTS
            sections["SUBCATCHMENTS"].append(
                f"{sb_id:<16} {rain_gage_name:<16} {outlet:<16} {area_ha:<8.4f} {imperv:<8.2f} {width:<8.2f} {slope:<8.2f} 0.0000"
            )

            # 2. SUBAREAS
            n_imp = row.get('n_imperv', 0.015) if hasattr(row, 'get') else getattr(row, 'n_imperv', 0.015)
            n_perv = row.get('n_perv', 0.25) if hasattr(row, 'get') else getattr(row, 'n_perv', 0.25)
            d_imp = row.get('d_store_imperv', 1.5) if hasattr(row, 'get') else getattr(row, 'd_store_imperv', 1.5)
            d_perv = row.get('d_store_perv', 5.0) if hasattr(row, 'get') else getattr(row, 'd_store_perv', 5.0)
            pct_zero = row.get('pct_zero_imperv', 25.0) if hasattr(row, 'get') else getattr(row, 'pct_zero_imperv', 25.0)
            sub_route = str(row.get('subarea_route', 'OUTLET') if hasattr(row, 'get') else getattr(row, 'subarea_route', 'OUTLET'))

            sections["SUBAREAS"].append(
                f"{sb_id:<16} {n_imp:<10.3f} {n_perv:<10.3f} "
                f"{d_imp:<10.2f} {d_perv:<10.2f} "
                f"{pct_zero:<10.1f} {sub_route:<10}"
            )

            # 3. INFILTRATION (Horton)
            f0_val = row.get('f0', 75.0) if hasattr(row, 'get') else getattr(row, 'f0', 75.0)
            fc_val = row.get('fc', 10.0) if hasattr(row, 'get') else getattr(row, 'fc', 10.0)
            k_val = row.get('decay_k', 4.0) if hasattr(row, 'get') else getattr(row, 'decay_k', 4.0)
            dry_val = row.get('dry_time', 7.0) if hasattr(row, 'get') else getattr(row, 'dry_time', 7.0)
            max_inf = row.get('max_infil', 0.0) if hasattr(row, 'get') else getattr(row, 'max_infil', 0.0)

            sections["INFILTRATION"].append(
                f"{sb_id:<16} {f0_val:<10.2f} {fc_val:<10.2f} "
                f"{k_val:<10.2f} {dry_val:<10.1f} {max_inf:<10.2f}"
            )

            # 4. POLYGONS (sommet par sommet)
            geom = row.geometry
            if geom and hasattr(geom, 'exterior') and geom.exterior:
                coords = list(geom.exterior.coords)
                for x, y in coords:
                    sections["POLYGONS"].append(f"{sb_id:<16} {x:<18.3f} {y:<18.3f}")

        return sections

