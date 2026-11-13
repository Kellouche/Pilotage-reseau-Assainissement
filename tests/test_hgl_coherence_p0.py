# -*- coding: utf-8 -*-
"""
LOT P0 — Cohérence hydraulique carte / diagnostic / profil en long.

Couvre la réconciliation SWMM démontrée dans l'audit P0 / P0.0.1 :
- parsing des synthèses .rpt (Node Depth Summary, Node Flooding Summary) ;
- maxima .rpt (pas de routage) prioritaires sur les maxima .out
  (instants de rapport) pour base='max' ;
- débordement confirmé par .rpt alors que FLOODING_LOSSES du .out vaut 0 ;
- absence de faux débordement sur simple surcharge ;
- instantané sans injection du statut global de débordement ;
- MNT absent : aucune courbe terrain prétendue, sommet de regard SWMM
  exposé séparément ;
- nœud non simulé : aucune altitude/HGL heuristique ;
- dégradation explicite quand le .rpt est absent ou incomplet.
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
from src.domain.moteur_swmm.analyse_rapport import (
    analyser_rapport_swmm_impl,
    enrichir_hydraulique_noeuds,
)

GPKG_TEST = Path("uploads/a66e32ad-f32b-4529-acc3-7a6026eb5a8a/network_Assainissement_Ville.gpkg")


# ---------------------------------------------------------------------------
# Fixture .rpt synthétique (structure réelle EPA SWMM 5.2)
# ---------------------------------------------------------------------------

RPT_SYNTHETIQUE = """
  Node Surcharge Summary
  **********************
  Node                 Type       Hours   Avg. Height   Max. Height   Min. Depth
                                                Above Crown     Below Rim
  7018                 JUNCTION     0.09       1.500         1.500        0.000
  7019                 JUNCTION     0.07       1.500         1.500        0.000



  Node Flooding Summary
  *********************
  Flooding refers to all water that overflows a node, whether it ponds or not.
  --------------------------------------------------------------------------
                                                             Total   Maximum
                                 Maximum   Time of Max       Flood    Ponded
                        Hours       Rate    Occurrence      Volume     Depth
  Node                 Flooded       CMS   days hr:min    10^6 ltr    Meters
  --------------------------------------------------------------------------
  7018                    0.01     0.067      0  01:05       0.000     0.000
  7019                    0.01     0.075      0  01:05       0.000     0.000



  Node Depth Summary
  ******************
  ---------------------------------------------------------------------------------
                                 Average  Maximum  Maximum  Time of Max    Reported
                                   Depth    Depth      HGL   Occurrence   Max Depth
  Node                 Type       Meters   Meters   Meters  days hr:min      Meters
  ---------------------------------------------------------------------------------
  7018                 JUNCTION     0.47     2.00   106.70     0  01:05        0.90
  7019                 JUNCTION     0.44     2.00   107.23     0  01:05        0.87
  7020                 JUNCTION     0.40     2.00   107.68     0  01:05        0.76



  Link Flow Summary
  *****************
  Link                Type      Flow     Time of     Velocity     Depth      Flow     Depth
                                (cms)    Maximum      (m/s)     (m)      Ratio    Ratio
  C1                  CONDUIT    0.500    0  01:00      1.000     0.90      1.10     0.95
