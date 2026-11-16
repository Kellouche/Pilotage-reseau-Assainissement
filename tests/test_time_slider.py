# -*- coding: utf-8 -*-
"""
================================================================================
Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
Auteur : Dr Abdelhakim KELLOUCHE
Date de création : 2026-04-20
Date de modification : 2026-11-09
Objet : Tests unitaires et d'intégration pour le Time Slider (Phase 6.B)
================================================================================
"""

import os
os.environ["TESTING"] = "true"

import pytest
from fastapi import HTTPException
from api.database import SessionLocal
from src.domain.moteur_swmm.timeseries_extractor import extraire_series_temporelles
from src.domain.moteur_swmm.execution_solver import executer_solver_swmm
from api.routes.simulations import get_simulation_timeseries
from types import SimpleNamespace
from api.models import Organization, Project, Simulation
import json
import uuid
from datetime import datetime, timezone
import tempfile
from pathlib import Path


def test_extraire_series_temporelles_fichier_inexistant():
    """Vérifie le comportement gracieux si le fichier .out n'existe pas."""
    res = extraire_series_temporelles("non_existent_file.out")
    assert res["status"] == "NO_DATA"
    assert res["steps"] == []


def test_executer_solver_swmm_retrocompatibilite():
    """Vérifie que executer_solver_swmm sans argument renvoie bien un tuple de 2 éléments."""
    inp = """[TITLE]
Test SWMM
[OPTIONS]
FLOW_UNITS CFS
INFILTRATION HORTON
FLOW_ROUTING KINWAVE
START_DATE 01/01/2026
START_TIME 00:00:00
END_DATE 01/01/2026
END_TIME 00:05:00
REPORT_STEP 00:01:00
[JUNCTIONS]
J1 10 0 0 0 0
J2 9 0 0 0 0
[OUTFALLS]
OUT1 8 FREE NO
[CONDUITS]
C1 J1 J2 100 0.01 0 0 0 0
C2 J2 OUT1 100 0.01 0 0 0 0
[XSECTIONS]
C1 CIRCULAR 1 0 0 0 1
C2 CIRCULAR 1 0 0 0 1
[REPORT]
INPUT NO
CONTROLS NO
SUBCATCHMENTS ALL
NODES ALL
LINKS ALL
"""
    # Appel classique (2 valeurs)
    ret = executer_solver_swmm(inp, return_timeseries=False)
    assert isinstance(ret, tuple)
    assert len(ret) == 2
    rpt_text, tmp_inp = ret
    assert isinstance(rpt_text, str)

    # Appel avec return_timeseries=True (3 valeurs)
    ret_ts = executer_solver_swmm(inp, return_timeseries=True)
    assert isinstance(ret_ts, tuple)
    assert len(ret_ts) == 3
    rpt_text2, tmp_inp2, ts_data = ret_ts
    assert isinstance(ts_data, dict)
    assert "steps" in ts_data
    assert ts_data["status"] == "SUCCESS"


def _uid() -> str:
    return uuid.uuid4().hex[:10]


def _contexte_isole(db):
    """Crée une org + projet isolés (aucune autre donnée ne peut fuiter)."""
    sfx = _uid()
    org = Organization(id=f"org_ts_{sfx}", name="OrgTS", slug=f"org-ts-{sfx}")
    proj = Project(id=f"proj_ts_{sfx}", org_id=org.id, name=f"Projet TS {sfx}")
    db.add_all([org, proj])
    db.commit()
    tenant = SimpleNamespace(org_id=org.id)
    return org, proj, tenant


def test_endpoint_timeseries_sans_simulation():
    """Vérifie que get_simulation_timeseries lève une 404 si aucune simulation autorisée."""
    db = SessionLocal()
    org = proj = None
    try:
        org, proj, tenant = _contexte_isole(db)
        with pytest.raises(HTTPException) as exc_info:
            get_simulation_timeseries(db=db, tenant=tenant)
        assert exc_info.value.status_code == 404
        assert "simulation" in exc_info.value.detail.lower()
    finally:
        if proj is not None:
            db.delete(proj)
        if org is not None:
            db.delete(org)
        db.commit()
        db.close()


