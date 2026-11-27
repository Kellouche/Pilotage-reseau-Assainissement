# -*- coding: utf-8 -*-
"""
================================================================================
Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
Auteur : Dr Abdelhakim KELLOUCHE
Date de création : 2026-11-27
Date de modification : 2026-11-27
Objet : Cache disque et résolution GPKG versionné des simulations (empreintes, chemins, lecture/écriture).
================================================================================
"""

import hashlib
import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from sqlalchemy.orm import Session

logger = logging.getLogger("swmm_platform.services.simulation_cache_service")

# Version du générateur .inp (sections_inp.py & cie) — incrémenter à chaque
# correctif susceptible de modifier le contenu du .inp afin d'invalider
# les simulations en cache calculées avec l'ancienne version.
# v2 : intervalle RAINGAGES dérivé de la série (fix pluie diluée ~1/3).
MOTEUR_VERSION_INP = "inp-gen-v2-raingage"


def _resoudre_gpkg_versionne(db: Session, proj: Any):
    """
    Résout le GPKG de simulation pour un projet via le versionnement (3B).
    Retourne (gpkg_path, version_meta) ou (None, meta_erreur).
    Une version existante mais indisponible n'est JAMAIS remplacée
    silencieusement par un autre fichier.
    """
    from api.services.gpkg_versions import resoudre_version_pour_simulation
    return resoudre_version_pour_simulation(db, proj)


def _sha256_gpkg(gpkg_path: Path) -> Optional[str]:
    """Empreinte SHA-256 complète du contenu GPKG (cache mémoire par mtime/taille)."""
    try:
        if gpkg_path and Path(gpkg_path).exists():
            from api.services.gpkg_versions import sha256_fichier
            return sha256_fichier(Path(gpkg_path))
    except Exception as e:
        logger.warning("Empreinte SHA-256 GPKG impossible pour %s : %s", gpkg_path, e)
    return None


def _cle_cache_gpkg(gpkg_path: Path, sha256: Optional[str] = None) -> str:
    """
    Identité de cache basée sur le CONTENU du GPKG (SHA-256 tronqué),
    jamais sur le chemin : le snapshot matérialisé d'une version et le
    fichier source du projet partagent ainsi le même cache.
    `sha256` peut être fourni par l'appelant (empreinte fraîche déjà
    calculée lors de la résolution de version) pour éviter un re-hachage
    du même fichier dans la même requête — il doit TOUJOURS provenir de
    la résolution de la version simulée, jamais d'une valeur cachée.
    """
    sha = sha256 or _sha256_gpkg(gpkg_path)
    if sha:
        return sha[:16]
    stem = Path(gpkg_path).stem if gpkg_path else "inconnu"
    return re.sub(r'[^\w\-]+', '_', stem)


def _repertoire_cache_simulation() -> Path:
    """Répertoire unique de cache : data/.simulation_cache (partagé, content-adressé)."""
    from api.services.gpkg_versions import GPKG_CACHE_DIR
    return Path(GPKG_CACHE_DIR).parent / ".simulation_cache"


def iter_fichiers_cache_simulation(gpkg_path: Path, sha256: Optional[str] = None):
    """
    Itère les fichiers de cache candidats pour ce GPKG, du plus récent au plus ancien :
    d'abord les entrées content-adressées (SHA-256), puis le legacy
    <gpkg_path.parent>/.simulation_cache (stem historique) pour compatibilité.
    """
    sha = sha256 or _sha256_gpkg(gpkg_path)
    candidats = []
    cle = sha[:16] if sha else re.sub(
        r'[^\w\-]+', '_', Path(gpkg_path).stem if gpkg_path else "inconnu")
    dossier = _repertoire_cache_simulation()
    if dossier.exists():
        candidats.extend(dossier.glob(f"sim_{cle}_cluster_*.json"))
        # Fichiers legacy éventuels dans le même dossier (stem d'origine)
        if gpkg_path:
            stem_legacy = re.sub(r'[^\w\-]+', '_', Path(gpkg_path).stem)
            if stem_legacy != cle:
                candidats.extend(dossier.glob(f"sim_{stem_legacy}_cluster_*.json"))
    legacy_dir = Path(gpkg_path).parent / ".simulation_cache" if gpkg_path else None
    if legacy_dir and legacy_dir != dossier and legacy_dir.exists():
        stem_legacy = re.sub(r'[^\w\-]+', '_', Path(gpkg_path).stem)
        candidats.extend(legacy_dir.glob(f"sim_{stem_legacy}_cluster_*.json"))
    # Dédupliquer puis trier par date de modification décroissante
    uniq = {p.resolve(): p for p in candidats}
    return sorted(uniq.values(), key=lambda x: x.stat().st_mtime, reverse=True)


