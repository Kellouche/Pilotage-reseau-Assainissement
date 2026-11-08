"""
================================================================================
Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
Auteur : Dr Abdelhakim KELLOUCHE
Date de création : 2026-04-20
Date de modification : 2026-11-08
Objet : Référentiel pluviométrique (Montana, courbes IDF et pluies de projet)
================================================================================
"""

import json
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
import logging

logger = logging.getLogger(__name__)

_CHEMIN_REFERENTIEL_DEFAUT = Path(__file__).resolve().parent.parent.parent / "data" / "referentiel_pluviometrie_algerie.json"
_CACHE_REFERENTIEL: Optional[Dict[str, Any]] = None


def charger_referentiel(chemin_json: Optional[Path] = None) -> Dict[str, Any]:
    """Charge en cache mémoire le référentiel pluviométrique JSON certifié."""
    global _CACHE_REFERENTIEL
    if _CACHE_REFERENTIEL is not None and chemin_json is None:
        return _CACHE_REFERENTIEL

    path = chemin_json or _CHEMIN_REFERENTIEL_DEFAUT
    if not path.exists():
        logger.error("Fichier de référentiel pluviométrique introuvable : %s", path)
        return {"metadata": {}, "wilayas": {}}

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            if chemin_json is None:
                _CACHE_REFERENTIEL = data
            return data
    except Exception as e:
        logger.exception("Erreur lors de la lecture du référentiel pluviométrique : %s", e)
        return {"metadata": {}, "wilayas": {}}


def lister_wilayas() -> List[Dict[str, Any]]:
    """Retourne la liste des wilayas documentées dans le référentiel."""
    ref = charger_referentiel()
    wilayas = []
    for key, val in ref.get("wilayas", {}).items():
        wilayas.append({
            "key": key,
            "nom": val.get("nom", key),
            "code_wilaya": val.get("code_wilaya", ""),
            "bassin": val.get("bassin_hydrographique_national", ""),
            "pluvio_moyenne_an": val.get("pluviometrie_moyenne_annuelle_mm", 0.0),
            "nb_stations": len(val.get("stations", []))
        })
    return wilayas


def obtenir_wilaya(nom_ou_code: str) -> Optional[Dict[str, Any]]:
    """Recherche une wilaya par sa clé, son nom ou son code officiel."""
    ref = charger_referentiel()
    q = nom_ou_code.strip().lower()
    for key, val in ref.get("wilayas", {}).items():
        if key.lower() == q or val.get("code_wilaya", "").lower() == q or q in val.get("nom", "").lower():
            return val
    return None


def lister_stations(wilaya_key: Optional[str] = None) -> List[Dict[str, Any]]:
    """Retourne toutes les stations ou celles d'une wilaya donnée."""
    ref = charger_referentiel()
    stations = []
    for w_key, w_val in ref.get("wilayas", {}).items():
        if wilaya_key and w_key.lower() != wilaya_key.lower():
            continue
        for st in w_val.get("stations", []):
            st_copy = dict(st)
            st_copy["wilaya_key"] = w_key
            st_copy["wilaya_nom"] = w_val.get("nom", w_key)
            stations.append(st_copy)
    return stations


def obtenir_station(station_id: str) -> Optional[Dict[str, Any]]:
    """Recherche une station par son identifiant unique ou son code ANRH."""
    stations = lister_stations()
    s_clean = station_id.strip().lower()
    for st in stations:
        if st.get("id", "").lower() == s_clean or st.get("code_anrh", "").lower() == s_clean:
            return st
    return None


def calculer_intensite_montana(
    station_id: str,
    duree_minutes: float,
    periode_retour: str = "T_10ans"
) -> float:
    """
    Calcule l'intensité de précipitation I(t) en mm/h selon la formule de Montana :
    I(mm/h) = 60 * a * t^(-b) pour t en minutes.
    """
    st = obtenir_station(station_id)
    if not st:
        # Valeur par défaut Chlef Siège T=10ans
        return round(60.0 * 9.334 * (max(duree_minutes, 1.0) ** (-0.745)), 2)

    cfg = st.get("coefficients_montana_uhbc_anrh", {}).get("parametres", {})
    if periode_retour not in cfg:
        periode_retour = "T_10ans" if "T_10ans" in cfg else list(cfg.keys())[0]

    params = cfg[periode_retour]
    a = float(params.get("a", 9.334))
    b = float(params.get("b", 0.745))

    # I en mm/min = a * t^(-b), converti en mm/h par multiplication par 60
    i_mmh = 60.0 * a * (max(duree_minutes, 1.0) ** (-b))
    return round(i_mmh, 2)


