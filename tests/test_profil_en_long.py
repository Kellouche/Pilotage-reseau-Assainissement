"""
================================================================================
Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
Auteur : Dr Abdelhakim KELLOUCHE
Date de création : 2026-04-20
Date de modification : 2026-11-09
Objet : Tests automatisés du profil en long hydraulique interactif (Phase 6.A)
================================================================================
"""

import os
import subprocess
import tempfile
from pathlib import Path
import pytest
from fastapi import HTTPException

os.environ["TESTING"] = "true"
from api.database import SessionLocal
from api.routes.simulations import get_profil_en_long


def test_profil_en_long_success():
    """Vérifie le calcul réussi d'un profil en long entre 2 regards connectés."""
    db = SessionLocal()
    try:
        res = get_profil_en_long(node_amont="2674", node_aval="2672", db=db)
        assert res["status"] == "success"
        assert res["node_amont"] == "2674"
        assert res["node_aval"] == "2672"
        assert res["nb_troncons"] >= 1
        assert res["longueur_totale_m"] > 0
        assert len(res["segments"]) >= 2

        # Vérification des attributs géométriques obligatoires
        premier_segment = res["segments"][0]
        assert "z_radier" in premier_segment
        assert "z_terrain" in premier_segment
        assert "z_gen_superieure" in premier_segment
        assert "distance_m" in premier_segment
        assert premier_segment["distance_m"] == 0.0
        assert premier_segment["z_terrain"] >= premier_segment["z_radier"]

        dernier_segment = res["segments"][-1]
        assert dernier_segment["distance_m"] == res["longueur_totale_m"]
    finally:
        db.close()


def test_profil_en_long_reverse_auto_fallback():
    """Vérifie que l'algorithme retrouve le chemin amont/aval même si l'ordre est inversé."""
    db = SessionLocal()
    try:
        res = get_profil_en_long(node_amont="2672", node_aval="2674", db=db)
        assert res["status"] == "success"
        assert res["nb_troncons"] >= 1
        assert res["longueur_totale_m"] > 0
    finally:
        db.close()


def test_profil_en_long_node_not_found():
    """Vérifie qu'un code de regard inexistant lève un code HTTP 404."""
    db = SessionLocal()
    try:
        with pytest.raises(HTTPException) as excinfo:
            get_profil_en_long(node_amont="REG_TOTALEMENT_INCONNU_99999", node_aval="2672", db=db)
        assert excinfo.value.status_code == 404
    finally:
        db.close()


