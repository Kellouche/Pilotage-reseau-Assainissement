# -*- coding: utf-8 -*-
"""
================================================================================
Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
Objet : LOT P1.2 — Référentiel des apports de temps sec (DWF)

Définit les vocabulaires contrôlés, les profils temporels prédéfinis et les
conversions d'unités des apports de temps sec.

SÉMANTIQUE DES PROFILS TEMPORELS (compatibilité SWMM [PATTERNS]) :
--------------------------------------------------------------------------------
Un profil SWMM [PATTERNS] est une grille de 7 jours × 24 facteurs horaires.
Le débit injecté à l'instant t est :

    Q(t) = Q_moyen_reférence × facteur(jour_semaine(t), heure(t))

où Q_moyen_reférence est le débit moyen journalier de l'apport.
IMPORTANT : les facteurs sont des MULTIPLICATEURS sans contrainte de moyenne
unitaire — le profil décrit la forme de la variation, pas une conservation
stricte du volume. Les profils prédéfinis ci-dessous sont normalisés pour que
la moyenne des 168 facteurs vaille 1.0 (volumes cohérents avec le débit moyen).

UNITÉS CANONIQUES :
- Débit : m³/s (CMS) — cohérent avec FLOW_UNITS CMS du fichier .inp.
- Débit spécifique domestique : L/hab/jour.
- EH : nombre d'équivalents-habitants (1 EH ≈ 1 habitant).

Ce module ne génère AUCUNE section INP (lot P1.3).
================================================================================
"""

from typing import Dict, Any, List

# ---------------------------------------------------------------------------
# Vocabulaires contrôlés
# ---------------------------------------------------------------------------

NATURES_APPORT = ("domestique", "industriel", "infiltration", "autre")

MODES_DETERMINATION = ("debit", "eh")

PROFILS_DWF_KEYS = ("constant", "journalier_type", "hebdomadaire")

# ---------------------------------------------------------------------------
# Constantes de conversion
# ---------------------------------------------------------------------------

#: Débit spécifique unitaire par défaut (eau usée domestique unitaire).
#: Référence courante assainissement : 150-250 L/hab/j ; valeur médiane retenue.
DEBIT_SPECIFIQUE_DEFAUT_L_HAB_J = 200.0

SECONDES_PAR_JOUR = 86400.0
LITRES_PAR_M3 = 1000.0


def eh_vers_debit_m3s(eh: float, debit_specifique_l_hab_j: float) -> float:
    """Convertit un apport en équivalents-habitants en débit moyen m³/s.

    Q (m³/s) = EH × q_spéc (L/hab/j) / (1000 L/m³ × 86400 s/j)
    """
    return (float(eh) * float(debit_specifique_l_hab_j)
            / (LITRES_PAR_M3 * SECONDES_PAR_JOUR))


def _normaliser_moyenne_168(facteurs: List[float]) -> List[float]:
    """Normalise 168 facteurs (7 j × 24 h) pour moyenne = 1.0."""
    if len(facteurs) != 168:
        raise ValueError("Un profil DWF SWMM doit contenir 168 facteurs (7 jours × 24 h).")
    moyenne = sum(facteurs) / 168.0
    if moyenne <= 0:
        raise ValueError("La moyenne des facteurs d'un profil DWF doit être > 0.")
    return [round(f / moyenne, 4) for f in facteurs]


def _profil_journalier(courbe_24h: List[float]) -> List[float]:
    """Répète une courbe journalière type sur les 7 jours de la semaine."""
    assert len(courbe_24h) == 24
    return _normaliser_moyenne_168(list(courbe_24h) * 7)


# ---------------------------------------------------------------------------
# Profils prédéfinis — forme type des apports unitaires de temps sec
# ---------------------------------------------------------------------------
#
# Convention d'index : jour 0 = dimanche … jour 6 = samedi (convention SWMM).
# Les valeurs ci-dessous sont des facteurs multiplicateurs horaires.

