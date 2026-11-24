# -*- coding: utf-8 -*-
"""
Tests du vérificateur d'invariants post-simulation et du fix RAINGAGES.

Contexte : bug réel constaté — la ligne RAINGAGES du .inp codait
`INTENSITY 0:05` en dur alors que la série TS_SCENARIO est échantillonnée
à 15 min. SWMM intègre chaque valeur sur l'intervalle déclaré → la pluie
réellement simulée était ~1/3 de la pluie prescrite (17,4 mm au lieu de
53,2 mm sur le bassin 459).
"""
import re

import pytest
import geopandas as gpd
from shapely.geometry import Point, LineString

from src.domain.moteur_swmm.sections_inp import generer_lignes_sections_inp
from src.domain.moteur_swmm.verificateur_invariants import (
    verifier_invariants_simulation,
    _profondeur_pluie_prescrite_mm,
    _surface_totale_inp_ha,
)


def _generer_inp(timeseries):
    regards = gpd.GeoDataFrame({
        "Code": ["R1"], "Profondeur": [2.0], "geometry": [Point(0, 0)]
    })
    canalisations = gpd.GeoDataFrame({
        "ID_AMONT": [None], "ID_AVAL": [None], "Longeur": [10.0],
        "DIAMETRE": [300.0], "MATERIAU": ["PVC"],
        "FORMESECT": ["Circulaire"], "HAUTEUR": [None], "GDEBASE": [None],
        "FONCTIONMT": ["Gravitaire"],
        "geometry": [LineString([(0, 0), (10, 0)])],
    })
    scen = {
        "nom": "test", "duree_heures": 1.0,
        "timeseries": timeseries, "intensite_max_defaut": 50.0,
    }
    swmm_sec = {
        "SUBCATCHMENTS": [";;x"], "SUBAREAS": [";;x"],
        "INFILTRATION": [";;x"], "POLYGONS": [";;x"],
    }
    lines, _ = generer_lignes_sections_inp(
        regards=regards, canalisations=canalisations,
        rejets=gpd.GeoDataFrame(), sb_gdf=gpd.GeoDataFrame(),
        swmm_sec=swmm_sec, scen=scen, duree_sim=1.0, pas_routage_sec=5,
        pente_moyenne_pct=1.0, outfall_code="R1", target_ex_id=None,
        exutoires_map={}, clean_target_nodes={"R1"},
        raccordements_orphelins=None, intensite_max_mmh=50.0,
        active_imperv=65.0, typ_nom="t", typologie_sol="t",
        st_id="s", scenario_key="k", cluster_id=1, bassin_nom="b",
        buf_actuel=25.0,
    )
    return "\n".join(lines)


class TestIntervalRaingage:
    def test_interval_derive_serie_15min(self):
        inp = _generer_inp([
            ("00:00", 0.0), ("00:15", 10.0), ("00:30", 20.0),
            ("00:45", 10.0), ("01:00", 0.0),
        ])
        m = re.search(r"RG1\s+INTENSITY\s+(\S+)", inp)
        assert m, "ligne RAINGAGES absente"
        assert m.group(1) == "0:15"

    def test_interval_derive_serie_10min(self):
        inp = _generer_inp([
            ("00:00", 0.0), ("00:10", 10.0), ("00:20", 20.0),
            ("00:30", 10.0), ("00:40", 0.0),
        ])
        m = re.search(r"RG1\s+INTENSITY\s+(\S+)", inp)
        assert m.group(1) == "0:10"


class TestVerificateurInvariants:
    INP_OK = """[TIMESERIES]
TS_SCENARIO    00:00   0.00
TS_SCENARIO    00:15   10.00
TS_SCENARIO    00:30   20.00
TS_SCENARIO    00:45   10.00
TS_SCENARIO    01:00   0.00
[SUBCATCHMENTS]
SB1   RG1   N1   1.0   65   100   1   0
"""

    RPT_TEMPLATE = """
Runoff Quantity Continuity
  Total Precipitation ...... {vol} {mm}
  Continuity Error (%) ..... {cerr}
Flow Routing Continuity
  Continuity Error (%) ..... {rerr}
"""

    def _rpt(self, mm, cerr=-0.02, rerr=-0.01):
        return self.RPT_TEMPLATE.format(vol="1.000", mm=mm,
                                        cerr=cerr, rerr=rerr)

    def test_conforme_quand_pluie_coherente(self):
        # Hyétogramme : trapèzes (0+10)/2+(10+20)/2+(20+10)/2+(10+0)/2
        # = 40 mm·pas × 0,25 h = 10,0 mm prescrits
        prescrite = _profondeur_pluie_prescrite_mm(self.INP_OK)
        assert prescrite == pytest.approx(10.0, abs=0.01)
        kpis = {
            "total_precipitation_mm": 9.9,
            "runoff_continuity_error_pct": -0.02,
            "routing_continuity_error_pct": -0.01,
            "timeseries": {"runoff_coefficient": 0.4,
                           "lag_time_minutes": 10,
                           "duration_minutes": 240},
        }
        v = verifier_invariants_simulation(self.INP_OK, self._rpt(9.9), kpis)
        assert v["statut"] == "conforme"

    def test_incoherent_quand_pluie_diluee(self):
        # Reproduit le bug 0:05 : .rpt rapporte ~1/3 de la pluie prescrite
        kpis = {
            "total_precipitation_mm": 2.5,
            "runoff_continuity_error_pct": -0.02,
            "routing_continuity_error_pct": -0.01,
            "timeseries": {"runoff_coefficient": 0.4,
                           "lag_time_minutes": 10,
                           "duration_minutes": 240},
        }
        v = verifier_invariants_simulation(self.INP_OK, self._rpt(2.5), kpis)
        assert v["statut"] == "incoherent"
        noms = [c["nom"] for c in v["controles"] if c["statut"] == "incoherent"]
        assert "pluie_prescrite_vs_appliquee" in noms

    def test_surface_somme_sous_bassins(self):
        assert _surface_totale_inp_ha(self.INP_OK) == pytest.approx(1.0)
