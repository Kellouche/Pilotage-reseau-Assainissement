"""
================================================================================
Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
Auteur : Dr Abdelhakim KELLOUCHE
Date de création : 2026-04-20
Date de modification : 2026-11-27 (suppression du repli glob inter-réseaux : résolution du cache clusters restreinte au sidecar du gpkg et à sa version immuable SHA-256)
Objet : Détection, isolement et traitement des tronçons et ouvrages orphelins
================================================================================
"""

import json
import logging
from collections import OrderedDict
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple, Union

import geopandas as gpd
import numpy as np
import pyproj
from shapely.geometry import Point, shape, LineString, box
from shapely.ops import transform, unary_union

logger = logging.getLogger(__name__)

# Prix unitaire estimé pour le raccordement en tranchée courte DN 600 mm (ONA / BTPH Algérie)
PRIX_UNITAIRE_RACCORDEMENT_DZD_ML = 45000.0

# Cache mémoire des artefacts coûteux de la détection : JSON clusters (~13 Mo)
# + couches GPKG lues (regards ~10k lignes) + topo par cluster. Sans cache,
# chaque appel payait ~1,3 s de lecture/parse ; avec, ~50 ms.
# Invalidé par (mtime, taille) du clusters_cache.json — régénéré à chaque
# partitionnement, donc une nouvelle version du réseau invalide tout.
# LRU borné à 4 réseaux pour ne pas gonfler la mémoire (chaque entrée
# peut retenir plusieurs dizaines de Mo de GeoDataFrames).
_DETECTION_CACHE: "OrderedDict[str, Dict[str, Any]]" = OrderedDict()
_DETECTION_CACHE_MAX = 4


def _obtenir_reprojecteurs(src_crs: str = "EPSG:32631", dst_crs: str = "EPSG:4326"):
    try:
        transformer_to_wgs = pyproj.Transformer.from_crs(src_crs, dst_crs, always_xy=True).transform
        transformer_to_utm = pyproj.Transformer.from_crs(dst_crs, src_crs, always_xy=True).transform
        return transformer_to_wgs, transformer_to_utm
    except Exception as e:
        logger.error("Erreur initialisation transformer CRS: %s", e)
        return None, None


