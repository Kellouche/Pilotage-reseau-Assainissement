# -*- coding: utf-8 -*-
"""
================================================================================
Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
Auteur : Dr Abdelhakim KELLOUCHE
Date de création : 2026-11-27
Date de modification : 2026-11-27
Objet : Endpoints de consultation et correction d'attributs de conduites (GPKG RW, noeuds candidats, contexte reseau) — extraits de routes/qualite.py.
================================================================================
"""

import json
import re
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from api.core.security import require_role, TenantContext
from api.database import get_db
from api.services.qualite_cache_service import (
    _cache_topologie,
    get_active_project_and_gpkg,
    reinitialiser_cache_qualite,
)

router = APIRouter(prefix="/qualite", tags=["Qualité réseau — Conduites"])


def _connecter_gpkg_rw(gpkg_file: Path) -> sqlite3.Connection:
    """Ouvre une connexion SQLite RW avec fonctions spatiales factices pour contourner les triggers GPKG sans SpatiaLite."""
    conn = sqlite3.connect(gpkg_file)
    conn.create_function("ST_IsEmpty", 1, lambda g: 0)
    conn.create_function("ST_MinX", 1, lambda g: 0.0)
    conn.create_function("ST_MaxX", 1, lambda g: 0.0)
    conn.create_function("ST_MinY", 1, lambda g: 0.0)
    conn.create_function("ST_MaxY", 1, lambda g: 0.0)
    return conn


def _resoudre_table_canalisations_gpkg(conn: sqlite3.Connection) -> Optional[str]:
    """Trouve le nom exact de la couche de canalisations dans le GPKG."""
    cur = conn.cursor()
    cur.execute("SELECT table_name FROM gpkg_contents WHERE data_type='features'")
    tables = [r[0] for r in cur.fetchall()]
    mots_cles = ["canalisat", "conduit", "pipe", "troncon"]
    for t in tables:
        t_low = t.lower()
        if any(m in t_low for m in mots_cles) and not any(e in t_low for e in ["desaffect", "désaffect"]):
            return t
    return tables[0] if tables else None


def _normaliser_nom_colonne(col_name: str) -> str:
    """Normalise un nom de colonne pour comparaison robuste."""
    c = col_name.lower().replace("è", "e").replace("é", "e").replace("-", "_").replace(" ", "_")
    if c == "longeur":
        return "longueur"
    return c


def _trouver_rowid_conduite_gpkg(cur: sqlite3.Cursor, table_name: str, id_conduite: str, col_id: str) -> Optional[int]:
    """Recherche le rowid d'une conduite de façon infaillible (aligné sur l'index C_idx d'analyse_qualite_gpkg)."""
    # 1. Correspondance par colonne identifiant si renseignée
    try:
        cur.execute(f'SELECT rowid FROM "{table_name}" WHERE "{col_id}" = ?', [str(id_conduite)])
        r = cur.fetchone()
        if r and r[0]:
            return r[0]
    except sqlite3.Error:
        pass

    # 2. Format canonique C_XX généré par le moteur d'analyse qualité
    import re
    m = re.match(r'^c_?(\d+)$', str(id_conduite), re.IGNORECASE)
    if m:
        idx = int(m.group(1)) - 1
        if idx >= 0:
            cur.execute(f'SELECT rowid FROM "{table_name}" LIMIT 1 OFFSET ?', [idx])
            r = cur.fetchone()
            if r and r[0]:
                return r[0]

    # 3. Entier brut (ex: "1" ou "37")
    try:
        idx = int(id_conduite) - 1
        if idx >= 0:
            cur.execute(f'SELECT rowid FROM "{table_name}" LIMIT 1 OFFSET ?', [idx])
            r = cur.fetchone()
            if r and r[0]:
                return r[0]
    except ValueError:
        pass

    # 4. Fallback fid_1 ou fid
    for fid_col in ["fid_1", "fid"]:
        try:
            cur.execute(f'SELECT rowid FROM "{table_name}" WHERE "{fid_col}" = ?', [id_conduite])
            r = cur.fetchone()
            if r and r[0]:
                return r[0]
        except sqlite3.Error:
            pass

    return None


