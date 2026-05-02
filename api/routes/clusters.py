from functools import lru_cache
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from typing import List, Optional, Dict

from api.database import get_db
from api import schemas, crud

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


@router.get("/{cluster_id}", response_model=schemas.ClusterResponse)
def get_cluster(cluster_id: int, db: Session = Depends(get_db)):
    """Détail d'un cluster."""
    cluster = crud.get_cluster(db, cluster_id)
    if not cluster:
        raise HTTPException(status_code=404, detail="Cluster non trouvé")
    return cluster


@router.post("/recalculate-all")
def recalculate_all_clusters(background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """Reconstruit tous les clusters en bassins exclusifs (sans chevauchement).

    Algorithme BFS multi-sources :
    - Chaque conduite appartient à UN SEUL bassin (le plus proche exutoire en aval)
    - Priorité : STEP > station > ouvrage > rejet
    """
    try:
        from src.domain.graphe_reseau import construire_graphe
        from src.domain.detecteur_clusters import (
            trouver_exutoires_physiques,
            partitionner_bassins_exclusifs,
            construire_geojson_cluster,
            calculer_statistiques,
            detecter_composantes_orphelines,
            compter_infrastructures
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

        # 3. ── Partition BFS multi-sources : bassins exclusifs ────────────
        print("[cluster] Partition BFS multi-sources…", flush=True)
        bassins = partitionner_bassins_exclusifs(G, exutoires_physiques)
        # ──────────────────────────────────────────────────────────────────

        color_map = {
            "step":    "#e74c3c",   # Rouge - exutoires terminaux
            "rejet":   "#e67e22",   # Orange
            "station": "#3498db",   # Bleu
            "ouvrage": "#9b59b6"    # Violet
        }

        results = []
        tous_les_troncons_connexes = set()

        for noeud_exutoire, edges in bassins.items():
            if not edges:
                continue

            info = exutoires_physiques[noeud_exutoire]
            tous_les_troncons_connexes.update(edges)

            stats = calculer_statistiques(G, edges)
            infrastructures = compter_infrastructures(edges)

            couleur = color_map.get(info["type"], "#4a90e2")
            classification = {
                edge: {"type": f"connecte_{info['type']}", "couleur": couleur}
                for edge in edges
            }
            geojson = construire_geojson_cluster(G, edges, classification)

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

            nom_exutoire = info["nom"]
            existing = db.query(crud.Cluster).filter(crud.Cluster.nom == nom_exutoire).first()

            if existing:
                cluster = crud.update_cluster_stats(db, existing.id, db_stats)
            else:
                cluster = crud.create_cluster(db, {
                    "nom": nom_exutoire,
                    "exutoire_noeud": str(noeud_exutoire),
                    **db_stats
                })

            results.append({
                "cluster": cluster,
                "exutoire": info,
                "stats": stats,
                "infrastructures": infrastructures,
                "geojson": geojson,
                "troncons": len(edges)
            })

        # 4. Identifier et classifier les tronçons orphelins
        troncons_orphelins = set()
        for comp_noeuds, comp_edges, type_issue in composantes_orphelines:
            troncons_orphelins.update(comp_edges)
        
        # Enlever les tronçons déjà connectés
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
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur calcul clusters: {str(e)}")


@router.post("/{cluster_id}/recalculate")
def recalculate_cluster(cluster_id: int, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """Recalcule un cluster spécifique."""
    cluster = crud.get_cluster(db, cluster_id)
    if not cluster:
        raise HTTPException(status_code=404, detail="Cluster non trouvé")
    raise HTTPException(status_code=501, detail="À implémenter")


@router.get("/{cluster_id}/geojson")
def export_cluster_geojson(cluster_id: int, db: Session = Depends(get_db)):
    """Export d'un cluster au format GeoJSON."""
    import ast
    from src.domain.detecteur_clusters import tracer_cluster_depuis_exutoire, construire_geojson_cluster
    
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
    
    return construire_geojson_cluster(G, edges, {})