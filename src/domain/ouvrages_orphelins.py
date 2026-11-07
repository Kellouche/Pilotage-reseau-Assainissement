"""
Module de détection et de raccordement des ouvrages spéciaux orphelins.
Permet d'identifier à proximité d'un cluster hydraulique (< 120 m) :
- Les déversoirs d'orage (DVO)
- Les trop-pleins de réseau
- Les stations de relevage (SR)
- Les rejets directs et exutoires non raccordés
et de proposer un raccordement virtuel avant simulation hydrodynamique SWMM 5.2.
"""

import json
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional

import geopandas as gpd
from shapely.geometry import Point
import pyproj

logger = logging.getLogger(__name__)

# Prix unitaire moyen tout compris (terrassement, lit de pose, fourniture & pose DN600, remblai, réfection voirie)
PRIX_UNITAIRE_RACCORDEMENT_DZD_ML = 45000.0


def _obtenir_reprojecteurs(crs_source="EPSG:32631", crs_cible="EPSG:4326"):
    """Retourne les transformateurs de coordonnées bidirectionnels."""
    try:
        transformer_to_wgs = pyproj.Transformer.from_crs(crs_source, crs_cible, always_xy=True).transform
        transformer_to_utm = pyproj.Transformer.from_crs(crs_cible, crs_source, always_xy=True).transform
        return transformer_to_wgs, transformer_to_utm
    except Exception as e:
        logger.warning("Erreur initialisation pyproj: %s", e)
        return None, None