def generer_hyetogramme_chicago(
    station_id: str,
    periode_retour: str = "T_10ans",
    duree_heures: float = 4.0,
    pas_minutes: int = 15,
    r: float = 0.40
) -> List[Tuple[str, float]]:
    """
    Génère un hyétogramme de projet synthétique Chicago centré conforme à la formule de Montana.
    r : coefficient d'asymétrie du pic (généralement 0.35 à 0.45 pour les averses orageuses en Algérie).
    """
    st = obtenir_station(station_id)
    if not st:
        st = obtenir_station("chlef_anrh_siege")

    # Si la station possède déjà un profil explicite pré-calé pour T=10ans
    if periode_retour == "T_10ans" and st and "hyetogrammes_chicago" in st:
        pre_profil = st["hyetogrammes_chicago"].get("profil_10ans")
        if pre_profil:
            return [(item["temps"], float(item["intensite_mmh"])) for item in pre_profil]

    # Génération analytique Chicago à partir des coefficients a et b
    cfg = st.get("coefficients_montana_uhbc_anrh", {}).get("parametres", {}) if st else {}
    params = cfg.get(periode_retour, {"a": 9.334, "b": 0.745})
    a = float(params.get("a", 9.334))
    b = float(params.get("b", 0.745))

    # Intensité de pointe cible à tc = 15 min
    i_max_cible = round(60.0 * a * (15.0 ** (-b)), 1)

    steps_count = int((duree_heures * 60) / pas_minutes)
    tp_min = duree_heures * 60.0 * r  # Temps d'occurrence du pic (ex: 96 min pour 4h à r=0.4)

    hyeto: List[Tuple[str, float]] = []
    for step in range(steps_count + 1):
        t_curr = step * pas_minutes
        h_str = f"{t_curr // 60:02d}:{t_curr % 60:02d}"

        dt = abs(t_curr - tp_min)
        if dt < (pas_minutes / 2.0):
            val = i_max_cible
        else:
            # Profil décroissant puissance Montana
            ratio = (15.0 / (dt + 15.0)) ** b
            val = round(i_max_cible * ratio, 2)

        hyeto.append((h_str, val))

    return hyeto


