# -*- coding: utf-8 -*-
"""
Tests terrain/altimétrie des couches auxiliaires (ex-test_aux_layers.py)
"""

import io
import json
import zipfile
from pathlib import Path

import geopandas as gpd
import numpy as np
import pytest
from shapely.geometry import Point
from starlette.testclient import TestClient

from api.core.auth import create_access_token, hash_password
from api.database import SessionLocal
from api.main import app
from api.models import GpkgVersion, Membership, Organization, Project, ProjectAuxLayer, User
from api.services import aux_altimetrie_service as alt
from api.services import aux_layers_service as svc

from tests.aux_layers_support import (
    _ecrire_fichier, _gpkg_regards, _h, _importer_topo,
    _topo_gdf, _uid, db, org_projet,
)

def test_regards_terrain_artefact(db, org_projet, tmp_path):
    """L'artefact produit z_terrain + pente + azimut pour chaque regard du GPKG projet."""
    # Regarder positions = sous-ensemble des points topo (dans l'emprise)
    topo = _topo_gdf(n=1500, spread=1200.0)
    coords = [(p.x, p.y) for p in topo.geometry.iloc[::100]]  # ~15 regards
    codes = [str(700 + i) for i in range(len(coords))]
    gpkg_regards = _gpkg_regards(tmp_path, coords, codes)

    # Rattacher le GPKG au projet
    proj = db.query(Project).filter(Project.id == org_projet["proj"].id).first()
    proj.source_gpkg_key = str(gpkg_regards)
    db.commit()

    # Import topo + grille
    f = tmp_path / "topo.gpkg"
    _ecrire_fichier(topo, f, "gpkg")
    res = svc.importer_couche_aux(
        db=db, org_id=org_projet["org"].id, project_id=org_projet["proj"].id,
        type_couche="altimetrie_points", nom="Topo",
        fichier_path=f, fichier_nom="topo.gpkg", colonne_z="Field4",
    )
    couche = db.query(ProjectAuxLayer).filter(ProjectAuxLayer.id == res["id"]).first()
    meta = alt.construire_grille_altimetrie(
        org_id=org_projet["org"].id, project_id=org_projet["proj"].id,
        layer_id=couche.id, storage_key=couche.storage_key, colonne_z="Field4",
    )
    assert meta["nb_points"] == 1500

    rt = alt.calculer_regards_terrain(
        db=db, org_id=org_projet["org"].id, project_id=org_projet["proj"].id,
        layer_id=couche.id, storage_key=couche.storage_key,
    )
    assert rt["statut"] == "ok"
    assert rt["nb_regards"] == len(coords)

    artefact = alt.charger_regards_terrain(org_projet["org"].id, org_projet["proj"].id, couche.id)
    assert artefact is not None
    assert artefact["meta"]["gpkg_sha256"]
    r0 = artefact["regards"]["700"]
    assert r0["z_terrain_m"] is not None
    assert 90 < r0["z_terrain_m"] < 110
    assert r0["confiance"] in ("haute", "moyenne")
    assert r0["pente_terrain_pct"] is not None
    assert 0 <= r0["azimut_pente_deg"] < 360


def test_regards_terrain_sans_gpkg(db, org_projet, tmp_path):
    """Projet sans GPKG → artefact 'ignore' honnête, pas d'erreur."""
    res = _importer_topo(db, org_projet, tmp_path, n=100, spread=800.0)
    couche = db.query(ProjectAuxLayer).filter(ProjectAuxLayer.id == res["id"]).first()
    alt.construire_grille_altimetrie(
        org_id=org_projet["org"].id, project_id=org_projet["proj"].id,
        layer_id=couche.id, storage_key=couche.storage_key, colonne_z="Field4",
    )
    rt = alt.calculer_regards_terrain(
        db=db, org_id=org_projet["org"].id, project_id=org_projet["proj"].id,
        layer_id=couche.id, storage_key=couche.storage_key,
    )
    assert rt["statut"] == "ignore"


