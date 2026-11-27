/**
 * ================================================================================
 * Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
 * Auteur : Dr Abdelhakim KELLOUCHE
 * Date de création : 2026-04-20
 * Date de modification : 2026-11-27
 * Objet : Gestionnaire des éléments d'interface utilisateur, panneaux latéraux et menus
 * ================================================================================
 */

// UI Variables
let measureMode = false;
let currentCorrectionFid = null;
let currentSuggestionPayload = null;
let measurePoints = [];
let measureLine = null;
let measureMarker = null;
let anomaliesMode = false;

// Switch sidebar tabs (Recherche vs Diagnostic)
function switchSidebarTab(tabId) {
    document.querySelectorAll('[id^="sidebar-content-"]').forEach(el => {
        el.classList.toggle('active', el.id === `sidebar-content-${tabId}`);
    });
    document.querySelectorAll('[id^="sidebar-tab-"]').forEach(btn => {
        btn.classList.toggle('active', btn.id === `sidebar-tab-${tabId}`);
    });
}

function updateSymbolSizes() {
    const zoom = map.getZoom();
    const radius = Math.max(2, Math.min(6, zoom - 10));
    if (regardsLayer) regardsLayer.eachLayer(m => m.setRadius ? m.setRadius(radius) : null);
}

function toggleSidebar() {
    const sidebar = document.getElementById('sidebar');
    const toggleBtn = document.querySelector('.sidebar-toggle');
    if (!sidebar) return;

    sidebar.classList.toggle('collapsed');

    if (sidebar.classList.contains('collapsed')) {
        if (toggleBtn) toggleBtn.textContent = '▶';
    } else {
        if (toggleBtn) toggleBtn.textContent = '◀';
    }

    // Indispensable pour que Leaflet recalcule la taille du conteneur après l'animation/changement
    setTimeout(() => {
        if (typeof map !== 'undefined' && map) {
            map.invalidateSize();
        }
    }, 300);
}

function switchTab(tabId, isInitial = false) {
    if (!diagnosticsLoaded) {
        if (isInitial) {
            currentTab = tabId;
            document.querySelectorAll('.tab-btn').forEach(btn => {
                btn.classList.toggle('active', btn.id === `tab-${tabId}`);
            });
            document.querySelectorAll('.tab-content').forEach(content => {
                content.classList.toggle('active', content.id === `content-${tabId}`);
            });
            return;
        }
        if (typeof lancerDiagnostic === 'function') {
            lancerDiagnostic(tabId);
        }
        return;
    }
    switchTabReal(tabId);
}

function switchTabReal(tabId) {
    console.log('Switching to tab:', tabId);
    currentTab = tabId;
    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.classList.toggle('active', btn.id === `tab-${tabId}`);
    });
    document.querySelectorAll('.tab-content').forEach(content => {
        content.classList.toggle('active', content.id === `content-${tabId}`);
    });
    updateTabDisplay();
    if (typeof calculateTabStats === 'function') calculateTabStats(tabId);
    if (typeof updateAnomaliesLayers === 'function') updateAnomaliesLayers();
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
    const isGeometrie = anomalie.type === 'geometrie_invalide';
    const isTopologie = anomalie.type === 'conduite_sans_regard' || anomalie.type === 'troncon_orphelin' || anomalie.type === 'incoherence_profondeur' || anomalie.type === 'incoherences_amont_aval';

    const id = anomalie.id || anomalie.fid || anomalie.id_conduite || anomalie.type_element || '';

    const correctionBtn = anomalie.type === 'geometrie_invalide'
        ? `<button class="popup-btn" onclick="openCorrectionModal('${id}', 'geometrie_invalide')">Corriger coords</button>`
        : anomalie.type === 'conduite_sans_regard' || anomalie.type === 'troncon_orphelin' || anomalie.type === 'incoherence_profondeur' || anomalie.type === 'incoherences_amont_aval'
        ? `<button class="popup-btn" onclick="openCorrectionModal('${id}', 'conduite_sans_regard')">Creer connexion</button>`
        : `<button class="popup-btn primary" onclick="openCorrectionModal('${id}', 'pente_negative')">Corriger profil</button>`;

    return `
        <div class="popup-content">
            <div class="popup-title" style="color: ${color}">${getAnomalieTitre(anomalie)}</div>
            <div class="popup-info">${getAnomalieDescription(anomalie)}</div>
            <div class="popup-info"><strong>Severite:</strong> ${anomalie.severite}</div>
            <div class="popup-actions">
                ${correctionBtn}
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
    if (typeof updateAnomaliesLayers === 'function') {
        updateAnomaliesLayers();
    }
}

function toggleAnalysisMode() {
    const analysisMode = document.getElementById('analysis-mode')?.checked;
    console.log('Analysis mode:', analysisMode);
    updateLayersVisibility();
}

// Event Listeners
document.addEventListener('change', function (e) {
    if (e.target.classList.contains('filter-checkbox') || e.target.id === 'analysis-mode') {
        if (typeof updateLayersVisibility === 'function') updateLayersVisibility();
        if (typeof updateAnomaliesLayers === 'function') updateAnomaliesLayers();
    }
});

// Mock functions for missing logic - adaptées par type d'anomalie
function corrigerGeometrie(id) {
    if (typeof openCorrectionModal === 'function') openCorrectionModal(id, 'geometrie_invalide');
}

function corrigerTopologie(id) {
    if (typeof openCorrectionModal === 'function') openCorrectionModal(id, 'conduite_sans_regard');
}

function corrigerAnomalie(type) {
    if (typeof openCorrectionModal === 'function') openCorrectionModal(null, type);
}

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
function exportVisibleData() {
    showNotification("L'exportation des données sera bientôt disponible.", 'info');
}