"""


# ---------------------------------------------------------------------------
# A. Parsing .rpt — maxima par identifiant exact
# ---------------------------------------------------------------------------

def test_parse_node_depth_summary_maxima():
    """Node Depth Summary → maxima HGL/profondeur par id SWMM exact,
    statut 'ok'. Les valeurs sont des maxima au pas de calcul."""
    kpis = analyser_rapport_swmm_impl(rpt_text=RPT_SYNTHETIQUE, meta={})
    assert kpis["node_depth_maxima_status"] == "ok"
    m = kpis["node_depth_maxima"]
    assert m["7018"]["max_hgl_m"] == pytest.approx(106.70)
    assert m["7018"]["max_depth_m"] == pytest.approx(2.00)
    assert m["7018"]["reported_max_depth_m"] == pytest.approx(0.90)
    assert m["7018"]["max_time_minute"] == 65  # 0 j + 01:05
    assert m["7019"]["max_hgl_m"] == pytest.approx(107.23)
    assert m["7020"]["max_hgl_m"] == pytest.approx(107.68)
    # Identifiants exacts uniquement — pas de correspondance approximative
    assert "70180" not in m and "701" not in m


def test_parse_node_depth_summary_absente():
    """Section absente → statut explicite, aucune valeur fabriquée."""
    kpis = analyser_rapport_swmm_impl(rpt_text="[TITLE]\nTest\n", meta={})
    assert kpis["node_depth_maxima"] == {}
    assert kpis["node_depth_maxima_status"] == "absent"


def test_parse_flooding_temps_et_volume():
    """Node Flooding Summary → heure du max (minute), volume, statut flooded."""
    kpis = analyser_rapport_swmm_impl(rpt_text=RPT_SYNTHETIQUE, meta={})
    n = kpis["node_results"]["7018"]
    assert n["status"] == "flooded"
    assert n["peak_flood_flow_cms"] == pytest.approx(0.067)
    assert n["flood_time_minute"] == 65
    assert n["color"] == "#dc2626"


def test_couleurs_surcharge_vs_debordement():
    """Surcharge de conduite = orange ; flooded = rouge. Le rouge ne
    qualifie plus la simple mise en charge."""
    kpis = analyser_rapport_swmm_impl(rpt_text=RPT_SYNTHETIQUE, meta={})
    assert kpis["conduit_results"]["C1"]["status"] == "surcharge"
    assert kpis["conduit_results"]["C1"]["color"] == "#f97316"
    assert kpis["node_results"]["7018"]["color"] == "#dc2626"


# ---------------------------------------------------------------------------
# B. Enrichissement node_hydraulics — provenance .rpt vs .out
# ---------------------------------------------------------------------------

def _kpis_enrich():
    return {
        "timeseries": {"node_hydraulics": {
            "7018": {"invert_m": 104.699, "max_head_m": 105.603,
                     "flooding_max_m3s": 0.0},
        }},
        "node_depth_maxima": {"7018": {"max_hgl_m": 106.70, "max_depth_m": 2.0,
                                       "max_time_minute": 65,
                                       "reported_max_depth_m": 0.90}},
        "node_results": {"7018": {"status": "flooded", "hours_flooded": 0.01,
                                  "peak_flood_flow_cms": 0.067,
                                  "flood_volume_m3": 0.5,
                                  "flood_time_minute": 66}},
    }


def test_enrichir_hydraulique_provenance():
    """Les maxima .rpt sont injectés avec provenance ; les maxima .out
    sont marqués 'aux instants de rapport', jamais exhaustifs."""
    kpis = _kpis_enrich()
    enrichir_hydraulique_noeuds(kpis)
    nh = kpis["timeseries"]["node_hydraulics"]["7018"]
    # .out conservé tel quel + marqué non exhaustif
    assert nh["max_head_m"] == pytest.approx(105.603)
    assert nh["max_head_source"] == "out_report_step"
    assert nh["max_head_exhaustif"] is False
    # .rpt injecté
    assert nh["rpt_max_head_m"] == pytest.approx(106.70)
    assert nh["rpt_max_head_minute"] == 65
    assert nh["hgl_max_source"] == "rpt_node_depth_summary"
    assert nh["rpt_flood_max_m3s"] == pytest.approx(0.067)
    assert nh["rpt_flood_minute"] == 66
    assert nh["flooding_source"] == "rpt_node_flooding_summary"


def test_enrichir_hgl_et_flood_instants_distincts():
    """Le maximum HGL (.rpt, t=65) et le maximum de débordement
    (t=66) peuvent survenir à des instants différents — les deux
    horodatages sont conservés séparément, jamais fusionnés."""
    kpis = _kpis_enrich()
    enrichir_hydraulique_noeuds(kpis)
    nh = kpis["timeseries"]["node_hydraulics"]["7018"]
    assert nh["rpt_max_head_minute"] == 65
    assert nh["rpt_flood_minute"] == 66
    assert nh["rpt_max_head_minute"] != nh["rpt_flood_minute"]


def test_enrichir_sans_rpt_ne_rien_invente():
    """Sans node_depth_maxima ni node_results flooded : aucun champ
    rpt_* n'est créé — dégradation explicite, pas d'estimation."""
    kpis = {"timeseries": {"node_hydraulics": {"7018": {"max_head_m": 105.0}}},
            "node_depth_maxima": {}, "node_results": {}}
    enrichir_hydraulique_noeuds(kpis)
    nh = kpis["timeseries"]["node_hydraulics"]["7018"]
    assert "rpt_max_head_m" not in nh
    assert "rpt_flood_max_m3s" not in nh
    assert nh["max_head_exhaustif"] is False


# ---------------------------------------------------------------------------
# C. Endpoint profil — fixture (même GPKG de référence que P0.2)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def ctx_p0():
    if not GPKG_TEST.exists():
        pytest.skip("GeoPackage de référence absent")
    db = SessionLocal()
    sfx = uuid.uuid4().hex[:8]
    org = Organization(id=f"org_p0_{sfx}", name="Org P0", slug=f"org-p0-{sfx}")
    proj = Project(id=f"proj_p0_{sfx}", org_id=org.id, name="Projet P0",
                   source_gpkg_key=str(GPKG_TEST.resolve()), gpkg_version_id=None,
                   is_archived=False)
    db.add_all([org, proj])
    db.commit()
    yield {"db": db, "org": org, "proj": proj,
           "tenant": SimpleNamespace(org_id=org.id)}
    db.delete(proj)
    db.delete(org)
    db.commit()
    db.close()


def _sim_data_p0(node_hydraulics, node_results=None):
    return {
        "node_results": node_results or {},
        "conduit_results": {"C1": {"u_node": "2674", "d_node": "2672",
                                   "flow_ratio": 0.4, "depth_ratio": 0.3,
                                   "status": "normal", "color": "#10b981"}},
        "meta": {"cluster_id": 1, "cluster_nom": "Bassin test",
                 "bbox": [3.0, 36.0, 3.1, 36.1], "junctions_count": 5,
                 "conduits_count": 4},
        "inp_content": ("[TITLE]\nTest P0\n[JUNCTIONS]\n"
                        "2674 0.0 2.0 0.0 0.0 0.0\n"
                        "2672 0.0 2.0 0.0 0.0 0.0\n"),
        "timeseries": {"status": "SUCCESS", "steps": [],
                       "node_hydraulics": node_hydraulics},
    }


def _creer_sim(db, ctx, data, suffix=""):
    sim_id = f"sim_p0_{uuid.uuid4().hex[:8]}{suffix}"
    fjson = Path(tempfile.mkdtemp()) / f"{sim_id}.json"
    fjson.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    sim = Simulation(id=sim_id, org_id=ctx["org"].id, project_id=ctx["proj"].id,
                     name=f"sim_p0{suffix}", status="completed",
                     scenario_pluie="pluie_decennale", duree_heures=4.0,
                     results_s3_key=str(fjson.resolve()), summary_kpis={})
    db.add(sim)
    db.commit()
    return sim


def _nh_p0(head_out=105.6, invert=104.699, head_rpt=None,
           flood_out=0.0, flood_rpt=None, flood_min=None, flood_vol=None):
    nh = {
        "invert_m": invert,
        "max_head_m": head_out,
        "max_head_minute": 65,
        "max_depth_m": round(max(0.0, head_out - invert), 4),
        "flooding_max_m3s": flood_out,
        "heads": [[0, head_out - 0.1], [65, head_out]],
        "floods": [[65, flood_out]] if flood_out else [],
    }
    if head_rpt is not None:
        nh["rpt_max_head_m"] = head_rpt
        nh["rpt_max_head_minute"] = 65
        nh["hgl_max_source"] = "rpt_node_depth_summary"
    if flood_rpt is not None:
        nh["rpt_flood_max_m3s"] = flood_rpt
        nh["rpt_flood_minute"] = flood_min
        nh["rpt_flood_volume_m3"] = flood_vol
        nh["flooding_source"] = "rpt_node_flooding_summary"
    return nh


def _seg(res, nid):
    return {s["node_id"]: s for s in res["segments"]}[nid]


# ---------------------------------------------------------------------------
# D. Profil — maxima .rpt prioritaires, débordement confirmé, MNT absent
# ---------------------------------------------------------------------------

def test_profil_base_max_utilise_maximum_rpt(ctx_p0):
    """base='max' : z_hgl = maximum .rpt (pas de routage) quand disponible,
    PAS le maximum .out aux instants de rapport. Provenance exposée."""
    db, ctx = ctx_p0["db"], ctx_p0
    # Cas réel 7018 : .out max=105.603, .rpt max=106.70
    nh = {"2674": _nh_p0(head_out=105.603, invert=104.699, head_rpt=106.70)}
    sim = _creer_sim(db, ctx, _sim_data_p0(nh), suffix="_rpt")
    try:
        res = get_profil_en_long(node_amont="2674", node_aval="2672",
                                 db=db, tenant=ctx["tenant"])
        seg = _seg(res, "2674")
        assert seg["z_hgl"] == pytest.approx(106.70, abs=0.01)
        assert seg["hgl_source"] == "rpt_max_head"
        assert res["hgl_source"] == "swmm_rpt_max_head"
        assert "raport SWMM" in res["hgl_base_label"] or "rapport SWMM" in res["hgl_base_label"]
    finally:
        db.delete(sim)
        db.commit()


def test_profil_debordement_rpt_out_zero(ctx_p0):
    """Cas réel 7018 : FLOODING_LOSSES .out = 0 (REPORT_STEP 60 s) mais
    .rpt confirme 0.067 m³/s → régime débordement, message honnête,
    JAMAIS « HGL ≥ Terrain » sans terrain vérifié."""
    db, ctx = ctx_p0["db"], ctx_p0
    nh = {"2674": _nh_p0(head_out=105.603, invert=104.699, head_rpt=106.70,
                         flood_out=0.0, flood_rpt=0.067, flood_min=65, flood_vol=0.4)}
    nr = {"2674": {"status": "flooded", "hours_flooded": 0.01,
                   "peak_flood_flow_cms": 0.067, "flood_volume_m3": 0.4,
                   "color": "#dc2626"}}
    sim = _creer_sim(db, ctx, _sim_data_p0(nh, nr), suffix="_flood_rpt")
    try:
        res = get_profil_en_long(node_amont="2674", node_aval="2672",
                                 db=db, tenant=ctx["tenant"])
        seg = _seg(res, "2674")
        assert seg["hgl_regime"] == "debordement"
        assert seg["flooding_m3s"] == pytest.approx(0.067)
        assert seg["node_status"] == "flooded"
        assert seg["node_color"] == "#dc2626"
        # Message d'alerte : débordement confirmé, pas de affirmation
        # « HGL ≥ Terrain » (aucun terrain vérifié dans le GPKG).
        al = [a for a in res["alertes"] if a["node"] == "2674"
              and a["type"] == "debordement"]
        assert al, "aucune alerte débordement émise"
        assert "Terrain" not in al[0]["message"]
        assert "terrain" not in al[0]["observations"].lower().replace(
            "terrain naturel", "") or "sommet" in al[0]["observations"]
        assert "0.067" in al[0]["observations"]
        assert "sommet du regard" in al[0]["observations"]
        # Libellés P0-finalisation : référence de charge explicite et
        # écart HGL/sommet distinct — jamais « charge au-dessus voûte ».
        assert "génératrice supérieure de la conduite sortante" in al[0]["observations"]
        assert "charge au-dessus voûte" not in al[0]["observations"]
        assert "Écart HGL / sommet du regard :" in al[0]["observations"]
    finally:
        db.delete(sim)
        db.commit()


def test_profil_surcharge_seule_pas_debordement(ctx_p0):
    """Surcharge (HGL > génératrice, sans perte) → jamais débordement,
    même si le .rpt qualifie le nœud 'surcharged'."""
    db, ctx = ctx_p0["db"], ctx_p0
    # Sonde : génératrice supérieure réelle du tronçon
    sim_probe = _creer_sim(db, ctx, _sim_data_p0(
        {"2674": _nh_p0(head_out=104.8, invert=104.699)}), suffix="_probe")
    try:
        res_probe = get_profil_en_long(node_amont="2674", node_aval="2672",
                                       db=db, tenant=ctx["tenant"])
        z_gs = _seg(res_probe, "2674")["z_gen_superieure"]
        z_sommet = _seg(res_probe, "2674")["z_sommet_regard"]
    finally:
        db.delete(sim_probe)
        db.commit()
    head = z_gs + 0.2
    assert head < z_sommet
    nh = {"2674": _nh_p0(head_out=head, invert=104.699)}
    nr = {"2674": {"status": "surcharged", "hours_surcharged": 0.09,
                   "color": "#f97316"}}
    sim = _creer_sim(db, ctx, _sim_data_p0(nh, nr), suffix="_surch")
    try:
        res = get_profil_en_long(node_amont="2674", node_aval="2672",
                                 db=db, tenant=ctx["tenant"])
        seg = _seg(res, "2674")
        # head=105.4 > gs (104.699+0.6=105.299) → surcharge ; < sommet 106.699
        assert seg["hgl_regime"] == "surcharge"
        assert seg["flooding_m3s"] == 0.0
        assert not any(a["type"] == "debordement" for a in res["alertes"])
        assert any(a["type"] == "surcharge" for a in res["alertes"])
    finally:
        db.delete(sim)
        db.commit()


def test_profil_instant_ne_melange_pas_statut_global(ctx_p0):
    """base='instant' : un nœud 'flooded' dans le .rpt (max global) ne
    doit PAS être présenté comme débordé à l'instant affiché — alerte
    distincte avec fenêtre connue."""
    db, ctx = ctx_p0["db"], ctx_p0
    nh = {"2674": _nh_p0(head_out=105.2, invert=104.699, head_rpt=106.70,
                         flood_out=0.0, flood_rpt=0.067, flood_min=65, flood_vol=0.4)}
    nr = {"2674": {"status": "flooded", "hours_flooded": 0.01,
                   "peak_flood_flow_cms": 0.067, "flood_volume_m3": 0.4,
                   "flood_time_minute": 65, "color": "#dc2626"}}
    sim = _creer_sim(db, ctx, _sim_data_p0(nh, nr), suffix="_inst")
    try:
        res = get_profil_en_long(node_amont="2674", node_aval="2672",
                                 base="instant", instant_minute=0,
                                 db=db, tenant=ctx["tenant"])
        seg = _seg(res, "2674")
        assert seg["hgl_regime"] != "debordement"
        assert seg["flooding_m3s"] == 0.0
        # Alerte distincte, jamais présentée comme état instantané
        infos = [a for a in res["alertes"] if a["node"] == "2674"
                 and a["type"] == "info"]
        assert infos and "instant affiché" in infos[0]["message"]
        assert not any(a["type"] == "debordement" for a in res["alertes"])
    finally:
        db.delete(sim)
        db.commit()


def test_profil_mnt_absent_sommet_expose(ctx_p0):
    """Aucun terrain vérifié → z_terrain=None partout,
    terrain_disponible=False, sommet de regard SWMM exposé."""
    db, ctx = ctx_p0["db"], ctx_p0
    nh = {"2674": _nh_p0(head_out=105.0, invert=104.699)}
    sim = _creer_sim(db, ctx, _sim_data_p0(nh), suffix="_mnt")
    try:
        res = get_profil_en_long(node_amont="2674", node_aval="2672",
                                 db=db, tenant=ctx["tenant"])
        assert res["terrain_disponible"] is False
        for s in res["segments"]:
            assert s["z_terrain"] is None
            assert s["terrain_reel"] is False
        seg = _seg(res, "2674")
        assert seg["z_sommet_regard"] == pytest.approx(106.699, abs=0.01)
    finally:
        db.delete(sim)
        db.commit()


def test_profil_noeud_non_simule_pas_heuristique(ctx_p0):
    """Nœud du chemin absent de node_hydraulics : aucune cote radier
    heuristique (plus de 100 - distance×0.01). z_radier=None sauf si une
    source réelle (GPKG/.out) existe."""
    db, ctx = ctx_p0["db"], ctx_p0
    # Seul 2674 est « simulé » ; les nœuds intermédiaires du chemin ne le sont pas.
    nh = {"2674": _nh_p0(head_out=105.0, invert=104.699)}
    sim = _creer_sim(db, ctx, _sim_data_p0(nh), suffix="_nosim")
    try:
        res = get_profil_en_long(node_amont="2674", node_aval="2672",
                                 db=db, tenant=ctx["tenant"])
        for s in res["segments"]:
            if not s["simule"]:
                assert s["z_hgl"] is None
                # z_radier ne peut venir que d'une source réelle ; le GPKG
                # de référence n'a ni COTRAD ni terrain → None attendu.
                assert s["z_radier"] is None
                assert s["z_radier"] != pytest.approx(100.0 - s["distance_m"] * 0.01)
    finally:
        db.delete(sim)
        db.commit()


def test_profil_sans_rpt_degradation_propre(ctx_p0):
    """Simulation sans enrichissement .rpt : profil fonctionnel sur les
    maxima .out, provenance 'swmm_out_max_head', pas de champ rpt."""
    db, ctx = ctx_p0["db"], ctx_p0
    nh = {"2674": _nh_p0(head_out=105.5, invert=104.699)}
    sim = _creer_sim(db, ctx, _sim_data_p0(nh), suffix="_legacy")
    try:
        res = get_profil_en_long(node_amont="2674", node_aval="2672",
                                 db=db, tenant=ctx["tenant"])
        seg = _seg(res, "2674")
        assert seg["z_hgl"] == pytest.approx(105.5, abs=0.01)
        assert seg["hgl_source"] == "swmm_out_max_head"
        assert res["hgl_source"] == "swmm_out_max_head"
        assert "rpt_max_head_m" not in nh["2674"]
    finally:
        db.delete(sim)
        db.commit()
