# -*- coding: utf-8 -*-
"""
================================================================================
Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
Auteur : Dr Abdelhakim KELLOUCHE
Date de création : 2026-11-27
Date de modification : 2026-11-27
Objet : Sous-bassins, detection des orphelins et export INP du reseau (extrait de routes/network.py)
================================================================================
"""

import json
import logging
import re
from pathlib import Path
from typing import List, Optional

import geopandas as gpd
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from api import schemas, crud
from api.database import get_db
from api.models import Project, Organization
from api.core.security import (
    get_tenant_context,
    get_tenant_context_optional,
    require_role,
    TenantContext,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/network", tags=["Réseau"])


@router.get("/subcatchments")
def get_network_subcatchments(
    snapshot: Optional[str] = None,
    ctx: TenantContext = Depends(require_role("viewer")),
    db: Session = Depends(get_db)
):
    """
    Génère et retourne les sous-bassins versants élémentaires (Subcatchments)
    au format GeoJSON pour le réseau actif du projet de l'organisation.
    """
    import json
    from src.domain.hydrologie import GenerateurHydrologie
    import geopandas as gpd
    from api.services.simulation_service import resoudre_gpkg_effectif_pour_projet
    from api.services.gpkg_versions import (
        resoudre_snapshot_pour_lecture, GpkgSimulationError)

    project = db.query(Project).filter(
        Project.org_id == ctx.org_id,
        Project.is_archived.is_(False)
    ).first()
    gpkg_path = None
    if project is not None:
        try:
            snap_ctx = resoudre_snapshot_pour_lecture(db, project, snapshot)
            gpkg_path = snap_ctx["path"]
        except GpkgSimulationError:
            if snapshot:
                raise HTTPException(status_code=404, detail="Ressource introuvable")
            gpkg_path = resoudre_gpkg_effectif_pour_projet(db, project)

    if gpkg_path is None or not gpkg_path.exists():
        return {
            "type": "FeatureCollection",
            "features": [],
            "total_area_ha": 0.0,
            "subcatchments_count": 0,
            "message": "Aucun réseau chargé pour ce projet."
        }

    # Vérification cache rapide sur disque
    cache_sub_path = gpkg_path.with_suffix(".subcatchments_cache.json")
    if cache_sub_path.exists():
        try:
            if cache_sub_path.stat().st_mtime >= gpkg_path.stat().st_mtime:
                with open(cache_sub_path, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception as e:
            print(f"[subcatchments] Erreur lecture cache: {e}", flush=True)

    try:
        layers = gpd.list_layers(str(gpkg_path))['name'].tolist()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur lecture couches GPKG: {e}")

    # Si la couche sous_bassins_voronoi existe déjà dans le GPKG, l'utiliser directement
    if "sous_bassins_voronoi" in layers:
        try:
            subcatchments = gpd.read_file(str(gpkg_path), layer="sous_bassins_voronoi")
            sub_wgs84 = subcatchments.to_crs("EPSG:4326") if subcatchments.crs != "EPSG:4326" else subcatchments
            geojson = json.loads(sub_wgs84.to_json(na="drop"))
            total_area_ha = round(float(subcatchments['area_ha'].sum()), 4) if 'area_ha' in subcatchments else 0.0
            res = {
                **geojson,
                "total_area_ha": total_area_ha,
                "subcatchments_count": len(subcatchments)
            }
            with open(cache_sub_path, "w", encoding="utf-8") as f:
                json.dump(res, f, ensure_ascii=False)
            return res
        except Exception as e:
            print(f"[subcatchments] Erreur lecture couche sous_bassins_voronoi: {e}", flush=True)

    regard_layer = next((l for l in layers if 'regard' in l.lower()), None)
    pipe_layer = next((l for l in layers if any(k in l.lower() for k in ['canalisat', 'conduit', 'pipe', 'troncon']) and 'désaffect' not in l.lower() and 'desaffect' not in l.lower()), None)

    if not regard_layer:
        return {
            "type": "FeatureCollection",
            "features": [],
            "total_area_ha": 0.0,
            "subcatchments_count": 0
        }

    regards_gdf = gpd.read_file(str(gpkg_path), layer=regard_layer)
    canalisations_gdf = gpd.read_file(str(gpkg_path), layer=pipe_layer) if pipe_layer else gpd.GeoDataFrame()

    # Projets issus d'une extraction par pochoir : la couche 'pochoir'
    # délimite le bassin versant étudié — les sous-bassins Voronoï sont
    # alors clipés à cette emprise (et non à l'enveloppe de buffers,
    # qui déborde du bassin puisque les objets sont exportés entiers).
    emprise_bassin = None
    pochoir_layer = next(
        (l for l in layers if 'pochoir' in l.lower()), None)
    if pochoir_layer:
        try:
            pg = gpd.read_file(str(gpkg_path), layer=pochoir_layer)
            if isinstance(pg, gpd.GeoDataFrame) and not pg.empty:
                if pg.crs is None and regards_gdf.crs is not None:
                    pg = pg.set_crs(regards_gdf.crs)
                elif pg.crs is not None and regards_gdf.crs is not None \
                        and str(pg.crs) != str(regards_gdf.crs):
                    pg = pg.to_crs(regards_gdf.crs)
                emprise_bassin = pg.union_all()
        except Exception as e:
            print(f"[subcatchments] Emprise pochoir illisible: {e}", flush=True)
            emprise_bassin = None

    gh = GenerateurHydrologie()
    subcatchments = gh.generer_sous_bassins(
        regards_gdf, canalisations_gdf, emprise_bassin=emprise_bassin)

    if subcatchments.empty:
        return {
            "type": "FeatureCollection",
            "features": [],
            "total_area_ha": 0.0,
            "subcatchments_count": 0
        }

    sub_wgs84 = subcatchments.to_crs("EPSG:4326") if subcatchments.crs != "EPSG:4326" else subcatchments
    geojson = json.loads(sub_wgs84.to_json(na="drop"))
    total_area_ha = round(float(subcatchments['area_ha'].sum()), 4)

    return {
        **geojson,
        "total_area_ha": total_area_ha,
        "subcatchments_count": len(subcatchments)
    }


@router.get("/orphelins/geojson")
def get_network_orphelins_geojson(
    ctx: TenantContext = Depends(require_role("viewer")),
    db: Session = Depends(get_db)
):
    """
    Retourne la liste des éléments orphelins (regards déconnectés du réseau amont-aval)
    au format GeoJSON pour audit et correction.
    """
    import json
    import geopandas as gpd
    from api.services.simulation_service import resoudre_gpkg_effectif_pour_projet

    project = db.query(Project).filter(
        Project.org_id == ctx.org_id,
        Project.is_archived.is_(False)
    ).first()
    gpkg_path = resoudre_gpkg_effectif_pour_projet(db, project) if project else None

    if not gpkg_path or not gpkg_path.exists():
        raise HTTPException(status_code=404, detail="Ressource introuvable")

    # 1. Vérifier si elements_orphelins.geojson existe
    orph_json_p = gpkg_path.parent / "elements_orphelins.geojson"
    if orph_json_p.exists():
        with open(orph_json_p, "r", encoding="utf-8") as f:
            return json.load(f)

    # 2. Sinon lire depuis la couche GPKG elements_orphelins_regards
    try:
        layers = gpd.list_layers(str(gpkg_path))['name'].tolist()
        if "elements_orphelins_regards" in layers:
            gdf = gpd.read_file(str(gpkg_path), layer="elements_orphelins_regards")
            gdf_wgs84 = gdf.to_crs("EPSG:4326") if gdf.crs != "EPSG:4326" else gdf
            return json.loads(gdf_wgs84.to_json(na="drop"))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur lecture orphelins: {e}")

    return {"type": "FeatureCollection", "features": [], "message": "Aucun orphelin trouvé"}


@router.get("/orphelins")
def get_network_orphelins(
    ctx: TenantContext = Depends(require_role("viewer")),
    db: Session = Depends(get_db)
):
    """
    Inventaire des éléments orphelins du réseau actif, pour le listing
    cliquable de la carte opérationnelle (/carte) :

    - noeuds_orphelins : nœuds déclarés (regards, rejets, ouvrages…) sans
      aucune conduite connectée (degré 0 dans le graphe) ;
    - troncons_orphelins : conduites exclues du graphe (extrémité non
      résolue par la chaîne canonique) et conduites des composantes
      connexes sans exutoire (sous-réseaux qui ne drainent nulle part).

    Coordonnées retournées en WGS84 (EPSG:4326) pour affichage cartographique.
    """
    import math
    import networkx as nx
    import pyproj
    from api.routes.clusters import _get_graph
    from api.services.simulation_service import resoudre_gpkg_effectif_pour_projet
    from src.domain.detecteur_clusters import trouver_exutoires_physiques

    project = db.query(Project).filter(
        Project.org_id == ctx.org_id,
        Project.is_archived.is_(False)
    ).first()
    gpkg_path = resoudre_gpkg_effectif_pour_projet(db, project) if project else None

    if not gpkg_path or not gpkg_path.exists():
        raise HTTPException(status_code=404, detail="Ressource introuvable")

    G = _get_graph(str(gpkg_path))
    if G is None or len(G.nodes) == 0:
        return {"noeuds_orphelins": [], "troncons_orphelins": [],
                "stats": {"noeuds_total": 0, "aretes_total": 0}}

    # --- Projection graphe (métrique) -> WGS84 ---
    crs_src = G.graph.get('crs') or "EPSG:32631"
    try:
        transformer = pyproj.Transformer.from_crs(crs_src, "EPSG:4326", always_xy=True)
    except Exception:
        transformer = None

    def _vers_wgs(x, y):
        if x is None or y is None or transformer is None:
            return None, None
        try:
            lon, lat = transformer.transform(float(x), float(y))
            if not (math.isfinite(lon) and math.isfinite(lat)):
                return None, None
            return round(lat, 6), round(lon, 6)
        except Exception:
            return None, None

    def _txt(v):
        """Chaîne sûre JSON : None pour NaN/None/vide."""
        if v is None:
            return None
        try:
            if isinstance(v, float) and not math.isfinite(v):
                return None
            s = str(v).strip()
        except Exception:
            return None
        if not s or s.lower() in ('nan', 'none', 'null'):
            return None
        return s

    def _num(v):
        try:
            f = float(v)
            return f if math.isfinite(f) else None
        except (TypeError, ValueError):
            return None

    # --- 1. Nœuds orphelins : déclarés mais aucun tronçon ne s'y rattache ---
    noeuds_orphelins = []
    nb_sans_geometrie = 0
    for noeud, data in G.nodes(data=True):
        if G.degree(noeud) != 0:
            continue
        x, y = data.get('x'), data.get('y')
        lat, lon = _vers_wgs(x, y)
        if lat is None:
            nb_sans_geometrie += 1
            continue
        noeuds_orphelins.append({
            "id": str(noeud),
            "type_noeud": _txt(data.get('type')) or 'noeud',
            "nom": _txt(data.get('nom')),
            "nom_voie": _txt(data.get('nom_voie')),
            "commune": _txt(data.get('commune')),
            "type_ouvrage": _txt(data.get('type_ouvrage')),
            "lat": lat,
            "lng": lon,
        })
    noeuds_orphelins.sort(key=lambda n: (n["type_noeud"], n["id"]))

    # --- 2. Tronçons orphelins ---
    troncons_orphelins = []

    # 2a. Conduites exclues du graphe (extrémités non résolues)
    for c in G.graph.get('conduits_non_graphes', []) or []:
        lat, lon = _vers_wgs(c.get('x'), c.get('y'))
        manquantes = c.get('extremites_manquantes') or []
        detail = "Extrémité(s) non résolue(s) : " + ", ".join(manquantes) if manquantes else "Extrémités non résolues"
        cid = str(c.get('cle') or '')
        if cid.lower() in ('', 'none', 'nan'):
            cid = f"ligne_{c.get('index_ligne')}"
        troncons_orphelins.append({
            "id": cid,
            "amont": _txt(c.get('amont_brut')) or _txt(c.get('amont_resolu')),
            "aval": _txt(c.get('aval_brut')) or _txt(c.get('aval_resolu')),
            "type_conduite": _txt(c.get('type_conduite')),
            "longueur_m": _num(c.get('longueur_m')),
            "diametre_mm": _num(c.get('diametre_mm')),
            "motif": "hors_graphe",
            "detail": detail,
            "lat": lat,
            "lng": lon,
        })

    # 2b. Arêtes des composantes connexes sans exutoire (exutoires implicites
    #     inclus : un fragment qui se termine sur un nœud mort est un bassin
    #     valide à vérifier, pas un orphelin).
    try:
        exutoires_map = trouver_exutoires_physiques(G, inclure_exutoires_implicites=True)
        ids_exutoire = set(exutoires_map.keys())
        composantes_orphelines = set()
        for comp in nx.weakly_connected_components(G):
            if not any(n in ids_exutoire for n in comp):
                composantes_orphelines.update(comp)
        nb_composantes = len([c for c in nx.weakly_connected_components(G)
                              if not any(n in ids_exutoire for n in c)])
    except Exception:
        composantes_orphelines = set()
        nb_composantes = 0

    nb_aretes_orphelines = 0
    for u, v, d in G.edges(data=True):
        if u not in composantes_orphelines or v not in composantes_orphelines:
            continue
        nb_aretes_orphelines += 1
        geom = d.get('geometry')
        cx = cy = None
        try:
            if geom is not None and not geom.is_empty:
                c = geom.centroid
                cx, cy = float(c.x), float(c.y)
        except Exception:
            pass
        lat, lon = _vers_wgs(cx, cy)
        if lat is None:
            continue
        eid = d.get('id') or d.get('key')
        eid = str(eid) if eid is not None else ''
        if eid.lower() in ('', 'none', 'nan'):
            eid = f"{u}->{v}"
        troncons_orphelins.append({
            "id": eid,
            "amont": str(u),
            "aval": str(v),
            "type_conduite": _txt(d.get('type')),
            "longueur_m": _num(d.get('length')),
            "diametre_mm": _num(d.get('diametre_mm')),
            "motif": "composante_sans_exutoire",
            "detail": "Sous-réseau isolé : aucune issue vers un exutoire",
            "lat": lat,
            "lng": lon,
        })

    troncons_orphelins.sort(key=lambda t: (t["motif"], str(t["id"])))

    return {
        "noeuds_orphelins": noeuds_orphelins,
        "troncons_orphelins": troncons_orphelins,
        "stats": {
            "noeuds_total": int(G.number_of_nodes()),
            "aretes_total": int(G.number_of_edges()),
            "noeuds_orphelins": len(noeuds_orphelins),
            "noeuds_orphelins_sans_geometrie": nb_sans_geometrie,
            "troncons_orphelins": len(troncons_orphelins),
            "aretes_orphelines_composante": nb_aretes_orphelines,
            "composantes_sans_exutoire": nb_composantes,
        },
    }


@router.get("/export/inp")
def export_network_inp(
    ctx: TenantContext = Depends(require_role("viewer")),
    db: Session = Depends(get_db)
):
    """Exporte l'intégralité du réseau actif au format standard EPA SWMM 5.2 (.inp) avec le nom du réseau."""
    from fastapi.responses import PlainTextResponse
    import re
    import unicodedata
    from src.domain.moteur_swmm import MoteurSWMM
    from api.services.simulation_service import resoudre_gpkg_effectif_pour_projet

    project = db.query(Project).filter(
        Project.org_id == ctx.org_id,
        Project.is_archived.is_(False)
    ).first()
    if not project:
        raise HTTPException(status_code=404, detail="Ressource introuvable")

    gpkg_path = resoudre_gpkg_effectif_pour_projet(db, project)
    if not gpkg_path or not gpkg_path.exists():
        raise HTTPException(status_code=404, detail="Ressource introuvable")

    project_name = project.name

    # 1. Si le fichier .inp original existe à côté du GPKG, le renvoyer directement (100% fidèle et instantané)
    original_inp = gpkg_path.with_suffix(".inp")
    if original_inp.exists():
        with open(original_inp, "r", encoding="utf-8", errors="ignore") as f:
            inp_content = f.read()
    else:
        # 3D.2 — plus de lecture de _DERNIERE_SIMULATION (état global non
        # cloisonné) : le modèle est assemblé depuis le GPKG du projet.
        moteur = MoteurSWMM()
        inp_content, _ = moteur.assembler_modele_inp(
            gpkg_path=gpkg_path,
            cluster_id=None,
            pente_moyenne_pct=1.0
        )
        try:
            with open(original_inp, "w", encoding="utf-8") as f:
                f.write(inp_content)
        except Exception:
            pass

    nom_reseau = project_name or gpkg_path.stem
    r = re.sub(r'\.(gpkg|inp)$', '', str(nom_reseau).strip(), flags=re.I)
    sans_accent = unicodedata.normalize('NFKD', r).encode('ASCII', 'ignore').decode('utf-8')
    clean = re.sub(r'[^\w\-_.]+', '_', sans_accent)
    clean = re.sub(r'_+', '_', clean).strip('_') or "reseau_swmm"
    filename = f"{clean}.inp"

    return PlainTextResponse(
        inp_content,
        media_type="text/plain; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )
