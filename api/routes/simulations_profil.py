"""
================================================================================
Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
Auteur : Dr Abdelhakim KELLOUCHE
Date de création : 2026-11-24
Date de modification : 2026-11-24
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
        if sim_valide:
            sim_node_results = sim_data.get("node_results", {})
            sim_meta = sim_data.get("meta", {})
            ts_data = sim_data.get("timeseries") or {}
            node_hydraulics = ts_data.get("node_hydraulics") or sim_data.get("node_hydraulics") or {}
            # Élévations depuis le meta de la simulation (node_elevs injecté dans meta)
            meta_node_elevs = sim_meta.get("node_elevs", {})
            if meta_node_elevs:
                node_elevs.update(meta_node_elevs)
            # Cotes d'invert réellement utilisées par SWMM (section .inp)
            for nh_nid, nh in node_hydraulics.items():
                inv = nh.get("invert_m")
                if inv is not None:
                    node_elevs.setdefault(str(nh_nid), float(inv))

            # P0 — enrichissement à la volée pour les simulations persistées
            # AVANT le lot P0 : node_hydraulics sans champs rpt_*, mais le
            # .rpt et node_results sont conservés dans le résultat → les
            # maxima au pas de routage et le débordement réel restent
            # accessibles sans relancer SWMM. Lecture seule, jamais
            # d'estimation : section .rpt absente → champs simplement absents.
            try:
                _besoin_rpt = any(
                    isinstance(_nh, dict) and _nh.get("rpt_max_head_m") is None
                    for _nh in node_hydraulics.values()
                )
                if _besoin_rpt and sim_data.get("rpt_content"):
                    from src.domain.moteur_swmm.analyse_rapport import (
                        extraire_maxima_noeuds_rpt,
                    )
                    _maxima_rpt = extraire_maxima_noeuds_rpt(sim_data["rpt_content"])
                    for _mnid, _mm in (_maxima_rpt or {}).items():
                        _ent = node_hydraulics.get(_mnid)
                        if isinstance(_ent, dict) and _ent.get("rpt_max_head_m") is None:
                            _ent["rpt_max_head_m"] = _mm.get("max_hgl_m")
                            _ent["rpt_max_head_minute"] = _mm.get("max_time_minute")
                            _ent["rpt_max_depth_m"] = _mm.get("max_depth_m")
                            _ent["rpt_reported_max_depth_m"] = _mm.get("reported_max_depth_m")
                            _ent["hgl_max_source"] = "rpt_node_depth_summary"
                # Synthèses .rpt complètes (Node Flooding Summary) : volume
                # brut SWMM et instant du pic — source d'autorité, prioritaire
                # sur node_results persisté (qui peut contenir l'ancienne
                # estimation de volume).
                if sim_data.get("rpt_content"):
                    try:
                        from src.domain.moteur_swmm.analyse_rapport import (
                            analyser_rapport_swmm_impl,
                        )
                        _kpis_rpt = analyser_rapport_swmm_impl(
                            rpt_text=sim_data["rpt_content"], meta={})
                        for _mnid, _nr in (_kpis_rpt.get("node_results") or {}).items():
                            if not isinstance(_nr, dict):
                                continue
                            if float(_nr.get("hours_flooded") or 0.0) <= 0.0 and _nr.get("status") != "flooded":
                                continue
                            _ent = node_hydraulics.get(_mnid)
                            if _ent is None:
                                _ent = node_hydraulics.get(_clean_node_id(_mnid))
                            if isinstance(_ent, dict) and _ent.get("rpt_flood_max_m3s") is None:
                                _ent["rpt_flood_max_m3s"] = _nr.get("peak_flood_flow_cms")
                                _ent["rpt_flood_minute"] = _nr.get("flood_time_minute")
                                _ent["rpt_flood_volume_m3"] = _nr.get("flood_volume_m3")
                                _ent["flood_volume_estime"] = bool(_nr.get("flood_volume_estime", True))
                                _ent["flooding_source"] = "rpt_node_flooding_summary"
                    except Exception as e_flood:
                        logger.warning("Synthèse flooding .rpt illisible: %s", e_flood)
                # Repli : node_results persisté (volume possiblement estimé
                # par une version antérieure → marqué non fiable).
                for _mnid, _nr in sim_node_results.items():
                    if not isinstance(_nr, dict):
                        continue
                    if float(_nr.get("hours_flooded") or 0.0) <= 0.0 and _nr.get("status") != "flooded":
                        continue
                    _ent = node_hydraulics.get(_mnid)
                    if _ent is None:
                        _nc = _clean_node_id(_mnid)
                        _ent = node_hydraulics.get(_nc)
                    if isinstance(_ent, dict) and _ent.get("rpt_flood_max_m3s") is None:
                        _ent["rpt_flood_max_m3s"] = _nr.get("peak_flood_flow_cms")
                        _ent["rpt_flood_minute"] = _nr.get("flood_time_minute")
                        _ent["rpt_flood_volume_m3"] = _nr.get("flood_volume_m3")
                        _ent["flood_volume_estime"] = bool(_nr.get("flood_volume_estime", True))
                        _ent["flooding_source"] = "rpt_node_flooding_summary"
            except Exception as e_lazy:
                logger.warning("Enrichissement .rpt à la volée impossible: %s", e_lazy)

        def _hydrau_noeud(nid: str) -> Optional[Dict[str, Any]]:
            """Entrée node_hydraulics pour un nœud du graphe (clés = noms .out/INP)."""
            if nid in node_hydraulics:
                return node_hydraulics[nid]
            nc = _clean_node_id(nid)
            if nc in node_hydraulics:
                return node_hydraulics[nc]
            for k, v in node_hydraulics.items():
                if _clean_node_id(k) == nc:
                    return v
            return None

        def _head_reel(nid: str):
            """(cote, source) — base='max' privilégie le maximum .rpt
            (pas de routage, source d'autorité) ; base='instant' utilise
            le .out à l'instant demandé. (None, 'indisponible') sinon."""
            nh = _hydrau_noeud(nid)
            if not nh:
                return None, "indisponible"
            if base == "instant":
                pairs = nh.get("heads") or []
                if not pairs:
                    v = nh.get("max_head_m")
                    return (float(v), "swmm_out_max_head") if v is not None else (None, "indisponible")
                best = min(pairs, key=lambda p: abs(p[0] - (instant_minute or 0)))
                return float(best[1]), "swmm_out_instant"
            rpt_h = nh.get("rpt_max_head_m")
            if rpt_h is not None:
                return float(rpt_h), "rpt_max_head"
            v = nh.get("max_head_m")
            return (float(v), "swmm_out_max_head") if v is not None else (None, "indisponible")

        def _flood_reel(nid: str):
            """(débit, source) au même référentiel temporel que la cote.
            base='max' : maximum .rpt (Node Flooding Summary) prioritaire ;
            base='instant' : débordement au pas échantillonné le plus proche,
            jamais le maximum global."""
            nh = _hydrau_noeud(nid)
            if not nh:
                return 0.0, "indisponible"
            if base == "instant":
                heads_pairs = nh.get("heads") or []
                if not heads_pairs:
                    return 0.0, "out_report_step"
                m_cible = min(heads_pairs,
                              key=lambda p: abs(p[0] - (instant_minute or 0)))[0]
                for m, v in (nh.get("floods") or []):
                    if m == m_cible:
                        return float(v), "swmm_out_instant"
                return 0.0, "swmm_out_instant"
            rpt_f = nh.get("rpt_flood_max_m3s")
            if rpt_f is not None:
                return float(rpt_f), "rpt_node_flooding_summary"
            return float(nh.get("flooding_max_m3s") or 0.0), "out_report_step"

        hgl_source = ("swmm_out_max_head" if (sim_valide and node_hydraulics and base == "max")
                      else "swmm_out_instant" if (sim_valide and node_hydraulics and base == "instant")
                      else "indisponible")

        # P0 — cotes de sommet de regard telles que définies par le modèle
        # SWMM ([JUNCTIONS] : Name Elevation MaxDepth InitDepth SurDepth
        # Aponded). Le sommet = radier + MaxDepth : ce n'est PAS le terrain
        # naturel, c'est le plan de rupture du modèle.
        inp_noeuds: Dict[str, Dict[str, float]] = {}
        inp_content = sim_data.get("inp_content") if sim_valide else None
        if inp_content:
            _sec = None
            for _line in str(inp_content).splitlines():
                _s = _line.strip()
                if _s.startswith("[") and _s.endswith("]"):
                    _sec = _s.strip("[]").lower()
                    continue
                if _sec in ("junctions", "outfalls", "storage") and _s and not _s.startswith(";"):
                    _p = _s.split()
                    if len(_p) >= 3:
                        try:
                            inp_noeuds[_p[0]] = {
                                "elevation": float(_p[1]),
                                "maxdepth": float(_p[2]),
                            }
                        except (TypeError, ValueError):
                            pass

        # Construire les séries du profil
        segments = []
        distance_cumulee = 0.0

        # Coordonnées WGS84 des nœuds du chemin (pour la couche d'anomalies
        # sur la carte) — même conversion que /recherche-element, limitée
        # aux nœuds du profil (pas les ~10k du réseau).
        _noeud_wgs = {}
        _crs_topo = _topo.get("crs")
        _tf_wgs = None
        if _crs_topo and "4326" not in str(_crs_topo):
            try:
                from pyproj import Transformer
                _tf_wgs = Transformer.from_crs(str(_crs_topo), "EPSG:4326", always_xy=True)
            except Exception:
                _tf_wgs = None
        for _nid in path_nodes:
            _info = node_index.get(_nid) or {}
            _x, _y = _info.get("x"), _info.get("y")
            if _x is None or _y is None:
                continue
            if _tf_wgs is not None:
                try:
                    _x, _y = _tf_wgs.transform(float(_x), float(_y))
                except Exception:
                    continue
            _noeud_wgs[_nid] = (_x, _y)

        for i, nid in enumerate(path_nodes):
            info = node_index.get(nid, {})
            profondeur = info.get("profondeur")
            cotrad = info.get("cotrad")
            cotetn = info.get("cotetn")  # cote terrain vérifiée (ou None)

            # Détermination de z_radier — sources réelles uniquement :
            # COTRAD (GPKG) → terrain vérifié − profondeur GPKG réelle →
            # radier .out SWMM (node_elevs). AUCUNE valeur heuristique.
            if cotrad is not None:
                z_rad = cotrad
            elif cotetn is not None and profondeur is not None:
                z_rad = cotetn - profondeur
            elif nid in node_elevs:
                z_rad = float(node_elevs[nid])
            else:
                nc = _clean_node_id(nid)
                z_rad = float(node_elevs.get(nc)) if nc in node_elevs else None
            if z_rad is not None and not math.isfinite(z_rad):
                z_rad = None

            # z_terrain : uniquement une cote altimétrique vérifiée.
            # Absente → None : aucune courbe « MNT » ne sera dessinée.
            z_terrain = cotetn
            terrain_reel = info.get("terrain_reel", False)
            terrain_source = info.get("terrain_source", "absent")

            # P3 — terrain interpolé satellite (affichage seul)
            z_terrain_interp = None
            terrain_confiance = None
            if terrain_par_code:
                _rk = (terrain_par_code.get(nid)
                       or terrain_par_code.get(_clean_node_id(nid) or "")
                       or terrain_par_code.get(str(nid)))
                if _rk and _rk.get("z_terrain_m") is not None:
                    z_terrain_interp = float(_rk["z_terrain_m"])
                    terrain_confiance = _rk.get("confiance")

            # Sommet de regard SWMM = radier + MaxDepth (.inp) — plan de
            # rupture du modèle, distinct du terrain naturel.
            # Règle Human-in-the-Loop : si l'hydraulicien a validé une profondeur certifiée,
            # celle-ci prévaut sur la valeur brute erronée.
            val_entry = (validations_map.get(str(nid), {}).get("profondeur") or
                         validations_map.get(_clean_node_id(nid), {}).get("profondeur"))
            prof_effectif = profondeur
            cote_est_validee = False
            if val_entry and val_entry.get("statut") == "valide" and val_entry.get("valeur_validee") is not None:
                prof_effectif = float(val_entry["valeur_validee"])
                cote_est_validee = True

            z_sommet = None
            inp_n = inp_noeuds.get(nid) or inp_noeuds.get(_clean_node_id(nid) or "")
            if prof_effectif is not None and z_rad is not None:
                z_sommet = z_rad + prof_effectif
            elif inp_n and inp_n.get("maxdepth") is not None:
                rad_src = z_rad if z_rad is not None else inp_n.get("elevation")
                if rad_src is not None:
                    z_sommet = rad_src + inp_n["maxdepth"]

            # Déterminer le diamètre de conduite local pour la génératrice supérieure
            diam_m = 0.6
            if i < len(path_nodes) - 1:
                next_n = path_nodes[i + 1]
                e = G.get_edge_data(nid, next_n) or G.get_edge_data(next_n, nid) or {}
                if e:
                    try:
                        _dm_f = float(e.get("diam_mm") or e.get("diametre_mm") or 600.0)
                    except (TypeError, ValueError):
                        _dm_f = 600.0
                    if not math.isfinite(_dm_f):
                        _dm_f = 600.0
                    diam_m = _dm_f / 1000.0
            elif i > 0:
                prev_n = path_nodes[i - 1]
                e = G.get_edge_data(prev_n, nid) or G.get_edge_data(nid, prev_n) or {}
                if e:
                    try:
                        _dm_f = float(e.get("diam_mm") or e.get("diametre_mm") or 600.0)
                    except (TypeError, ValueError):
                        _dm_f = 600.0
                    if not math.isfinite(_dm_f):
                        _dm_f = 600.0
                    diam_m = _dm_f / 1000.0

            z_gen_sup = (z_rad + diam_m) if z_rad is not None else None

            # LOT P0 — HGL : maximum .rpt (base=max) ou valeur .out à
            # l'instant demandé. Provenance conservée par nœud.
            hgl, hgl_src = _head_reel(nid)
            if hgl is not None and not math.isfinite(hgl):
                hgl, hgl_src = None, "indisponible"
            hgl_reel = hgl is not None
            nh_entry = _hydrau_noeud(nid) or {}
            simule = bool(nh_entry)
            flooding_max, flood_src = _flood_reel(nid)
            flooding_global_max = float(nh_entry.get("flooding_max_m3s") or 0.0)
            rpt_flood_vol = nh_entry.get("rpt_flood_volume_m3")
            rpt_flood_min = nh_entry.get("rpt_flood_minute")

            node_sim = sim_node_results.get(nid, {})
            status_n = node_sim.get("status", "normal")
            if hgl is not None:
                # CONTRÔLE P0 — distinction stricte :
                #   debordement = flooding RÉEL confirmé par SWMM
                #     (FLOODING_LOSSES > 0, .rpt prioritaire sur .out) ;
                #   inondation = cote ≥ terrain naturel VÉRIFIÉ sans débordement ;
                #   surcharge = mise en charge (cote > génératrice supérieure) ;
                #   libre = écoulement non mis en charge.
                # Sans terrain vérifié, aucune « inondation » ne peut être
                # affirmée : la comparaison se fait sur la génératrice.
                if flooding_max > 0.0:
                    hgl_regime = "debordement"
                elif z_terrain is not None and hgl >= z_terrain:
                    hgl_regime = "inondation"
                elif z_gen_sup is not None and hgl > z_gen_sup:
                    hgl_regime = "surcharge"
                else:
                    hgl_regime = "libre"
            else:
                # Donnée hydraulique absente : le statut RPT (donnée SWMM
                # réelle) qualifie le régime, mais aucune cote n'est inventée.
                if status_n == "flooded" and base == "max":
                    hgl_regime = "debordement"
                elif status_n == "surcharged":
                    hgl_regime = "surcharge"
                else:
                    hgl_regime = "inconnu"

            # Trouver la conduite qui sort de ce nœud vers le suivant
            conduit = None
            if i < len(path_nodes) - 1:
                next_nid = path_nodes[i + 1]
                edge_data = G.get_edge_data(nid, next_nid) or G.get_edge_data(next_nid, nid) or {}
                if edge_data:
                    geom = edge_data.get("geometry")
                    try:
                        length = float(edge_data.get("length") or (geom.length if geom else 15.0))
                    except (TypeError, ValueError):
                        length = 15.0
                    if not math.isfinite(length):
                        length = float(geom.length) if (geom is not None and math.isfinite(geom.length)) else 15.0
                    try:
                        diam_mm = float(edge_data.get("diam_mm") or edge_data.get("diametre_mm") or 600.0)
                    except (TypeError, ValueError):
                        diam_mm = 600.0
                    if not math.isfinite(diam_mm):
                        diam_mm = 600.0
                    conduit = {
                        "cid": edge_data.get("cid") or edge_data.get("id") or f"C_{i+1}",
                        "length": round(length, 2),
                        "diam_mm": diam_mm,
                        "materiau": edge_data.get("materiau", "Béton"),
                        "nom_voie": edge_data.get("nom_voie", ""),
                    }
                    # Résultats simulation sur cette conduite
                    cond_sim = {}
                    if sim_data:
                        all_cond = sim_data.get("conduit_results", {})
                        # Trouver la conduite par u_node/d_node
                        for ck, cv in all_cond.items():
                            if cv.get("u_node") == nid and cv.get("d_node") == next_nid:
                                cond_sim = cv
                                break
                    if cond_sim:
                        conduit["flow_ratio"] = cond_sim.get("flow_ratio", 0.0)
                        conduit["depth_ratio"] = cond_sim.get("depth_ratio", 0.0)
                        conduit["max_flow_cms"] = cond_sim.get("max_flow_cms", 0.0)
                        conduit["max_velocity_ms"] = cond_sim.get("max_velocity_ms")
                        conduit["status"] = cond_sim.get("status", "normal")
                        conduit["color"] = cond_sim.get("color", "#10b981")
                    else:
                        conduit["flow_ratio"] = 0.0
                        conduit["depth_ratio"] = 0.0
                        conduit["max_flow_cms"] = 0.0
                        conduit["max_velocity_ms"] = None
                        conduit["status"] = "inconnu"
                        conduit["color"] = "#64748b"

            # LOT P0.2 — plus de rehaussement heuristique de la HGL depuis le
            # statut de la conduite : la cote .out fait foi. Le statut réel
            # de la conduite reste reporté dans conduit_sortant.

            z_gs = (z_rad + (conduit["diam_mm"] / 1000.0 if conduit else diam_m)) if z_rad is not None else None
            pression_m = (round(max(0.0, hgl - z_gs), 2)
                          if (hgl is not None and z_gs is not None and hgl > z_gs) else 0.0)
            revanche_m = (round(max(0.0, z_terrain - hgl), 2)
                          if (z_terrain is not None and hgl is not None and hgl < z_terrain)
                          else (0.0 if (z_terrain is not None and hgl is not None) else None))

            # Cote du plan d'eau réel dans la conduite (Water Surface Profile - WSP)
            # Si en charge : la conduite est 100% pleine d'eau (z_eau = z_gs)
            # Si écoulement libre : z_eau = min(z_gs, max(z_rad, hgl))
            if hgl is not None and z_gs is not None and z_rad is not None:
                z_eau_conduite = z_gs if hgl >= z_gs else max(z_rad, hgl)
            elif z_rad is not None:
                z_eau_conduite = z_rad
            else:
                z_eau_conduite = None

            _ll_wgs = _noeud_wgs.get(nid)
            segments.append({
                "node_id": nid,
                "lng": _ll_wgs[0] if _ll_wgs else None,
                "lat": _ll_wgs[1] if _ll_wgs else None,
                "distance_m": round(distance_cumulee, 2),
                "z_radier": round(z_rad, 3) if z_rad is not None else None,
                "z_terrain": round(z_terrain, 3) if z_terrain is not None else None,
                "z_terrain_interp": round(z_terrain_interp, 3) if z_terrain_interp is not None else None,
                "terrain_confiance": terrain_confiance,
                "z_sommet_regard": round(z_sommet, 3) if z_sommet is not None else None,
                "terrain_reel": bool(terrain_reel),
                "terrain_source": terrain_source,
                "z_gen_superieure": round(z_gs, 3) if z_gs is not None else None,
                "z_eau_conduite": round(z_eau_conduite, 3) if z_eau_conduite is not None else None,
                "z_hgl": round(hgl, 3) if hgl is not None else None,
                "hgl_reel": hgl_reel,
                "hgl_source": hgl_src,
                "hgl_regime": hgl_regime,
                "simule": simule,
                "atteint_terrain": bool(z_terrain is not None and hgl is not None and hgl >= z_terrain),
                "atteint_sommet": bool(z_sommet is not None and hgl is not None and hgl >= z_sommet - 1e-6),
                "flooding_m3s": round(flooding_max, 6) if hgl_reel else None,
                "flood_source": flood_src,
                "flooding_max_m3s": round(flooding_global_max, 6) if hgl_reel else None,
                "rpt_flood_volume_m3": rpt_flood_vol,
                "flood_volume_estime": bool(nh_entry.get("flood_volume_estime", True)),
                "flood_time_minute": rpt_flood_min,
                "pression_m": pression_m,
                "revanche_m": revanche_m,
                "profondeur_m": round(prof_effectif, 2) if prof_effectif is not None else None,
                "cote_validee": cote_est_validee,
                "node_status": node_sim.get("status", "normal") if node_sim else "normal",
                "node_color": node_sim.get("color", "#10b981") if node_sim else "#10b981",
                "conduit_sortant": conduit,
            })

            if conduit:
                distance_cumulee += conduit.get("length", 0.0)

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

        for _i, _s in enumerate(segments):
            _cond = _s.get("conduit_sortant")
            # --- anomalies sur la conduite sortante (nœud i → i+1) ---
            if _cond and _i + 1 < len(segments):
                _long = _cond.get("length") or 0.0
                _sn = segments[_i + 1]
                _zr_a = _s.get("z_radier")
                _zr_b = _sn.get("z_radier")
                if _zr_a is not None and _zr_b is not None and _long > 0:
                    _n_liens_radier += 1
                    _dz = _zr_b - _zr_a
                    _pente_pct = round(-100.0 * _dz / _long, 2)
                    _cond["slope_pct"] = _pente_pct
                    _cond["dz_radier_m"] = round(_dz, 3)
                    if _dz > 0.02:
                        _n_contre_pentes += 1
                        _sev = "fort" if _dz > 0.30 else "moyen"
                        _jalon(
                            _sn, "contre_pente", _sev,
                            f"Contre-pente radier : +{_dz:.2f} m sur {_long:.0f} m "
                            f"(pente {_pente_pct:.1f} %) — l'eau doit remonter, "
                            f"vérifier le sens ou la cote aval",
                            valeur_m=_dz, unite="m",
                        )
                    elif _pente_pct > 8.0:
                        _jalon(
                            _sn, "pente_forte", "moyen",
                            f"Pente radier forte : {_pente_pct:.1f} % "
                            f"({_zr_a:.2f} → {_zr_b:.2f} m sur {_long:.0f} m) — "
                            f"risque d'érosion / vitesse excessive",
                            valeur_pct=_pente_pct, unite="%",
                        )
                    # vitesse d'autocurage (SWMM réel, jamais estimée)
                    _v = _cond.get("max_velocity_ms")
                    _q = _cond.get("max_flow_cms") or 0.0
                    if _v is not None:
                        if _v >= 4.0:
                            _jalon(
                                _sn, "vitesse_autocurage", "fort",
                                f"Vitesse max {_v:.2f} m/s ≥ 4 m/s — risque "
                                f"d'érosion et de mise en charge brutal",
                                valeur_ms=_v, unite="m/s",
                            )
                        elif _v >= 3.0:
                            _jalon(
                                _sn, "vitesse_autocurage", "moyen",
                                f"Vitesse max {_v:.2f} m/s ≥ 3 m/s — vérifier "
                                f"l'absence d'érosion et la tenue du radier",
                                valeur_ms=_v, unite="m/s",
                            )
                        elif _v < 0.6 and _q > 0.005:
                            _jalon(
                                _sn, "autocurage_insuffisant", "faible",
                                f"Vitesse max {_v:.2f} m/s < 0,6 m/s avec "
                                f"écoulement ({_q:.3f} m³/s) — risque de dépôt",
                                valeur_ms=_v, unite="m/s",
                            )
                # terrain interpolé qui remonte (info — bruit IDW possible)
                _zt_a = _s.get("z_terrain_interp")
                _zt_b = _sn.get("z_terrain_interp")
                if (_zt_a is not None and _zt_b is not None
                        and (_zt_b - _zt_a) > 0.5):
                    _jalon(
                        _sn, "terrain_remonte", "info",
                        f"Terrain interpolé remonte de {_zt_b - _zt_a:.2f} m "
                        f"— probable bruit IDW, pas une anomalie hydraulique",
                        valeur_m=round(_zt_b - _zt_a, 2), unite="m",
                    )
            # --- anomalies au nœud lui-même (hydraulique) ---
            _statut = _s.get("node_status") or ""
            _regime = _s.get("hgl_regime") or ""
            if _statut == "flooded" or _regime in ("inondation", "debordement"):
                _jalon(
                    _s, "hydraulique", "fort",
                    "Nœud inondé / débordement confirmé par SWMM — "
                    "intervention hydraulique requise",
                    flooding_m3s=_s.get("flooding_max_m3s"), unite="m³/s",
                )
            elif _statut == "surcharged" or _regime == "surcharge":
                _jalon(
                    _s, "hydraulique", "moyen",
                    "Conduite ou nœud en surcharge — HGL au-dessus de la "
                    "génératrice supérieure",
                    pression_m=_s.get("pression_m"), unite="m",
                )
            elif _s.get("atteint_sommet"):
                _jalon(
                    _s, "hydraulique", "faible",
                    "Plan d'eau atteint le sommet du regard — marge "
                    "quasi nulle",
                )

        _par_sev = {}
        _par_type = {}
        for _a in anomalies_liste:
            _par_sev[_a["severite"]] = _par_sev.get(_a["severite"], 0) + 1
            _par_type[_a["type"]] = _par_type.get(_a["type"], 0) + 1
        resume_anomalies = {
            "total": len(anomalies_liste),
            "par_severite": _par_sev,
            "par_type": _par_type,
            "orientation_suspecte": bool(
                _n_liens_radier >= 3
                and _n_contre_pentes > 0.5 * _n_liens_radier
            ),
            "liens_avec_radier": _n_liens_radier,
            "contre_pentes": _n_contre_pentes,
        }

        # Statistiques du profil — uniquement sur les cotes réellement
        # disponibles (aucune valeur nulle n'est comptée comme une altitude).
        _z_rad_vals = [s["z_radier"] for s in segments if s.get("z_radier") is not None]
        _z_ref_vals = ([s["z_terrain"] for s in segments if s.get("z_terrain") is not None]
                       + [s["z_sommet_regard"] for s in segments if s.get("z_sommet_regard") is not None])
        z_min = min(_z_rad_vals) if _z_rad_vals else 0.0
        z_max = max(_z_ref_vals) if _z_ref_vals else (max(_z_rad_vals) if _z_rad_vals else 0.0)
        longueur_totale = distance_cumulee
        conduites_en_charge = sum(
            1 for s in segments
            if s.get("conduit_sortant") and s["conduit_sortant"].get("status") in ("surcharge", "critique")
        )

        # Diagnostic automatique et recommandations expertes
        alerts = []
        for s in segments:
            cond = s.get("conduit_sortant")
            pression = s.get("pression_m") or 0.0
            regime = s.get("hgl_regime", "libre")
            flood_same = s.get("flooding_m3s") or 0.0
            flood_global = s.get("flooding_max_m3s") or 0.0
            z_hgl_s = s.get("z_hgl")
            z_sommet_s = s.get("z_sommet_regard")

            if regime == "debordement" or (base == "max" and s["node_status"] == "flooded"):
                reco = "Rehaussement du tampon, création d'un bassin de rétention amont ou surcalibrage de la conduite aval."
                if cond and cond.get("diam_mm"):
                    next_diam = int(cond["diam_mm"] * 1.35 // 100 * 100) or int(cond["diam_mm"] + 200)
                    reco = f"Préconisation : recalibrage conduite aval Ø{cond['diam_mm']:.0f} mm → Ø{next_diam} mm ou bassin tampon amont."
                # Observations construites UNIQUEMENT sur des faits SWMM :
                # jamais de « HGL ≥ Terrain » si la cote affichée est sous
                # le terrain (ou si aucun terrain vérifié n'existe).
                obs_parts = []
                if flood_same > 0.0:
                    obs_parts.append(f"Débordement SWMM : {flood_same:.3f} m³/s")
                    _fv = s.get("rpt_flood_volume_m3")
                    if _fv is not None and not s.get("flood_volume_estime", True):
                        if _fv > 0:
                            obs_parts.append(f"volume total débordé rapporté : {_fv:.2f} m³")
                        else:
                            obs_parts.append(
                                "volume total débordé < 0,5 m³ (valeur arrondie par "
                                "SWMM — volume exact non déterminable)")
                    else:
                        obs_parts.append(
                            "volume total débordé non déterminable depuis le rapport")
                    fm = s.get("flood_time_minute")
                    if fm is not None:
                        obs_parts.append(f"max vers {fm // 60:02d}:{fm % 60:02d}")
                elif flood_global > 0.0:
                    obs_parts.append(
                        "Débordement confirmé par SWMM — pic non visible dans la "
                        "série temporelle enregistrée (événement plus court que "
                        "le pas de rapport).")
                if z_hgl_s is not None:
                    if z_sommet_s is not None:
                        obs_parts.append(f"HGL max {z_hgl_s} m / plan de surverse {z_sommet_s} m")
                        obs_parts.append(f"Écart HGL / plan de surverse : {z_hgl_s - z_sommet_s:+.3f} m")
                    else:
                        obs_parts.append(f"HGL max {z_hgl_s} m")
                    if s.get("atteint_sommet"):
                        obs_parts.append("la cote a atteint le plan de surverse")
                    if s.get("atteint_terrain"):
                        obs_parts.append(f"et dépasse le terrain naturel ({s['z_terrain']} m)")
                if pression:
                    _diam_ob = f" (Ø{cond['diam_mm']:.0f} mm)" if (cond and cond.get("diam_mm")) else ""
                    obs_parts.append(
                        "charge au-dessus de la génératrice supérieure de la "
                        f"conduite sortante{_diam_ob} : +{pression} m")
                if not obs_parts:
                    obs_parts.append("Débordement confirmé par le rapport SWMM.")
                alerts.append({
                    "type": "debordement",
                    "node": s["node_id"],
                    "message": f"🔴 Regard {s['node_id']} : Débordement confirmé par SWMM (eau déversée en surface)",
                    "observations": ". ".join(obs_parts) + ".",
                    "recommandation": reco
                })
            elif base == "instant" and s["node_status"] == "flooded":
                # base=instant : le statut flooded est un maximum GLOBAL —
                # présenté comme alerte distincte, jamais comme un état
                # observé à l'instant affiché.
                fm = s.get("flood_time_minute")
                when = f" vers {fm // 60:02d}:{fm % 60:02d}" if fm is not None else ""
                alerts.append({
                    "type": "info",
                    "node": s["node_id"],
                    "message": f"ℹ️ Regard {s['node_id']} : pic de débordement ailleurs dans la simulation{when} — non observé à l'instant affiché",
                    "observations": f"Maximum global de débordement : {flood_global:.3f} m³/s (agrégé par SWMM, hors pas de rapport).",
                    "recommandation": "Consulter le profil en mode enveloppe (maxima) pour la vision complète."
                })
            elif regime == "inondation":
                alerts.append({
                    "type": "inondation",
                    "node": s["node_id"],
                    "message": f"🟠 Regard {s['node_id']} : niveau ≥ terrain naturel (sans débordement mesuré)",
                    "observations": f"HGL {z_hgl_s} m ≥ terrain {s['z_terrain']} m — mise en eau de surface ou stockage, à confirmer sur le MNT.",
                    "recommandation": "Vérifier la capacité de stockage superficiel et le point bas du secteur."
                })
            elif regime == "surcharge" or s["node_status"] == "surcharged" or (cond and cond.get("flow_ratio", 0) >= 1.0):
                flow_txt = f" (Q/Qmax = {cond['flow_ratio']:.0%})" if cond and cond.get("flow_ratio") else ""
                alerts.append({
                    "type": "surcharge",
                    "node": s["node_id"],
                    "message": f"🟡 Regard {s['node_id']} : Surcharge hydraulique en cheminée{flow_txt}",
                    "observations": f"Conduite en charge sous pression (+{pression} m au-dessus de la génératrice sup).",
                    "recommandation": f"Vérifier l'effet de remous aval et tester un élargissement de section."
                })
            elif cond and cond.get("flow_ratio", 0) >= 0.8:
                alerts.append({
                    "type": "critique",
                    "node": s["node_id"],
                    "message": f"🟠 Conduite {cond['cid']} proche de la saturation ({cond['flow_ratio']:.0%})",
                    "observations": "Capacité résiduelle inférieure à 20%.",
                    "recommandation": "Surveiller lors d'épisodes orageux de période de retour supérieure à T10."
                })

        if forcer_brut and cotes_suspectes_bloquantes:
            for cs in cotes_suspectes_bloquantes:
                alerts.append({
                    "type": "cote_suspecte_non_validee",
                    "node": cs["node_id"],
                    "message": f"⚠️ Regard {cs['node_id']} : Tracé avec cote brute non certifiée ({cs['valeur_brute']} m)",
                    "observations": "Cette valeur brute déforme l'échelle géométrique du profil.",
                    "recommandation": f"Validation recommandée à {cs['valeur_suggeree']} m.",
                })

        _hgl_max_srcs = {s.get("hgl_source") for s in segments if s.get("hgl_source")}
        _a_rpt = "rpt_max_head" in _hgl_max_srcs
        _a_out = "swmm_out_max_head" in _hgl_max_srcs
        hgl_source_global = (
            "swmm_rpt_max_head" if (base == "max" and _a_rpt and not _a_out)
            else "swmm_rpt_max_head_partiel" if (base == "max" and _a_rpt and _a_out)
            else hgl_source
        )

        # Fiabilité du modèle de la simulation sous-jacente (agent
        # garde-fou hydraulicien) : le profil affiche un avertissement
        # quand le modèle est dégradé.
        _gf_prof = ((sim_data.get("agents_expertise") or {}).get("controle_modele_hydraulique") or {}) if sim_data else {}

        # Provenance altimétrique des cotes radier : le profil déclare si le
        # modèle a été résolu sur altimétrie SIG réelle, terrain interpolé
        # (IDW) ou cotes synthétiques — indispensable pour interpréter tout
        # écart radier/terrain (ex. radier ~40 m sous le sol réel).
        _meta_alt = (sim_data.get("meta") or {}) if sim_data else {}
        _prov_alt = ((sim_data.get("provenance") or {}).get("altimetrie") or {}) if sim_data else {}
        _src_alt = str(_meta_alt.get("source_altimetrique") or "")
        _src_low = _src_alt.lower()

        # Écart médian radier ↔ terrain interpolé : quantifie le décalage de
        # datum. Calculé AVANT la détection du mode car il sert de repli pour
        # les anciennes simulations sans provenance enregistrée.
        _ecarts = [
            abs(s["z_radier"] - s["z_terrain_interp"])
            for s in segments
            if s.get("z_radier") is not None and s.get("z_terrain_interp") is not None
        ]
        if _ecarts:
            import statistics as _st
            _ecarts_tri = sorted(_ecarts)
            _ecart_med = round(_st.median(_ecarts_tri), 2)
            _ecart_max = round(_ecarts_tri[-1], 2)
        else:
            _ecart_med = _ecart_max = None

        if _prov_alt.get("mode") == "terrain_idw" or "terrain" in _src_low or "idw" in _src_low:
            _alt_mode, _alt_fiable = "terrain_idw", "estimee"
            _alt_label = "Altimétrie : terrain interpolé (IDW)"
        elif "réelles" in _src_low or "reelles" in _src_low or "sig" in _src_low:
            _alt_mode, _alt_fiable = "sig_reel", "reelle"
            _alt_label = "Altimétrie : SIG réelle"
        elif _src_alt:
            _alt_mode, _alt_fiable = "synthetique", "synthetique"
            _alt_label = "Altimétrie : synthétique"
        elif _ecart_med is not None and _ecart_med > 8.0:
            # Repli (anciennes simulations non estampillées) : un écart médian
            # radier↔terrain > 8 m trahit des cotes synthétiques sur un datum
            # fictif (ex. exutoire 100 m + pente) — jamais un vrai relief.
            _alt_mode, _alt_fiable = "synthetique", "synthetique"
            _alt_label = "Altimétrie : synthétique (inférée)"
        else:
            _alt_mode, _alt_fiable = "indisponible", "inconnue"
            _alt_label = "Altimétrie : source non tracée"

        _altimetrie_info = {
            "mode": _alt_mode,
            "fiable": _alt_fiable,
            "label": _alt_label,
            "source": _src_alt or None,
            "ecart_radier_terrain_med_m": _ecart_med,
            "ecart_radier_terrain_max_m": _ecart_max,
            "avertissement": (
                "Cotes radier synthétiques : exutoire de référence + pente "
                "moyenne, sans lien avec le terrain réel. Les écarts radier/"
                "terrain ne sont pas des anomalies hydrauliques mais un "
                "défaut de données altimétriques."
                if _alt_mode == "synthetique" else
                "Cotes radier dérivées du terrain interpolé (IDW ±1–2 m) : "
                "estimations, pas des mesures de radier."
                if _alt_mode == "terrain_idw" else
                "Cotes radier issues du SIG (relevés altimétriques)."
                if _alt_mode == "sig_reel" else
                "Provenance altimétrique non enregistrée pour cette simulation."
            ),
        }

        # Synthèse des anomalies hydrauliques du profil : indépendante de la
        # fiabilité du modèle (un modèle SAIN peut présenter des contre-pentes,
        # débordements ou dépôts). Compteurs par sévérité et types majeurs.
        _anoms_prof = [a for s in segments for a in (s.get("anomalies") or [])]
        _par_sev = {}
        _par_type = {}
        for _a in _anoms_prof:
            _sev = _a.get("severite") or "info"
            _par_sev[_sev] = _par_sev.get(_sev, 0) + 1
            if _sev in ("fort", "moyen"):
                _t = _a.get("type") or "autre"
                _par_type[_t] = _par_type.get(_t, 0) + 1
        _synthese_anomalies = {
            "total": len(_anoms_prof),
            "forts": _par_sev.get("fort", 0),
            "moyens": _par_sev.get("moyen", 0),
            "faibles": _par_sev.get("faible", 0),
            "types_majeurs": _par_type,
            "messages_forts": [
                _a.get("message") for _a in _anoms_prof
                if _a.get("severite") == "fort" and _a.get("message")
            ][:3],
        }

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
