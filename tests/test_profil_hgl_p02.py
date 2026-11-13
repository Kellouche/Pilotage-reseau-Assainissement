# -*- coding: utf-8 -*-
"""
LOT P0.2 — Profil en long HGL fondé sur les résultats réels du .out SWMM.

Couvre :
- extraction des cotes hydrauliques réelles (HYDRAULIC_HEAD / INVERT_DEPTH /
  FLOODING_LOSSES) et comparaison aux valeurs de référence lues directement
  dans le .out par pyswmm.Output ;
- profil sans mise en charge, avec surcharge, avec débordement ;
- profil à un instant donné et profil aux valeurs maximales ;
- correspondance incorrecte/absente des références de nœuds ;
- .out absent ou simulation historique sans node_hydraulics ;
- simulation historique associée à un GPKG (versionné ou non).
"""

import json
import os
import tempfile
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest

os.environ["TESTING"] = "true"

from api.database import SessionLocal
from api.models import Organization, Project, Simulation
from api.routes.simulations import get_profil_en_long
from src.domain.moteur_swmm.execution_solver import executer_solver_swmm
from src.domain.moteur_swmm.timeseries_extractor import (
    extraire_series_temporelles,
    _extraire_inverts_noeuds_inp,
)

GPKG_TEST = Path("uploads/a66e32ad-f32b-4529-acc3-7a6026eb5a8a/network_Assainissement_Ville.gpkg")


# ---------------------------------------------------------------------------
# INP de test paramétrable (réseau minimal J1→J2→OUT)
# ---------------------------------------------------------------------------

def _inp_hydraulique(intensite=80.0, duree_h=2.0, diam=0.5,
                     allow_ponding="NO", longueur=100.0):
    return f"""[TITLE]
Test HGL P0.2
[OPTIONS]
FLOW_UNITS CMS
INFILTRATION HORTON
FLOW_ROUTING DYNWAVE
START_DATE 01/01/2026
START_TIME 00:00:00
END_DATE 01/01/2026
END_TIME {int(duree_h):02d}:00:00
REPORT_STEP 00:01:00
ALLOW_PONDING {allow_ponding}
[EVAPORATION]
CONSTANT 0
[JUNCTIONS]
J1 10.0 2.0 0 0 0
J2 9.0 2.0 0 0 0
J3 8.0 2.0 0 0 0
[OUTFALLS]
OUT1 7.5 FREE NO
[CONDUITS]
C1 J1 J2 {longueur} 0.013 0 0 0 0
C2 J2 J3 {longueur} 0.013 0 0 0 0
C3 J3 OUT1 {longueur} 0.013 0 0 0 0
[XSECTIONS]
C1 CIRCULAR {diam} 0 0 0 1
C2 CIRCULAR {diam} 0 0 0 1
C3 CIRCULAR {diam} 0 0 0 1
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
TS1 00:30 {intensite:.2f}
TS1 01:30 {intensite:.2f}
TS1 {int(duree_h):02d}:00 0.00
[REPORT]
INPUT NO
CONTROLS NO
SUBCATCHMENTS ALL
NODES ALL
LINKS ALL
"""


# ---------------------------------------------------------------------------
# A. Extraction .out — réseau sans mise en charge
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not GPKG_TEST.exists(), reason="GPKG de référence absent")
def test_extraction_hydraulique_noeuds_reelle():
    """node_hydraulics provient du .out : max_head = max de la série,
    head = invert + tirant d'eau (surface libre), inverts lus depuis le .inp."""
    inp = _inp_hydraulique(intensite=40.0)
    rpt, tmp_inp, ts = executer_solver_swmm(inp, return_timeseries=True)
    assert ts["status"] == "SUCCESS"
    nh = ts.get("node_hydraulics") or {}
    assert nh, "node_hydraulics doit être extrait du .out"
    assert ts.get("hgl_source") == "swmm_out"

    for nid, entry in nh.items():
        heads = entry["heads"]
        assert heads, f"série de cotes vide pour {nid}"
        # CONTRÔLE P0.2 — max_head_m = maximum EXHAUSTIF (tous pas SWMM) ;
        # max_head_sampled_m = maximum de la seule série échantillonnée.
        assert entry["max_head_m"] >= max(h for _, h in heads) - 1e-6
        assert entry["max_head_sampled_m"] == pytest.approx(
            max(h for _, h in heads), abs=1e-3)
        # en surface libre : head ≈ invert + depth ; head ≥ invert toujours
        if entry.get("invert_m") is not None:
            assert entry["max_head_m"] >= entry["invert_m"] - 1e-6
        # série temporelle continue (minutes croissantes)
        minutes = [m for m, _ in heads]
        assert minutes == sorted(minutes)


