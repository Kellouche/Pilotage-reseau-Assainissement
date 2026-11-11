"""
================================================================================
Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
Auteur : Dr Abdelhakim KELLOUCHE
Date de création : 2026-04-20
Date de modification : 2026-11-08
Objet : Génération et calibration des bassins versants pour le scénario 79
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


def _log_part(*args, **kwargs):
    """Affiche les logs d'ingénierie sauf si le mode silencieux est actif."""
    if os.getenv("DRAINPILOT_SILENT", "").lower() not in ("1", "true", "yes"):
        print(*args, **kwargs)


def generer_palette_couleurs(nb_couleurs: int) -> List[str]:
    """Génère une palette de couleurs HSL contrastées et réparties harmonieusement."""
    couleurs = []
    # Palette de base pour les premiers exutoires emblématiques
    base_palette = [
        "#e74c3c", "#3498db", "#2ecc71", "#9b59b6", "#f39c12",
        "#1abc9c", "#d35400", "#e84393", "#00cec9", "#6c5ce7",
        "#fdcb6e", "#0984e3", "#00b894", "#b2bec3", "#e17055",
        "#a29bfe", "#fd79a8", "#636e72", "#2d3436", "#55efc4"
    ]
    if nb_couleurs <= len(base_palette):
        return base_palette[:nb_couleurs]

    # Génération HSL équilibrée
    for i in range(nb_couleurs):
        hue = (i * 0.618033988749895) % 1.0  # Nombre d'or pour étaler les teintes
        saturation = 0.75 + (i % 3) * 0.10
        lightness = 0.48 + (i % 2) * 0.08
        r, g, b = colorsys.hls_to_rgb(hue, lightness, saturation)
        hex_color = f"#{int(r*255):02x}{int(g*255):02x}{int(b*255):02x}"
        couleurs.append(hex_color)
    return couleurs