def detecter_ouvrages_orphelins_proches(
    gpkg_path: str,
    cluster_id: int,
    rayon_max_m: float = 120.0,
    G_topo: Optional[Any] = None
) -> Dict[str, Any]:
    """
    Détecte les ouvrages spéciaux, stations de relevage et déversoirs d'orage
    situés à moins de rayon_max_m des regards du cluster sélectionné.
    """
    gpkg_p = Path(gpkg_path)
    if not gpkg_p.exists():
        return {"cluster_id": cluster_id, "nb_ouvrages_trouves": 0, "ouvrages": []}

    cache_path = gpkg_p.with_suffix(".clusters_cache.json")
    if not cache_path.exists():
        # Recherche fallback dans uploads/ si le fichier gpkg provient de la racine ou d'un projet uploadé
        cands = list(Path("uploads").glob(f"**/*{gpkg_p.stem}*.clusters_cache.json"))
        if not cands:
            cands = list(Path("uploads").glob("**/*clusters_cache.json"))
        if cands:
            cache_path = cands[0]
        else:
            return {"cluster_id": cluster_id, "nb_ouvrages_trouves": 0, "ouvrages": []}

    try:
        with open(cache_path, "r", encoding="utf-8") as f:
            cdata = json.load(f)
    except Exception as e:
        logger.error("Erreur lecture clusters_cache: %s", e)
        return {"cluster_id": cluster_id, "nb_ouvrages_trouves": 0, "ouvrages": []}

    # 1. Trouver le cluster cible
    target_c = None
    for c in cdata.get("resultats", []):
        c_id = c.get("cluster", {}).get("id")
        if c_id is None:
            c_id = c.get("id") or c.get("bassin_id")
        if str(c_id) == str(cluster_id):
            target_c = c
            break

    if not target_c:
        return {"cluster_id": cluster_id, "nb_ouvrages_trouves": 0, "ouvrages": []}

    to_wgs, to_utm = _obtenir_reprojecteurs("EPSG:32631", "EPSG:4326")
    if not to_utm or not to_wgs:
        return {"cluster_id": cluster_id, "nb_ouvrages_trouves": 0, "ouvrages": []}

    # 2. Obtenir les couches du GeoPackage
    import pyogrio
    try:
        available_layers = [l[0] for l in pyogrio.list_layers(gpkg_p)]
    except Exception as e:
        logger.error("Erreur list_layers: %s", e)
        return {"cluster_id": cluster_id, "nb_ouvrages_trouves": 0, "ouvrages": []}

    r_layers = [l for l in available_layers if "regard" in l.lower()]
    if not r_layers:
        return {"cluster_id": cluster_id, "nb_ouvrages_trouves": 0, "ouvrages": []}

    try:
        gdf_r = gpd.read_file(gpkg_p, layer=r_layers[0])
    except Exception as e:
        logger.error("Erreur lecture regards: %s", e)
        return {"cluster_id": cluster_id, "nb_ouvrages_trouves": 0, "ouvrages": []}

    # 3. Identifier les vrais regards du cluster via le graphe ou le cache
    nodes_real_set = set()
    exutoire_nom = target_c.get("exutoire", {}).get("nom")
    if G_topo is None:
        try:
            from api.routes.clusters import _get_graph
            G_topo = _get_graph(str(gpkg_p))
        except Exception:
            pass

    if G_topo is not None and exutoire_nom and G_topo.has_node(exutoire_nom):
        from src.domain.detecteur_clusters import tracer_cluster_depuis_exutoire
        trace = tracer_cluster_depuis_exutoire(G_topo, exutoire_nom)
        for u, v in trace.get("edges", []):
            u_s = str(u).replace(".0", "")
            v_s = str(v).replace(".0", "")
            # On conserve les vrais nœuds de voirie (codes numériques ou regards)
            if not any(k in u_s.lower() for k in ["ouvrage", "station", "step"]):
                nodes_real_set.add(u_s)
            if not any(k in v_s.lower() for k in ["ouvrage", "station", "step"]):
                nodes_real_set.add(v_s)

    # Fallback si le graphe n'a pas renvoyé de nœuds : extraire depuis le GeoJSON
    if not nodes_real_set:
        c_features = target_c.get("geojson", {}).get("features", [])
        for f in c_features:
            props = f.get("properties", {})
            am = props.get("ID_AMONT") or props.get("id_amont")
            av = props.get("ID_AVAL") or props.get("id_aval")
            if am:
                nodes_real_set.add(str(am).replace(".0", ""))
            if av:
                nodes_real_set.add(str(av).replace(".0", ""))

    # Si toujours vide, récupérer par intersection spatiale avec le polygone du cluster
    if not nodes_real_set:
        for f in target_c.get("geojson", {}).get("features", []):
            if f.get("geometry", {}).get("type") == "Polygon":
                poly_wgs = shape(f["geometry"])
                # Bounding box des regards
                for idx, r_row in gdf_r.iterrows():
                    pt = r_row.geometry
                    if pt:
                        wgs_c = to_wgs(pt.x, pt.y)
                        if poly_wgs.contains(Point(wgs_c[0], wgs_c[1])):
                            nodes_real_set.add(str(r_row.get("Code", idx)).replace(".0", ""))
                break

    # Filtrer les regards du cluster
    gdf_r_cluster = gdf_r[gdf_r["Code"].astype(str).str.replace(".0", "").isin(nodes_real_set)]
    if gdf_r_cluster.empty:
        # Fallback de secours : utiliser tous les regards à l'intérieur du buffer du cluster
        gdf_r_cluster = gdf_r

    # 4. Parcourir les couches d'ouvrages spéciaux candidats
    special_layer_defs = [
        ("ouvrages_speciaux", "Trop-plein de réseau", "#a855f7", [l for l in available_layers if "ouvrage" in l.lower() and "specia" in l.lower()]),
        ("station_relevage", "Station de relevage (SR)", "#f97316", [l for l in available_layers if "station" in l.lower()]),
        ("rejets", "Exutoire / Rejet direct", "#22c55e", [l for l in available_layers if "rejet" in l.lower()]),
    ]

    ouvrages_detectes = []
    seen_coords = set()

    for cat_key, default_label, badge_color, lyr_candidates in special_layer_defs:
        if not lyr_candidates:
            continue
        lyr_name = lyr_candidates[0]
        try:
            gdf_spec = gpd.read_file(gpkg_p, layer=lyr_name)
        except Exception as e_read:
            logger.warning("Impossible de lire %s: %s", lyr_name, e_read)
            continue

        for idx, row in gdf_spec.iterrows():
            pt = row.geometry
            if pt is None or pt.is_empty:
                continue

            # Clé d'unicité spatiale (éviter les doublons à moins de 2m)
            coord_key = (round(pt.x, 1), round(pt.y, 1))
            if coord_key in seen_coords:
                continue

            # Calcul de distance minimale aux regards réels du cluster
            dists_to_cluster = gdf_r_cluster.geometry.distance(pt)
            if dists_to_cluster.empty:
                continue

            min_d = float(dists_to_cluster.min())

            # Si l'ouvrage est à portée utile (< rayon_max_m) et pas déjà confondu (< 0.5m)
            if 0.5 <= min_d <= rayon_max_m:
                seen_coords.add(coord_key)
                r_idx = dists_to_cluster.idxmin()
                nearest_r = gdf_r_cluster.loc[r_idx]
                r_code = str(nearest_r.get("Code", f"REG_{r_idx}")).replace(".0", "")
                r_pt = nearest_r.geometry

                # Coordonnées WGS84 [lat, lon] pour Leaflet
                r_lon, r_lat = to_wgs(r_pt.x, r_pt.y)
                ouv_lon, ouv_lat = to_wgs(pt.x, pt.y)

                # Résolution précise du type et du nom
                type_ouvr_raw = row.get("TYPEOUVR") or row.get("Type") or row.get("TYPE") or row.get("FONCTIOP6")
                type_label = default_label
                if type_ouvr_raw and str(type_ouvr_raw).lower() != "nan":
                    type_label = str(type_ouvr_raw)

                nom_raw = row.get("NOMPRR") or row.get("Nom") or row.get("NOM") or row.get("Code") or f"{cat_key}_{idx+1}"
                nom_str = str(nom_raw).replace(".0", "")
                if "nan" in nom_str.lower() or not nom_str:
                    nom_str = f"Ouvrage #{idx+1}"

                # Détermination du badge et de la catégorie
                current_badge = badge_color
                cat_resolved = cat_key
                if "déversoir" in type_label.lower() or "dvo" in type_label.lower():
                    current_badge = "#06b6d4"  # cyan
                    cat_resolved = "deversoir_orage"
                elif "trop" in type_label.lower():
                    current_badge = "#a855f7"  # violet
                    cat_resolved = "trop_plein"
                elif "station" in type_label.lower() or "refoulement" in type_label.lower():
                    current_badge = "#f97316"  # orange
                    cat_resolved = "station_relevage"
                elif "rejet" in type_label.lower():
                    current_badge = "#22c55e"  # vert
                    cat_resolved = "rejet"

                cout_estime = max(int(min_d * PRIX_UNITAIRE_RACCORDEMENT_DZD_ML), 150000)

                ouvrages_detectes.append({
                    "ouvrage_id": f"orph_{cat_resolved}_{idx+1}",
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

    # Trier par distance croissante
    ouvrages_detectes.sort(key=lambda x: x["distance_m"])

    return {
        "cluster_id": cluster_id,
        "nb_ouvrages_trouves": len(ouvrages_detectes),
        "ouvrages": ouvrages_detectes,
        "prix_unitaire_dzd_ml": PRIX_UNITAIRE_RACCORDEMENT_DZD_ML,
    }