def detecter_ouvrages_orphelins_proches(
    gpkg_path: str,
    cluster_id: Union[int, str],
    rayon_max_m: float = 45.0,
    G_topo: Optional[Any] = None
) -> Dict[str, Any]:
    """
    Détecte les ouvrages spéciaux, stations de relevage et déversoirs d'orage
    situés à moins de rayon_max_m (45 m par défaut) des regards du cluster sélectionné.
    Exécution spatiale ultra-rapide (< 1 seconde) sans charger le graphe complet de 10 000 nœuds.
    """
    gpkg_p = Path(gpkg_path)
    if not gpkg_p.exists():
        return {"cluster_id": cluster_id, "nb_ouvrages_trouves": 0, "ouvrages": []}

    cache_path = gpkg_p.with_suffix(".clusters_cache.json")
    if not cache_path.exists():
        # Repli versionné (étape 3B) : data/.gpkg_cache/<sha256>.clusters_cache.json
        # — le sidecar historique peut avoir été purgé lors d'un ré-import.
        try:
            from api.services.gpkg_versions import GPKG_CACHE_DIR, sha256_fichier
            vc = Path(GPKG_CACHE_DIR) / f"{sha256_fichier(gpkg_p)}.clusters_cache.json"
            if vc.exists():
                cache_path = vc
        except Exception:
            pass
    if not cache_path.exists():
        # AUCUN repli inter-réseaux : charger le cache d'un AUTRE GeoPackage
        # (premier glob venu) reviendrait à détecter des ouvrages sur un réseau
        # étranger — confusion de données inacceptable entre réseaux/projets.
        # Le cluster est résolu uniquement depuis le sidecar du gpkg ou sa
        # version immuable (empreinte SHA-256). Sinon : retour explicite.
        logger.warning(
            "detecter_ouvrages_orphelins_proches: clusters_cache introuvable pour %s "
            "(ni sidecar « %s », ni version immuable SHA-256) — retour 0 ouvrage explicite.",
            gpkg_p,
            gpkg_p.with_suffix(".clusters_cache.json").name,
        )
        return {
            "cluster_id": cluster_id,
            "nb_ouvrages_trouves": 0,
            "ouvrages": [],
            "status": "cache_clusters_absent",
        }

    # Entrée de cache pour ce réseau (invalidée si le cache disque change)
    try:
        _st = cache_path.stat()
        _sig = (_st.st_mtime, _st.st_size)
    except OSError:
        _sig = None
    _cle = str(cache_path)
    entree = _DETECTION_CACHE.get(_cle)
    if entree is None or entree.get("sig") != _sig:
        entree = {"sig": _sig, "cdata": None, "gdf_r": None, "layers": None,
                  "to_wgs": None, "to_utm": None, "spec": {}, "topos": {}}
        _DETECTION_CACHE[_cle] = entree
        _DETECTION_CACHE.move_to_end(_cle)
        while len(_DETECTION_CACHE) > _DETECTION_CACHE_MAX:
            _DETECTION_CACHE.popitem(last=False)

    cdata = entree.get("cdata")
    if cdata is None:
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                cdata = json.load(f)
        except Exception as e:
            logger.error("Erreur lecture clusters_cache: %s", e)
            return {"cluster_id": cluster_id, "nb_ouvrages_trouves": 0, "ouvrages": []}
        entree["cdata"] = cdata

    # 1. Trouver le cluster cible (par id numérique, id texte, nom de cluster ou nom d'exutoire)
    target_c = None
    target_str = str(cluster_id).strip().lower()
    for c in cdata.get("resultats", []):
        cid = str(c.get("cluster", {}).get("id", "")).strip().lower()
        cnom = str(c.get("cluster", {}).get("nom", "")).strip().lower()
        exnom = str(c.get("exutoire", {}).get("nom", "")).strip().lower()
        if cid == target_str or cnom == target_str or exnom == target_str:
            target_c = c
            break
        if cnom.startswith(f"{target_str}_") or exnom.startswith(f"{target_str}_"):
            target_c = c
            break
        if len(target_str) >= 5 and (target_str in cnom or target_str in exnom or cnom in target_str):
            target_c = c
            break

    if not target_c:
        return {"cluster_id": cluster_id, "nb_ouvrages_trouves": 0, "ouvrages": []}

    to_wgs, to_utm = entree.get("to_wgs"), entree.get("to_utm")
    if to_wgs is None or to_utm is None:
        to_wgs, to_utm = _obtenir_reprojecteurs("EPSG:32631", "EPSG:4326")
        if not to_utm or not to_wgs:
            return {"cluster_id": cluster_id, "nb_ouvrages_trouves": 0, "ouvrages": []}
        entree["to_wgs"], entree["to_utm"] = to_wgs, to_utm

    # 2. Obtenir les couches du GeoPackage (couche regards lue une seule fois)
    import pyogrio
    if entree.get("layers") is None:
        try:
            entree["layers"] = [l[0] for l in pyogrio.list_layers(gpkg_p)]
        except Exception as e:
            logger.error("Erreur list_layers: %s", e)
            return {"cluster_id": cluster_id, "nb_ouvrages_trouves": 0, "ouvrages": []}
    available_layers = entree["layers"]

    r_layers = [l for l in available_layers if "regard" in l.lower()]
    if not r_layers:
        return {"cluster_id": cluster_id, "nb_ouvrages_trouves": 0, "ouvrages": []}

    if entree.get("gdf_r") is None:
        try:
            entree["gdf_r"] = gpd.read_file(gpkg_p, layer=r_layers[0])
        except Exception as e:
            logger.error("Erreur lecture regards: %s", e)
            return {"cluster_id": cluster_id, "nb_ouvrages_trouves": 0, "ouvrages": []}
    gdf_r = entree["gdf_r"]

    # 3. Filtrer précisément les regards du cluster par les conduites réelles du
    # sous-bassin — résultat mis en cache par cluster (union + filtrage ~0,1-0,5 s)
    _topo_key = str(cluster_id)
    _topo = entree["topos"].get(_topo_key, "absent")
    if _topo == "absent":
        gdf_r_cluster = None
        network_geom = None
        line_feats = [f for f in target_c.get("geojson", {}).get("features", []) if f.get("geometry", {}).get("type") in ("LineString", "MultiLineString")]
        if line_feats:
            try:
                line_geoms = [transform(to_utm, shape(f["geometry"])) for f in line_feats]
                network_geom = unary_union(line_geoms)
                gdf_r_cluster = gdf_r[gdf_r.geometry.distance(network_geom) <= 2.5]
            except Exception as e_tr:
                logger.warning("Erreur filtrage regards par conduites: %s", e_tr)

        if gdf_r_cluster is None or gdf_r_cluster.empty:
            poly_feats = [f for f in target_c.get("geojson", {}).get("features", []) if f.get("geometry", {}).get("type") == "Polygon"]
            if poly_feats:
                try:
                    poly_wgs = shape(poly_feats[0]["geometry"])
                    poly_utm = transform(to_utm, poly_wgs)
                    gdf_r_cluster = gdf_r[gdf_r.geometry.within(poly_utm.buffer(2.0))]
                except Exception:
                    gdf_r_cluster = None

        # None = cluster sans regard rattaché (mis en cache pour ne pas recalculer)
        entree["topos"][_topo_key] = (gdf_r_cluster if (gdf_r_cluster is not None and not gdf_r_cluster.empty) else None, network_geom)
        _topo = entree["topos"][_topo_key]
    gdf_r_cluster, network_geom = _topo if _topo[0] is not None else (None, _topo[1])

    # Si aucun regard n'est rattaché à ce cluster, ne JAMAIS fallback sur tous les regards de la ville !
    if gdf_r_cluster is None or gdf_r_cluster.empty:
        return {"cluster_id": cluster_id, "nb_ouvrages_trouves": 0, "ouvrages": []}

    # 4. Parcourir les couches d'ouvrages spéciaux candidats
    special_layer_defs = [
        ("ouvrages_speciaux", "Trop-plein de réseau", "#a855f7", [l for l in available_layers if "ouvrage" in l.lower() and "specia" in l.lower()]),
        ("station_relevage", "Station de relevage (SR)", "#f97316", [l for l in available_layers if "station" in l.lower()]),
        ("rejets", "Exutoire / Rejet direct", "#22c55e", [l for l in available_layers if "rejet" in l.lower()]),
    ]

    ouvrages_detectes = []
    seen_coords = set()
    seen_ouv_ids = set()

    # Enveloppe de recherche : bounds des regards du cluster élargies du rayon.
    # Tout ouvrage à moins de rayon_max_m d'un regard du cluster est forcément
    # dans cette boîte — le STRtree ne retient que ces candidats réels.
    _rb = gdf_r_cluster.total_bounds
    _search_geom = box(_rb[0] - rayon_max_m, _rb[1] - rayon_max_m,
                       _rb[2] + rayon_max_m, _rb[3] + rayon_max_m)

    for cat_key, default_label, badge_color, lyr_candidates in special_layer_defs:
        if not lyr_candidates:
            continue
        lyr_name = lyr_candidates[0]
        if cat_key not in entree["spec"]:
            try:
                entree["spec"][cat_key] = gpd.read_file(gpkg_p, layer=lyr_name)
            except Exception as e_read:
                logger.warning("Impossible de lire %s: %s", lyr_name, e_read)
                entree["spec"][cat_key] = None
        gdf_spec = entree["spec"][cat_key]
        if gdf_spec is None:
            continue

        # Index spatial de la couche (construit une seule fois par réseau)
        _tree_key = f"_tree_{cat_key}"
        if _tree_key not in entree["spec"]:
            try:
                from shapely import STRtree
                entree["spec"][_tree_key] = STRtree(np.asarray(gdf_spec.geometry))
            except Exception:
                entree["spec"][_tree_key] = None
        _tree = entree["spec"].get(_tree_key)
        _positions = _tree.query(_search_geom) if _tree is not None else range(len(gdf_spec))

        for _pos in _positions:
            row = gdf_spec.iloc[_pos]
            idx = row.name
            pt = row.geometry
            if pt is None or pt.is_empty:
                continue

            coord_key = (round(pt.x, 1), round(pt.y, 1))
            if coord_key in seen_coords:
                continue

            # Calcul de distance aux regards admissibles du cluster
            dists_to_cluster = gdf_r_cluster.geometry.distance(pt)
            regards_cands = gdf_r_cluster[dists_to_cluster <= rayon_max_m].copy()
            if regards_cands.empty:
                continue

            seen_coords.add(coord_key)

            # Règle de génie civil universelle : Privilégier les tracés sans cisaillement de canalisation existante
            meilleur_r = None
            meilleur_dist = 999999.0
            meilleur_crosses = True

            for r_idx, cand_r in regards_cands.iterrows():
                d_c = float(cand_r.geometry.distance(pt))
                c_line = LineString([cand_r.geometry, pt])
                crosses = False
                if network_geom is not None and c_line.length > 2.0:
                    try:
                        s_line = LineString([c_line.interpolate(0.5), c_line.interpolate(c_line.length - 0.5)])
                        crosses = bool(s_line.intersects(network_geom))
                    except Exception:
                        crosses = False

                if meilleur_r is None:
                    meilleur_r = cand_r
                    meilleur_dist = d_c
                    meilleur_crosses = crosses
                else:
                    if not crosses and meilleur_crosses:
                        meilleur_r = cand_r
                        meilleur_dist = d_c
                        meilleur_crosses = False
                    elif crosses == meilleur_crosses and d_c < meilleur_dist:
                        meilleur_r = cand_r
                        meilleur_dist = d_c

            if meilleur_r is None:
                continue

            closest_r = meilleur_r
            min_d = meilleur_dist
            closest_idx = closest_r.name

            r_code = str(closest_r.get("Code", closest_r.get("code", closest_r.get("id", f"R_{closest_idx}")))).replace(".0", "")
            r_lon, r_lat = to_wgs(closest_r.geometry.x, closest_r.geometry.y)
            ouv_lon, ouv_lat = to_wgs(pt.x, pt.y)

            raw_nom = str(row.get("Nom", row.get("nom", row.get("Code", row.get("code", ""))))).strip()
            type_label = str(row.get("type_ouvrage", row.get("Type", row.get("type", default_label)))).strip()
            if "nan" in type_label.lower() or not type_label:
                type_label = default_label

            # Résolution sémantique des noms usuels d'ouvrages
            if "nan" in raw_nom.lower() or not raw_nom:
                if cat_key == "station_relevage":
                    nom_str = "Hay Houria N°01"
                else:
                    nom_str = f"Ouvrage #{idx+1}"
            else:
                nom_str = raw_nom

            # Détermination du badge et de la catégorie
            current_badge = badge_color
            cat_resolved = cat_key
            if "déversoir" in type_label.lower() or "dvo" in type_label.lower() or "10" in nom_str:
                current_badge = "#06b6d4"  # cyan
                cat_resolved = "deversoir_orage"
                type_label = "Déversoir d'orage (DVO)"
                if nom_str == "10":
                    nom_str = "Code 10"
            elif "trop" in type_label.lower() or "11" in nom_str:
                current_badge = "#a855f7"  # violet
                cat_resolved = "trop_plein"
                type_label = "Trop-plein de réseau"
                if nom_str == "11":
                    nom_str = "Code 11"
            elif "station" in type_label.lower() or "refoulement" in type_label.lower() or cat_key == "station_relevage":
                current_badge = "#f97316"  # orange
                cat_resolved = "station_relevage"
                type_label = "Station de relevage (SR)"
                if nom_str.startswith("Ouvrage"):
                    nom_str = "Hay Houria N°01"
            elif "rejet" in type_label.lower() or cat_key == "rejets":
                current_badge = "#22c55e"  # vert
                cat_resolved = "rejet"
                type_label = "Exutoire / Rejet direct"

            cout_estime = max(int(min_d * PRIX_UNITAIRE_RACCORDEMENT_DZD_ML), 150000)

            base_id = f"orph_{cat_resolved}_{idx+1}"
            cand_id = base_id
            seq = 2
            while cand_id in seen_ouv_ids:
                cand_id = f"{base_id}_{seq}"
                seq += 1
            seen_ouv_ids.add(cand_id)

            ouvrages_detectes.append({
                "id": cand_id,
                "ouvrage_id": cand_id,
                "nom": f"{type_label} ({nom_str})",
                "code_ouvrage": nom_str,
                "type": cat_resolved,
                "type_label": type_label,
                "badge_color": current_badge,
                "distance_m": round(min_d, 1),
                "regard_proche_id": r_code,
                "regard_coord_wgs84": [round(r_lat, 6), round(r_lon, 6)],
                "ouvrage_coord_wgs84": [round(ouv_lat, 6), round(ouv_lon, 6)],
                "diametre_recommande_mm": 600,
                "cout_estime_dzd": cout_estime,
                "recommandation": f"Raccordement court ({round(min_d, 1)} m) recommandé vers {type_label} ({nom_str}) pour décharger immédiatement le réseau amont."
            })

    # Règle de génie civil universelle : Appariement Station de Relevage + Trop-plein de sécurité
    # Si un trop-plein est situé à moins de 30 m d'une station de relevage, ils forment un complexe unique
    sr_ouvrages = [o for o in ouvrages_detectes if o["type"] == "station_relevage"]
    if sr_ouvrages:
        for sr in sr_ouvrages:
            sr_lat, sr_lon = sr["ouvrage_coord_wgs84"]
            for o in ouvrages_detectes:
                if o["type"] == "trop_plein":
                    tp_lat, tp_lon = o["ouvrage_coord_wgs84"]
                    d_sr_tp = ((sr_lat - tp_lat)**2 + (sr_lon - tp_lon)**2)**0.5 * 111320.0
                    if d_sr_tp <= 30.0:
                        # Aligner le regard amont du trop-plein sur celui de la station (évite les tracés en ciseaux)
                        o["regard_proche_id"] = sr["regard_proche_id"]
                        o["regard_coord_wgs84"] = sr["regard_coord_wgs84"]
                        o["nom"] = f"Trop-plein de secours (By-pass {sr['code_ouvrage']})"
                        o["type_label"] = "Trop-plein de secours (SR)"
                        o["recommandation"] = f"Trop-plein de sécurité apparié à la {sr['nom']} pour évacuation gravitaire des pointes de crue sans cisaillement de voirie."

    # Trier par distance croissante
    ouvrages_detectes.sort(key=lambda x: x["distance_m"])

    return {
        "cluster_id": cluster_id,
        "nb_ouvrages_trouves": len(ouvrages_detectes),
        "ouvrages": ouvrages_detectes,
        "prix_unitaire_dzd_ml": PRIX_UNITAIRE_RACCORDEMENT_DZD_ML,
    }
