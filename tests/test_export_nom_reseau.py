import pytest
from api.routes.simulations import _formater_nom_fichier_export, download_latest_inp, download_latest_rpt
import api.routes.simulations as sim_module


def test_formater_nom_fichier_export_basique():
    assert _formater_nom_fichier_export("Cité des 80 logements", ext="inp") == "Cite_des_80_logements.inp"
    assert _formater_nom_fichier_export("Cité des 80 logements.gpkg", "Bassin_Nord", ext="inp") == "Cite_des_80_logements_Bassin_Nord.inp"
    assert _formater_nom_fichier_export("Assainissement_Ville.gpkg", None, ext="rpt") == "Assainissement_Ville.rpt"
    assert _formater_nom_fichier_export(None, None, ext="inp") == "modele_swmm.inp"


def test_download_simulation_inp_nom_dynamique():
    sim_module._DERNIERE_SIMULATION = {
        "inp_content": "[TITLE]\nTest model content",
        "rpt_content": "SWMM 5.2 Report",
        "project_name": "Cité des 80 logements",
        "meta": {"bassin_nom": "Bassin_Est"}
    }

    res_inp = download_latest_inp(db=None)
    assert res_inp.status_code == 200
    assert 'filename="Cite_des_80_logements_Bassin_Est.inp"' in res_inp.headers.get("content-disposition", "")
    assert res_inp.body.decode("utf-8").startswith("[TITLE]")

    res_rpt = download_latest_rpt(db=None)
    assert res_rpt.status_code == 200
    assert 'filename="Cite_des_80_logements_Bassin_Est.rpt"' in res_rpt.headers.get("content-disposition", "")
    assert "SWMM 5.2 Report" in res_rpt.body.decode("utf-8")
