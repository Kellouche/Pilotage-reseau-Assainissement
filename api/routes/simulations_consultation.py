# -*- coding: utf-8 -*-
"""
================================================================================
Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
Auteur : Dr Abdelhakim KELLOUCHE
Date de création : 2026-11-27
Date de modification : 2026-11-27
Objet : Endpoints de consultation : time series, recherche d'élément réseau, résultats et statuts de simulation (extraits de simulations.py).
================================================================================
"""

import logging
import time
from typing import Any, Dict, List, Optional, Union

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from api import crud, schemas
from api.core.security import get_tenant_context, TenantContext
from api.database import get_db
from api.routes.simulations_contexte import (
    _gpkg_demo_autorise,
    _identite_bassin_du_cache,
    _org_id_requete,
    _signaler_mismatch_version_gpkg,
)
from api.services.simulation_service import (
    ContexteSimulationIntrouvable,
    ProjetAmbigu,
    _resoudre_projet_pour_simulation,
    construire_reponse_simulation as _construire_reponse_simulation,
    est_simulation_valide as _est_simulation_valide,
    resoudre_gpkg_effectif_pour_projet as _resoudre_gpkg_effectif_pour_projet,
    resoudre_simulation_courante,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/simulations", tags=["Simulations — Consultation résultats"])


# ============================================================
# ANIMATION TEMPORELLE & TIME SLIDER (Phase 6.B)
# ============================================================

def _injecter_fiabilite_timeseries(ts_out: Dict[str, Any], sim_data: Dict[str, Any]) -> Dict[str, Any]:
    """Ajoute le verdict du garde-fou hydraulicien aux séries temporelles
    pour que le time slider affiche l'avertissement de fiabilité."""
    if isinstance(ts_out, dict) and isinstance(sim_data, dict):
        _gf = (sim_data.get("agents_expertise") or {}).get("controle_modele_hydraulique") or {}
        if _gf:
            ts_out["fiabilite_modele"] = _gf.get("fiabilite_modele")
            ts_out["modelisation_anomalies"] = _gf.get("anomalies") or []
    return ts_out


@router.get("/recherche-element")
def rechercher_element_reseau(
    q: str,
    project_id: Optional[str] = None,
    limite: int = 20,
    snapshot: Optional[str] = None,
    db: Session = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant_context),
):
    """
    Recherche un regard (par code) ou un tronçon (par regard amont/aval)
    dans le GPKG du projet — alimente l'outil de recherche du profil en
    long. Lecture seule, isolation org_id stricte (stealth 404).
    """
    org_id = _org_id_requete(tenant)
    requete = (q or "").strip()
    if len(requete) < 2:
        return {"resultats": [], "total": 0}
    limite = max(1, min(int(limite or 20), 50))

    proj = None
    try:
        proj = _resoudre_projet_pour_simulation(db, org_id, project_id)
    except ProjetAmbigu as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ContexteSimulationIntrouvable:
        if project_id:
            raise HTTPException(status_code=404, detail="Projet introuvable ou non autorisé.")
        proj = None
    gpkg_effectif = None
    if proj is not None:
        try:
            from api.services.gpkg_versions import (
                resoudre_snapshot_pour_lecture, GpkgSimulationError)
            snap_ctx = resoudre_snapshot_pour_lecture(db, proj, snapshot)
            gpkg_effectif = snap_ctx["path"]
        except GpkgSimulationError:
            if snapshot:
                raise HTTPException(status_code=404, detail="Ressource introuvable")
            gpkg_effectif = _resoudre_gpkg_effectif_pour_projet(db, proj)
    if gpkg_effectif is None:
        gpkg_effectif = _resoudre_gpkg_effectif_pour_projet(db, proj)
    if gpkg_effectif is None:
        gpkg_effectif = _gpkg_demo_autorise()
    if gpkg_effectif is None or not gpkg_effectif.exists():
        raise HTTPException(status_code=404, detail="Réseau introuvable.")

    from api.services.profil_topo_service import _charger_topo_pour_profil
    topo = _charger_topo_pour_profil(gpkg_effectif)
    node_index = topo.get("node_index") or {}
    canalisations = topo.get("canalisations")

    q_low = requete.lower()
    # Recherche numérique tolérante : « 615 » doit trouver « 6152 ».
    q_num = None
    try:
        q_num = float(requete)
    except (TypeError, ValueError):
        pass

    resultats = []

    # --- Regards ---
    for nid, info in node_index.items():
        nid_low = str(nid).lower()
        match = q_low in nid_low
        if not match and q_num is not None:
            try:
                match = float(nid) == q_num
            except (TypeError, ValueError):
                pass
        if match:
            resultats.append({
                "type": "regard",
                "id": nid,
                "libelle": f"Regard {nid}",
                "sous_titre": info.get("nom_voie") or "",
                "lng": info.get("x"),
                "lat": info.get("y"),
            })
            if len([r for r in resultats if r["type"] == "regard"]) >= limite:
                break

    # --- Tronçons (identifiés par le couple amont → aval) ---
    if canalisations is not None and len(resultats) < limite * 2:
        try:
            cols = set(canalisations.columns)
            col_am = next((c for c in ("ID_AMONT", "id_amont", "AMONT") if c in cols), None)
            col_av = next((c for c in ("ID_AVAL", "id_aval", "AVAL") if c in cols), None)
            if col_am and col_av:
                for _, row in canalisations.iterrows():
                    am = str(row.get(col_am) or "").strip()
                    av = str(row.get(col_av) or "").strip()
                    if not am or not av:
                        continue
                    pair = f"{am} → {av}"
                    hay = f"{am} {av} {pair}".lower()
                    match = q_low in hay
                    if not match and q_num is not None:
                        try:
                            match = (float(am) == q_num or float(av) == q_num)
                        except (TypeError, ValueError):
                            pass
                    if match:
                        try:
                            geom = row.geometry
                            cx, cy = (geom.centroid.x, geom.centroid.y) if geom else (None, None)
                        except Exception:
                            cx = cy = None
                        resultats.append({
                            "type": "troncon",
                            "id": pair,
                            "libelle": f"Tronçon {am} → {av}",
                            "sous_titre": str(row.get("NOM-VOIE") or row.get("nom_voie") or ""),
                            "lng": cx,
                            "lat": cy,
                            "amont": am,
                            "aval": av,
                        })
                        if len([r for r in resultats if r["type"] == "troncon"]) >= limite:
                            break
        except Exception as e:
            logger.warning("Recherche tronçons impossible : %s", e)

    # Regards d'abord, tronçons ensuite, plafond global
    regards = [r for r in resultats if r["type"] == "regard"][:limite]
    troncons = [r for r in resultats if r["type"] == "troncon"][:limite]

    # Conversion CRS projet → WGS84 pour le centrage carte Leaflet
    _crs = topo.get("crs")
    if _crs and "4326" not in str(_crs):
        try:
            from pyproj import Transformer
            _tf = Transformer.from_crs(str(_crs), "EPSG:4326", always_xy=True)
            for _r in regards + troncons:
                if _r.get("lng") is not None and _r.get("lat") is not None:
                    try:
                        _r["lng"], _r["lat"] = _tf.transform(_r["lng"], _r["lat"])
                    except Exception:
                        pass
        except Exception as e:
            logger.warning("Transformation CRS recherche impossible : %s", e)

    return {"resultats": regards + troncons, "total": len(regards) + len(troncons)}


