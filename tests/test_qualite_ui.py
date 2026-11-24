# -*- coding: utf-8 -*-
"""
Tests de validation de l'interface Cockpit Qualité Réseau V2.1 (Lot 4).
Spec : docs/05_CONTROLE_QUALITE_V2.md §6/§7.
"""
import re
from fastapi.testclient import TestClient
from api.main import app
from api.core.auth import create_access_token
from api.database import SessionLocal
from api.models import User, Organization, Project


def test_qualite_ui_redirection_anonyme():
    """Un utilisateur non authentifié est redirigé vers /login."""
    client = TestClient(app)
    resp = client.get("/qualite", follow_redirects=False)
    assert resp.status_code == 302
    assert "/login" in resp.headers.get("location", "")


def test_qualite_ui_structure_et_contrat():
    """L'UI V2.1 contient tous les composants interactifs et les contrats d'API."""
    client = TestClient(app)
    db = SessionLocal()
    try:
        user = db.query(User).first()
        token = create_access_token({"sub": user.id if user else "test_user", "type": "access"})
        client.cookies.set("access_token", token)

        resp = client.get("/qualite")
        assert resp.status_code == 200
        html = resp.text

        # 1. Bibliothèques cartographiques
        assert "leaflet.js" in html.lower()
        assert "leaflet.markercluster" in html.lower()

        # 2. Conteneurs majeurs Split-Screen V2.1
        assert 'id="map"' in html
        assert 'id="queue-stepper-bar"' in html
        assert 'id="fiche-container"' in html
        assert 'id="anom-table-tbody"' in html
        assert 'id="kpi-verdict"' in html
        assert 'id="kpi-score-topo"' in html
        assert 'id="kpi-score-alti"' in html
        assert 'id="chk-toggle-n3"' in html

        # 3. Routes API référencées dans le script client
        assert "/api/v1/qualite" in html
        assert "/synthese" in html
        assert "/anomalies.geojson" in html
        assert "/statut" in html

        # 4. Fonction de retour cockpit
        assert "retournerCockpit" in html
    finally:
        db.close()
