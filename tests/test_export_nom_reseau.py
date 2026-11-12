"""
================================================================================
Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
Auteur : Dr Abdelhakim KELLOUCHE
Date de création : 2026-04-20
Date de modification : 2026-11-08
Objet : Tests d'exportation des données réseau et conventions de nommage
================================================================================
"""

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from api.routes.simulations import _formater_nom_fichier_export, download_latest_inp, download_latest_rpt
from api.database import SessionLocal
from api.models import Organization, Project, Simulation


def test_formater_nom_fichier_export_basique():
    assert _formater_nom_fichier_export("Cité des 80 logements", ext="inp") == "Cite_des_80_logements.inp"
    assert _formater_nom_fichier_export("Cité des 80 logements.gpkg", "Bassin_Nord", ext="inp") == "Bassin_Nord.inp"
    assert _formater_nom_fichier_export("Assainissement_Ville.gpkg", None, ext="rpt") == "Assainissement_Ville.rpt"
    assert _formater_nom_fichier_export(None, None, ext="inp") == "modele_swmm.inp"


def test_download_simulation_inp_nom_dynamique(tmp_path):
    """3D.2 — les téléchargements servent la simulation AUTORISÉE du contexte
    (ligne Simulation persistée), plus la globale _DERNIERE_SIMULATION."""
    db = SessionLocal()
    sfx = uuid.uuid4().hex[:10]
    org = Organization(id=f"org_{sfx}", name="Org", slug=f"org-{sfx}")
    db.add(org)
    db.flush()
    proj = Project(id=f"proj_{sfx}", org_id=org.id, name="Cité des 80 logements")
    db.add(proj)
    db.commit()

    data = {
        "inp_content": "[TITLE]\nTest model content",
        "rpt_content": "SWMM 5.2 Report",
        "project_name": "Cité des 80 logements",
        "meta": {"bassin_nom": "Bassin_Est", "cluster_id": 1,
                 "bbox": [3.0, 36.0, 3.1, 36.1]},
        "node_results": {"N1": {"hgl": 1.0}},
        "conduit_results": {"C1": {"q": 0.1}},
    }
    fjson = tmp_path / f"sim_{sfx}.json"
    fjson.write_text(json.dumps(data), encoding="utf-8")
    sim = Simulation(
        id=str(uuid.uuid4()), org_id=org.id, project_id=proj.id,
        name="SWMM_test", status="completed", scenario_pluie="pluie_decennale",
        duree_heures=4.0, results_s3_key=str(fjson.resolve()),
        summary_kpis={"cluster_id": 1, "parameters": {}},
        created_at=datetime.now(timezone.utc),
    )
    db.add(sim)
    db.commit()

    tenant = SimpleNamespace(org_id=org.id)
    try:
        res_inp = download_latest_inp(db=db, tenant=tenant)
        assert res_inp.status_code == 200
        assert 'filename="Bassin_Est.inp"' in res_inp.headers.get("content-disposition", "")
        assert res_inp.body.decode("utf-8").startswith("[TITLE]")

        res_rpt = download_latest_rpt(db=db, tenant=tenant)
        assert res_rpt.status_code == 200
        assert 'filename="Bassin_Est.rpt"' in res_rpt.headers.get("content-disposition", "")
        assert "SWMM 5.2 Report" in res_rpt.body.decode("utf-8")
    finally:
        db.delete(sim)
        db.delete(proj)
        db.delete(org)
        db.commit()
        db.close()
