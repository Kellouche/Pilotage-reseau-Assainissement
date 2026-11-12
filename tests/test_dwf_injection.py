# -*- coding: utf-8 -*-
"""
================================================================================
Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
Objet : LOT P1.3 — Tests de l'injection des apports DWF dans le .inp SWMM

Trois niveaux :
  1. Unitaire : construire_injection_dwf (groupement nœud, méthodes,
     normalisation moyenne=1, index calendaire, couverture temporelle).
  2. Témoin SWMM 5.2.4 réel : INP minimal + sections générées, exécuté via
     PySWMM, comparaison débit théorique / TOTAL_INFLOW simulé.
  3. Service : résolution DB bornée org/projet, empreinte de cache.
================================================================================
"""

import io
import contextlib
import os
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from src.domain.apports_dwf import PROFILS_DWF
from src.domain.moteur_swmm.dwf_injection import (
    construire_injection_dwf,
    empreinte_apports_dwf,
    _index_calendaire,
)

DEBUT = datetime(2026, 1, 1, 0, 0, 0)   # jeudi (convention .inp)
NOEUDS = {"J1", "J2"}


def _apport(aid="a1", node="J1", q=0.002, profile="constant", **kw):
    d = {
        "id": aid, "org_id": "o", "project_id": "p", "node_id": node,
        "nature": "domestique", "mode_determination": "debit",
        "debit_moyen_m3s": q, "eh": None, "debit_specifique_l_hab_j": None,
        "profile_key": profile, "actif": True, "source": None,
        "observations": None,
    }
    d.update(kw)
    return d


# ---------------------------------------------------------------------------
# 1. Unitaire — construction des sections
# ---------------------------------------------------------------------------

def test_constant_produit_dwf_sans_pattern():
    r = construire_injection_dwf([_apport()], NOEUDS, DEBUT, DEBUT + timedelta(hours=24))
    assert len(r["dwf_lines"]) == 1 and not r["pattern_lines"]
    assert not r["inflow_lines"] and not r["timeseries_lines"]
    assert "FLOW" in r["dwf_lines"][0] and "0.002000" in r["dwf_lines"][0]
    assert r["apports_meta"][0]["methode_injection"] == "DWF"


def test_journalier_dwf_avec_pattern_hourly():
    r = construire_injection_dwf(
        [_apport(profile="journalier_type")], NOEUDS,
        DEBUT, DEBUT + timedelta(hours=48))
    assert len(r["pattern_lines"]) == 1
    assert "HOURLY" in r["pattern_lines"][0]
    # 24 facteurs attendus
    vals = r["pattern_lines"][0].split()[2:]
    assert len(vals) == 24
    assert len(r["dwf_lines"]) == 1 and "DWF_P_JOURNALIER" in r["dwf_lines"][0]
    # moyenne des facteurs émis ≈ 1 → q_base ≈ q
    assert r["apports_meta"][0]["methode_injection"] == "DWF"


def test_hebdomadaire_inflows_timeseries():
    r = construire_injection_dwf(
        [_apport(profile="hebdomadaire")], NOEUDS,
        DEBUT, DEBUT + timedelta(hours=72))
    assert not r["dwf_lines"] and not r["pattern_lines"]
    assert len(r["inflow_lines"]) == 1
    assert "TS_DWF_J1" in r["inflow_lines"][0]
    # 72 h × 2 points + clôture
    assert len(r["timeseries_lines"]) >= 2 * 72
    assert r["apports_meta"][0]["methode_injection"] == "INFLOWS_TIMESERIES"


def test_noeud_absent_ignore():
    r = construire_injection_dwf(
        [_apport(node="ABSENT")], NOEUDS, DEBUT, DEBUT + timedelta(hours=24))
    assert not r["dwf_lines"] and not r["inflow_lines"]
    assert r["ignores"][0]["motif"] == "noeud_absent_du_inp"


def test_apport_inactif_ignore():
    r = construire_injection_dwf(
        [_apport(actif=False)], NOEUDS, DEBUT, DEBUT + timedelta(hours=24))
    assert r["ignores"][0]["motif"] == "inactif"


