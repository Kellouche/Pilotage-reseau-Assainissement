"""
================================================================================
Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
Auteur : Dr Abdelhakim KELLOUCHE
Date de création : 2026-04-20
Date de modification : 2026-11-08
Objet : Fonctions utilitaires communes et formatage monétaire / numérique DZD
================================================================================
"""

from typing import Any


def formater_cout_dzd(montant: Any, avec_decimales: bool = True, inclure_unite: bool = True) -> str:
    """Formate un montant en DZD selon les normes comptables francophones (Algérie / ONA) :
    espace comme séparateur de milliers, virgule comme séparateur décimal.
    Exemple : 1446816 -> '1 446 816,00 DZD'
    """
    try:
        val = float(montant or 0.0)
    except (ValueError, TypeError):
        val = 0.0
    if avec_decimales:
        s = f"{val:,.2f}".replace(",", " ").replace(".", ",")
    else:
        s = f"{val:,.0f}".replace(",", " ")
    return f"{s} DZD" if inclure_unite else s


# Alias pour compatibilité
formater_montant_dzd = formater_cout_dzd


def formater_nombre_fr(val: Any, decimales: int = 3) -> str:
    """Formate un nombre décimal avec la virgule française.
    Exemple : 1.716 -> '1,716'
    """
    try:
        fval = float(val or 0.0)
    except (ValueError, TypeError):
        fval = 0.0
    fmt = f"{{:,.{decimales}f}}"
    return fmt.format(fval).replace(",", " ").replace(".", ",")
