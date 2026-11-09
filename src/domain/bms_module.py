# -*- coding: utf-8 -*-
"""
================================================================================
Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
Auteur : Dr Abdelhakim KELLOUCHE
Date de création : 2026-11-09
Objet : Module de modélisation et simulation des Bulletins Météorologiques Spéciaux (BMS)
         de l'Office National de la Météorologie (ONM Algérie) pour la gestion de proximité
================================================================================
"""

import math
from typing import Dict, Any, List, Tuple, Optional


def calculer_duree_heures(heure_debut: str, heure_fin: str) -> float:
    """
    Calcule la durée en heures décimales entre deux heures au format HH:MM.
    Gère le passage à minuit si heure_fin <= heure_debut.
    """
    try:
        h1, m1 = map(int, heure_debut.strip().split(":"))
        h2, m2 = map(int, heure_fin.strip().split(":"))
        t1 = h1 + m1 / 60.0
        t2 = h2 + m2 / 60.0
        if t2 <= t1:
            t2 += 24.0  # Passage à minuit (ex: 20h00 -> 08h00 le lendemain)
        return round(t2 - t1, 2)
    except Exception:
        return 14.0  # Durée par défaut


def generer_hyetogramme_bms(
    cumul_pluie_mm: float,
    duree_heures: float,
    type_profil: str = "cloche",
    pas_minutes: int = 15,
    r_pic: float = 0.35
) -> Tuple[List[Tuple[str, float]], float]:
    """
    Génère la série temporelle (hyétogramme) d'un BMS pour SWMM 5.2 :
    - cumul_pluie_mm : hauteur cumulée totale en mm annoncée par le BMS (ex: 30 mm)
    - duree_heures : durée totale de validité du bulletin en heures (ex: 14 h)
    - type_profil : 'cloche' (Huff/dissymétrique), 'orage_concentre' ou 'uniforme'
    - pas_minutes : pas de discrétisation temporelle (ex: 15 min)
    - r_pic : position relative du pic pour le profil en cloche (0.35 = pic à 35% de la durée)

    Retourne : (timeseries, intensite_max_mmh)
    """
    cumul_pluie_mm = max(1.0, float(cumul_pluie_mm))
    duree_heures = max(1.0, float(duree_heures))
    pas_heures = pas_minutes / 60.0
    nb_pas = int(math.ceil((duree_heures * 60.0) / pas_minutes))

    # Tableau temporaire des intensités brutes
    raw_intensities: List[float] = []

    if type_profil == "uniforme":
        # Pluie continue régulière : intensité constante I = P_tot / Delta_T
        i_const = round(cumul_pluie_mm / duree_heures, 2)
        raw_intensities = [i_const] * (nb_pas + 1)

    elif type_profil == "orage_concentre":
        # 75% du volume tombe en une averse orageuse concentrée de 2h à 3h
        duree_orage_h = min(2.5, duree_heures * 0.4)
        t_centre_h = duree_heures * r_pic
        sigma_h = duree_orage_h / 2.5

        for step in range(nb_pas + 1):
            t_h = step * pas_heures
            if t_h > duree_heures:
                raw_intensities.append(0.0)
                continue
            # Composante de fond (25%) + Gaussienne orageuse (75%)
            fond = 0.25 / duree_heures
            orage = (0.75 / (sigma_h * math.sqrt(2.0 * math.pi))) * math.exp(-0.5 * ((t_h - t_centre_h) / sigma_h) ** 2)
            raw_intensities.append(fond + orage)

    else:
        # Profil par défaut : "cloche" (forme Huff type II adaptée aux orages méditerranéens)
        # Forme Gamma/Weibull dissymétrique avec pic plus raide et traîne de décrue
        t_pic_h = duree_heures * r_pic
        for step in range(nb_pas + 1):
            t_h = step * pas_heures
            if t_h > duree_heures:
                raw_intensities.append(0.0)
                continue
            if t_h <= t_pic_h:
                # Montée progressive accélérée vers le pic
                ratio = (t_h / max(0.25, t_pic_h)) ** 1.8
            else:
                # Décrue exponentielle après le pic
                t_apres = t_h - t_pic_h
                duree_restante = max(0.5, duree_heures - t_pic_h)
                ratio = math.exp(-2.2 * (t_apres / duree_restante))
            raw_intensities.append(max(0.01, ratio))

    # Normalisation pour que l'intégrale numérique donne exactement cumul_pluie_mm
    # Intégrale trapézoïdale : Somme de (I_prev + I_curr)/2 * dt
    aire_brute = 0.0
    for i in range(1, len(raw_intensities)):
        aire_brute += ((raw_intensities[i - 1] + raw_intensities[i]) / 2.0) * pas_heures

    facteur_echelle = (cumul_pluie_mm / max(1e-6, aire_brute)) if aire_brute > 0 else 1.0

    timeseries: List[Tuple[str, float]] = []
    i_max = 0.0

    for step in range(nb_pas + 1):
        t_min_total = step * pas_minutes
        hh = int(t_min_total // 60)
        mm = int(t_min_total % 60)
        t_str = f"{hh:02d}:{mm:02d}"

        val = round(raw_intensities[step] * facteur_echelle, 2)
        if val > i_max:
            i_max = val
        timeseries.append((t_str, val))

    # Ajouter 1h de ressuyage à intensité nulle à la fin pour permettre la décrue complète du réseau
    t_fin_min = (nb_pas + 1) * pas_minutes
    hh_ress = int((t_fin_min + 60) // 60)
    mm_ress = int((t_fin_min + 60) % 60)
    timeseries.append((f"{hh_ress:02d}:{mm_ress:02d}", 0.0))

    return timeseries, round(i_max, 2)


def creer_scenario_bms(
    cumul_pluie_mm: float = 30.0,
    duree_heures: Optional[float] = None,
    heure_debut: str = "07:00",
    heure_fin: str = "21:00",
    niveau_vigilance: str = "orange",
    type_profil: str = "cloche",
    wilaya: str = "Chlef",
    station_id: str = "chlef_anrh_siege",
    code_bms: str = "BMS-ONM-2026"
) -> Dict[str, Any]:
    """
    Construit un objet scénario complet conforme au standard SWMM 5.2 de DrainPilot.
    """
    if duree_heures is None or duree_heures <= 0:
        duree_heures = calculer_duree_heures(heure_debut, heure_fin)

    vigilance_clean = niveau_vigilance.strip().lower()
    if vigilance_clean not in ("jaune", "orange", "rouge"):
        vigilance_clean = "orange"

    symboles = {
        "jaune": "🟡",
        "orange": "🟠",
        "rouge": "🔴"
    }
    symbole = symboles.get(vigilance_clean, "🟠")

    # Génération de l'hyétogramme dynamique
    timeseries, i_max = generer_hyetogramme_bms(
        cumul_pluie_mm=cumul_pluie_mm,
        duree_heures=duree_heures,
        type_profil=type_profil,
        pas_minutes=15
    )

    nom_scenario = (
        f"{symbole} Alerte météo BMS {vigilance_clean.capitalize()} — "
        f"{cumul_pluie_mm:.0f} mm sur {duree_heures:.0f} h ({heure_debut} → {heure_fin})"
    )

    desc = (
        f"Bulletin Météorologique Spécial (BMS ONM) émis pour la wilaya de {wilaya}. "
        f"Vigilance {vigilance_clean.upper()} : précipitations estimées à {cumul_pluie_mm:.1f} mm "
        f"du {heure_debut} au {heure_fin} (durée d'alerte : {duree_heures:.1f} h). "
        f"Profil d'épisode : {type_profil} (intensité de crête Imax = {i_max:.1f} mm/h)."
    )

    # Durée totale de simulation = durée BMS + 1h de ressuyage
    duree_totale_sim = round(duree_heures + 1.0, 1)

    return {
        "nom": nom_scenario,
        "station": f"Cellule de crise — Wilaya de {wilaya} ({code_bms})",
        "station_id": station_id,
        "periode_retour": f"Alerte BMS {vigilance_clean.capitalize()}",
        "intensite_max_defaut": i_max,
        "duree_heures": duree_totale_sim,
        "duree_bms_heures": duree_heures,
        "formule_montana": f"Hyétogramme BMS {type_profil} (cumul {cumul_pluie_mm:.1f} mm)",
        "coefficients_montana": {"a": 0.0, "b": 0.0},
        "hauteur_p24_mm": cumul_pluie_mm,
        "hauteur_totale_mm": cumul_pluie_mm,
        "source": f"Office National de la Météorologie (ONM Algérie) / Cellule de crise {wilaya}",
        "description": desc,
        "timeseries": timeseries,
        "bms_metadata": {
            "is_bms": True,
            "vigilance": vigilance_clean,
            "symbole": symbole,
            "cumul_mm": cumul_pluie_mm,
            "heure_debut": heure_debut,
            "heure_fin": heure_fin,
            "duree_heures": duree_heures,
            "type_profil": type_profil,
            "wilaya": wilaya,
            "code_bms": code_bms,
            "intensite_pic_mmh": i_max
        }
    }

