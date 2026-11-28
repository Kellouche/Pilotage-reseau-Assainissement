# -*- coding: utf-8 -*-
"""
================================================================================
Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
Auteur : Dr Abdelhakim KELLOUCHE
Date de création : 2026-11-27
Date de modification : 2026-11-27
Objet : Étapes du partitionnement 79 bassins versants (extrait verbatim de
         src/domain/generateur_bassins_79.py)
================================================================================
"""

import os
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")
os.environ.setdefault("OMP_NUM_THREADS", "1")

import time
import math
import json
from pathlib import Path
from typing import Dict, Any, List, Tuple, Optional
import colorsys

import numpy as np
import networkx as nx
import geopandas as gpd
import pyproj
from shapely.geometry import Point, LineString, Polygon, MultiPolygon, MultiPoint, mapping
from shapely.ops import voronoi_diagram, unary_union, transform
from shapely import STRtree

from src.domain.graphe_reseau import construire_graphe
from src.domain.detecteur_clusters import (
    trouver_exutoires_physiques,
    extraire_adresse_reelle_bassin,
    classifier_type_hydraulique,
)
from src.domain.moteur_swmm import _clean_node_id
from collections import Counter
import re


def _etape_affectation_voronoi(ctx):
    """Étape extraite verbatim de partitionner_79_bassins_versants."""
    G = ctx["G"]
    bassin_polygons_map = ctx["bassin_polygons_map"]
    buffer_voronoi_m = ctx["buffer_voronoi_m"]
    conn_tree = ctx["conn_tree"]
    connected_ex_ids = ctx["connected_ex_ids"]
    connected_nodes = ctx["connected_nodes"]
    connected_points = ctx["connected_points"]
    ex_to_color = ctx["ex_to_color"]
    ex_to_num = ctx["ex_to_num"]
    exutoires_attribution = ctx["exutoires_attribution"]
    exutoires_bassins = ctx["exutoires_bassins"]
    node_to_exutoire = ctx["node_to_exutoire"]
    orphelins_regards_records = ctx["orphelins_regards_records"]
    pt_to_cell = ctx["pt_to_cell"]
    regards_gdf = ctx["regards_gdf"]
    voronoi_records = ctx["voronoi_records"]

    for i, row in regards_gdf.iterrows():
        pt = row.geometry
        if not isinstance(pt, Point):
            continue

        raw_code = row.get('Code', row.get('id', i))
        str_code = str(raw_code).strip()
        if str_code.endswith('.0'):
            str_code = str_code[:-2]

        # Vérifier connexion topologique ou rattachement orphelin
        is_orphelin = False
        dist_snap = 0.0

        assigned_ex = None
        cand_ex = node_to_exutoire.get(str(raw_code)) or node_to_exutoire.get(str_code)
        if cand_ex:
            # Vérification anti-collision : si le regard a le même identifiant textuel qu'un exutoire
            # (ex: Ouvrage 11 vs Regard 11.0 distant de 3 km), on n'accepte la correspondance directe
            # que s'ils sont physiquement au même emplacement (< 60 m).
            if cand_ex in exutoires_attribution:
                ex_info = exutoires_attribution[cand_ex]
                ex_x = ex_info.get('x')
                ex_y = ex_info.get('y')
                if ex_x is not None and ex_y is not None:
                    if (str_code == str(cand_ex) or str(raw_code) == str(cand_ex)) and pt.distance(Point(float(ex_x), float(ex_y))) > 60.0:
                        cand_ex = None
            assigned_ex = cand_ex

        if not assigned_ex:
            # Regard orphelin : aucune connexion topologique amont-aval vers un exutoire
            # NE JAMAIS snapper artificiellement un orphelin dans un bassin versant connecté !
            is_orphelin = True
            n_idx = conn_tree.nearest(pt)
            nearest_ex = connected_ex_ids[n_idx]
            nearest_node = connected_nodes[n_idx] if connected_nodes else str(nearest_ex)
            dist_snap = round(float(pt.distance(connected_points[n_idx])), 2)
            orphelins_regards_records.append({
                "code_regard": str_code,
                "exutoire_proche": nearest_ex,
                "nom_exutoire_proche": exutoires_attribution.get(nearest_ex, {}).get('nom', str(nearest_ex)),
                "noeud_proche": str(nearest_node),
                "distance_rattachement_m": dist_snap,
                "commune": row.get('COMMUNE', ''),
                "nom_voie": row.get('NOMVOIE', ''),
                "geometry": pt
            })

        # Cellule de Voronoï bornée par le buffer de drainage urbain
        cell = pt_to_cell.get(i)
        if cell is not None and not cell.is_empty:
            clipped_cell = cell.intersection(pt.buffer(buffer_voronoi_m))
            if clipped_cell.is_empty:
                clipped_cell = pt.buffer(5.0)
        else:
            clipped_cell = pt.buffer(buffer_voronoi_m)

        area_m2 = round(float(clipped_cell.area), 2)
        area_ha = round(area_m2 / 10000.0, 4)
        width_m = round(max(math.sqrt(area_m2), 5.0), 2)

        if not is_orphelin and assigned_ex is not None and assigned_ex in exutoires_bassins:
            ex_info = exutoires_attribution.get(assigned_ex, {})
            b_num = ex_to_num.get(assigned_ex, 1)
            b_color = ex_to_color.get(assigned_ex, "#3498db")

            voronoi_records.append({
                "subcatchment_id": f"SB_{str_code}",
                "outlet": str_code,
                "id_bassin": b_num,
                "exutoire_id": str(assigned_ex),
                "nom_bassin": ex_info.get('nom', f"Bassin_{b_num}"),
                "type_exutoire": ex_info.get('type', 'exutoire'),
                "nom_voie": str(row.get('NOMVOIE', '') or (G.nodes.get(str_code, {}).get('nom_voie', '') if str_code in G.nodes else '')),
                "area_ha": area_ha,
                "area_m2": area_m2,
                "imperv_pct": 70.0,
                "width_m": width_m,
                "slope_pct": 0.5,
                # Infiltration Horton
                "f0": 75.0,
                "fc": 10.0,
                "decay_k": 4.0,
                "is_orphelin": 0,
                "dist_snap_m": 0.0,
                "couleur": b_color,
                "geometry": clipped_cell
            })

            bassin_polygons_map[assigned_ex].append(clipped_cell)
        elif not is_orphelin and assigned_ex is not None:
            # Fragment connecté à un exutoire implicite non significatif :
            # rattaché (is_orphelin=0) mais sans bassin versant propre —
            # relève de la file de revue, pas de la simulation.
            ex_info = exutoires_attribution.get(assigned_ex, {})
            voronoi_records.append({
                "subcatchment_id": f"SB_{str_code}",
                "outlet": str_code,
                "id_bassin": None,
                "exutoire_id": str(assigned_ex),
                "nom_bassin": "Fragment à exutoire non déclaré",
                "type_exutoire": "exutoire_implicite",
                "nom_voie": str(row.get('NOMVOIE', '') or (G.nodes.get(str_code, {}).get('nom_voie', '') if str_code in G.nodes else '')),
                "area_ha": area_ha,
                "area_m2": area_m2,
                "imperv_pct": 70.0,
                "width_m": width_m,
                "slope_pct": 0.5,
                # Infiltration Horton
                "f0": 75.0,
                "fc": 10.0,
                "decay_k": 4.0,
                "is_orphelin": 0,
                "dist_snap_m": 0.0,
                "couleur": "#64748b",
                "geometry": clipped_cell
            })
        else:
            # Regard orphelin : sa cellule Voronoï est isolée hors des 79 bassins versants d'exutoires
            voronoi_records.append({
                "subcatchment_id": f"SB_{str_code}",
                "outlet": str_code,
                "id_bassin": None,
                "exutoire_id": "orphelin",
                "nom_bassin": "Éléments orphelins (déconnectés)",
                "type_exutoire": "orphelin",
                "nom_voie": str(row.get('NOMVOIE', '') or (G.nodes.get(str_code, {}).get('nom_voie', '') if str_code in G.nodes else '')),
                "area_ha": area_ha,
                "area_m2": area_m2,
                "imperv_pct": 70.0,
                "width_m": width_m,
                "slope_pct": 0.5,
                # Infiltration Horton
                "f0": 75.0,
                "fc": 10.0,
                "decay_k": 4.0,
                "is_orphelin": 1,
                "dist_snap_m": dist_snap,
                "couleur": "#f59e0b",
                "geometry": clipped_cell
            })



