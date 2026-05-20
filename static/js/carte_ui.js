
// UI Variables
let measureMode = false;
let currentCorrectionFid = null;
let currentSuggestionPayload = null;
let measurePoints = [];
let measureLine = null;
let measureMarker = null;
let anomaliesMode = false;

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

function zoomOnTabAnomalies(tabId) {
    if (typeof zoomToVisibleAnomalies === 'function') {
        zoomToVisibleAnomalies();
    }
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

// Minimal modal control (ensure modal opens even if other scripts missing)
function openCorrectionModal(id, type) {
    try {
        if (!id || id === 'Inconnu') {
            if (typeof showError === 'function') showError('Impossible de corriger : identifiant invalide.');
            return;
        }

        // Parse id value: may be "fid|lat,lng" or just fid or coords
        let fidCandidate = null;
        let coords = null;
        if (typeof id === 'string' && id.includes('|')) {
            const parts = id.split('|');
            fidCandidate = parts[0];
            const c = parts[1].split(',').map(Number);
            if (c.length === 2 && !isNaN(c[0]) && !isNaN(c[1])) coords = { lat: c[0], lng: c[1] };
        } else if (typeof id === 'string' && id.includes(',')) {
            const c = id.split(',').map(Number);
            if (c.length === 2 && !isNaN(c[0]) && !isNaN(c[1])) coords = { lat: c[0], lng: c[1] };
        } else {
            fidCandidate = id;
        }

        currentCorrectionFid = fidCandidate || null;

        const tgt = document.getElementById('correction-target-id');
        if (tgt) tgt.textContent = `Cible : ${fidCandidate || (coords ? coords.lat + ',' + coords.lng : id)} (${type || 'conduite'})`;
        const modal = document.getElementById('correction-modal');
        if (modal) modal.style.display = 'flex';
        const box = document.getElementById('hybrid-suggestion-box'); if (box) box.style.display = 'none';
        const profile = document.getElementById('profile-container'); if (profile) profile.style.display = 'none';
        const am = document.getElementById('correction-amont'); const av = document.getElementById('correction-aval');
        if (am) am.value = ''; if (av) av.value = '';

        // Try to fetch profile with candidate fid first
        function tryProfile(fidToTry) {
            return fetch(`/api/v1/corrections/profile/${encodeURIComponent(fidToTry)}`)
                .then(res => {
                    if (!res.ok) throw new Error('Not found');
                    return res.json();
                });
        }

        if (currentCorrectionFid) {
            tryProfile(currentCorrectionFid).then(data => {
                // successful: show suggestion box and allow tracing
                if (typeof fetchHybridSuggestion === 'function') {
                    // fetchHybridSuggestion will call suggestion endpoint too
                    fetchHybridSuggestion(currentCorrectionFid, type);
                }
            }).catch(err => {
                // profile not found for fidCandidate, try fallback with coords
                if (coords && typeof findConduiteByCoords === 'function') {
                    const found = findConduiteByCoords(coords.lat, coords.lng);
                    if (found) {
                        currentCorrectionFid = found;
                        if (typeof fetchHybridSuggestion === 'function') fetchHybridSuggestion(currentCorrectionFid, type);
                    } else {
                        const content = document.getElementById('hybrid-suggestion-content');
                        if (content) content.textContent = 'Aucune donnée topo disponible pour cette conduite. Saisir manuellement.';
                        const box2 = document.getElementById('hybrid-suggestion-box'); if (box2) box2.style.display = 'block';
                    }
                } else {
                    const content = document.getElementById('hybrid-suggestion-content');
                    if (content) content.textContent = 'Aucune donnée topo disponible pour cette conduite. Saisir manuellement.';
                    const box2 = document.getElementById('hybrid-suggestion-box'); if (box2) box2.style.display = 'block';
                }
            });
        } else if (coords && typeof findConduiteByCoords === 'function') {
            const found = findConduiteByCoords(coords.lat, coords.lng);
            if (found) {
                currentCorrectionFid = found;
                if (typeof fetchHybridSuggestion === 'function') fetchHybridSuggestion(currentCorrectionFid, type);
            } else {
                const content = document.getElementById('hybrid-suggestion-content');
                if (content) content.textContent = 'Aucune donnée topo disponible pour cette conduite. Saisir manuellement.';
                const box2 = document.getElementById('hybrid-suggestion-box'); if (box2) box2.style.display = 'block';
            }
        } else {
            // No fid and no coords: show fallback message
            const content = document.getElementById('hybrid-suggestion-content');
            if (content) content.textContent = 'Aucune donnée topo disponible pour cette conduite. Saisir manuellement.';
            const box2 = document.getElementById('hybrid-suggestion-box'); if (box2) box2.style.display = 'block';
        }

    } catch (e) { console.warn('openCorrectionModal error', e); }
}

function closeCorrectionModal() {
    const modal = document.getElementById('correction-modal');
    if (modal) modal.style.display = 'none';
}

// Stub functions for modal correction flow
function fetchHybridSuggestion(id, type) {
    const box = document.getElementById('hybrid-suggestion-box');
    const content = document.getElementById('hybrid-suggestion-content');
    if (!box || !content) return;
    box.style.display = 'block';
    content.textContent = 'Analyse en cours...';

    currentCorrectionFid = id;
    currentSuggestionPayload = null;

    // Call backend suggestion endpoint
    fetch(`/api/v1/corrections/hybride/suggest?fid=${encodeURIComponent(id)}&anomalie_type=${encodeURIComponent(type || '')}`)
        .then(res => res.json())
        .then(data => {
            currentSuggestionPayload = data;
            if (!data || !data.suggestion) {
                content.textContent = 'Aucune suggestion disponible.';
                return;
            }

            const s = data.suggestion;
            // Build detailed suggestion display with metrics
            const cappedNote = (s.capped) ? '<div style="color:#b36b00;font-size:12px;margin-top:6px;">⚠️ Proposition limitée par contraintes hydraulique (cappée). Vérifier avant application.</div>' : '';
            content.innerHTML = `
                <div style="font-size:13px;">${s.message || 'Proposition'}</div>
                <div style="margin-top:6px;font-size:13px;"><strong>Pente proposée:</strong> ${s.pente_pourcent ? s.pente_pourcent + ' %' : '—'}</div>
                <div style="margin-top:4px;font-size:13px;"><strong>Amont / Aval proposés:</strong> ${s.prof_fe_am || '—'} / ${s.prof_fe_av || '—'}</div>
                <div style="margin-top:6px;font-size:12px;color:#666">Confiance: ${s.confidence || 'indisponible'} — Sources: ${data.suggestion.source_count || 0}</div>
                ${cappedNote}
                <div style="margin-top:6px;font-size:11px;color:#666">Détails: S_req=${data.suggestion.s_req || '—'}, final_S=${data.suggestion.final_S || '—'}, V_final=${data.suggestion.V_final || '—'}, n=${data.suggestion.n_manning || '—'}</div>
            `;

            // Fill inputs if suggestion available
            if (s.available) {
                const am = document.getElementById('correction-amont');
                const av = document.getElementById('correction-aval');
                if (am && av) {
                    if (s.prof_fe_am) am.value = s.prof_fe_am;
                    if (s.prof_fe_av) av.value = s.prof_fe_av;
                }
            }
        })
        .catch(e => {
            console.warn('fetchHybridSuggestion error', e);
            content.textContent = 'Erreur lors de la récupération de la suggestion.';
        });
}

function drawCurrentProfile() {
    if (!currentCorrectionFid) { showNotification('Aucune conduite sélectionnée.', 'warning'); return; }
    const profileBox = document.getElementById('profile-container');
    if (!profileBox) return;
    profileBox.style.display = 'block';

    fetch(`/api/v1/corrections/profile/${encodeURIComponent(currentCorrectionFid)}`)
        .then(res => {
            if (!res.ok) throw new Error('profile-not-found');
            return res.json();
        })
        .then(data => {
            // Draw simple linear profile on canvas using actuelle and suggestion if any
            const canvas = document.getElementById('profile-canvas');
            if (!canvas) return;
            const ctx = canvas.getContext('2d');
            const w = canvas.width, h = canvas.height;
            ctx.clearRect(0,0,w,h);

            // baseline
            ctx.fillStyle = '#fff'; ctx.fillRect(0,0,w,h);
            ctx.strokeStyle = '#ccc'; ctx.strokeRect(0,0,w,h);

            const marge = 30;
            const usableW = w - marge*2; const usableH = h - marge*2;

            const actuel = data.actuel || {};
            const sugg = (data.suggestion && data.suggestion.available) ? data.suggestion : null;

            // Determine depths: use prof_fe_am (upstream elevation) and prof_fe_av
            const am = actuel.prof_fe_am; const av = actuel.prof_fe_av;
            const sam = sugg ? sugg.prof_fe_am : null; const sav = sugg ? sugg.prof_fe_av : null;

            // Fallback if null -> set flat zero baseline
            const vals = [am, av, sam, sav].filter(v => v !== null && v !== undefined);
            if (vals.length === 0) {
                ctx.fillStyle = '#999'; ctx.fillText('Pas de cotes disponibles pour ce tronçon', marge, h/2);
                return;
            }

            const minV = Math.min(...vals); const maxV = Math.max(...vals);
            const range = Math.max(1e-3, maxV - minV);

            function yFromProf(p) { return marge + ((maxV - p) / range) * usableH; }
            // Points: left = am, right = av
            const x1 = marge, x2 = marge + usableW;

            // Draw actuelle profile
            if (am !== null && av !== null) {
                ctx.beginPath(); ctx.moveTo(x1, yFromProf(am)); ctx.lineTo(x2, yFromProf(av));
                ctx.strokeStyle = '#ff5722'; ctx.lineWidth = 3; ctx.stroke();
                // labels
                ctx.fillStyle = '#000'; ctx.font = '12px Arial';
                ctx.fillText(`AM: ${am}`, x1 + 4, yFromProf(am) - 6);
                ctx.fillText(`AV: ${av}`, x2 - 40, yFromProf(av) - 6);
            }

            // Draw suggestion profile if present
            if (sugg && sugg.prof_fe_am !== null && sugg.prof_fe_av !== null) {
                ctx.beginPath(); ctx.moveTo(x1, yFromProf(sugg.prof_fe_am)); ctx.lineTo(x2, yFromProf(sugg.prof_fe_av));
                ctx.strokeStyle = '#2e7d32'; ctx.lineWidth = 3; ctx.setLineDash([6,4]); ctx.stroke(); ctx.setLineDash([]);
                ctx.fillStyle = '#2e7d32'; ctx.fillText(`Sugg AM: ${sugg.prof_fe_am}`, x1 + 4, yFromProf(sugg.prof_fe_am) - 6);
                ctx.fillText(`Sugg AV: ${sugg.prof_fe_av}`, x2 - 70, yFromProf(sugg.prof_fe_av) - 6);
            }

            // Legend
            const legend = document.getElementById('profile-legend');
            if (legend) {
                legend.innerHTML = `<span style="color:#ff5722">— Profil actuel</span> &nbsp; <span style="color:#2e7d32">— Suggestion</span>`;
            }
        }).catch(e => {
            console.warn('drawCurrentProfile error', e);
            showNotification('Impossible de récupérer le profil', 'error');
        });
}

function applyHybridSuggestion() {
    if (!currentSuggestionPayload || !currentCorrectionFid) {
        showNotification('Pas de suggestion disponible à appliquer.', 'warning');
        return;
    }

    const s = currentSuggestionPayload.suggestion;
    if (!s || !s.available) {
        showNotification('Suggestion non applicable.', 'warning');
        return;
    }

    // Require explicit confirmation if capped
    if (s.capped) {
        const ok = confirm('La proposition a été limitée pour respecter des contraintes hydrauliques. Confirmez-vous l\'application ?');
        if (!ok) return;
    }

    // Call manual correction endpoint to apply suggestion
    fetch(`/api/v1/corrections/manuel/${encodeURIComponent(currentCorrectionFid)}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ prof_fe_am: s.prof_fe_am, prof_fe_av: s.prof_fe_av })
    }).then(res => res.json())
      .then(r => {
        showNotification(r.message || 'Suggestion appliquée', 'success');
        closeCorrectionModal();
        // Refresh anomalies / layers
        if (typeof chargerDonnees === 'function') chargerDonnees();
      }).catch(e => {
        console.warn('applyHybridSuggestion error', e);
        showNotification('Erreur lors de l\'application de la suggestion', 'error');
      });
}

function applyManualCorrection() {
    const amont = document.getElementById('correction-amont');
    const aval = document.getElementById('correction-aval');
    if (!amont || !aval || !currentCorrectionFid) return;

    const payload = { prof_fe_am: (amont.value !== '') ? parseFloat(amont.value) : null, prof_fe_av: (aval.value !== '') ? parseFloat(aval.value) : null };
    fetch(`/api/v1/corrections/manuel/${encodeURIComponent(currentCorrectionFid)}`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload)
    }).then(res => res.json())
      .then(r => {
        showNotification(r.message || 'Correction appliquée', 'success');
        closeCorrectionModal();
        if (typeof chargerDonnees === 'function') chargerDonnees();
      }).catch(e => {
        console.warn('applyManualCorrection error', e);
        showNotification('Erreur lors de l\'application de la correction', 'error');
      });
}

// Ensure dropdown selection opens modal when an id is present
document.addEventListener('change', function(e) {
    try {
        if (!e.target || !e.target.id) return;
        if (e.target.id.startsWith('select-anomalies-')) {
            const val = e.target.value;
            if (!val) return;
            if (typeof openCorrectionModal === 'function') {
                // open modal after zoom (small delay) and pass full value (may contain coords)
                setTimeout(() => openCorrectionModal(val, 'conduite'), 300);
            }
        }
    } catch (err) { console.warn('select change handler error', err); }
});

