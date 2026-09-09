"""
Module de construction et de fiabilisation topologique du graphe orienté.
Fichier : src/domain/graphe_reseau.py
"""

from typing import Dict, Any, List
import networkx as nx
import geopandas as gpd
from shapely.geometry import Point, LineString

class ConstructeurGrapheReseau:
    def __init__(self, seuil_pente_min: float = 0.001):
        self.seuil_pente_min = seuil_pente_min
        self.anomalies_topologiques: List[Dict[str, Any]] = []

    def construire_graphe(
        self,
        gdf_noeuds: gpd.GeoDataFrame,
        gdf_troncons: gpd.GeoDataFrame
    ) -> nx.DiGraph:
        G = nx.DiGraph()
        self.anomalies_topologiques.clear()

        for _, row in gdf_noeuds.iterrows():
            noeud_id = str(row.get('id', row.get('id_noeud', row.name)))
            geom = row.geometry if hasattr(row, 'geometry') else None
            x = geom.x if isinstance(geom, Point) else row.get('x', row.get('COORDX', 0.0))
            y = geom.y if isinstance(geom, Point) else row.get('y', row.get('COORDY', 0.0))
            
            # Extraction cote tampon (COORDZ)
            z_tampon = row.get('cote_tampon', row.get('z_sol', row.get('COORDZ', None)))
            
            # Extraction cote radier : directe ou par soustraction (COORDZ - PROFRADI)
            z_radier = row.get('cote_radier', row.get('z_radier', None))
            profradi = row.get('PROFRADI', row.get('profradi', None))
            if z_radier is None and z_tampon is not None and profradi is not None:
                try:
                    z_radier = float(z_tampon) - float(profradi)
                except ValueError:
                    pass
            
            type_noeud = str(row.get('type', row.get('nature', row.get('TYPERES', 'regard')))).lower()

            G.add_node(
                noeud_id,
                geometry=geom,
                x=float(x),
                y=float(y),
                z_tampon=float(z_tampon) if z_tampon is not None else None,
                z_radier=float(z_radier) if z_radier is not None else None,
                type=type_noeud
            )

        for _, row in gdf_troncons.iterrows():
            troncon_id = str(row.get('id', row.get('id_troncon', row.name)))
            u_init = str(row.get('noeud_amont', row.get('amont', row.get('ID_AMONT', ''))))
            v_init = str(row.get('noeud_aval', row.get('aval', row.get('ID_AVAL', ''))))
            geom = row.geometry if hasattr(row, 'geometry') else None
            diametre = row.get('diametre', row.get('diametre_mm', row.get('DIAMETRE', 300)))
            longueur = row.get('longueur', row.get('length', row.get('Longeur', 0.0)))
            type_conduite = str(row.get('type', row.get('nature', row.get('Fonction_1', 'gravitaire')))).lower()

            if not u_init or not v_init or u_init not in G or v_init not in G:
                self.anomalies_topologiques.append({
                    'troncon_id': troncon_id,
                    'type': 'noeud_orphelin',
                    'detail': f"Nœud amont '{u_init}' ou aval '{v_init}' introuvable."
                })
                continue

            # Tentative de récupération des radiers des nœuds
            z_u = G.nodes[u_init].get('z_radier')
            z_v = G.nodes[v_init].get('z_radier')
            
            u_reel, v_reel = u_init, v_init
            est_inverse = False
            contre_pente = False

            # Si c'est du refoulement, on force le sens de numérisation (l'eau peut monter)
            if 'refoulement' in type_conduite or 'pompage' in type_conduite:
                pass
            elif z_u is not None and z_v is not None:
                delta_z = z_u - z_v
                # L'eau coule du point le plus haut vers le point le plus bas (delta_z > 0).
                # Si delta_z < 0 (nœud amont plus bas que nœud aval), l'écoulement gravitaire va dans l'autre sens.
                # On tolère une petite incertitude de 1 cm (0.01 m).
                if delta_z < -0.01:
                    u_reel, v_reel = v_init, u_init
                    est_inverse = True
                    if geom and isinstance(geom, LineString):
                        geom = LineString(list(geom.coords)[::-1])
                elif abs(delta_z) <= 0.01 and longueur > 0:
                    contre_pente = True

            if longueur <= 0 and geom and isinstance(geom, LineString):
                longueur = geom.length

            pente = 0.001
            z_amont_final = G.nodes[u_reel].get('z_radier')
            z_aval_final = G.nodes[v_reel].get('z_radier')
            if z_amont_final is not None and z_aval_final is not None and longueur > 0:
                pente = max((z_amont_final - z_aval_final) / longueur, 0.0001)

            G.add_edge(
                u_reel,
                v_reel,
                key=troncon_id,
                id=troncon_id,
                geometry=geom,
                diametre_mm=float(diametre) if diametre else 300.0,
                length=float(longueur),
                pente=pente,
                type=type_conduite,
                inverse_automatiquement=est_inverse,
                est_contre_pente=contre_pente
            )

        try:
            cycles = list(nx.simple_cycles(G))
            if cycles:
                for c in cycles:
                    self.anomalies_topologiques.append({
                        'type': 'boucle_fermee',
                        'detail': f"Cycle hydraulique fermé sur : {c}"
                    })
        except Exception:
            pass

        G.graph['anomalies_topologiques'] = self.anomalies_topologiques
        return G

