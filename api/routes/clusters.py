import ast
import logging
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
        determiner_nom_bassin,
        partitionner_bassins_hydrauliques,
        detecter_composantes_orphelines,
    )

    # Reconstruire le graphe
    _reset_graph_cache()
    G = _get_graph()

    # 1. Exutoires physiques
    print("[cluster] Identification des exutoires physiques…", flush=True)
    exutoires_physiques = trouver_exutoires_physiques(G)

    if not exutoires_physiques:
        raise HTTPException(status_code=400, detail="Aucun exutoire physique identifié.")

    # 2. Composantes orphelines (pour information)
    print("[cluster] Détection des tronçons orphelins…", flush=True)
    composantes_orphelines = detecter_composantes_orphelines(G)

    print(f"[cluster] {len(exutoires_physiques)} exutoires, {len(composantes_orphelines)} composantes", flush=True)

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
        "ouvrage": "#9b59b6"
    }

    results = []

    for i, (noeud_exutoire, info) in enumerate(exutoires_physiques.items()):
        edges = bassins_par_exutoire.get(noeud_exutoire, set())
        if not edges:
            continue

        try:
            # Déterminer le nom du bassin depuis les données de la zone drainée
            nom_bassin = determiner_nom_bassin(edges, G, exutoire_info=info)
            nom_exutoire = info["nom"]

            # Calculer les statistiques et le polygone du bassin
            stats = calculer_statistiques(G, edges)
            infrastructures = compter_infrastructures(edges)
            bassin_hull = calculer_bassin_polygon(edges, G=G)

            couleur = color_map.get(info["type"], "#4a90e2")
            classification = {
                edge: {"type": f"connecte_{info['type']}", "couleur": couleur}
                for edge in edges
            }
            geojson = construire_geojson_cluster(
                G,
                edges,
                classification,
                bassin_hull=bassin_hull,
                cluster_id=i + 1,
                exutoire_node=noeud_exutoire if isinstance(noeud_exutoire, tuple) else ast.literal_eval(noeud_exutoire),
                exutoire_info=info,
                nom_bassin=nom_bassin,
            )

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

            results.append({
                "cluster": cluster,
                "exutoire": info,
                "stats": stats,
                "infrastructures": infrastructures,
                "geojson": geojson,
                "troncons": len(edges),
                "ordre_topologique": ordre_topologique
            })
        except Exception as e:
            logger.error(
                f"[cluster] Erreur traitement bassin {info.get('nom', noeud_exutoire)}: {e}",
                exc_info=True
            )
            # Continuer avec les autres bassins
            continue

    # 4. Tronçons orphelins (déjà calculés par partitionner_bassins_hydrauliques)
    #    Compléter avec les composantes orphelines non connectées
    troncons_orphelins = set(troncons_orphelines_set)
    for comp_noeuds, comp_edges, type_issue in composantes_orphelines:
        troncons_orphelins.update(comp_edges)

    # Enlever les tronçons déjà connectés à un bassin
    troncons_orphelins -= tous_les_troncons_connexes

    # Créer un cluster "Orphelins" pour visualisation
    if troncons_orphelins:
        stats_orphelins = calculer_statistiques(G, troncons_orphelins)
        classification_orpheline = {
            edge: {"type": "orphelin", "couleur": "#e67e22"}
            for edge in troncons_orphelins
        }
        geojson_orphelins = construire_geojson_cluster(G, troncons_orphelins, classification_orpheline)

        results.append({
            "cluster": None,
            "exutoire": {"type": "inconnu", "nom": "Réseau orphelin"},
            "stats": stats_orphelins,
            "infrastructures": {"nb_regards": 0, "nb_stations": 0, "nb_ouvrages": 0},
            "geojson": geojson_orphelins,
            "troncons": len(troncons_orphelins),
            "type_issue": type_issue
        })

    return {
        "status": "success",
        "exutoires_physiques": len(exutoires_physiques),
        "composantes_orphelines": len(composantes_orphelines),
        "troncons_orphelins": len(troncons_orphelins),
        "clusters_crees": len([r for r in results if r["cluster"]]),
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
    import ast
    from src.domain.detecteur_clusters import tracer_cluster_depuis_exutoire, construire_geojson_cluster
    from src.domain.graphe_reseau import calculer_ordre_topologique
    
    cluster = crud.get_cluster(db, cluster_id)
    if not cluster:
        raise HTTPException(status_code=404, detail="Cluster non trouvé")
    
    G = _get_graph()
    target_node = cluster.exutoire_noeud
    try:
        node_tuple = ast.literal_eval(target_node) if target_node else None
    except (ValueError, SyntaxError):
        raise HTTPException(status_code=400, detail=f"Format exutoire_noeud invalide: {target_node}")
    
    edges = tracer_cluster_depuis_exutoire(G, node_tuple)
    
    geojson = construire_geojson_cluster(G, edges, {})
    ordre_topologique = calculer_ordre_topologique(G, edges)
    
    return {
        "geojson": geojson,
        "ordre_topologique": ordre_topologique,
        "cluster_id": cluster_id,
        "nb_conduites": len(edges)
    }