@router.patch("/conduites/{id_conduite}", response_model=Dict[str, Any])
async def modifier_attributs_conduite(
    id_conduite: str,
    payload: Dict[str, Any],
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(require_role("engineer"))
):
    """
    Modifie les attributs d'une conduite (diamètre, matériau, longueur, etc.)
    directement dans le GeoPackage du réseau actif et dans la base si applicable.
    Marque automatiquement l'anomalie associée comme corrigée et purge le cache.
    """
    if not payload:
        raise HTTPException(status_code=400, detail="Aucune donnée à modifier fournie.")

    gpkg_path, nom_projet = get_active_project_and_gpkg(db, ctx)
    if not gpkg_path or not Path(gpkg_path).exists():
        raise HTTPException(status_code=404, detail="Fichier GeoPackage du réseau introuvable.")

    gpkg_file = Path(gpkg_path)
    champs_modifies = []

    # 1. Mise à jour dans le GeoPackage SQLite
    try:
        conn = _connecter_gpkg_rw(gpkg_file)
        table_name = _resoudre_table_canalisations_gpkg(conn)
        if not table_name:
            conn.close()
            raise HTTPException(status_code=500, detail="Couche canalisations introuvable dans le GeoPackage.")

        cur = conn.cursor()
        pragma_cols = cur.execute(f'PRAGMA table_info("{table_name}")').fetchall()
        mapping_cols = {_normaliser_nom_colonne(r[1]): r[1] for r in pragma_cols}
        noms_bruts = [r[1] for r in pragma_cols]

        col_id = "id" if "id" in mapping_cols else ("ID" if "ID" in noms_bruts else "fid_1")

        rowid = _trouver_rowid_conduite_gpkg(cur, table_name, id_conduite, col_id)
        if rowid is None:
            conn.close()
            raise HTTPException(status_code=404, detail=f"Conduite {id_conduite} introuvable dans le GeoPackage.")

        set_clauses = []
        valeurs = []
        for k, v in payload.items():
            if k in ("cle_anomalie", "commentaire"):
                continue
            k_norm = _normaliser_nom_colonne(k)
            if k_norm in mapping_cols:
                reel = mapping_cols[k_norm]
                set_clauses.append(f'"{reel}" = ?')
                if k_norm in ("diametre", "longueur", "hauteur", "rugosite", "prof_fe_am", "prof_fe_av"):
                    try:
                        v = float(v)
                    except (ValueError, TypeError):
                        pass
                valeurs.append(v)
                champs_modifies.append(f"{reel} = {v}")

        if not set_clauses:
            conn.close()
            raise HTTPException(status_code=400, detail="Aucun attribut reconnu correspondant aux colonnes de la couche.")

        sql = f'UPDATE "{table_name}" SET {", ".join(set_clauses)} WHERE rowid = ?'
        cur.execute(sql, valeurs + [rowid])
        lignes_affectees = cur.rowcount
        conn.commit()
        conn.close()

    except sqlite3.Error as e:
        raise HTTPException(status_code=500, detail=f"Erreur SQLite lors de la modification : {e}")

    # 2. Mise à jour de la table Canalisation en base si elle existe
    try:
        from api.crud import update_canalisation
        update_canalisation(db, id_conduite, payload, user_id=str(ctx.actor.id), org_id=ctx.org_id)
    except Exception:
        pass

    # 3. Traçabilité du statut qualité (marquer comme corrigé)
    cle_anomalie = payload.get("cle_anomalie")
    if cle_anomalie:
        try:
            await definir_statut_anomalie_par_cle(
                cle_anomalie=cle_anomalie,
                request={"statut": "corrige", "commentaire": payload.get("commentaire") or f"Attributs mis à jour ({', '.join(champs_modifies)})"},
                db=db,
                ctx=ctx
            )
        except Exception as e:
            print(f"[QUALITE] Erreur mise à jour statut anomalie : {e}")

    # 4. Invalidation du cache pour actualisation des calculs
    reinitialiser_cache_qualite(gpkg_file)

    return {
        "status": "success",
        "message": f"Conduite {id_conduite} modifiée avec succès ({lignes_affectees} ligne affectée).",
        "id_conduite": id_conduite,
        "champs_modifies": champs_modifies,
        "lignes_affectees": lignes_affectees
    }