def test_endpoint_regards_terrain(db, org_projet, tmp_path):
    """GET /regards-terrain → artefact + flag perime ; POST recalculer → ok."""
    client = TestClient(app)
    pid = org_projet["proj"].id
    tok = org_projet["token"]

    topo = _topo_gdf(n=800, spread=1000.0)
    coords = [(p.x, p.y) for p in topo.geometry.iloc[::80]]
    codes = [str(800 + i) for i in range(len(coords))]
    gpkg_regards = _gpkg_regards(tmp_path, coords, codes)
    proj = db.query(Project).filter(Project.id == pid).first()
    proj.source_gpkg_key = str(gpkg_regards)
    db.commit()

    f = tmp_path / "topo.gpkg"
    _ecrire_fichier(topo, f, "gpkg")
    with open(f, "rb") as fh:
        r = client.post(f"/api/v1/projets/{pid}/aux-layers",
                        files=[("files", ("topo.gpkg", fh, "application/octet-stream"))],
                        data={"type": "altimetrie_points", "colonne_z": "Field4"},
                        headers=_h(tok))
    assert r.status_code == 200, r.text
    layer_id = r.json()["couche"]["id"]

    # GET artefact (calculé à l'import)
    r = client.get(f"/api/v1/projets/{pid}/aux-layers/{layer_id}/regards-terrain", headers=_h(tok))
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["meta"]["nb_regards"] == len(coords)
    assert "perime" in j["meta"]
    assert j["regards"]["800"]["z_terrain_m"] is not None

    # POST recalculer
    r = client.post(f"/api/v1/projets/{pid}/aux-layers/{layer_id}/regards-terrain/recalculer",
                    headers=_h(tok))
    assert r.status_code == 200, r.text
    assert r.json()["resultat"]["nb_regards"] == len(coords)


def test_endpoint_sans_altitude_colonne_z(db, org_projet, tmp_path):
    """Sans colonne_z ni auto-détection → statut sans_altitude, endpoints elevation → 422."""
    client = TestClient(app)
    pid = org_projet["proj"].id
    tok = org_projet["token"]

    # GeoJSON sans aucune colonne d'altitude exploitable : 'valeur' contient
    # des codes hors plage altitude (>9000 m) et 'nom' est non numérique.
    gdf = _topo_gdf(n=10).rename(columns={"Field4": "valeur"})
    gdf["valeur"] = 50000.0
    f = tmp_path / "topo.geojson"
    _ecrire_fichier(gdf, f, "geojson")
    with open(f, "rb") as fh:
        r = client.post(f"/api/v1/projets/{pid}/aux-layers",
                        files=[("files", ("topo.geojson", fh, "application/geo+json"))],
                        data={"type": "altimetrie_points"}, headers=_h(tok))
    assert r.status_code == 200, r.text
    couche = r.json()["couche"]
    assert couche["statut"] == "sans_altitude"

    r = client.get(f"/api/v1/projets/{pid}/aux-layers/{couche['id']}/elevation?lng=1.3&lat=36.17",
                   headers=_h(tok))
    assert r.status_code == 422


def test_endpoint_auto_detection_colonne_z_par_valeurs(db, org_projet, tmp_path):
    """Colonne à nom générique ('valeur') portant des cotes plausibles →
    auto-détection par valeurs, statut ok, colonne_z renseignée."""
    client = TestClient(app)
    pid = org_projet["proj"].id
    tok = org_projet["token"]

    gdf = _topo_gdf(n=10).rename(columns={"Field4": "valeur"})
    f = tmp_path / "topo.geojson"
    _ecrire_fichier(gdf, f, "geojson")
    with open(f, "rb") as fh:
        r = client.post(f"/api/v1/projets/{pid}/aux-layers",
                        files=[("files", ("topo.geojson", fh, "application/geo+json"))],
                        data={"type": "altimetrie_points"}, headers=_h(tok))
    assert r.status_code == 200, r.text
    couche = r.json()["couche"]
    assert couche["statut"] == "ok"
    assert couche["colonne_z"] == "valeur"


