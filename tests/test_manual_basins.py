"""
Tests de persistance et d'intégration des bassins manuels tracés par l'ingénieur.
Fichier : tests/test_manual_basins.py
"""

import json
from pathlib import Path
def test_manual_basin_crud(tmp_path, monkeypatch):
    test_overrides = tmp_path / "manual_overrides_test.json"
    import src.infrastructure.persistance_manuelle as pm
    monkeypatch.setattr(pm, "OVERRIDES_FILE", test_overrides)
    monkeypatch.setattr(pm, "DATA_DIR", tmp_path)

    from api.main import api_save_manual_basin_alias, api_get_manual_basins_alias, api_delete_manual_basin_alias

    # 1. Sauvegarder un bassin manuel via l'API
    payload = {
        "conduites": ["T1", "T2"],
        "nom": "Bassin Industriel Manuel",
        "exutoire": {"nom": "Exutoire Rivière", "type": "rejet", "latlng": {"lat": 36.7, "lng": 3.05}}
    }
    data = api_save_manual_basin_alias(payload)
    assert data["nom"] == "Bassin Industriel Manuel"
    assert "id" in data
    bassin_id = data["id"]

    # 2. Lister les bassins manuels
    bassins = api_get_manual_basins_alias()
    assert len(bassins) == 1
    assert bassins[0]["id"] == bassin_id

    # 3. Supprimer le bassin manuel (test avec identifiant M_1 ou entier)
    del_res = api_delete_manual_basin_alias(f"M_{bassin_id}")
    assert del_res["status"] == "ok"

    # 4. Vérifier la liste vide après suppression
    bassins_after = api_get_manual_basins_alias()
    assert len(bassins_after) == 0


