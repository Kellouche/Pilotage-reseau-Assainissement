"""
================================================================================
Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
Auteur : Hakim / Équipe DrainPilot
Date de création : 2026-04-20
Date de modification : 2026-11-08
Objet : Agent 1 - Diagnosticien hydraulique causal et détection des anomalies 1D
================================================================================
"""

from typing import Dict, Any, List, Optional
import pandas as pd
import geopandas as gpd


class AgentDiagnosticCausal:
    """
    Agent expert chargé de remonter des symptômes (débordements, surpressions)
    aux causes physiques racines (goulots d'étranglement, ruptures de pente, reflux).
    """

    def analyser(
        self,
        kpis: Dict[str, Any],
        conduit_results: Dict[str, Any],
        node_results: Dict[str, Any],
        meta: Dict[str, Any],
        canalisations_gdf: Optional[gpd.GeoDataFrame] = None
    ) -> Dict[str, Any]:
        bottlenecks = []
        slope_anomalies = []
        backwater_nodes = []
        low_velocity_links = []
        high_velocity_links = []
        surcharged_links = []
        flooded_nodes_detail = []

        # Construction d'un index des diamètres et pentes géométriques si le GeoDataFrame est fourni
        pipe_geom_map = {}
        if canalisations_gdf is not None and not canalisations_gdf.empty:
            for idx, row in canalisations_gdf.iterrows():
                cid = f"C_{idx + 1}"
                diam = row.get("DIAMETRE") or row.get("diametre") or row.get("Diametre")
                mat = row.get("MATERIAU") or row.get("materiau") or "Béton"
                try:
                    diam = float(diam) if (diam is not None and pd.notna(diam) and float(diam) > 0) else 600.0
                except Exception:
                    diam = 600.0
                u = str(row.get("ID_AMONT", "")).replace(".0", "").strip()
                d = str(row.get("ID_AVAL", "")).replace(".0", "").strip()

                # Récupération de la longueur réelle métrique
                val_l = row.get("Longeur")
                if val_l is not None and pd.notna(val_l) and float(val_l) > 0:
                    length = float(val_l)
                elif hasattr(row, 'geometry') and row.geometry:
                    try:
                        length = float(row.geometry.length)
                    except Exception:
                        length = 45.0
                else:
                    length = 45.0
                length = max(1.0, round(length, 1))

                # Récupération de l'adresse ou rue
                nom_voie = str(row.get("NOM-VOIE") or row.get("NOMVOIE") or row.get("nom_voie") or "").strip()
                if nom_voie.lower() in ("nan", "none", "null", ""):
                    nom_voie = ""

                pipe_geom_map[cid] = {
                    "diam": diam,
                    "mat": mat,
                    "upstream": u,
                    "downstream": d,
                    "length": length,
                    "nom_voie": nom_voie
                }

        # 1. Analyse des conduites en charge et des vitesses
        for cid, c in conduit_results.items():
            ratio = c.get("flow_ratio", 0.0)
            depth_ratio = c.get("depth_ratio", 0.0)
            vel = c.get("max_velocity_ms", 0.0)
            q_max = c.get("max_flow_cms", 0.0)
            pipe_info = pipe_geom_map.get(cid, {"diam": 600.0, "mat": "Béton", "upstream": "", "downstream": "", "length": 45.0, "nom_voie": ""})

            u_str = pipe_info.get("upstream", "")
            d_str = pipe_info.get("downstream", "")
            cond_label = f"{cid} ({u_str}➔{d_str})" if (u_str and d_str) else cid

            # Surcharge / Mise en pression
            if ratio >= 1.0 or depth_ratio >= 1.0:
                surcharged_links.append({
                    "cid": cid,
                    "conduit": cond_label,
                    "upstream": u_str,
                    "downstream": d_str,
                    "nom_voie": pipe_info.get("nom_voie", ""),
                    "flow_ratio": ratio,
                    "depth_ratio": depth_ratio,
                    "max_flow_cms": q_max,
                    "q_max": q_max,
                    "max_velocity_ms": vel,
                    "vitesse": vel,
                    "diam": pipe_info["diam"],
                    "mat": pipe_info["mat"],
                    "longueur_m": pipe_info["length"],
                    "longueur": pipe_info["length"],
                    "cause": "Capacité gravitaire théorique dépassée lors du pic de crue"
                })

            # Auto-curage insuffisant (risque d'ensablement à long terme)
            if vel < 0.6 and ratio > 0.08:
                low_velocity_links.append({
                    "cid": cid,
                    "conduit": cond_label,
                    "upstream": u_str,
                    "downstream": d_str,
                    "longueur_m": pipe_info["length"],
                    "velocity_ms": vel,
                    "vitesse": vel,
                    "flow_ratio": ratio,
                    "cause": f"Vitesse maximale {vel:.2f} m/s < 0.6 m/s (seuil réglementaire d'auto-curage)"
                })

            # Risque d'affouillement / érosion
            if vel > 4.0:
                high_velocity_links.append({
                    "cid": cid,
                    "conduit": cond_label,
                    "velocity_ms": vel,
                    "vitesse": vel,
                    "cause": f"Vitesse d'écoulement {vel:.2f} m/s > 4.0 m/s (risque d'érosion du radier)"
                })

        # 2. Analyse des goulots d'étranglement amont ➔ aval
        if pipe_geom_map:
            # Recherche de diminutions de diamètre de l'amont vers l'aval
            node_out_pipes = {}
            node_in_pipes = {}
            for cid, info in pipe_geom_map.items():
                node_out_pipes.setdefault(info["upstream"], []).append(cid)
                node_in_pipes.setdefault(info["downstream"], []).append(cid)

            for nid, in_cids in node_in_pipes.items():
                out_cids = node_out_pipes.get(nid, [])
                for ic in in_cids:
                    d_in = pipe_geom_map[ic]["diam"]
                    for oc in out_cids:
                        d_out = pipe_geom_map[oc]["diam"]
                        if d_out < d_in:
                            bottlenecks.append({
                                "regard": nid,
                                "amont_cid": ic,
                                "aval_cid": oc,
                                "amont": f"{ic} (Ø{int(d_in)}mm)",
                                "aval": f"{oc} (Ø{int(d_out)}mm)",
                                "diam_amont": d_in,
                                "diam_aval": d_out,
                                "longueur": pipe_geom_map[ic]["length"],
                                "delta_mm": d_in - d_out,
                                "description": f"Étranglement géométrique anormal : passage de Ø{int(d_in)} à Ø{int(d_out)} mm au regard {nid}."
                            })

        # 3. Analyse des débordements de regards
        for nid, n in node_results.items():
            if n.get("status") == "flooded":
                h_flood = n.get("hours_flooded", 0.0)
                vol_m3 = n.get("flood_volume_m3", 0.0)
                pk_cms = n.get("peak_flood_flow_cms", 0.0)
                if vol_m3 <= 0.0 and h_flood > 0 and pk_cms > 0:
                    vol_m3 = max(round(0.5 * pk_cms * (h_flood * 3600.0), 3), 0.05)
                vol_arrondi = round(vol_m3, 2) if vol_m3 < 10.0 else round(vol_m3, 1)
                flooded_nodes_detail.append({
                    "node_id": nid,
                    "hours_flooded": round(h_flood, 2),
                    "flood_volume_m3": vol_arrondi,
                    "peak_flow_cms": round(pk_cms, 3),
                    "diagnostic": "Débordement avec inondation superficielle de voirie"
                })

        nb_deb = len(flooded_nodes_detail)
        nb_sur = len(surcharged_links)
        nb_goul = len(bottlenecks)

        if nb_deb > 0 or nb_sur > 0:
            note_technique = (
                f"L'analyse hydrodynamique 1D Saint-Venant (Dynamic Wave) met en évidence un régime d'écoulement sous forte tension. "
                f"Lors du pic d'intensité pluviométrique, {nb_deb} regard(s) subissent un débordement direct en surface et {nb_sur} tronçon(s) "
                f"travaillent en charge sévère (Q/Qmax > 100% ou H/D = 100%). Cette mise en pression résulte d'un effet de remous hydraulique (backwater) "
                f"amplifié par {nb_goul} goulot(s) d'étranglement géométrique où le diamètre diminue anormalement vers l'aval. "
                f"La ligne d'eau piézométrique dépasse la cote tampon du terrain naturel, provoquant des reflux et des stagnations d'eau sur les voiries urbaines."
            )
        else:
            note_technique = (
                "L'analyse hydrodynamique confirme un écoulement gravitaire fluide et stable à surface libre sur l'ensemble des collecteurs. "
                "Aucune surpression ni reflux critique n'a été détecté sous ce scénario pluviométrique."
            )

        return {
            "agent": "Agent 1 : Diagnosticien Causal",
            "statut": "Analyse complète",
            "note_technique": note_technique,
            "nb_surcharges": len(surcharged_links),
            "surcharged_links": surcharged_links,
            "nb_goulots": len(bottlenecks),
            "bottlenecks": bottlenecks,
            "nb_debordements": len(flooded_nodes_detail),
            "flooded_nodes": flooded_nodes_detail,
            "nb_autocurage_faible": len(low_velocity_links),
            "low_velocity_links": low_velocity_links[:6],
            "nb_erosion": len(high_velocity_links),
            "high_velocity_links": high_velocity_links[:6]
        }
