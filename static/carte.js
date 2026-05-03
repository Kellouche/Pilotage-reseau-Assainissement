// ============================================================
// SWMM Platform - Frontend Carte
// Version simple : affichage direct des couches GeoPackage
// ============================================================

let carte = null;
let couches = {};
let dataGlobal = null;

function initCarte() {
    console.log('initCarte() start');
    carte = L.map('map').setView([36.15, 1.33], 13);
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '© OpenStreetMap'
    }).addTo(carte);

    // Couches Leaflet (vides initialement)
    couches = {
        conduites: L.layerGroup().addTo(carte),
        regards: L.layerGroup().addTo(carte),
        stations: L.layerGroup().addTo(carte),
        step: L.layerGroup().addTo(carte),
        ouvrages: L.layerGroup().addTo(carte)
    };

    // Toggle checkboxes
    ['conduites', 'regards', 'stations', 'step', 'ouvrages'].forEach(type => {
        const el = document.getElementById('f-' + type);
        if (el) {
            el.onchange = () => {
                if (el.checked) couches[type].addTo(carte);
                else carte.removeLayer(couches[type]);
            };
        }
    });

    // Charger les données
    chargerDonnees();
}

function chargerDonnees() {
    console.log('Fetch /api/v1/layers...');
    fetch('/api/v1/layers?ts=' + Date.now())
        .then(r => r.json())
        .then(d => {
            console.log('Données reçues:', d.compteurs);
            dataGlobal = d;
            afficherCouches(d);
            majStats(d.compteurs);
            majSelectClusters(d.couches);
        })
        .catch(e => {
            console.error('Erreur:', e);
            toast('Erreur chargement: ' + e.message);
        });
}

function afficherCouches(d) {
    // Nettoyer
    Object.values(couches).forEach(c => c.clearLayers());

    const couleurs = {
        conduites: '#3498db',   // bleu
        regards: '#f1c40f',     // jaune
        stations: '#e67e22',    // orange
        step: '#27ae60',        // vert
        ouvrages: '#9b59b6'     // violet
    };

    // 1. Conduites (lignes)
    (d.couches.conduites?.features || []).forEach(f => {
        if (f.geometry?.type === 'LineString') {
            const coords = f.geometry.coordinates.map(c => [c[1], c[0]]);
            L.polyline(coords, {
                color: couleurs.conduites,
                weight: 3,
                opacity: 0.8
            }).addTo(couches.conduites);
        }
    });
    console.log('Conduites:', couches.conduites.getLayers().length);

    // 2. Regards (points)
    (d.couches.regards?.features || []).forEach(f => {
        if (f.geometry?.type === 'Point') {
            const [x, y] = f.geometry.coordinates;
            L.circleMarker([y, x], {
                radius: 4,
                color: couleurs.regards,
                fillColor: couleurs.regards,
                fillOpacity: 0.9
            }).bindPopup('<b>Regard</b>').addTo(couches.regards);
        }
    });
    console.log('Regards:', couches.regards.getLayers().length);

    // 3. Stations (points)
    (d.couches.stations?.features || []).forEach(f => {
        if (f.geometry?.type === 'Point') {
            const [x, y] = f.geometry.coordinates;
            L.circleMarker([y, x], {
                radius: 6,
                color: couleurs.stations,
                fillColor: couleurs.stations,
                fillOpacity: 0.9
            }).bindPopup('<b>Station</b>').addTo(couches.stations);
        }
    });
    console.log('Stations:', couches.stations.getLayers().length);

    // 4. STEP (points)
    (d.couches.step?.features || []).forEach(f => {
        if (f.geometry?.type === 'Point') {
            const [x, y] = f.geometry.coordinates;
            L.circleMarker([y, x], {
                radius: 7,
                color: couleurs.step,
                fillColor: couleurs.step,
                fillOpacity: 0.9
            }).bindPopup('<b>STEP</b>').addTo(couches.step);
        }
    });
    console.log('STEP:', couches.step.getLayers().length);

    // 5. Ouvrages (points)
    (d.couches.ouvrages?.features || []).forEach(f => {
        if (f.geometry?.type === 'Point') {
            const [x, y] = f.geometry.coordinates;
            L.circleMarker([y, x], {
                radius: 6,
                color: couleurs.ouvrages,
                fillColor: couleurs.ouvrages,
                fillOpacity: 0.9
            }).bindPopup('<b>Ouvrage</b>').addTo(couches.ouvrages);
        }
    });
    console.log('Ouvrages:', couches.ouvrages.getLayers().length);

    // Zoom
    const allLayers = Object.values(couches).filter(l => l.getLayers().length > 0);
    if (allLayers.length > 0) {
        const bounds = L.latLngBounds([]);
        allLayers.forEach(l => l.getLayers().forEach(layer => {
            bounds.extend(layer.getBounds ? layer.getBounds() : layer.getLatLng());
        }));
        carte.fitBounds(bounds, {padding: [50, 50]});
    }
}

function majStats(compteurs) {
    document.getElementById('stat-total').textContent = compteurs.conduites || 0;
    const s = document.getElementById('mini-stats');
    if (s) {
        s.style.display = 'block';
        document.getElementById('m-stats').innerHTML =
            (compteurs.conduites || 0) + ' tronçons, ' +
            (compteurs.regards || 0) + ' regards, ' +
            (compteurs.stations || 0) + ' stations, ' +
            (compteurs.step || 0) + ' STEP, ' +
            (compteurs.ouvrages || 0) + ' ouvrages';
    }
}

function majSelectClusters(couches) {
    // Remplit la liste déroulante (ex: "Canalisations", "Regards", etc.)
    const sel = document.getElementById('sel-cluster');
    if (!sel) return;
    sel.innerHTML = '<option value="">-- Choisir --</option>';
    Object.keys(couches).forEach((key, idx) => {
        const opt = document.createElement('option');
        opt.value = idx;
        opt.textContent = key.charAt(0).toUpperCase() + key.slice(1) + ' (' + couches[key].features.length + ')';
        sel.appendChild(opt);
    });
}

function selectionnerCluster(idx) {
    // Affiche une couche spécifique (optionnel)
}

function recharger() { window.location.reload(); }
function toast(msg) {
    const t = document.getElementById('toast');
    if (t) {
        t.textContent = msg;
        t.style.display = 'block';
        setTimeout(() => t.style.display = 'none', 3000);
    }
}

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initCarte);
} else {
    initCarte();
}
