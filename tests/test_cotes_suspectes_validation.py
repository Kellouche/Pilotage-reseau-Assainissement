"""
================================================================================
Tests automatisés du Registre des cotes suspectes et de la suspension
du profil en long jusqu'à validation utilisateur (Human-in-the-Loop).
================================================================================
"""

import os
from types import SimpleNamespace
import pytest
from fastapi.testclient import TestClient

os.environ["TESTING"] = "true"
from api.main import app
from api.database import SessionLocal
from api.models import Organization, Project, User, Membership, NodeCoteValidation
from api.routes.simulations import get_profil_en_long
from api.core.auth import create_access_token


@pytest.fixture
def ctx_cotes(tmp_path):
    """Fixture de test avec une organisation et un projet réel ou fixture."""
    db = SessionLocal()
    org = Organization(id="org_cotes_test", name="Org Cotes", slug="org-cotes-test")
    user = User(
        id="user_cotes_test",
        email="eng@cotes.dz",
        password_hash="hash",
        email_verified=True,
    )
    mem = Membership(org_id=org.id, user_id=user.id, role="engineer")
    # Trouver le projet Assainissement_Ville ou le GeoPackage existant
    real_proj = db.query(Project).filter(Project.name.contains("Assainissement_Ville")).first()
    gpkg_key = real_proj.source_gpkg_key if real_proj else "tests/data/golden_dataset/network_test.gpkg"
    proj = Project(
        id="proj_cotes_test",
        org_id=org.id,
        name="Projet Cotes Test",
        slug="proj-cotes-test",
        source_gpkg_key=gpkg_key,
    )
    db.add_all([org, user, mem, proj])
    db.commit()

    token = create_access_token({"sub": user.id, "email": user.email, "org_id": org.id, "role": "engineer"})
    headers = {"Authorization": f"Bearer {token}"}

    yield {
        "db": db,
        "org": org,
        "proj": proj,
        "user": user,
        "token": token,
        "headers": headers,
    }

    # Nettoyage
    db.query(NodeCoteValidation).filter(NodeCoteValidation.project_id == proj.id).delete()
    db.delete(mem)
    db.delete(proj)
    db.delete(user)
    db.delete(org)
    db.commit()
    db.close()


def test_suspension_profil_si_cotes_suspectes(ctx_cotes):
    """Vérifie que get_profil_en_long suspend le tracé si des cotes non validées sont présentes."""
    db = ctx_cotes["db"]
    tenant = SimpleNamespace(org_id=ctx_cotes["org"].id, user_id=ctx_cotes["user"].id, role="engineer")

    # Appel sur 1045 -> 1046 sans validation préalable
    res = get_profil_en_long(node_amont="1045", node_aval="1046", db=db, tenant=tenant)
    assert res["status"] == "cotes_suspectes_a_valider"
    assert "cotes_suspectes" in res
    assert len(res["cotes_suspectes"]) >= 2
    nodes_suspects = [cs["node_id"] for cs in res["cotes_suspectes"]]
    assert "1045" in nodes_suspects
    assert "1046" in nodes_suspects

    # Vérification des suggestions d'échelle centimétrique
    for cs in res["cotes_suspectes"]:
        if cs["node_id"] == "1045":
            assert cs["valeur_brute"] == 198.0
            assert cs["valeur_suggeree"] == 1.98
        elif cs["node_id"] == "1046":
            assert cs["valeur_brute"] == 190.0
            assert cs["valeur_suggeree"] == 1.90


def test_validation_cotes_et_elaboration_profil(ctx_cotes):
    """Vérifie le cycle complet : validation par l'hydraulicien -> tracé propre du profil."""
    client = TestClient(app)
    headers = ctx_cotes["headers"]
    db = ctx_cotes["db"]
    tenant = SimpleNamespace(org_id=ctx_cotes["org"].id, user_id=ctx_cotes["user"].id, role="engineer")

    # 1. Valider les cotes pour 1045 et 1046 via l'API
    payload = {
        "validations": [
            {"node_id": "1045", "champ": "profondeur", "action": "valider", "valeur_validee": 1.98},
            {"node_id": "1046", "champ": "profondeur", "action": "valider", "valeur_validee": 1.90},
        ]
    }
    resp = client.post("/api/v1/simulations/cotes-suspectes/valider", json=payload, headers=headers)
    assert resp.status_code == 200, resp.text
    data_val = resp.json()
    assert data_val["status"] == "success"
    assert len(data_val["items"]) == 2

    # 2. Relancer le profil en long : il doit maintenant réussir (status == success)
    res = get_profil_en_long(node_amont="1045", node_aval="1046", db=db, tenant=tenant)
    assert res["status"] == "success"
    assert res["nb_troncons"] >= 1

    # 3. Vérifier que les segments utilisent les profondeurs certifiées et que z_sommet n'est plus à 298m !
    seg_1045 = next((s for s in res["segments"] if s["node_id"] == "1045"), None)
    seg_1046 = next((s for s in res["segments"] if s["node_id"] == "1046"), None)
    assert seg_1045 is not None
    assert seg_1046 is not None

    assert seg_1045["profondeur_m"] == 1.98
    assert seg_1046["profondeur_m"] == 1.90
    assert seg_1045["cote_validee"] is True
    assert seg_1046["cote_validee"] is True

    # Sommet = radier + 1.98 (si radier disponible, bien loin des 298.79 m !)
    if seg_1045.get("z_sommet_regard") is not None:
        assert seg_1045["z_sommet_regard"] < 120.0
    if seg_1046.get("z_sommet_regard") is not None:
        assert seg_1046["z_sommet_regard"] < 120.0


def test_forcer_tracé_brut(ctx_cotes):
    """Vérifie que forcer_brut permet d'outrepasser la suspension en alertant l'utilisateur."""
    db = ctx_cotes["db"]
    tenant = SimpleNamespace(org_id=ctx_cotes["org"].id, user_id=ctx_cotes["user"].id, role="engineer")

    # Suppression de validations éventuelles pour tester le forçage
    db.query(NodeCoteValidation).filter(NodeCoteValidation.project_id == ctx_cotes["proj"].id).delete()
    db.commit()

    res = get_profil_en_long(node_amont="1045", node_aval="1046", forcer_brut=True, db=db, tenant=tenant)
    assert res["status"] == "success"
    # Vérifier la présence d'une alerte sur cotes brutes non certifiées
    alertes_suspectes = [a for a in res["alertes"] if a.get("type") == "cote_suspecte_non_validee"]
    assert len(alertes_suspectes) >= 1
