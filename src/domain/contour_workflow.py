"""
src/domain/contour_workflow.py
Remplacement du workflow complet de génération des bassins.
"""

from typing import Dict, Any, Optional
import networkx as nx
import geopandas as gpd
from src.domain.graphe_reseau import ConstructeurGrapheReseau
from src.domain.detecteur_clusters import (
    identifier_exutoires,
    partitionner_bassins_exclusifs,
    tracer_cluster_depuis_exutoire,
    exporter_bassins_geojson
)
from src.domain.extracteur_contours import ExtracteurContoursBassin


class ContourWorkflow:
    """
    Point d'entrée unique utilisé par le serveur Web et les contrôleurs
    pour exécuter le diagnostic et la sectorisation des bassins.
    """

    def __init__(self, largeur_drainage_m: float = 20.0):
        self.constructeur_graphe = ConstructeurGrapheReseau()
        self.extracteur = ExtracteurContoursBassin(largeur_bande_m=largeur_drainage_m)
        self.G: Optional[nx.DiGraph] = None
        self.bassins_calcules: Dict[str, Any] = {}

    def initialiser_depuis_geodataframes(
        self,
        gdf_noeuds: gpd.GeoDataFrame,
        gdf_troncons: gpd.GeoDataFrame
    ) -> Dict[str, Any]:
        """
        Construit le graphe physique et vérifie les anomalies topologiques.
        Remplace l'ancienne initialisation non orientée.
        """
        self.G = self.constructeur_graphe.construire_graphe(gdf_noeuds, gdf_troncons)
        return {
            'nb_noeuds': self.G.number_of_nodes(),
            'nb_troncons': self.G.number_of_edges(),
            'anomalies': self.constructeur_graphe.anomalies_topologiques
        }

    def executer_partitionnement_complet(self) -> Dict[str, Any]:
        """
        Exécute le découpage complet et génère le GeoJSON pour l'interface web.
        Remplace l'ancien appel à 'detecteur_clusters' / 'extraire_contours'.
        """
        if self.G is None:
            raise ValueError("Le réseau n'est pas initialisé.")

        # 1. Détection des exutoires
        exutoires = identifier_exutoires(self.G)

        # 2. Découpage sans chevauchement
        self.bassins_calcules = partitionner_bassins_exclusifs(self.G, exutoires)

        # 3. Calcul des géométries réalistes
        for b_id, b_data in self.bassins_calcules.items():
            poly = self.extracteur.extraire_contour_bassin(
                self.G, b_data['edges'], b_data['noeuds']
            )
            b_data['polygon'] = poly
            b_data['surface_ha'] = round(poly.area / 10000.0, 2) if poly else 0.0

        # 4. Formatage direct pour Leaflet
        return exporter_bassins_geojson(self.bassins_calcules)

    def obtenir_bassin_noeud(self, noeud_id: str) -> Dict[str, Any]:
        """
        Utilisé lors du clic sur la carte pour surligner le bassin amont d'un regard.
        """
        if self.G is None or noeud_id not in self.G:
            return {}

        cluster = tracer_cluster_depuis_exutoire(self.G, noeud_id)
        poly = self.extracteur.extraire_contour_bassin(self.G, cluster['edges'], cluster['noeuds'])

        return {
            'exutoire': noeud_id,
            'surface_ha': round(poly.area / 10000.0, 2) if poly else 0.0,
            'longueur_m': cluster['longueur_totale_m'],
            'noeuds': cluster['noeuds'],
            'troncons': [e[3].get('id', '') for e in cluster['edges']],
            'geojson': poly.__geo_interface__ if poly else None
        }