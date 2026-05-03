#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Migration des données GeoPackage vers PostgreSQL + PostGIS.
Lit le GeoPackage original et insère dans les tables de la plateforme.
"""

import sys
from pathlib import Path
from typing import Dict, Any

# Ajouter src au path
current_dir = Path(__file__).parent
sys.path.insert(0, str(current_dir))

from src.infrastructure.chargeur_geopackage import charger_donnees
from api.database import engine, SessionLocal, Base
from api.models import Regard, Canalisation, Rejet, Cluster
from sqlalchemy import text
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def check_postgis(engine):
    """Vérifie que PostGIS est activé."""
    with engine.connect() as conn:
        try:
            result = conn.execute(text("SELECT PostGIS_Full_Version()"))
            version = result.fetchone()[0]
            logger.info(f"✅ PostGIS disponible: {version[:50]}...")
            return True
        except Exception as e:
            logger.warning(f"⚠️ PostGIS non disponible: {e}")
            return False


def clear_tables(session):
    """Vide les tables avant migration (pour idempotence)."""
    logger.info("🧹 Nettoyage des tables...")
    session.execute(text("DELETE FROM simulations"))
    session.execute(text("DELETE FROM audit_logs"))
    session.execute(text("DELETE FROM regards"))
    session.execute(text("DELETE FROM conduites"))
    session.execute(text("DELETE FROM rejets"))
    session.execute(text("DELETE FROM clusters"))
    session.commit()
    logger.info("✅ Tables nettoyées")


def safe_float(value, default=0.0):
    """Convertit une valeur en float en nettoyant les strings."""
    if value is None or value == "":
        return default
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        # Nettoyer : remplacer espaces, virgules françaises
        cleaned = value.strip().replace(",", ".").replace(" ", "")
        if cleaned == "" or cleaned.lower() in ["null", "none", "nan"]:
            return default
        try:
            return float(cleaned)
        except ValueError:
            return default
    return default


def migrate_regards(session, geojson_features):
    """Migre les regards depuis GeoJSON vers PostgreSQL."""
    logger.info(f"📦 Migration de {len(geojson_features)} regards...")
    count = 0
    errors = 0
    duplicates = 0

    # Récupérer codes existants (pour éviter doublons)
    existing_codes = set(r[0] for r in session.query(Regard.code).all())

    for idx, feature in enumerate(geojson_features):
        try:
            props = feature.get("properties", {})
            geom = feature.get("geometry", {})
            coords = geom.get("coordinates", [0, 0])

            code_raw = props.get("Code", f"UNKNOWN_{idx}")
            code = str(code_raw).strip() if code_raw else f"UNKNOWN_{idx}"
            
            # Skip si code déjà en base
            if code in existing_codes:
                duplicates += 1
                continue

            profondeur = safe_float(props.get("Profondeur"), 0.0)
            diametre = safe_float(props.get("DIAMETRES"), 0.0)
            profrad = safe_float(props.get("PROFRADI"), 0.0)
            hfermsol = safe_float(props.get("HFERMSOL"), 0.0)

            regard = Regard(
                code=code,
                nom_voie=props.get("NOMVOIE"),
                commune=props.get("COMMUNE"),
                profondeur=profondeur,
                diametre=diametre,
                type_res=props.get("TYPERES"),
                profrad=profrad,
                hfermsol=hfermsol,
                longitude=coords[0] if coords else 0.0,
                latitude=coords[1] if coords else 0.0,
                version=1
            )
            session.add(regard)
            existing_codes.add(code)  # marquer comme ajouté
            count += 1

            if count % 1000 == 0:
                try:
                    session.commit()
                    logger.info(f"  ... {count} regards insérés")
                except Exception as e:
                    session.rollback()
                    errors += count % 1000  # approximer
                    logger.warning(f"  ... erreur lot, rollback")

        except Exception as e:
            errors += 1
            if errors % 100 == 0:
                logger.warning(f"  ... {errors} erreurs regards")
            continue

    try:
        session.commit()
    except Exception as e:
        logger.warning(f"Commit final regards échoué: {e}")
        session.rollback()

    logger.info(f"✅ {count} regards migrés ({duplicates} doublons ignorés, {errors} erreurs)")


def safe_float(value, default=0.0):
    """Convertit une valeur en float en nettoyant les strings."""
    if value is None or value == "":
        return default
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        cleaned = value.strip().replace(",", ".").replace(" ", "")
        if cleaned in ["", "null", "none", "nan", "NaN"]:
            return default
        try:
            return float(cleaned)
        except ValueError:
            return default
    return default


def migrate_conduites(session, geojson_features):
    """Migre les canalisations."""
    logger.info(f"📦 Migration de {len(geojson_features)} canalisations...")
    count = 0
    errors = 0
    duplicates = 0

    # Récupérer fid existants
    existing_fids = set(c[0] for c in session.query(Canalisation.fid).all())

    for idx, feature in enumerate(geojson_features):
        try:
            props = feature.get("properties", {})
            geom = feature.get("geometry", {})
            coords = geom.get("coordinates", [])

            fid_raw = props.get("fid", props.get("ID", idx))
            fid = str(fid_raw).strip() if fid_raw else f"C_{idx}"
            
            if fid in existing_fids:
                duplicates += 1
                continue

            # Construire WKT linestring
            if coords and len(coords) >= 2:
                points = [f"{c[0]:.6f} {c[1]:.6f}" for c in coords]
                wkt = f"LINESTRING ({', '.join(points)})"
            else:
                wkt = None

            # Nettoyage valeurs
            diametre = safe_float(props.get("DIAMETRE"), 0.0)
            longueur = safe_float(props.get("LINEAIRE"), 0.0)
            prof_fe_am = safe_float(props.get("PROF_FE_AM"), 0.0)
            prof_fe_av = safe_float(props.get("PROF_FE_AV"), 0.0)
            hauteur = safe_float(props.get("HAUTEUR"), 0.0)
            gdebase = safe_float(props.get("GDEBASE"), 0.0)

            canalisation = Canalisation(
                fid=fid,
                nom_voie=props.get("NOM-VOIE"),
                diametre=diametre,
                materiau=props.get("MATERIAU"),
                longueur=longueur,
                prof_fe_am=prof_fe_am,
                prof_fe_av=prof_fe_av,
                fonction_mt=props.get("FONCTIONMT"),
                id_amont=str(props.get("ID_AMONT", "") or ""),
                id_aval=str(props.get("ID_AVAL", "") or ""),
                forme_sect=props.get("FORMESECT"),
                hauteur=hauteur,
                gdebase=gdebase,
                geometry_wkt=wkt,
                version=1
            )
            session.add(canalisation)
            existing_fids.add(fid)
            count += 1

            if count % 500 == 0:
                try:
                    session.commit()
                    logger.info(f"  ... {count} canalisations insérées")
                except Exception as e:
                    session.rollback()
                    errors += count % 500
                    logger.warning(f"  ... erreur lot canalisations, rollback")

        except Exception as e:
            errors += 1
            if errors % 100 == 0:
                logger.warning(f"  ... {errors} erreurs canalisations")
            continue

    try:
        session.commit()
    except Exception as e:
        logger.warning(f"Commit final canalisations échoué: {e}")
        session.rollback()

    logger.info(f"✅ {count} canalisations migrées ({duplicates} doublons ignorés, {errors} erreurs)")


def migrate_rejets(session, geojson_features):
    """Migre les rejets (exutoires)."""
    logger.info(f"📦 Migration de {len(geojson_features)} rejets...")
    count = 0
    errors = 0
    duplicates = 0

    existing_noms = set(r[0] for r in session.query(Rejet.nom).all())

    for feature in geojson_features:
        try:
            props = feature.get("properties", {})
            geom = feature.get("geometry", {})
            coords = geom.get("coordinates", [0, 0])

            nom = str(props.get("NOM", "")).strip()
            if not nom:
                continue
            if nom in existing_noms:
                duplicates += 1
                continue

            rejet = Rejet(
                nom=nom,
                commune=props.get("COMMUNE"),
                nom_voie=props.get("NOMVOIE"),
                longitude=coords[0],
                latitude=coords[1],
                version=1
            )
            session.add(rejet)
            existing_noms.add(nom)
            count += 1

        except Exception as e:
            errors += 1
            continue

    try:
        session.commit()
    except:
        session.rollback()

    logger.info(f"✅ {count} rejets migrés ({duplicates} doublons ignorés, {errors} erreurs)")


def create_clusters_from_graph(session):
    """Reconstruit les clusters depuis le graphe et les insère en DB."""
    logger.info("🔧 Recalcul des clusters depuis le graphe...")

    from src.domain.graphe_reseau import construire_graphe, trouver_exutoires
    from src.domain.detecteur_clusters import (
        tracer_cluster_depuis_exutoire,
        calculer_statistiques,
        compter_infrastructures
    )

    try:
        G = construire_graphe()
        exutoires = trouver_exutoires(G)

        if not exutoires:
            logger.warning("⚠️ Aucun exutoire trouvé")
            return

        logger.info(f"📊 {len(exutoires)} exutoires identifiés")

        for idx, exutoire in enumerate(exutoires):
            edges = tracer_cluster_depuis_exutoire(G, exutoire["noeud"])
            if not edges:
                continue

            stats = calculer_statistiques(G, edges)

            # Compter infrastructures
            infra = compter_infrastructures(edges)

            # Enveloppe convexe des nœuds du cluster (pour géométrie)
            nodes = set()
            for amont, aval in edges:
                nodes.add(amont)
                nodes.add(aval)

            import shapely.geometry as geom
            from shapely import Point
            points = [Point(x, y) for x, y in nodes]
            hull = geom.MultiPoint(points).convex_hull
            geometry_wkt = hull.wkt if hull else None

            cluster = Cluster(
                nom=exutoire.get("nom", f"Exutoire_{idx}"),
                exutoire_noeud=str(exutoire["noeud"]),
                nb_conduites=stats["nb_conduites"],
                nb_noeuds=stats["nb_noeuds"],
                longueur_totale=stats["longueur_totale_m"],
                diametre_min=stats.get("diametre_min_m"),
                diametre_max=stats.get("diametre_max_m"),
                diametre_moy=stats.get("diametre_moy_m"),
                nb_regards=infra["nb_regards"],
                nb_stations=infra["nb_stations"],
                nb_ouvrages=infra["nb_ouvrages"],
                geometry_wkt=geometry_wkt,
                version=1
            )
            session.add(cluster)
            session.flush()  # pour obtenir l'ID

            # Lier regards et canalisations à ce cluster
            # (approche simplifiée : par proximité ou autres critères)
            # Pour POC: on laisse cluster_id NULL, à améliorer

            logger.info(f"  ✓ Cluster '{cluster.nom}': {stats['nb_conduites']} conduites")

        session.commit()
        logger.info(f"✅ {len(exutoires)} clusters créés")

    except Exception as e:
        logger.error(f"❌ Erreur création clusters: {e}")
        raise


def main():
    """Point d'entrée principal de la migration."""
    logger.info("🚀 Démarrage migration GeoPackage → PostgreSQL")
    logger.info("=" * 60)

    # 1. Charger données GeoPackage
    logger.info("📖 Chargement des données GeoPackage...")
    data = charger_donnees()

    if not data:
        logger.error("❌ Aucune donnée chargée depuis GeoPackage")
        return

    regards_data = data.get("regards", {"features": []})
    conduites_data = data.get("conduites", {"features": []})
    rejets_data = data.get("rejets", {"features": []})

    logger.info(f"✅ Données chargées:")
    logger.info(f"   - Regards: {len(regards_data['features'])}")
    logger.info(f"   - Canalisations: {len(conduites_data['features'])}")
    logger.info(f"   - Rejets: {len(rejets_data['features'])}")

    # 2. Créer tables
    logger.info("\n🏗️ Création des tables...")
    Base.metadata.create_all(bind=engine)
    logger.info("✅ Tables créées")

    # 3. Vérifier PostGIS
    postgis_ok = check_postgis(engine)

    # 4. Migrer
    session = SessionLocal()
    try:
        clear_tables(session)

        # Migration顺序: regards (pour foreign keys), rejets, conduites
        migrate_regards(session, regards_data["features"])
        migrate_rejets(session, rejets_data["features"])
        migrate_conduites(session, conduites_data["features"])

        # 5. Créer clusters
        create_clusters_from_graph(session)

        logger.info("\n" + "=" * 60)
        logger.info("✅ MIGRATION TERMINÉE AVEC SUCCÈS")
        logger.info("=" * 60)

        # Récapitulatif
        counts = {
            "regards": session.query(Regard).count(),
            "conduites": session.query(Canalisation).count(),
            "rejets": session.query(Rejet).count(),
            "clusters": session.query(Cluster).count()
        }
        logger.info(f"\n📊 Tables remplies:")
        for table, count in counts.items():
            logger.info(f"   {table}: {count} enregistrements")

    except Exception as e:
        logger.exception(f"❌ Erreur migration: {e}")
        session.rollback()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    main()