# Courbe journalière type (eau usée unitaire, semaine) :
#   nuit creuse ~0.55 (00h-05h), montée 06h-09h, pointe matinale ~1.35,
#   milieu de journée ~1.0, pointe vesprale ~1.30 (18h-21h), décrue nocturne.
_COURBE_JOURNALIER_TYPE_24H = [
    0.55, 0.52, 0.50, 0.50, 0.52, 0.58,   # 00h-05h : étiage nocturne
    0.75, 1.10, 1.35, 1.30, 1.15, 1.05,   # 06h-11h : pointe matinale
    1.00, 0.98, 1.00, 1.05, 1.12, 1.22,   # 12h-17h : remontée vesprale
    1.32, 1.28, 1.15, 0.95, 0.75, 0.62,   # 18h-23h : pointe du soir puis décrue
]

# Dimanche : profil moins marqué (activité réduite), moyenne identique.
_COURBE_DIMANCHE_24H = [
    0.60, 0.58, 0.56, 0.55, 0.57, 0.62,
    0.80, 1.00, 1.15, 1.10, 1.00, 0.95,
    0.92, 0.95, 0.98, 1.02, 1.08, 1.15,
    1.20, 1.15, 1.05, 0.90, 0.75, 0.66,
]

# Samedi : intermédiaire entre semaine et dimanche.
_COURBE_SAMEDI_24H = [
    0.58, 0.55, 0.53, 0.53, 0.55, 0.60,
    0.78, 1.05, 1.25, 1.22, 1.10, 1.02,
    0.98, 0.98, 1.00, 1.06, 1.14, 1.24,
    1.30, 1.25, 1.12, 0.95, 0.72, 0.64,
]

# Profil hebdomadaire : lun-ven = journalier type, sam = atténué, dim = creux.
_FACTEURS_HEBDOMADAIRE = (
    _COURBE_DIMANCHE_24H            # dimanche (jour 0)
    + _COURBE_JOURNALIER_TYPE_24H * 5   # lundi-vendredi (jours 1 à 5)
    + _COURBE_SAMEDI_24H            # samedi (jour 6)
)
assert len(_FACTEURS_HEBDOMADAIRE) == 168


def _facteurs_constant() -> List[float]:
    return [1.0] * 168


PROFILS_DWF: Dict[str, Dict[str, Any]] = {
    "constant": {
        "nom": "Débit constant",
        "description": (
            "Apport uniforme : facteur 1.0 à chaque pas de temps. "
            "Recommandé pour les apports industriels continus et les "
            "infiltrations parasites permanentes."
        ),
        "type_swmm": "PATTERN",
        "facteurs_168": _facteurs_constant(),
    },
    "journalier_type": {
        "nom": "Profil journalier type (eau usée unitaire)",
        "description": (
            "Variation diurne type des eaux usées domestiques : étiage "
            "nocturne (~0.5×), pointe matinale (~1.35× vers 9h) et pointe "
            "vesprale (~1.3× vers 20h). Identique les 7 jours."
        ),
        "type_swmm": "PATTERN",
        "facteurs_168": _profil_journalier(_COURBE_JOURNALIER_TYPE_24H),
    },
    "hebdomadaire": {
        "nom": "Profil hebdomadaire (semaine / week-end)",
        "description": (
            "Combine le profil journalier type en semaine (lun-ven), une "
            "atténuation le samedi et un creux le dimanche."
        ),
        "type_swmm": "PATTERN",
        "facteurs_168": _normaliser_moyenne_168(list(_FACTEURS_HEBDOMADAIRE)),
    },
}


def obtenir_profil_dwf(profile_key: str) -> Dict[str, Any]:
    """Retourne la définition d'un profil prédéfini (KeyError si inconnu)."""
    return PROFILS_DWF[profile_key]


def lister_profils_dwf() -> List[Dict[str, Any]]:
    """Liste les profils disponibles pour l'API (métadonnées + facteurs)."""
    return [
        {
            "key": key,
            "nom": p["nom"],
            "description": p["description"],
            "type_swmm": p["type_swmm"],
            "nb_facteurs": len(p["facteurs_168"]),
            "moyenne_facteurs": round(
                sum(p["facteurs_168"]) / len(p["facteurs_168"]), 4),
            "facteurs_168": p["facteurs_168"],
        }
        for key, p in PROFILS_DWF.items()
    ]