def test_extraction_hydraulique_reference_moteur():
    """Les valeurs extraites sont comparées aux relevés directs du .out
    par pyswmm.Output (référence moteur SWMM)."""
    pyswmm = pytest.importorskip("pyswmm")
    from pyswmm import Simulation, Output
    from swmm.toolkit.shared_enum import NodeAttribute

    inp = _inp_hydraulique(intensite=60.0)
    with tempfile.NamedTemporaryFile(suffix=".inp", mode="w", delete=False,
                                     encoding="utf-8") as f:
        f.write(inp)
        tmp_inp = f.name
    out_path = tmp_inp.replace(".inp", ".out")
    rpt_path = tmp_inp.replace(".inp", ".rpt")
    try:
        with Simulation(tmp_inp) as sim:
            sim.execute()
        # Référence : lecture directe du .out
        ref_max_head = {}
        with Output(out_path) as out:
            for nid in out.nodes.keys():
                series = out.node_series(nid, NodeAttribute.HYDRAULIC_HEAD)
                ref_max_head[nid] = max(series.values()) if series else None
        # Extraction applicative sur le même .out
        ts = extraire_series_temporelles(out_path, inp_path=tmp_inp)
        assert ts["status"] == "SUCCESS"
        nh = ts["node_hydraulics"]
        assert set(nh.keys()) == set(ref_max_head.keys())
        for nid, ref_h in ref_max_head.items():
            assert nh[nid]["max_head_m"] == pytest.approx(ref_h, abs=5e-3), \
                f"max_head {nid} : extrait={nh[nid]['max_head_m']} réf={ref_h}"
    finally:
        for p in (tmp_inp, out_path, rpt_path):
            try:
                if os.path.exists(p):
                    os.unlink(p)
            except Exception:
                pass


def test_extraction_inverts_inp():
    """Les cotes d'invert proviennent des sections [JUNCTIONS]/[OUTFALLS]."""
    inp = _inp_hydraulique()
    with tempfile.NamedTemporaryFile(suffix=".inp", mode="w", delete=False,
                                     encoding="utf-8") as f:
        f.write(inp)
        tmp_inp = f.name
    try:
        inv = _extraire_inverts_noeuds_inp(tmp_inp)
        assert inv["J1"] == pytest.approx(10.0)
        assert inv["J2"] == pytest.approx(9.0)
        assert inv["J3"] == pytest.approx(8.0)
        assert inv["OUT1"] == pytest.approx(7.5)
    finally:
        try:
            os.unlink(tmp_inp)
        except Exception:
            pass


def test_extraction_out_absent():
    """Fichier .out absent → NO_DATA, aucune donnée fabriquée."""
    res = extraire_series_temporelles("fichier_inexistant_p02.out")
    assert res["status"] == "NO_DATA"
    assert res["steps"] == []


# ---------------------------------------------------------------------------
# B. Endpoint profil — données réelles vs absentes
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def ctx_profil_hgl():
    if not GPKG_TEST.exists():
        pytest.skip("GeoPackage de référence absent")
    db = SessionLocal()
    sfx = uuid.uuid4().hex[:8]
    org = Organization(id=f"org_hgl_{sfx}", name="Org HGL", slug=f"org-hgl-{sfx}")
    proj = Project(
        id=f"proj_hgl_{sfx}", org_id=org.id, name="Projet HGL",
        source_gpkg_key=str(GPKG_TEST.resolve()), gpkg_version_id=None,
        is_archived=False,
    )
    db.add_all([org, proj])
    db.commit()
    yield {"db": db, "org": org, "proj": proj,
           "tenant": SimpleNamespace(org_id=org.id)}
    db.delete(proj)
    db.delete(org)
    db.commit()
    db.close()


def _sim_data_hgl(node_hydraulics, with_ts=True):
    """Payload de simulation persistée : résultats + cotes .out réelles."""
    data = {
        "node_results": {},
        "conduit_results": {"C1": {"u_node": "2674", "d_node": "2672",
                                   "flow_ratio": 0.4, "depth_ratio": 0.3,
                                   "status": "normal", "color": "#10b981"}},
        "meta": {"cluster_id": 1, "cluster_nom": "Bassin test",
                 "bbox": [3.0, 36.0, 3.1, 36.1], "junctions_count": 5,
                 "conduits_count": 4},
        "inp_content": ("[TITLE]\nTest HGL\n[JUNCTIONS]\n"
                        "2674 0.0 2.0 0.0 0.0 0.0\n"
                        "2672 0.0 2.0 0.0 0.0 0.0\n"),
    }
    if with_ts:
        data["timeseries"] = {"status": "SUCCESS", "steps": [],
                              "node_hydraulics": node_hydraulics}
    return data


