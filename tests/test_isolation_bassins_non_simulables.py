import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch
from fastapi import HTTPException
from api.routes.simulations import _identite_bassin_du_cache

def test_identite_bassin_du_cache_detection_isole(tmp_path):
    cache_file = tmp_path / "test.clusters_cache.json"
    cache_content = """{
        "bassins_geojson": {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "properties": {
                        "type": "bassin_urbain",
                        "cluster_id": 55,
                        "nom": "Prison",
                        "nb_regards": 21,
                        "nb_conduites": 25,
                        "surface_ha": 3.5,
                        "exutoire_id": "OUT_55"
                    }
                },
                {
                    "type": "Feature",
                    "properties": {
                        "type": "bassin_urbain",
                        "cluster_id": 999,
                        "nom": "Rejet Isole",
                        "nb_regards": 0,
                        "nb_conduites": 0,
                        "surface_ha": 0.05,
                        "exutoire_id": "OUT_ISOLE"
                    }
                }
            ]
        }
    }"""
    cache_file.write_text(cache_content, encoding="utf-8")
    gpkg_dummy = tmp_path / "test.gpkg"
    gpkg_dummy.touch()

    # 1. Bassin collecteur standard (Prison) : non isolé
    ident_prison = _identite_bassin_du_cache(gpkg_dummy, "55")
    assert ident_prison["nom"] == "Prison"
    assert ident_prison["est_isole"] is False
    assert ident_prison["nb_conduites"] == 25

    # 2. Ouvrage isolé sans réseau amont (Rejet Isole) : est_isole = True
    ident_isole = _identite_bassin_du_cache(gpkg_dummy, "999")
    assert ident_isole["nom"] == "Rejet Isole"
    assert ident_isole["est_isole"] is True
    assert ident_isole["nb_conduites"] == 0
