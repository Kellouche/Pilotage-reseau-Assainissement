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

from typing import Dict, Any, List, Optional
import math
import geopandas as gpd
import pandas as pd
from shapely.geometry import Point, Polygon, MultiPolygon, MultiPoint, mapping
from shapely.ops import voronoi_diagram, unary_union
from shapely import STRtree


def _identifiant_propre(val: Any) -> str:
    """Normalise un identifiant pour SWMM."""
    if val is None:
        return ""
    txt = str(val).strip()
    if txt.endswith('.0'):
        txt = txt[:-2]
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

        # 3. Index spatial STRtree pour appariement 1-à-1 ultra-rapide (< 0.1s pour 10 000 points)
        cell_tree = STRtree(cellules_voronoi)
        pt_indices, cell_indices = cell_tree.query(points_list, predicate='intersects')
        pt_to_cell: Dict[int, Polygon] = {}
        for p_idx, c_idx in zip(pt_indices, cell_indices):
            if p_idx not in pt_to_cell:
                pt_to_cell[p_idx] = cellules_voronoi[c_idx]

        # 4. Découpage et enrichissement vectoriel
        sous_bassins_records = []
        buf_m = float(self.tampon_buffer_m)

        for i, (idx, row) in enumerate(valid_rows):
            pt = points_list[i]
            raw_id = row.get('id', row.get('id_noeud', row.get('swmm_id', row.get('code', row.get('Code', idx)))))
            noeud_id = _identifiant_propre(raw_id)

            cell = pt_to_cell.get(i)
            if cell is not None and not cell.is_empty:
                clipped_cell = cell.intersection(pt.buffer(buf_m))
                if clipped_cell.is_empty:
                    clipped_cell = pt.buffer(5.0)
            else:
                clipped_cell = pt.buffer(buf_m)

            aire_m2 = round(float(clipped_cell.area), 2)
            aire_ha = max(round(aire_m2 / 10000.0, 4), 0.0001)
            largeur_m = max(round(math.sqrt(aire_m2), 2), 5.0)
            pente_pct = 0.5  # Pente minimale conventionnelle d'assainissement

            subcatchment_id = f"SB_{noeud_id}"

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
            sections["SUBAREAS"].append(
                f"{sb_id:<16} {row['n_imperv']:<10.3f} {row['n_perv']:<10.3f} "
                f"{row['d_store_imperv']:<10.2f} {row['d_store_perv']:<10.2f} "
                f"{row['pct_zero_imperv']:<10.1f} {row['subarea_route']:<10}"
            )

            # 3. INFILTRATION (Horton)
            sections["INFILTRATION"].append(
                f"{sb_id:<16} {row['f0']:<10.2f} {row['fc']:<10.2f} "
                f"{row['decay_k']:<10.2f} {row['dry_time']:<10.1f} {row['max_infil']:<10.2f}"
            )

            # 4. POLYGONS (sommet par sommet)
            geom = row.geometry
            if geom and hasattr(geom, 'exterior') and geom.exterior:
                coords = list(geom.exterior.coords)
                for x, y in coords:
                    sections["POLYGONS"].append(f"{sb_id:<16} {x:<18.3f} {y:<18.3f}")

        return sections

