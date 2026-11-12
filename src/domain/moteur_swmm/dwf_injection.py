# -*- coding: utf-8 -*-
"""
================================================================================
Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
Objet : LOT P1.3 — Injection des apports de temps sec (DWF) dans le .inp SWMM

Génère les sections [PATTERNS], [DWF], [INFLOWS] et les lignes [TIMESERIES]
correspondantes à partir des apports DWF résolus pour un projet.

RÈGLES D'INJECTION (vérifiées sur SWMM 5.2.4 — contrôle P1.2) :
--------------------------------------------------------------------------------
- Une SEULE ligne [DWF] FLOW par nœud (un doublon écrase le précédent).
- Une SEULE ligne [INFLOWS] FLOW par nœud (idem).
- [DWF] et [INFLOWS] sur un même nœud s'ADDITIONNENT (vérifié).
- Types de [PATTERNS] reconnus par ce build : HOURLY (24 h, répété chaque
  jour), DAILY (7 jours), WEEKEND (sam+dim), MONTHLY. Aucun type « 7 jours »
  horaire n'existe : la grille 168 arbitraire n'est pas représentable par
  patterns seuls.

Méthode par profil :
- "constant"        → [DWF] sans pattern (Q constant).
- "journalier_type" → [DWF] + [PATTERNS] HOURLY (24 facteurs, 1er jour).
- "hebdomadaire"    → [INFLOWS] + [TIMESERIES] (série exacte 168 h).
- tout autre profil → [INFLOWS] + [TIMESERIES] (extensibilité).

Nœud multi-apports : les apports éligibles à [DWF] (constant / journalier)
occupent le slot [DWF] par priorité journalier > constant ; tous les autres
sont fusionnés en UNE [TIMESERIES] par nœud (somme exacte des débits).
Un même apport n'est jamais injecté par les deux mécanismes.

CONSERVATION DU DÉBIT MOYEN :
- Les facteurs stockés (arrondis à 4 décimales) peuvent avoir une moyenne
  légèrement ≠ 1. Avant injection, on renormalise chaque profil par sa
  moyenne effective : f_eff = f / mean(f). Le débit moyen injecté est
  alors exactement debit_moyen_m3s sur une semaine complète.
- Pour [DWF]+HOURLY, la valeur de base est divisée par la moyenne des 24
  facteurs émis (≈1) par sécurité.
- Pour [TIMESERIES], les valeurs absolues Q(t) = Σ Q_i × f_eff_i(idx(t))
  sont émises avec des points horaires doublés (valeur à h:00 et à
  h:59:59) : l'interpolation linéaire SWMM produit des marches quasi
  exactes (transition rampe d'1 s aux changements d'heure).

INDEX TEMPOREL : jour 0 = dimanche … jour 6 = samedi (convention SWMM
[DAILY] et PROFILS_DWF). Calculé depuis la date calendaire absolue —
les simulations commençant un autre jour et celles de plusieurs semaines
sont gérées sans cas particulier.
================================================================================
"""

import hashlib
import json
import logging
import re
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from src.domain.apports_dwf import PROFILS_DWF

logger = logging.getLogger("swmm_platform.moteur_swmm.dwf_injection")

# Slot [DWF] : profils dont la forme est native SWMM. Priorité décroissante.
_PROFILS_NATIVE_DWF = ("journalier_type", "constant")

_HEURE_PAR_JOUR = 24


def _json_canonique(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, default=str)


def empreinte_apports_dwf(apports: List[Dict[str, Any]]) -> str:
    """Empreinte SHA-256 du jeu d'apports résolu (identité de cache)."""
    return hashlib.sha256(_json_canonique(apports).encode("utf-8")).hexdigest()


def _facteurs_normalises(profile_key: str) -> Optional[List[float]]:
    """
    Facteurs 168 du profil, renormalisés pour moyenne EXACTE = 1
    (correction de la dérive d'arrondi à 4 décimales des données stockées).
    Retourne None si le profil est inconnu.
    """
    profil = PROFILS_DWF.get(profile_key)
    if not profil:
        return None
    bruts = [float(v) for v in profil["facteurs_168"]]
    if len(bruts) != 168:
        return None
    moyenne = sum(bruts) / 168.0
    if moyenne <= 0:
        return None
    return [v / moyenne for v in bruts]


def _index_calendaire(moment: datetime) -> int:
    """Index du facteur 168 pour un instant : jour 0 = dimanche … 6 = samedi."""
    # datetime.weekday() : lundi=0 … dimanche=6 → décalage pour dimanche=0.
    jour = (moment.weekday() + 1) % 7
    return jour * _HEURE_PAR_JOUR + moment.hour