@router.post("/conduites/{id_conduite}/inverser-sens", response_model=Dict[str, Any])
async def inverser_sens_conduite(
    id_conduite: str,
    request: Optional[Dict[str, Any]] = None,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(require_role("engineer"))
):
    """
    Inverse le sens d'écoulement de la conduite en permutant ID_AMONT et ID_AVAL
    dans le GeoPackage du réseau actif.
    Marque l'anomalie associée comme corrigée et purge le cache.
    """
    gpkg_path, nom_projet = get_active_project_and_gpkg(db, ctx)
    if not gpkg_path or not Path(gpkg_path).exists():
        raise HTTPException(status_code=404, detail="Fichier GeoPackage du réseau introuvable.")

    gpkg_file = Path(gpkg_path)

    try:
        conn = _connecter_gpkg_rw(gpkg_file)
        table_name = _resoudre_table_canalisations_gpkg(conn)
        if not table_name:
            conn.close()
            raise HTTPException(status_code=500, detail="Couche canalisations introuvable dans le GeoPackage.")

        cur = conn.cursor()
        pragma_cols = cur.execute(f'PRAGMA table_info("{table_name}")').fetchall()
        noms_bruts = [r[1] for r in pragma_cols]
        mapping_cols = {_normaliser_nom_colonne(r[1]): r[1] for r in pragma_cols}

        col_amont = mapping_cols.get("id_amont")
        col_aval = mapping_cols.get("id_aval")
        if not col_amont or not col_aval:
            conn.close()
            raise HTTPException(status_code=500, detail="Colonnes amont/aval introuvables dans la couche.")

        col_id = "id" if "id" in mapping_cols else ("ID" if "ID" in noms_bruts else "fid_1")

        rowid = _trouver_rowid_conduite_gpkg(cur, table_name, id_conduite, col_id)
        if rowid is None:
            conn.close()
            raise HTTPException(status_code=404, detail=f"Conduite {id_conduite} introuvable dans le GeoPackage.")

        # Lire les valeurs actuelles
        cur.execute(f'SELECT "{col_amont}", "{col_aval}" FROM "{table_name}" WHERE rowid = ?', [rowid])
        row = cur.fetchone()
        if not row:
            conn.close()
            raise HTTPException(status_code=404, detail=f"Conduite {id_conduite} introuvable dans le GeoPackage.")

        ancien_amont, ancien_aval = str(row[0]), str(row[1])
        nouvel_amont, nouvel_aval = ancien_aval, ancien_amont

        # Permuter amont et aval
        cur.execute(
            f'UPDATE "{table_name}" SET "{col_amont}" = ?, "{col_aval}" = ? WHERE rowid = ?',
            [nouvel_amont, nouvel_aval, rowid]
        )
        conn.commit()
        conn.close()

    except sqlite3.Error as e:
        raise HTTPException(status_code=500, detail=f"Erreur SQLite lors de l'inversion : {e}")

    # Mettre à jour la base si présente
    try:
        from api.crud import update_canalisation
        update_canalisation(db, id_conduite, {"id_amont": nouvel_amont, "id_aval": nouvel_aval}, user_id=str(ctx.actor.id), org_id=ctx.org_id)
    except Exception:
        pass

    # Traçabilité du statut qualité
    cle_anomalie = (request or {}).get("cle_anomalie")
    if cle_anomalie:
        try:
            commentaire = (request or {}).get("commentaire") or f"Sens d'écoulement inversé : {ancien_amont}➔{ancien_aval} devenu {nouvel_amont}➔{nouvel_aval}"
            await definir_statut_anomalie_par_cle(
                cle_anomalie=cle_anomalie,
                request={"statut": "corrige", "commentaire": commentaire},
                db=db,
                ctx=ctx
            )
        except Exception as e:
            print(f"[QUALITE] Erreur mise à jour statut anomalie : {e}")

    # Invalidation du cache qualité
    reinitialiser_cache_qualite(gpkg_file)

    return {
        "status": "success",
        "message": f"Sens d'écoulement inversé avec succès pour {id_conduite} ({ancien_amont}➔{ancien_aval} inversé en {nouvel_amont}➔{nouvel_aval}).",
        "id_conduite": id_conduite,
        "ancien_amont": ancien_amont,
        "ancien_aval": ancien_aval,
        "nouvel_amont": nouvel_amont,
        "nouvel_aval": nouvel_aval
    }