def test_endpoint_timeseries_avec_donnees():
    """Vérifie que get_simulation_timeseries retourne le payload complet
    depuis la simulation persistée du contexte (3D.4 — plus de globale)."""
    db = SessionLocal()
    org = proj = sim = None
    try:
        org, proj, tenant = _contexte_isole(db)
        data = {
            "status": "SUCCESS",
            "conduit_results": {"C_1": {"flow_ratio": 0.5}},
            "node_results": {"2287": {"status": "normal"}},
            "meta": {"cluster_id": 1, "cluster_nom": "B1"},
            "timeseries": {
                "status": "SUCCESS",
                "duration_hours": 4.0,
                "total_steps": 240,
                "sampled_count": 2,
                "peak_outflow_m3s": 0.45,
                "peak_time": "01:30",
                "time_labels": ["00:00", "01:30"],
                "outflow_series": [0.0, 0.45],
                "steps": [
                    {
                        "step_index": 0,
                        "time_str": "00:00",
                        "minute": 0,
                        "outflow_m3s": 0.0,
                        "surcharged_pipes_count": 0,
                        "flooded_nodes_count": 0,
                        "flooded_nodes": [],
                        "links": {}
                    },
                    {
                        "step_index": 1,
                        "time_str": "01:30",
                        "minute": 90,
                        "outflow_m3s": 0.45,
                        "surcharged_pipes_count": 5,
                        "flooded_nodes_count": 1,
                        "flooded_nodes": ["2287"],
                        "links": {"C_1": 0.85}
                    }
                ]
            }
        }
        with tempfile.TemporaryDirectory() as td:
            fjson = Path(td) / "sim_ts.json"
            fjson.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            sim = Simulation(
                id=str(uuid.uuid4()), org_id=org.id, project_id=proj.id,
                name="SWMM_TS", status="completed",
                scenario_pluie="pluie_decennale", duree_heures=4.0,
                results_s3_key=str(fjson.resolve()),
                summary_kpis={"cluster_id": 1, "parameters": {}},
                created_at=datetime.now(timezone.utc),
            )
            db.add(sim)
            db.commit()
            out = get_simulation_timeseries(db=db, tenant=tenant)
        assert out["status"] == "SUCCESS"
        assert len(out["steps"]) == 2
        assert out["peak_outflow_m3s"] == 0.45
        assert "2287" in out["steps"][1]["flooded_nodes"]
    finally:
        if sim is not None:
            db.delete(sim)
        if proj is not None:
            db.delete(proj)
        if org is not None:
            db.delete(org)
        db.commit()
        db.close()


def _data_sim_ts(exutoire: str = "EX_1"):
    """Résultat minimal valide avec séries temporelles pour un exutoire."""
    return {
        "status": "SUCCESS",
        "conduit_results": {"C_1": {"flow_ratio": 0.5}},
        "node_results": {"N1": {"status": "normal"}},
        "meta": {"cluster_id": exutoire, "cluster_nom": "Bassin Test"},
        "timeseries": {
            "status": "SUCCESS",
            "duration_hours": 1.0,
            "total_steps": 1,
            "sampled_count": 1,
            "peak_outflow_m3s": 0.1,
            "time_labels": ["00:00"],
            "outflow_series": [0.1],
            "steps": [{
                "step_index": 0, "time_str": "00:00", "minute": 0,
                "outflow_m3s": 0.1, "surcharged_pipes_count": 0,
                "flooded_nodes_count": 0, "flooded_nodes": [],
                "links": {"C_1": 0.5},
            }],
        },
    }