def test_terrain_aux_pour_profil(db, org_projet):
    """P3 — l'artefact regards_terrain n'est servi au profil que si son
    estampillage gpkg_sha256 correspond au GPKG actif (jamais périmé)."""
    import json as _json
    from api.routes.simulations_profil import _terrain_aux_pour_profil
    from api.services.aux_layers_service import cle_couche_aux, _store
    from api.models import ProjectAuxLayer

    oid, pid = org_projet["org"].id, org_projet["proj"].id
    couche = ProjectAuxLayer(
        org_id=oid, project_id=pid, type="altimetrie_points",
        nom="topo test", storage_key="cle-test", statut="ok",
        colonne_z="Field4", nb_features=10,
    )
    db.add(couche)
    db.commit()

    art = {
        "meta": {"gpkg_sha256": "sha_test_123", "resolution_m": 30.0},
        "regards": {"123": {"z_terrain_m": 100.5, "confiance": "haute"}},
    }
    _store().put_bytes(
        cle_couche_aux(oid, pid, couche.id, "derive/regards_terrain.json"),
        _json.dumps(art).encode("utf-8"),
    )

    # SHA correspondant → artefact retourné
    res = _terrain_aux_pour_profil(db, oid, org_projet["proj"], {"gpkg_sha": "sha_test_123"})
    assert res is not None
    assert res["artefact"]["regards"]["123"]["z_terrain_m"] == 100.5

    # SHA différent → artefact périmé ignoré
    assert _terrain_aux_pour_profil(db, oid, org_projet["proj"], {"gpkg_sha": "autre_sha"}) is None
    # Pas de sha → pas de lookup
    assert _terrain_aux_pour_profil(db, oid, org_projet["proj"], {}) is None
    # Projet None → pas de lookup
    assert _terrain_aux_pour_profil(db, oid, None, {"gpkg_sha": "sha_test_123"}) is None


def test_calculer_apercu_terrain(db, org_projet):
    """Calcul pur de l'aperçu terrain→radier : médiane profondeur, flags,
    inversions amont/aval, seuil 95 %."""
    import geopandas as gpd
    from shapely.geometry import Point
    from api.services.aux_altimetrie_service import calculer_apercu_terrain

    regards = gpd.GeoDataFrame(
        {"Code": ["A", "B", "C"], "Profondeur": [2.0, None, 3.0]},
        geometry=[Point(0, 0), Point(1, 0), Point(2, 0)], crs="EPSG:4326",
    )
    canas = gpd.GeoDataFrame(
        {"ID_AMONT": ["A", "B"], "ID_AVAL": ["B", "C"]},
        geometry=[Point(0, 0), Point(1, 0)], crs="EPSG:4326",
    )
    artefact = {
        "meta": {"gpkg_sha256": "x", "resolution_m": 30.0},
        "regards": {
            "A": {"z_terrain_m": 100.0, "confiance": "haute"},
            "B": {"z_terrain_m": 99.0, "confiance": "haute"},
            "C": {"z_terrain_m": 100.0, "confiance": "haute"},
        },
    }
    res = calculer_apercu_terrain(regards, canas, artefact)

    # Médiane des profondeurs réelles {2.0, 3.0} = 2.5
    assert res["profondeur"]["mediane_reseau_m"] == 2.5
    assert res["profondeur"]["nb_estimees"] == 1
    # B sans profondeur → médiane 2.5, flaggé
    assert res["par_regard"]["B"]["profondeur_estimee"] is True
    assert res["par_regard"]["B"]["profondeur_m"] == 2.5
    assert res["par_regard"]["B"]["z_radier_terrain_m"] == 96.5
    # A→B : 98 > 96.5 OK ; B→C : 96.5 <= 97.0 → inversion
    assert res["inversions_amont_aval"]["nb"] == 1
    assert res["inversions_amont_aval"]["echantillon"][0]["amont"] == "B"
    assert res["couverture"]["pct"] == 100.0
    assert res["eligible_injection_95"] is True


