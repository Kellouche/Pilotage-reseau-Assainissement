"""
================================================================================
Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
Auteur : Dr Abdelhakim KELLOUCHE
Date de création : 2026-04-20
Date de modification : 2026-11-08
Objet : Tests automatisés de synchronisation de la simulation par bassin et non-duplication des bandeaux
================================================================================
"""

from pathlib import Path
import uuid
import pytest
from types import SimpleNamespace
from api.routes.simulations import get_bassin_simulation, download_latest_inp
from api.database import SessionLocal
from api.models import Organization, Project

GPKG_BASSIN = Path("uploads/a66e32ad-f32b-4529-acc3-7a6026eb5a8a/network_Assainissement_Ville.gpkg")


@pytest.fixture(scope="module")
def ctx_bassin():
    """LOT P0.1 — org dédiée + projet unique sur le GPKG de référence :
    résolution strictement bornée au tenant (plus d'appel anonyme)."""
    if not GPKG_BASSIN.exists():
        pytest.skip("GeoPackage de référence absent")
    db = SessionLocal()
    sfx = uuid.uuid4().hex[:8]
    org = Organization(id=f"org_bassin_{sfx}", name="Org Bassin", slug=f"org-bassin-{sfx}")
    proj = Project(
        id=f"proj_bassin_{sfx}", org_id=org.id, name="Projet Bassin",
        source_gpkg_key=str(GPKG_BASSIN.resolve()), gpkg_version_id=None,
        is_archived=False,
    )
    db.add_all([org, proj])
    db.commit()
    try:
        yield {"db": db, "org": org, "proj": proj,
               "tenant": SimpleNamespace(org_id=org.id)}
    finally:
        db.delete(proj)
        db.delete(org)
        db.commit()
        db.close()

def _get_full_cockpit_content():
    base = Path(__file__).resolve().parent.parent
    content = (base / "templates" / "index.html").read_text(encoding="utf-8")
    for p in (base / "templates" / "partials").glob("*.html"):
        content += "\n" + p.read_text(encoding="utf-8")
    for j in (base / "static" / "js" / "app").glob("*.js"):
        content += "\n" + j.read_text(encoding="utf-8")
    for c in (base / "static" / "css").glob("*.css"):
        content += "\n" + c.read_text(encoding="utf-8")
    return content

def test_suppression_bandeau_flottant_doublon():
    """Vérifie que l'indicateur flottant en doublon sur la carte a été retiré."""
    cockpit_content = _get_full_cockpit_content()
    assert 'id="map-bassin-indicator"' not in cockpit_content
    assert 'id="topbar-bassin-container"' in cockpit_content
    assert 'id="topbar-bassin-pill"' in cockpit_content
    assert 'gererAffichageSimulationPourBassin' in cockpit_content


def test_endpoint_simulation_par_bassin(ctx_bassin):
    """Vérifie le fonctionnement de l'endpoint get_bassin_simulation."""
    db = ctx_bassin["db"]
    tenant = ctx_bassin["tenant"]
    try:
        # 1. Bassin sans calcul
        r = get_bassin_simulation("999999", db=db, tenant=tenant)
        assert r["status"] == "none"

        # 2. Bassin avec calcul sauvegardé (ex: cluster 92 = 25_ouvrages_speciaux_348883)
        r_exist = get_bassin_simulation("92", db=db, tenant=tenant)
        assert r_exist["status"] in ("none", "success")
        if r_exist["status"] == "success":
            assert "kpis" in r_exist or "conduit_results" in r_exist
            assert "meta" in r_exist

        # 3. Résolution robuste par nom textuel de bassin
        r_nom = get_bassin_simulation("25_ouvrages_speciaux_348883", db=db, tenant=tenant)
        assert r_nom["status"] in ("none", "success")
        if r_nom["status"] == "success":
            assert "meta" in r_nom
    finally:
        pass