def _creer_simulation(db, ctx, data, suffix=""):
    sim_id = f"sim_hgl_{uuid.uuid4().hex[:8]}{suffix}"
    fjson = Path(tempfile.mkdtemp()) / f"{sim_id}.json"
    fjson.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    sim = Simulation(
        id=sim_id, org_id=ctx["org"].id, project_id=ctx["proj"].id,
        name=f"sim_hgl{suffix}", status="completed",
        scenario_pluie="pluie_decennale", duree_heures=4.0,
        results_s3_key=str(fjson.resolve()),
        summary_kpis={},
    )
    db.add(sim)
    db.commit()
    return sim


def _nh(head_max, invert=100.0, heads=None, flooding=0.0, floods=None):
    return {
        "invert_m": invert,
        "max_head_m": head_max,
        "max_head_minute": 60,
        "max_depth_m": round(max(0.0, head_max - invert), 4),
        "flooding_max_m3s": flooding,
        "heads": heads if heads is not None else [[0, head_max - 0.1], [60, head_max]],
        "floods": floods if floods is not None else ([[60, flooding]] if flooding else []),
    }


def test_profil_hgl_reelle_max(ctx_profil_hgl):
    """Sans mise en charge : z_hgl = cote .out réelle, hgl_reel=True,
    hgl_source=swmm_out_max_head."""
    db, ctx = ctx_profil_hgl["db"], ctx_profil_hgl
    nh = {"2674": _nh(105.20, invert=105.0), "2672": _nh(104.10, invert=103.9)}
    sim = _creer_simulation(db, ctx, _sim_data_hgl(nh), suffix="_max")
    try:
        res = get_profil_en_long(node_amont="2674", node_aval="2672",
                                 db=db, tenant=ctx["tenant"])
        assert res["status"] == "success"
        assert res["hgl_source"] == "swmm_out_max_head"
        assert res["hgl_base"] == "max"
        # Enveloppe des maxima individuels : identifiée explicitement,
        # les instants des maxima peuvent différer d'un nœud à l'autre.
        assert "enveloppe" in res["hgl_base_label"]
        segs = {s["node_id"]: s for s in res["segments"]}
        # Les nœuds couverts par le .out ont leur cote réelle
        assert segs["2674"]["z_hgl"] == pytest.approx(105.20, abs=0.01)
        assert segs["2674"]["hgl_reel"] is True
        assert segs["2672"]["z_hgl"] == pytest.approx(104.10, abs=0.01)
        # Nœuds intermédiaires sans donnée .out → HGL honnêtement absente
        for s in res["segments"]:
            if s["node_id"] not in ("2674", "2672"):
                assert s["z_hgl"] is None
                assert s["hgl_reel"] is False
                assert s["hgl_regime"] == "inconnu"
        # Simulation persistée retrouvée (pas de repli fabrique)
        assert res["simulation_active"] is True
    finally:
        db.delete(sim)
        db.commit()


def test_profil_hgl_instantane(ctx_profil_hgl):
    """base='instant' : la cote est celle du pas de temps demandé."""
    db, ctx = ctx_profil_hgl["db"], ctx_profil_hgl
    nh = {"2674": _nh(105.50, heads=[[0, 105.0], [60, 105.3], [120, 105.5]])}
    sim = _creer_simulation(db, ctx, _sim_data_hgl(nh), suffix="_inst")
    try:
        res = get_profil_en_long(node_amont="2674", node_aval="2672",
                                 base="instant", instant_minute=60,
                                 db=db, tenant=ctx["tenant"])
        assert res["hgl_source"] == "swmm_out_instant"
        assert res["instant_minute"] == 60
        segs = {s["node_id"]: s for s in res["segments"]}
        assert segs["2674"]["z_hgl"] == pytest.approx(105.30, abs=0.01)
        # Validation des paramètres
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as e1:
            get_profil_en_long(node_amont="2674", node_aval="2672",
                               base="instant", db=db, tenant=ctx["tenant"])
        assert e1.value.status_code == 422
        with pytest.raises(HTTPException) as e2:
            get_profil_en_long(node_amont="2674", node_aval="2672",
                               base="inconnu", db=db, tenant=ctx["tenant"])
        assert e2.value.status_code == 422
    finally:
        db.delete(sim)
        db.commit()


