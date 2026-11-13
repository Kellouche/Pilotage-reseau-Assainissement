# -*- coding: utf-8 -*-
"""
================================================================================
Projet : DrainPilot 5.2 - Tests LOT P1.5.4
Objet : Restitution détaillée des apports DWF dans les résultats de
        simulation — synthèse, détail injectés/ignorés, états de provenance.

Les tests fonctionnels exécutent le VRAI JavaScript (resultats_dwf.js)
via Node.js sur des fixtures reprenant les structures réellement
persistées (result.json sync / Celery).
================================================================================
"""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

MODAL_HTML = (ROOT / "templates" / "partials" / "modal_simulation.html").read_text(encoding="utf-8")
INDEX_HTML = (ROOT / "templates" / "index.html").read_text(encoding="utf-8")
DWF_JS_PATH = ROOT / "static" / "js" / "app" / "resultats_dwf.js"
DWF_JS = DWF_JS_PATH.read_text(encoding="utf-8")
RES_AFFICHAGE_JS = (ROOT / "static" / "js" / "app" / "resultats_affichage.js").read_text(encoding="utf-8")
RES_ACTIONS_JS = (ROOT / "static" / "js" / "app" / "resultats_actions.js").read_text(encoding="utf-8")

NODE = shutil.which("node")

# ---------------------------------------------------------------------------
# Fixtures calquées sur les result.json réels persistés
# ---------------------------------------------------------------------------

APPORT_INJ_SYNC = {
    "apport_id": "a328c2aa-6153-4c04-9ddd-2101891edc4c",
    "node_id": "7018",
    "nature": "domestique",
    "debit_moyen_m3s": 0.002,
    "mode_determination": "debit",
    "eh": None,
    "debit_specifique_l_hab_j": None,
    "profile_key": "constant",
    "gpkg_version_id": "99f7b256-2abf-4b08-a744-00599e66cd9b",
    "gpkg_sha256": "aa5161d34ec7e4e286a95fc6835595619234c0a99443916ab8d4c93912e8eb64",
    "methode_injection": "DWF",
    "pattern": None,
    "q_base_m3s": 0.002,
}

APPORT_INJ_JOURNALIER = dict(
    APPORT_INJ_SYNC,
    apport_id="b1111111-1111-1111-1111-111111111111",
    node_id="7020",
    debit_moyen_m3s=0.001,
    profile_key="journalier_type",
    methode_injection="DWF",
    pattern="DWF_P_JOURNALIER",
    q_base_m3s=0.0004,  # valeur technique normalisée — ne doit JAMAIS sommer
)

APPORT_IGNORE = {
    "apport_id": "186ec201-161d-41c8-bfd5-1551ed1504ea",
    "node_id": "7019",
    "motif": "noeud_absent_du_inp",
}

RESULT_SYNC = {
    "provenance": {
        "apports_dwf": {
            "injectes": [APPORT_INJ_SYNC, dict(APPORT_INJ_SYNC, apport_id="x2", node_id="7019", debit_moyen_m3s=0.0015)],
            "ignores": [],
        }
    }
}

RESULT_CELERY = {
    "provenance": {
        "apports_dwf": {
            "injectes": [APPORT_INJ_SYNC],
            "ignores": [APPORT_IGNORE],
        }
    }
}

RESULT_VIDE = {"provenance": {"apports_dwf": {"injectes": [], "ignores": []}}}
RESULT_ABSENT = {"provenance": {"engine": "EPA SWMM"}, "meta": {"apports_dwf": []}}
RESULT_META_SEUL = {"meta": {"apports_dwf": [APPORT_INJ_SYNC], "apports_dwf_ignores": []}}
RESULT_META_VIDE = {"meta": {"apports_dwf": [], "apports_dwf_ignores": []}}


# ---------------------------------------------------------------------------
# Harnais Node : charge le vrai JS et exécute les fonctions pures
# ---------------------------------------------------------------------------

def _node_eval(expressions):
    """Exécute resultats_dwf.js dans Node et évalue des expressions.

    expressions : liste de chaînes JS, chacune devant renvoyer du JSON.
    Retourne la liste des résultats parsés.
    """
    assert NODE, "Node.js requis pour les tests fonctionnels P1.5.4"
    script = (
        "global.window = {};\n"
        + DWF_JS_PATH.read_text(encoding="utf-8")
        + "\nconst out = [];\n"
        + "\n".join(
            f"out.push(JSON.stringify({expr}));" for expr in expressions
        )
        + "\nconsole.log(JSON.stringify(out));\n"
    )
    proc = subprocess.run(
        [NODE, "-e", script],
        capture_output=True, text=True, timeout=60,
    )
    assert proc.returncode == 0, f"Node a échoué : {proc.stderr}"
    return [json.loads(line) for line in json.loads(proc.stdout.strip().splitlines()[-1])]