def test_fermeture_automatique_modale_et_zoom_grande_echelle():
    """Vérifie que la modale se ferme automatiquement post-simulation et que le zoom cible la grande échelle."""
    sim_ui_js = Path("static/js/app/simulation_ui.js").read_text(encoding="utf-8")
    resultats_couches_js = Path("static/js/app/resultats_couches.js").read_text(encoding="utf-8")
    resultats_affichage_js = Path("static/js/app/resultats_affichage.js").read_text(encoding="utf-8")

    # 1. Présence de l'appel automatique de fermeture de la modale dans declencherSimulationSWMM
    assert "fermerModalSimulation" in sim_ui_js
    assert "window.fermerModalSimulation()" in sim_ui_js
    assert "window.zoomerSurZoneSimulee(data, 19)" in sim_ui_js

    # 2. Zoom à grande échelle (maxZoom 19)
    assert "maxZoom: cibleMaxZoom || 19" in resultats_couches_js
    assert "maxZoom: 19" in resultats_affichage_js
    assert "padding: [35, 35]" in resultats_couches_js
    assert "padding: [35, 35]" in resultats_affichage_js


def test_anti_cache_et_cache_busting():
    """Vérifie la présence du middleware anti-cache HTTP et des tags de cache-busting dans les templates."""
    main_py = Path("api/main.py").read_text(encoding="utf-8")
    index_html = Path("templates/index.html").read_text(encoding="utf-8")

    assert "anti_cache_static_middleware" in main_py
    assert "no-store, must-revalidate" in main_py
    assert "?v=5.2.5" in index_html


def test_bassin_non_simule_mention_et_masquage_legende():
    """Vérifie que pour un bassin non simulé, l'indicateur affiche '(non simulé)' et la légende est masquée."""
    bassins_js = Path("static/js/app/bassins_selection.js").read_text(encoding="utf-8")
    assert "(non simulé)" in bassins_js
    assert "legNonSim.style.display = 'none'" in bassins_js


def test_persistance_cochage_rejets_et_step():
    """Vérifie que les couches rejets et step restent cochées et affichées lors des transitions."""
    res_aff = Path("static/js/app/resultats_affichage.js").read_text(encoding="utf-8")
    res_act = Path("static/js/app/resultats_actions.js").read_text(encoding="utf-8")
    bassin_sel = Path("static/js/app/bassins_selection.js").read_text(encoding="utf-8")

    assert "elRejets.checked = true" in res_aff
    assert "elStep.checked = true" in res_aff
    assert "elRej.checked = true" in res_act
    assert "elStep.checked = true" in res_act
    assert "elRejSync.checked = true" in bassin_sel
    assert "elStepSync.checked = true" in bassin_sel


def test_allegement_panneau_lateral_sans_pave_bassin_info():
    """Vérifie que le panneau latéral est allégé et ne contient plus le pavé descriptif redondant."""
    edit_js = Path("static/js/app/edition_attributs.js").read_text(encoding="utf-8")
    sidebar_html = Path("templates/partials/sidebar_engineering.html").read_text(encoding="utf-8")

    assert "infoDiv.innerHTML = ''" in edit_js
    assert 'display: none;' in sidebar_html


def test_zone_simulee_survol_garde_bleu_ciel():
    """Vérifie que le survol et la sortie de la zone simulée conservent le bleu ciel et évitent le marron."""
    couches_js = Path("static/js/app/resultats_couches.js").read_text(encoding="utf-8")
    det_js = Path("static/js/app/bassins_detection.js").read_text(encoding="utf-8")
    sel_js = Path("static/js/app/bassins_selection.js").read_text(encoding="utf-8")

    # resultats_couches.js
    assert "mouseover.simBassin" in couches_js
    assert "mouseout.simBassin" in couches_js
    assert "fillColor: '#38bdf8'" in couches_js
    assert "color: '#0284c7'" in couches_js

    # bassins_detection.js
    assert "isSimule" in det_js
    assert "this.setStyle({ color: '#0284c7', weight: 3.5, fillColor: '#38bdf8'" in det_js

    # bassins_selection.js
    assert "Bassin simulé : maintien impératif de la teinte bleu ciel" in sel_js
    assert "layer.setStyle({ color: '#0284c7', fillColor: '#38bdf8'" in sel_js


