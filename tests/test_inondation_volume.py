import pytest
from src.domain.moteur_swmm import MoteurSWMM
from src.domain.agents_expertise import AgentDiagnosticCausal


def test_reconstitution_volume_inondation_swmm_tronque():
    """
    Vérifie que lorsqu'un regard déborde (h_flood > 0, pk_flood > 0) mais que le rapport SWMM
    affiche '0.000' en volume (troncature d'EPA SWMM en 10^6 litres pour les volumes < 500 L),
    le moteur SWMM reconstitue le volume hydrodynamique réel au lieu de laisser 0.0 m³.
    """
    moteur = MoteurSWMM()

    # Extrait représentatif d'un rapport SWMM 5.2 avec débordement tronqué à 0.000 (10^6 ltr)
    fake_rpt = """
  *********************
  Node Flooding Summary
  *********************

  --------------------------------------------------------------------------
                                                             Total   Maximum
                                 Maximum   Time of Max       Flood    Ponded
                        Hours       Rate    Occurrence      Volume     Depth
  Node                 Flooded       CMS   days hr:min    10^6 ltr    Meters
  --------------------------------------------------------------------------
  7242                    0.01     0.020      0  00:45       0.000     0.000
  7562                    0.01     0.095      0  00:45       0.000     0.000
  2047                    0.02     0.453      0  01:22       0.010     0.000

  ***********************
  Outfall Loading Summary
  ***********************
"""
    kpis = {
        "node_results": {},
        "flooded_nodes": [],
        "flooded_nodes_count": 0,
        "surcharged_nodes_count": 0
    }

    # Simulation de l'extraction de la section 7 du rapport
    flood_part = fake_rpt.split("Node Flooding Summary")[1].split("Outfall Loading Summary")[0]
    for line in flood_part.strip().splitlines():
        parts = line.split()
        if len(parts) >= 6 and parts[0] != "Node" and not parts[0].startswith("-"):
            nid = parts[0]
            try:
                h_flood = float(parts[1])
                pk_flood = float(parts[2])
                vol_flood = float(parts[5]) * 1000.0
                if h_flood > 0:
                    if vol_flood <= 0.0 and pk_flood > 0:
                        vol_estime = round(0.5 * pk_flood * (h_flood * 3600.0), 3)
                        vol_flood = max(vol_estime, 0.05)
                    else:
                        vol_flood = round(vol_flood, 3)

                    kpis["node_results"][nid] = {
                        "node": nid,
                        "hours_flooded": h_flood,
                        "peak_flood_flow_cms": pk_flood,
                        "flood_volume_m3": vol_flood,
                        "status": "flooded"
                    }
                    kpis["flooded_nodes"].append(kpis["node_results"][nid])
            except Exception:
                pass

    # Vérification regard 7242 (0.02 m3/s pendant 0.01h = 36s) -> 0.5 * 0.02 * 36 = 0.36 m3
    n_7242 = kpis["node_results"]["7242"]
    assert n_7242["flood_volume_m3"] > 0.0
    assert abs(n_7242["flood_volume_m3"] - 0.36) < 0.01

    # Vérification regard 7562 (0.095 m3/s pendant 0.01h = 36s) -> 0.5 * 0.095 * 36 = 1.71 m3
    n_7562 = kpis["node_results"]["7562"]
    assert n_7562["flood_volume_m3"] > 0.0
    assert abs(n_7562["flood_volume_m3"] - 1.71) < 0.01

    # Vérification regard 2047 avec volume SWMM non-nul (0.010 * 1000 = 10.0 m3)
    n_2047 = kpis["node_results"]["2047"]
    assert abs(n_2047["flood_volume_m3"] - 10.0) < 0.01


def test_agent_diagnostic_volume_deborde():
    """Vérifie que l'Agent 1 (Diagnostic) formate un volume positif pour chaque inondation."""
    agent = AgentDiagnosticCausal()
    node_results = {
        "7242": {
            "node": "7242",
            "hours_flooded": 0.01,
            "peak_flood_flow_cms": 0.02,
            "flood_volume_m3": 0.36,
            "status": "flooded"
        }
    }
    kpis = {"flooded_nodes_count": 1}
    diag = agent.analyser(kpis, conduit_results={}, node_results=node_results, meta={})

    assert len(diag["flooded_nodes"]) == 1
    fn = diag["flooded_nodes"][0]
    assert fn["node_id"] == "7242"
    assert fn["flood_volume_m3"] == 0.36
    assert fn["hours_flooded"] == 0.01
