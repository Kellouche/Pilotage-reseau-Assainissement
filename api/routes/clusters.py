import ast
import logging
import math
import networkx as nx
from functools import lru_cache
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from typing import List, Optional, Dict

from api.database import get_db
from api import schemas, crud

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/clusters", tags=["Clusters"])

# Cache du graphe et état
_GRAPH_CACHE = None
_GRAPH_STATUS = "pending"  # pending | building | ready | error


def _json_safe(value):
    """Convertit les valeurs pandas/NumPy non conformes JSON en valeurs sûres."""
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value

def _get_graph():
    """Get cached graph, building it once on first call."""
    global _GRAPH_CACHE, _GRAPH_STATUS
    if _GRAPH_CACHE is None:
        _GRAPH_STATUS = "building"
        try:
            from src.domain.graphe_reseau import construire_graphe
            print("[clusters] Building graph (first call)...", flush=True)
            _GRAPH_CACHE = construire_graphe()
            _GRAPH_STATUS = "ready"
            print("[clusters] Graph built and cached.", flush=True)
        except Exception as e:
            _GRAPH_STATUS = "error"
            print(f"[clusters] ERROR building graph: {e}", flush=True)
            raise
    return _GRAPH_CACHE

def _reset_graph_cache():
    """Reset the graph cache."""
    global _GRAPH_CACHE, _GRAPH_STATUS
    _GRAPH_CACHE = None
    _GRAPH_STATUS = "pending"

def get_graph_status():
    """Return current graph cache status."""
    return _GRAPH_STATUS


