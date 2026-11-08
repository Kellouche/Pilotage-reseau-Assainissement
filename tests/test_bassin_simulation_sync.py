"""
================================================================================
Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
Auteur : Dr Abdelhakim KELLOUCHE
Date de création : 2026-04-20
Date de modification : 2026-11-08
Objet : Tests automatisés de synchronisation de la simulation par bassin et non-duplication des bandeaux
================================================================================
"""

from pathlib import Path
from api.routes.simulations import get_bassin_simulation
from api.database import SessionLocal

def _get_full_cockpit_content():
    base = Path(__file__).resolve().parent.parent
    content = (base / "templates" / "index.html").read_text(encoding="utf-8")
    for p in (base / "templates" / "partials").glob("*.html"):
        content += "\n" + p.read_text(encoding="utf-8")
    for j in (base / "static" / "js" / "app").glob("*.js"):
        content += "\n" + j.read_text(encoding="utf-8")
    for c in (base / "static" / "css").glob("*.css"):
        content += "\n" + c.read_text(encoding="utf-8")
    return content

def test_suppression_bandeau_flottant_doublon():
    """Vérifie que l'indicateur flottant en doublon sur la carte a été retiré."""
    cockpit_content = _get_full_cockpit_content()
    assert 'id="map-bassin-indicator"' not in cockpit_content
    assert 'id="topbar-bassin-container"' in cockpit_content
    assert 'id="topbar-bassin-pill"' in cockpit_content
    assert 'gererAffichageSimulationPourBassin' in cockpit_content


def test_endpoint_simulation_par_bassin():
    """Vérifie le fonctionnement de l'endpoint get_bassin_simulation."""
    db = SessionLocal()
    try:
        # 1. Bassin sans calcul
        r = get_bassin_simulation("999999", db=db, tenant=None)
        assert r["status"] == "none"

        # 2. Bassin avec calcul sauvegardé (ex: cluster 92 = 25_ouvrages_speciaux_348883)
        r_exist = get_bassin_simulation("92", db=db, tenant=None)
        assert r_exist["status"] in ("none", "success")
        if r_exist["status"] == "success":
            assert "kpis" in r_exist or "conduit_results" in r_exist
            assert "meta" in r_exist

        # 3. Résolution robuste par nom textuel de bassin
        r_nom = get_bassin_simulation("25_ouvrages_speciaux_348883", db=db, tenant=None)
        assert r_nom["status"] in ("none", "success")
        if r_nom["status"] == "success":
            assert "meta" in r_nom
    finally:
        db.close()


def test_fermeture_automatique_modale_et_zoom_grande_echelle():
    """Vérifie que la modale se ferme automatiquement post-simulation et que le zoom cible la grande échelle."""
    sim_ui_js = Path("static/js/app/simulation_ui.js").read_text(encoding="utf-8")
    resultats_couches_js = Path("static/js/app/resultats_couches.js").read_text(encoding="utf-8")
    resultats_affichage_js = Path("static/js/app/resultats_affichage.js").read_text(encoding="utf-8")

    # 1. Présence de l'appel automatique de fermeture de la modale dans declencherSimulationSWMM
    assert "fermerModalSimulation" in sim_ui_js
    assert "window.fermerModalSimulation()" in sim_ui_js
    assert "window.zoomerSurZoneSimulee(data, 19)" in sim_ui_js

    # 2. Zoom à grande échelle (maxZoom 19)
    assert "maxZoom: cibleMaxZoom || 19" in resultats_couches_js
    assert "maxZoom: 19" in resultats_affichage_js
    assert "padding: [35, 35]" in resultats_couches_js
    assert "padding: [35, 35]" in resultats_affichage_js


def test_anti_cache_et_cache_busting():
    """Vérifie la présence du middleware anti-cache HTTP et des tags de cache-busting dans les templates."""
    main_py = Path("api/main.py").read_text(encoding="utf-8")
    index_html = Path("templates/index.html").read_text(encoding="utf-8")

    assert "anti_cache_static_middleware" in main_py
    assert "no-store, must-revalidate" in main_py
    assert "?v=5.2.2" in index_html


def test_bassin_non_simule_mention_et_masquage_legende():
    """Vérifie que pour un bassin non simulé, l'indicateur affiche '(non simulé)' et la légende est masquée."""
    bassins_js = Path("static/js/app/bassins_selection.js").read_text(encoding="utf-8")
    assert "(non simulé)" in bassins_js
    assert "legNonSim.style.display = 'none'" in bassins_js