def test_profil_regime_surcharge_et_debordement(ctx_profil_hgl):
    """Mise en charge / débordement déduits de la cote RÉELLE vs géométrie.
    P0 — le GPKG de référence ne contient aucune cote terrain vérifiée :
    z_terrain=None, aucune courbe MNT n'est prétendue ; la référence haute
    est le sommet de regard SWMM (radier + MaxDepth .inp)."""
    db, ctx = ctx_profil_hgl["db"], ctx_profil_hgl
    # D'abord sonder les cotes géométriques réelles du tronçon
    nh_probe = {"2674": _nh(105.0), "2672": _nh(104.0)}
    sim_probe = _creer_simulation(db, ctx, _sim_data_hgl(nh_probe), suffix="_probe")
    try:
        res_probe = get_profil_en_long(node_amont="2674", node_aval="2672",
                                       db=db, tenant=ctx["tenant"])
        segs = {s["node_id"]: s for s in res_probe["segments"]}
        z_terrain = segs["2674"]["z_terrain"]
        z_gs = segs["2674"]["z_gen_superieure"]
        z_sommet = segs["2674"]["z_sommet_regard"]
        assert z_terrain is None           # aucun MNT vérifié dans le GPKG
        assert res_probe["terrain_disponible"] is False
        assert z_sommet is not None        # sommet SWMM = radier + MaxDepth
    finally:
        db.delete(sim_probe)
        db.commit()

    # Mise en charge : head au-dessus de la génératrice sup mais sous le sommet
    head_surcharge = z_gs + 0.3
    assert head_surcharge < z_sommet
    nh = {"2674": _nh(head_surcharge)}
    sim = _creer_simulation(db, ctx, _sim_data_hgl(nh), suffix="_surch")
    try:
        res = get_profil_en_long(node_amont="2674", node_aval="2672",
                                 db=db, tenant=ctx["tenant"])
        seg = {s["node_id"]: s for s in res["segments"]}["2674"]
        assert seg["hgl_regime"] == "surcharge"
        assert seg["z_hgl"] == pytest.approx(head_surcharge, abs=0.01)
        assert seg["pression_m"] > 0
        assert not any(a["type"] == "debordement" for a in res["alertes"]
                       if a["node"] == "2674")
    finally:
        db.delete(sim)
        db.commit()

    # Niveau ≥ sommet du regard SANS débit de débordement et SANS terrain
    # vérifié : surcharge (mise en charge), JAMAIS « inondation » ni
    # « débordement » — la cote terrain n'est pas connue.
    nh = {"2674": _nh(z_sommet + 0.2)}
    sim = _creer_simulation(db, ctx, _sim_data_hgl(nh), suffix="_flood")
    try:
        res = get_profil_en_long(node_amont="2674", node_aval="2672",
                                 db=db, tenant=ctx["tenant"])
        seg = {s["node_id"]: s for s in res["segments"]}["2674"]
        assert seg["hgl_regime"] == "surcharge"
        assert seg["atteint_sommet"] is True
        assert seg["atteint_terrain"] is False
        assert seg["flooding_max_m3s"] == 0.0
        assert not any(a["type"] == "debordement" for a in res["alertes"])
    finally:
        db.delete(sim)
        db.commit()

    # Débordement réel : FLOODING_LOSSES > 0 calculé par SWMM.
    nh = {"2674": _nh(z_sommet + 0.2, flooding=0.12)}
    sim = _creer_simulation(db, ctx, _sim_data_hgl(nh), suffix="_flood3")
    try:
        res = get_profil_en_long(node_amont="2674", node_aval="2672",
                                 db=db, tenant=ctx["tenant"])
        seg = {s["node_id"]: s for s in res["segments"]}["2674"]
        assert seg["hgl_regime"] == "debordement"
        assert seg["flooding_max_m3s"] == pytest.approx(0.12)
    finally:
        db.delete(sim)
        db.commit()

    # Débordement par pertes de surface même si head < sommet
    nh = {"2674": _nh(z_gs - 0.1, flooding=0.05)}
    sim = _creer_simulation(db, ctx, _sim_data_hgl(nh), suffix="_flood2")
    try:
        res = get_profil_en_long(node_amont="2674", node_aval="2672",
                                 db=db, tenant=ctx["tenant"])
        seg = {s["node_id"]: s for s in res["segments"]}["2674"]
        assert seg["hgl_regime"] == "debordement"
    finally:
        db.delete(sim)
        db.commit()


