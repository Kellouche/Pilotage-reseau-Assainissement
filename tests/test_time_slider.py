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


def test_indices_pics_surcharge_injection():
    """L'injection des instants de pic retient l'index du maximum CAPACITY
    des conduites dont le pic ≥ 0.8 — même s'il tombe entre deux pas
    échantillonnés réguliers (sinon la surcharge « rouge » n'apparaît
    jamais dans l'animation alors que le .rpt l'a captée)."""
    from datetime import datetime, timedelta
    from src.domain.moteur_swmm.timeseries_extractor import (
        _indices_pics_surcharge,
    )

    base = datetime(2026, 1, 1)
    times = [base + timedelta(minutes=i) for i in range(60)]

    # Pic bref à l'index 37 (hors grille régulière 0,6,12,…), valeur 1.0
    link_caps = {
        "C_pic": {times[i]: (1.0 if i == 37 else 0.1) for i in range(60)},
        "C_moyen": {times[i]: 0.5 for i in range(60)},   # pic < 0.8 → ignoré
        "C_rien": {times[i]: 0.0 for i in range(60)},
    }
    idx = _indices_pics_surcharge(link_caps, times)
    assert idx == [37]

    # Plusieurs liens : même index → dédupliqué ; index distincts triés
    link_caps["C_pic2"] = {times[i]: (0.95 if i == 50 else 0.1) for i in range(60)}
    idx = _indices_pics_surcharge(link_caps, times)
    assert idx == [37, 50]

    # Pic exactement à 0.8 → inclus (seuil de criticité)
    link_caps["C_seuil"] = {times[i]: (0.8 if i == 10 else 0.0) for i in range(60)}
    idx = _indices_pics_surcharge(link_caps, times)
    assert idx == [10, 37, 50]

    # Borne max_inject : seuls les pics les plus marqués sont conservés
    times_long = [base + timedelta(minutes=i) for i in range(120)]
    many = {}
    for i in range(100):
        many[f"L{i}"] = {times_long[5 + i]: 0.8 + i * 0.001}
    idx = _indices_pics_surcharge(many, times_long, max_inject=10)
    assert len(idx) == 10
    # les 10 plus fortes valeurs (i = 90..99 → index 95..104)
    assert idx == list(range(95, 105))


def test_extraire_series_temporelles_capture_pic_surcharge_bref():
    """Intégration : sur un .out réel avec surcharge, le maximum CAPACITY de
    chaque conduite critique (≥ 0.8) est retrouvé dans les steps échantillonnés."""
    pyswmm = pytest.importorskip("pyswmm")
    from pyswmm import Simulation, Output
    from swmm.toolkit.shared_enum import LinkAttribute

    inp = """[TITLE]
Test pic bref
[OPTIONS]
FLOW_UNITS CMS
INFILTRATION HORTON
FLOW_ROUTING DYNWAVE
START_DATE 01/01/2026
START_TIME 00:00:00
END_DATE 01/01/2026
END_TIME 03:00:00
REPORT_STEP 00:01:00
ALLOW_PONDING NO
[EVAPORATION]
CONSTANT 0
[JUNCTIONS]
J1 10.0 2.0 0 0 0
J2 9.0 2.0 0 0 0
J3 8.0 2.0 0 0 0
[OUTFALLS]
OUT1 7.5 FREE NO
[CONDUITS]
C1 J1 J2 50 0.013 0 0 0 0
C2 J2 J3 50 0.013 0 0 0 0
C3 J3 OUT1 50 0.013 0 0 0 0
[XSECTIONS]
C1 CIRCULAR 0.15 0 0 0 1
C2 CIRCULAR 0.15 0 0 0 1
C3 CIRCULAR 0.15 0 0 0 1
[SUBCATCHMENTS]
S1 RG1 J1 1.0 100 50 1.0 0
[SUBAREAS]
S1 0.015 0.10 2.0 5.0 25 OUTLET
[INFILTRATION]
S1 75 10 4 7 0
[RAINGAGES]
RG1 INTENSITY 0:05 1.0 TIMESERIES TS1
[TIMESERIES]
TS1 00:00 0.00
TS1 00:30 0.00
TS1 01:00 200.00
TS1 01:10 200.00
TS1 01:20 0.00
TS1 03:00 0.00
[REPORT]
INPUT NO
CONTROLS NO
SUBCATCHMENTS ALL
NODES ALL
LINKS ALL
"""
    with tempfile.NamedTemporaryFile(suffix=".inp", mode="w", delete=False,
                                     encoding="utf-8") as f:
        f.write(inp)
        tmp_inp = f.name
    out_path = tmp_inp.replace(".inp", ".out")
    try:
        with Simulation(tmp_inp) as sim:
            sim.execute()

        # Référence moteur : max CAPACITY par lien sur TOUS les pas .out
        ref_max = {}
        with Output(out_path) as out:
            for lid in out.links.keys():
                series = out.link_series(lid, LinkAttribute.CAPACITY)
                vals = [v for v in series.values() if v is not None]
                ref_max[lid] = max(vals) if vals else 0.0
        assert any(v >= 0.8 for v in ref_max.values()), \
            "Le scénario de test doit produire au moins une surcharge"

        # Échantillonnage volontairement grossier
        ts = extraire_series_temporelles(out_path, max_steps=30, inp_path=tmp_inp)
        assert ts["status"] == "SUCCESS"
        assert ts["steps"], "steps ne doit pas être vide"

        for lid, mx in ref_max.items():
            if mx < 0.8:
                continue
            sampled_max = max(
                (st.get("links", {}).get(lid, 0.0) or 0.0) for st in ts["steps"]
            )
            # round(..., 2) côté extracteur → tolérance 0.011
            assert sampled_max == pytest.approx(mx, abs=0.011), (
                f"Pic de {lid} non capturé : réel={mx:.3f} "
                f"échantillonné={sampled_max:.3f}"
            )
    finally:
        for p in (tmp_inp, out_path, tmp_inp.replace(".inp", ".rpt")):
            try:
                if os.path.exists(p):
                    os.unlink(p)
            except Exception:
                pass


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
