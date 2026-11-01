"""
Module de modélisation hydrologique pour SWMM 5.2.
Fichier : src/domain/hydrologie.py

Génère les sous-bassins versants élémentaires (Subcatchments) par décomposition
spatiale (Voronoï / Thiessen), calcule les paramètres physiques (surface, imperméabilisation,
largeur hydraulique, pente, infiltration selon Horton) et formate les sections SWMM .inp.
"""

from typing import Dict, Any, List, Optional
import math
import geopandas as gpd
import pandas as pd
from shapely.geometry import Point, Polygon, MultiPolygon, MultiPoint, mapping
from shapely.ops import voronoi_diagram, unary_union


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
        Retourne un GeoDataFrame avec géométries polygonales et attributs SWMM complets.
        """
        if noeuds_gdf.empty:
            return gpd.GeoDataFrame()

        crs_source = noeuds_gdf.crs or "EPSG:32631"

        # 1. Délimitation de l'emprise urbaine de référence
        if emprise_bassin is not None and not emprise_bassin.is_empty:
            enveloppe_drainage = emprise_bassin
        elif not canalisations_gdf.empty:
            reseau_union = canalisations_gdf.geometry.union_all()
            enveloppe_drainage = reseau_union.buffer(self.tampon_buffer_m)
        else:
            points_union = noeuds_gdf.geometry.union_all()
            enveloppe_drainage = points_union.buffer(self.tampon_buffer_m)

        # 2. Construction des polygones de Voronoï / Thiessen
        points_list = [geom for geom in noeuds_gdf.geometry if isinstance(geom, Point)]
        if not points_list:
            return gpd.GeoDataFrame()

        multipoints = MultiPoint(points_list)
        # Calcul du diagramme de Voronoï avec l'enveloppe de drainage comme masque englobant
        diagramme = voronoi_diagram(multipoints, envelope=enveloppe_drainage.envelope)

        cellules_voronoi = list(diagramme.geoms) if hasattr(diagramme, 'geoms') else [diagramme]

        # 3. Appariement polygone <-> regard le plus proche ou intersectant
        sous_bassins_records = []

        for idx, row in noeuds_gdf.iterrows():
            pt = row.geometry
            if not isinstance(pt, Point):
                continue

            raw_id = row.get('id', row.get('id_noeud', row.get('swmm_id', row.get('code', row.get('Code', row.name)))))
            noeud_id = _identifiant_propre(raw_id)
            node_type = str(row.get('type', row.get('node_type', 'regard'))).lower()

            # Trouver la cellule contenant ce point
            cellule_trouvee = None
            for cell in cellules_voronoi:
                if cell.contains(pt) or cell.touches(pt):
                    cellule_trouvee = cell
                    break

            # Fallback : cellule la plus proche
            if cellule_trouvee is None:
                cellule_trouvee = min(cellules_voronoi, key=lambda c: c.distance(pt))

            # Tronquer par l'emprise de drainage urbaine
            cellule_clippee = cellule_trouvee.intersection(enveloppe_drainage)
            if cellule_clippee.is_empty:
                cellule_clippee = pt.buffer(5.0)

            aire_m2 = cellule_clippee.area
            aire_ha = max(aire_m2 / 10000.0, 0.001)

            # Largeur hydraulique caractéristique W = Aire / Longueur_chemin
            # Pour un polygone régulier, L_chemin ~ sqrt(Aire), donc W ~ sqrt(Aire)
            largeur_m = max(math.sqrt(aire_m2), 5.0)

            # Pente de surface estimée en %
            pente_pct = 0.5  # Standard urbain 0.5% si pas de MNT direct

            subcatchment_id = f"SB_{noeud_id}"

            sous_bassins_records.append({
                "subcatchment_id": subcatchment_id,
                "outlet": noeud_id,
                "rain_gage": rain_gage,
                "area_ha": round(aire_ha, 4),
                "area_m2": round(aire_m2, 2),
                "imperv_pct": self.imperv_defaut,
                "width_m": round(largeur_m, 2),
                "slope_pct": round(pente_pct, 2),
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
                "geometry": cellule_clippee
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

