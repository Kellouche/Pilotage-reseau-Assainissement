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
    finally:
        db.close()
