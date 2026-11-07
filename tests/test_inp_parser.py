import pytest
from pathlib import Path
import pyogrio

from src.domain.inp_parser import (
    detecter_crs_coordonnees,
    parser_fichier_inp,
    convertir_inp_vers_gpkg
)

SAMPLE_INP_CONTENT = """[TITLE]
;; Test SWMM model
Test Model for INP Parser

[OPTIONS]
FLOW_UNITS          CMS
INFILTRATION        HORTON
FLOW_ROUTING        DYNWAVE
START_DATE          01/01/2026
START_TIME          00:00:00
END_DATE            01/01/2026
END_TIME            04:00:00

[JUNCTIONS]
;;Name           Elevation  MaxDepth   InitDepth  SurDepth   Aponded
J1               105.500    2.500      0.000      0.000      0.000
J2               104.200    2.500      0.000      0.000      0.000
J3               103.000    2.000      0.000      0.000      0.000

[OUTFALLS]
;;Name           Elevation  Type       Stage Data       Gated    Route To
OUT1             100.000    FREE                        NO

[CONDUITS]
;;Name           From Node        To Node          Length     Roughness  InOffset   OutOffset  InitFlow   MaxFlow
C1               J1               J2               120.00     0.0130     0.000      0.000      0.000      0.000
C2               J2               J3               95.00      0.0130     0.000      0.000      0.000      0.000
C3               J3               OUT1             50.00      0.0130     0.000      0.000      0.000      0.000

[XSECTIONS]
;;Link           Shape        Geom1            Geom2      Geom3      Geom4      Barrels    Culvert
C1               CIRCULAR     0.600            0.000      0.000      0.000      1
C2               CIRCULAR     0.800            0.000      0.000      0.000      1
C3               CIRCULAR     1.000            0.000      0.000      0.000      1

[COORDINATES]
;;Node           X-Coord            Y-Coord
J1               554000.000         4006000.000
J2               554100.000         4006050.000
J3               554180.000         4006100.000
OUT1             554220.000         4006120.000

[VERTICES]
;;Link           X-Coord            Y-Coord
C1               554050.000         4006020.000

[SUBCATCHMENTS]
;;Name           RainGage         Outlet           Area     %Imperv  Width    %Slope   CurbLen  SnowPack
SB1              RG1              J1               2.500    60.0     150.0    1.0000   0        
SB2              RG1              J2               1.800    50.0     120.0    1.5000   0

[POLYGONS]
;;Subcatchment   X-Coord            Y-Coord
SB1              553950.000         4005950.000
SB1              554050.000         4005950.000
SB1              554050.000         4006050.000
SB1              553950.000         4006050.000
SB2              554050.000         4006000.000
SB2              554150.000         4006000.000
SB2              554150.000         4006100.000
SB2              554050.000         4006100.000

[MAP]
DIMENSIONS       553900.000 4005900.000 554300.000 4006200.000
Units            Meters
"""


def test_detecter_crs():
    # Coordonnées UTM 31N Chlef
    assert detecter_crs_coordonnees(553000, 4005000, 555000, 4007000) == "EPSG:32631"
    # Coordonnées WGS84
    assert detecter_crs_coordonnees(1.30, 36.15, 1.35, 36.20) == "EPSG:4326"


def test_parser_fichier_inp(tmp_path):
    inp_file = tmp_path / "model.inp"
    inp_file.write_text(SAMPLE_INP_CONTENT, encoding="utf-8")

    sections = parser_fichier_inp(inp_file)
    assert "JUNCTIONS" in sections
    assert "CONDUITS" in sections
    assert "COORDINATES" in sections
    assert "XSECTIONS" in sections
    assert len(sections["JUNCTIONS"]) == 3
    assert len(sections["CONDUITS"]) == 3
    assert len(sections["OUTFALLS"]) == 1


def test_convertir_inp_vers_gpkg(tmp_path):
    inp_file = tmp_path / "model.inp"
    inp_file.write_text(SAMPLE_INP_CONTENT, encoding="utf-8")

    gpkg_out = tmp_path / "model.gpkg"
    res = convertir_inp_vers_gpkg(inp_file, gpkg_out)

    assert res["status"] == "success"
    assert res["conduits_count"] == 3
    assert res["junctions_count"] == 3
    assert res["outfalls_count"] == 1
    assert res["subcatchments_count"] == 2
    assert res["crs"] == "EPSG:32631"

    # Vérification des couches dans le GeoPackage
    layers = dict(pyogrio.list_layers(str(gpkg_out)))
    assert "canalisations" in layers
    assert "regards" in layers
    assert "rejets" in layers
    assert "sous_bassins" in layers

    # Vérification des attributs et géométries des canalisations
    info_c = pyogrio.read_info(str(gpkg_out), layer="canalisations")
    assert info_c["features"] == 3
    assert "ID_AMONT" in info_c["fields"]
    assert "ID_AVAL" in info_c["fields"]
    assert "DIAMETRE" in info_c["fields"]