def _node_eval_data(data, expression):
    payload = json.dumps(data, ensure_ascii=False)
    return _node_eval([f"(function(){{ const d = {payload}; return {expression}; }})()"])[0]


# ---------------------------------------------------------------------------
# A. Contrat fichiers / intégration
# ---------------------------------------------------------------------------

def test_bloc_dans_carte_resultats():
    assert 'id="sim-dwf-resultats-box"' in MODAL_HTML
    # à l'intérieur de la carte des résultats
    assert MODAL_HTML.index('id="sim-results-card"') < MODAL_HTML.index('id="sim-dwf-resultats-box"')


def test_module_charge_avant_affichage():
    assert "/static/js/app/resultats_dwf.js" in INDEX_HTML
    assert INDEX_HTML.index("resultats_dwf.js") < INDEX_HTML.index("resultats_affichage.js")


def test_point_d_entree_sur_donnees_simulation():
    # Le bloc est alimenté par `data` de la simulation consultée
    assert "window.afficherBlocResultatsDwf(data)" in RES_AFFICHAGE_JS
    # Purge du bloc lors de la réinitialisation
    assert "sim-dwf-resultats-box" in RES_ACTIONS_JS


# ---------------------------------------------------------------------------
# B. États de provenance (tests fonctionnels sur le vrai JS)
# ---------------------------------------------------------------------------

def test_etat_provenance_absente():
    html = _node_eval_data(RESULT_ABSENT, "window.dwfConstruireHtmlBloc(d)")
    assert "DWF non tracé" in html
    assert "simulation antérieure ou état non documenté" in html
    # jamais assimilé à « DWF désactivé » ni à « aucun injecté »
    assert "désactivé" not in html.lower()
    assert "Aucun apport DWF injecté" not in html


def test_etat_listes_vides():
    html = _node_eval_data(RESULT_VIDE, "window.dwfConstruireHtmlBloc(d)")
    assert "Aucun apport DWF injecté ou enregistré" in html


def test_meta_vide_ne_declenche_pas_etat_active():
    # meta.apports_dwf=[] sans provenance → état « non tracé », pas « activé »
    html = _node_eval_data(RESULT_META_VIDE, "window.dwfConstruireHtmlBloc(d)")
    assert "DWF non tracé" in html


def test_repli_meta_quand_provenance_absente():
    html = _node_eval_data(RESULT_META_SEUL, "window.dwfConstruireHtmlBloc(d)")
    assert "Apports de temps sec (DWF)" in html
    assert "1" in html  # un injecté via meta


def test_injectes_et_ignores_restitues():
    html = _node_eval_data(RESULT_CELERY, "window.dwfConstruireHtmlBloc(d)")
    assert "Apports de temps sec (DWF)" in html
    assert "Apports injectés" in html
    assert "Apports ignorés" in html
    assert "noeud_absent_du_inp" in html  # motif exact, non reformulé
    assert "hors bassin" not in html


# ---------------------------------------------------------------------------
# C. Synthèse : somme, profils, pas de double comptage
# ---------------------------------------------------------------------------

def test_somme_debits_moyens_declares_seuls():
    synth = _node_eval_data(
        RESULT_SYNC,
        "window.dwfCalculerSynthese(window.dwfExtraireProvenance(d).injectes)",
    )
    assert synth["nb_injectes"] == 2
    # 0.002 + 0.0015 — jamais q_base_m3s
    assert abs(synth["debit_cumule_m3s"] - 0.0035) < 1e-9
    assert synth["nb_debits_valides"] == 2


def test_q_base_jamais_utilise_pour_la_somme():
    # journalier_type : debit_moyen=0.001, q_base=0.0004 → somme = 0.001
    res = {"provenance": {"apports_dwf": {"injectes": [APPORT_INJ_JOURNALIER], "ignores": []}}}
    synth = _node_eval_data(
        res,
        "window.dwfCalculerSynthese(window.dwfExtraireProvenance(d).injectes)",
    )
    assert abs(synth["debit_cumule_m3s"] - 0.001) < 1e-9
    html = _node_eval_data(res, "window.dwfConstruireHtmlBloc(d)")
    # q_base affiché uniquement comme valeur technique étiquetée
    assert "q_base slot SWMM (technique)" in html
    assert "0,0004" in html  # format fr-FR