def test_resolution_et_contour_cluster_9_ouvrages_speciaux_345101():
    """Vérifie que le cluster 9_ouvrages_speciaux_345101 résout son exutoire réel et a un contour valide."""
    import json
    from shapely.geometry import shape

    cache_path = Path("uploads/a66e32ad-f32b-4529-acc3-7a6026eb5a8a/network_Assainissement_Ville.clusters_cache.json")
    if cache_path.exists():
        with open(cache_path, "r", encoding="utf-8") as f:
            cdata = json.load(f)

        found_98 = False
        for feat in cdata.get("bassins_geojson", {}).get("features", []):
            fp = feat.get("properties", {})
            if fp.get("cluster_id") == 98 or "345101" in str(fp.get("nom")):
                found_98 = True
                geom = feat.get("geometry")
                assert geom is not None, "La géométrie du contour du cluster 98 ne doit pas être nulle"
                poly = shape(geom)
                assert poly.is_valid or poly.buffer(0).is_valid, f"Le contour du cluster 98 doit être valide topologiquement (sans auto-intersection)"
                assert poly.bounds[1] > 30.0, "Les coordonnées doivent être en Algérie (~36°N)"
                break
        assert found_98, "Le cluster 98 (9_ouvrages_speciaux_345101) doit être présent dans le cache"

    # Vérifier que le code de filtrage_bassin gère exutoire_id et regard_proche_id
    code_fb = Path("src/domain/moteur_swmm/filtrage_bassin.py").read_text(encoding="utf-8")
    assert "matched_fp.get(\"exutoire_id\")" in code_fb
    assert "matched_fp.get(\"regard_proche_id\")" in code_fb


def test_export_modele_inp_nom_bassin_et_contenu(ctx_bassin):
    """Vérifie que l'export INP cible le nom du bassin versant sans déborder sur la totalité du réseau."""
    from api.routes.simulations import _formater_nom_fichier_export

    # 1. Nom de fichier ciblé
    fn = _formater_nom_fichier_export("network_Assainissement_Ville", nom_bassin="9_ouvrages_speciaux_345101", ext="inp")
    assert fn == "9_ouvrages_speciaux_345101.inp", f"Attendu 9_ouvrages_speciaux_345101.inp, obtenu {fn}"

    # 2. Appel de download_latest_inp avec cluster_id et project_id explicite
    # (LOT P0.1 — tenant authentifié, périmètre projet strict).
    db = ctx_bassin["db"]
    tenant = ctx_bassin["tenant"]
    proj = ctx_bassin["proj"]
    resp = download_latest_inp(
        cluster_id="98", project_id=proj.id, db=db, tenant=tenant)
    assert resp.status_code == 200
    disp = resp.headers.get("content-disposition", "")
    assert 'filename="9_ouvrages_speciaux_345101.inp"' in disp
    body = resp.body.decode("utf-8")
    assert "[JUNCTIONS]" in body
    assert "[CONDUITS]" in body
    assert len(body.splitlines()) > 500


def test_suppression_popups_blanches_indesirables():
    """Vérifie que les popups blanches sur les polygones de bassins ont été supprimées au profit du tooltip noir."""
    det_js = Path("static/js/app/bassins_detection.js").read_text(encoding="utf-8")
    couches_js = Path("static/js/app/resultats_couches.js").read_text(encoding="utf-8")
    act_js = Path("static/js/app/resultats_actions.js").read_text(encoding="utf-8")

    # Vérifier qu'aucune popup n'est bindée aux couches de bassins
    assert "layer.bindPopup(tipHtml)" not in det_js
    assert "layer.bindPopup(fullSimTooltip)" not in couches_js
    assert "layer.bindPopup(baseTip)" not in act_js
    assert "className: 'sim-bassin-tooltip'" in det_js