@router.get("", response_model=schemas.ClusterListResponse)
def list_clusters(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    """Liste tous les clusters."""
    clusters = crud.get_clusters(db=db, skip=skip, limit=limit)
    total = db.query(crud.Cluster).count()
    return {"clusters": clusters, "total": total}


@router.get("/status")
def get_cluster_status():
    """Statut du cache du graphe."""
    return {"graph_cache": _GRAPH_STATUS}


@router.post("/graph/rebuild")
def rebuild_graph_cache(background_tasks: BackgroundTasks):
    """Reconstruit le cache du graphe (utile après modification des données)."""
    _reset_graph_cache()
    # Pré-chauffer le graphe en arrière-plan pour ne pas bloquer le client
    background_tasks.add_task(_warm_graph_cache)
    return {"status": "scheduled", "message": "Reconstruction du graphe programmée"}


@router.get("/recalculate-all", include_in_schema=False)
def recalculate_all_clusters_async_precedence(background_tasks: BackgroundTasks):
    """Schedule recalculation before the generic cluster-id route can match."""
    background_tasks.add_task(_calculate_clusters_background)
    return {"status": "scheduled"}


@router.get("/{cluster_id}", response_model=schemas.ClusterResponse)
def get_cluster(cluster_id: int, db: Session = Depends(get_db)):
    """Détail d'un cluster."""
    cluster = crud.get_cluster(db, cluster_id)
    if not cluster:
        raise HTTPException(status_code=404, detail="Cluster non trouvé")
    return cluster


@router.post("/recalculate-all")
def recalculate_all_clusters(
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    persist: bool = True
):
    """Reconstruit tous les clusters en bassins exclusifs (sans chevauchement).

    Par défaut: exécution synchrone (POST) - retourne le résultat.
    Pour les appels GET (interface/rafraîchissement), voir /recalculate-all (GET) qui programme un job en arrière-plan.
    Le paramètre persist=false permet à l'interface carte de recalculer sans écrire en base, évitant les verrous SQLite.
    """
    return _calculate_clusters_sync(db, persist=persist)


@router.get("/recalculate-all")
def recalculate_all_clusters_async(background_tasks: BackgroundTasks):
    """Schedule cluster recalculation as a background task and return 202.

    Ceci évite de bloquer le client pour les opérations longues et résout le problème
    d'appels GET depuis le front qui provoquaient une 422.
    """
    background_tasks.add_task(_calculate_clusters_background)
    return {"status": "scheduled"}


# Helpers
from api.database import SessionLocal

def _calculate_clusters_sync(db: Session, persist: bool = True):
    """Wrapper to run the heavy calculation synchronously using provided DB session."""
    try:
        return _calculate_clusters(db, persist=persist)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur calcul clusters: {str(e)}")


def _warm_graph_cache():
    """Warm the graph cache in background."""
    global _GRAPH_CACHE, _GRAPH_STATUS
    if _GRAPH_CACHE is None:
        _GRAPH_STATUS = "building"
        try:
            from src.domain.graphe_reseau import construire_graphe
            print("[clusters] Warming graph cache...", flush=True)
            _GRAPH_CACHE = construire_graphe()
            _GRAPH_STATUS = "ready"
            print("[clusters] Graph cache warmed.", flush=True)
        except Exception as e:
            _GRAPH_STATUS = "error"
            print(f"[clusters] ERROR warming graph cache: {e}", flush=True)


def _calculate_clusters_background():
    """Background worker that creates its own DB session and runs the calculation."""
    db = SessionLocal()
    try:
        result = _calculate_clusters(db)
        print("[cluster][background] Recalculation completed", flush=True)
        # Optionally log result summary
        print(f"[cluster][background] {result.get('clusters_crees', 0)} clusters créés", flush=True)
    except Exception as e:
        print(f"[cluster][background] Erreur: {e}", flush=True)
    finally:
        db.close()


def _calculate_clusters(db: Session, persist: bool = True):
    """Core logic extracted from the original endpoint. Returns the same result structure."""
    from src.domain.graphe_reseau import construire_graphe, calculer_ordre_topologique
    from src.domain.detecteur_clusters import (
        trouver_exutoires_physiques,
        construire_geojson_cluster,
        calculer_statistiques,
        compter_infrastructures,
        calculer_bassin_polygon,
        calculer_polygone_urbain_estime,
        determiner_nom_bassin,
        proposer_raccordement_exutoire,
        partitionner_bassins_hydrauliques,
        detecter_composantes_orphelines,
        tracer_cluster_depuis_exutoire,
    )

    # Reconstruire le graphe
    _reset_graph_cache()
    G = _get_graph()

    # Un réseau hydraulique exploitable pour un traçage amont doit être
    # acyclique. Les cycles issus des données brutes sont isolés et cassés
    # avant les appels à ancestors(), afin d'éviter les bassins qui débordent
    # dans une composante entière et les parcours inutilement coûteux.
    G = G.copy()
    cycles_casses = []
    for _ in range(1000):
        try:
            cycle = nx.find_cycle(G)
        except nx.NetworkXNoCycle:
            break
        if not cycle:
            break
        edge = cycle[-1]
        u, v = edge[0], edge[1]
        if G.is_multigraph() and len(edge) >= 3:
            G.remove_edge(u, v, edge[2])
        else:
            G.remove_edge(u, v)
        cycles_casses.append((str(u), str(v)))
    if cycles_casses:
        print(f"[cluster] {len(cycles_casses)} cycle(s) neutralise(s) avant tracage", flush=True)

    if persist:
        # Nettoyer les anciens clusters pour éviter l'affichage de "bassins fantômes" des précédents calculs
        try:
            db.query(crud.Regard).update({crud.Regard.cluster_id: None})
            db.query(crud.Canalisation).update({crud.Canalisation.cluster_id: None})
            db.query(crud.Rejet).update({crud.Rejet.cluster_id: None})
            db.query(crud.Cluster).delete()
            db.commit()
            print("[cluster] Anciens clusters purgés de la base de données.", flush=True)
        except Exception as e:
            db.rollback()
            print(f"[cluster] Erreur lors de la purge des anciens clusters: {e}", flush=True)

    # 1. Exutoires physiques
    print("[cluster] Identification des exutoires physiques…", flush=True)
    exutoires_physiques = trouver_exutoires_physiques(G)

    if not exutoires_physiques:
        raise HTTPException(status_code=400, detail="Aucun exutoire physique identifié.")

    # 2. Composantes orphelines (pour information)
    print("[cluster] Détection des tronçons orphelins…", flush=True)
    composantes_orphelines = detecter_composantes_orphelines(G)

    print(f"[cluster] {len(exutoires_physiques)} exutoires, {len(composantes_orphelines)} composantes", flush=True)
    print(
        f"[cluster] Objectif: {len(exutoires_physiques)} bassins hydrauliques urbains, "
        "un par exutoire physique.",
        flush=True,
    )

    # 3. ── Partition hydraulique : bassins exclusifs sans inclusion ─────
    #    Conforme à la littérature : chaque bassin draine vers son exutoire,
    #    pas de chevauchement, pas d'inclusion, série et parallèle gérés.
    print("[cluster] Partition hydraulique des bassins…", flush=True)
    bassins_par_exutoire, troncons_orphelines_set, attribution = \
        partitionner_bassins_hydrauliques(G, exutoires_physiques)

    tous_les_troncons_connexes = set()
    for edges in bassins_par_exutoire.values():
        tous_les_troncons_connexes.update(edges)
    # ──────────────────────────────────────────────────────────────────

    color_map = {
        "step":    "#e74c3c",
        "rejet":   "#e67e22",
        "station": "#3498db",
        "ouvrage": "#9b59b6",
        "exutoire_implicite": "#f1c40f"
    }

    results = []
    stations_diagnostics = []
    bassins_sans_reseau = []
    emprise_occupee = None
    troncons_orphelins = set(troncons_orphelines_set)

    for i, (noeud_exutoire, info) in enumerate(exutoires_physiques.items()):
        edges = bassins_par_exutoire.get(noeud_exutoire, set())
        info_local = dict(info)
        station_estimee = "station" in str(info.get("type", "")).lower()

        # La partition exclusive est utile pour éviter les doublons, mais elle
        # peut ne rien attribuer à un exutoire. Le bassin d'un exutoire doit
        # alors être reconstruit directement par remontée de ses ancêtres.
        if station_estimee:
            raccordement = proposer_raccordement_exutoire(G, noeud_exutoire)
            info_local["raccordement"] = raccordement
            info_local["surface_source"] = "empreinte_reseau_estimee"
            stations_diagnostics.append({
                "noeud_station": str(noeud_exutoire),
                "nom": info.get("nom", str(noeud_exutoire)),
                **raccordement,
            })
            if not edges and raccordement.get("statut") in {"propose", "connecte"}:
                noeud_reseau = raccordement.get("noeud_reseau")
                trace = tracer_cluster_depuis_exutoire(G, noeud_reseau)
                edges = trace.get("edges", set())
                info_local["noeud_reseau"] = noeud_reseau
                info_local["surface_source"] = "empreinte_reseau_estimee"
        
        # RÈGLE STRICTE: un bassin ne peut pas être conçu pour un seul point ou une seule conduite.
        # Pour les exutoires implicites (bouts de réseau), on filtre les micro-réseaux (ex: < 10 conduites).
        is_implicite = info.get("type") == "exutoire_implicite"
        min_edges = 10 if is_implicite else 1
        
        if len(edges) < min_edges:
            bassins_sans_reseau.append({
                "noeud_exutoire": str(noeud_exutoire),
                "nom": info_local.get("nom", str(noeud_exutoire)),
                "type": info_local.get("type"),
                "motif": "aucun_troncon_amont_resolu",
            })
            troncons_orphelins.update(edges)
            continue

        try:
            # Déterminer le nom du bassin depuis les données de la zone drainée
            nom_bassin = determiner_nom_bassin(edges, G, exutoire_info=info_local)
            nom_exutoire = info_local["nom"]

            # Calculer les statistiques et le polygone du bassin
            stats = calculer_statistiques(G, edges)
            infrastructures = compter_infrastructures(edges)
            if station_estimee:
                noeuds_bassin = {edges_item for edge in edges for edges_item in edge[:2]}
                bassin_hull = calculer_polygone_urbain_estime(G, edges, noeuds_bassin)
            else:
                bassin_hull = calculer_bassin_polygon(edges, G=G)

            if bassin_hull is not None and not bassin_hull.is_empty:
                if emprise_occupee is not None and not emprise_occupee.is_empty:
                    bassin_hull = bassin_hull.difference(emprise_occupee)
                if bassin_hull is not None and not bassin_hull.is_empty:
                    emprise_occupee = bassin_hull if emprise_occupee is None else emprise_occupee.union(bassin_hull)

            couleur = color_map.get(info_local["type"], "#4a90e2")
            classification = {
                edge: {"type": f"connecte_{info_local['type']}", "couleur": couleur}
                for edge in edges
            }
            geojson = construire_geojson_cluster(
                G,
                edges,
                classification,
                bassin_hull=bassin_hull,
                cluster_id=i + 1,
                exutoire_node=noeud_exutoire,
                exutoire_info=info_local,
                nom_bassin=nom_bassin,
            )

            for feature in geojson.get("features", []):
                properties = feature.setdefault("properties", {})
                properties.update({
                    "nb_troncons": stats["nb_conduites"],
                    "nb_noeuds": stats["nb_noeuds"],
                    "longueur_totale_m": stats["longueur_totale_m"],
                })

            # Calculer l'ordre topologique des conduites dans ce bassin
            ordre_topologique = calculer_ordre_topologique(G, edges)

            db_stats = {
                "nb_conduites":    stats["nb_conduites"],
                "nb_noeuds":       stats["nb_noeuds"],
                "longueur_totale": stats["longueur_totale_m"],
                "diametre_min":    stats["diametre_min_m"],
                "diametre_max":    stats["diametre_max_m"],
                "diametre_moy":    stats["diametre_moy_m"],
                "nb_regards":      infrastructures["nb_regards"],
                "nb_stations":     infrastructures["nb_stations"],
                "nb_ouvrages":     infrastructures["nb_ouvrages"]
            }

            cluster = None

            if persist:
                # Chercher par nom d'exutoire (compatibilité) ou par nom de bassin
                existing = db.query(crud.Cluster).filter(
                    (crud.Cluster.nom == nom_exutoire) |
                    (crud.Cluster.nom == nom_bassin)
                ).first()

                if existing:
                    # Mettre à jour le nom si le bassin a été renommé
                    update_data = {**db_stats}
                    if existing.nom != nom_bassin:
                        update_data["nom"] = nom_bassin
                    cluster = crud.update_cluster_stats(db, existing.id, update_data)
                else:
                    cluster = crud.create_cluster(db, {
                        "nom": nom_bassin,
                        "exutoire_noeud": str(noeud_exutoire),
                        **db_stats
                    })

            info_clean = dict(info_local)
            info_clean.pop("geometry", None)
            info_clean = _json_safe(info_clean)

            results.append({
                "cluster": cluster,
                "exutoire": info_clean,
                "stats": stats,
                "infrastructures": infrastructures,
                "geojson": _json_safe(geojson),
                "troncons": len(edges),
                "ordre_topologique": ordre_topologique
            })
        except Exception as e:
            logger.error(
                    f"[cluster] Erreur traitement bassin {info_local.get('nom', noeud_exutoire)}: {e}",
                exc_info=True
            )
            # Continuer avec les autres bassins
            continue

    # 4. Compter les tronçons connectés (dans un bassin) vs orphelins
    #    troncons_orphelins a été alimenté dans la boucle ci-dessus avec les
    #    edges des bassins trop petits. On y ajoute les orphelins de la partition.
    #    Puis on s'assure de ne pas compter deux fois les tronçons déjà dans un bassin.
    troncons_connectes = set()
    for r in results:
        geo = r.get('geojson', {})
        if geo and 'features' in geo:
            for f in geo['features']:
                ft = f.get('properties', {}).get('type')
                if ft == 'conduite' or (isinstance(ft, str) and ft.startswith('connecte_')):
                    u_str = f['properties'].get('u')
                    v_str = f['properties'].get('v')
                    if u_str and v_str:
                        troncons_connectes.add((u_str, v_str))

    # Compter le total d'arêtes dans le graphe
    total_edges = G.number_of_edges()
    nb_connectes = len(troncons_connectes)
    nb_orphelins = total_edges - nb_connectes

    return {
        "status": "success",
        "exutoires_physiques": len(exutoires_physiques),
        "cycles_neutralises": len(cycles_casses),
        "bassins_attendus": len(exutoires_physiques),
        "bassins_non_resolus": len(bassins_sans_reseau),
        "exutoires_sans_reseau": bassins_sans_reseau,
        "composantes_orphelines": len(composantes_orphelines),
        "troncons_orphelins": nb_orphelins,
        "troncons_connectes": nb_connectes,
        "clusters_crees": len(results),
        "stations_diagnostics": stations_diagnostics,
        "resultats": results
    }


@router.post("/{cluster_id}/recalculate")
def recalculate_cluster(cluster_id: int, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """Recalcule un cluster spécifique."""
    cluster = crud.get_cluster(db, cluster_id)
    if not cluster:
        raise HTTPException(status_code=404, detail="Cluster non trouvé")
    raise HTTPException(status_code=501, detail="À implémenter")


@router.get("/{cluster_id}/geojson")
def export_cluster_geojson(cluster_id: int, db: Session = Depends(get_db)):
    """Export d'un cluster au format GeoJSON avec ordre topologique."""
    from src.domain.detecteur_clusters import tracer_cluster_depuis_exutoire, construire_geojson_cluster
    from src.domain.graphe_reseau import calculer_ordre_topologique
    
    cluster = crud.get_cluster(db, cluster_id)
    if not cluster:
        raise HTTPException(status_code=404, detail="Cluster non trouvé")
    
    G = _get_graph()
    target_node = cluster.exutoire_noeud
    node_tuple = target_node
    if not node_tuple:
        raise HTTPException(status_code=400, detail="Exutoire du bassin absent")
    
    edges = tracer_cluster_depuis_exutoire(G, node_tuple)['edges']
    
    geojson = construire_geojson_cluster(G, edges, {})
    ordre_topologique = calculer_ordre_topologique(G, edges)
    
    return {
        "geojson": geojson,
        "ordre_topologique": ordre_topologique,
        "cluster_id": cluster_id,
        "nb_conduites": len(edges)
    }