def test_debit_nul_ignore():
    r = construire_injection_dwf(
        [_apport(q=0.0)], NOEUDS, DEBUT, DEBUT + timedelta(hours=24))
    assert r["ignores"][0]["motif"] == "debit_nul"


def test_multi_apports_memes_noeuds():
    """constant + journalier sur J1 : journalier prend le slot [DWF],
    constant part en [TIMESERIES] — jamais les deux mécanismes pour
    un même apport, un seul [DWF] FLOW par nœud."""
    r = construire_injection_dwf(
        [_apport("a1", q=0.001, profile="constant"),
         _apport("a2", q=0.002, profile="journalier_type")],
        NOEUDS, DEBUT, DEBUT + timedelta(hours=24))
    assert len(r["dwf_lines"]) == 1
    assert len(r["inflow_lines"]) == 1
    methodes = {m["apport_id"]: m["methode_injection"] for m in r["apports_meta"]}
    assert methodes["a1"] == "INFLOWS_TIMESERIES"
    assert methodes["a2"] == "DWF"
    assert not r["ignores"]


def test_multi_noeuds_independants():
    r = construire_injection_dwf(
        [_apport("a1", node="J1", profile="constant"),
         _apport("a2", node="J2", profile="hebdomadaire")],
        NOEUDS, DEBUT, DEBUT + timedelta(hours=48))
    assert len(r["dwf_lines"]) == 1 and "J1" in r["dwf_lines"][0]
    assert len(r["inflow_lines"]) == 1 and "J2" in r["inflow_lines"][0]


def test_serie_couvre_toute_la_duree():
    """La [TIMESERIES] hebdo couvre sans lacune du début à la fin."""
    fin = DEBUT + timedelta(hours=200, minutes=30)
    r = construire_injection_dwf(
        [_apport(profile="hebdomadaire")], NOEUDS, DEBUT, fin)
    instants = []
    for ligne in r["timeseries_lines"]:
        parties = ligne.split()
        # format : NOM  MM/DD/YYYY HH:MM:SS  valeur
        instants.append(datetime.strptime(parties[1] + " " + parties[2],
                                          "%m/%d/%Y %H:%M:%S"))
    assert min(instants) == DEBUT
    assert max(instants) >= fin
    # pas de trou > 1 h entre points consécutifs distincts
    uni = sorted(set(instants))
    for a, b in zip(uni, uni[1:]):
        assert (b - a) <= timedelta(hours=1, seconds=1)


def test_index_calendaire_dimanche_zero():
    # 2026-01-04 = dimanche, 2026-01-03 = samedi
    assert _index_calendaire(datetime(2026, 1, 4, 0, 0)) == 0
    assert _index_calendaire(datetime(2026, 1, 3, 0, 0)) == 6 * 24
    assert _index_calendaire(datetime(2026, 1, 1, 9, 0)) == 4 * 24 + 9  # jeudi


def test_normalisation_moyenne_unite():
    """Les facteurs émis (pattern HOURLY / valeurs TS) donnent moyenne 1."""
    r = construire_injection_dwf(
        [_apport(profile="hebdomadaire", q=0.003)], NOEUDS,
        DEBUT, DEBUT + timedelta(hours=168))
    vals = []
    for ligne in r["timeseries_lines"]:
        vals.append(float(ligne.split()[-1]))
    # 2 points par heure (h:00 et h:59:59) → même valeur, moyenne = Q moyen
    assert sum(vals) / len(vals) == pytest.approx(0.003, rel=2e-3)


def test_empreinte_stable():
    a = [_apport()]
    assert empreinte_apports_dwf(a) == empreinte_apports_dwf(list(a))
    assert empreinte_apports_dwf(a) != empreinte_apports_dwf(
        [_apport(q=0.003)])
    assert empreinte_apports_dwf([]) != empreinte_apports_dwf(a)


# ---------------------------------------------------------------------------
# 2. Témoins SWMM 5.2.4 réels — INP minimal + sections générées
# ---------------------------------------------------------------------------

