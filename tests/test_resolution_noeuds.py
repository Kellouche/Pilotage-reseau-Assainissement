# -*- coding: utf-8 -*-
"""
Tests du résolveur topologique canonique (ID -> alias -> snap -> spatial).
"""
import pytest

from src.domain.topologie import (
    PROV_ABSENT,
    PROV_ALIAS,
    PROV_ID,
    PROV_SNAP,
    ResoluteurNoeuds,
)


@pytest.fixture
def resolveur():
    return ResoluteurNoeuds(
        {
            "REG_1": (0.0, 0.0),
            "12": (100.0, 100.0),      # CODE numérique d'un rejet
            "SR_HH01": (200.0, 200.0),
        },
        tolerance_snap_m=0.5,
    )


def test_resolution_par_id(resolveur):
    r = resolveur.resoudre("REG_1", (0.0, 0.0))
    assert r.noeud == "REG_1"
    assert r.provenance == PROV_ID


def test_resolution_par_alias_rj(resolveur):
    # 'RJ12' doit résoudre le rejet CODE '12' — convention GPKG réelle
    r = resolveur.resoudre("RJ12", None)
    assert r.noeud == "12"
    assert r.provenance == PROV_ALIAS


def test_resolution_par_alias_rj_avec_espace(resolveur):
    r = resolveur.resoudre("RJ 12", None)   # _clean_node_id -> 'RJ_12'
    assert r.noeud == "12"
    assert r.provenance == PROV_ALIAS


def test_snap_uniquement_si_id_inconnu(resolveur):
    # ID inconnu + point à 5 cm d'un nœud -> snap
    r = resolveur.resoudre("INCONNU_99", (0.05, 0.0))
    assert r.noeud == "REG_1"
    assert r.provenance == PROV_SNAP
    assert r.distance_m <= 0.5


def test_id_valide_ne_snape_jamais(resolveur):
    # Un ID valide l'emporte TOUJOURS sur le snap, même si un autre
    # nœud est spatialement plus proche du point fourni.
    r = resolveur.resoudre("SR_HH01", (0.0, 0.0))
    assert r.noeud == "SR_HH01"
    assert r.provenance == PROV_ID


def test_snap_hors_tolerance_echoue(resolveur):
    r = resolveur.resoudre("INCONNU_99", (50.0, 50.0))
    assert r.noeud is None
    assert r.provenance == PROV_SNAP  # snap tenté, hors tolérance


def test_absent_sans_id_ni_point(resolveur):
    r = resolveur.resoudre("", None)
    assert r.noeud is None
    assert r.provenance == PROV_ABSENT