def test_profil_historique_sans_out(ctx_profil_hgl):
    """Simulation historique sans node_hydraulics (.out non persisté) :
    aucune HGL estimée — z_hgl=None, hgl_source=indisponible,
    régime qualifié par le statut RPT réel uniquement."""
    db, ctx = ctx_profil_hgl["db"], ctx_profil_hgl
    data = _sim_data_hgl({}, with_ts=False)
    data["node_results"] = {"2674": {"status": "flooded", "color": "#ef4444"}}
    sim = _creer_simulation(db, ctx, data, suffix="_hist")
    try:
        res = get_profil_en_long(node_amont="2674", node_aval="2672",
                                 db=db, tenant=ctx["tenant"])
        assert res["hgl_source"] == "indisponible"
        segs = {s["node_id"]: s for s in res["segments"]}
        assert segs["2674"]["z_hgl"] is None
        assert segs["2674"]["hgl_reel"] is False
        # Le statut RPT réel (flooded) qualifie le régime sans inventer de cote
        assert segs["2674"]["hgl_regime"] == "debordement"
        assert segs["2674"]["node_status"] == "flooded"
        for s in res["segments"]:
            if s["node_id"] != "2674":
                assert s["z_hgl"] is None
    finally:
        db.delete(sim)
        db.commit()


def test_profil_instantane_coherence_temporelle(ctx_profil_hgl):
    """CONTRÔLE P0.2/A — un débordement survenu à un autre instant ne doit
    pas être présenté comme un débordement à l'instant demandé : cote,
    débordement et classification au même pas de temps."""
    db, ctx = ctx_profil_hgl["db"], ctx_profil_hgl
    # Cote requested instant=0 ; débordement survenu à t=120
    nh = {"2674": _nh(
        118.0,
        heads=[[0, 105.0], [60, 105.0], [120, 118.0]],
        flooding=0.4,
        floods=[[120, 0.4]],
    )}
    sim = _creer_simulation(db, ctx, _sim_data_hgl(nh), suffix="_tps")
    try:
        # À t=0 : head=105 (probablement < terrain), PAS de débordement
        res0 = get_profil_en_long(node_amont="2674", node_aval="2672",
                                  base="instant", instant_minute=0,
                                  db=db, tenant=ctx["tenant"])
        seg0 = {s["node_id"]: s for s in res0["segments"]}["2674"]
        assert seg0["z_hgl"] == pytest.approx(105.0, abs=0.01)
        assert seg0["flooding_m3s"] == 0.0
        assert seg0["hgl_regime"] != "debordement"

        # À t=120 : head=118 (crête) + débordement au même pas
        res120 = get_profil_en_long(node_amont="2674", node_aval="2672",
                                    base="instant", instant_minute=120,
                                    db=db, tenant=ctx["tenant"])
        seg120 = {s["node_id"]: s for s in res120["segments"]}["2674"]
        assert seg120["z_hgl"] == pytest.approx(118.0, abs=0.01)
        assert seg120["flooding_m3s"] == pytest.approx(0.4)
        assert seg120["hgl_regime"] == "debordement"

        # Enveloppe max : head max=118 ET flooding max=0.4 → debordement
        # (documenté comme maxima individuels, instants potentiellement
        # differents — voir hgl_base_label).
        resmax = get_profil_en_long(node_amont="2674", node_aval="2672",
                                    db=db, tenant=ctx["tenant"])
        segmax = {s["node_id"]: s for s in resmax["segments"]}["2674"]
        assert segmax["z_hgl"] == pytest.approx(118.0, abs=0.01)
        assert segmax["flooding_max_m3s"] == pytest.approx(0.4)
        assert "enveloppe" in resmax["hgl_base_label"]
    finally:
        db.delete(sim)
        db.commit()


def test_profil_noeuds_hors_out(ctx_profil_hgl):
    """Références de nœuds absentes du .out : HGL indisponible pour ces
    nœuds, jamais de correspondance approximative."""
    db, ctx = ctx_profil_hgl["db"], ctx_profil_hgl
    # node_hydraulics ne contient que des noms étrangers au réseau
    nh = {"NOEUD_INEXISTANT": _nh(105.0), "AUTRE_FAUX": _nh(104.0)}
    sim = _creer_simulation(db, ctx, _sim_data_hgl(nh), suffix="_badref")
    try:
        res = get_profil_en_long(node_amont="2674", node_aval="2672",
                                 db=db, tenant=ctx["tenant"])
        for s in res["segments"]:
            assert s["z_hgl"] is None
            assert s["hgl_reel"] is False
    finally:
        db.delete(sim)
        db.commit()
