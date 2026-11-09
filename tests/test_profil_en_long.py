"""
================================================================================
Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
Auteur : Dr Abdelhakim KELLOUCHE
Date de création : 2026-04-20
Date de modification : 2026-11-09
Objet : Tests automatisés du profil en long hydraulique interactif (Phase 6.A)
================================================================================
"""

import os
from pathlib import Path
import pytest
from fastapi import HTTPException

os.environ["TESTING"] = "true"
from api.database import SessionLocal
from api.routes.simulations import get_profil_en_long


def test_profil_en_long_success():
    """Vérifie le calcul réussi d'un profil en long entre 2 regards connectés."""
    db = SessionLocal()
    try:
        res = get_profil_en_long(node_amont="2674", node_aval="2672", db=db)
        assert res["status"] == "success"
        assert res["node_amont"] == "2674"
        assert res["node_aval"] == "2672"
        assert res["nb_troncons"] >= 1
        assert res["longueur_totale_m"] > 0
        assert len(res["segments"]) >= 2

        # Vérification des attributs géométriques obligatoires
        premier_segment = res["segments"][0]
        assert "z_radier" in premier_segment
        assert "z_terrain" in premier_segment
        assert "z_gen_superieure" in premier_segment
        assert "distance_m" in premier_segment
        assert premier_segment["distance_m"] == 0.0
        assert premier_segment["z_terrain"] >= premier_segment["z_radier"]

        dernier_segment = res["segments"][-1]
        assert dernier_segment["distance_m"] == res["longueur_totale_m"]
    finally:
        db.close()


def test_profil_en_long_reverse_auto_fallback():
    """Vérifie que l'algorithme retrouve le chemin amont/aval même si l'ordre est inversé."""
    db = SessionLocal()
    try:
        res = get_profil_en_long(node_amont="2672", node_aval="2674", db=db)
        assert res["status"] == "success"
        assert res["nb_troncons"] >= 1
        assert res["longueur_totale_m"] > 0
    finally:
        db.close()


def test_profil_en_long_node_not_found():
    """Vérifie qu'un code de regard inexistant lève un code HTTP 404."""
    db = SessionLocal()
    try:
        with pytest.raises(HTTPException) as excinfo:
            get_profil_en_long(node_amont="REG_TOTALEMENT_INCONNU_99999", node_aval="2672", db=db)
        assert excinfo.value.status_code == 404
    finally:
        db.close()


def test_cockpit_includes_profil_long_components():
    """Vérifie la bonne intégration dans le template HTML et la barre d'outils du Cockpit."""
    root = Path(__file__).resolve().parent.parent
    index_html = (root / "templates" / "index.html").read_text(encoding="utf-8")
    toolbar_html = (root / "templates" / "partials" / "toolbar_edit.html").read_text(encoding="utf-8")
    panel_html = (root / "templates" / "partials" / "panel_profil_long.html").read_text(encoding="utf-8")

    assert "chart.umd.min.js" in index_html
    assert "profil_long.js" in index_html
    assert "panel_profil_long.html" in index_html
    assert "btn-profil-long" in toolbar_html
    assert "canvas-profil-long" in panel_html
    assert "input-profil-amont" in panel_html
    assert "input-profil-aval" in panel_html