def _etape_fusion_bassins(ctx):
    """Étape extraite verbatim de partitionner_79_bassins_versants."""
    G = ctx["G"]
    bassin_polygons_map = ctx["bassin_polygons_map"]
    bassins_records = ctx["bassins_records"]
    buffer_voronoi_m = ctx["buffer_voronoi_m"]
    est_invalide = ctx["est_invalide"]
    ex_to_color = ctx["ex_to_color"]
    ex_to_num = ctx["ex_to_num"]
    exutoires_bassins = ctx["exutoires_bassins"]
    voronoi_records = ctx["voronoi_records"]

    for ex_id, geoms in bassin_polygons_map.items():
        ex_info = exutoires_bassins.get(ex_id, {})
        b_num = ex_to_num.get(ex_id, 1)
        b_color = ex_to_color.get(ex_id, "#3498db")

        if geoms:
            geom_union = unary_union(geoms)
            # Nettoyage anti-parasite : garantir la contiguïté stricte du bassin versant autour de son exutoire
            if isinstance(geom_union, MultiPolygon):
                ex_x = ex_info.get('x')
                ex_y = ex_info.get('y')
                if ex_x is not None and ex_y is not None:
                    ex_pt = Point(float(ex_x), float(ex_y))
                    main_poly = min(geom_union.geoms, key=lambda p: p.distance(ex_pt))
                    proches = [p for p in geom_union.geoms if p.distance(main_poly) <= 25.0]
                    geom_union = unary_union(proches) if proches else main_poly
                if isinstance(geom_union, MultiPolygon):
                    geom_union = max(geom_union.geoms, key=lambda p: p.area)

            # Comblement systématique des cavités intérieures des îlots urbains
            if isinstance(geom_union, Polygon):
                geom_union = Polygon(geom_union.exterior)
            elif isinstance(geom_union, MultiPolygon):
                largest = max(geom_union.geoms, key=lambda p: p.area)
                geom_union = Polygon(largest.exterior)
            area_m2 = round(float(geom_union.area), 2)
            area_ha = round(area_m2 / 10000.0, 2)
        else:
            # Si exutoire isolé sans cellule, créer un polygone tampon minimal
            ex_pt = Point(float(ex_info.get('x', 0)), float(ex_info.get('y', 0)))
            geom_union = ex_pt.buffer(buffer_voronoi_m)
            area_m2 = round(float(geom_union.area), 2)
            area_ha = round(area_m2 / 10000.0, 2)

        # Statistiques regards et conduites
        regards_in_bassin = [r for r in voronoi_records if r['exutoire_id'] == str(ex_id)]
        nb_regards_total = len(regards_in_bassin)
        nb_regards_orphelins = sum(1 for r in regards_in_bassin if r['is_orphelin'] == 1)

        # Harmonisation hydrologique : la surface drainée est la somme exacte des sous-bassins Voronoï
        sum_sb_ha = round(sum(r.get('area_ha', 0.0) for r in regards_in_bassin), 2)
        if sum_sb_ha > 0:
            area_ha = sum_sb_ha
            area_m2 = round(sum_sb_ha * 10000.0, 2)

        # Collecter les noms de voie des regards du bassin
        voies_bassin = [r.get('nom_voie') for r in regards_in_bassin if r.get('nom_voie')]
        compteur_voies = Counter([
            str(v).strip() for v in voies_bassin 
            if v and str(v).strip().lower() not in ('nan', 'none', '', 'null') 
            and not re.match(r'^\d+(\.0)?$', str(v).strip()) and len(str(v).strip()) > 2
        ])
        top_voie = compteur_voies.most_common(1)[0][0] if compteur_voies else None

        ex_nom = ex_info.get('nom')
        ex_node_voie = G.nodes.get(ex_id, {}).get('nom_voie') if ex_id in G.nodes else None
        
        def est_invalide(s):
            if not s: return True
            st = str(s).strip()
            return st.lower() in ('nan', 'none', '', 'null', 'sans designation', 'inconnu') or bool(re.match(r'^\d+(\.0)?$', st)) or len(st) <= 2

        if str(ex_id) == '0' or 'step' in str(ex_info.get('type', '')).lower():
            adresse_reelle = f"{top_voie or 'Chorfa'} (STEP)"
        else:
            zc = ex_info.get('zone_collecte') or (G.nodes.get(ex_id, {}).get('zone_collecte') if ex_id in G.nodes else None)
            zc_clean = str(zc).replace('BC_', '').replace('_', ' ').strip() if zc and not est_invalide(zc) else None
            
            # Priorité au nom d'ouvrage ou de quartier réel
            if ex_nom and not est_invalide(ex_nom):
                adresse_reelle = str(ex_nom).strip()
            elif zc_clean and not est_invalide(zc_clean):
                adresse_reelle = zc_clean
            elif top_voie and not est_invalide(top_voie):
                adresse_reelle = top_voie
            elif ex_node_voie and not est_invalide(ex_node_voie):
                adresse_reelle = str(ex_node_voie).strip()
            else:
                adresse_reelle = f"Bassin {b_num}"

        typ_det = ex_info.get('type_detaille') or ex_info.get('type', 'exutoire')
        lib_det = ex_info.get('libelle_type') or typ_det
        coul_det = ex_info.get('couleur_type')

        bassins_records.append({
            "id_bassin": b_num,
            "exutoire_id": str(ex_id),
            "nom_exutoire": adresse_reelle,
            "type_exutoire": typ_det,
            "libelle_type": lib_det,
            "couleur_type": coul_det,
            "type_ouvrage": ex_info.get('type_ouvrage'),
            "h_seuil": ex_info.get('h_seuil'),
            "milieu_rec": ex_info.get('milieu_rec'),
            "zone_collecte": ex_info.get('zone_collecte'),
            "surface_ha": area_ha,
            "surface_m2": area_m2,
            "nb_regards": nb_regards_total,
            "nb_regards_orphelins": nb_regards_orphelins,
            "couleur": b_color,
            "geometry": geom_union
        })



