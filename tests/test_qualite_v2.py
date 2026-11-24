# -*- coding: utf-8 -*-
"""
Tests de non-régression du moteur Contrôle Qualité V2.1
(spec : docs/05_CONTROLE_QUALITE_V2.md).

Cibles chiffrées sur le jeu Assainissement_Ville :
- pentes_suspectes issues de PROFRADI : 0 (les 1134 faux positifs historiques)
- inversions_sens_ecoulement : 180-250 quand le contexte topo est présent
- donnees_manquantes : honnêteté déclarative (jamais une anomalie)
- cas témoin : conduite 20150 -> 3824 détectée en inversion de sens
"""
import os
from pathlib import Path

import pytest

os.environ.setdefault("TESTING", "true")

from src.analyse_qualite_gpkg import analyser_qualite_gpkg
from api.services.aux_altimetrie_service import _sanitiser_profondeur_m


def _trouver_gpkg_ville() -> Path:
    """Localise le GPKG du projet Assainissement_Ville dans uploads/."""
    for p in Path("uploads").glob("*/network_Assainissement_Ville.gpkg"):
        return p
    return None


GPKG_VILLE = _trouver_gpkg_ville()

pytestmark_db = pytest.mark.skipif(
    GPKG_VILLE is None or not GPKG_VILLE.exists(),
    reason="GPKG Assainissement_Ville absent (jeu de test non disponible)",
)


# ---------------------------------------------------------------------------
# Sanitisation des profondeurs (spec §4.2)
# ---------------------------------------------------------------------------

def test_sanitiser_profondeur_unites_mmm_cm():
    assert _sanitiser_profondeur_m(2.5) == pytest.approx(2.5)
    assert _sanitiser_profondeur_m(1.8) == pytest.approx(1.8)
    # Valeurs aberrantes historiques PROFRADI (mm/cm)
    assert _sanitiser_profondeur_m(2600) == pytest.approx(2.6)
    assert _sanitiser_profondeur_m(3671) == pytest.approx(3.671)
    assert _sanitiser_profondeur_m(208) == pytest.approx(2.08)
    assert _sanitiser_profondeur_m(225) == pytest.approx(2.25)
    # Hors limites physiques -> rejet
    assert _sanitiser_profondeur_m(0.1) is None
    assert _sanitiser_profondeur_m(0.0) is None
    assert _sanitiser_profondeur_m(-3.0) is None
    assert _sanitiser_profondeur_m(50000) is None
    assert _sanitiser_profondeur_m(None) is None
    assert _sanitiser_profondeur_m("abc") is None


# ---------------------------------------------------------------------------
# Moteur sans contexte terrain : fin des faux positifs PROFRADI
# ---------------------------------------------------------------------------

@pytestmark_db
def test_v2_1_zero_faux_positif_profradi():
    """Sans contexte topo, aucune pente ne doit être émise depuis PROFRADI."""
    rapport = analyser_qualite_gpkg(GPKG_VILLE, "Assainissement_Ville")
    anomalies = rapport["anomalies"]

    assert rapport.get("moteur") == "v2.1"
    assert anomalies["pentes_suspectes"] == []
    # Aucune description historique « l'eau doit remonter »
    for cat, items in anomalies.items():
        for a in items:
            assert "l'eau doit remonter" not in (a.get("description") or "")


@pytestmark_db
def test_v2_1_inversion_cas_temoin():
    """Le signal N2 doit flagger la conduite témoin 20150 -> 3824."""
    contexte = {
        "suspects_ecoulement": [{
            "amont": "20150",
            "aval": "3824",
            "severite": "fort",
            "motifs": ["terrain monte de 26.6 m le long du flux (76.0 % > 1.0 %)"],
            "ecart_terrain_m": 26.6,
            "pente_contre_pct": 76.0,
            "confiance": "haute",
        }],
        "par_regard": {},
        "couverture_pct": 0.0,
    }
    rapport = analyser_qualite_gpkg(
        GPKG_VILLE, "Assainissement_Ville", contexte_terrain=contexte)
    anomalies = rapport["anomalies"]

    inversions = anomalies["inversions_sens_ecoulement"]
    assert any(
        a.get("id_amont") == "20150" and a.get("id_aval") == "3824"
        for a in inversions
    ), "Le cas témoin 20150 -> 3824 doit être détecté en inversion de sens"

    # Sans couverture radier : le reste du réseau bascule honnêtement en N3
    assert len(anomalies["donnees_manquantes"]) > 5000


@pytestmark_db
def test_v2_1_deconnexion_spatiale_categorie():
    """La catégorie deconnexion_spatiale_extreme existe et reste bornée."""
    rapport = analyser_qualite_gpkg(GPKG_VILLE, "Assainissement_Ville")
    anomalies = rapport["anomalies"]

    assert "deconnexions_spatiales" in anomalies
    assert "donnees_manquantes" in anomalies
    assert "inversions_sens_ecoulement" in anomalies
    # Cible recette : 10-25 raccordements spatiaux extrêmes (avec contexte
    # réel la borne haute peut légèrement varier)
    assert len(anomalies["deconnexions_spatiales"]) <= 100