@router.get("/timeseries")
def get_simulation_timeseries(
    cluster_id: Optional[Union[int, str]] = None,
    exutoire_noeud: Optional[str] = None,
    bassin_ref: Optional[str] = None,
    simulation_id: Optional[str] = None,
    db: Session = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant_context),
):
    """
    Retourne les séries temporelles extraites du fichier binaire .out de SWMM
    pour animer la propagation de l'onde de crue (Time Slider).

    Étape 3D.4 — séries lues depuis la simulation AUTORISÉE du contexte
    (org/projet), plus jamais depuis la globale `_DERNIERE_SIMULATION`.
    """
    org_id = _org_id_requete(tenant)

    # Simulation autorisée : filtre bassin si fourni, sinon dernière du projet.
    # Le cluster_id du dropdown est positionnel alors que les simulations
    # sont enregistrées sous exutoire_noeud/bassin_ref : résoudre la même
    # identité métier que /bassin/{id} sinon les séries d'un autre bassin
    # seraient servies (link_id sans correspondance → carte toute verte).
    filtres = {}
    if cluster_id is not None:
        filtres["cluster_id"] = cluster_id
    # Identité métier stable transmise directement par le client
    # (dataset.bassinRef / dataset.exutoireId du dropdown) : contourne le
    # pont positionnel→exutoire par cache, fragile si le cache est absent.
    if exutoire_noeud:
        filtres["exutoire_noeud"] = str(exutoire_noeud).strip()
    if bassin_ref:
        filtres["bassin_ref"] = str(bassin_ref).strip()
    if cluster_id is not None or exutoire_noeud or bassin_ref:
        try:
            _cid_txt = str(cluster_id).strip() if cluster_id is not None else ""
            _ref_ex = _cid_txt.lower().startswith("exutoire:")
            _cle = _cid_txt.split(":", 1)[1] if _ref_ex else cluster_id
            proj_id = _resoudre_projet_pour_simulation(db, org_id, None)
            gpkg_id = _resoudre_gpkg_effectif_pour_projet(db, proj_id)
            # _cid_txt conserve « exutoire: » : la fonction de cache
            # distingue les espaces exutoire / positionnel.
            ident = _identite_bassin_du_cache(gpkg_id, _cid_txt) if _cid_txt else {}
            _exo = ident.get("exutoire_id") or (_cle if _ref_ex else None)
            _bref = ident.get("bassin_ref") or (_cid_txt if _ref_ex else None)
            if _exo and "exutoire_noeud" not in filtres:
                filtres["exutoire_noeud"] = _exo
            if _bref and "bassin_ref" not in filtres:
                filtres["bassin_ref"] = _bref
            if ident.get("nom"):
                filtres["bassin_nom_attendu"] = ident["nom"]
        except Exception as _e_ident:
            # Sans ce log, une erreur transitoire (verrou SQLite pendant
            # l'écriture de la simulation, GPKG non résolu…) dégradait
            # silencieusement le filtre au seul cluster_id positionnel,
            # qui ne peut jamais matcher → 404 « aucune simulation active ».
            logger.warning("[timeseries] Identité bassin non résolue pour cluster_id=%s : %s", cluster_id, _e_ident)

    ctx = None
    sim_data: Dict[str, Any] = {}
    # Repli « dernière simulation » UNIQUEMENT sans filtre bassin : avec un
    # filtre demandé, servir les séries d'un autre bassin produirait
    # des link_id sans correspondance (carte entièrement verte).
    # simulation_id explicite = LA simulation affichée par le client :
    # prioritaire sur tout filtre bassin (évite de servir les séries d'une
    # sim d'une autre version réseau que le snapshot affiché).
    if simulation_id:
        try:
            ctx = resoudre_simulation_courante(
                db, org_id=org_id, resoudre_gpkg=False,
                simulation_id=simulation_id)
            sim_data = ctx.data or {}
        except (ContexteSimulationIntrouvable, ProjetAmbigu) as _e_ts:
            raise HTTPException(status_code=404, detail="Ressource introuvable")
    else:
        _a_filtre = bool(cluster_id is not None or exutoire_noeud or bassin_ref)
        _essais = [filtres] if _a_filtre else [filtres, {}]
        for f in _essais:
            try:
                ctx = resoudre_simulation_courante(
                    db, org_id=org_id, resoudre_gpkg=False, **f)
                sim_data = ctx.data or {}
                break
            except (ContexteSimulationIntrouvable, ProjetAmbigu):
                continue

    # 1. Séries temporelles déjà présentes dans le résultat persisté
    if sim_data and _est_simulation_valide(sim_data):
        ts = sim_data.get("timeseries")
        if ts and ts.get("status") == "SUCCESS":
            from src.domain.moteur_swmm.timeseries_extractor import enrichir_timeseries_pluie
            return _injecter_fiabilite_timeseries(enrichir_timeseries_pluie(ts, sim_data), sim_data)

        # Génération à la volée si l'INP est disponible
        inp_content = sim_data.get("inp_content")
        if inp_content:
            logger.info("Génération à la volée des séries temporelles (Phase 6.B)...")
            try:
                from src.domain.moteur_swmm.execution_solver import executer_solver_swmm
                _, _, ts_gen = executer_solver_swmm(inp_content, return_timeseries=True)
                if ts_gen and ts_gen.get("status") == "SUCCESS":
                    sim_data["timeseries"] = ts_gen
                    # Persister dans le résultat de LA simulation (fichier local
                    # ou clé store), jamais dans un cache anonyme.
                    if ctx is not None and ctx.simulation is not None:
                        from api.services.simulation_service import persister_resultat_simulation
                        persister_resultat_simulation(ctx.simulation, sim_data)
                    return _injecter_fiabilite_timeseries(ts_gen, sim_data)
            except Exception as e_calc:
                logger.warning("Erreur calcul à la volée timeseries: %s", e_calc)

    # 2. Si aucune simulation autorisée avec séries temporelles
    if not sim_data or not _est_simulation_valide(sim_data):
        raise HTTPException(
            status_code=404,
            detail="Aucune simulation active disponible. Veuillez lancer une simulation SWMM au préalable pour activer l'animation temporelle."
        )

    raise HTTPException(
        status_code=404,
        detail="Séries temporelles non disponibles pour cette simulation. Relancez la simulation pour générer les données dynamiques."
    )