def _obtenir_topologie_cachee(gpkg_file: Path):
    """Charge ou réutilise le résolveur topologique et les couches du GPKG.

    Retourne (resolveur, pipes, regards, rejets)."""
    global _cache_topologie
    import geopandas as gpd
    from src.analyse_qualite_gpkg import _construire_resolveur, _vers_metres_gdf

    try:
        mtime = gpkg_file.stat().st_mtime
    except Exception:
        mtime = 0

    if (_cache_topologie["resolveur"] is not None
            and _cache_topologie["gpkg_path"] == str(gpkg_file)
            and _cache_topologie["mtime"] == mtime):
        return (_cache_topologie["resolveur"], _cache_topologie["pipes"],
                _cache_topologie["regards"], _cache_topologie["rejets"])

    try:
        layers = gpd.list_layers(str(gpkg_file))["name"].tolist()
        pipe_layer = next((l for l in layers if any(k in l.lower() for k in ["canalisat", "conduit", "pipe", "troncon"]) and "désaffect" not in l.lower() and "desaffect" not in l.lower()), None)
        regard_layer = next((l for l in layers if "regard" in l.lower()), None)
        rejet_layer = next((l for l in layers if any(k in l.lower() for k in ["rejet", "exutoire", "outfall"])), None)

        pipes = gpd.read_file(str(gpkg_file), layer=pipe_layer) if pipe_layer else None
        regards = gpd.read_file(str(gpkg_file), layer=regard_layer) if regard_layer else gpd.GeoDataFrame()
        rejets = gpd.read_file(str(gpkg_file), layer=rejet_layer) if rejet_layer else gpd.GeoDataFrame()

        resolveur = _construire_resolveur(regards, rejets, gpkg_file, layers)

        _cache_topologie["gpkg_path"] = str(gpkg_file)
        _cache_topologie["mtime"] = mtime
        _cache_topologie["resolveur"] = resolveur
        _cache_topologie["pipes"] = pipes
        _cache_topologie["regards"] = regards
        _cache_topologie["rejets"] = rejets
        _cache_topologie["pipes_m"] = _vers_metres_gdf(pipes) if pipes is not None else None
        _cache_topologie["regards_m"] = _vers_metres_gdf(regards) if regards is not None else None
        _cache_topologie["rejets_m"] = _vers_metres_gdf(rejets) if rejets is not None else None
        return resolveur, pipes, regards, rejets
    except Exception as e:
        print(f"[QUALITE] Erreur chargement topologie : {e}")
        return None, None, None, None


def _obtenir_couches_metriques(gpkg_file: Path):
    """Garantit le cache chaud et retourne les couches en CRS métrique
    (pipes_m, regards_m, rejets_m) pour les calculs de distance."""
    _obtenir_topologie_cachee(gpkg_file)
    return (_cache_topologie["pipes_m"], _cache_topologie["regards_m"],
            _cache_topologie["rejets_m"])


def _trouver_conduite_par_id(pipes, id_conduite):
    """Retrouve la ligne GeoDataFrame correspondant à un identifiant de
    conduite. Retourne (row, position_entiere) — la position alimente le
    schéma d'identifiants C_{pos+1} utilisé par les anomalies — ou
    (None, -1)."""
    import re
    pos = None
    m = re.match(r'^c_?(\d+)$', str(id_conduite), re.IGNORECASE)
    if m:
        pos = int(m.group(1)) - 1
    else:
        try:
            pos = int(id_conduite) - 1
        except ValueError:
            pass

    if pos is not None and 0 <= pos < len(pipes):
        return pipes.iloc[pos], pos
    for i, (_, row) in enumerate(pipes.iterrows()):
        if str(row.get("id")) == str(id_conduite) or str(row.get("fid_1")) == str(id_conduite) or str(row.get("fid")) == str(id_conduite):
            return row, i
    return None, -1