def partitionner_79_bassins_versants(
    gpkg_path: str,
    buffer_voronoi_m: float = 35.0,
    sauvegarder_gpkg: bool = True
) -> Dict[str, Any]:
    """
    Construit les 79 macro-bassins versants urbains et intègre pour chacun
    ses sous-bassins élémentaires Voronoï.
    
    1. Attribue les nœuds connectés au premier exutoire aval rencontré dans le graphe.
    2. Rapproche géométriquement les regards et tronçons orphelins du bassin le plus proche.
    3. Isole les orphelins dans un fichier et une couche dédiée pour audit.
    4. Calcule les 10 538 polygones Voronoï élémentaires avec leurs attributs SWMM.
    5. Fusionne (unary_union) les Voronoï par exutoire pour former les 79 bassins continus.
    6. Persiste directement dans le GeoPackage (si demandé) et met en cache.
    """
    t0 = time.time()
    gpkg_p = Path(gpkg_path)
    if not gpkg_p.exists():
        raise FileNotFoundError(f"GeoPackage introuvable : {gpkg_path}")

    _log_part(f"[partitionnement] Construction du graphe depuis {gpkg_p.name}...", flush=True)
    G = construire_graphe(str(gpkg_p))
    exutoires_physiques = trouver_exutoires_physiques(G)
    nb_exutoires = len(exutoires_physiques)
    _log_part(f"[partitionnement] {nb_exutoires} exutoires physiques identifiés.", flush=True)

    # 1. Neutraliser les boucles / cycles pour un parcours amont strict
    try:
        while True:
            cycle = nx.find_cycle(G, orientation="original")
            G.remove_edge(cycle[-1][0], cycle[-1][1])
    except nx.NetworkXNoCycle:
        pass

    # 2. Attribution de chaque nœud au premier exutoire aval rencontré
    #    Chaque exutoire draine son réseau amont direct jusqu'aux exutoires amont voisins
    ex_set = set(exutoires_physiques.keys())
    node_to_exutoire: Dict[str, str] = {}

    # Tri par priorité hydraulique
    exutoires_tries = sorted(exutoires_physiques.items(), key=lambda x: x[1].get('priorite', 99))

    for ex_id, _ in exutoires_tries:
        node_to_exutoire[ex_id] = ex_id
        queue = [ex_id]
        while queue:
            curr = queue.pop(0)
            for pred in G.predecessors(curr):
                if pred not in ex_set and pred not in node_to_exutoire:
                    node_to_exutoire[pred] = ex_id
                    queue.append(pred)

    _log_part(f"[partitionnement] {len(node_to_exutoire)} nœuds connectés directement aux {nb_exutoires} exutoires.", flush=True)

    # 3. Charger les couches Regards et Canalisations du GPKG
    layers = gpd.list_layers(str(gpkg_p))['name'].tolist()
    regard_layer = next((l for l in layers if 'regard' in l.lower()), None)
    pipe_layer = next((l for l in layers if any(k in l.lower() for k in ['canalisat', 'conduit', 'pipe', 'troncon']) and 'désaffect' not in l.lower() and 'desaffect' not in l.lower()), None)

    if not regard_layer:
        raise ValueError("Couche Regards introuvable dans le GeoPackage.")

    regards_gdf = gpd.read_file(str(gpkg_p), layer=regard_layer)
    pipes_gdf = gpd.read_file(str(gpkg_p), layer=pipe_layer) if pipe_layer else gpd.GeoDataFrame()
    crs_metrique = regards_gdf.crs or "EPSG:32631"

    # Index spatial des regards connectés pour l'audit des distances orphelins
    connected_points = []
    connected_ex_ids = []
    connected_nodes = []
    for idx, row in regards_gdf.iterrows():
        c = str(row.get('Code', row.get('id', idx)))
        if c in node_to_exutoire:
            connected_points.append(row.geometry)
            connected_ex_ids.append(node_to_exutoire[c])
            connected_nodes.append(c)

    if not connected_points:
        # Fallback si aucun regard n'est connecté par code : utiliser la position des exutoires
        for ex_id, ex_data in exutoires_physiques.items():
            if 'x' in ex_data and 'y' in ex_data:
                connected_points.append(Point(float(ex_data['x']), float(ex_data['y'])))
                connected_ex_ids.append(ex_id)
                connected_nodes.append(str(ex_id))

    conn_tree = STRtree(connected_points)

    # Palette de couleurs
    palette = generer_palette_couleurs(nb_exutoires)
    exutoire_id_list = list(exutoires_physiques.keys())
    ex_to_color = {ex_id: palette[i % len(palette)] for i, ex_id in enumerate(exutoire_id_list)}
    ex_to_num = {ex_id: i + 1 for i, ex_id in enumerate(exutoire_id_list)}

    # 4. Génération du diagramme de Voronoï sur tous les regards
    points_list = [g for g in regards_gdf.geometry if isinstance(g, Point)]
    multipoints = MultiPoint(points_list)
    diagramme = voronoi_diagram(multipoints)
    cellules = list(diagramme.geoms) if hasattr(diagramme, 'geoms') else [diagramme]

    # Index spatial des cellules Voronoï pour appariement 1-à-1 ultra-rapide
    cell_tree = STRtree(cellules)
    pt_indices, cell_indices = cell_tree.query(points_list, predicate='intersects')
    pt_to_cell: Dict[int, Polygon] = {}
    for p_idx, c_idx in zip(pt_indices, cell_indices):
        if p_idx not in pt_to_cell:
            pt_to_cell[p_idx] = cellules[c_idx]

    # 5. Découpage et enrichissement des sous-bassins Voronoï
    voronoi_records = []
    bassin_polygons_map: Dict[str, List[Polygon]] = {ex_id: [] for ex_id in exutoire_id_list}
    orphelins_regards_records = []

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
            # Vérification anti-collision : si le regard a le même identifiant textuel qu'un exutoire physique
            # (ex: Ouvrage 11 vs Regard 11.0 distant de 3 km), on n'accepte la correspondance directe
            # que s'ils sont physiquement au même emplacement (< 60 m).
            if cand_ex in exutoires_physiques:
                ex_info = exutoires_physiques[cand_ex]
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
                "nom_exutoire_proche": exutoires_physiques.get(nearest_ex, {}).get('nom', str(nearest_ex)),
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

        if not is_orphelin and assigned_ex is not None:
            ex_info = exutoires_physiques.get(assigned_ex, {})
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

    # Continuité hydraulique : intégrer le fuseau tampon (15m) des conduites connectées
    for u, v, data in G.edges(data=True):
        geom_metric = data.get('geometry')
        if geom_metric is not None and not geom_metric.is_empty:
            assigned_pipe_ex = node_to_exutoire.get(v) or node_to_exutoire.get(u)
            if assigned_pipe_ex and assigned_pipe_ex in bassin_polygons_map:
                bassin_polygons_map[assigned_pipe_ex].append(geom_metric.buffer(15.0))

    gdf_voronoi = gpd.GeoDataFrame(voronoi_records, crs=crs_metrique)
    _log_part(f"[partitionnement] {len(gdf_voronoi)} sous-bassins Voronoï générés et typés.", flush=True)

    # 6. Fusion géométrique (unary_union) pour créer les macro-bassins versants
    bassins_records = []
    _log_part(f"[partitionnement] Fusion spatiale des macro-bassins versants urbains ({len(bassin_polygons_map)} exutoires)...", flush=True)

    for ex_id, geoms in bassin_polygons_map.items():
        ex_info = exutoires_physiques.get(ex_id, {})
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

    # Trier par numéro de bassin
    bassins_records.sort(key=lambda x: x['id_bassin'])
    gdf_bassins_79 = gpd.GeoDataFrame(bassins_records, crs=crs_metrique)

    # 7. Identifier et colorier les canalisations par bassin versant
    pipes_by_exutoire: Dict[str, List[Dict[str, Any]]] = {ex_id: [] for ex_id in exutoire_id_list}
    orphelins_pipes_features: List[Dict[str, Any]] = []

    _log_part("[partitionnement] Classification topologique des conduites par exutoire...", flush=True)
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
        _log_part(f"[partitionnement] {len(orphelins_pipes_features)} tronçons orphelins isolés.", flush=True)
    except Exception as e:
        _log_part(f"[partitionnement] Erreur classification conduites: {e}", flush=True)

    gdf_orphelins_regards = gpd.GeoDataFrame(orphelins_regards_records, crs=crs_metrique) if orphelins_regards_records else gpd.GeoDataFrame()

    total_surface_ha = round(float(gdf_bassins_79['surface_ha'].sum()), 2)
    _log_part(f"[partitionnement] {len(gdf_bassins_79)} bassins versants créés (Surface totale : {total_surface_ha} ha).", flush=True)
    _log_part(f"[partitionnement] Regards orphelins isolés : {len(gdf_orphelins_regards)}.", flush=True)

    # 8. Persistance dans le GeoPackage (si demandé)
    if sauvegarder_gpkg:
        _log_part(f"[partitionnement] Écriture des nouvelles couches dans {gpkg_p.name}...", flush=True)
        try:
            gdf_bassins_79.to_file(str(gpkg_p), layer="bassins_versants_79", driver="GPKG")
            _log_part("[partitionnement] Couche 'bassins_versants_79' sauvegardée.", flush=True)
        except Exception as e:
            _log_part(f"[partitionnement] Erreur sauvegarde bassins_versants_79: {e}", flush=True)

        try:
            gdf_voronoi.to_file(str(gpkg_p), layer="sous_bassins_voronoi", driver="GPKG")
            _log_part("[partitionnement] Couche 'sous_bassins_voronoi' sauvegardée.", flush=True)
        except Exception as e:
            _log_part(f"[partitionnement] Erreur sauvegarde sous_bassins_voronoi: {e}", flush=True)

        if not gdf_orphelins_regards.empty:
            try:
                gdf_orphelins_regards.to_file(str(gpkg_p), layer="elements_orphelins_regards", driver="GPKG")
                _log_part("[partitionnement] Couche 'elements_orphelins_regards' sauvegardée.", flush=True)
            except Exception as e:
                _log_part(f"[partitionnement] Erreur sauvegarde orphelins: {e}", flush=True)

    # 9. Export du fichier isolé des orphelins (GeoJSON) dans le dossier upload
    orphelins_geojson_path = gpkg_p.parent / "elements_orphelins.geojson"
    gdf_orph_wgs84 = gdf_orphelins_regards.to_crs("EPSG:4326") if not gdf_orphelins_regards.empty else gpd.GeoDataFrame()
    if not gdf_orph_wgs84.empty:
        try:
            gdf_orph_wgs84.to_file(str(orphelins_geojson_path), driver="GeoJSON")
            _log_part(f"[partitionnement] Fichier d'isolation exporté : {orphelins_geojson_path.name}", flush=True)
        except Exception as e:
            _log_part(f"[partitionnement] Erreur export orphelins.geojson: {e}", flush=True)

    # 10. Préparation des structures GeoJSON WGS84 pour l'API et le cache Web
    gdf_bassins_wgs84 = gdf_bassins_79.to_crs("EPSG:4326")
    bassins_geojson = json.loads(gdf_bassins_wgs84.to_json(na="drop"))

    gdf_voronoi_wgs84 = gdf_voronoi.to_crs("EPSG:4326")
    voronoi_geojson = json.loads(gdf_voronoi_wgs84.to_json(na="drop"))

    # Construction des 79 items de resultats pour le cockpit
    results_formatted = []
    total_troncons_assignes = 0

    for feat in bassins_geojson.get("features", []):
        props = feat.get("properties", {})
        b_id = props.get("id_bassin")
        ex_id_str = props.get("exutoire_id")
        b_nom = props.get("nom_exutoire")
        b_type = props.get("type_exutoire")
        b_color = props.get("couleur")
        bassin_pipes = pipes_by_exutoire.get(ex_id_str, [])

        feat["properties"]["type"] = "bassin_urbain"
        feat["properties"]["cluster_id"] = b_id
        feat["properties"]["nom"] = b_nom
        feat["properties"]["bassin_ref"] = f"exutoire:{ex_id_str}" if ex_id_str else None
        feat["properties"]["exutoire_type"] = b_type
        feat["properties"]["exutoire_type_detaille"] = props.get("type_exutoire")
        feat["properties"]["libelle_type"] = props.get("libelle_type")
        feat["properties"]["couleur_type"] = props.get("couleur_type")
        feat["properties"]["type_ouvrage"] = props.get("type_ouvrage")
        feat["properties"]["h_seuil"] = props.get("h_seuil")
        feat["properties"]["milieu_rec"] = props.get("milieu_rec")
        feat["properties"]["couleur"] = b_color
        feat["properties"]["surface_ha"] = float(props.get("surface_ha", 0.0))
        feat["properties"]["nb_regards"] = int(props.get("nb_regards", 0))
        feat["properties"]["nb_regards_orphelins"] = int(props.get("nb_regards_orphelins", 0))
        feat["properties"]["nb_conduites"] = len(bassin_pipes)
        longueur_bassin = round(sum(p['properties'].get('longueur', 0.0) for p in bassin_pipes), 1)
        feat["properties"]["longueur_totale_m"] = longueur_bassin

        cluster_features = [feat]

        # Ajouter l'exutoire ponctuel s'il a des coordonnées valides
        ex_info = exutoires_physiques.get(ex_id_str, {})
        if 'x' in ex_info and 'y' in ex_info:
            try:
                pt_ex = Point(float(ex_info['x']), float(ex_info['y']))
                gdf_ex_pt = gpd.GeoSeries([pt_ex], crs=crs_metrique).to_crs("EPSG:4326")
                ex_geom = gdf_ex_pt.iloc[0]
                cluster_features.append({
                    "type": "Feature",
                    "geometry": mapping(ex_geom),
                    "properties": {
                        "type": "exutoire",
                        "cluster_id": b_id,
                        "nom": b_nom,
                        "exutoire_id": ex_id_str,
                        "bassin_ref": f"exutoire:{ex_id_str}" if ex_id_str else None,
                        "exutoire_type": b_type,
                        "exutoire_type_detaille": props.get("type_exutoire"),
                        "libelle_type": props.get("libelle_type"),
                        "couleur_type": props.get("couleur_type"),
                        "type_ouvrage": props.get("type_ouvrage"),
                        "h_seuil": props.get("h_seuil"),
                        "milieu_rec": props.get("milieu_rec"),
                    }
                })
            except Exception:
                pass

        # Ajouter les conduites de ce bassin
        cluster_features.extend(bassin_pipes)
        total_troncons_assignes += len(bassin_pipes)

        results_formatted.append({
            "cluster": {
                "id": b_id,
                "nom": b_nom,
                "surface_ha": props.get("surface_ha")
            },
            "exutoire": {
                "nom": b_nom,
                "type": b_type
            },
            "stats": {
                "surface_ha": props.get("surface_ha"),
                "nb_regards": props.get("nb_regards"),
                "nb_regards_orphelins": props.get("nb_regards_orphelins"),
                "nb_conduites": len(bassin_pipes),
                "longueur_totale_m": longueur_bassin
            },
            "infrastructures": {
                "regards": props.get("nb_regards"),
                "conduites": len(bassin_pipes),
                "longueur_totale_m": longueur_bassin
            },
            "geojson": {
                "type": "FeatureCollection",
                "features": cluster_features
            },
            "troncons": len(bassin_pipes)
        })

    # Sauvegarde du cache disque pour rapidité web instantanée (< 50ms)
    cache_clusters_path = gpkg_p.with_suffix(".clusters_cache.json")
    try:
        orph_reg_geojson = json.loads(gdf_orph_wgs84.to_json(na="drop")) if not gdf_orph_wgs84.empty else {"type": "FeatureCollection", "features": []}
        clusters_cache_data = {
            "status": "success",
            "exutoires_physiques": nb_exutoires,
            "clusters_crees": len(gdf_bassins_79),
            "surface_totale_ha": total_surface_ha,
            "nb_sous_bassins_voronoi": len(gdf_voronoi),
            "nb_regards_orphelins": len(gdf_orphelins_regards),
            "nb_troncons_orphelins": len(orphelins_pipes_features),
            "troncons_connectes": total_troncons_assignes,
            "bassins_geojson": bassins_geojson,
            "orphelins_conduites": {
                "type": "FeatureCollection",
                "features": orphelins_pipes_features
            },
            "orphelins_regards": orph_reg_geojson,
            "resultats": results_formatted
        }
        with open(cache_clusters_path, "w", encoding="utf-8") as f:
            json.dump(clusters_cache_data, f, ensure_ascii=False)
        _log_part(f"[partitionnement] Cache disque des clusters mis à jour : {cache_clusters_path.name}", flush=True)
    except Exception as e:
        _log_part(f"[partitionnement] Erreur écriture cache clusters: {e}", flush=True)

    cache_subcatchments_path = gpkg_p.with_suffix(".subcatchments_cache.json")
    try:
        sub_cache_data = {
            "type": "FeatureCollection",
            "features": voronoi_geojson.get("features", []),
            "total_area_ha": total_surface_ha,
            "subcatchments_count": len(gdf_voronoi)
        }
        with open(cache_subcatchments_path, "w", encoding="utf-8") as f:
            json.dump(sub_cache_data, f, ensure_ascii=False)
        _log_part(f"[partitionnement] Cache disque subcatchments mis à jour : {cache_subcatchments_path.name}", flush=True)
    except Exception as e:
        _log_part(f"[partitionnement] Erreur écriture cache subcatchments: {e}", flush=True)

    elapsed = round(time.time() - t0, 2)
    _log_part(f"[partitionnement] Traitement complet terminé en {elapsed} secondes.", flush=True)

    return {
        "status": "success",
        "nb_bassins": len(gdf_bassins_79),
        "surface_totale_ha": total_surface_ha,
        "nb_voronoi": len(gdf_voronoi),
        "nb_orphelins": len(gdf_orphelins_regards),
        "elapsed_seconds": elapsed,
        "orphelins_file": str(orphelins_geojson_path)
    }