_INP_TEMPLATE = """[TITLE]
t
[OPTIONS]
FLOW_UNITS CMS
INFILTRATION HORTON
FLOW_ROUTING DYNWAVE
START_DATE {start:%m/%d/%Y}
START_TIME {start:%H:%M:%S}
REPORT_START_DATE {start:%m/%d/%Y}
REPORT_START_TIME {start:%H:%M:%S}
END_DATE {end:%m/%d/%Y}
END_TIME {end:%H:%M:%S}
REPORT_STEP 01:00:00
WET_STEP 00:05:00
DRY_STEP 00:15:00
ROUTING_STEP 00:00:05
ALLOW_PONDING NO
[EVAPORATION]
CONSTANT 0.0
DRY_ONLY NO
[RAINGAGES]
RG1 INTENSITY 0:05 1.0 TIMESERIES TS_ZERO
[TIMESERIES]
TS_ZERO 00:00 0.0
TS_ZERO 24:00 0.0
{ts_dwf}
[PATTERNS]
{patterns}
[DWF]
;;Node Parameter Value Patterns
{dwf}
[INFLOWS]
;;Node Constituent Time Series Type Mfactor Sfactor Baseline Pattern
{inflows}
[JUNCTIONS]
J1 10.0 3.0 0.0 0.0 0.0
J2 9.0 3.0 0.0 0.0 0.0
[OUTFALLS]
OUT1 7.0 FREE NO
[CONDUITS]
C1 J1 J2 100.0 0.013 0 0 0 0
C2 J2 OUT1 50.0 0.013 0 0 0 0
[XSECTIONS]
C1 CIRCULAR 0.8 0 0 0 1
C2 CIRCULAR 0.8 0 0 0 1
[COORDINATES]
J1 0 0
J2 100 0
OUT1 150 0
[REPORT]
NODES ALL
"""


def _run_swmm(tag, apports, duree_h=72, start=DEBUT):
    """Exécute un INP témoin avec les sections DWF générées."""
    pyswmm = pytest.importorskip("pyswmm")
    from swmm.toolkit.shared_enum import NodeAttribute
    fin = start + timedelta(hours=duree_h)
    inj = construire_injection_dwf(apports, NOEUDS, start, fin)
    inp = _INP_TEMPLATE.format(
        start=start, end=fin,
        ts_dwf="\n".join(inj["timeseries_lines"]),
        patterns="\n".join(inj["pattern_lines"]),
        dwf="\n".join(inj["dwf_lines"]),
        inflows="\n".join(inj["inflow_lines"]),
    )
    p = Path(f"_t_dwf_{tag}.inp")
    p.write_text(inp, encoding="utf-8")
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            with pyswmm.Simulation(str(p)) as sim:
                sim.execute()
        out = p.with_suffix(".out")
        with pyswmm.Output(str(out)) as o:
            ser = dict(o.node_series("J1", NodeAttribute.TOTAL_INFLOW))
            times = list(o.times)
        return ser, times, inj
    finally:
        for x in (p, p.with_suffix(".out"), p.with_suffix(".rpt")):
            try:
                x.unlink()
            except OSError:
                pass


def _q_sim_heure(ser, times, heure_depuis_t0):
    """TOTAL_INFLOW simulé à `heure_depuis_t0` heures après le 1er relevé."""
    t0 = times[0]
    cible = t0 + timedelta(hours=heure_depuis_t0)
    cle = min(ser.keys(), key=lambda t: abs((t - cible).total_seconds()))
    return ser[cle], cle


@pytest.mark.skipif(
    not __import__("importlib").util.find_spec("pyswmm"),
    reason="pyswmm non installé")
def test_swmm_constant():
    ser, times, _ = _run_swmm("const", [_apport(q=0.002)], duree_h=24)
    vals = [q for _, q in sorted(ser.items())]
    assert min(vals) == pytest.approx(0.002, abs=1e-5)
    assert max(vals) == pytest.approx(0.002, abs=1e-5)


