
// UI Variables
let measureMode = false;
let measurePoints = [];
let measureLine = null;
let measureMarker = null;
let anomaliesMode = false;

function toggleSidebar() {
    const sidebar = document.getElementById('sidebar');
    if (sidebar) sidebar.classList.toggle('collapsed');
}

function centerOnData() {
    const layers = [regardsLayer, conduitesLayer, rejetsLayer, stationsLayer, ouvragesLayer].filter(l => l && map.hasLayer(l));
    if (layers.length === 0) return;
    
    const bounds = L.latLngBounds([]);
    layers.forEach(layer => {
        if (layer.getBounds) bounds.extend(layer.getBounds());
        else layer.eachLayer(m => bounds.extend(m.getLatLng ? m.getLatLng() : m.getBounds()));
    });
    
    if (bounds.isValid()) map.fitBounds(bounds, { padding: [20, 20] });
}

function updateLegendForZoom() {
    const zoom = map.getZoom();
    const shouldShowRegards = zoom >= 14;
    const shouldShowConduites = zoom >= 12;
    
    if (regardsLayer) {
        if (shouldShowRegards) { if (!map.hasLayer(regardsLayer)) map.addLayer(regardsLayer); }
        else { if (map.hasLayer(regardsLayer)) map.removeLayer(regardsLayer); }
    }
    // ... logic for other layers if needed ...
}

function updateSymbolSizes() {
    const zoom = map.getZoom();
    const radius = Math.max(2, Math.min(6, zoom - 10));
    if (regardsLayer) regardsLayer.eachLayer(m => m.setRadius ? m.setRadius(radius) : null);
}

function switchTab(tabId) {
    currentTab = tabId;
    document.querySelectorAll('.tab-btn').forEach(btn => btn.classList.toggle('active', btn.dataset.tab === tabId));
    document.querySelectorAll('.tab-content').forEach(content => content.classList.toggle('active', content.id === `tab-${tabId}`));
    updateTabDisplay();
    calculateTabStats(tabId);
}

function createPopupContent(props, type) {
    let html = `<div class="popup-content"><div class="popup-title">${type.toUpperCase()}</div>`;
    for (const [k, v] of Object.entries(props)) {
        if (v !== null && v !== undefined) html += `<div class="popup-info"><strong>${k}:</strong> ${v}</div>`;
    }
    html += '</div>';
    return html;
}

function createAnomaliePopup(anomalie) {
    const color = getAnomalieColor(anomalie.severite);
    return `
        <div class="popup-content">
            <div class="popup-title" style="color: ${color}">${getAnomalieTitre(anomalie)}</div>
            <div class="popup-info">${getAnomalieDescription(anomalie)}</div>
            <div class="popup-info"><strong>Sévérité:</strong> ${anomalie.severite}</div>
            <div class="popup-actions">
                <button class="popup-btn primary" onclick="corrigerAnomalie('${anomalie.type}')">Corriger</button>
            </div>
        </div>
    `;
}

function selectFeature(props, type) {
    console.log('Selected feature:', type, props);
}

function selectAnomalie(anomalie) {
    selectedAnomalie = anomalie;
    console.log('Selected anomalie:', anomalie);
}

function deselectAnomalie() {
    selectedAnomalie = null;
}

function updateLayersVisibility() {
    updateLegendForZoom();
}

function toggleAnalysisMode() {
    const analysisMode = document.getElementById('analysis-mode')?.checked;
    console.log('Analysis mode:', analysisMode);
    updateLayersVisibility();
}

// Event Listeners
document.addEventListener('change', function(e) {
    if (e.target.classList.contains('filter-checkbox') || e.target.id === 'analysis-mode') {
        if (typeof updateLayersVisibility === 'function') updateLayersVisibility();
        if (typeof updateAnomaliesLayers === 'function') updateAnomaliesLayers();
    }
});

// Mock functions for missing logic
function corrigerAnomalie(type) { showNotification(`Correction pour ${type} non implémentée`, 'warning'); }
function toggleFullscreen() { 
    if (!document.fullscreenElement) {
        document.documentElement.requestFullscreen();
    } else {
        if (document.exitFullscreen) document.exitFullscreen();
    }
}
function toggleAdvancedOptions() {
    const el = document.getElementById('advanced-options');
    if (el) el.style.display = el.style.display === 'none' ? 'block' : 'none';
}
function zoomOnTabAnomalies(tab) {
    if (typeof switchTab === 'function') switchTab(tab);
    if (typeof zoomToVisibleAnomalies === 'function') zoomToVisibleAnomalies();
}
function exportVisibleData() {
    showNotification("L'exportation des données sera bientôt disponible.", 'info');
}