# ============================================================
# ROUTES PARAMÉTRÉES /{simulation_id} (Placées à la fin)
# ============================================================

@router.get("/{simulation_id}/resultat")
def get_simulation_resultat(
    simulation_id: str,
    db: Session = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant_context),
):
    """
    Retourne le résultat COMPLET sauvegardé d'une simulation précise
    (result.json / cache), pour affichage instantané sur la carte —
    aucun recalcul SWMM, aucune nouvelle simulation créée.
    """
    org_id = _org_id_requete(tenant)
    ctx = None
    try:
        ctx = resoudre_simulation_courante(
            db, org_id=org_id, simulation_id=simulation_id,
            resoudre_gpkg=True)
    except (ContexteSimulationIntrouvable, ProjetAmbigu):
        ctx = None
    except Exception:
        # La résolution GPKG peut échouer sans que le résultat soit perdu
        try:
            ctx = resoudre_simulation_courante(
                db, org_id=org_id, simulation_id=simulation_id,
                resoudre_gpkg=False)
        except Exception:
            ctx = None

    if ctx is None or not ctx.data or not _est_simulation_valide(ctx.data):
        raise HTTPException(
            status_code=404,
            detail="Résultat de simulation introuvable ou invalide pour ce contexte.")

    data = ctx.data
    if ctx.gpkg_path is not None and ctx.gpkg_path.exists():
        data["source_gpkg"] = str(ctx.gpkg_path.resolve())
    if ctx.project is not None and getattr(ctx.project, "name", None):
        data["project_name"] = ctx.project.name
    _signaler_mismatch_version_gpkg(data, ctx, ctx.project)
    return _construire_reponse_simulation(
        data, cached=True,
        simulation_id=(ctx.simulation.id if ctx.simulation is not None else simulation_id))


