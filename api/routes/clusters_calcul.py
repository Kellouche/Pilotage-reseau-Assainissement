# -*- coding: utf-8 -*-
"""
================================================================================
Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
Auteur : Dr Abdelhakim KELLOUCHE
Date de création : 2026-11-27
Date de modification : 2026-11-27
Objet : Moteur de calcul des clusters/bassins : detection, persistance, taches de fond (extrait de routes/clusters.py)
================================================================================
"""

import json
import logging
from pathlib import Path
from typing import Optional

import networkx as nx
from fastapi import HTTPException
from sqlalchemy.orm import Session

from api import crud
from api.database import SessionLocal
from api.models import Project
from api.routes.clusters import (
    _CLUSTERS_CACHE,
    _CLUSTERS_LOCK,
    _GRAPH_CACHES,
    _get_clusters_disk_cache_path,
    _get_graph,
    _json_safe,
    _log_cluster,
    _set_graph_status,
)

logger = logging.getLogger(__name__)


def _calculate_clusters_sync(db: Session, persist: bool = True, chemin_gpkg: Optional[str] = None):
    """Wrapper to run the heavy calculation synchronously using provided DB session."""
    try:
        return _calculate_clusters(db, persist=persist, chemin_gpkg=chemin_gpkg)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur calcul clusters: {str(e)}")


def _prechauffer_ouvrages_proches(chemin_gpkg: str, cluster_id: str) -> None:
    """Réchauffe le cache de detecter_ouvrages_orphelins_proches (threadpool FastAPI)."""
    try:
        from src.domain.ouvrages_orphelins import detecter_ouvrages_orphelins_proches
        detecter_ouvrages_orphelins_proches(chemin_gpkg, cluster_id, rayon_max_m=45.0)
    except Exception as e:
        _log_cluster(f"[clusters] Prechauffe ouvrages-proches ignore: {e}", flush=True)


def _warm_graph_cache(chemin_gpkg: Optional[str] = None):
    """Warm the graph cache in background."""
    global _GRAPH_CACHES
    try:
        from src.domain.graphe_reseau import construire_graphe
        cache_key = str(chemin_gpkg) if chemin_gpkg else "default"
        _log_cluster(f"[clusters] Warming graph cache for {cache_key}...", flush=True)
        G = construire_graphe(chemin_gpkg)
        _GRAPH_CACHES[cache_key] = G
        _set_graph_status("ready")
        _log_cluster(f"[clusters] Graph cache warmed for {cache_key}.", flush=True)
    except Exception as e:
        _set_graph_status("error")
        _log_cluster(f"[clusters] ERROR warming graph cache: {e}", flush=True)


def _calculate_clusters_background():
    """Background worker that creates its own DB session and runs the calculation."""
    db = SessionLocal()
    try:
        from api.services.simulation_service import resoudre_gpkg_effectif_pour_projet
        proj = db.query(Project).filter(Project.is_archived.is_(False)).first()
        _chemin = resoudre_gpkg_effectif_pour_projet(db, proj)
        chemin_gpkg = str(_chemin) if _chemin is not None else None
        result = _calculate_clusters(db, persist=True, chemin_gpkg=chemin_gpkg)
        _log_cluster("[cluster][background] Recalculation completed", flush=True)
        # Optionally log result summary
        _log_cluster(f"[cluster][background] {result.get('clusters_crees', 0)} clusters créés", flush=True)
    except Exception as e:
        _log_cluster(f"[cluster][background] Erreur: {e}", flush=True)
    finally:
        db.close()


def _purger_clusters_du_projet(db: Session, network_id_cible: Optional[str]) -> None:
    """
    Supprime les clusters rattachés au projet `network_id_cible` et détache
    les éléments (regards, conduites, rejets) du même périmètre.

    Étape 3A — isolation multi-projets :
    - les clusters des AUTRES projets (network_id différent) sont préservés ;
    - les clusters legacy sans network_id sont traités comme non attribués :
      purgés lors d'un recalcul de projet (comportement historique), mais
      jamais ceux explicitement rattachés à un autre projet ;
    - sans projet résolu, seuls les clusters sans network_id sont purgés.
    """
    purge_query = db.query(crud.Cluster)
    if network_id_cible:
        purge_query = purge_query.filter(
            (crud.Cluster.network_id == network_id_cible) |
            (crud.Cluster.network_id.is_(None))
        )
    else:
        purge_query = purge_query.filter(crud.Cluster.network_id.is_(None))
    purge_query.delete(synchronize_session=False)

    for modele in (crud.Regard, crud.Canalisation, crud.Rejet):
        q = db.query(modele)
        if network_id_cible:
            q = q.filter(modele.network_id == network_id_cible)
        q.update({modele.cluster_id: None}, synchronize_session=False)
    db.commit()