def resoudre_gpkg_effectif_pour_projet_avec_meta(
    db: Session, proj: Any
) -> Tuple[Optional[Path], Dict[str, Any]]:
    """
    LOT P1.4 — comme resoudre_gpkg_effectif_pour_projet mais retourne aussi
    les métadonnées de version (version_id, sha256, storage_kind) :
    indispensable à l'estampillage des apports DWF et à leur validation
    stricte contre la version exacte du réseau.
    """
    if proj is None:
        return None, {}
    chemin, meta = _resoudre_gpkg_versionne(db, proj)
    if chemin is not None:
        return Path(chemin), meta or {}
    if getattr(proj, "gpkg_version_id", None):
        return None, meta or {}
    if proj.source_gpkg_key and Path(proj.source_gpkg_key).exists():
        return Path(proj.source_gpkg_key), meta or {}
    return None, meta or {}


def resoudre_gpkg_effectif_pour_projet(db: Session, proj: Any) -> Optional[Path]:
    """
    Chemin GPKG effectif pour les endpoints de lecture (téléchargements, PDF) :
    snapshot matérialisé de la version courante si le projet est versionné,
    sinon source_gpkg_key. Si une version est référencée mais indisponible,
    retourne None — jamais de repli silencieux sur un fichier différent.
    """
    chemin, _meta = resoudre_gpkg_effectif_pour_projet_avec_meta(db, proj)
    return chemin


def generer_cle_cache_simulation(gpkg_path: Path, payload: Any,
                                 extra_params: Optional[Dict[str, Any]] = None,
                                 gpkg_sha256: Optional[str] = None) -> Tuple[str, Dict[str, Any]]:
    """
    Génère un dictionnaire canonique normalisé et une empreinte SHA-256
    garantissant l'idempotence exacte de la simulation hydrodynamique.
    L'identité du GPKG est son empreinte de CONTENU (SHA-256) : deux chemins
    vers le même contenu (source projet / snapshot versionné) partagent
    la même empreinte de cache.
    """
    gpkg_stat = gpkg_path.stat() if gpkg_path.exists() else None
    gpkg_size = int(gpkg_stat.st_size) if gpkg_stat else 0
    # LOT P1.4.1 — gpkg_sha256 peut être fourni par la résolution de version
    # (empreinte fraîche du contenu exact) : même valeur, sans re-hachage.
    if gpkg_sha256 is None:
        gpkg_sha256 = _sha256_gpkg(gpkg_path) if gpkg_stat else None

    orph_ids = []
    if getattr(payload, "raccordements_orphelins", None):
        for item in payload.raccordements_orphelins:
            if isinstance(item, dict):
                orph_ids.append(str(item.get("id", item.get("nom", ""))))
            else:
                orph_ids.append(str(item))
    orph_ids.sort()

    # Version du moteur de génération .inp : entre dans l'empreinte pour
    # qu'un correctif du générateur (ex. intervalle RAINGAGES) invalide
    # automatiquement les simulations mises en cache avec l'ancien code.
    # À incrémenter à chaque changement susceptible d'altérer le .inp.
    params_dict = {
        "moteur_version": MOTEUR_VERSION_INP,
        "gpkg_sha256": gpkg_sha256,
        "gpkg_size": gpkg_size,
        "cluster_id": str(getattr(payload, "cluster_id", None)),
        "scenario_key": str(getattr(payload, "scenario_key", "pluie_decennale")),
        "duree_heures": float(getattr(payload, "duree_heures", None)) if getattr(payload, "duree_heures", None) is not None else None,
        "pas_routage_sec": int(getattr(payload, "pas_routage_sec", None) or 5),
        "pente_moyenne_pct": float(getattr(payload, "pente_moyenne_pct", None) or 1.0),
        "buffer_m": float(getattr(payload, "buffer_m", None) or 35.0),
        "valider_raccordement": bool(getattr(payload, "valider_raccordement", None) if getattr(payload, "valider_raccordement", None) is not None else True),
        "typologie_sol": str(getattr(payload, "typologie_sol", None) or "habitat_mixte"),
        "imperv_pct": float(getattr(payload, "imperv_pct", None)) if getattr(payload, "imperv_pct", None) is not None else None,
        "intensite_max_mmh": float(getattr(payload, "intensite_max_mmh", None)) if getattr(payload, "intensite_max_mmh", None) is not None else None,
        "station_id": str(getattr(payload, "station_id", None) or "chlef_anrh_siege"),
        "raccordements_orphelins": orph_ids,
        "bms_mode": bool(getattr(payload, "bms_mode", False)),
        "bms_vigilance": str(getattr(payload, "bms_vigilance", None) or "orange"),
        "bms_cumul_mm": float(getattr(payload, "bms_cumul_mm", None) or 30.0),
        "bms_heure_debut": str(getattr(payload, "bms_heure_debut", None) or "07:00"),
        "bms_heure_fin": str(getattr(payload, "bms_heure_fin", None) or "21:00"),
        "bms_profil": str(getattr(payload, "bms_profil", None) or "cloche"),
        "altimetrie_terrain": bool(getattr(payload, "altimetrie_terrain", False)),
        "altimetrie_layer_id": (str(getattr(payload, "altimetrie_layer_id", None))
                                if getattr(payload, "altimetrie_layer_id", None) else None),
    }
    # Étape 3A : la référence métier du bassin n'entre dans l'empreinte
    # que lorsqu'elle est fournie — les caches historiques restent valides.
    if getattr(payload, "bassin_ref", None):
        params_dict["bassin_ref"] = str(payload.bassin_ref)
    # État du réseau (Colmatage & Vieillissement) — n'entre dans l'empreinte
    # que s'il est non-nominal, préservant les caches nominaux existants.
    raw_etat = getattr(payload, "etat_reseau", None)
    if raw_etat:
        from src.domain.moteur_swmm.etat_reseau import normaliser_etat_reseau, est_etat_nominal
        etat_norm = normaliser_etat_reseau(raw_etat)
        if not est_etat_nominal(etat_norm):
            params_dict["etat_reseau"] = etat_norm
    # LOT P1.3 : l'état des apports DWF entre dans l'empreinte — modifier
    # un apport invalide le cache (sinon collision silencieuse).
    if extra_params:
        params_dict.update(extra_params)

    serialized = json.dumps(params_dict, sort_keys=True, ensure_ascii=False)
    param_hash = hashlib.sha256(serialized.encode("utf-8")).hexdigest()[:16]
    return param_hash, params_dict


