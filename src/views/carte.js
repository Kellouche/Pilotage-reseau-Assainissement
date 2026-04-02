const CENTER = [36.7, 3.0];

const COLORS = {
    regards:   "#0066cc",
    rejets:    "#ff0000",
    conduites: "#666666",
    ouvrages:  "#00cc66",
    stations:  "#ffa500",
    step:      "#9933ff"
};

const LABELS = {
    regards:   "Regards",
    rejets:    "Rejets",
    conduites: "Canalisations",
    ouvrages:  "Ouvrages",
    stations:  "Stations",
    step:      "STEP"
};

const DEFAULT_VISIBLE = {
    regards:   true,
    rejets:    true,
    conduites: true,
    ouvrages:  true,
    stations:  true,
    step:      true
};

const MIN_ZOOM_ARROWS = 14;
const MIN_ZOOM_RUES = 13;

let map;
let data       = {};
let mapLayers  = {};
let arrowsLayer  = null;
let ruesLayer    = null;

window.addEventListener("load", () => {
    initMap();
    buildSidebar();
    fetchData();
});

function initMap() {
    map = L.map("map", { center: CENTER, zoom: 12, preferCanvas: true });
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
        attribution: "&copy; OpenStreetMap",
        maxZoom: 19,
        maxNativeZoom: 18
    }).addTo(map);
    map.on("zoomend", updateOverlays);
}

function fetchData() {
    fetch("/get-data")
        .then(r => r.json())
        .then(json => {
            data = json;
            if (data.center) {
                map.setView(data.center, 13);
            }
            updateStats();
            renderMap();
            fitBounds();
        })
        .catch(err => {
            document.getElementById("stats").innerHTML =
                '<div style="color:red;padding:16px;text-align:center">Erreur : ' +
                err.message + "</div>";
        });
}

function buildSidebar() {
    const toggles = document.getElementById("layer-toggles");
    toggles.innerHTML = "";
    for (const key of Object.keys(LABELS)) {
        const checked = DEFAULT_VISIBLE[key] ? "checked" : "";
        toggles.innerHTML +=
            '<label class="checkbox-row">' +
            `<input type="checkbox" id="cb-${key}" ${checked} onchange="renderMap()">` +
            `${LABELS[key]}</label>`;
    }

    const legend = document.getElementById("legend");
    legend.innerHTML = "";
    for (const [key, color] of Object.entries(COLORS)) {
        legend.innerHTML +=
            '<div class="legend-item">' +
            `<div class="legend-dot" style="background:${color}"></div>` +
            `<span>${LABELS[key]}</span></div>`;
    }
}

function updateStats() {
    const grid = document.getElementById("stats");
    grid.innerHTML = "";
    for (const key of Object.keys(LABELS)) {
        const count = data[key]?.features?.length ?? 0;
        grid.innerHTML +=
            '<div class="stat-card">' +
            `<div class="value">${count.toLocaleString()}</div>` +
            `<div class="label">${LABELS[key]}</div></div>`;
    }
}

function popupHtml(title, fields) {
    const lines = fields
        .filter(([, v]) => v != null && v !== "")
        .map(([k, v]) => "<b>" + k + " :</b> " + v)
        .join("<br>");
    return "<strong>" + title + "</strong><br>" + (lines || "Aucune donnée");
}

function regardPopup(props) {
    return popupHtml("Regards", [
        ["Code", props.Code],
        ["Rue", props.NOMVOIE],
        ["Commune", props.COMMUNE],
        ["Profondeur", props.Profondeur],
        ["Diametre", props.DIAMETRES],
        ["Type", props.TYPERES],
    ]);
}

function conduitPopup(props) {
    return popupHtml("Canalisation", [
        ["Rue", props["NOM-VOIE"]],
        ["Diametre", props.DIAMETRE],
        ["Materiau", props.MATERIAU],
        ["Longueur", props.LINEAIRE],
        ["Prof. amont", props.PROF_FE_AM],
        ["Prof. aval", props.PROF_FE_AV],
        ["Fonction", props.FONCTIONMT],
    ]);
}