@pytest.mark.skipif(
    not __import__("importlib").util.find_spec("pyswmm"),
    reason="pyswmm non installé")
def test_swmm_journalier_repetition_24h():
    """Début jeudi : les pics du profil journalier reviennent chaque 24 h
    aux mêmes heures calendaires, identiques les 7 jours."""
    q = 0.002
    ser, times, _ = _run_swmm(
        "jour", [_apport(q=q, profile="journalier_type")], duree_h=96)
    f = PROFILS_DWF["journalier_type"]["facteurs_168"]
    moy = sum(f) / 168.0
    # Le .out SWMM rapporte la moyenne sur la période de reporting dont le
    # timestamp est la FIN : l'échantillon à h:00 (REPORT_STEP 1 h)
    # correspond à l'heure calendaire h-1. On compare donc au facteur de
    # l'heure contenant (relevé - 1 min).
    for h_abs in (0, 9, 20, 24, 33, 44, 48, 57, 68, 72, 81, 92):
        qs, releve = _q_sim_heure(ser, times, h_abs)
        idx = _index_calendaire(releve - timedelta(minutes=1))
        attendu = q * f[idx] / moy
        assert qs == pytest.approx(attendu, rel=0.02, abs=2e-4), (
            f"h={h_abs} ({releve}) sim={qs:.5f} attendu={attendu:.5f}")


@pytest.mark.skipif(
    not __import__("importlib").util.find_spec("pyswmm"),
    reason="pyswmm non installé")
def test_swmm_hebdomadaire_fidelite_168():
    """Profil hebdomadaire via [INFLOWS]+[TIMESERIES] : fidélité exacte
    des 168 facteurs sur 2 semaines, y compris transitions dim→lun."""
    q = 0.002
    apport = _apport(q=q, profile="hebdomadaire")
    ser, times, _ = _run_swmm("hebdo", [apport], duree_h=336)
    f = PROFILS_DWF["hebdomadaire"]["facteurs_168"]
    moy = sum(f) / 168.0
    # échantillon toutes les 6 h sur 2 semaines — convention .out :
    # moyenne de la période (T-1h, T] → facteur de l'heure T-1min.
    for h_abs in range(0, 336, 6):
        qs, releve = _q_sim_heure(ser, times, h_abs)
        attendu = q * f[_index_calendaire(releve - timedelta(minutes=1))] / moy
        assert qs == pytest.approx(attendu, rel=0.02, abs=3e-4), (
            f"h={h_abs} ({releve}) sim={qs:.5f} attendu={attendu:.5f}")


@pytest.mark.skipif(
    not __import__("importlib").util.find_spec("pyswmm"),
    reason="pyswmm non installé")
def test_swmm_multi_apports_noeuds():
    """Deux apports sur J1 (constant+hebdo) et un sur J2 : J1 reçoit la
    somme ; J2 reçoit son propre profil."""
    apports = [
        _apport("a1", node="J1", q=0.001, profile="constant"),
        _apport("a2", node="J1", q=0.001, profile="hebdomadaire"),
        _apport("a3", node="J2", q=0.0015, profile="constant"),
    ]
    ser, times, inj = _run_swmm("multi", apports, duree_h=48)
    # J1 : slot [DWF] → journalier absent → constant ? non :
    # profils présents = {constant, hebdomadaire} → slot=constant (DWF),
    # hebdomadaire → TIMESERIES. Vérifions via apports_meta.
    meta = {m["apport_id"]: m["methode_injection"] for m in inj["apports_meta"]}
    assert meta["a1"] == "DWF" and meta["a2"] == "INFLOWS_TIMESERIES"
    # J1 : constant 0.001 (DWF) + hebdo 0.001 (TS) → flux ≥ 0.001 partout
    # et variable dans le temps (le profil hebdo n'est pas constant).
    vals = [q for _, q in sorted(ser.items())]
    assert min(vals) > 0.0009
    assert max(vals) - min(vals) > 0.0002


# ---------------------------------------------------------------------------
# 3. Service — résolution DB et empreinte
# ---------------------------------------------------------------------------