def _fmt_ts_date(moment: datetime) -> str:
    return f"{moment:%m/%d/%Y %H:%M:%S}"


def _sanitizer_nom(prefix: str, node_id: str) -> str:
    """Nom SWMM sûr (alphanumérique + _ -) pour séries/patterns."""
    propre = re.sub(r"[^A-Za-z0-9_\-]+", "_", str(node_id)).strip("_")
    return f"{prefix}{propre or 'X'}"


def construire_injection_dwf(
    apports: Optional[List[Dict[str, Any]]],
    noeuds_inp: set,
    debut: datetime,
    fin: datetime,
) -> Dict[str, Any]:
    """
    Construit les lignes INP d'injection DWF.

    `apports` : liste de dicts résolus (champs ApportDwf.to_dict()).
    `noeuds_inp` : ensemble des noms de nœuds JUNCTION émis dans le .inp —
        un apport sur un nœud absent du réseau simulé est ignoré (P1.4
        assurera la liaison à la version GPKG exacte).
    `debut`/`fin` : fenêtre temporelle absolue de la simulation.

    Retourne :
      pattern_lines, dwf_lines, inflow_lines, timeseries_lines : lignes INP ;
      apports_meta : traçabilité par apport (provenance) ;
      ignores : apports non injectés et motif.
    """
    resultat: Dict[str, Any] = {
        "pattern_lines": [],
        "dwf_lines": [],
        "inflow_lines": [],
        "timeseries_lines": [],
        "apports_meta": [],
        "ignores": [],
    }
    if not apports:
        return resultat

    # ---- 1. Filtrage : nœud présent dans le .inp, profil connu, q > 0 ----
    injectables: List[Tuple[Dict[str, Any], List[float], float]] = []
    for a in apports:
        if not a.get("actif", True):
            resultat["ignores"].append({"apport_id": a.get("id"),
                                        "node_id": a.get("node_id"),
                                        "motif": "inactif"})
            continue
        nid = str(a.get("node_id") or "").strip()
        if nid not in noeuds_inp:
            resultat["ignores"].append({"apport_id": a.get("id"),
                                        "node_id": nid or None,
                                        "motif": "noeud_absent_du_inp"})
            continue
        q = float(a.get("debit_moyen_m3s") or 0.0)
        if q <= 0:
            resultat["ignores"].append({"apport_id": a.get("id"),
                                        "node_id": nid,
                                        "motif": "debit_nul"})
            continue
        facteurs = _facteurs_normalises(a.get("profile_key") or "constant")
        if facteurs is None:
            resultat["ignores"].append({"apport_id": a.get("id"),
                                        "node_id": nid,
                                        "motif": f"profil_inconnu:{a.get('profile_key')}"})
            continue
        injectables.append((a, facteurs, q))

    if not injectables:
        return resultat

    # ---- 2. Groupement par nœud ----
    par_noeud: Dict[str, List[Tuple[Dict[str, Any], List[float], float]]] = {}
    for item in injectables:
        par_noeud.setdefault(str(item[0].get("node_id")).strip(), []).append(item)

    # Pattern HOURLY mutualisé pour tous les apports "journalier_type"
    # (même profil → mêmes 24 facteurs).
    pattern_journalier_emis = False

    for nid in sorted(par_noeud):
        groupe = par_noeud[nid]
        profils = {str(a.get("profile_key") or "constant") for a, _, _ in groupe}

        # Slot [DWF] : priorité journalier_type > constant (un seul Flux DWF
        # par nœud — un doublon [DWF] écraserait le précédent).
        slot_dwf = None
        for cand in _PROFILS_NATIVE_DWF:
            if cand in profils:
                slot_dwf = cand
                break

        # Apports du slot [DWF]
        if slot_dwf == "journalier_type":
            membres_dwf = [(a, f, q) for a, f, q in groupe
                           if a.get("profile_key") == "journalier_type"]
            reste = [(a, f, q) for a, f, q in groupe
                     if a.get("profile_key") != "journalier_type"]
        elif slot_dwf == "constant":
            membres_dwf = [(a, f, q) for a, f, q in groupe
                           if a.get("profile_key") == "constant"]
            reste = [(a, f, q) for a, f, q in groupe
                     if a.get("profile_key") != "constant"]
        else:
            membres_dwf = []
            reste = list(groupe)

        q_dwf = sum(q for _, _, q in membres_dwf)

        # ---- Ligne [DWF] ----
        if q_dwf > 0:
            if slot_dwf == "journalier_type":
                # 24 facteurs = 1er jour de la grille (les 7 jours sont
                # identiques pour ce profil).
                f_slot = membres_dwf[0][1]
                h24 = [f_slot[h] for h in range(24)]
                moy_h24 = sum(h24) / 24.0
                q_base = q_dwf / moy_h24 if moy_h24 > 0 else q_dwf
                if not pattern_journalier_emis:
                    resultat["pattern_lines"].append(
                        "DWF_P_JOURNALIER   HOURLY      "
                        + " ".join(f"{v:.6f}" for v in h24))
                    pattern_journalier_emis = True
                resultat["dwf_lines"].append(
                    f"{nid:<16} FLOW        {q_base:<12.6f} "
                    f"DWF_P_JOURNALIER     \"\"         \"\"         \"\"         \"\"")
                methode = "DWF"
                detail = {"pattern": "DWF_P_JOURNALIER", "q_base_m3s": q_base}
            else:  # constant
                resultat["dwf_lines"].append(
                    f"{nid:<16} FLOW        {q_dwf:<12.6f} "
                    f"\"\"             \"\"         \"\"         \"\"         \"\"")
                methode = "DWF"
                detail = {"pattern": None, "q_base_m3s": q_dwf}

            for a, f, q in membres_dwf:
                resultat["apports_meta"].append({
                    "apport_id": a.get("id"),
                    "node_id": nid,
                    "nature": a.get("nature"),
                    "debit_moyen_m3s": q,
                    "mode_determination": a.get("mode_determination"),
                    "eh": a.get("eh"),
                    "debit_specifique_l_hab_j": a.get("debit_specifique_l_hab_j"),
                    "profile_key": a.get("profile_key"),
                    "methode_injection": methode,
                    **detail,
                })
        # ---- [INFLOWS] + [TIMESERIES] pour les apports restants ----
        if reste:
            ts_name = _sanitizer_nom("TS_DWF_", nid)
            q_par_heure = _series_heures_dwf(reste, debut, fin)
            if q_par_heure:
                # Points horaires doublés : valeur à h:00 et h:59:59 →
                # interpolation linéaire SWMM = marche quasi exacte.
                for moment, val in q_par_heure:
                    resultat["timeseries_lines"].append(
                        f"{ts_name:<16} {_fmt_ts_date(moment):<20} {val:<14.8f}")
                    resultat["timeseries_lines"].append(
                        f"{ts_name:<16} {_fmt_ts_date(moment + timedelta(seconds=3599)):<20} {val:<14.8f}")
                resultat["inflow_lines"].append(
                    f"{nid:<16} FLOW        {ts_name:<16} FLOW      "
                    f"1.0        1.0        0.0        ")
                for a, f, q in reste:
                    resultat["apports_meta"].append({
                        "apport_id": a.get("id"),
                        "node_id": nid,
                        "nature": a.get("nature"),
                        "debit_moyen_m3s": q,
                        "mode_determination": a.get("mode_determination"),
                        "eh": a.get("eh"),
                        "debit_specifique_l_hab_j": a.get("debit_specifique_l_hab_j"),
                        "profile_key": a.get("profile_key"),
                        "methode_injection": "INFLOWS_TIMESERIES",
                        "timeseries": ts_name,
                    })

    return resultat


def _series_heures_dwf(
    membres: List[Tuple[Dict[str, Any], List[float], float]],
    debut: datetime,
    fin: datetime,
) -> List[Tuple[datetime, float]]:
    """
    Série horaire Q(t) = Σ_i Q_i × f_i(idx_calendaire(t)), pour chaque
    heure pleine de [debut, fin]. Les facteurs sont déjà renormalisés
    (moyenne 1) par _facteurs_normalises.
    """
    points: List[Tuple[datetime, float]] = []
    t = debut.replace(minute=0, second=0, microsecond=0)
    while t < fin:
        idx = _index_calendaire(t)
        q = sum(q * f[idx] for _, f, q in membres)
        points.append((t, q))
        t += timedelta(hours=1)
    # Point de clôture à l'instant de fin (vaut la dernière heure pleine)
    if points and points[-1][0] < fin:
        idx = _index_calendaire(fin - timedelta(seconds=1))
        q = sum(q * f[idx] for _, f, q in membres)
        points.append((fin, q))
    return points