def test_endpoint_apercu_inp_absent(db, org_projet):
    """Sans artefact regards_terrain, l'aperçu répond 'absent' (pas de crash)."""
    client = TestClient(app)
    pid = org_projet["proj"].id
    tok = org_projet["token"]

    couche = ProjectAuxLayer(
        org_id=org_projet["org"].id, project_id=pid,
        type="altimetrie_points", nom="topo sans artefact",
        storage_key="cle-test", statut="ok", colonne_z="Field4",
    )
    db.add(couche)
    db.commit()

    r = client.get(f"/api/v1/projets/{pid}/aux-layers/{couche.id}/apercu-inp",
                   headers=_h(tok))
    assert r.status_code == 200
    assert r.json()["statut"] == "absent"

    # Couche d'un autre org → stealth 404
    r2 = client.get(f"/api/v1/projets/{pid}/aux-layers/{couche.id}/apercu-inp")
    assert r2.status_code in (401, 404)


def test_analyser_ecoulement_terrain():
    """P1 — file de revue : terrain qui monte le long du flux = suspect,
    conduit cohérent ignoré, sévérité et motifs corrects."""
    import geopandas as gpd
    from shapely.geometry import LineString, Point
    from api.services.aux_altimetrie_service import analyser_ecoulement_terrain

    # A(0,0) → B(0.001,0) : ~111 m vers l'Est ; C(0.002,0) plus loin
    regards = gpd.GeoDataFrame(
        {"Code": ["A", "B", "C"], "Profondeur": [2.0, 2.0, 2.0]},
        geometry=[Point(0, 0), Point(0.001, 0), Point(0.002, 0)],
        crs="EPSG:4326",
    )
    canas = gpd.GeoDataFrame(
        {"ID_AMONT": ["A", "B"], "ID_AVAL": ["B", "C"], "Longeur": [100.0, 100.0]},
        geometry=[LineString([(0, 0), (0.001, 0)]),
                  LineString([(0.001, 0), (0.002, 0)])],
        crs="EPSG:4326",
    )
    artefact = {
        "meta": {"gpkg_sha256": "x", "resolution_m": 30.0},
        "regards": {
            # A→B : terrain descend (100→99) = cohérent ; B→C : monte (99→100.5)
            "A": {"z_terrain_m": 100.0, "confiance": "haute",
                  "pente_terrain_pct": 1.0, "azimut_pente_deg": 90.0},
            "B": {"z_terrain_m": 99.0, "confiance": "haute",
                  "pente_terrain_pct": 1.5, "azimut_pente_deg": 270.0},
            "C": {"z_terrain_m": 100.5, "confiance": "haute",
                  "pente_terrain_pct": 1.0, "azimut_pente_deg": 90.0},
        },
    }
    res = analyser_ecoulement_terrain(regards, canas, artefact)

    assert res["statut"] == "ok"
    assert res["nb_conduites_analysées"] == 2
    assert res["nb_suspects"] == 1
    s = res["suspects"][0]
    assert s["amont"] == "B" and s["aval"] == "C"
    assert s["ecart_terrain_m"] == 1.5
    # 1.5 m / 100 m = 1.5 % > 1 % → fort ; + radier + azimut → score élevé
    assert s["severite"] in ("fort", "moyen")
    assert any("monte" in m for m in s["motifs"])


def test_endpoint_suspects_ecoulement_absent(db, org_projet):
    """Sans artefact, l'endpoint répond 'absent' proprement."""
    client = TestClient(app)
    pid = org_projet["proj"].id
    tok = org_projet["token"]

    couche = ProjectAuxLayer(
        org_id=org_projet["org"].id, project_id=pid,
        type="altimetrie_points", nom="topo sans artefact 2",
        storage_key="cle-test2", statut="ok", colonne_z="Field4",
    )
    db.add(couche)
    db.commit()

    r = client.get(f"/api/v1/projets/{pid}/aux-layers/{couche.id}/suspects-ecoulement",
                   headers=_h(tok))
    assert r.status_code == 200
    assert r.json()["statut"] == "absent"

    # Couche d'un autre org → stealth 404
    r2 = client.get(f"/api/v1/projets/{pid}/aux-layers/{couche.id}/suspects-ecoulement")
    assert r2.status_code in (401, 404)