@router.get("/conduites/{id_conduite}/noeuds-candidats", response_model=Dict[str, Any])
async def obtenir_noeuds_candidats_conduite(
    id_conduite: str,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(require_role("viewer"))
):
    """
    Détecte par analyse spatiale les nœuds les plus proches (Regards, Rejets)
    des extrémités amont et aval d'une conduite pour assister le raccordement topologique.
    """
    from src.analyse_qualite_gpkg import _points_extremite

    gpkg_path, nom_projet = get_active_project_and_gpkg(db, ctx)
    if not gpkg_path or not Path(gpkg_path).exists():
        raise HTTPException(status_code=404, detail="Fichier GeoPackage du réseau introuvable.")

    gpkg_file = Path(gpkg_path)
    resolv, pipes, _regards, _rejets = _obtenir_topologie_cachee(gpkg_file)
    if resolv is None or pipes is None or pipes.empty:
        raise HTTPException(status_code=500, detail="Impossible d'initialiser le résolveur topologique.")

    p, _pos = _trouver_conduite_par_id(pipes, id_conduite)
    if p is None:
        raise HTTPException(status_code=404, detail=f"Conduite {id_conduite} introuvable.")

    pts = _points_extremite(p.geometry)
    if not pts:
        raise HTTPException(status_code=400, detail="Géométrie de conduite invalide.")

    res_am = resolv.plus_proche(pts[0])
    res_av = resolv.plus_proche(pts[1])

    return {
        "status": "success",
        "id_conduite": id_conduite,
        "amont_actuel": str(p.get("ID_AMONT") or p.get("id_amont") or ""),
        "aval_actuel": str(p.get("ID_AVAL") or p.get("id_aval") or ""),
        "amont_proche": {"id": str(res_am[0]), "distance_m": round(float(res_am[1]), 2)} if res_am else None,
        "aval_proche": {"id": str(res_av[0]), "distance_m": round(float(res_av[1]), 2)} if res_av else None,
        "longueur_m": round(float(p.geometry.length), 1) if p.geometry and p.geometry.length else None
    }