function rejetPopup(props) {
    return popupHtml("Rejet", [
        ["Nom", props.NOM],
        ["Commune", props.COMMUNE],
        ["Rue", props.NOMVOIE],
    ]);
}

function renderMap() {
    for (const layer of Object.values(mapLayers)) {
        map.removeLayer(layer);
    }
    mapLayers = {};
    if (arrowsLayer) { map.removeLayer(arrowsLayer); arrowsLayer = null; }
    if (ruesLayer) { map.removeLayer(ruesLayer); ruesLayer = null; }

    const show = {};
    for (const key of Object.keys(LABELS)) {
        show[key] = document.getElementById("cb-" + key)?.checked ?? false;
    }

    if (show.conduites && data.conduites) {
        const features = data.conduites.features || [];
        const layers = [];
        for (let i = 0; i < features.length; i++) {
            const feat = features[i];
            const geom = feat.geometry;
            if (!geom) continue;

            let latlngs;
            if (geom.type === "MultiLineString") {
                latlngs = geom.coordinates[0].map(c => [c[1], c[0]]);
            } else if (geom.type === "LineString") {
                latlngs = geom.coordinates.map(c => [c[1], c[0]]);
            } else {
                continue;
            }

            const line = L.polyline(latlngs, {
                color: COLORS.conduites, weight: 2, opacity: 0.6
            });
            line._featProps = feat.properties;
            line.on("click", function () {
                this.bindPopup(conduitPopup(this._featProps)).openPopup();
            });
            layers.push(line);
        }
        const group = L.layerGroup(layers).addTo(map);
        mapLayers.conduites = group;
    }

    const pointConfigs = [
        { key: "regards",  popupFn: regardPopup },
        { key: "rejets",   popupFn: rejetPopup },
        { key: "ouvrages", popupFn: null },
        { key: "stations", popupFn: null },
        { key: "step",     popupFn: null },
    ];

    for (const { key, popupFn } of pointConfigs) {
        if (!show[key] || !data[key]) continue;

        const geojson = data[key];
        const features = geojson.features || [];
        const color = COLORS[key];
        const label = LABELS[key];
        const layers = [];

        for (let i = 0; i < features.length; i++) {
            const feat = features[i];
            const coords = feat.geometry?.coordinates;
            if (!coords || coords.length < 2) continue;

            const marker = L.circleMarker([coords[1], coords[0]], {
                radius: pointRadius(),
                fillColor: color, color: color,
                weight: 1, opacity: 0.7, fillOpacity: 0.7
            });

            if (popupFn) {
                const props = feat.properties;
                marker._featProps = props;
                marker.on("click", function () {
                    this.bindPopup(popupFn(this._featProps)).openPopup();
                });
            } else {
                const props = feat.properties || {};
                const lines = Object.entries(props)
                    .filter(([, v]) => v != null && v !== "")
                    .map(([k, v]) => "<b>" + k + " :</b> " + v)
                    .join("<br>");
                marker.bindPopup("<strong>" + label + "</strong><br>" + (lines || "Aucune donnee"));
            }

            layers.push(marker);
        }

        const group = L.layerGroup(layers).addTo(map);
        mapLayers[key] = group;
    }

    updateOverlays();
}

function pointRadius() {
    const z = map ? map.getZoom() : 12;
    if (z <= 12) return 2;
    if (z <= 14) return 3;
    if (z <= 16) return 5;
    return 7;
}

function updatePointSizes() {
    const r = pointRadius();
    for (const key of ["regards", "rejets", "ouvrages", "stations", "step"]) {
        const group = mapLayers[key];
        if (!group) continue;
        group.eachLayer(marker => {
            if (marker.setRadius) marker.setRadius(r);
        });
    }
}