def test_profil_unique_et_profils_multiples():
    synth_unique = _node_eval_data(
        RESULT_SYNC,
        "window.dwfCalculerSynthese(window.dwfExtraireProvenance(d).injectes)",
    )
    assert synth_unique["profil"] == "constant"
    res_mixte = {"provenance": {"apports_dwf": {
        "injectes": [APPORT_INJ_SYNC, APPORT_INJ_JOURNALIER], "ignores": []}}}
    synth_mixte = _node_eval_data(
        res_mixte,
        "window.dwfCalculerSynthese(window.dwfExtraireProvenance(d).injectes)",
    )
    assert synth_mixte["profil"] == "multiple"
    html_mixte = _node_eval_data(res_mixte, "window.dwfConstruireHtmlBloc(d)")
    assert "Profils multiples" in html_mixte


def test_plusieurs_apports_meme_noeud_pas_de_double_comptage():
    # Deux apports distincts sur le même nœud : chacun compte son débit moyen
    a1 = dict(APPORT_INJ_SYNC, apport_id="n1", debit_moyen_m3s=0.001)
    a2 = dict(APPORT_INJ_SYNC, apport_id="n2", debit_moyen_m3s=0.002)
    res = {"provenance": {"apports_dwf": {"injectes": [a1, a2], "ignores": []}}}
    synth = _node_eval_data(
        res,
        "window.dwfCalculerSynthese(window.dwfExtraireProvenance(d).injectes)",
    )
    assert synth["nb_injectes"] == 2
    assert abs(synth["debit_cumule_m3s"] - 0.003) < 1e-9


def test_ignores_jamais_dans_la_somme():
    synth = _node_eval_data(
        RESULT_CELERY,
        "window.dwfCalculerSynthese(window.dwfExtraireProvenance(d).injectes)",
    )
    assert synth["nb_injectes"] == 1
    assert abs(synth["debit_cumule_m3s"] - 0.002) < 1e-9


# ---------------------------------------------------------------------------
# D. Contradiction provenance/meta et échappement
# ---------------------------------------------------------------------------

def test_contradiction_provenance_meta_provenance_prioritaire():
    res = {
        "provenance": {"apports_dwf": {"injectes": [], "ignores": []}},
        "meta": {"apports_dwf": [APPORT_INJ_SYNC], "apports_dwf_ignores": []},
    }
    extrait = _node_eval_data(
        res,
        "window.dwfExtraireProvenance(d)",
    )
    assert extrait["source"] == "provenance"
    assert extrait["injectes"] == []
    assert extrait["anomalie"] is True
    html = _node_eval_data(res, "window.dwfConstruireHtmlBloc(d)")
    assert "Anomalie de cohérence" in html


def test_echappement_html_champs_textuels():
    malveillant = dict(
        APPORT_INJ_SYNC,
        node_id='<script>alert(1)</script>',
        nature='"><img src=x onerror=alert(1)>',
        motif=None,
    )
    res = {"provenance": {"apports_dwf": {
        "injectes": [malveillant],
        "ignores": [{"apport_id": "<b>id</b>", "node_id": "<i>x</i>", "motif": "<script>"}],
    }}}
    html = _node_eval_data(res, "window.dwfConstruireHtmlBloc(d)")
    assert "<script>" not in html
    assert "<img" not in html
    assert "&lt;script&gt;" in html


def test_libelles_interdits_absents():
    # Jamais de volume, débit instantané ou total réseau dans le rendu
    html = _node_eval_data(RESULT_CELERY, "window.dwfConstruireHtmlBloc(d)")
    html_bas = html.lower()
    for interdit in ("volume", "peak_outflow", "débit instantané", "débit total"):
        assert interdit not in html_bas
    # 'débit de pointe' n'apparaît que dans la mention de distinction
    assert "distincte du ruissellement et du débit de pointe" in html_bas


def test_aucun_calcul_interdit_dans_le_js():
    # Le JS ne doit pas dériver de volume ni utiliser q_base dans la somme
    assert "q_base_m3s" in DWF_JS  # affichage technique autorisé
    synth_fn = DWF_JS[DWF_JS.index("window.dwfCalculerSynthese"):]
    synth_fn = synth_fn[:synth_fn.index("window.dwfConstruireHtmlBloc")]
    assert "q_base" not in synth_fn
    assert "volume" not in synth_fn.lower()
    assert "peak_outflow" not in synth_fn