def test_analyser_raccordements_terrain():
    """P2 — orphelin proche d'une cible connectée : candidat classé par
    cohérence altimétrique ; orphelin isolé → aucun candidat."""
    import geopandas as gpd
    from shapely.geometry import LineString, Point
    from api.services.aux_altimetrie_service import analyser_raccordements_terrain

    # CRS métrique (UTM-like) pour des distances en mètres
    regards = gpd.GeoDataFrame(
        {"Code": ["A", "B", "O", "O2"], "Profondeur": [2.0, 2.0, 2.0, 2.0]},
        geometry=[Point(100, 0), Point(200, 0), Point(200, 10), Point(5000, 5000)],
        crs="EPSG:32631",
    )
    canas = gpd.GeoDataFrame(
        {"ID_AMANT": ["A"], "ID_AVAL": ["B"], "Longeur": [100.0]},
        geometry=[LineString([(100, 0), (200, 0)])],
        crs="EPSG:32631",
    )
    artefact = {
        "meta": {"gpkg_sha256": "x", "resolution_m": 30.0},
        "regards": {
            "A": {"z_terrain_m": 103.0, "confiance": "haute",
                  "pente_terrain_pct": 1.0, "azimut_pente_deg": 90.0,
                  "lng": 1.0, "lat": 36.0},
            "B": {"z_terrain_m": 100.0, "confiance": "haute",
                  "pente_terrain_pct": 1.0, "azimut_pente_deg": 90.0,
                  "lng": 1.001, "lat": 36.0},
            # O : 10 m au nord de B, terrain plus haut → O→B descend
            "O": {"z_terrain_m": 105.0, "confiance": "haute",
                  "pente_terrain_pct": 1.0, "azimut_pente_deg": 180.0,
                  "lng": 1.001, "lat": 36.0001},
            "O2": {"z_terrain_m": 90.0, "confiance": "haute",
                   "pente_terrain_pct": 1.0, "azimut_pente_deg": 0.0,
                   "lng": 1.05, "lat": 36.05},
        },
    }
    res = analyser_raccordements_terrain(regards, canas, artefact, rayon_max_m=50.0)

    assert res["statut"] == "ok"
    assert res["nb_orphelins"] == 2
    par_code = {r["orphelin"]: r for r in res["orphelins"]}
    # O : cible B à 10 m, terrain descend 105→100, radier cohérent
    o = par_code["O"]
    assert o["candidats"], "O devrait avoir au moins un candidat"
    top = o["candidats"][0]
    assert top["cible"] == "B"
    assert top["distance_m"] == 10.0
    assert top["score"] > 50.0
    assert any("descend" in m for m in top["motifs"])
    # O2 : isolé à >4 km → aucun candidat dans le rayon
    assert par_code["O2"]["candidats"] == []


def test_endpoint_raccordements_orphelins_absent(db, org_projet):
    """Sans artefact, l'endpoint raccordements répond 'absent' + stealth 404."""
    client = TestClient(app)
    pid = org_projet["proj"].id
    tok = org_projet["token"]

    couche = ProjectAuxLayer(
        org_id=org_projet["org"].id, project_id=pid,
        type="altimetrie_points", nom="topo sans artefact 3",
        storage_key="cle-test3", statut="ok", colonne_z="Field4",
    )
    db.add(couche)
    db.commit()

    r = client.get(f"/api/v1/projets/{pid}/aux-layers/{couche.id}/raccordements-orphelins",
                   headers=_h(tok))
    assert r.status_code == 200
    assert r.json()["statut"] == "absent"

    r2 = client.get(f"/api/v1/projets/{pid}/aux-layers/{couche.id}/raccordements-orphelins")
    assert r2.status_code in (401, 404)