def generer_scenarios_swmm_pour_station(station_id: str) -> Dict[str, Any]:
    """
    Génère le dictionnaire de scénarios SWMM 5.2 prêt à être injecté
    dans MoteurSWMM.SCENARIOS_PLUIE à partir de la station choisie.
    """
    st = obtenir_station(station_id)
    if not st:
        st = obtenir_station("chlef_anrh_siege")
        station_id = "chlef_anrh_siege"

    st_nom = st.get("nom", "Station ANRH Chlef")
    code_anrh = st.get("code_anrh", "010501")
    cfg_montana = st.get("coefficients_montana_uhbc_anrh", {}).get("parametres", {})

    scenarios = {}

    # Scénario 1 : Pluie Décennale T=10 ans (Standard Réglementaire ONA)
    p10 = cfg_montana.get("T_10ans", {"a": 9.334, "b": 0.745, "i_max_15min_mmh": 74.9, "p_cumul_4h_mm": 42.8})
    ts10 = generer_hyetogramme_chicago(station_id, "T_10ans", duree_heures=4.0, pas_minutes=15)
    scenarios["pluie_decennale"] = {
        "nom": f"{st_nom} — Pluie Décennale (T = 10 ans) [Standard ONA]",
        "station": f"{st_nom} (Réf. ANRH {code_anrh})",
        "station_id": station_id,
        "periode_retour": "T = 10 ans (Décennale réglementaire)",
        "intensite_max_defaut": float(p10.get("i_max_15min_mmh", 74.9)),
        "duree_heures": 4.0,
        "formule_montana": f"I(t) = {p10.get('a', 9.334)} · t^(-{p10.get('b', 0.745)}) (UHBC/ANRH, durée critique tc = 15 min)",
        "coefficients_montana": {"a": p10.get("a", 9.334), "b": p10.get("b", 0.745)},
        "hauteur_p24_mm": float(st.get("pluie_journaliere_gumbel_mm", {}).get("T_10ans", 56.0)),
        "hauteur_totale_mm": float(p10.get("p_cumul_4h_mm", 42.8)),
        "source": f"ANRH Antenne Chlef / UHBC Laboratoire Eau & Environnement (Code {code_anrh})",
        "description": f"Pluie d'orage décennale réglementaire ONA selon les séries validées de la station {st_nom} (P24 = {st.get('pluie_journaliere_gumbel_mm', {}).get('T_10ans', 56.0)} mm, Imax = {p10.get('i_max_15min_mmh', 74.9)} mm/h).",
        "timeseries": ts10
    }

    # Scénario 2 : Pluie Cinquantennale T=50 ans (Crise Majeure / Inondations de surface)
    p50 = cfg_montana.get("T_50ans", {"a": 15.795, "b": 0.760, "i_max_15min_mmh": 120.0, "p_cumul_4h_mm": 67.5})
    ts50 = generer_hyetogramme_chicago(station_id, "T_50ans", duree_heures=4.0, pas_minutes=15)
    scenarios["pluie_cinquantennale"] = {
        "nom": f"{st_nom} — Pluie Cinquantennale (T = 50 ans) [Crise Majeure]",
        "station": f"{st_nom} (Réf. ANRH {code_anrh})",
        "station_id": station_id,
        "periode_retour": "T = 50 ans (Cinquantennale)",
        "intensite_max_defaut": float(p50.get("i_max_15min_mmh", 120.0)),
        "duree_heures": 4.0,
        "formule_montana": f"I(t) = {p50.get('a', 15.795)} · t^(-{p50.get('b', 0.760)})",
        "coefficients_montana": {"a": p50.get("a", 15.795), "b": p50.get("b", 0.760)},
        "hauteur_p24_mm": float(st.get("pluie_journaliere_gumbel_mm", {}).get("T_50ans", 81.0)),
        "hauteur_totale_mm": float(p50.get("p_cumul_4h_mm", 67.5)),
        "source": f"ANRH Chlef / Gumbel Extrêmes (Code {code_anrh})",
        "description": f"Événement pluvieux exceptionnel cinquantennal simulant une crise d'inondation majeure (P24 = {st.get('pluie_journaliere_gumbel_mm', {}).get('T_50ans', 81.0)} mm, Imax = {p50.get('i_max_15min_mmh', 120.0)} mm/h).",
        "timeseries": ts50
    }

    # Scénario 3 : Pluie Centennale T=100 ans (Crue Historique)
    p100 = cfg_montana.get("T_100ans", {"a": 19.338, "b": 0.764, "i_max_15min_mmh": 144.5, "p_cumul_4h_mm": 81.0})
    ts100 = generer_hyetogramme_chicago(station_id, "T_100ans", duree_heures=4.0, pas_minutes=15)
    scenarios["pluie_centennale"] = {
        "nom": f"{st_nom} — Pluie Centennale (T = 100 ans) [Crue Historique]",
        "station": f"{st_nom} (Réf. ANRH {code_anrh})",
        "station_id": station_id,
        "periode_retour": "T = 100 ans (Centennale)",
        "intensite_max_defaut": float(p100.get("i_max_15min_mmh", 144.5)),
        "duree_heures": 4.0,
        "formule_montana": f"I(t) = {p100.get('a', 19.338)} · t^(-{p100.get('b', 0.764)})",
        "coefficients_montana": {"a": p100.get("a", 19.338), "b": p100.get("b", 0.764)},
        "hauteur_p24_mm": float(st.get("pluie_journaliere_gumbel_mm", {}).get("T_100ans", 94.0)),
        "hauteur_totale_mm": float(p100.get("p_cumul_4h_mm", 81.0)),
        "source": f"ANRH Chlef / Gumbel-GEV Extrêmes (Code {code_anrh})",
        "description": f"Pluie centennale de submersion totale (P24 = {st.get('pluie_journaliere_gumbel_mm', {}).get('T_100ans', 94.0)} mm, Imax = {p100.get('i_max_15min_mmh', 144.5)} mm/h).",
        "timeseries": ts100
    }

    # Scénario 4 : Pluie Biennale T=2 ans (Pluie Courante)
    p2 = cfg_montana.get("T_2ans", {"a": 5.250, "b": 0.720, "i_max_15min_mmh": 45.0, "p_cumul_4h_mm": 26.0})
    ts2 = generer_hyetogramme_chicago(station_id, "T_2ans", duree_heures=4.0, pas_minutes=15)
    scenarios["pluie_biennale"] = {
        "nom": f"{st_nom} — Pluie Biennale (T = 2 ans) [Pluie Courante]",
        "station": f"{st_nom} (Réf. ANRH {code_anrh})",
        "station_id": station_id,
        "periode_retour": "T = 2 ans (Biennale)",
        "intensite_max_defaut": float(p2.get("i_max_15min_mmh", 45.0)),
        "duree_heures": 4.0,
        "formule_montana": f"I(t) = {p2.get('a', 5.250)} · t^(-{p2.get('b', 0.720)})",
        "coefficients_montana": {"a": p2.get("a", 5.250), "b": p2.get("b", 0.720)},
        "hauteur_p24_mm": float(st.get("pluie_journaliere_gumbel_mm", {}).get("T_2ans", 34.0)),
        "hauteur_totale_mm": float(p2.get("p_cumul_4h_mm", 26.0)),
        "source": f"ANRH Chlef / Fréquentiel (Code {code_anrh})",
        "description": f"Pluie biennale d'exploitation normale (P24 = {st.get('pluie_journaliere_gumbel_mm', {}).get('T_2ans', 34.0)} mm, Imax = {p2.get('i_max_15min_mmh', 45.0)} mm/h).",
        "timeseries": ts2
    }

    # Scénario 5 : Orage estival brutal méditerranéen (2h)
    p20 = cfg_montana.get("T_20ans", {"a": 11.823, "b": 0.752, "i_max_15min_mmh": 92.5, "p_cumul_4h_mm": 52.0})
    scenarios["pluie_orage_2h"] = {
        "nom": f"{st_nom} — Orage d'Été Brutal Méditerranéen (2h — Imax = 92.5 mm/h)",
        "station": f"{st_nom} (Réf. ANRH {code_anrh})",
        "station_id": station_id,
        "periode_retour": "T = 20 ans (Orage Convectif)",
        "intensite_max_defaut": float(p20.get("i_max_15min_mmh", 92.5)),
        "duree_heures": 2.0,
        "formule_montana": f"Averse orageuse convective concentrée (a={p20.get('a', 11.823)}, b={p20.get('b', 0.752)})",
        "coefficients_montana": {"a": p20.get("a", 11.823), "b": p20.get("b", 0.752)},
        "hauteur_p24_mm": float(st.get("pluie_journaliere_gumbel_mm", {}).get("T_20ans", 66.5)),
        "hauteur_totale_mm": 45.0,
        "source": f"Données orages convectifs estivaux Chélif / ANRH (Code {code_anrh})",
        "description": "Averse estivale brève et intense concentrée sur 60 minutes avec pic de crête à 92.5 mm/h.",
        "timeseries": [
            ("00:00", 0.0),
            ("00:10", 12.0),
            ("00:20", 38.0),
            ("00:30", float(p20.get("i_max_15min_mmh", 92.5))),
            ("00:40", 55.0),
            ("00:50", 18.0),
            ("01:00", 4.0),
            ("02:00", 0.0)
        ]
    }

    # Scénario 6 : Temps Sec Pur
    scenarios["temps_sec_pur"] = {
        "nom": "Temps Sec Pur (Étiage / Eaux Usées sans pluie)",
        "station": "Régime d'Étiage Sans Précipitation",
        "station_id": "temps_sec",
        "periode_retour": "Régime Permanent DWF",
        "intensite_max_defaut": 0.0,
        "duree_heures": 24.0,
        "formule_montana": "I = 0 mm/h",
        "coefficients_montana": {"a": 0.0, "b": 0.0},
        "hauteur_p24_mm": 0.0,
        "hauteur_totale_mm": 0.0,
        "source": "Réseau d'assainissement par temps sec",
        "description": "Simulation d'étiage et de transit des eaux usées domestiques sans précipitation.",
        "timeseries": [("00:00", 0.0), ("24:00", 0.0)]
    }

    # Scénario 7 : Saisie Personnalisée
    scenarios["personnalise"] = {
        "nom": "✏️ Saisie Manuelle Ingénieur (Intensité Personnalisée)",
        "station": f"{st_nom} (Profil Personnalisé)",
        "station_id": station_id,
        "periode_retour": "Saisie Manuelle",
        "intensite_max_defaut": float(p10.get("i_max_15min_mmh", 74.9)),
        "duree_heures": 4.0,
        "formule_montana": "Hyétogramme Chicago proportionnel à l'intensité de pointe spécifiée",
        "coefficients_montana": {"a": p10.get("a", 9.334), "b": p10.get("b", 0.745)},
        "hauteur_p24_mm": float(st.get("pluie_journaliere_gumbel_mm", {}).get("T_10ans", 56.0)),
        "hauteur_totale_mm": float(p10.get("p_cumul_4h_mm", 42.8)),
        "source": "Saisie Directe Utilisateur",
        "description": "Pluie de projet personnalisée générée d'après la valeur d'intensité de pointe spécifiée par l'ingénieur.",
        "timeseries": ts10
    }

    for s_key, s_data in scenarios.items():
        s_data["code_anrh"] = code_anrh
        s_data["wilaya"] = st.get("wilaya_nom", "Wilaya de Chlef")

    return scenarios