@router.get("/conduites/{id_conduite}/contexte-reseau", response_model=Dict[str, Any])
async def contexte_reseau_local_conduite(
    id_conduite: str,
    rayon_m: float = Query(20.0, ge=5.0, le=200.0,
                           description="Rayon du périmètre local autour du tronçon suspect (m)"),
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(require_role("viewer"))
):
    """
    « Fine réseau » volatile : retourne en GeoJSON (EPSG:4326) le tronçon
    suspect, les conduites et les nœuds (regards/rejets) situés à moins de
    `rayon_m` de sa géométrie, plus le périmètre de recherche. Sert à donner
    le contexte local d'une anomalie (contre-pente, inversion, orphelin…)
    sans charger le réseau complet. Lecture seule.
    """
    from src.analyse_qualite_gpkg import _col_val
    from shapely.geometry import mapping

    gpkg_path, _nom_projet = get_active_project_and_gpkg(db, ctx)
    if not gpkg_path or not Path(gpkg_path).exists():
        raise HTTPException(status_code=404, detail="Fichier GeoPackage du réseau introuvable.")

    gpkg_file = Path(gpkg_path)
    resolv, pipes, _regards, _rejets = _obtenir_topologie_cachee(gpkg_file)
    if resolv is None or pipes is None or pipes.empty:
        raise HTTPException(status_code=500, detail="Impossible d'initialiser le résolveur topologique.")

    p, pos = _trouver_conduite_par_id(pipes, id_conduite)
    if p is None or pos < 0:
        raise HTTPException(status_code=404, detail=f"Conduite {id_conduite} introuvable.")

    pipes_m, regards_m, rejets_m = _obtenir_couches_metriques(gpkg_file)
    if pipes_m is None or pipes_m.empty:
        raise HTTPException(status_code=500, detail="Couches métriques indisponibles.")

    suspect_geom = pipes_m.geometry.iloc[pos] if pos < len(pipes_m) else None
    if suspect_geom is None or suspect_geom.is_empty:
        raise HTTPException(status_code=400, detail="Géométrie de conduite invalide.")

    # Conduites voisines : distance à la géométrie du tronçon suspect ≤ rayon
    distances = pipes_m.geometry.distance(suspect_geom)
    masque_voisines = (distances <= rayon_m)
    masque_voisines.iloc[pos] = False  # le suspect est traité à part

    pos_of_label = {label: i for i, label in enumerate(pipes_m.index)}
    features = []

    def _props_conduite(row_m, position):
        row_src = pipes.loc[row_m.name] if row_m.name in pipes.index else None
        return {
            "type_feature": "conduite",
            "suspect": False,
            "id_conduite": f"C_{position + 1}",
            "id_amont": str(_col_val(row_src, "ID_AMONT", "id_amont", "amont", "AMONT", "NOEUD_AMONT") or ""),
            "id_aval": str(_col_val(row_src, "ID_AVAL", "id_aval", "aval", "AVAL", "NOEUD_AVAL") or ""),
            "longueur_m": round(float(row_m.geometry.length), 1) if row_m.geometry and row_m.geometry.length else None,
        }

    # Le tronçon suspect (mis en évidence côté client)
    row_suspect_m = pipes_m.iloc[pos]
    geom_suspect_wgs = row_suspect_m.geometry
    crs_src = getattr(pipes_m, "crs", None)
    if crs_src is not None and str(crs_src) != "EPSG:4326":
        import geopandas as gpd
        geom_suspect_wgs = gpd.GeoSeries([row_suspect_m.geometry], crs=crs_src).to_crs("EPSG:4326").iloc[0]
    features.append({
        "type": "Feature",
        "geometry": mapping(geom_suspect_wgs),
        "properties": {
            "type_feature": "conduite",
            "suspect": True,
            "id_conduite": f"C_{pos + 1}",
            "id_amont": str(_col_val(p, "ID_AMONT", "id_amont", "amont", "AMONT", "NOEUD_AMONT") or ""),
            "id_aval": str(_col_val(p, "ID_AVAL", "id_aval", "aval", "AVAL", "NOEUD_AVAL") or ""),
            "longueur_m": round(float(suspect_geom.length), 1) if suspect_geom.length else None,
        },
    })

    # Conduites voisines dans le rayon (transformées en WGS84 par lots)
    labels_voisines = list(masque_voisines[masque_voisines].index)
    if labels_voisines:
        voisines_wgs = pipes_m.loc[labels_voisines].to_crs("EPSG:4326")
        for _, row_wgs in voisines_wgs.iterrows():
            geom_w = getattr(row_wgs, "geometry", None)
            if geom_w is None or geom_w.is_empty:
                continue
            features.append({
                "type": "Feature",
                "geometry": mapping(geom_w),
                "properties": _props_conduite(row_wgs, pos_of_label.get(row_wgs.name, -1)),
            })

    # Nœuds (regards puis rejets) dans le rayon — le centroïde d'un Point
    # est le point lui-même ; distance calculée en vectorisé puis sous-ensemble.
    nb_noeuds = 0
    for gdf_m, kind in ((regards_m, "regard"), (rejets_m, "rejet")):
        if gdf_m is None or gdf_m.empty:
            continue
        try:
            dists_noeuds = gdf_m.geometry.centroid.distance(suspect_geom)
            labels_hit = dists_noeuds[dists_noeuds <= rayon_m].index
            if len(labels_hit) == 0:
                continue
            hits_wgs = gdf_m.loc[labels_hit].to_crs("EPSG:4326")
            for _, row_wgs in hits_wgs.iterrows():
                nid = _col_val(row_wgs, "Code", "CODE", "id", "ID", "swmm_id", "SWMM_ID", "NOM", "nom", "INTITULE", "intitule")
                geom = getattr(row_wgs, "geometry", None)
                if geom is None or geom.is_empty:
                    continue
                features.append({
                    "type": "Feature",
                    "geometry": mapping(geom),
                    "properties": {
                        "type_feature": "noeud",
                        "kind_noeud": kind,
                        "id_noeud": str(nid or f"{kind}_{nb_noeuds}"),
                    },
                })
                nb_noeuds += 1
        except Exception:
            continue

    # Périmètre de recherche (zone tampon autour du tronçon suspect)
    try:
        zone = suspect_geom.buffer(rayon_m)
        import geopandas as gpd
        zone_wgs = gpd.GeoSeries([zone], crs=crs_src).to_crs("EPSG:4326").iloc[0]
        features.append({
            "type": "Feature",
            "geometry": mapping(zone_wgs),
            "properties": {"type_feature": "zone_recherche", "rayon_m": rayon_m},
        })
    except Exception:
        pass

    return {
        "type": "FeatureCollection",
        "rayon_m": rayon_m,
        "id_conduite": f"C_{pos + 1}",
        "nb_conduites_voisines": len(labels_voisines),
        "nb_noeuds": nb_noeuds,
        "features": features,
    }
