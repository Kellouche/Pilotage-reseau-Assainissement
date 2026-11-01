# -*- coding: utf-8 -*-
"""
Nom Auteur : Dr Abdelhakim Kellouche
Nom de l'application : SWMM Platform SaaS
Numéro version : 2.2.0
Date de création : 01-11-2026

Module domain.moteur_swmm : Assemblage du modèle SWMM 5.2 natif, exécution hydrodynamique
via pyswmm (Dynamic Wave DYNWAVE), et analyse certifiée des résultats hydrauliques.
"""

import os
import re
import tempfile
import logging
from pathlib import Path
from typing import Dict, Any, Optional, Tuple, List
import geopandas as gpd

from src.domain.hydrologie import GenerateurHydrologie
from pyswmm import Simulation

logger = logging.getLogger("swmm_platform.moteur_swmm")


SCENARIOS_PLUIE = {
    "pluie_decennale": {
        "nom": "Pluie Décennale (T = 10 ans) — Montana / Chicago",
        "duree_heures": 4.0,
        "description": "Pluie d'orage décennale type Chlef/Centre (a=5.8, b=0.62) avec pic Chicago à r=0.4.",
        "timeseries": [
            ("00:00", 0.0),
            ("00:15", 8.0),
            ("00:30", 22.0),
            ("00:45", 55.0),
            ("01:00", 92.0),
            ("01:15", 45.0),
            ("01:30", 20.0),
            ("01:45", 10.0),
            ("02:00", 3.0),
            ("03:00", 0.0),
            ("04:00", 0.0),
        ]
    },
    "pluie_cinquantennale": {
        "nom": "Pluie Cinquantennale (T = 50 ans) — Crise Hydraulique",
        "duree_heures": 4.0,
        "description": "Événement pluvieux exceptionnel cinquantennal (pic de 145 mm/h).",
        "timeseries": [
            ("00:00", 0.0),
            ("00:15", 14.0),
            ("00:30", 38.0),
            ("00:45", 95.0),
            ("01:00", 145.0),
            ("01:15", 70.0),
            ("01:30", 30.0),
            ("01:45", 15.0),
            ("02:00", 5.0),
            ("03:00", 0.0),
            ("04:00", 0.0),
        ]
    },
    "pluie_orage_2h": {
        "nom": "Orage d'Été Court et Violent (2h)",
        "duree_heures": 2.0,
        "description": "Averse estivale brève et intense concentrée sur 60 minutes.",
        "timeseries": [
            ("00:00", 0.0),
            ("00:10", 15.0),
            ("00:20", 45.0),
            ("00:30", 110.0),
            ("00:40", 65.0),
            ("00:50", 20.0),
            ("01:00", 5.0),
            ("02:00", 0.0),
        ]
    },
    "temps_sec_pur": {
        "nom": "Temps Sec Pur (DWF seul)",
        "duree_heures": 24.0,
        "description": "Simulation d'étiage et de transit des eaux usées domestiques sans précipitation.",
        "timeseries": [
            ("00:00", 0.0),
            ("24:00", 0.0)
        ]
    }
}