def get_cache_simulation_file(gpkg_path: Path, cluster_id: Any, param_hash: str,
                              gpkg_sha256: Optional[str] = None) -> Path:
    """Retourne le chemin vers le fichier de persistance de simulation (content-adressé)."""
    cache_dir = _repertoire_cache_simulation()
    cache_dir.mkdir(parents=True, exist_ok=True)
    clean_stem = _cle_cache_gpkg(gpkg_path, gpkg_sha256)
    clean_cid = re.sub(r'[^\w\-]+', '_', str(cluster_id))
    return cache_dir / f"sim_{clean_stem}_cluster_{clean_cid}_{param_hash}.json"


def est_simulation_valide(data: Any) -> bool:
    """Vérifie si les résultats de simulation sont valides et non un artefact corrompu ou factice."""
    if not isinstance(data, dict):
        return False
    if "node_results" not in data or "conduit_results" not in data:
        return False
    meta = data.get("meta") or {}
    bbox = meta.get("bbox")
    if bbox and len(bbox) == 4:
        # Rejeter les coordonnées dummy résiduelles (0, 0) envoyées dans l'océan Atlantique
        if abs(bbox[0]) < 1.0 and abs(bbox[1]) < 2.0:
            return False
    # Valide si des conduits/junctions sont répertoriés dans les métadonnées OU dans les dictionnaires de résultats
    nb_conduits = meta.get("conduits_count", 0) or len(data.get("conduit_results", {}))
    nb_junctions = meta.get("junctions_count", 0) or len(data.get("node_results", {}))
    if nb_conduits <= 0 and nb_junctions <= 0 and not data.get("inp_content"):
        return False
    return True


def charger_cache_simulation(gpkg_path: Path, cluster_id: Any, param_hash: str,
                             gpkg_sha256: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Charge les résultats de la simulation si le fichier de cache existe."""
    cache_file = get_cache_simulation_file(gpkg_path, cluster_id, param_hash, gpkg_sha256)
    if cache_file.exists():
        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            if data and est_simulation_valide(data):
                return data
        except Exception as e:
            logger.warning("Échec de lecture du cache simulation %s: %s", cache_file, e)
    return None