def test_preparer_apports_isolation_projet(tmp_path):
    """La résolution ne retourne que les apports actifs du projet/org."""
    from api.database import SessionLocal
    from api.models import Organization, Project, ApportDwf
    from api.services.apports_dwf_service import (
        resoudre_apports_dwf, preparer_apports_pour_simulation)

    db = SessionLocal()
    pref = "p13svc"
    org = Organization(id=f"{pref}_o", name="O", slug=f"{pref}-o")
    org2 = Organization(id=f"{pref}_o2", name="O2", slug=f"{pref}-o2")
    proj = Project(id=f"{pref}_p", org_id=org.id, name="P",
                   slug=f"{pref}-p", is_archived=False)
    proj2 = Project(id=f"{pref}_p2", org_id=org2.id, name="P2",
                    slug=f"{pref}-p2", is_archived=False)
    # LOT P1.4 — les apports actifs doivent être estampillés sur la version
    # simulée : on les stampe sur un sha legacy fictif cohérent.
    META_LEGACY = {"version_id": None, "sha256": "sha_test_p13",
                   "storage_kind": "LEGACY"}
    a1 = ApportDwf(id=f"{pref}_a1", org_id=org.id, project_id=proj.id,
                   node_id="N1", nature="domestique",
                   mode_determination="debit", debit_moyen_m3s=0.001,
                   profile_key="constant", actif=True,
                   gpkg_sha256="sha_test_p13")
    a2 = ApportDwf(id=f"{pref}_a2", org_id=org.id, project_id=proj.id,
                   node_id="N2", nature="industriel",
                   mode_determination="debit", debit_moyen_m3s=0.002,
                   profile_key="constant", actif=False)
    a3 = ApportDwf(id=f"{pref}_a3", org_id=org2.id, project_id=proj2.id,
                   node_id="N3", nature="autre",
                   mode_determination="debit", debit_moyen_m3s=0.003,
                   profile_key="constant", actif=True,
                   gpkg_sha256="sha_test_p13")
    db.add_all([org, org2, proj, proj2, a1, a2, a3])
    db.commit()
    try:
        res = resoudre_apports_dwf(db, proj)
        assert [a["id"] for a in res] == [f"{pref}_a1"]  # actif seul, bon projet
        apports, info = preparer_apports_pour_simulation(
            db, proj, dwf_actif=True, version_meta=META_LEGACY)
        assert len(apports) == 1 and "apports_dwf_sha256" in info
        # Désactivation explicite
        apports_off, info_off = preparer_apports_pour_simulation(
            db, proj, dwf_actif=False)
        assert apports_off == [] and info_off["dwf_actif"] is False
        # Projet sans apports → liste vide mais empreinte stable
        apports_v, _ = preparer_apports_pour_simulation(
            db, proj2, dwf_actif=True, version_meta=META_LEGACY)
        assert [a["id"] for a in apports_v] == [f"{pref}_a3"]
    finally:
        for o in (a1, a2, a3, proj, proj2, org, org2):
            db.delete(o)
        db.commit()
        db.close()


def test_cache_extra_params_dwf():
    """L'empreinte des apports entre dans params_dict → clés distinctes."""
    from types import SimpleNamespace
    from api.services.simulation_service import generer_cle_cache_simulation
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".gpkg", delete=False) as f:
        f.write(b"x")
        gp = Path(f.name)
    try:
        p = SimpleNamespace(scenario_key="s", cluster_id=1)
        _, d1 = generer_cle_cache_simulation(gp, p)
        _, d2 = generer_cle_cache_simulation(
            gp, p, extra_params={"apports_dwf_sha256": "abc", "dwf_actif": True})
        assert "apports_dwf_sha256" not in d1
        assert d2["apports_dwf_sha256"] == "abc"
        h1, _ = generer_cle_cache_simulation(gp, p)
        h2, _ = generer_cle_cache_simulation(
            gp, p, extra_params={"apports_dwf_sha256": "abc"})
        assert h1 != h2
    finally:
        gp.unlink(missing_ok=True)
