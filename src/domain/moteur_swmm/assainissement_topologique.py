# -*- coding: utf-8 -*-
"""
================================================================================
Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
Auteur : Dr Abdelhakim KELLOUCHE
Date de création : 2026-04-20
Date de modification : 2026-11-08
Objet : Résolution altimétrique et assainissement topologique pour solveur SWMM 5.2
================================================================================
"""

import logging
from typing import Dict, Any, Optional, Tuple, List, Set
import pandas as pd
import geopandas as gpd
import networkx as nx

from src.domain.moteur_swmm.constants import _clean_node_id

logger = logging.getLogger("swmm_platform.moteur_swmm.assainissement_topologique")


def _resoudre_altimetrie_noeuds(
    regards: gpd.GeoDataFrame,
    canalisations: gpd.GeoDataFrame,
    rejets: Optional[gpd.GeoDataFrame],
    outfall_code: str,
    pente_moyenne_pct: Optional[float] = None
) -> Tuple[Dict[str, float], str]:
    """
    Détermine la cote altimétrique (radier) de chaque nœud du réseau.
    1. Si des cotes réelles valides existent (PROFRADI, COTTN, COORDZ), elles sont utilisées.
    2. Sinon, si une pente moyenne est fournie par l'utilisateur (ex: 1.0%),
       calcule les cotes par propagation topologique amont-aval depuis l'exutoire.
    3. Sinon, lève une exception bloquante pour empêcher une simulation avec pente nulle.
    """
    alt_candidates = ["PROFRADI", "COTTN", "COORDZ", "Z", "cote_tampon", "cote_radier"]
    col_trouvee = None
    for c in alt_candidates:
        if c in regards.columns:
            non_nulls = pd.to_numeric(regards[c], errors="coerce").dropna()
            if len(non_nulls) >= len(regards) * 0.5:
                if (non_nulls.max() - non_nulls.min()) > 0.2:
                    col_trouvee = c
                    break

    elevations: Dict[str, float] = {}

    if col_trouvee:
        for idx, r in regards.iterrows():
            nid = _clean_node_id(r.get("Code"), fallback=f"REG_{idx+1}")
            val = float(r[col_trouvee]) if pd.notna(r[col_trouvee]) else 100.0
            if col_trouvee in ("COTTN", "cote_tampon"):
                prof = float(r["Profondeur"]) if ("Profondeur" in r and pd.notna(r["Profondeur"]) and r["Profondeur"] > 0) else 2.0
                elevations[nid] = round(val - prof, 3)
            else:
                elevations[nid] = round(val, 3)

        # Vérifier si des nœuds dans rejets ont aussi une altimétrie
        if rejets is not None and len(rejets) > 0:
            for idx, rj in rejets.iterrows():
                r_id = _clean_node_id(rj.get("Code") or rj.get("CODE") or rj.get("id") or rj.get("NOM"), fallback=f"REJ_{idx+1}")
                val = None
                for ac in [col_trouvee, "PROFRADI", "COTTN", "COORDZ", "Z", "COTETN"]:
                    if ac and ac in rj and pd.notna(rj[ac]):
                        try:
                            val = float(rj[ac])
                            if ac in ("COTTN", "cote_tampon", "COTETN"):
                                prof = float(rj.get("Profondeur", 2.0)) if ("Profondeur" in rj and pd.notna(rj["Profondeur"]) and rj["Profondeur"] > 0) else 2.0
                                val = val - prof
                            break
                        except (ValueError, TypeError):
                            continue
                if val is not None:
                    elevations[r_id] = round(val, 3)
                elif r_id == outfall_code and elevations:
                    elevations[r_id] = round(min(elevations.values()) - 1.0, 3)

        return elevations, f"Données réelles SIG ({col_trouvee})"

    # Pas de données altimétriques valides dans le SIG
    if pente_moyenne_pct is None or float(pente_moyenne_pct) <= 0:
        raise ValueError(
            "Données altimétriques absentes : Le réseau ne contient aucune cote de radier ou altitude valide (Z/COTTN). "
            "Pour éviter des calculs hydrodynamiques erronés (surcharges artificielles et débits aberrants causés par une pente nulle), "
            "veuillez renseigner une pente moyenne (%) dans les paramètres de simulation."
        )

    pente_fraction = float(pente_moyenne_pct) / 100.0
    outfall_z = 100.0

    G = nx.Graph()
    for _, pipe in canalisations.iterrows():
        u = _clean_node_id(pipe.get("ID_AMONT"))
        v = _clean_node_id(pipe.get("ID_AVAL"))
        l_cand = pipe.get("Longeur") or pipe.get("LONGUEUR") or pipe.get("Longueur") or pipe.get("length")
        if l_cand and float(l_cand) > 0:
            length = float(l_cand)
        elif hasattr(pipe, 'geometry') and pipe.geometry is not None and not pipe.geometry.is_empty:
            length = float(pipe.geometry.length)
        else:
            length = 5.0
        if u and v and u != v:
            G.add_edge(u, v, weight=max(1.0, length))

    outfall_geom = None
    for idx, r in regards.iterrows():
        nid = _clean_node_id(r.get("Code"), fallback=f"REG_{idx+1}")
        if nid == outfall_code:
            outfall_geom = r.geometry
            break
    if outfall_geom is None and rejets is not None and len(rejets) > 0:
        for idx, rj in rejets.iterrows():
            r_id = _clean_node_id(rj.get("Code") or rj.get("CODE") or rj.get("id") or rj.get("NOM"), fallback=f"REJ_{idx+1}")
            if r_id == outfall_code:
                outfall_geom = rj.geometry
                break

    try:
        lengths_dict = nx.single_source_dijkstra_path_length(G, source=outfall_code, weight="weight") if (G.has_node(outfall_code)) else {}
    except Exception:
        lengths_dict = {}

    for idx, r in regards.iterrows():
        nid = _clean_node_id(r.get("Code"), fallback=f"REG_{idx+1}")
        if nid == outfall_code:
            elevations[nid] = outfall_z
        else:
            if nid in lengths_dict:
                dist = lengths_dict[nid]
            elif outfall_geom and hasattr(r, 'geometry') and r.geometry:
                try:
                    dist = float(r.geometry.distance(outfall_geom)) * 1.25
                except Exception:
                    dist = 100.0
            else:
                dist = 100.0
            elevations[nid] = round(outfall_z + (dist * pente_fraction), 3)

    elevations[outfall_code] = outfall_z
    return elevations, f"Pente moyenne utilisateur ({pente_moyenne_pct}%)"