@router.get("/{simulation_id}", response_model=schemas.SimulationResponse)
def get_simulation(
    simulation_id: str,
    db: Session = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant_context),
):
    """Récupère une simulation par ID (périmètre organisation strict)."""
    if simulation_id in ("profil-en-long", "timeseries", "latest", "run", "recalculate", "export", "bassin"):
        raise HTTPException(status_code=404, detail=f"Endpoint '{simulation_id}' non trouvé")
    sim = crud.get_simulation(db, simulation_id, org_id=_org_id_requete(tenant))
    if not sim:
        raise HTTPException(status_code=404, detail="Simulation non trouvée")
    return sim.to_dict()


@router.get("/job/{job_id}", response_model=schemas.SimulationResponse)
def get_simulation_by_job(
    job_id: str,
    db: Session = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant_context),
):
    """Récupère une simulation par job_id (Celery)."""
    sim = crud.get_simulation_by_job_id(db, job_id, org_id=_org_id_requete(tenant))
    if not sim:
        raise HTTPException(status_code=404, detail="Job non trouvé")
    return sim.to_dict()


@router.get("/cluster/{cluster_id}", response_model=List[schemas.SimulationResponse])
def list_cluster_simulations(
    cluster_id: int,
    status: Optional[str] = None,
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant_context),
):
    """Liste des simulations d'un cluster (périmètre organisation strict)."""
    sims = crud.get_simulations(
        db=db,
        status=status,
        skip=skip,
        limit=limit,
        org_id=_org_id_requete(tenant),
    )
    return [s.to_dict() for s in sims if (s.summary_kpis or {}).get("cluster_id") == cluster_id]