def _calculate_clusters(db: Session, persist: bool = True, chemin_gpkg: Optional[str] = None):
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

    global _CLUSTERS_CACHE, _CLUSTERS_LOCK
    norm_key = str(Path(chemin_gpkg).resolve()).replace("\\", "/") if chemin_gpkg else "default"
    cache_key = str(chemin_gpkg) if chemin_gpkg else "default"

    if not persist:
        if cache_key in _CLUSTERS_CACHE:
            _log_cluster(f"[clusters] Cache mémoire hit pour {cache_key}", flush=True)
            return _CLUSTERS_CACHE[cache_key]
        if norm_key in _CLUSTERS_CACHE:
            _log_cluster(f"[clusters] Cache mémoire hit pour {norm_key}", flush=True)
            return _CLUSTERS_CACHE[norm_key]

        disk_path = _get_clusters_disk_cache_path(chemin_gpkg)
        if disk_path and disk_path.exists():
            try:
                _log_cluster(f"[clusters] Cache disque hit pour {cache_key}", flush=True)
                with open(disk_path, "r", encoding="utf-8") as f:
                    cached_res = json.load(f)
                if cached_res.get("clusters_crees") and cached_res.get("resultats"):
                    _CLUSTERS_CACHE[cache_key] = cached_res
                    _CLUSTERS_CACHE[norm_key] = cached_res
                    return cached_res
            except Exception as e:
                _log_cluster(f"[clusters] Erreur lecture cache disque: {e}", flush=True)

        # Protection concurrence : un seul thread exécute le partitionnement à la fois
        with _CLUSTERS_LOCK:
            # Double-check après acquisition du verrou
            if cache_key in _CLUSTERS_CACHE:
                return _CLUSTERS_CACHE[cache_key]
            if norm_key in _CLUSTERS_CACHE:
                return _CLUSTERS_CACHE[norm_key]
            if disk_path and disk_path.exists():
                try:
                    with open(disk_path, "r", encoding="utf-8") as f:
                        cached_res = json.load(f)
                    if cached_res.get("clusters_crees") and cached_res.get("resultats"):
                        _CLUSTERS_CACHE[cache_key] = cached_res
                        _CLUSTERS_CACHE[norm_key] = cached_res
                        return cached_res
                except Exception as e:
                    _log_cluster(f"[clusters] Erreur lecture cache disque sous verrou: {e}", flush=True)

            # Si le cache n'a pas les bassins, lancer le partitionnement topologique
            if chemin_gpkg and Path(chemin_gpkg).exists():
                try:
                    from src.domain.generateur_bassins_79 import partitionner_79_bassins_versants
                    partitionner_79_bassins_versants(chemin_gpkg, sauvegarder_gpkg=False)
                    if disk_path and disk_path.exists():
                        with open(disk_path, "r", encoding="utf-8") as f:
                            cached_res = json.load(f)
                        _CLUSTERS_CACHE[cache_key] = cached_res
                        _CLUSTERS_CACHE[norm_key] = cached_res
                        return cached_res
                except Exception as e:
                    _log_cluster(f"[clusters] Erreur partitionnement: {e}", flush=True)

    # Récupérer le graphe (depuis le cache ou construit pour ce gpkg)
    G = _get_graph(chemin_gpkg)

    if G is None or G.number_of_nodes() == 0:
        return {
            "statut": "ok",
            "message": "Réseau vide",
            "clusters_crees": 0,
            "bassins": [],
            "resultats": [],
            "stations_diagnostics": []
        }

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
        _log_cluster(f"[cluster] {len(cycles_casses)} cycle(s) neutralise(s) avant tracage", flush=True)

    # Résolution du projet porteur du GeoPackage (portée d'unicité des clusters)
    # 3C.0 : le chemin peut être un snapshot matérialisé — on compare le chemin
    # EFFECTIF résolu de chaque projet (version courante), pas source_gpkg_key.
    projet_cible = None
    if chemin_gpkg:
        try:
            from api.services.simulation_service import resoudre_gpkg_effectif_pour_projet
            gpkg_resolu = str(Path(chemin_gpkg).resolve())
            for cand in db.query(Project).filter(Project.is_archived.is_(False)).all():
                eff = resoudre_gpkg_effectif_pour_projet(db, cand)
                if eff is not None and str(Path(eff).resolve()) == gpkg_resolu:
                    projet_cible = cand
                    break
                if cand.source_gpkg_key and Path(cand.source_gpkg_key).exists() \
                        and str(Path(cand.source_gpkg_key).resolve()) == gpkg_resolu:
                    projet_cible = cand
                    break
        except Exception as e_proj:
            _log_cluster(f"[cluster] Résolution projet impossible: {e_proj}", flush=True)
    network_id_cible = projet_cible.id if projet_cible else None
    org_id_cible = projet_cible.org_id if projet_cible else None

    if persist:
        # Nettoyer les anciens clusters du PROJET UNIQUEMENT (étape 3A :
        # plus de purge globale — les clusters des autres projets sont préservés)
        try:
            _purger_clusters_du_projet(db, network_id_cible)
            _log_cluster(f"[cluster] Anciens clusters du projet {network_id_cible or 'legacy/NULL'} purgés.", flush=True)
        except Exception as e:
            db.rollback()
            _log_cluster(f"[cluster] Erreur lors de la purge des anciens clusters: {e}", flush=True)

    # 1. Exutoires physiques + nœuds morts (exutoires implicites)
    #    Un nœud sans sortie est une extrémité hydraulique légitime : les
    #    fragments qu'il domine deviennent des bassins 'exutoire_implicite'
    #    (filtrés par min_edges, tracés et soumis à revue) au lieu d'être
    #    exclus comme orphelins alors qu'ils sont connectés.
    _log_cluster("[cluster] Identification des exutoires physiques et implicites…", flush=True)
    exutoires_physiques = trouver_exutoires_physiques(G, inclure_exutoires_implicites=True)

    if not exutoires_physiques:
        return {
            "statut": "ok",
            "message": "Aucun exutoire ou extrémité identifié.",
            "clusters_crees": 0,
            "bassins": [],
            "resultats": [],
            "stations_diagnostics": []
        }

    # 2. Composantes orphelines (pour information)
    _log_cluster("[cluster] Détection des tronçons orphelins…", flush=True)
    composantes_orphelines = detecter_composantes_orphelines(G)

    _log_cluster(f"[cluster] {len(exutoires_physiques)} exutoires, {len(composantes_orphelines)} composantes", flush=True)
    _log_cluster(
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
        "step":               "#22c55e",
        "station":            "#f97316",
        "rejet":              "#ef4444",
        "deversoir_orage":    "#06b6d4",
        "trop_plein":         "#a855f7",
        "bassin_retention":   "#10b981",
        "ouvrage_regulation": "#6366f1",
        "ouvrage_reception":  "#f59e0b",
        "ouvrage_special":    "#ec4899",
        "ouvrage":            "#9b59b6",
        "exutoire_implicite": "#64748b"
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
            # Déterminer l'adresse réelle du bassin depuis les données de la zone drainée
            nom_bassin = determiner_nom_bassin(edges, G, exutoire_info=info_local, exutoire_node=noeud_exutoire)
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

            t_det = info_local.get("type_detaille", info_local.get("type"))
            couleur = info_local.get("couleur_type") or color_map.get(t_det) or color_map.get(info_local.get("type"), "#4a90e2")
            classification = {
                edge: {"type": f"connecte_{t_det}", "couleur": couleur}
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
                # Chercher par référence métier stable (étape 3A), puis par nom
                # dans le périmètre du projet uniquement — jamais de correspondance globale
                ref_bassin = f"exutoire:{noeud_exutoire}"
                existing = None
                if network_id_cible:
                    existing = db.query(crud.Cluster).filter(
                        crud.Cluster.network_id == network_id_cible,
                        (crud.Cluster.bassin_ref == ref_bassin) |
                        (crud.Cluster.exutoire_noeud == str(noeud_exutoire))
                    ).first()
                if not existing:
                    existing = db.query(crud.Cluster).filter(
                        crud.Cluster.network_id == network_id_cible,
                        (crud.Cluster.nom == nom_exutoire) |
                        (crud.Cluster.nom == nom_bassin)
                    ).first() if network_id_cible else None

                if existing:
                    # Mettre à jour le nom et renseigner la référence métier si absente
                    update_data = {**db_stats}
                    if existing.nom != nom_bassin:
                        update_data["nom"] = nom_bassin
                    if not existing.bassin_ref:
                        update_data["bassin_ref"] = ref_bassin
                    cluster = crud.update_cluster_stats(db, existing.id, update_data)
                else:
                    cluster = crud.create_cluster(db, {
                        "nom": nom_bassin,
                        "exutoire_noeud": str(noeud_exutoire),
                        "bassin_ref": ref_bassin,
                        "network_id": network_id_cible,
                        "org_id": org_id_cible,
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

    # 3.bis. Intégrer les bassins manuels
    try:
        from src.infrastructure.persistance_manuelle import charger_bassins_manuels
        from src.domain.detecteur_clusters import calculer_bassin_polygon, construire_geojson_cluster
        manual_bassins = charger_bassins_manuels(org_id=ctx.org_id)
        for mb in manual_bassins:
            conduit_ids = set(str(x) for x in mb.get("conduits", []))
            edges_manual = set()
            for u, v, attrs in G.edges(data=True):
                cid = str(attrs.get("conduit_id", ""))
                fid = str(attrs.get("fid", ""))
                if cid in conduit_ids or fid in conduit_ids:
                    edges_manual.add((u, v))

            if edges_manual:
                hull = calculer_bassin_polygon(edges_manual, G=G)
                info_ex = mb.get("exutoire") or {"nom": mb.get("nom", "Manuel"), "type": "manuel"}
                noeud_ex = None
                if mb.get("exutoire") and isinstance(mb["exutoire"], dict) and mb["exutoire"].get("latlng"):
                    ll = mb["exutoire"]["latlng"]
                    if isinstance(ll, dict):
                        noeud_ex = (ll.get("lng"), ll.get("lat"))

                mb_geojson = construire_geojson_cluster(
                    G, edges_manual,
                    bassin_hull=hull,
                    cluster_id=f"M_{mb.get('id', 1)}",
                    exutoire_node=noeud_ex,
                    exutoire_info=info_ex
                )

                if mb_geojson and "features" in mb_geojson:
                    for feat in mb_geojson["features"]:
                        if feat.get("properties", {}).get("type") == "bassin_urbain":
                            feat["properties"]["nom"] = f"{mb.get('nom', 'Bassin Manuel')} [MANUEL]"
                            feat["properties"]["exutoire_type"] = info_ex.get("type", "manuel")
                            # Identité contextuelle des bassins manuels (jamais persistée :
                            # les identifiants M_x sont instables — voir étape 3A)
                            feat["properties"]["bassin_ref"] = f"manuel:M_{mb.get('id', 1)}"

                results.append({
                    "cluster": None,
                    "exutoire": info_ex,
                    "stats": {"troncons": len(edges_manual), "longueur_totale_m": 0.0},
                    "infrastructures": {"conduites": len(edges_manual), "regards": 0},
                    "geojson": _json_safe(mb_geojson),
                    "troncons": len(edges_manual),
                    "ordre_topologique": []
                })
    except Exception as e:
        logger.error(f"[cluster] Erreur intégration bassins manuels: {e}", exc_info=True)

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

    final_res = {
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

    if not persist:
        _CLUSTERS_CACHE[cache_key] = final_res
        _CLUSTERS_CACHE[norm_key] = final_res
        disk_path = _get_clusters_disk_cache_path(chemin_gpkg)
        if disk_path:
            try:
                with open(disk_path, "w", encoding="utf-8") as f:
                    json.dump(final_res, f, ensure_ascii=False)
                _log_cluster(f"[clusters] Cache disque sauvegardé: {disk_path}", flush=True)
            except Exception as e:
                _log_cluster(f"[clusters] Erreur écriture cache disque: {e}", flush=True)

    return final_res