def test_endpoint_timeseries_filtres_identite_stable():
    """Régression Rempois Chorfa : l'endpoint /timeseries doit résoudre la
    simulation via exutoire_noeud/bassin_ref explicites (identité stable du
    dropdown), sans dépendre du cluster_id positionnel ni du cache GPKG."""
    db = SessionLocal()
    org = proj = sim = None
    try:
        org, proj, tenant = _contexte_isole(db)
        data = _data_sim_ts()
        with tempfile.TemporaryDirectory() as td:
            fjson = Path(td) / "sim_ex.json"
            fjson.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            sim = Simulation(
                id=str(uuid.uuid4()), org_id=org.id, project_id=proj.id,
                name="SWMM_EX_1", status="completed",
                scenario_pluie="pluie_biennale", duree_heures=1.0,
                results_s3_key=str(fjson.resolve()),
                exutoire_noeud="EX_1",
                bassin_ref="exutoire:EX_1",
                summary_kpis={"cluster_id": "EX_1", "parameters": {}},
                created_at=datetime.now(timezone.utc),
            )
            db.add(sim)
            db.commit()

            # Identité stable explicite → résolution directe
            out = get_simulation_timeseries(
                db=db, tenant=tenant,
                exutoire_noeud="EX_1", bassin_ref="exutoire:EX_1")
            assert out["status"] == "SUCCESS"
            assert len(out["steps"]) == 1

            # Un autre exutoire ne doit JAMAIS retomber sur cette simulation
            with pytest.raises(HTTPException) as exc_info:
                get_simulation_timeseries(
                    db=db, tenant=tenant, exutoire_noeud="EX_AUTRE")
            assert exc_info.value.status_code == 404
    finally:
        if sim is not None:
            db.delete(sim)
        if proj is not None:
            db.delete(proj)
        if org is not None:
            db.delete(org)
        db.commit()
        db.close()


def test_identite_bassin_du_cache_espaces_identifiants():
    """Régression collision « 12 » : un exutoire_id numérique ne doit JAMAIS
    être matché par un cluster_id positionnel (et inversement). Sinon le
    dropdown « cluster 12 » résolvait le bassin dont l'exutoire est « 12 »
    → historique vide + timeseries 404 (cas réel Rempois Chorfa /
    Nouvelle ville hassania)."""
    from api.routes.simulations import _identite_bassin_du_cache

    cache = {
        "bassins_geojson": {"features": [
            {"properties": {"type": "bassin_urbain", "cluster_id": 1,
                            "id_bassin": 1, "exutoire_id": 12,
                            "nom": "Nouvelle ville hassania",
                            "bassin_ref": "exutoire:12"}},
            {"properties": {"type": "bassin_urbain", "cluster_id": 12,
                            "id_bassin": 12, "exutoire_id": "8_rejets_346731",
                            "nom": "Rempois chorfa",
                            "bassin_ref": "exutoire:8_rejets_346731"}},
        ]}
    }
    with tempfile.TemporaryDirectory() as td:
        gpkg = Path(td) / "reseau.gpkg"
        gpkg.write_bytes(b"fake")
        # with_suffix remplace « .gpkg » → « reseau.clusters_cache.json »
        Path(td, "reseau.clusters_cache.json").write_text(
            json.dumps(cache), encoding="utf-8")

        # cluster_id positionnel → match cluster_id/id_bassin uniquement
        assert _identite_bassin_du_cache(gpkg, "12")["nom"] == "Rempois chorfa"
        assert _identite_bassin_du_cache(gpkg, "1")["nom"] == "Nouvelle ville hassania"
        # préfixe exutoire → espace exutoire
        assert _identite_bassin_du_cache(gpkg, "exutoire:12")["nom"] == "Nouvelle ville hassania"
        assert _identite_bassin_du_cache(gpkg, "exutoire:8_rejets_346731")["nom"] == "Rempois chorfa"
        # identifiant stable nu → repli exutoire_id / bassin_ref
        assert _identite_bassin_du_cache(gpkg, "8_rejets_346731")["nom"] == "Rempois chorfa"
        assert _identite_bassin_du_cache(gpkg, "exutoire:inconnu") == {}


def test_construire_reponse_simulation_timeseries_uniquement_cached():
    """Après « Afficher » (mode cached), la réponse doit embarquer les séries
    temporelles persistées pour que le time-slider anime la simulation
    affichée — pas la plus récente du bassin. En mode run (non caché), la
    clé reste vide pour ne pas alourdir la réponse."""
    from api.services.simulation_service import construire_reponse_simulation

    resultat = {
        "meta": {"cluster_id": "EX_1"},
        "conduit_results": {},
        "node_results": {},
        "timeseries": {"status": "SUCCESS", "steps": [{"step_index": 0}]},
    }
    rep_cached = construire_reponse_simulation(resultat, cached=True)
    assert rep_cached["timeseries"]["status"] == "SUCCESS"
    rep_run = construire_reponse_simulation(resultat, cached=False)
    assert not rep_run.get("timeseries")