function buildArrows() {
    const geojson = data.conduites;
    if (!geojson) return null;

    const arrows = [];
    const features = geojson.features || [];
    const step = Math.max(1, Math.floor(features.length / 2000));

    for (let i = 0; i < features.length; i += step) {
        const g = features[i].geometry;
        if (!g) continue;

        let coords;
        if (g.type === "MultiLineString") {
            coords = g.coordinates[0];
        } else if (g.type === "LineString") {
            coords = g.coordinates;
        }
        if (!coords || coords.length < 2) continue;

        const mid = Math.floor(coords.length / 2);
        const p1 = [coords[mid][1], coords[mid][0]];
        const p2 = [coords[Math.min(mid + 1, coords.length - 1)][1],
                     coords[Math.min(mid + 1, coords.length - 1)][0]];
        const angle = Math.atan2(p2[0] - p1[0], p2[1] - p1[1]) * 180 / Math.PI;

        const icon = L.divIcon({
            className: "",
            html: '<div style="color:' + COLORS.conduites + ';font-size:14px;font-weight:bold;transform:rotate(' + (-angle) + 'deg);text-shadow:0 0 2px #fff,0 0 2px #fff;line-height:1">&#9654;</div>',
            iconSize: [14, 14],
            iconAnchor: [7, 7]
        });

        arrows.push(L.marker(p1, { icon: icon, interactive: false }));
    }

    return arrows.length > 0 ? L.layerGroup(arrows) : null;
}

function buildRues() {
    const geojson = data.rues_labels;
    if (!geojson) return null;

    const features = geojson.features || [];
    const markers = [];

    for (let i = 0; i < features.length; i++) {
        const feat = features[i];
        const coords = feat.geometry?.coordinates;
        if (!coords || coords.length < 2) continue;

        const props = feat.properties || {};
        const text = props.nom;
        if (!text) continue;

        const icon = L.divIcon({
            className: "",
            html: '<div style="color:#555;font-size:11px;font-weight:700;text-shadow:1px 1px 2px #fff,-1px -1px 2px #fff,1px -1px 2px #fff,-1px 1px 2px #fff;white-space:nowrap;line-height:1">' + text + '</div>',
            iconSize: [0, 0],
            iconAnchor: [-4, -4]
        });

        markers.push(L.marker([coords[1], coords[0]], { icon: icon, interactive: false }));
    }

    return markers.length > 0 ? L.layerGroup(markers) : null;
}

function updateOverlays() {
    if (!map) return;
    const zoom = map.getZoom();

    updatePointSizes();

    const showArrows = document.getElementById("cb-arrows")?.checked ?? false;
    const showRues = document.getElementById("cb-rues")?.checked ?? false;

    if (showArrows && zoom >= MIN_ZOOM_ARROWS) {
        if (!arrowsLayer) {
            arrowsLayer = buildArrows();
            if (arrowsLayer) arrowsLayer.addTo(map);
        } else if (!map.hasLayer(arrowsLayer)) {
            arrowsLayer.addTo(map);
        }
    } else if (arrowsLayer && map.hasLayer(arrowsLayer)) {
        map.removeLayer(arrowsLayer);
    }

    if (showRues && zoom >= MIN_ZOOM_RUES) {
        if (!ruesLayer) {
            ruesLayer = buildRues();
            if (ruesLayer) ruesLayer.addTo(map);
        } else if (!map.hasLayer(ruesLayer)) {
            ruesLayer.addTo(map);
        }
    } else if (ruesLayer && map.hasLayer(ruesLayer)) {
        map.removeLayer(ruesLayer);
    }
}

function fitBounds() {
    let bounds = null;
    for (const layer of Object.values(mapLayers)) {
        try {
            const b = layer.getBounds();
            if (b.isValid()) bounds = bounds ? bounds.extend(b) : b;
        } catch (_) {}
    }
    if (bounds?.isValid()) {
        map.fitBounds(bounds, { padding: [50, 50] });
    }
}

function reload() {
    data = {};
    fetch("/get-data?reload=1")
        .then(r => r.json())
        .then(json => { data = json; updateStats(); renderMap(); fitBounds(); });
}