def _etape_classification_conduites(ctx):
    """Étape extraite verbatim de partitionner_79_bassins_versants."""
    from src.domain.generateur_bassins_79 import _log_part  # noqa: E402 (anti-cycle)
    G = ctx["G"]
    crs_metrique = ctx["crs_metrique"]
    ex_set = ctx["ex_set"]
    ex_to_color = ctx["ex_to_color"]
    ex_to_num = ctx["ex_to_num"]
    fragments_pipes_features = ctx["fragments_pipes_features"]
    gdf_bassins_79 = ctx["gdf_bassins_79"]
    node_to_exutoire = ctx["node_to_exutoire"]
    orphelins_pipes_features = ctx["orphelins_pipes_features"]
    pipes_by_exutoire = ctx["pipes_by_exutoire"]
    pipes_gdf = ctx["pipes_gdf"]
    total_troncons_assignes = ctx["total_troncons_assignes"]

    try:
        transformer_to_wgs84 = pyproj.Transformer.from_crs(crs_metrique, "EPSG:4326", always_xy=True).transform

        if not pipes_gdf.empty:
            for idx, row in pipes_gdf.iterrows():
                geom_metric = row.geometry
                if geom_metric is None or geom_metric.is_empty:
                    continue

                pipe_id = str(row.get('id', row.get('id_troncon', row.get('ID_TRONCON', idx))))
                u = _clean_node_id(row.get('noeud_amont', row.get('amont', row.get('ID_AMONT'))))
                v = _clean_node_id(row.get('noeud_aval', row.get('aval', row.get('ID_AVAL'))))

                raw_len = row.get('longueur', row.get('length', row.get('LONGUEUR', row.get('Longeur'))))
                if raw_len is None or (isinstance(raw_len, (int, float)) and (math.isnan(raw_len) or raw_len <= 0)):
                    longueur = float(geom_metric.length)
                else:
                    try:
                        longueur = float(raw_len)
                    except (ValueError, TypeError):
                        longueur = float(geom_metric.length)
                longueur = round(longueur, 1)

                raw_diam = row.get('diametre', row.get('diametre_mm', row.get('DIAMETRE', 300)))
                try:
                    diametre = int(raw_diam) if raw_diam and not (isinstance(raw_diam, float) and math.isnan(raw_diam)) else 300
                except (ValueError, TypeError):
                    diametre = 300

                materiau = str(row.get('materiau', row.get('type', row.get('MATERIAU', 'Béton'))))

                try:
                    geom_wgs84 = transform(transformer_to_wgs84, geom_metric)
                except Exception:
                    geom_wgs84 = None

                if geom_wgs84 is None or geom_wgs84.is_empty:
                    continue

                # Règle hydraulique stricte : l'eau s'écoule vers le nœud aval v.
                # La conduite appartient au bassin versant auquel son nœud aval v est rattaché.
                # Si v n'est pas encore attribué mais u l'est (et n'est pas lui-même un exutoire d'évacuation),
                # rattacher au bassin de u.
                assigned_pipe_ex = node_to_exutoire.get(v)
                if not assigned_pipe_ex and u and u not in ex_set:
                    assigned_pipe_ex = node_to_exutoire.get(u)

                if assigned_pipe_ex and assigned_pipe_ex in pipes_by_exutoire:
                    b_num = ex_to_num.get(assigned_pipe_ex, 1)
                    b_color = ex_to_color.get(assigned_pipe_ex, "#3498db")
                    feat_pipe = {
                        "type": "Feature",
                        "geometry": mapping(geom_wgs84),
                        "properties": {
                            "conduit_id": pipe_id,
                            "cluster_id": b_num,
                            "couleur": b_color,
                            "diametre": diametre,
                            "longueur": longueur,
                            "materiau": materiau,
                            "type": "conduite",
                            "is_orphelin": 0
                        }
                    }
                    pipes_by_exutoire[assigned_pipe_ex].append(feat_pipe)
                elif assigned_pipe_ex:
                    # Fragment connecté à un exutoire implicite non significatif :
                    # rattaché (is_orphelin=0) mais sans bassin versant propre.
                    feat_pipe = {
                        "type": "Feature",
                        "geometry": mapping(geom_wgs84),
                        "properties": {
                            "conduit_id": pipe_id,
                            "cluster_id": None,
                            "exutoire_id": str(assigned_pipe_ex),
                            "exutoire_type": "exutoire_implicite",
                            "couleur": "#64748b",
                            "diametre": diametre,
                            "longueur": longueur,
                            "materiau": materiau,
                            "type": "conduite",
                            "is_orphelin": 0
                        }
                    }
                    fragments_pipes_features.append(feat_pipe)
                else:
                    feat_pipe = {
                        "type": "Feature",
                        "geometry": mapping(geom_wgs84),
                        "properties": {
                            "conduit_id": pipe_id,
                            "cluster_id": "orphelin",
                            "couleur": "#f59e0b",
                            "diametre": diametre,
                            "longueur": longueur,
                            "materiau": materiau,
                            "type": "conduite_orpheline",
                            "is_orphelin": 1
                        }
                    }
                    orphelins_pipes_features.append(feat_pipe)
        else:
            for u, v, data in G.edges(data=True):
                geom_metric = data.get('geometry')
                if geom_metric is None or geom_metric.is_empty:
                    continue

                pipe_id = str(data.get('id', f"{u}_{v}"))
                raw_len = data.get('length')
                if raw_len is None or (isinstance(raw_len, float) and (math.isnan(raw_len) or raw_len <= 0)):
                    longueur = float(geom_metric.length)
                else:
                    longueur = float(raw_len)
                longueur = round(longueur, 1)

                raw_diam = data.get('diametre_mm', 300)
                diametre = int(raw_diam) if raw_diam and not (isinstance(raw_diam, float) and math.isnan(raw_diam)) else 300
                materiau = str(data.get('materiau', data.get('type', 'Béton')))

                try:
                    geom_wgs84 = transform(transformer_to_wgs84, geom_metric)
                except Exception:
                    geom_wgs84 = None

                if geom_wgs84 is None or geom_wgs84.is_empty:
                    continue

                assigned_pipe_ex = node_to_exutoire.get(v) or node_to_exutoire.get(u)

                if assigned_pipe_ex and assigned_pipe_ex in pipes_by_exutoire:
                    b_num = ex_to_num.get(assigned_pipe_ex, 1)
                    b_color = ex_to_color.get(assigned_pipe_ex, "#3498db")
                    feat_pipe = {
                        "type": "Feature",
                        "geometry": mapping(geom_wgs84),
                        "properties": {
                            "conduit_id": pipe_id,
                            "cluster_id": b_num,
                            "couleur": b_color,
                            "diametre": diametre,
                            "longueur": longueur,
                            "materiau": materiau,
                            "type": "conduite",
                            "is_orphelin": 0
                        }
                    }
                    pipes_by_exutoire[assigned_pipe_ex].append(feat_pipe)
                elif assigned_pipe_ex:
                    feat_pipe = {
                        "type": "Feature",
                        "geometry": mapping(geom_wgs84),
                        "properties": {
                            "conduit_id": pipe_id,
                            "cluster_id": None,
                            "exutoire_id": str(assigned_pipe_ex),
                            "exutoire_type": "exutoire_implicite",
                            "couleur": "#64748b",
                            "diametre": diametre,
                            "longueur": longueur,
                            "materiau": materiau,
                            "type": "conduite",
                            "is_orphelin": 0
                        }
                    }
                    fragments_pipes_features.append(feat_pipe)
                else:
                    feat_pipe = {
                        "type": "Feature",
                        "geometry": mapping(geom_wgs84),
                        "properties": {
                            "conduit_id": pipe_id,
                            "cluster_id": "orphelin",
                            "couleur": "#f59e0b",
                            "diametre": diametre,
                            "longueur": longueur,
                            "materiau": materiau,
                            "type": "conduite_orpheline",
                            "is_orphelin": 1
                        }
                    }
                    orphelins_pipes_features.append(feat_pipe)

        _log_part(f"[partitionnement] {sum(len(p) for p in pipes_by_exutoire.values())} conduites connectées réparties sur les {len(gdf_bassins_79)} bassins.", flush=True)
        _log_part(f"[partitionnement] {len(fragments_pipes_features)} conduites en fragments à exutoire implicite.", flush=True)
        _log_part(f"[partitionnement] {len(orphelins_pipes_features)} tronçons orphelins isolés.", flush=True)
    except Exception as e:
        _log_part(f"[partitionnement] Erreur classification conduites: {e}", flush=True)
