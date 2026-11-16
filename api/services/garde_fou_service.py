# -*- coding: utf-8 -*-
"""
================================================================================
Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
Objet : Paramétrage du garde-fou hydraulicien (Agent 0) par projet.

Le garde-fou n'est pas une vérité hydraulique : c'est une POLITIQUE
D'ACCEPTATION de la fiabilité d'un résultat, propre au contexte
métier du projet. Ce module centralise :

  - le catalogue des seuils (valeur par défaut, unité, justification) ;
  - les préréglages (standard / strict / avant-projet) ;
  - les profils réseau suggérant des seuils (unitaire / séparatif /
    neuf / ancien) ;
  - la fusion en configuration effective ;
  - la ré-évaluation rétroactive des simulations d'un projet.

La config brute persistée sur `projects.garde_fou_config` reste
minimale (preset + profil + surcharges utilisateur) : les valeurs
fusionnées sont recalculées à chaque usage, ce qui garantit que les
défauts évoluent avec le code sans migration de données.
================================================================================
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

logger = logging.getLogger("swmm_platform.services.garde_fou")

# ---------------------------------------------------------------------------
# Catalogue des seuils — chaque entrée documente sa justification.
# `cle` = nom stable stocké dans la config et lu par l'agent.
# ---------------------------------------------------------------------------

SEUILS_CATALOGUE: Dict[str, Dict[str, Any]] = {
    "reseau_plat_pct": {
        "label": "Part modale de cotes radier identiques",
        "unite": "part (0-1)",
        "defaut": 0.90,
        "justification": (
            "≥ ce seuil, la topographie est quasi uniforme : aucun gradient "
            "gravitaire ne peut s'établir (heuristique d'ingénierie)."
        ),
    },
    "pente_nulle_m": {
        "label": "Écart altimétrique minimal par tronçon",
        "unite": "m",
        "defaut": 0.005,
        "justification": (
            "|Δz| inférieur sur un tronçon long = pente pratiquement nulle ; "
            "5 mm correspond à une pente < 0,05 % sur 10 m."
        ),
    },
    "pente_nulle_longueur_m": {
        "label": "Longueur minimale pour tester la pente",
        "unite": "m",
        "defaut": 10.0,
        "justification": (
            "En dessous, les incertitudes d'arrondi masquent une pente réelle."
        ),
    },
    "ratio_aberrant": {
        "label": "Ratio Q/Qmax aberrant",
        "unite": "×",
        "defaut": 50.0,
        "justification": (
            "Un ratio très supérieur à 1 sur de longues sections signale "
            "probablement un défaut d'unité ou de diamètre source."
        ),
    },
    "continuite_pct": {
        "label": "Erreur de continuité max (routage)",
        "unite": "%",
        "defaut": 5.0,
        "justification": (
            "Critère du .rpt SWMM : <1 % sain, >5 % = volumes non conservés."
        ),
    },
    "inondation_pct": {
        "label": "Part de nœuds en débordement",
        "unite": "part (0-1)",
        "defaut": 0.80,
        "justification": (
            "Au-delà, le débordement généralisé n'est plus un signal localisé "
            "mais un état du modèle entier."
        ),
    },
    "altimetrie_confondue_pct": {
        "label": "Cote radier = profondeur (part de nœuds)",
        "unite": "part (0-1)",
        "defaut": 0.30,
        "justification": (
            "Incohérence sémantique .inp : une « altitude » identique à la "
            "profondeur du regard est en réalité une profondeur mal reprise."
        ),
    },
    "sentinelle_pct": {
        "label": "Part de nœuds à la cote sentinelle",
        "unite": "part (0-1)",
        "defaut": 0.20,
        "justification": (
            "Plateau à la valeur par défaut (100 m) = altitudes non résolues "
            "silencieusement."
        ),
    },
    "sentinelle_valeur_m": {
        "label": "Valeur sentinelle de cote par défaut",
        "unite": "m",
        "defaut": 100.0,
        "justification": (
            "Valeur codée en dur par le résolveur d'altimétrie pour les nœuds "
            "sans source ; à ajuster si la convention change."
        ),
    },
}

# Contrôles activables (checks_actives) — les bugs de données ne devraient
# en principe jamais être désactivés, mais la main reste à l'ingénieur.
CHECKS_ACTIFS_DEFAUT: Dict[str, bool] = {
    "RESEAU_PLAT": True,
    "NOEUD_SANS_EXUTOIRE": True,
    "PENTE_NULLE": True,
    "BILAN_MASSE_DEGRADE": True,
    "INONDATION_GENERALISEE": True,
    "RATIO_HYDRAULIQUE_ABERRANT": True,
    "ALTIMETRIE_SYNTHETIQUE": True,
    "ALTIMETRIE_CONFONDUE_PROFONDEUR": True,
    "SENTINELLE_COTE_DEFAUT": True,
}

CHECKS_LABELS: Dict[str, str] = {
    "RESEAU_PLAT": "Réseau hydrauliquement plat",
    "NOEUD_SANS_EXUTOIRE": "Nœud terminal sans exutoire",
    "PENTE_NULLE": "Conduites à pente insuffisante",
    "BILAN_MASSE_DEGRADE": "Erreur de continuité excessive",
    "INONDATION_GENERALISEE": "Débordement généralisé",
    "RATIO_HYDRAULIQUE_ABERRANT": "Ratio Q/Qmax aberrant",
    "ALTIMETRIE_SYNTHETIQUE": "Altimétrie synthétique (propagation pente)",
    "ALTIMETRIE_CONFONDUE_PROFONDEUR": "Profondeur reprise comme altitude",
    "SENTINELLE_COTE_DEFAUT": "Cotes par défaut non résolues",
}

# ---------------------------------------------------------------------------
# Préréglages — cohérents par famille d'usage.
#   standard    : défauts (usage courant)
#   strict      : prudence maximale — un avant-projet sérieux ou une note
#                 de calcul ne devrait pas tolérer de doute
#   avant_projet: screening rapide — tolère les phénomènes physiques
#                 (inondation, surcharge) mais JAMAIS les bugs de données
# ---------------------------------------------------------------------------

PRESETS: Dict[str, Dict[str, Any]] = {
    "standard": {
        "label": "Standard",
        "description": "Seuils par défaut équilibrés.",
        "seuils": {},
        "checks_actives": {},
    },
    "strict": {
        "label": "Strict",
        "description": (
            "Contrôle renforcé : note de calcul, avant-projet avancé ou "
            "résultats destinés à engagement."
        ),
        "seuils": {
            "reseau_plat_pct": 0.75,
            "pente_nulle_m": 0.010,
            "continuite_pct": 2.0,
            "inondation_pct": 0.60,
            "altimetrie_confondue_pct": 0.15,
            "sentinelle_pct": 0.10,
            "ratio_aberrant": 20.0,
        },
        "checks_actives": {},
    },
    "avant_projet": {
        "label": "Avant-projet",
        "description": (
            "Screening rapide : tolère les phénomènes physiques attendus "
            "(fortes pluies, surcharge) mais conserve tous les contrôles "
            "d'intégrité des données."
        ),
        "seuils": {
            "continuite_pct": 10.0,
            "inondation_pct": 0.95,
            "ratio_aberrant": 100.0,
        },
        "checks_actives": {},
    },
}

# ---------------------------------------------------------------------------
# Profils réseau — suggestions métier pré-remplies (l'utilisateur reste
# libre de modifier chaque seuil après application).
# ---------------------------------------------------------------------------

PROFILS_RESEAU: Dict[str, Dict[str, Any]] = {
    "unitaire": {
        "label": "Réseau unitaire",
        "description": (
            "Unitaire : les débordements sont fréquents par conception — "
            "seuil d'inondation généralisée relevé."
        ),
        "seuils": {"inondation_pct": 0.95, "ratio_aberrant": 80.0},
        "preset_suggere": "standard",
    },
    "separatif": {
        "label": "Réseau séparatif",
        "description": (
            "Séparatif : tout débordement est anormal — contrôle standard."
        ),
        "seuils": {},
        "preset_suggere": "strict",
    },
    "neuf": {
        "label": "Ouvrage récent / neuf",
        "description": (
            "Réseau récent : données censées être propres — contrôle strict "
            "sur la continuité et les pentes."
        ),
        "seuils": {"continuite_pct": 2.0, "pente_nulle_m": 0.010},
        "preset_suggere": "strict",
    },
    "ancien": {
        "label": "Réseau ancien / dégradé",
        "description": (
            "Patrimoine ancien : données hétérogènes — tolérance accrue sur "
            "les anomalies physiques, contrôle des données conservé."
        ),
        "seuils": {"continuite_pct": 10.0, "inondation_pct": 0.90},
        "preset_suggere": "avant_projet",
    },
}


# ---------------------------------------------------------------------------
# Fusion de configuration
# ---------------------------------------------------------------------------

def seuils_par_defaut() -> Dict[str, float]:
    return {k: float(v["defaut"]) for k, v in SEUILS_CATALOGUE.items()}


def config_effective(raw: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Fusionne : défauts catalogue ← preset ← profil réseau ← surcharges
    utilisateur. Retourne le dict canonique consommé par l'agent et
    exposé à l'API (traçabilité : la config utilisée est stockée dans
    chaque verdict).
    """
    raw = raw if isinstance(raw, dict) else {}

    seuils = seuils_par_defaut()
    checks = dict(CHECKS_ACTIFS_DEFAUT)

    preset_key = str(raw.get("preset") or "standard")
    preset = PRESETS.get(preset_key) or PRESETS["standard"]
    for k, v in (preset.get("seuils") or {}).items():
        if k in seuils:
            seuils[k] = float(v)
    for k, v in (preset.get("checks_actives") or {}).items():
        checks[k] = bool(v)

    profil_key = raw.get("profil_reseau")
    profil = PROFILS_RESEAU.get(str(profil_key)) if profil_key else None
    if profil:
        for k, v in (profil.get("seuils") or {}).items():
            if k in seuils:
                seuils[k] = float(v)

    # Surcharges utilisateur (valeurs saisies dans la modale)
    for k, v in (raw.get("seuils") or {}).items():
        if k in seuils:
            try:
                seuils[k] = float(v)
            except (TypeError, ValueError):
                continue
    for k, v in (raw.get("checks_actives") or {}).items():
        if k in checks:
            checks[k] = bool(v)

    return {
        "preset": preset_key if preset_key in PRESETS else "standard",
        "profil_reseau": profil_key if profil else None,
        "seuils": seuils,
        "checks_actives": checks,
        "source": "personnalisee" if raw else "defauts",
    }


