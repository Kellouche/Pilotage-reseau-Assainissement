"""
================================================================================
Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
Auteur : Dr Abdelhakim KELLOUCHE
Date de création : 2026-11-15
Objet : Agent garde-fou hydraulicien — contrôle qualité du modèle .inp et
       détection des anomalies de modélisation susceptibles de fausser les
       résultats (réseau plat, nœuds sans exutoire, pentes nulles, bilan
       de masse dégradé, ratios hydrauliques aberrants).
================================================================================
"""

import logging
import re
from collections import Counter
from typing import Any, Dict, List, Optional

logger = logging.getLogger("swmm_platform.agents_expertise.agent_hydraulicien")


class AgentHydraulicienGardeFou:
    """
    Agent expert de contrôle qualité du modèle hydrodynamique.
    Il s'exécute AVANT l'interprétation des résultats : son rôle est de
    signaler toute anomalie de construction du .inp ou de cohérence des
    sorties SWMM qui rendrait le diagnostic hydraulique non fiable.
    """

    SEUIL_RESEAU_PLAT = 0.90      # ≥90 % des radier identiques → réseau plat
    SEUIL_PENTE_NULLE_M = 0.005   # |Δz| < 5 mm sur une conduites → pente nulle
    SEUIL_RATIO_ABERRANT = 50.0   # Q/Qmax > 50 → probable défaut de données
    SEUIL_CONTINUITE_PCT = 5.0    # Erreur de continuité > 5 % → bilan douteux
    SEUIL_INONDATION_ARTIFICIELLE = 0.80  # ≥80 % des nœuds inondés

    def analyser(
        self,
        sim_result: Dict[str, Any],
        node_results: Optional[Dict[str, Any]] = None,
        conduit_results: Optional[Dict[str, Any]] = None,
        meta: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        anomalies: List[Dict[str, Any]] = []
        recommandations: List[str] = []
        inp_content = sim_result.get("inp_content") or ""
        # Les KPIs sont exposés à plat sur sim_result (chemin moteur) ou
        # nichés sous "kpis" selon l'appelant : on couvre les deux.
        kpis = sim_result.get("kpis") or sim_result
        node_results = node_results if node_results is not None else (sim_result.get("node_results") or {})
        conduit_results = conduit_results if conduit_results is not None else (sim_result.get("conduit_results") or {})
        meta = meta if meta is not None else (sim_result.get("meta") or {})

        sections = self._parser_sections(inp_content)
        junctions = self._lire_junctions(sections.get("junctions", []))
        outfalls = self._lire_outfalls(sections.get("outfalls", []))
        conduits = self._lire_conduits(sections.get("conduits", []))

        indicateurs: Dict[str, Any] = {
            "nb_junctions": len(junctions),
            "nb_outfalls": len(outfalls),
            "nb_conduits": len(conduits),
            "nb_elevations_distinctes": len(set(junctions.values())),
        }

        # ── 1. Réseau plat : altimétrie synthétique dégradée ─────────────
        if len(junctions) >= 10:
            _comptage = Counter(round(v, 3) for v in junctions.values())
            _modal_elev, _modal_n = _comptage.most_common(1)[0]
            _part = _modal_n / len(junctions)
            indicateurs["elevation_modale"] = _modal_elev
            indicateurs["part_elevation_modale_pct"] = round(_part * 100.0, 1)
            if _part >= self.SEUIL_RESEAU_PLAT:
                anomalies.append({
                    "code": "RESEAU_PLAT",
                    "severite": "critique",
                    "message": (
                        f"{_modal_n}/{len(junctions)} nœuds ({_part*100:.0f} %) partagent la même "
                        f"cote radier {_modal_elev:.3f} m : le réseau est hydrauliquement plat, "
                        "aucun gradient gravitaire ne peut s'établir."
                    ),
                    "details": {
                        "elevation_modale_m": _modal_elev,
                        "noeuds_a_cette_cote": _modal_n,
                        "source_altimetrique": meta.get("source_altimetrique"),
                    },
                })
                recommandations.append(
                    "Vérifier la résolution de l'exutoire du bassin et la disponibilité des "
                    "cotes altimétriques (PROFRADI/COTTN) dans le GPKG ; relancer la simulation."
                )

        # ── 2. Nœuds sans exutoire : inondation artificielle garantie ────
        _noeuds_sans_issue = self._detecter_noeuds_sans_issue(junctions, outfalls, conduits)
        indicateurs["nb_noeuds_sans_exutoire"] = len(_noeuds_sans_issue)
        if _noeuds_sans_issue:
            anomalies.append({
                "code": "NOEUD_SANS_EXUTOIRE",
                "severite": "majeure",
                "message": (
                    f"{len(_noeuds_sans_issue)} nœud(s)-jonction terminal(aux) ne possèdent "
                    "aucun tronçon sortant ni exutoire : l'eau qui les atteint ne peut "
                    "s'évacuer et produit un débordement artificiel."
                ),
                "details": {"noeuds": _noeuds_sans_issue[:20]},
            })
            recommandations.append(
                "Raccorder chaque nœud frontière à un exutoire libre (débordement de "
                "sous-réseau tronqué) ou élargir le périmètre du bassin simulé."
            )

        # ── 3. Conduites à pente nulle ────────────────────────────────────
        _pentes_nulles = self._detecter_pentes_nulles(conduits, junctions)
        indicateurs["nb_conduites_pente_nulle"] = len(_pentes_nulles)
        if _pentes_nulles:
            _pct = len(_pentes_nulles) / max(len(conduits), 1) * 100.0
            anomalies.append({
                "code": "PENTE_NULLE",
                "severite": "majeure" if _pct > 50 else "mineure",
                "message": (
                    f"{len(_pentes_nulles)} conduites ({_pct:.0f} %) relient des nœuds à "
                    "côte identique (|Δz| < 5 mm) : écoulement gravitaire impossible."
                ),
                "details": {"conduites": _pentes_nulles[:20]},
            })

        # ── 4. Bilan de masse (continuité de routage) ─────────────────────
        _continuite = self._lire_continuite_rpt(sim_result.get("rpt_content") or "")
        _kpis_cont = [abs(float(kpis.get(k) or 0.0))
                      for k in ("routing_continuity_error_pct", "runoff_continuity_error_pct")]
        if _kpis_cont:
            _continuite = max([v for v in _kpis_cont if v > 0] or [0.0]) or _continuite
        if _continuite is not None:
            indicateurs["continuite_erreur_pct_max"] = _continuite
            if abs(_continuite) > self.SEUIL_CONTINUITE_PCT:
                anomalies.append({
                    "code": "BILAN_MASSE_DEGRADE",
                    "severite": "majeure",
                    "message": (
                        f"Erreur de continuité maximale du routage : {abs(_continuite):.2f} % "
                        f"(seuil {self.SEUIL_CONTINUITE_PCT} %) — les volumes routés ne "
                        "sont pas strictement conservés."
                    ),
                    "details": {"continuity_error_pct": _continuite},
                })

        # ── 5. Inondation généralisée suspecte ───────────────────────────
        _nb_noeuds = len(node_results)
        _nb_inondes = sum(
            1 for n in node_results.values()
            if isinstance(n, dict) and (n.get("status") == "flooded" or float(n.get("hours_flooded") or 0) > 0)
        )
        if _nb_noeuds:
            _taux_inond = _nb_inondes / _nb_noeuds
            indicateurs["taux_noeuds_inondes_pct"] = round(_taux_inond * 100.0, 1)
            if _taux_inond >= self.SEUIL_INONDATION_ARTIFICIELLE:
                _plat = any(a["code"] == "RESEAU_PLAT" for a in anomalies)
                anomalies.append({
                    "code": "INONDATION_GENERALISEE",
                    "severite": "info" if _plat else "mineure",
                    "message": (
                        f"{_nb_inondes}/{_nb_noeuds} nœuds ({_taux_inond*100:.0f} %) sont "
                        "en débordement : résultat cohérent avec un réseau saturé, "
                        + ("mais probablement amplifié par l'altimétrie plate du modèle."
                           if _plat else "à interpréter avec les cotes réelles du réseau.")
                    ),
                    "details": {"noeuds_inondes": _nb_inondes, "noeuds_total": _nb_noeuds},
                })

        # ── 6. Ratios hydrauliques aberrants (qualité des données) ────────
        _ratios = [float(c.get("flow_ratio") or 0.0) for c in conduit_results.values()
                   if isinstance(c, dict)]
        _ratio_max = max(_ratios) if _ratios else 0.0
        indicateurs["flow_ratio_max"] = round(_ratio_max, 2)
        if _ratio_max > self.SEUIL_RATIO_ABERRANT:
            anomalies.append({
                "code": "RATIO_HYDRAULIQUE_ABERRANT",
                "severite": "mineure",
                "message": (
                    f"Ratio Q/Qmax maximal observé : {_ratio_max:.1f} — très au-delà du "
                    "fonctionnement gravitaire ; vérifiez les diamètres et pentes "
                    "sources (unités, valeurs aberrantes)."
                ),
                "details": {"flow_ratio_max": _ratio_max},
            })

        # ── 7. Altimétrie synthétique : transparence sur la provenance ───
        _src_alt = str(meta.get("source_altimetrique") or "")
        if "Pente moyenne" in _src_alt or "utilisateur" in _src_alt.lower():
            anomalies.append({
                "code": "ALTIMETRIE_SYNTHETIQUE",
                "severite": "info",
                "message": (
                    f"Cotes radier synthétiques ({_src_alt}) : le réseau ne dispose "
                    "pas d'altimétrie SIG exploitable ; les résultats sont "
                    "conditionnels à la pente adoptée."
                ),
                "details": {"source_altimetrique": _src_alt,
                            "pente_moyenne_pct": meta.get("pente_moyenne_pct")},
            })

        # ── Verdict de fiabilité ─────────────────────────────────────────
        _critiques = [a for a in anomalies if a["severite"] == "critique"]
        _majeures = [a for a in anomalies if a["severite"] == "majeure"]
        if _critiques:
            fiabilite = "DEGRADE"
        elif _majeures:
            fiabilite = "A_VERIFIER"
        else:
            fiabilite = "SAIN"

        if fiabilite != "SAIN":
            recommandations.insert(0,
                "Ne pas utiliser ce diagnostic hydraulique comme référence "
                "d'ingénierie sans correction des anomalies ci-dessus.")

        return {
            "agent": "Agent 0 : Garde-fou hydraulicien (contrôle qualité modèle)",
            "fiabilite_modele": fiabilite,
            "nb_anomalies": len(anomalies),
            "anomalies": anomalies,
            "indicateurs_modele": indicateurs,
            "recommandations": recommandations,
        }

    # ── Parsing minimal des sections .inp ────────────────────────────────

    @staticmethod
    def _parser_sections(inp_text: str) -> Dict[str, List[str]]:
        sections: Dict[str, List[str]] = {}
        courant = None
        for ligne in (inp_text or "").splitlines():
            s = ligne.strip()
            if s.startswith("[") and s.endswith("]"):
                courant = s.strip("[]").lower()
                sections[courant] = []
            elif courant is not None:
                sections[courant].append(ligne)
        return sections

    @staticmethod
    def _lire_junctions(lignes: List[str]) -> Dict[str, float]:
        out = {}
        for l in lignes:
            s = l.strip()
            if not s or s.startswith(";"):
                continue
            p = s.split()
            if len(p) >= 2:
                try:
                    out[p[0]] = float(p[1])
                except (TypeError, ValueError):
                    continue
        return out

    @staticmethod
    def _lire_outfalls(lignes: List[str]) -> set:
        out = set()
        for l in lignes:
            s = l.strip()
            if not s or s.startswith(";"):
                continue
            p = s.split()
            if p:
                out.add(p[0])
        return out

    @staticmethod
    def _lire_conduits(lignes: List[str]) -> List[Dict[str, Any]]:
        out = []
        for l in lignes:
            s = l.strip()
            if not s or s.startswith(";"):
                continue
            p = s.split()
            if len(p) >= 3:
                try:
                    out.append({"nom": p[0], "amont": p[1], "aval": p[2],
                                "longueur": float(p[3]) if len(p) > 3 else 0.0})
                except (TypeError, ValueError):
                    continue
        return out

    @staticmethod
    def _detecter_noeuds_sans_issue(junctions, outfalls, conduits) -> List[str]:
        """Jonctions aval de conduites sans aucun tronçon sortant ni exutoire."""
        _amonts = {c["amont"] for c in conduits}
        _avals = {c["aval"] for c in conduits}
        _candidats = (_avals - _amonts) & set(junctions.keys())
        return sorted(n for n in _candidats if n not in outfalls)

    @staticmethod
    def _detecter_pentes_nulles(conduits, junctions) -> List[str]:
        out = []
        for c in conduits:
            z_u = junctions.get(c["amont"])
            z_d = junctions.get(c["aval"])
            if z_u is None or z_d is None:
                continue
            if c["longueur"] > 10.0 and abs(z_u - z_d) < AgentHydraulicienGardeFou.SEUIL_PENTE_NULLE_M:
                out.append(c["nom"])
        return out

    @staticmethod
    def _lire_continuite_rpt(rpt_text: str) -> Optional[float]:
        """Erreur de continuité max du routement dynamique (section Flow Routing)."""
        if not rpt_text:
            return None
        _valeurs = []
        for m in re.finditer(r"Continuity Error \(%\)\s*\.*\s*(-?[\d.]+)", rpt_text):
            try:
                _valeurs.append(abs(float(m.group(1))))
            except ValueError:
                continue
        return max(_valeurs) if _valeurs else None
