# -*- coding: utf-8 -*-
"""
================================================================================
Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
Objet : Vérificateur d'invariants post-simulation SWMM 5.2

Compare ce que le fichier .inp PRESCRIT (hyétogramme, surface) à ce que le
moteur a RÉELLEMENT simulé (.rpt), puis vérifie les lois physiques
d'invariants censées être vraies pour toute simulation :

  1. Pluie appliquée (.rpt « Total Precipitation ») ≈ pluie prescrite
     (intégrale de l'hyétogramme .inp). Écart > 10 % → incohérence
     (cas réel détecté : intervalle RAINGAGES 0:05 sur série 15 min
     diluait la pluie d'un facteur ~3).
  2. Erreurs de continuité massique SWMM (runoff / routing) ≤ seuil.
  3. Coefficient de ruissellement dans des bornes physiques plausibles.
  4. Lag pic-pluie → pic-exutoire ≤ durée de simulation.

Le verdict est stocké dans kpis["verification_invariants"] pour être
surfaced dans l'UI et les logs — une simulation « incoherente » ne doit
jamais passer inaperçue.
================================================================================
"""

import logging
import re
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("swmm_platform.moteur_swmm.verificateur_invariants")

SEUIL_ECART_PLUIE = 0.10       # 10 % d'écart prescrite/appliquée → incohérent
SEUIL_CONTINUITE_ALERTE = 1.0  # % — au-delà, à surveiller
SEUIL_CONTINUITE_MAX = 5.0     # % — au-delà, incohérent (aligné compliance_continuity)
SEUIL_CR_MAX = 1.5             # Cr > 1.5 physiquement suspect (DWF peut pousser >1)


def _parse_timeseries_inp(texte_inp: str) -> List[Tuple[float, float]]:
    """Extrait les points (minute, intensite_mmh) de la section [TIMESERIES]
    contenant TS_SCENARIO (l'hyétogramme de pluie, pas les séries DWF)."""
    points: List[Tuple[float, float]] = []
    in_ts = False
    for line in texte_inp.splitlines():
        s = line.strip()
        if not s or s.startswith(";"):
            continue
        if s.startswith("["):
            in_ts = s.upper() == "[TIMESERIES]"
            continue
        if in_ts:
            parts = s.split()
            if len(parts) >= 3 and parts[0].startswith("TS_SCENARIO"):
                try:
                    t_parts = parts[1].split(":")
                    m = float(t_parts[0]) * 60.0 + float(t_parts[1])
                    points.append((m, float(parts[2])))
                except Exception:
                    pass
    points.sort(key=lambda x: x[0])
    return points


def _profondeur_pluie_prescrite_mm(texte_inp: str) -> Optional[float]:
    """Intégrale trapézoïdale de l'hyétogramme TS_SCENARIO (mm)."""
    pts = _parse_timeseries_inp(texte_inp)
    if len(pts) < 2:
        return None
    total = 0.0
    for i in range(1, len(pts)):
        dt_h = (pts[i][0] - pts[i - 1][0]) / 60.0
        total += (pts[i][1] + pts[i - 1][1]) / 2.0 * dt_h
    return round(total, 2)


def _surface_totale_inp_ha(texte_inp: str) -> float:
    """Somme des surfaces [SUBCATCHMENTS] (colonne Area, ha en unités CMS)."""
    total = 0.0
    in_sub = False
    for line in texte_inp.splitlines():
        s = line.strip()
        if not s or s.startswith(";"):
            continue
        if s.startswith("["):
            in_sub = s.upper() == "[SUBCATCHMENTS]"
            continue
        if in_sub:
            parts = s.split()
            # Format : Nom Raingage Outlet Area %Imperv Width Slope CurbLen
            if len(parts) >= 4:
                try:
                    total += float(parts[3])
                except Exception:
                    pass
    return round(total, 2)