class MoteurSWMM:
    """
    Orchestrateur de simulation hydrodynamique EPA SWMM 5.2.
    Transforme un réseau SIG (GeoPackage) en modèle .inp, exécute le solveur
    Saint-Venant via pyswmm et extrait les KPIs d'audit capacitaire.
    """

    def __init__(self, tampon_buffer_m: float = 35.0, imperv_defaut: float = 70.0):
        self.gh = GenerateurHydrologie(tampon_buffer_m=tampon_buffer_m, imperv_defaut=imperv_defaut)

    def assembler_modele_inp(
        self,
        gpkg_path: Path,
        scenario_key: str = "pluie_decennale",
        duree_heures: Optional[float] = None,
        pas_routage_sec: int = 5
    ) -> Tuple[str, Dict[str, Any]]:
        """
        Génère l'intégralité du contenu textuel conforme au standard EPA SWMM 5.2 .inp.
        """
        if scenario_key not in SCENARIOS_PLUIE:
            scenario_key = "pluie_decennale"

        scen = SCENARIOS_PLUIE[scenario_key]
        duree_sim = duree_heures if (duree_heures and duree_heures > 0) else scen["duree_heures"]

        layers = gpd.list_layers(str(gpkg_path))["name"].tolist()
        regard_layer = next((l for l in layers if "regard" in l.lower()), None)
        pipe_layer = next((l for l in layers if any(k in l.lower() for k in ["canalisat", "conduit", "pipe", "troncon"]) and "désaffect" not in l.lower() and "desaffect" not in l.lower()), None)
        rejet_layer = next((l for l in layers if any(k in l.lower() for k in ["rejet", "exutoire", "outfall"])), None)

        if not regard_layer or not pipe_layer:
            raise ValueError("Le fichier GeoPackage doit contenir les couches regards et canalisations.")

        regards = gpd.read_file(str(gpkg_path), layer=regard_layer)
        canalisations = gpd.read_file(str(gpkg_path), layer=pipe_layer)
        rejets = gpd.read_file(str(gpkg_path), layer=rejet_layer) if rejet_layer else gpd.GeoDataFrame()

        # Détermination de l'exutoire principal (Outfall)
        outfall_code = None
        if len(rejets) > 0:
            outfall_geom = rejets.geometry.iloc[0]
            distances = regards.geometry.distance(outfall_geom)
            outfall_idx = distances.idxmin()
            outfall_code = str(int(regards.loc[outfall_idx, "Code"])) if ("Code" in regards and not regards.isna().loc[outfall_idx, "Code"]) else str(outfall_idx)
        else:
            outfall_code = str(int(regards.iloc[-1]["Code"])) if ("Code" in regards and not regards.isna().iloc[-1]["Code"]) else str(len(regards) - 1)

        # Génération des sous-bassins versants Voronoï / Thiessen
        sb_gdf = self.gh.generer_sous_bassins(regards, canalisations)
        swmm_sec = self.gh.formater_sections_swmm(sb_gdf, rain_gage_name="RG1")

        # Formatage des durées SWMM
        h_end = int(duree_sim)
        m_end = int((duree_sim - h_end) * 60)
        end_time_str = f"{h_end:02d}:{m_end:02d}:00"

        routing_step_str = f"00:00:{pas_routage_sec:02d}"

        lines = [
            "[TITLE]",
            f";; SWMM Platform SaaS - Simulation Hydrodynamique Native 5.2",
            f";; Scénario : {scen['nom']}",
            f";; Durée : {duree_sim} heures | Pas de routage : {pas_routage_sec}s",
            "",
            "[OPTIONS]",
            "FLOW_UNITS          CMS",
            "INFILTRATION        HORTON",
            "FLOW_ROUTING        DYNWAVE",
            "START_DATE          01/01/2026",
            "START_TIME          00:00:00",
            "REPORT_START_DATE   01/01/2026",
            "REPORT_START_TIME   00:00:00",
            f"END_DATE            01/01/2026",
            f"END_TIME            {end_time_str}",
            "REPORT_STEP         00:01:00",
            "WET_STEP            00:05:00",
            "DRY_STEP            01:00:00",
            f"ROUTING_STEP        {routing_step_str}",
            "ALLOW_PONDING       NO",
            "INERTIAL_DAMPING    PARTIAL",
            "VARIABLE_STEP       0.75",
            "LENGTHENING_STEP    0",
            "MIN_SURFAREA        1.167",
            "NORMAL_FLOW_LIMITED BOTH",
            "FORCE_MAIN_EQUATION H-W",
            "LINK_OFFSETS        DEPTH",
            "MIN_SLOPE           0",
            "MAX_TRIALS          8",
            "HEAD_TOLERANCE      0.0015",
            "SYS_FLOW_TOL        5",
            "LAT_FLOW_TOL        5",
            "MINIMUM_STEP        0.5",
            "THREADS             1",
            "",
            "[EVAPORATION]",
            "CONSTANT 0.0",
            "DRY_ONLY NO",
            "",
            "[RAINGAGES]",
            ";;Name           Format    Interval SCF      Source",
            "RG1              INTENSITY 0:05     1.0      TIMESERIES TS_SCENARIO",
            "",
            "[TIMESERIES]",
            ";;Name           Date       Time       Value",
        ]

        # Ajout du hyétogramme de pluie
        for t_str, val in scen["timeseries"]:
            lines.append(f"TS_SCENARIO                 {t_str:<10} {val:<10.2f}")
        lines.append("")

        # Sections hydrologiques (Subcatchments, Subareas, Infiltration)
        for sec_name in ["SUBCATCHMENTS", "SUBAREAS", "INFILTRATION"]:
            lines.append(f"[{sec_name}]")
            lines.extend(swmm_sec[sec_name])
            lines.append("")

        # Section regards (Junctions)
        lines.append("[JUNCTIONS]")
        lines.append(";;Name           Elevation  MaxDepth   InitDepth  SurDepth   Aponded")
        for idx, r in regards.iterrows():
            nid = str(int(r["Code"])) if ("Code" in r and not r.isna()["Code"]) else str(idx)
            if nid == outfall_code:
                continue
            prof = float(r["Profondeur"]) if ("Profondeur" in r and r["Profondeur"] > 0) else 2.0
            # Cote radier fixée arbitrairement si non fournie (100.0)
            lines.append(f"{nid:<16} 100.000    {prof:<10.3f} 0.000      0.000      0.000")
        lines.append("")

        # Section exutoire (Outfalls)
        lines.append("[OUTFALLS]")
        lines.append(";;Name           Elevation  Type       Stage Data       Gated    Route To")
        lines.append(f"{outfall_code:<16} 95.000     FREE                        NO")
        lines.append("")

        # Section conduites (Conduits)
        lines.append("[CONDUITS]")
        lines.append(";;Name           From Node        To Node          Length     Roughness  InOffset   OutOffset  InitFlow   MaxFlow")

        conduit_lines = []
        xsec_lines = []
        for idx, c in canalisations.iterrows():
            cid = f"C_{idx+1}"
            u_node = str(int(float(c["ID_AMONT"]))) if ("ID_AMONT" in c and c["ID_AMONT"]) else ""
            d_node = str(int(float(c["ID_AVAL"]))) if ("ID_AVAL" in c and c["ID_AVAL"]) else ""
            length = float(c["Longeur"]) if ("Longeur" in c and c["Longeur"] > 0) else float(c.geometry.length)
            length = max(1.0, round(length, 2))
            rough = 0.013  # Manning béton standard
            diam_mm = float(c["DIAMETRE"]) if ("DIAMETRE" in c and c["DIAMETRE"] > 0) else 600.0
            diam_m = max(0.2, diam_mm / 1000.0)

            conduit_lines.append(f"{cid:<16} {u_node:<16} {d_node:<16} {length:<10.2f} {rough:<10.4f} 0.000      0.000      0.000      0.000")
            xsec_lines.append(f"{cid:<16} CIRCULAR     {diam_m:<16.3f} 0.000      0.000      0.000      1")

        lines.extend(conduit_lines)
        lines.append("")

        # Section sections transversales (Xsections)
        lines.append("[XSECTIONS]")
        lines.append(";;Link           Shape        Geom1            Geom2      Geom3      Geom4      Barrels    Culvert")
        lines.extend(xsec_lines)
        lines.append("")

        # Section coordonnées géographiques des regards (Coordinates)
        lines.append("[COORDINATES]")
        for idx, r in regards.iterrows():
            nid = str(int(r["Code"])) if ("Code" in r and not r.isna()["Code"]) else str(idx)
            lines.append(f"{nid:<16} {r.geometry.x:<18.3f} {r.geometry.y:<18.3f}")
        lines.append("")

        # Polygones des sous-bassins
        lines.append("[POLYGONS]")
        lines.extend(swmm_sec["POLYGONS"])
        lines.append("")

        # Section rapport détaillée
        lines.append("[REPORT]")
        lines.append("INPUT      NO")
        lines.append("CONTROLS   NO")
        lines.append("SUBCATCHMENTS ALL")
        lines.append("NODES ALL")
        lines.append("LINKS ALL")
        lines.append("")

        meta = {
            "scenario": scen["nom"],
            "duree_heures": duree_sim,
            "subcatchments_count": len(sb_gdf),
            "junctions_count": len(regards) - 1,
            "outfalls_count": 1,
            "conduits_count": len(canalisations),
            "outfall_code": outfall_code,
            "total_area_ha": round(float(sb_gdf["area_ha"].sum()), 2),
        }

        return "\n".join(lines), meta

    def executer_simulation(
        self,
        gpkg_path: Path,
        scenario_key: str = "pluie_decennale",
        duree_heures: Optional[float] = None,
        pas_routage_sec: int = 5
    ) -> Dict[str, Any]:
        """
        Exécute la simulation complète avec pyswmm et extrait les KPIs hydrauliques.
        """
        inp_content, meta = self.assembler_modele_inp(
            gpkg_path=gpkg_path,
            scenario_key=scenario_key,
            duree_heures=duree_heures,
            pas_routage_sec=pas_routage_sec
        )

        with tempfile.NamedTemporaryFile(suffix=".inp", mode="w", delete=False, encoding="utf-8") as f:
            f.write(inp_content)
            tmp_inp = f.name

        rpt_path = tmp_inp.replace(".inp", ".rpt")
        out_path = tmp_inp.replace(".inp", ".out")

        try:
            logger.info("Lancement du moteur EPA SWMM 5.2 via pyswmm sur %s", tmp_inp)
            with Simulation(tmp_inp) as sim:
                for _ in sim:
                    pass

            rpt_text = ""
            if os.path.exists(rpt_path):
                with open(rpt_path, "r", encoding="utf-8", errors="ignore") as rf:
                    rpt_text = rf.read()

            kpis = self._analyser_rapport_swmm(rpt_text, meta)
            kpis["inp_content"] = inp_content
            kpis["rpt_content"] = rpt_text
            kpis["status"] = "SUCCESS"
            return kpis

        finally:
            # Nettoyage sécurisé des fichiers temporaires
            for p in [tmp_inp, rpt_path, out_path]:
                if os.path.exists(p):
                    try:
                        os.unlink(p)
                    except Exception:
                        pass

    def _analyser_rapport_swmm(self, rpt_text: str, meta: Dict[str, Any]) -> Dict[str, Any]:
        """
        Parse et extrait les indicateurs clés (KPIs) et les résultats cartographiques
        détaillés par conduite et par regard depuis le rapport officiel EPA SWMM.
        """
        kpis = {
            "meta": meta,
            "routing_continuity_error_pct": 0.0,
            "runoff_continuity_error_pct": 0.0,
            "total_precipitation_mm": 0.0,
            "total_runoff_volume_m3": 0.0,
            "total_outflow_m3": 0.0,
            "peak_outflow_m3s": 0.0,
            "flooded_nodes_count": 0,
            "surcharged_nodes_count": 0,
            "flooded_nodes": [],
            "node_results": {},
            "conduit_results": {},
            "compliance_continuity": True
        }

        # 1. Continuité routage
        m_routing = re.search(r"Flow Routing Continuity.*?Continuity Error \(%\) \.\.\.\.\.\s+([\-\d\.]+)", rpt_text, re.DOTALL)
        if m_routing:
            kpis["routing_continuity_error_pct"] = float(m_routing.group(1))

        # 2. Continuité ruissellement
        m_runoff = re.search(r"Runoff Quantity Continuity.*?Continuity Error \(%\) \.\.\.\.\.\s+([\-\d\.]+)", rpt_text, re.DOTALL)
        if m_runoff:
            kpis["runoff_continuity_error_pct"] = float(m_runoff.group(1))

        # 3. Précipitations totales
        m_precip = re.search(r"Total Precipitation \.\.\.\.\.\s+[\d\.]+\s+([\d\.]+)", rpt_text)
        if m_precip:
            kpis["total_precipitation_mm"] = float(m_precip.group(1))

        # 4. Sortie totale à l'exutoire (Outflow)
        m_outflow = re.search(r"Total Outflow \.\.\.\.\.\s+[\d\.]+\s+([\d\.]+)", rpt_text)
        if m_outflow:
            kpis["total_outflow_m3"] = round(float(m_outflow.group(1)) * 1000.0, 1)

        # 5. Débit de pointe à l'exutoire (Outfall Loading Summary)
        if "Outfall Loading Summary" in rpt_text:
            outfall_sec = rpt_text.split("Outfall Loading Summary")[1].split("\n\n")[0]
            for line in outfall_sec.strip().splitlines():
                if meta.get("outfall_code") and meta["outfall_code"] in line:
                    parts = line.split()
                    if len(parts) >= 4:
                        try:
                            kpis["peak_outflow_m3s"] = float(parts[2])
                        except Exception:
                            pass

        # 6. Surcharge des regards (Node Surcharge Summary)
        if "Node Surcharge Summary" in rpt_text:
            surch_part = rpt_text.split("Node Surcharge Summary")[1].split("Node Flooding Summary")[0].split("\n\n\n")[0]
            for line in surch_part.strip().splitlines():
                parts = line.split()
                if len(parts) >= 5 and parts[1] == "JUNCTION":
                    nid = parts[0]
                    try:
                        h_surch = float(parts[2])
                        kpis["node_results"][nid] = {
                            "node": nid,
                            "hours_surcharged": h_surch,
                            "hours_flooded": 0.0,
                            "peak_flood_flow_cms": 0.0,
                            "flood_volume_m3": 0.0,
                            "status": "surcharged" if h_surch > 0 else "normal",
                            "color": "#f59e0b" if h_surch > 0 else "#3b82f6"
                        }
                    except Exception:
                        pass

        # 7. Inondations / Débordements en surface (Node Flooding Summary)
        if "Node Flooding Summary" in rpt_text:
            flood_part = rpt_text.split("Node Flooding Summary")[1].split("Outfall Loading Summary")[0]
            for line in flood_part.strip().splitlines():
                parts = line.split()
                if len(parts) >= 6 and parts[0] != "Node":
                    nid = parts[0]
                    try:
                        h_flood = float(parts[1])
                        pk_flood = float(parts[2])
                        vol_flood = float(parts[5]) * 1000.0
                        if h_flood > 0:
                            if nid not in kpis["node_results"]:
                                kpis["node_results"][nid] = {"node": nid, "hours_surcharged": h_flood}
                            kpis["node_results"][nid].update({
                                "hours_flooded": h_flood,
                                "peak_flood_flow_cms": pk_flood,
                                "flood_volume_m3": vol_flood,
                                "status": "flooded",
                                "color": "#ef4444"
                            })
                            kpis["flooded_nodes"].append(kpis["node_results"][nid])
                    except Exception:
                        pass

        kpis["flooded_nodes_count"] = len(kpis["flooded_nodes"])
        kpis["surcharged_nodes_count"] = sum(1 for n in kpis["node_results"].values() if n.get("status") in ("surcharged", "flooded"))

        # 8. Taux de charge des conduites (Link Flow Summary)
        if "Link Flow Summary" in rpt_text:
            link_part = rpt_text.split("Link Flow Summary")[1].split("Flow Classification Summary")[0].split("Conduit Surcharge Summary")[0]
            for line in link_part.strip().splitlines():
                parts = line.split()
                if len(parts) >= 8 and parts[1] == "CONDUIT":
                    cid = parts[0]
                    try:
                        flow_cms = float(parts[2])
                        veloc_ms = float(parts[5])
                        q_ratio = float(parts[6])
                        d_ratio = float(parts[7])

                        # Classification thématique
                        if q_ratio >= 1.0 or d_ratio >= 1.0:
                            c_status = "surcharge"
                            color = "#ef4444"  # Rouge (> 100% ou sous pression)
                            label = "Surcharge (> 100%)"
                        elif q_ratio >= 0.8 or d_ratio >= 0.8:
                            c_status = "critique"
                            color = "#f97316"  # Orange (80% - 100%)
                            label = "Critique (80-100%)"
                        elif q_ratio >= 0.5 or d_ratio >= 0.5:
                            c_status = "moderee"
                            color = "#facc15"  # Jaune (50% - 80%)
                            label = "Modéré (50-80%)"
                        else:
                            c_status = "normal"
                            color = "#10b981"  # Vert (< 50%)
                            label = "Normal (< 50%)"

                        kpis["conduit_results"][cid] = {
                            "link_id": cid,
                            "max_flow_cms": flow_cms,
                            "max_velocity_ms": veloc_ms,
                            "flow_ratio": round(q_ratio, 2),
                            "depth_ratio": round(d_ratio, 2),
                            "status": c_status,
                            "label": label,
                            "color": color
                        }
                    except Exception:
                        pass

        kpis["compliance_continuity"] = abs(kpis["routing_continuity_error_pct"]) <= 5.0
        return kpis