def _assainir_topologie_swmm(inp_text: str) -> str:
    """
    Garantit la conformité absolue avec le solveur Saint-Venant 1D (DYNWAVE) d'EPA SWMM 5.2 :
    Règle DYNWAVE (Erreur 141) : Tout nœud [OUTFALLS] ne doit STRICTEMENT avoir :
    - au maximum qu'UN SEUL tronçon entrant (inlet link <= 1)
    - AUCUN tronçon sortant (outlet link == 0)
    - aucune présence simultanée dans [JUNCTIONS]
    Si un exutoire possède plusieurs tronçons entrants ou un tronçon sortant, il est automatiquement
    converti en regard [JUNCTIONS] et déchargé via un tronçon court vers un exutoire terminal dédié.
    """
    lines = inp_text.splitlines()
    sections: Dict[Optional[str], List[str]] = {}
    current_sec: Optional[str] = None

    for line in lines:
        stripped = line.strip()
        if stripped.startswith('[') and stripped.endswith(']'):
            current_sec = stripped.upper()
            sections[current_sec] = []
        elif current_sec:
            sections[current_sec].append(line)
        else:
            if None not in sections:
                sections[None] = []
            sections[None].append(line)

    if '[OUTFALLS]' not in sections or '[CONDUITS]' not in sections:
        return inp_text

    # 1. Recenser les nœuds de [OUTFALLS]
    outfalls_info: Dict[str, Dict[str, Any]] = {}
    for idx, l in enumerate(sections['[OUTFALLS]']):
        st = l.strip()
        if not st or st.startswith(';;'):
            continue
        parts = st.split()
        if parts:
            name = parts[0]
            elev = float(parts[1]) if len(parts) > 1 else 100.0
            outfalls_info[name] = {"idx": idx, "line": l, "elev": elev, "parts": parts}

    # 2. Recenser les jonctions
    junctions_info: Dict[str, Dict[str, Any]] = {}
    if '[JUNCTIONS]' in sections:
        for idx, l in enumerate(sections['[JUNCTIONS]']):
            st = l.strip()
            if not st or st.startswith(';;'):
                continue
            parts = st.split()
            if parts:
                name = parts[0]
                elev = float(parts[1]) if len(parts) > 1 else 100.0
                prof = float(parts[2]) if len(parts) > 2 else 2.0
                junctions_info[name] = {"idx": idx, "line": l, "elev": elev, "prof": prof, "parts": parts}

    # 3. Recenser les conduites
    conduit_inlets: Dict[str, List[str]] = {}
    conduit_outlets: Dict[str, List[str]] = {}
    for l in sections['[CONDUITS]']:
        st = l.strip()
        if not st or st.startswith(';;'):
            continue
        parts = st.split()
        if len(parts) >= 3:
            cid, u, d = parts[0], parts[1], parts[2]
            conduit_inlets.setdefault(d, []).append(cid)
            conduit_outlets.setdefault(u, []).append(cid)

    # 4. Détecter les violations d'exutoires
    outfalls_to_convert: Dict[str, Dict[str, Any]] = {}
    for out_name, odata in outfalls_info.items():
        inlets = conduit_inlets.get(out_name, [])
        outlets = conduit_outlets.get(out_name, [])
        if len(inlets) > 1 or len(outlets) > 0:
            outfalls_to_convert[out_name] = {
                "inlets": inlets,
                "outlets": outlets,
                "elev": odata["elev"]
            }

    # 5. Dédupliquer [OUTFALLS] si des noms identiques apparaissent plusieurs fois
    seen_out_names: Set[str] = set()
    deduped_outfalls = []
    for l in sections['[OUTFALLS]']:
        st = l.strip()
        if st and not st.startswith(';;'):
            parts = st.split()
            if parts:
                o_n = parts[0]
                if o_n in seen_out_names:
                    continue
                seen_out_names.add(o_n)
        deduped_outfalls.append(l)
    sections['[OUTFALLS]'] = deduped_outfalls

    if not outfalls_to_convert:
        # Nettoyer les doublons stricts entre [JUNCTIONS] et [OUTFALLS]
        if '[JUNCTIONS]' in sections:
            new_jlines = []
            modified = False
            for l in sections['[JUNCTIONS]']:
                st = l.strip()
                if st and not st.startswith(';;'):
                    parts = st.split()
                    if parts and parts[0] in outfalls_info:
                        modified = True
                        continue
                new_jlines.append(l)
            if modified:
                sections['[JUNCTIONS]'] = new_jlines
                rebuilt = []
                for sec_name, sec_lines in sections.items():
                    if sec_name is not None:
                        rebuilt.append(sec_name)
                    rebuilt.extend(sec_lines)
                return "\n".join(rebuilt)
        return inp_text

    # Coordonnées
    coords_dict: Dict[str, Tuple[str, str]] = {}
    if '[COORDINATES]' in sections:
        for idx, l in enumerate(sections['[COORDINATES]']):
            st = l.strip()
            if not st or st.startswith(';;'):
                continue
            parts = st.split()
            if len(parts) >= 3:
                coords_dict[parts[0]] = (parts[1], parts[2])

    # Convertir chaque exutoire fautif en Junction + créer un Outfall terminal dédié
    new_outfall_lines = []
    removed_outfalls = set(outfalls_to_convert.keys())
    for l in sections['[OUTFALLS]']:
        st = l.strip()
        if st and not st.startswith(';;'):
            parts = st.split()
            if parts and parts[0] in removed_outfalls:
                continue
        new_outfall_lines.append(l)

    if '[JUNCTIONS]' not in sections:
        sections['[JUNCTIONS]'] = [";;Name           Elevation  MaxDepth   InitDepth  SurDepth   Aponded"]

    for out_name, info in outfalls_to_convert.items():
        z_node = info["elev"]
        # Ajouter le nœud converti dans [JUNCTIONS] s'il n'y est pas
        if out_name not in junctions_info:
            sections['[JUNCTIONS]'].append(f"{out_name:<16} {z_node:<10.3f} 2.000      0.000      0.000      0.000")
            junctions_info[out_name] = {"elev": z_node}

        # Créer le véritable exutoire terminal dédié
        term_out_name = f"OUT_SAFE_{out_name}"
        term_z = round(z_node - 0.05, 3)
        new_outfall_lines.append(f"{term_out_name:<16} {term_z:<10.3f} FREE                        NO")

        # Créer le tronçon court de décharge unique vers l'exutoire terminal
        cid_out = f"C_SAFE_{out_name}"
        sections['[CONDUITS]'].append(f"{cid_out:<16} {out_name:<16} {term_out_name:<16} 5.00       0.0130     0.000      0.000      0.000      0.000")

        if '[XSECTIONS]' not in sections:
            sections['[XSECTIONS]'] = [";;Link           Shape        Geom1            Geom2      Geom3      Geom4      Barrels    Culvert"]
        sections['[XSECTIONS]'].append(f"{cid_out:<16} CIRCULAR     1.200            0.000      0.000      0.000      1")

        # Coordonnées
        if '[COORDINATES]' in sections and out_name in coords_dict:
            cx, cy = coords_dict[out_name]
            try:
                nx_val = float(cx) + 5.0
                ny_val = float(cy) + 5.0
                sections['[COORDINATES]'].append(f"{term_out_name:<16} {nx_val:<18.3f} {ny_val:<18.3f}")
            except Exception:
                pass

    sections['[OUTFALLS]'] = new_outfall_lines

    # Reconstitution du texte INP
    rebuilt = []
    for sec_name, sec_lines in sections.items():
        if sec_name is not None:
            rebuilt.append(sec_name)
        rebuilt.extend(sec_lines)
    return "\n".join(rebuilt)