def construire_graphe(chemin_gpkg: str = None) -> nx.DiGraph:
    """
    Point d'entrée global. Charge les données depuis le GeoPackage
    et construit le graphe en utilisant les processeurs de noeuds et conduites.
    """
    import geopandas as gpd
    from src.domain.processeur_noeuds import ProcesseurNoeuds
    from src.domain.processeur_conduites import ProcesseurConduites
    
    chemin_gpkg = chemin_gpkg or r"D:\IA Water Data Analysis\Assainissement\Assainissement_Ville.gpkg"
    
    # 1. Charger les couches
    try:
        regards_gdf = gpd.read_file(chemin_gpkg, layer="Regards_e3c22000_8bba_45a0_a575_d60bbd4b99d3")
    except Exception:
        regards_gdf = gpd.GeoDataFrame()
        
    try:
        rejets_gdf = gpd.read_file(chemin_gpkg, layer="Rejets_3cc8eef2_2241_47a0_ad80_fd59749ab068")
    except Exception:
        rejets_gdf = gpd.GeoDataFrame()
        
    try:
        ouvrages_gdf = gpd.read_file(chemin_gpkg, layer="Ouvrages_Speciaux_4162132f_cd17_43bc_835d_2f7b46f2419f")
    except Exception:
        ouvrages_gdf = gpd.GeoDataFrame()
        
    try:
        stations_gdf = gpd.read_file(chemin_gpkg, layer="Station_de_relevage_5c8a759c_c2c5_46cb_a2be_8993c368e0c2")
    except Exception:
        stations_gdf = gpd.GeoDataFrame()
        
    try:
        step_gdf = gpd.read_file(chemin_gpkg, layer="STEP_d9ded7b2_1693_4298_baf4_6691f781d403")
    except Exception:
        step_gdf = gpd.GeoDataFrame()
        
    try:
        canalisations_gdf = gpd.read_file(chemin_gpkg, layer="Canalisations_860f298d_9fd9_40a5_bfa4_f913acc71f2e")
    except Exception:
        canalisations_gdf = gpd.GeoDataFrame()

    # 2. Traiter les nœuds
    proc_noeuds = ProcesseurNoeuds()
    noeuds_gdf, _ = proc_noeuds.traiter(regards_gdf, rejets_gdf, ouvrages_gdf, stations_gdf, step_gdf)
    
    # Si on a pas de noeuds mais on a des regards bruts, on fallback
    if noeuds_gdf.empty and not regards_gdf.empty:
        noeuds_gdf = regards_gdf
    
    # 3. Construire le graphe
    constructeur = ConstructeurGrapheReseau()
    G = constructeur.construire_graphe(noeuds_gdf, canalisations_gdf)
    return G


def calculer_ordre_topologique(G: nx.DiGraph, edges: set) -> list:
    """Calcul l'ordre topologique des conduites d'un sous-bassin."""
    try:
        # Créer un sous-graphe avec seulement les arêtes du bassin
        subG = nx.DiGraph()
        for edge in edges:
            subG.add_edge(edge[0], edge[1])
        
        # Trouver l'ordre topologique des nœuds
        nodes_order = list(nx.topological_sort(subG))
        
        # Récupérer les identifiants de tronçons dans le bon ordre
        edge_order = []
        for u in nodes_order:
            for v in subG.successors(u):
                edge_id = G.edges[u, v].get('id', G.edges[u, v].get('key', f"{u}-{v}"))
                edge_order.append(edge_id)
        return edge_order
    except nx.NetworkXUnfeasible:
        # En cas de cycle (ne devrait pas arriver si le graphe a été nettoyé)
        return []

