"""
Module de construction et de fiabilisation topologique du graphe orienté.
Fichier : src/domain/graphe_reseau.py
"""

from typing import Dict, Any, List
import math
import networkx as nx
import geopandas as gpd
from shapely.geometry import Point, LineString, MultiLineString


def _identifiant_reseau(value):
    """Normalise un identifiant SIG et rejette les valeurs nulles pandas."""
    if value is None:
        return None
    texte = str(value).strip()
    if not texte or texte.lower() in {'nan', 'none', 'null'}:
        return None
    if texte.endswith('.0'):
        texte = texte[:-2]
    return texte

class ConstructeurGrapheReseau:
    def __init__(self, seuil_pente_min: float = 0.001, tolerance_raccordement: float = 2.0):
        self.seuil_pente_min = seuil_pente_min
        self.tolerance_raccordement = tolerance_raccordement
        self.anomalies_topologiques: List[Dict[str, Any]] = []
        self._index_noeuds = {}

    def _construire_index_noeuds(self, G: nx.DiGraph):
        taille = max(self.tolerance_raccordement, 1e-9)
        self._index_noeuds = {}
        for noeud, data in G.nodes(data=True):
            x, y = data.get('x'), data.get('y')
            if x is None or y is None:
                continue
            cellule = (math.floor(float(x) / taille), math.floor(float(y) / taille))
            self._index_noeuds.setdefault(cellule, []).append((float(x), float(y), noeud))

    def _noeud_proche(self, point: Point, G: nx.DiGraph):
        candidats = []
        taille = max(self.tolerance_raccordement, 1e-9)
        cellule_x = math.floor(point.x / taille)
        cellule_y = math.floor(point.y / taille)
        for delta_x in (-1, 0, 1):
            for delta_y in (-1, 0, 1):
                for x, y, noeud in self._index_noeuds.get(
                    (cellule_x + delta_x, cellule_y + delta_y), []
                ):
                    candidats.append((point.distance(Point(x, y)), noeud))
        if not candidats:
            return None
        distance, noeud = min(candidats)
        return noeud if distance <= self.tolerance_raccordement else None

    @staticmethod
    def _extremites(geom):
        if isinstance(geom, LineString) and len(geom.coords) >= 2:
            return Point(geom.coords[0]), Point(geom.coords[-1])
        if isinstance(geom, MultiLineString) and geom.geoms:
            return Point(geom.geoms[0].coords[0]), Point(geom.geoms[-1].coords[-1])
        return None, None

    def construire_graphe(
        self,
        gdf_noeuds: gpd.GeoDataFrame,
        gdf_troncons: gpd.GeoDataFrame
    ) -> nx.DiGraph:
        G = nx.DiGraph()
        self.anomalies_topologiques.clear()

        for _, row in gdf_noeuds.iterrows():
            raw_id = row.get(
                'id', row.get('id_noeud', row.get('swmm_id', row.get('code', row.get('Code', row.get('NOM', row.name)))))
            )
            noeud_id = _identifiant_reseau(raw_id) or str(row.name)
            geom = row.geometry if hasattr(row, 'geometry') else None
            x = geom.x if isinstance(geom, Point) else row.get('x', row.get('COORDX', 0.0))
            y = geom.y if isinstance(geom, Point) else row.get('y', row.get('COORDY', 0.0))
            
            # Extraction cote tampon (COORDZ)
            z_tampon = row.get(
                'cote_tampon', row.get('z_sol', row.get('COORDZ', row.get('elevation', None)))
            )
            
            # Extraction cote radier : directe ou par soustraction (COORDZ - PROFRADI)
            z_radier = row.get('cote_radier', row.get('z_radier', None))
            profradi = row.get('PROFRADI', row.get('profradi', None))
            if z_radier is None and z_tampon is not None and profradi is not None:
                try:
                    z_radier = float(z_tampon) - float(profradi)
                except ValueError:
                    pass
            
            type_noeud = str(row.get(
                'original_gdf', row.get(
                    'type', row.get('node_type', row.get('nature', row.get('TYPERES', 'regard')))
                )
            )).lower()

            # Anti-collision d'identifiants entre couches distinctes (ex: regard vs rejet partageant le même ID)
            if noeud_id in G:
                old_x = G.nodes[noeud_id].get('x', 0.0)
                old_y = G.nodes[noeud_id].get('y', 0.0)
                if Point(x, y).distance(Point(old_x, old_y)) > 2.0:
                    noeud_id = f"{noeud_id}_{type_noeud}_{int(x)}"

            G.add_node(
                noeud_id,
                geometry=geom,
                x=float(x),
                y=float(y),
                z_tampon=float(z_tampon) if z_tampon is not None else None,
                z_radier=float(z_radier) if z_radier is not None else None,
                type=type_noeud,
                nom=row.get('nom', row.get('NOM', row.get('name'))),
                nom_voie=row.get('nom_voie', row.get('NOMVOIE', row.get('NOM-VOIE'))),
                commune=row.get('commune', row.get('COMMUNE')),
                adresse=row.get('adresse', row.get('ADRESSE')),
                type_ouvrage=row.get('type_ouvrage', row.get('TYPEOUVR', row.get('TYPE_OUVR'))),
                h_seuil=row.get('h_seuil', row.get('H_de_Seuil', row.get('H_DE_SEUIL'))),
                milieu_rec=row.get('milieu_rec', row.get('MILIEUREC', row.get('MILIEU_REC'))),
                zone_collecte=row.get('zone_collecte', row.get('ZONECOLLE', row.get('ZONE_COLLE'))),
            )

        self._construire_index_noeuds(G)

        for _, row in gdf_troncons.iterrows():
            troncon_id = str(row.get('id', row.get('id_troncon', row.name)))
            u_init = _identifiant_reseau(row.get('noeud_amont', row.get('amont', row.get('ID_AMONT'))))
            v_init = _identifiant_reseau(row.get('noeud_aval', row.get('aval', row.get('ID_AVAL'))))
            geom = row.geometry if hasattr(row, 'geometry') else None
            diametre = row.get('diametre', row.get('diametre_mm', row.get('DIAMETRE', 300)))
            longueur = row.get('longueur', row.get('length', row.get('Longeur', 0.0)))
            type_conduite = str(row.get('type', row.get('nature', row.get('Fonction_1', 'gravitaire')))).lower()

            point_depart, point_arrivee = self._extremites(geom)

            # Validation géométrique amont : rejeter les raccordements aberrants à des centaines de mètres
            if u_init in G and point_depart is not None:
                d_u = point_depart.distance(Point(G.nodes[u_init].get('x', 0), G.nodes[u_init].get('y', 0)))
                if d_u > self.tolerance_raccordement:
                    u_init = self._noeud_proche(point_depart, G)
            elif u_init not in G and point_depart is not None:
                u_snapped = self._noeud_proche(point_depart, G)
                if u_snapped is not None:
                    u_init = u_snapped
                    self.anomalies_topologiques.append({
                        'troncon_id': troncon_id,
                        'type': 'raccordement_geometrique',
                        'detail': f"Extrémité amont raccordée au nœud '{u_snapped}'."
                    })

            # Validation géométrique aval : rejeter les raccordements aberrants à des centaines de mètres
            if v_init in G and point_arrivee is not None:
                d_v = point_arrivee.distance(Point(G.nodes[v_init].get('x', 0), G.nodes[v_init].get('y', 0)))
                if d_v > self.tolerance_raccordement:
                    v_init = self._noeud_proche(point_arrivee, G)
            elif v_init not in G and point_arrivee is not None:
                v_snapped = self._noeud_proche(point_arrivee, G)
                if v_snapped is not None:
                    v_init = v_snapped
                    self.anomalies_topologiques.append({
                        'troncon_id': troncon_id,
                        'type': 'raccordement_geometrique',
                        'detail': f"Extrémité aval raccordée au nœud '{v_snapped}'."
                    })

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
                    self.anomalies_topologiques.append({
                        'troncon_id': troncon_id,
                        'type': 'contre_pente',
                        'detail': f"Radiers quasi égaux entre '{u_init}' et '{v_init}'."
                    })
            elif 'refoulement' not in type_conduite and 'pompage' not in type_conduite:
                self.anomalies_topologiques.append({
                    'troncon_id': troncon_id,
                    'type': 'cote_radier_manquante',
                    'detail': f"Cote radier manquante pour '{u_init}' ou '{v_init}'."
                })

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
                nom_voie=row.get('nom_voie', row.get('NOM-VOIE', row.get('NOMVOIE'))),
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
    from pathlib import Path
    from typing import Optional
    import geopandas as gpd
    from src.domain.processeur_noeuds import ProcesseurNoeuds
    from src.domain.processeur_conduites import ProcesseurConduites
    
    if not chemin_gpkg or not Path(chemin_gpkg).exists():
        default_candidate = r"D:\IA Water Data Analysis\Assainissement\Assainissement_Ville.gpkg"
        if Path(default_candidate).exists():
            chemin_gpkg = default_candidate
        else:
            demo_cand = Path(__file__).resolve().parents[2] / "data" / "demo_reseau.gpkg"
            chemin_gpkg = str(demo_cand) if demo_cand.exists() else None

    if not chemin_gpkg or not Path(chemin_gpkg).exists():
        return nx.DiGraph()

    try:
        available_layers = gpd.list_layers(chemin_gpkg)['name'].tolist()
    except Exception:
        available_layers = []

    def _trouver_couche(mots_cles: list, exclusions: list = None) -> Optional[str]:
        exclusions = exclusions or []
        for nom in available_layers:
            nom_bas = nom.lower()
            if any(e in nom_bas for e in exclusions):
                continue
            if any(m in nom_bas for m in mots_cles):
                return nom
        return None

    couche_regards = _trouver_couche(['regard'])
    couche_rejets = _trouver_couche(['rejet', 'outfall', 'exutoire'])
    couche_ouvrages = _trouver_couche(['ouvrage'])
    couche_stations = _trouver_couche(['station', 'pompage', 'relevage'])
    couche_step = _trouver_couche(['step', 'epuration'])
    couche_canalisations = _trouver_couche(['canalisat', 'conduit', 'pipe', 'troncon'], exclusions=['désaffect', 'desaffect'])

    # 1. Charger les couches
    try:
        regards_gdf = gpd.read_file(chemin_gpkg, layer=couche_regards) if couche_regards else gpd.GeoDataFrame()
    except Exception:
        regards_gdf = gpd.GeoDataFrame()
        
    try:
        rejets_gdf = gpd.read_file(chemin_gpkg, layer=couche_rejets) if couche_rejets else gpd.GeoDataFrame()
    except Exception:
        rejets_gdf = gpd.GeoDataFrame()
        
    try:
        ouvrages_gdf = gpd.read_file(chemin_gpkg, layer=couche_ouvrages) if couche_ouvrages else gpd.GeoDataFrame()
    except Exception:
        ouvrages_gdf = gpd.GeoDataFrame()
        
    try:
        stations_gdf = gpd.read_file(chemin_gpkg, layer=couche_stations) if couche_stations else gpd.GeoDataFrame()
    except Exception:
        stations_gdf = gpd.GeoDataFrame()
        
    try:
        step_gdf = gpd.read_file(chemin_gpkg, layer=couche_step) if couche_step else gpd.GeoDataFrame()
    except Exception:
        step_gdf = gpd.GeoDataFrame()
        
    try:
        canalisations_gdf = gpd.read_file(chemin_gpkg, layer=couche_canalisations) if couche_canalisations else gpd.GeoDataFrame()
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
    
    # Store CRS for later reprojection to EPSG:4326
    if not regards_gdf.empty and regards_gdf.crs:
        G.graph['crs'] = regards_gdf.crs
    elif not canalisations_gdf.empty and canalisations_gdf.crs:
        G.graph['crs'] = canalisations_gdf.crs
        
    return G


def trouver_exutoires(G: nx.DiGraph):
    """Compatibilité Flask : retourne les exutoires sous forme de liste."""
    from src.domain.detecteur_clusters import trouver_exutoires_physiques
    return [
        {'noeud': noeud, 'nom': info.get('nom', str(noeud)), **info}
        for noeud, info in trouver_exutoires_physiques(G).items()
    ]


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