def config_bare(raw: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Normalise la config BRUTE à persister : ne garde que les champs
    connus (preset, profil_reseau, seuils, checks_actives) pour éviter
    d'enregistrer des clés parasites.
    """
    raw = raw if isinstance(raw, dict) else {}
    out: Dict[str, Any] = {}
    if raw.get("preset") in PRESETS:
        out["preset"] = raw["preset"]
    if raw.get("profil_reseau") in PROFILS_RESEAU:
        out["profil_reseau"] = raw["profil_reseau"]
    seuils = {}
    for k, v in (raw.get("seuils") or {}).items():
        if k in SEUILS_CATALOGUE:
            try:
                seuils[k] = float(v)
            except (TypeError, ValueError):
                continue
    if seuils:
        out["seuils"] = seuils
    checks = {}
    for k, v in (raw.get("checks_actives") or {}).items():
        if k in CHECKS_ACTIFS_DEFAUT:
            checks[k] = bool(v)
    if checks:
        out["checks_actives"] = checks
    out["maj_le"] = datetime.now(timezone.utc).isoformat()
    return out


def decrire_catalogue() -> Dict[str, Any]:
    """Métadonnées exposées à l'API pour construire la modale."""
    return {
        "seuils": SEUILS_CATALOGUE,
        "checks": {"codes": CHECKS_LABELS, "defauts": CHECKS_ACTIFS_DEFAUT},
        "presets": PRESETS,
        "profils_reseau": PROFILS_RESEAU,
    }


# ---------------------------------------------------------------------------
# Ré-évaluation rétroactive des simulations d'un projet
# ---------------------------------------------------------------------------

SEVERITE_RANG = {"SAIN": 0, "A_VERIFIER": 1, "DEGRADE": 2}


def _persister_resultat(sim: Any, data: Dict[str, Any]) -> bool:
    """Réécrit le JSON de résultat là où il a été lu (cache local prioritaire)."""
    cle = getattr(sim, "results_s3_key", None)
    if cle:
        p = Path(str(cle))
        try:
            if p.exists() and p.is_file():
                with open(p, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False)
                return True
        except Exception as e:
            logger.warning("Réécriture impossible %s : %s", p, e)
            return False
    try:
        from api.services.result_store import (
            ArtifactKind, ResultNotFound, ResultRef, ResultStore,
        )
        ref = ResultRef.depuis_simulation(sim)
        if ref is not None:
            ResultStore().save(ref, data, ArtifactKind.RESULT_JSON)
            return True
    except ResultNotFound:
        pass
    except Exception as e:
        logger.warning("ResultStore save impossible (%s) : %s",
                       getattr(sim, "id", "?"), e)
    return False


def reevaluer_garde_fou_projet(db: Session, project: Any,
                              appliquer: bool = False,
                              config: Optional[Dict[str, Any]] = None
                              ) -> Dict[str, Any]:
    """
    Ré-évalue les simulations `completed` d'un projet avec la
    configuration garde-fou effective. `appliquer=False` = dry-run
    (aucune écriture). Retourne les statistiques et le détail des
    changements de verdict.
    """
    from api.models import Simulation
    from api.services.simulation_service import charger_resultat_simulation
    from src.domain.agents_expertise.agent_hydraulicien_garde_fou import (
        AgentHydraulicienGardeFou,
    )

    cfg = config if config is not None else config_effective(
        getattr(project, "garde_fou_config", None))
    agent = AgentHydraulicienGardeFou()

    sims = (db.query(Simulation)
            .filter(Simulation.project_id == project.id,
                    Simulation.status == "completed")
            .order_by(Simulation.created_at.desc())
            .all())

    stats = {"total": 0, "charges": 0, "modifies": 0, "degrades": 0,
             "erreurs": 0, "deja_ko": 0}
    details: List[Dict[str, Any]] = []

    for sim in sims:
        stats["total"] += 1
        sid = getattr(sim, "id", "?")
        try:
            data = charger_resultat_simulation(sim)
        except Exception as e:
            logger.warning("Chargement impossible %s : %s", sid, e)
            stats["erreurs"] += 1
            continue
        if not isinstance(data, dict) or not data:
            stats["erreurs"] += 1
            continue
        stats["charges"] += 1

        try:
            gf = agent.analyser(data, config=cfg)
        except Exception as e:
            logger.warning("Garde-fou en échec %s : %s", sid, e)
            stats["erreurs"] += 1
            continue

        ancien = ((data.get("agents_expertise") or {})
                  .get("controle_modele_hydraulique") or {})
        v_ancien = ancien.get("fiabilite_modele")
        v_nouveau = gf.get("fiabilite_modele")
        n_ancien = ancien.get("nb_anomalies", 0)
        n_nouveau = gf.get("nb_anomalies", 0)

        if v_nouveau == v_ancien and n_nouveau == n_ancien:
            if v_nouveau == "DEGRADE":
                stats["deja_ko"] += 1
            continue

        stats["modifies"] += 1
        if SEVERITE_RANG.get(v_nouveau, 0) > SEVERITE_RANG.get(v_ancien or "SAIN", 0):
            stats["degrades"] += 1

        codes = [a.get("code") for a in (gf.get("anomalies") or [])]
        details.append({
            "simulation_id": sid,
            "nom": getattr(sim, "name", None),
            "avant": v_ancien or "(absent)",
            "apres": v_nouveau,
            "anomalies": codes,
        })

        if not appliquer:
            continue

        data.setdefault("agents_expertise", {})["controle_modele_hydraulique"] = {
            **gf,
            "audit_automatique": {
                "date": datetime.now(timezone.utc).isoformat(),
                "motif": "garde_fou_parametrage_projet",
                "verdict_precedent": v_ancien,
            },
        }
        _persister_resultat(sim, data)

        kpis = dict(sim.summary_kpis or {})
        kpis["fiabilite_modele"] = v_nouveau
        kpis["fiabilite_anomalies"] = n_nouveau
        kpis["audit_garde_fou"] = {
            "date": datetime.now(timezone.utc).isoformat(),
            "verdict_precedent": v_ancien,
            "anomalies": codes,
        }
        sim.summary_kpis = kpis

    if appliquer:
        db.commit()

    return {**stats, "details": details,
            "config_utilisee": {"preset": cfg.get("preset"),
                                "profil_reseau": cfg.get("profil_reseau"),
                                "source": cfg.get("source")}}