def test_profil_long_frontend_delegate_connectivite_a_l_api():
    """Vérifie que la sélection de deux regards ne dépend pas d'un graphe
    frontend incomplet : l'API reste l'autorité de routage hydraulique."""
    js_path = Path("static/js/app/profil_long.js").resolve()
    harness = r'''
const fs = require('fs');
const vm = require('vm');
const sourcePath = process.argv[2];
const source = fs.readFileSync(sourcePath, 'utf8');
const fetchCalls = [];
const sandbox = {
    window: {
        _dernierResultatSimulation: {
            conduit_results: {
                C_1: { link_id: 'C_1', u_node: '2288', d_node: '2287' }
            }
        }
    },
    document: { getElementById: () => null },
    fetch: (url) => {
        fetchCalls.push(url);
        return new Promise(() => {});
    },
    alert: (message) => { throw new Error(`Alerte frontend inattendue : ${message}`); },
    console
};
vm.createContext(sandbox);
vm.runInContext(source, sandbox);
sandbox.chargerProfilLong('2288', '2287');
const expected = '/api/v1/simulations/profil-en-long?node_amont=2288&node_aval=2287';
if (fetchCalls.length !== 1 || fetchCalls[0] !== expected) {
    console.error(`Appel API inattendu : ${JSON.stringify(fetchCalls)}`);
    process.exit(1);
}
'''
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as tf:
        tf.write(harness)
        tf_name = tf.name
    try:
        result = subprocess.run(
            ["node", tf_name, str(js_path)],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stderr or result.stdout
    finally:
        os.remove(tf_name)


def test_resultats_regard_normal_cliquable_en_mode_profil():
    """Vérifie qu'un regard simulé en écoulement normal (sans entrée détaillée
    dans node_results) conserve bien son interception de clic pour le profil."""
    js_path = Path("static/js/app/resultats_affichage.js").resolve()
    harness = r'''
const fs = require('fs');
const vm = require('vm');
const sourcePath = process.argv[2];
const source = fs.readFileSync(sourcePath, 'utf8');
const createdLayers = [];
const layerGroup = () => ({
    addTo() { return this; },
    addLayer() { return this; },
    clearLayers() {},
    bringToFront() { return this; },
    getLayers() { return []; },
    getBounds() { return null; },
    eachLayer() {}
});
const nodesGeo = {
    type: 'FeatureCollection',
    features: [{
        type: 'Feature',
        properties: { Code: '2288' },
        geometry: { type: 'Point', coordinates: [0, 0] }
    }]
};
const carte = {
    getPane: () => null,
    createPane: () => ({ style: {} }),
    hasLayer: () => false,
    removeLayer: () => {},
    closePopup: () => {},
    fitBounds: () => {}
};
const couches = {
    conduites: layerGroup(),
    regards: layerGroup(),
    rejets: layerGroup(),
    step: layerGroup(),
    res_conduites: layerGroup(),
    res_regards: layerGroup()
};
const L = {
    geoJSON: (geojson, options = {}) => ({
        addTo: () => {
            (geojson.features || []).forEach((feature) => {
                if (options.filter && !options.filter(feature)) return;
                const layer = {
                    feature,
                    handlers: {},
                    bindTooltip() { return this; },
                    bindPopup() { return this; },
                    on(event, fn) { this.handlers[event] = fn; return this; },
                    setStyle() { return this; },
                    getTooltip() { return null; },
                    openTooltip() {},
                    closeTooltip() {},
                    closePopup() {}
                };
                if (options.onEachFeature) options.onEachFeature(feature, layer);
                createdLayers.push(layer);
            });
            return this;
        }
    }),
    DomEvent: { stop() {} },
    polyline: () => ({ bindPopup() { return this; }, bindTooltip() { return this; }, addTo() { return this; } })
};
const calls = [];
const sandbox = {
    window: {
        profilLongState: { active: true, step: 'amont' },
        handleRegardClickForProfil: (code) => calls.push(code),
        _rawNetworkData: { couches: { regards: nodesGeo } }
    },
    carte,
    couches,
    L,
    document: { getElementById: () => null },
    setTimeout: (fn) => fn(),
    console
};
vm.createContext(sandbox);
vm.runInContext(source, sandbox);
sandbox.window.afficherResultatsSimulation({
    conduit_results: {},
    node_results: {},
    meta: { simulated_nodes: ['2288'], raccordements_orphelins: [] }
});
const layer = createdLayers.find((l) => l.feature.properties.Code === '2288');
if (!layer || typeof layer.handlers.click !== 'function') {
    console.error('Le regard normal ne possède pas de handler click profil');
    process.exit(1);
}
layer.handlers.click.call(layer, { latlng: { lat: 1, lng: 2 } });
if (calls.length !== 1 || calls[0] !== '2288') {
    console.error(`Sélection profil inattendue : ${JSON.stringify(calls)}`);
    process.exit(1);
}
'''
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as tf:
        tf.write(harness)
        tf_name = tf.name
    try:
        result = subprocess.run(
            ["node", tf_name, str(js_path)],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stderr or result.stdout
    finally:
        os.remove(tf_name)


def test_cockpit_includes_profil_long_components():
    """Vérifie la bonne intégration dans le template HTML et la barre d'outils du Cockpit."""
    root = Path(__file__).resolve().parent.parent
    index_html = (root / "templates" / "index.html").read_text(encoding="utf-8")
    toolbar_html = (root / "templates" / "partials" / "toolbar_edit.html").read_text(encoding="utf-8")
    panel_html = (root / "templates" / "partials" / "panel_profil_long.html").read_text(encoding="utf-8")

    assert "chart.umd.min.js" in index_html
    assert "profil_long.js" in index_html
    assert "panel_profil_long.html" in index_html
    assert "btn-profil-long" in toolbar_html
    assert "canvas-profil-long" in panel_html
    assert "input-profil-amont" in panel_html
    assert "input-profil-aval" in panel_html