def verifier_invariants_simulation(
    inp_content: Optional[str],
    rpt_text: Optional[str],
    kpis: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Vérifie les invariants post-simulation. Retourne un verdict structuré :
      {"statut": "conforme"|"a_surveiller"|"incoherent",
       "controles": [{"nom","statut","detail","valeur"}],
       "pluie_prescrite_mm", "pluie_appliquee_mm", ...}
    Ne lève jamais d'exception — en cas de donnée manquante le contrôle
    est marqué "non_verifiable".
    """
    kpis = kpis or {}
    timeseries = kpis.get("timeseries") or {}
    controles: List[Dict[str, Any]] = []
    statut_global = "conforme"

    def _ajouter(nom: str, statut: str, detail: str, valeur: Any = None) -> None:
        nonlocal statut_global
        controles.append({"nom": nom, "statut": statut, "detail": detail, "valeur": valeur})
        if statut == "incoherent":
            statut_global = "incoherent"
        elif statut == "a_surveiller" and statut_global == "conforme":
            statut_global = "a_surveiller"

    # ── 1. Pluie prescrite vs appliquée ──────────────────────────────────
    pluie_prescrite = _profondeur_pluie_prescrite_mm(inp_content) if inp_content else None
    m_appliquee = re.search(
        r"Total Precipitation\s*[\.]+\s+[\d\.]+\s+([\d\.]+)", rpt_text or ""
    )
    pluie_appliquee = float(m_appliquee.group(1)) if m_appliquee else None
    if pluie_appliquee is None:
        m2 = re.search(r"Total Precipitation\s*[\.]+\s+([\d\.]+)\s+([\d\.]+)", rpt_text or "")
        pluie_appliquee = float(m2.group(2)) if m2 else None

    if pluie_prescrite and pluie_appliquee is not None and pluie_prescrite > 0:
        ecart = abs(pluie_appliquee - pluie_prescrite) / pluie_prescrite
        if ecart <= SEUIL_ECART_PLUIE:
            _ajouter("pluie_prescrite_vs_appliquee", "conforme",
                     f"Écart {ecart * 100:.1f} % entre hyétogramme .inp et pluie .rpt",
                     {"prescrite_mm": pluie_prescrite, "appliquee_mm": pluie_appliquee,
                      "ecart_pct": round(ecart * 100, 1)})
        else:
            _ajouter("pluie_prescrite_vs_appliquee", "incoherent",
                     f"La pluie réellement simulée ({pluie_appliquee} mm) s'écarte de "
                     f"{ecart * 100:.0f} % de l'hyétogramme prescrit ({pluie_prescrite} mm) "
                     "— vérifier l'intervalle RAINGAGES du .inp",
                     {"prescrite_mm": pluie_prescrite, "appliquee_mm": pluie_appliquee,
                      "ecart_pct": round(ecart * 100, 1)})
    else:
        _ajouter("pluie_prescrite_vs_appliquee", "non_verifiable",
                 "Hyétogramme .inp ou Total Precipitation .rpt illisible",
                 {"prescrite_mm": pluie_prescrite, "appliquee_mm": pluie_appliquee})

    # ── 2. Continuité massique ───────────────────────────────────────────
    for cle, seuil_alerte in (("runoff_continuity_error_pct", True),
                              ("routing_continuity_error_pct", True)):
        val = kpis.get(cle)
        if val is None:
            _ajouter(cle, "non_verifiable", "Indicateur absent du rapport .rpt")
            continue
        av = abs(float(val))
        if av > SEUIL_CONTINUITE_MAX:
            _ajouter(cle, "incoherent",
                     f"Erreur de continuité {val} % > {SEUIL_CONTINUITE_MAX} %",
                     val)
        elif av > SEUIL_CONTINUITE_ALERTE:
            _ajouter(cle, "a_surveiller",
                     f"Erreur de continuité {val} % (> {SEUIL_CONTINUITE_ALERTE} %)", val)
        else:
            _ajouter(cle, "conforme", f"Erreur de continuité {val} %", val)

    # ── 3. Coefficient de ruissellement ─────────────────────────────────
    cr = timeseries.get("runoff_coefficient")
    if cr is not None:
        cr_f = float(cr)
        if cr_f < 0 or cr_f > SEUIL_CR_MAX:
            _ajouter("runoff_coefficient", "a_surveiller",
                     f"Cr = {cr_f} hors bornes physiques plausibles [0, {SEUIL_CR_MAX}]",
                     cr_f)
        else:
            _ajouter("runoff_coefficient", "conforme", f"Cr = {cr_f}", cr_f)
    else:
        _ajouter("runoff_coefficient", "non_verifiable", "Absent des séries temporelles")

    # ── 4. Lag ≤ durée de simulation ────────────────────────────────────
    lag = timeseries.get("lag_time_minutes")
    duree = timeseries.get("duration_minutes") or kpis.get("duree_simulation_minutes")
    if lag is not None and duree:
        if float(lag) > float(duree):
            _ajouter("lag_vs_duree", "incoherent",
                     f"Lag {lag} min > durée simulation {duree} min", lag)
        else:
            _ajouter("lag_vs_duree", "conforme",
                     f"Lag {lag} min ≤ durée {duree} min", lag)
    else:
        _ajouter("lag_vs_duree", "non_verifiable", "lag ou durée absent")

    return {
        "statut": statut_global,
        "controles": controles,
        "pluie_prescrite_mm": pluie_prescrite,
        "pluie_appliquee_mm": pluie_appliquee,
        "surface_totale_ha": _surface_totale_inp_ha(inp_content) if inp_content else None,
    }


def harmoniser_pluie_appliquee(kpis: Dict[str, Any]) -> None:
    """
    Aligne les métriques de pluie des séries temporelles sur la pluie
    RÉELLEMENT appliquée lue dans le .rpt (et non sur l'hyétogramme .inp
    prescrit). Corrige volume de pluie et coefficient de ruissellement.
    No-op si la donnée .rpt est absente.
    """
    timeseries = kpis.get("timeseries")
    if not isinstance(timeseries, dict):
        return
    pluie_appliquee = kpis.get("total_precipitation_mm")
    surface = timeseries.get("total_surface_ha") or 0.0
    if pluie_appliquee is None or surface <= 0:
        return
    try:
        pluie_appliquee = float(pluie_appliquee)
        surface = float(surface)
    except Exception:
        return
    outflow_vol = float(timeseries.get("total_outflow_volume_m3") or 0.0)
    prescrite = timeseries.get("total_precipitation_mm")
    rain_vol = round(surface * pluie_appliquee * 10.0, 1)
    timeseries["pluie_prescrite_mm"] = prescrite
    timeseries["total_precipitation_mm"] = round(pluie_appliquee, 2)
    timeseries["total_rain_volume_m3"] = rain_vol
    timeseries["pluie_source"] = "rpt_appliquee"
    if rain_vol > 0:
        timeseries["runoff_coefficient"] = round(outflow_vol / rain_vol, 2)
        timeseries["runoff_coefficient_source"] = "exutoire_sur_pluie_appliquee"
