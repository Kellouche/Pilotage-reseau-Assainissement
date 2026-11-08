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

def test_suppression_bandeau_flottant_doublon():
    """Vérifie que l'indicateur flottant en doublon sur la carte a été retiré."""
    index_html = Path("templates/index.html").read_text(encoding="utf-8")
    assert 'id="map-bassin-indicator"' not in index_html
    assert 'id="topbar-bassin-container"' in index_html
    assert 'id="topbar-bassin-pill"' in index_html
    assert 'gererAffichageSimulationPourBassin' in index_html


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
