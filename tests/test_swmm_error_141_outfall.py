"""
================================================================================
Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
Auteur : Dr Abdelhakim KELLOUCHE
Date de création : 2026-04-20
Date de modification : 2026-11-08
Objet : Tests de prévention et résolution de l'erreur SWMM 141 (Outfall invalide)
================================================================================
"""

import pytest
from pathlib import Path
from src.domain.moteur_swmm import MoteurSWMM, _assainir_topologie_swmm
from pyswmm import Simulation
import tempfile
import os


def test_sanitizer_resolves_error_141_multiple_inlets():
    """Vérifie que deux conduites convergeant vers un exutoire sont automatiquement assainies."""
    raw_inp = """[OPTIONS]
FLOW_ROUTING         DYNWAVE

[JUNCTIONS]
;;Name           Elevation  MaxDepth
J1               105.000    2.000
J2               104.000    2.000

[OUTFALLS]
;;Name           Elevation  Type
OUT1             100.000    FREE

[CONDUITS]
;;Name           From Node        To Node          Length     Roughness
C1               J1               OUT1             100.00     0.013
C2               J2               OUT1             100.00     0.013

[XSECTIONS]
C1               CIRCULAR     0.600
C2               CIRCULAR     0.600

[COORDINATES]
J1               10.0 20.0
J2               15.0 25.0
OUT1             20.0 30.0
"""
    cleaned_inp = _assainir_topologie_swmm(raw_inp)
    
    # OUT1 doit être converti en regard JUNCTIONS
    assert "OUT1" in cleaned_inp
    assert "OUT_SAFE_OUT1" in cleaned_inp
    assert "C_SAFE_OUT1" in cleaned_inp


def test_sanitizer_resolves_error_141_outlet_from_outfall():
    """Vérifie qu'un exutoire servant de nœud amont est converti pour éviter l'erreur 141."""
    raw_inp = """[OPTIONS]
FLOW_ROUTING         DYNWAVE

[JUNCTIONS]
J1               105.000    2.000

[OUTFALLS]
OUT_BASE         100.000    FREE

[CONDUITS]
C1               J1               OUT_BASE         100.00     0.013
C_EXTRA          OUT_BASE         OTHER_SINK       50.00      0.013

[XSECTIONS]
C1               CIRCULAR     0.600
C_EXTRA          CIRCULAR     0.600
"""
    cleaned_inp = _assainir_topologie_swmm(raw_inp)
    assert "OUT_SAFE_OUT_BASE" in cleaned_inp
    assert "C_SAFE_OUT_BASE" in cleaned_inp


def test_simulation_cluster_with_orphans_no_error_141():
    """Vérifie qu'une simulation complète avec ouvrages orphelins multiples s'exécute sans erreur 141."""
    import glob
    gpkgs = glob.glob("uploads/**/network_Assainissement_Ville.gpkg", recursive=True)
    if not gpkgs:
        pytest.skip("GeoPackage complet non présent dans uploads/.")

    gpkg = gpkgs[0]
    from src.domain.ouvrages_orphelins import detecter_ouvrages_orphelins_proches
    orph_data = detecter_ouvrages_orphelins_proches(gpkg, cluster_id=18)
    ouvs = orph_data.get("ouvrages", [])

    moteur = MoteurSWMM()
    inp, meta = moteur.assembler_modele_inp(
        gpkg_path=gpkg,
        cluster_id=18,
        pente_moyenne_pct=1.0,
        raccordements_orphelins=ouvs
    )

    with tempfile.NamedTemporaryFile(suffix=".inp", delete=False, mode="w", encoding="utf-8") as f:
        f.write(inp)
        p = f.name

    try:
        with Simulation(p) as sim:
            for step in sim:
                break
    finally:
        if os.path.exists(p):
            try:
                os.remove(p)
            except:
                pass

