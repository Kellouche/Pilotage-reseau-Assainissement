"""
================================================================================
Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
Auteur : Dr Abdelhakim KELLOUCHE
Date de création : 2026-11-24
Date de modification : 2026-11-27
Objet : Endpoint GET /simulations/profil-en-long — profil en long hydraulique
        HGL (Phase 6.A), extrait de api/routes/simulations.py (découpage 600 lignes)
================================================================================
"""

import logging
import math
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from api.database import get_db
from api.core.security import get_tenant_context, TenantContext
# Helpers d'autorisation mutualisés avec le routeur principal.
from api.routes.simulations import _gpkg_demo_autorise, _org_id_requete
# Topo GPKG mutualisée (aussi utilisée par /recherche-element).
from api.services.profil_topo_service import _charger_topo_pour_profil
from api.services.simulation_service import (
    resoudre_gpkg_effectif_pour_projet as _resoudre_gpkg_effectif_pour_projet,
    est_simulation_valide as _est_simulation_valide,
    charger_derniere_simulation_disque_ou_db as _charger_derniere_simulation_disque_ou_db,
    ProjetAmbigu,
    ContexteSimulationIntrouvable,
)

from api.routes.simulations_profil_etapes import (
    _etape_coords_noeuds, _etape_segments_profil,
)
from api.routes.simulations_profil_etapes_suite import (
    _etape_alertes, _etape_anomalies_resume, _etape_defs_hydraulique,
    _etape_hgl_altimetrie, _etape_sim_data_hydraulique,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/simulations", tags=["Simulations — Profil en long"])


# ============================================================
# PROFIL EN LONG HYDRAULIQUE (Phase 6.A)
# ============================================================

def _terrain_aux_pour_profil(db, org_id: str, proj, topo: Dict[str, Any]):
    """
    P3 (SHP.md §7) — localise l'artefact `regards_terrain` de la couche
    altimétrie satellite active pour ce projet.

    Retourne None si : pas de projet, pas de couche altimétrie OK, ou si
    l'artefact est estampillé sur une AUTRE version du GPKG réseau
    (meta.gpkg_sha256 ≠ sha du GPKG du profil) — jamais de terrain
    interpolé servi pour un réseau périmé.
    """
    if proj is None or not (topo or {}).get("gpkg_sha"):
        return None
    try:
        from api.models import ProjectAuxLayer
        from api.services import aux_altimetrie_service as alt

        couches = (
            db.query(ProjectAuxLayer)
            .filter(
                ProjectAuxLayer.project_id == proj.id,
                ProjectAuxLayer.org_id == org_id,
                ProjectAuxLayer.type == "altimetrie_points",
                ProjectAuxLayer.statut == "ok",
            )
            .order_by(ProjectAuxLayer.created_at.desc())
            .limit(3)
            .all()
        )
        for c in couches:
            art = alt.charger_regards_terrain(org_id, proj.id, c.id)
            if not art:
                continue
            meta = art.get("meta") or {}
            if meta.get("gpkg_sha256") != topo["gpkg_sha"]:
                logger.info(
                    "Profil : artefact regards_terrain de la couche %s périmé "
                    "(sha %s ≠ GPKG %s) — ignoré.",
                    c.id, str(meta.get("gpkg_sha256"))[:12], topo["gpkg_sha"][:12],
                )
                continue
            return {"layer": c, "artefact": art, "meta": meta}
    except Exception as e:
        logger.warning("Profil : recherche terrain satellite impossible : %s", e)
    return None


@router.get("/profil-en-long")
def get_profil_en_long(
    node_amont: str,
    node_aval: str,
    base: str = "max",
    instant_minute: Optional[int] = None,
    forcer_brut: bool = False,
    db: Session = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant_context),
):
    """
    Calcule et retourne le profil en long hydraulique entre deux regards.
    Chemin topologique amont→aval avec cotes géométriques (radiers, terrain naturel,
    génératrices supérieures) et ligne de charge HGL.

    LOT P0.2 — la HGL provient EXCLUSIVEMENT des cotes hydrauliques réelles
    extraites du fichier .out SWMM (HYDRAULIC_HEAD / INVERT_DEPTH /
    FLOODING_LOSSES) et persistées dans la simulation (`timeseries.
    node_hydraulics`) :
      - base="max" (défaut) : enveloppe des cotes maximales atteintes ;
      - base="instant" + instant_minute : cote à l'instant demandé ;
      - sans données .out (simulation historique) : z_hgl=None et
        hgl_source="indisponible" — aucune valeur estimée n'est présentée
        comme un résultat SWMM.
    """
    if base not in ("max", "instant"):
        raise HTTPException(status_code=422, detail="base doit être 'max' ou 'instant'.")
    if base == "instant" and instant_minute is None:
        raise HTTPException(status_code=422, detail="instant_minute requis avec base='instant'.")

    # 3D.3 — le profil est tracé sur le GPKG DE LA SIMULATION autorisée du
    # contexte (org/projet), jamais sur le fichier mutable ni la globale.
    from api.services.gpkg_versions import (
        resoudre_gpkg_pour_simulation,
        GpkgSimulationError,
    )
    from api.services.simulation_service import (
        resoudre_simulation_courante,
        _resoudre_projet_pour_simulation,
    )

    org_id = _org_id_requete(tenant)

    # Projet résolu de façon non ambiguë + GPKG courant (fallback lecture seule)
    proj = None
    try:
        proj = _resoudre_projet_pour_simulation(db, org_id, None)
    except ProjetAmbigu as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ContexteSimulationIntrouvable:
        proj = None
    gpkg_effectif = _resoudre_gpkg_effectif_pour_projet(db, proj)
    if gpkg_effectif is None:
        gpkg_effectif = _gpkg_demo_autorise()

    # Simulation autorisée du contexte : données HGL + snapshot GPKG exact
    sim_data: Dict[str, Any] = {}
    active_gpkg = None
    ctx = None
    try:
        ctx = resoudre_simulation_courante(db, org_id=org_id, resoudre_gpkg=True)
    except ProjetAmbigu as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ContexteSimulationIntrouvable:
        ctx = None
    except GpkgSimulationError as e:
        raise HTTPException(status_code=409, detail=str(e))

    if ctx is not None:
        sim_data = ctx.data or {}
        # Option A — topologie = LE SNAPSHOT GPKG qui a produit la simulation
        # (ctx.gpkg_path, résolu par resoudre_gpkg_pour_simulation avec
        # vérification SHA-256). La HGL et la géométrie décrivent alors le
        # MÊME réseau par construction : fini la jointure « code de regard
        # censé stable entre versions » qui produisait des profils hybrids
        # silencieusement faux. Un profil reste traçable sur tout nœud du
        # snapshot ; les nœuds hors emprise de la sim restent en lecture
        # topographique seule.
        # Repli gpkg_effectif UNIQUEMENT si la provenance de la sim est
        # irrésoluble (simulation legacy sans empreinte) — cas dégradé
        # documenté, jamais pour une sim à provenance vérifiable.
        active_gpkg = ctx.gpkg_path if (ctx.gpkg_path and ctx.gpkg_path.exists()) else (
            gpkg_effectif if (gpkg_effectif and gpkg_effectif.exists()) else None)
    elif proj is not None and gpkg_effectif and gpkg_effectif.exists():
        # Repli legacy : simulation sans ligne DB (ancien cache disque) —
        # uniquement si le projet est vérifiable (3D.6).
        try:
            restored = _charger_derniere_simulation_disque_ou_db(gpkg_effectif, db, proj)
            if restored and _est_simulation_valide(restored):
                gpkg_rest, _vmeta = resoudre_gpkg_pour_simulation(db, proj, restored)
                sim_data = restored
                active_gpkg = gpkg_rest if (gpkg_rest and gpkg_rest.exists()) else gpkg_effectif
        except GpkgSimulationError as e:
            logger.warning("Simulation legacy disque non résoluble: %s", e)
            sim_data = {}
            active_gpkg = gpkg_effectif
        except Exception as e_rest:
            logger.warning("Échec restauration simulation pour profil en long: %s", e_rest)

    # Sans simulation autorisée : lecture seule du réseau courant du projet
    if active_gpkg is None:
        active_gpkg = gpkg_effectif

    if not active_gpkg or not active_gpkg.exists():
        raise HTTPException(status_code=404, detail="Aucun réseau actif chargé.")

    try:
        import geopandas as gpd
        import pandas as pd
        from src.domain.moteur_swmm.constants import _clean_node_id

        import networkx as nx

        # Topologie + index regards : servis par le cache mémoire
        # (_charger_topo_pour_profil) — ~10 s de construction une seule fois
        # par version de GPKG au lieu de chaque appel.
        _topo = _charger_topo_pour_profil(active_gpkg)
        node_index = _topo["node_index"]
        canalisations = _topo["canalisations"]
        G = _topo["G"]

        # P3 (SHP.md §7) — terrain interpolé satellite (couche altimétrie
        # IDW) : sert UNIQUEMENT à l'affichage du profil (z_terrain_interp).
        # Jamais injecté dans z_terrain : la classification hydraulique
        # (inondation/revanche/atteint_terrain) reste réservée aux cotes
        # altimétriques vérifiées du GPKG.
        terrain_aux = _terrain_aux_pour_profil(db, org_id, proj, _topo)
        terrain_par_code = ((terrain_aux or {}).get("artefact") or {}).get("regards") or {}

        if len(G.edges) == 0:
            for idx, c in canalisations.iterrows():
                u = _clean_node_id(c.get("ID_AMONT"))
                v = _clean_node_id(c.get("ID_AVAL"))
                if u and v and u != v:
                    length = float(c["Longeur"]) if ("Longeur" in c and c["Longeur"] > 0) else float(c.geometry.length)
                    diam_mm = float(c["DIAMETRE"]) if ("DIAMETRE" in c and c["DIAMETRE"] > 0) else 600.0
                    cid = f"C_{idx+1}"
                    G.add_edge(u, v, cid=cid, length=length, diam_mm=diam_mm,
                               materiau=str(c.get("MATERIAU", "Béton") or "Béton"),
                               nom_voie=str(c.get("NOM-VOIE", "") or ""))

        # Chercher le nœud dans le réseau
        def find_node(partial: str) -> Optional[str]:
            p_str = str(partial).strip()
            p_clean = _clean_node_id(p_str)
            if p_clean in G.nodes:
                return p_clean
            if p_str in G.nodes:
                return p_str
            for n in G.nodes:
                if p_clean == _clean_node_id(n) or p_str.lower() == str(n).lower():
                    return n
            if len(p_str) >= 3:
                for n in G.nodes:
                    if p_str.lower() in str(n).lower():
                        return n
            return None

        src = find_node(node_amont)
        dst = find_node(node_aval)

        if not src:
            raise HTTPException(status_code=404, detail=f"Regard amont '{node_amont}' introuvable dans le réseau.")
        if not dst:
            raise HTTPException(status_code=404, detail=f"Regard aval '{node_aval}' introuvable dans le réseau.")

        # Trouver le plus court chemin
        try:
            path_nodes = nx.shortest_path(G, src, dst, weight="length")
        except nx.NetworkXNoPath:
            # Essai inverse : si l'utilisateur a sélectionné l'aval avant l'amont
            try:
                path_nodes = nx.shortest_path(G, dst, src, weight="length")
                # Rétablir le sens naturel amont -> aval
                path_nodes = path_nodes[::-1]
                src, dst = dst, src
            except nx.NetworkXNoPath:
                # Tentative en non orienté si des conduites sont numérisées à contre-sens
                try:
                    G_undir = G.to_undirected()
                    path_nodes = nx.shortest_path(G_undir, src, dst, weight="length")
                    # Réaligner le chemin pour qu'il commence toujours par l'amont (src)
                    if path_nodes and path_nodes[0] != src:
                        path_nodes = path_nodes[::-1]
                except nx.NetworkXNoPath:
                    raise HTTPException(
                        status_code=422,
                        detail=f"Aucun chemin hydraulique entre '{node_amont}' et '{node_aval}'. "
                               "Vérifiez que les deux regards appartiennent au même réseau connecté."
                    )

        # Règle de Rigour Hydraulicienne (Human-in-the-Loop) :
        # Contrôle des cotes nodales suspectes sur le chemin demandé.
        # Tout regard ayant une profondeur aberrante non certifiée suspend le tracé
        # jusqu'à validation ou confirmation explicite de l'utilisateur.
        from api.services.cotes_suspectes_service import (
            synchroniser_cotes_suspectes_projet,
            obtenir_map_validations_projet,
            SEUIL_PROFONDEUR_MAX_M,
            suggerer_correction_profondeur,
        )
        validations_map = {}
        if proj is not None:
            try:
                synchroniser_cotes_suspectes_projet(db, proj)
                validations_map = obtenir_map_validations_projet(db, proj.id, org_id)
            except Exception as e_cs:
                logger.warning("Erreur synchronisation cotes suspectes: %s", e_cs)

        cotes_suspectes_bloquantes = []
        for nid in path_nodes:
            info = node_index.get(nid, {})
            prof = info.get("profondeur")
            val_entry = (validations_map.get(str(nid), {}).get("profondeur") or
                         validations_map.get(_clean_node_id(nid), {}).get("profondeur"))
            if prof is not None and prof > SEUIL_PROFONDEUR_MAX_M:
                if not val_entry or val_entry.get("statut") == "a_valider":
                    sugg = suggerer_correction_profondeur(prof)
                    cotes_suspectes_bloquantes.append({
                        "node_id": str(nid),
                        "champ": "profondeur",
                        "valeur_brute": float(prof),
                        "valeur_suggeree": float(sugg) if sugg is not None else None,
                        "motif_suspicion": (
                            f"Profondeur excessive ({prof:.1f} m > {SEUIL_PROFONDEUR_MAX_M:.0f} m) — "
                            f"confusion d'unité probable ({sugg:.2f} m suggéré)"
                        ),
                        "statut": "a_valider",
                    })

        if cotes_suspectes_bloquantes and not forcer_brut:
            return {
                "status": "cotes_suspectes_a_valider",
                "message": (
                    f"Le profil hydraulique entre '{node_amont}' et '{node_aval}' traverse "
                    f"{len(cotes_suspectes_bloquantes)} regard(s) aux cotes non validées. "
                    "Conformément aux règles d'ingénierie hydraulique, veuillez valider "
                    "ou corriger ces valeurs avant l'élaboration du tracé."
                ),
                "node_amont": src,
                "node_aval": dst,
                "cotes_suspectes": cotes_suspectes_bloquantes,
            }

        # Couverture du chemin : la « dernière » simulation completed peut
        # être un cluster sectorisé qui ne couvre pas le chemin demandé
        # (ses cotes nodales node_hydraulics/node_elevs sont limitées aux
        # nœuds simulés). On retient alors la plus récente simulation
        # autorisée du même projet/org dont les cotes interceptent le
        # chemin — jamais de substitution inter-tenant.
        def _sim_couvre_chemin(d: Dict[str, Any]) -> int:
            """Nombre de nœuds du chemin couverts par les cotes d'une simulation."""
            if not d or not _est_simulation_valide(d):
                return 0
            _ts = d.get("timeseries") or {}
            _nh = _ts.get("node_hydraulics") or d.get("node_hydraulics") or {}
            _ev = (d.get("meta") or {}).get("node_elevs") or {}
            _cles = set()
            for _k in list(_nh.keys()) + [str(_k) for _k in _ev.keys()]:
                _cles.add(str(_k))
                _cn = _clean_node_id(_k)
                if _cn:
                    _cles.add(_cn)
            return sum(
                1 for _n in path_nodes
                if str(_n) in _cles or (_clean_node_id(_n) or "") in _cles)

        if proj is not None and _sim_couvre_chemin(sim_data) == 0:
            try:
                from api.models import Simulation
                from api.services.simulation_service import (
                    charger_resultat_simulation,
                    _ref_pour_simulation,
                )
                _id_deja = (ctx.simulation.id
                            if (ctx is not None and ctx.simulation is not None)
                            else None)
                _q = db.query(Simulation).filter(
                    Simulation.project_id == proj.id,
                    Simulation.status == "completed")
                if org_id:
                    _q = _q.filter(Simulation.org_id == org_id)
                _meilleure = None
                _meilleure_couv = 0
                for _sim in _q.order_by(
                        Simulation.created_at.desc(),
                        Simulation.id.desc()).limit(150).all():
                    try:
                        if _id_deja is not None and _sim.id == _id_deja:
                            continue
                        if not _sim.results_s3_key and _ref_pour_simulation(_sim) is None:
                            continue
                        _d = charger_resultat_simulation(_sim)
                        if not _d or not _est_simulation_valide(_d):
                            continue
                        _c = _sim_couvre_chemin(_d)
                        if _c > _meilleure_couv:
                            _meilleure_couv = _c
                            _meilleure = _d
                            if _c >= len(path_nodes):
                                break
                    except Exception as e_sim:
                        logger.debug("Simulation %s illisible pour couverture: %s",
                                     getattr(_sim, "id", "?"), e_sim)
                        continue
                if _meilleure is not None:
                    logger.info(
                        "Profil en long : simulation « dernière » sans couverture "
                        "du chemin → repli sur une simulation autorisée "
                        "couvrant %s/%s nœuds.",
                        _meilleure_couv, len(path_nodes))
                    sim_data = _meilleure
            except Exception as e_cov:
                logger.warning("Recherche simulation couvrante impossible: %s", e_cov)

        # Récupérer les élévations nodales depuis la simulation ou le MNT
        node_elevs: Dict[str, float] = {}
        sim_node_results: Dict[str, Any] = {}
        sim_meta: Dict[str, Any] = {}
        # LOT P0.2 — cotes hydrauliques RÉELLES (.out SWMM) persistées dans
        # timeseries.node_hydraulics ; absentes pour les simulations
        # historiques → HGL signalée indisponible, jamais estimée.
        node_hydraulics: Dict[str, Any] = {}
        sim_valide = bool(sim_data and _est_simulation_valide(sim_data))
        node_hydraulics, sim_meta, sim_node_results = _etape_sim_data_hydraulique({
            "_clean_node_id": _clean_node_id,
            "node_elevs": node_elevs,
            "node_hydraulics": node_hydraulics,
            "sim_data": sim_data,
            "sim_meta": sim_meta,
            "sim_node_results": sim_node_results,
            "sim_valide": sim_valide,
        })

        _hydrau_noeud, _head_reel, _flood_reel = _etape_defs_hydraulique({
            "_clean_node_id": _clean_node_id,
            "base": base,
            "instant_minute": instant_minute,
            "node_hydraulics": node_hydraulics,
        })

        segments, distance_cumulee, hgl_source, inp_noeuds, _noeud_wgs = _etape_coords_noeuds({
        "_topo": _topo,
        "base": base,
        "node_hydraulics": node_hydraulics,
        "node_index": node_index,
        "path_nodes": path_nodes,
        "sim_data": sim_data,
        "sim_valide": sim_valide,
    })

        distance_cumulee = _etape_segments_profil({
        "distance_cumulee": distance_cumulee,
        "G": G,
        "_clean_node_id": _clean_node_id,
        "_flood_reel": _flood_reel,
        "_head_reel": _head_reel,
        "_hydrau_noeud": _hydrau_noeud,
        "_noeud_wgs": _noeud_wgs,
        "base": base,
        "inp_noeuds": inp_noeuds,
        "node_elevs": node_elevs,
        "node_index": node_index,
        "path_nodes": path_nodes,
        "segments": segments,
        "sim_data": sim_data,
        "sim_node_results": sim_node_results,
        "terrain_par_code": terrain_par_code,
        "validations_map": validations_map,
    })

        # Ajouter le dernier nœud (aval) sans conduit sortant
        # (il est déjà ajouté dans la boucle)

        # ------------------------------------------------------------------
        # Jalons d'anomalies — audit visuel du profil en long.
        # Chaque anomalie est accrochée au nœud AVAL du tronçon concerné
        # (segment[i] porte la conduite sortante vers segment[i+1]) et
        # listée dans `anomalies` avec un résumé `resume_anomalies`.
        # Seuils documentés (valeurs indicatives d'ingénierie, affichées
        # dans les messages — pas des seuils arbitraires cachés) :
        #   - vitesse max SWMM ≥ 4 m/s  → fort (érosion / mise en charge)
        #   - vitesse max SWMM ≥ 3 m/s  → moyen
        #   - vitesse max < 0,6 m/s avec écoulement → faible (autocurage
        #     insuffisant → risque de dépôt)
        #   - radier aval > radier amont de plus de 2 cm → contre-pente
        #   - pente radier > 8 % → forte pente (à recouper avec la vitesse)
        #   - terrain interpolé qui remonte de plus de 0,5 m → info
        #     (bruit IDW probable — jamais une anomalie hydraulique)
        # ------------------------------------------------------------------
        for _s in segments:
            _s["anomalies"] = []
        anomalies_liste = []
        _n_liens_radier = 0
        _n_contre_pentes = 0

        def _jalon(cible, type_, severite, message, **kw):
            a = {"type": type_, "severite": severite, "message": message, **kw}
            cible["anomalies"].append(a)
            anomalies_liste.append({
                "node_id": cible["node_id"],
                "distance_m": cible["distance_m"],
                **a,
            })

        resume_anomalies, conduites_en_charge, longueur_totale, z_min, z_max, alerts = _etape_anomalies_resume({
        "_jalon": _jalon,
        "anomalies_liste": anomalies_liste,
        "distance_cumulee": distance_cumulee,
        "segments": segments,
            "_n_liens_radier": _n_liens_radier,
        "_n_contre_pentes": _n_contre_pentes,
    })
        _etape_alertes({
        "alerts": alerts,
        "base": base,
        "segments": segments,
    })

        _altimetrie_info, _gf_prof, _synthese_anomalies, hgl_source_global = _etape_hgl_altimetrie({
        "alerts": alerts,
        "base": base,
        "cotes_suspectes_bloquantes": cotes_suspectes_bloquantes,
        "forcer_brut": forcer_brut,
        "hgl_source": hgl_source,
        "segments": segments,
        "sim_data": sim_data,
    })

        return {
            "status": "success",
            "altimetrie": _altimetrie_info,
            "synthese_anomalies": _synthese_anomalies,
            "node_amont": src,
            "node_aval": dst,
            "fiabilite_modele": _gf_prof.get("fiabilite_modele"),
            "modelisation_anomalies": _gf_prof.get("anomalies") or [],
            "longueur_totale_m": round(longueur_totale, 2),
            "nb_troncons": len(path_nodes) - 1,
            "z_min": round(z_min, 3),
            "z_max": round(z_max, 3),
            "conduites_en_charge": conduites_en_charge,
            "simulation_active": bool(sim_valide),
            "terrain_disponible": any(s.get("z_terrain") is not None for s in segments),
            "terrain_interpole": ({
                "disponible": True,
                "source": "topo_idw",
                "layer_id": terrain_aux["layer"].id,
                "layer_nom": terrain_aux["layer"].nom,
                "resolution_m": (terrain_aux.get("meta") or {}).get("resolution_m"),
                "nb_regards_couverts": sum(
                    1 for s in segments if s.get("z_terrain_interp") is not None),
                "nb_regards": len(segments),
                "avertissement": "Terrain interpolé (IDW sur points cotés) — "
                                 "cote du terrain, pas le fond de regard.",
            } if terrain_aux else {"disponible": False}),
            "hgl_source": hgl_source_global,
            "hgl_base": base,
            "hgl_base_label": (
                "enveloppe des cotes maximales individuelles — les maxima "
                "proviennent du rapport SWMM (.rpt, pas de routage) quand "
                "disponible, sinon des instants de rapport du .out ; les "
                "maxima des differents regards peuvent survenir a des "
                "instants differents ; la classification porte sur ces "
                "memes maxima, pas sur un instant unique" if base == "max"
                else "profil instantane a l'instant demande — cote, "
                     "debordement et classification au meme pas de temps ; "
                     "les evenements de debordement detectes a d'autres "
                     "instants sont signales separement"),
            "instant_minute": instant_minute,
            "anomalies": anomalies_liste,
            "resume_anomalies": resume_anomalies,
            "segments": segments,
            "alertes": alerts,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Erreur calcul profil en long: %s", e)
        raise HTTPException(status_code=500, detail=f"Erreur calcul profil en long : {e}")