def _result_url_simulation(sim) -> Optional[str]:
    """
    URL de téléchargement du résultat d'une simulation.

    Priorité absolue : l'artefact permanent ResultStore `result.json`
    (clé ArtifactStore `{org}/{projet}/simulations/{id}/result.json`,
    compatible `/api/v1/artifacts/download`). Repli : `results_s3_key`
    legacy — qui peut être une clé ArtifactStore (anciennes sims Celery)
    ou un chemin local historique (auquel cas l'URL reste impropre au
    téléchargement, comportement inchangé).
    """
    try:
        from api.services.result_store import (
            ArtifactKind, ResultRef, ResultStore,
        )
        ref = ResultRef.depuis_simulation(sim)
        store = ResultStore()
        key = store.cle(ref, ArtifactKind.RESULT_JSON)
        if store.store.exists(key):
            return (f"/api/v1/artifacts/download?key={key}"
                    f"&project_id={ref.project_id}")
    except Exception:
        pass
    cle = getattr(sim, "results_s3_key", None)
    if cle:
        projet = getattr(sim, "project_id", None)
        suffix = f"&project_id={projet}" if projet else ""
        return f"/api/v1/artifacts/download?key={cle}{suffix}"
    return None


@router.get("/status/{job_id}", response_model=schemas.SimulationStatusResponse)
def get_simulation_status(
    job_id: str,
    db: Session = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant_context),
):
    """Polling du statut d'une simulation."""
    sim = crud.get_simulation_by_job_id(db, job_id, org_id=_org_id_requete(tenant))
    if not sim:
        raise HTTPException(status_code=404, detail="Job non trouvé")

    response = {
        "job_id": job_id,
        "status": sim.status
    }

    if sim.status.lower() == "completed":
        response["result_url"] = _result_url_simulation(sim)
    elif sim.status.lower() == "failed":
        response["error"] = (sim.summary_kpis or {}).get("error", "Simulation failed")

    return response


@router.delete("/{simulation_id}", status_code=status.HTTP_204_NO_CONTENT)
def cancel_simulation(
    simulation_id: str,
    db: Session = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant_context),
):
    """
    - pending/running : annule la simulation (statut 'cancelled') ;
    - statut final (completed/failed/cancelled) : suppression définitive
      de la simulation et de ses artefacts (cache disque + ResultStore).
    """
    from api.services.simulation_service import supprimer_simulation

    sim = crud.get_simulation(db, simulation_id, org_id=_org_id_requete(tenant))
    if not sim:
        raise HTTPException(status_code=404, detail="Simulation non trouvée")

    if sim.status.lower() in ["pending", "running"]:
        sim.status = "cancelled"
        db.commit()
        return None

    supprimer_simulation(sim, db)
    return None
