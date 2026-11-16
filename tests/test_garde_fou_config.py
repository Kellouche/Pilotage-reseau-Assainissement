# -*- coding: utf-8 -*-
"""
Tests du paramétrage garde-fou par projet : fusion de configuration,
seuils applicables par l'agent et filtrage de la config persistée.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from api.services.garde_fou_service import (
    CHECKS_ACTIFS_DEFAUT,
    SEUILS_CATALOGUE,
    config_bare,
    config_effective,
    seuils_par_defaut,
)
from src.domain.agents_expertise.agent_hydraulicien_garde_fou import (
    AgentHydraulicienGardeFou,
)


def _inp_avec_junctions(n=12, elev=50.0, maxdepth=2.0):
    lignes = []
    for i in range(n):
        lignes.append(f"J{i} {elev} {maxdepth} 0 0 0")
    return "[JUNCTIONS]\n" + "\n".join(lignes) + "\n[CONDUITS]\n"


# ---------------------------------------------------------------------------
# config_effective — fusion défauts ← preset ← profil ← surcharges
# ---------------------------------------------------------------------------

def test_config_effective_defauts():
    cfg = config_effective(None)
    assert cfg["preset"] == "standard"
    assert cfg["seuils"]["continuite_pct"] == 5.0
    assert cfg["checks_actives"]["RESEAU_PLAT"] is True
    assert cfg["source"] == "defauts"


def test_config_effective_preset_strict():
    cfg = config_effective({"preset": "strict"})
    assert cfg["seuils"]["continuite_pct"] == 2.0
    assert cfg["seuils"]["inondation_pct"] == 0.60


def test_config_effective_profil_puis_surcharge():
    # profil 'neuf' impose continuite 2.0, puis surcharge utilisateur 7.5
    cfg = config_effective({
        "preset": "standard",
        "profil_reseau": "neuf",
        "seuils": {"continuite_pct": 7.5},
    })
    assert cfg["seuils"]["continuite_pct"] == 7.5
    assert cfg["seuils"]["pente_nulle_m"] == 0.010  # du profil


def test_config_effective_cle_inconnue_ignoree():
    cfg = config_effective({"seuils": {"cle_inconnue": 42, "continuite_pct": 3.0}})
    assert "cle_inconnue" not in cfg["seuils"]
    assert cfg["seuils"]["continuite_pct"] == 3.0


def test_config_bare_filtre_et_horodate():
    brut = config_bare({
        "preset": "strict",
        "profil_reseau": "inconnu",
        "seuils": {"continuite_pct": 3.0, "hack": "x"},
        "checks_actives": {"RESEAU_PLAT": False, "FAUX": True},
        "bidon": 123,
    })
    assert brut["preset"] == "strict"
    assert "profil_reseau" not in brut
    assert brut["seuils"] == {"continuite_pct": 3.0}
    assert brut["checks_actives"] == {"RESEAU_PLAT": False}
    assert "bidon" not in brut
    assert "maj_le" in brut


# ---------------------------------------------------------------------------
# Agent — seuils et contrôles désactivables
# ---------------------------------------------------------------------------

def test_agent_seuil_personnalise():
    """Un seuil resserré (continuite 0.5 %) déclenche là où le défaut (5 %) non."""
    sim = {"inp_content": _inp_avec_junctions(), "rpt_content": "",
           "meta": {}, "routing_continuity_error_pct": 3.0}
    agent = AgentHydraulicienGardeFou()
    # Défaut : 3 % < 5 % → pas d'anomalie bilan
    r_defaut = agent.analyser(dict(sim))
    assert not any(a["code"] == "BILAN_MASSE_DEGRADE" for a in r_defaut["anomalies"])
    # Config stricte : 3 % > 2 % → anomalie
    r_strict = agent.analyser(dict(sim), config={"preset": "strict"})
    assert any(a["code"] == "BILAN_MASSE_DEGRADE" for a in r_strict["anomalies"])
    # Config via meta (chemin moteur)
    sim_meta = dict(sim)
    sim_meta["meta"] = dict(sim["meta"], garde_fou_config={"preset": "strict"})
    r_meta = agent.analyser(sim_meta)
    assert r_meta["config_garde_fou"]["preset"] == "strict"
    assert any(a["code"] == "BILAN_MASSE_DEGRADE" for a in r_meta["anomalies"])


def test_agent_check_desactive():
    """Un contrôle désactivé ne produit plus son anomalie."""
    # 12 jonctions à la même cote → RESEAU_PLAT (critique)
    sim = {"inp_content": _inp_avec_junctions(elev=50.0), "rpt_content": "",
           "meta": {}}
    agent = AgentHydraulicienGardeFou()
    r_on = agent.analyser(dict(sim))
    assert r_on["fiabilite_modele"] == "DEGRADE"
    assert any(a["code"] == "RESEAU_PLAT" for a in r_on["anomalies"])

    r_off = agent.analyser(dict(sim), config={
        "checks_actives": {"RESEAU_PLAT": False,
                           "NOEUD_SANS_EXUTOIRE": False,
                           "PENTE_NULLE": False,
                           "BILAN_MASSE_DEGRADE": False,
                           "INONDATION_GENERALISEE": False,
                           "RATIO_HYDRAULIQUE_ABERRANT": False,
                           "ALTIMETRIE_SYNTHETIQUE": False,
                           "ALTIMETRIE_CONFONDUE_PROFONDEUR": False,
                           "SENTINELLE_COTE_DEFAUT": False},
    })
    assert r_off["fiabilite_modele"] == "SAIN"
    assert r_off["nb_anomalies"] == 0


def test_agent_tracabilite_config():
    """Le verdict expose la config utilisée (preset/profil/source/seuils)."""
    sim = {"inp_content": _inp_avec_junctions(), "rpt_content": "",
           "meta": {}}
    r = AgentHydraulicienGardeFou().analyser(
        sim, config={"preset": "strict", "profil_reseau": "neuf"})
    trace = r.get("config_garde_fou")
    assert trace is not None
    assert trace["preset"] == "strict"
    assert trace["profil_reseau"] == "neuf"
    assert trace["source"] == "personnalisee"
    assert "continuite_pct" in (trace["seuils"] or {})


def test_agent_defauts_sans_config():
    """Sans config : comportement identique aux constantes de classe."""
    sim = {"inp_content": _inp_avec_junctions(), "rpt_content": "",
           "meta": {}}
    r = AgentHydraulicienGardeFou().analyser(sim)
    assert r["config_garde_fou"] is None
    assert r["fiabilite_modele"] == "DEGRADE"  # réseau plat → critique
