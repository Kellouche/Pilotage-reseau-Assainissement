# -*- coding: utf-8 -*-
"""
================================================================================
Projet : DrainPilot 5.2 - Tests de contrat LOT P1.5.3
Objet : Intégration des apports DWF dans la fenêtre de lancement des
        simulations — interrupteur, compteurs via API existantes, gestion
        du 422 de compatibilité, traçabilité dans les résultats.

Ces tests vérifient le CONTRAT frontend (gabarits + JS) et la non-régression
du chemin de lancement : aucune règle DWF n'est dupliquée côté client.
================================================================================
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

MODAL_HTML = (ROOT / "templates" / "partials" / "modal_simulation.html").read_text(encoding="utf-8")
SIM_UI_JS = (ROOT / "static" / "js" / "app" / "simulation_ui.js").read_text(encoding="utf-8")
RES_ACTIONS_JS = (ROOT / "static" / "js" / "app" / "resultats_actions.js").read_text(encoding="utf-8")
RES_AFFICHAGE_JS = (ROOT / "static" / "js" / "app" / "resultats_affichage.js").read_text(encoding="utf-8")
COMMON_JS = (ROOT / "static" / "js" / "app" / "common.js").read_text(encoding="utf-8")
ROUTES_APPORTS = (ROOT / "api" / "routes" / "apports.py").read_text(encoding="utf-8")
ROUTES_SIMS = (ROOT / "api" / "routes" / "simulations.py").read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# A. Interrupteur et section DWF dans la modale de lancement
# ---------------------------------------------------------------------------

def test_section_dwf_presente_dans_modale():
    assert 'id="sim-dwf-section"' in MODAL_HTML
    assert 'id="sim-chk-dwf-actif"' in MODAL_HTML
    assert "Activer les apports DWF" in MODAL_HTML


def test_compteurs_et_lien_gestion_dwf():
    assert 'id="sim-dwf-stats"' in MODAL_HTML
    assert 'id="sim-dwf-alerte-incompat"' in MODAL_HTML
    assert "ouvrirModalApportsDwf()" in MODAL_HTML
    # Mention explicite de l'indépendance vis-à-vis de la pluie
    assert "Indépendant de la pluie" in MODAL_HTML


# ---------------------------------------------------------------------------
# B. Chargement des informations via les API existantes (pas de duplication)
# ---------------------------------------------------------------------------

def test_chargement_utilise_api_existantes():
    assert "chargerInfosDwfSimulation" in SIM_UI_JS
    # Requête au projet actif puis aux endpoints /apports existants
    assert "/api/v1/network/datasets" in SIM_UI_JS
    assert "/api/v1/apports?" in SIM_UI_JS
    assert "/api/v1/apports/a-reconcilier?" in SIM_UI_JS


def test_pas_de_regle_de_compatibilite_dupliquee_cote_client():
    # Le frontend ne doit pas réimplémenter les contrôles P1.4
    # (estampillage version_id / sha256).
    for interdit in ("gpkg_version_id", "gpkg_sha256", "sha256"):
        assert interdit not in SIM_UI_JS


def test_defaut_dwf_conditionne():
    # DWF coché par défaut si des apports actifs existent et qu'au moins
    # un est compatible (ou aucun incompatible) ; décoché si 0 actif ou
    # si TOUS les apports actifs sont incompatibles.
    assert "chk.checked = (info.compatibles > 0 || nIncompat === 0)" in SIM_UI_JS
    assert "actifs.length === 0" in SIM_UI_JS


def test_actualisation_a_l_ouverture_modale():
    assert "chargerInfosDwfSimulation" in RES_ACTIONS_JS


# ---------------------------------------------------------------------------
# C. Transmission explicite de dwf_actif (synchrone)
# ---------------------------------------------------------------------------

def test_payload_contient_dwf_actif():
    assert "dwf_actif: dwfActif" in SIM_UI_JS
    # Valeur lue depuis l'interrupteur ; null si non évalué
    assert "sim-chk-dwf-actif" in SIM_UI_JS


# ---------------------------------------------------------------------------
# D. Gestion du 422 apports incompatibles
# ---------------------------------------------------------------------------

def test_422_structure_detail_objet():
    # Le backend renvoie detail = {message, apports_incompatibles}
    assert '"apports_incompatibles": e.details' in ROUTES_SIMS


def test_frontend_detecte_422_dwf():
    assert "errDwfIncompatibles" in SIM_UI_JS
    assert "apports_incompatibles" in SIM_UI_JS
    assert "err.dwfIncompatibles" in SIM_UI_JS


def test_message_422_et_acces_reconciliation_sans_relance():
    assert "Apports DWF incompatibles" in SIM_UI_JS
    assert "Ouvrir le panneau de réconciliation DWF" in SIM_UI_JS
    assert "ouvrirModalApportsDwf()" in SIM_UI_JS
    # Aucune relance automatique après réconciliation dans le code
    assert "revalider" not in SIM_UI_JS


# ---------------------------------------------------------------------------
# E. Traçabilité des résultats (provenance existante)
# ---------------------------------------------------------------------------

def test_legende_dwf_dans_commun():
    assert 'id="sim-legend-dwf-info"' in COMMON_JS


def test_affichage_provenance_apports_dwf():
    assert "apports_dwf" in RES_AFFICHAGE_JS
    assert "provenance" in RES_AFFICHAGE_JS
    assert "injectes" in RES_AFFICHAGE_JS


def test_provenance_existee_cote_moteur():
    # Le moteur produit déjà kpis.provenance.apports_dwf — on vérifie que
    # le contrat n'est pas contourné (pas de champ parallèle inventé).
    moteur = (ROOT / "src" / "domain" / "moteur_swmm" / "moteur.py").read_text(encoding="utf-8")
    assert 'kpis["provenance"]["apports_dwf"]' in moteur


# ---------------------------------------------------------------------------
# F. Non-régression : scénarios pluvieux ≠ DWF, async respecte dwf_actif
# ---------------------------------------------------------------------------

def test_backend_async_transmet_dwf_actif():
    # POST /api/v1/simulations (Celery) : champ typé prioritaire
    assert '"dwf_actif": simulation.dwf_actif' in ROUTES_SIMS


def test_backend_sync_preserve_api_dwf():
    assert "preparer_apports_pour_simulation" in ROUTES_SIMS
    assert "dwf_actif=payload.dwf_actif" in ROUTES_SIMS


def test_api_reconcilier_existe():
    assert '"/a-reconcilier"' in ROUTES_APPORTS


def test_async_pas_routage_sec_defaut_quand_absent():
    # Bug trouvé en validation réelle Celery : params.get("pas_routage_sec")
    # renvoyait None → crash f"{None:02d}" dans sections_inp. Le défaut
    # moteur (5 s) doit s'appliquer quand le paramètre est absent.
    service = (ROOT / "api" / "services" / "simulation_service.py").read_text(encoding="utf-8")
    assert 'params.get("pas_routage_sec")\n                         if params.get("pas_routage_sec") is not None else 5' in service
