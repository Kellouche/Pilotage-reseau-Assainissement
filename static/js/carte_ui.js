
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

// Minimal modal control (ensure modal opens even if other scripts missing)
function openCorrectionModal(id, type) {
    try {
        // Normaliser l'identifiant : accepter les formats "fid|lat,lng" ou simple "fid"
        let fidCandidate = null;
        if (typeof id === 'string' && id.includes('|')) {
            fidCandidate = id.split('|')[0];
        } else {
            fidCandidate = id;
        }
        // Si l'identifiant reste vide ou non résolvable, afficher une erreur claire
        if (!fidCandidate || fidCandidate === 'Inconnu') {
            if (typeof showError === 'function')
                showError('Impossible de corriger : identifiant invalide ou non reconnu.');
            return;
        }
        // Conserver le fid normalisé pour le reste du flux
        id = fidCandidate;

        // Descriptions et solutions pour chaque type de diagnostic
        const diagnosticSolutions = {
            'geometrie_invalide': {
                title: 'Corriger la position',
                description: 'Corrigez les coordonnées XY du point ou du début de la conduite.',
                solution: 'formulaire_coords',
                suggestionTitle: 'Saisie des coordonnées'
            },
            'conduite_sans_regard': {
                title: 'Ajouter une connexion manquante',
                description: 'Cette conduite n\'est pas connectée à un regard. Créez la connexion en indiquant les nœuds amont et aval.',
                solution: 'formulaire_connexion_with_suggestion',
                suggestionTitle: 'Solution de connexion'
            },
            'troncon_orphelin': {
                title: 'Relier le tronçon orphelin',
                description: 'Ce tronçon est isolé du réseau. Connectez-le aux nœuds amont et aval appropriés.',
                solution: 'formulaire_connexion_with_suggestion',
                suggestionTitle: 'Solution de connexion'
            },
            'incoherence_profondeur': {
                title: 'Corriger l\'incohérence de profondeur',
                description: 'Les profondeurs des nœuds amont et aval sont incohérentes. Ajustez le profil de la conduite.',
                solution: 'formulaire_profil_with_profile',
                suggestionTitle: 'Solution hydraulique'
            },
            'incoherences_amont_aval': {
                title: 'Corriger l\'incohérence amont/aval',
                description: 'Les connexions amont/aval sont manquantes ou incorrectes. Corrigez les nœuds.',
                solution: 'formulaire_connexion_with_suggestion',
                suggestionTitle: 'Solution de connexion'
            },
            'pente_negative': {
                title: 'Corriger la pente négative',
                description: 'La pente est négative. Inversez le profil ou corrigez les profondeurs pour obtenir une pente positive.',
                solution: 'formulaire_profil_with_profile',
                suggestionTitle: 'Solution hydraulique'
            },
            'pente_trop_forte': {
                title: 'Corriger la pente excessive',
                description: 'La pente est trop forte (>50%). Ajustez les profondeurs ou la longueur de la conduite.',
                solution: 'formulaire_profil_with_profile',
                suggestionTitle: 'Solution hydraulique'
            },
            'champs_manquants_conduite': {
                title: 'Compléter les données (conduite)',
                description: 'Des champs essentiels manquent. Complétez les informations de la conduite.',
                solution: 'formulaire_profil_simple',
                suggestionTitle: 'Données manquantes'
            },
            'champs_manquants_regard': {
                title: 'Compléter les données (regard)',
                description: 'Des champs essentiels manquent pour ce regard. Complétez les informations.',
                solution: 'formulaire_coords',
                suggestionTitle: 'Données manquantes'
            }
        };

        const solutionConfig = diagnosticSolutions[type] || {
            title: 'Correction d\'anomalie',
            description: 'Corrigez cette anomalie en saisissant les valeurs appropriées.',
            solution: 'formulaire_profil_with_profile',
            suggestionTitle: 'Proposition'
        };

        // Mettre à jour le titre et la description de la modale
        const titleEl = document.getElementById('modal-title-diagnostic');
        if (titleEl) {
            titleEl.textContent = solutionConfig.title;
        }

        // Mettre à jour le titre de la boîte de suggestion
        const suggestionTitleEl = document.getElementById('suggestion-title');
        if (suggestionTitleEl) {
            suggestionTitleEl.textContent = solutionConfig.suggestionTitle;
        }

        // Parse id value: may be "fid|lat,lng" or just fid or coords
        fidCandidate = null;
        coords = null;
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
        if (tgt) {
            tgt.innerHTML = `<strong>Problème :</strong> ${solutionConfig.description}<br><strong>Cible :</strong> ${fidCandidate || (coords ? coords.lat + ',' + coords.lng : id)}`;
        }

        // Afficher/masquer les sections appropriées
        const profile = document.getElementById('profile-container');
        const suggestionBox = document.getElementById('hybrid-suggestion-box');
        const formCoords = document.getElementById('form-coords');
        const formConnexion = document.getElementById('form-connexion');
        const formProfil = document.getElementById('form-profil');
        const btnApply = document.getElementById('btn-apply-correction');

        // Masquer tous les formulaires par défaut
        if (profile) profile.style.display = 'none';
        if (suggestionBox) suggestionBox.style.display = 'none';
        if (formCoords) formCoords.style.display = 'none';
        if (formConnexion) formConnexion.style.display = 'none';
        if (formProfil) formProfil.style.display = 'none';

        // Afficher la solution appropriée selon le type
        switch (solutionConfig.solution) {
            case 'formulaire_coords':
                // Géométrie: afficher formulaire coordonnées uniquement
                if (formCoords) formCoords.style.display = 'block';
                if (btnApply) btnApply.onclick = () => applyGeometrieCorrection();
                break;

            case 'formulaire_connexion_with_suggestion':
                // Connexion: afficher formulaire + suggestion
                if (suggestionBox) suggestionBox.style.display = 'block';
                if (formConnexion) formConnexion.style.display = 'block';
                if (btnApply) btnApply.onclick = () => applyTopologieCorrection();
                break;

            case 'formulaire_profil_with_profile':
                // Profil avec graphique: afficher profil + formulaire profondeur + suggestion
                if (profile) profile.style.display = 'block';
                if (suggestionBox) suggestionBox.style.display = 'block';
                if (formProfil) formProfil.style.display = 'block';
                if (btnApply) btnApply.onclick = () => applyManualCorrection();
                break;

            case 'formulaire_profil_simple':
                // Profil simple: formulaire profondeur sans graphique
                if (formProfil) formProfil.style.display = 'block';
                if (btnApply) btnApply.onclick = () => applyManualCorrection();
                break;

            default:
                // Défaut: formulaire profil complet
                if (profile) profile.style.display = 'block';
                if (formProfil) formProfil.style.display = 'block';
                if (btnApply) btnApply.onclick = () => applyManualCorrection();
        }

        // Mapper les IDs pour les formulaires profil
        if (formProfil) {
            // Déplacer les valeurs vers les nouveaux IDs
            const am = document.getElementById('correction-amont');
            const av = document.getElementById('correction-aval');
            const amProf = document.getElementById('correction-amont-profil');
            const avProf = document.getElementById('correction-aval-profil');
            if (amProf && avProf) {
                amProf.value = am ? am.value : '';
                avProf.value = av ? av.value : '';
            }
        }

        const modal = document.getElementById('correction-modal');
        if (modal) modal.style.display = 'flex';

        const am = document.getElementById('correction-amont'); 
        const av = document.getElementById('correction-aval');
        if (am) am.value = ''; 
        if (av) av.value = '';

        // Try to fetch profile with candidate fid first
        function tryProfile(fidToTry) {
            return fetch(`/api/v1/corrections/profile/${encodeURIComponent(fidToTry)}`)
                .then(res => {
                    if (!res.ok) throw new Error('Not found');
                    return res.json();
                });
        }

        // Charger les données appropriées selon le type de solution
        if (currentCorrectionFid && (solutionConfig.solution === 'formulaire_profil_with_profile' || solutionConfig.solution === 'formulaire_profil_simple')) {
            // Pour les problèmes de profil: charger le profil et la suggestion
            tryProfile(currentCorrectionFid).then(data => {
                // Tracer le profil réel automatiquement
                if (typeof drawCurrentProfile === 'function') {
                    setTimeout(() => drawCurrentProfile(), 100);
                }
                if (typeof fetchHybridSuggestion === 'function') {
                    fetchHybridSuggestion(currentCorrectionFid, type);
                }
            }).catch(err => {
                // Profil non trouvé - afficher un message
                const content = document.getElementById('hybrid-suggestion-content');
                if (content) content.textContent = 'Données topographiques non disponibles. Veuillez saisir les profondeurs manuellement.';
                const box2 = document.getElementById('hybrid-suggestion-box'); 
                if (box2) box2.style.display = 'block';
            });
        } else if (currentCorrectionFid && (solutionConfig.solution === 'formulaire_connexion_with_suggestion')) {
            // Pour les problèmes de connexion: charger la suggestion de connexion
            if (typeof fetchHybridSuggestion === 'function') {
                fetchHybridSuggestion(currentCorrectionFid, type);
            }
        }
        // Pour formulaire_coords: pas de chargement spécifique requis

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

    // Messages adapté selon le type de diagnostic
    const typeMessages = {
        'pente_negative': 'Solution : inverser ou augmenter les profondeurs pour obtenir une pente positive',
        'pente_trop_forte': 'Solution : réduire la différence de profondeur ou augmenter la longueur pour diminuer la pente',
        'incoherence_profondeur': 'Solution : harmoniser les profondeurs des nœuds amont et aval',
        'incoherences_amont_aval': 'Solution : vérifier et corriger les connexions amont/aval',
        'conduite_sans_regard': 'Solution : connecter cette conduite à un nœud (regard/station/ouvrage) amont et aval',
        'troncon_orphelin': 'Solution : intégrer ce tronçon orphelin au réseau en créant les connexions'
    };

    // Call backend suggestion endpoint
    fetch(`/api/v1/corrections/hybride/suggest?fid=${encodeURIComponent(id)}&anomalie_type=${encodeURIComponent(type || '')}`)
        .then(res => res.json())
        .then(data => {
            currentSuggestionPayload = data;
            if (!data || !data.suggestion) {
                content.textContent = typeMessages[type] || 'Veuillez saisir manuellement la correction appropriée.';
                return;
            }

            const s = data.suggestion;
            const typeMsg = typeMessages[type] || 'Solution hydraulique proposée';
            
            // Build detailed suggestion display with metrics
            const cappedNote = (s.capped) ? '<div style="color:#b36b00;font-size:12px;margin-top:6px;">⚠️ Proposition limitée par contraintes hydrauliques (cappée). Vérifier avant application.</div>' : '';
            
            // Adapter le contenu selon le type
            let solutionDisplay = '';
            if (type && (type.includes('pente') || type.includes('profondeur') || type.includes('coherence'))) {
                // Pour les problèmes de profil/pente
                solutionDisplay = `
                    <div style="font-size:13px;color:#2c5aa0;"><strong>💧 Solution hydraulique :</strong></div>
                    <div style="font-size:12px;margin-top:4px;">${typeMsg}</div>
                    <div style="margin-top:8px;font-size:12px;background:#e8f4f8;padding:6px;border-radius:4px;">
                        <strong>Profondeur amont proposée :</strong> ${s.prof_fe_am ? s.prof_fe_am + ' m' : '—'} <br>
                        <strong>Profondeur aval proposée :</strong> ${s.prof_fe_av ? s.prof_fe_av + ' m' : '—'} <br>
                        <strong>Pente résultante :</strong> ${s.pente_pourcent ? s.pente_pourcent.toFixed(2) + ' %' : '—'}
                    </div>
                    <div style="margin-top:6px;font-size:11px;color:#666">Confiance: ${s.confidence || 'indisponible'} — Sources: ${data.suggestion.source_count || 0}</div>
                    ${cappedNote}
                `;
            } else if (type && type.includes('conduite_sans_regard')) {
                // Pour connexion manquante
                solutionDisplay = `
                    <div style="font-size:13px;color:#2c5aa0;"><strong>🔗 Solution de connexion :</strong></div>
                    <div style="font-size:12px;margin-top:4px;">${typeMsg}</div>
                    <div style="margin-top:8px;font-size:12px;background:#e8f4f8;padding:6px;border-radius:4px;">
                        <strong>Nœud amont suggéré :</strong> ${s.noeud_amont || '—'} <br>
                        <strong>Nœud aval suggéré :</strong> ${s.noeud_aval || '—'} <br>
                        <strong>Type de nœud :</strong> ${s.type_noeud || 'regard'}
                    </div>
                    <div style="margin-top:6px;font-size:11px;color:#666">Confiance: ${s.confidence || 'indisponible'}</div>
                `;
            } else {
                // Affichage par défaut
                solutionDisplay = `
                    <div style="font-size:13px;">${s.message || 'Proposition'}</div>
                    <div style="margin-top:6px;font-size:13px;"><strong>Pente proposée:</strong> ${s.pente_pourcent ? s.pente_pourcent + ' %' : '—'}</div>
                    <div style="margin-top:4px;font-size:13px;"><strong>Amont / Aval proposés:</strong> ${s.prof_fe_am || '—'} / ${s.prof_fe_av || '—'}</div>
                    <div style="margin-top:6px;font-size:12px;color:#666">Confiance: ${s.confidence || 'indisponible'} — Sources: ${data.suggestion.source_count || 0}</div>
                    ${cappedNote}
                `;
            }

            content.innerHTML = solutionDisplay;

            // Fill inputs if suggestion available
            if (s.available) {
                const am = document.getElementById('correction-amont-profil');
                const av = document.getElementById('correction-aval-profil');
                if (am && av) {
                    if (s.prof_fe_am) am.value = s.prof_fe_am;
                    if (s.prof_fe_av) av.value = s.prof_fe_av;
                }
            }

            // Tracer automatiquement le profil (réel + proposé) quand la suggestion est chargée
            if (typeof drawCurrentProfile === 'function') {
                setTimeout(() => drawCurrentProfile(), 200);
            }
        })
        .catch(e => {
            console.warn('fetchHybridSuggestion error', e);
            content.textContent = typeMessages[type] || 'Veuillez saisir manuellement la correction appropriée.';
        });
}

function drawCurrentProfile() {
    if (!currentCorrectionFid) { showNotification('Aucune conduite sélectionnée.', 'warning'); return; }
    const profileBox = document.getElementById('profile-container');
    if (!profileBox) return;
    profileBox.style.display = 'block';

    // Récupérer d'abord le profil réel, puis ajouter la suggestion si disponible
    Promise.all([
        fetch(`/api/v1/corrections/profile/${encodeURIComponent(currentCorrectionFid)}`).then(res => {
            if (!res.ok) throw new Error('profile-not-found');
            return res.json();
        }),
        // Si la suggestion n'est pas déjà en cache, la récupérer maintenant
        (currentSuggestionPayload && currentSuggestionPayload.suggestion && currentSuggestionPayload.suggestion.available)
            ? Promise.resolve(currentSuggestionPayload)
            : fetch(`/api/v1/corrections/hybride/suggest?fid=${encodeURIComponent(currentCorrectionFid)}&anomalie_type=conduite`).then(res => res.json()).catch(() => null)
    ]).then(([profileData, suggestionData]) => {
        // Draw simple linear profile on canvas using actuelle and suggestion if any
        const canvas = document.getElementById('profile-canvas');
        if (!canvas) return;
        const ctx = canvas.getContext('2d');
        const w = canvas.width, h = canvas.height;
        ctx.clearRect(0, 0, w, h);

        // baseline
        ctx.fillStyle = '#fff'; ctx.fillRect(0, 0, w, h);
        ctx.strokeStyle = '#ccc'; ctx.strokeRect(0, 0, w, h);

        const marge = 30;
        const usableW = w - marge * 2; const usableH = h - marge * 2;

        const actuel = profileData.actuel || {};
        const sugg = (suggestionData && suggestionData.suggestion && suggestionData.suggestion.available)
            ? suggestionData.suggestion : null;

        // Determine depths: use prof_fe_am (upstream elevation) and prof_fe_av
        const am = actuel.prof_fe_am; const av = actuel.prof_fe_av;
        const sam = sugg ? sugg.prof_fe_am : null; const sav = sugg ? sugg.prof_fe_av : null;

        // Fallback if null -> set flat zero baseline
        const vals = [am, av, sam, sav].filter(v => v !== null && v !== undefined);
        if (vals.length === 0) {
            ctx.fillStyle = '#999'; ctx.fillText('Pas de cotes disponibles pour ce tronçon', marge, h / 2);
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
            ctx.strokeStyle = '#2e7d32'; ctx.lineWidth = 3; ctx.setLineDash([6, 4]); ctx.stroke(); ctx.setLineDash([]);
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
    // Si une suggestion automatique est disponible, l'appliquer d'office
    if (currentSuggestionPayload && currentSuggestionPayload.suggestion && currentSuggestionPayload.suggestion.available) {
        const s = currentSuggestionPayload.suggestion;
        // Confirmation si la suggestion a été limitée par contraintes hydrauliques
        if (s.capped) {
            const ok = confirm('La proposition a été limitée pour respecter des contraintes hydrauliques (cappée). Confirmez-vous l\'application ?');
            if (!ok) return;
        }
        fetch(`/api/v1/corrections/manuel/${encodeURIComponent(currentCorrectionFid)}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ prof_fe_am: s.prof_fe_am, prof_fe_av: s.prof_fe_av })
        }).then(res => res.json())
            .then(r => {
                showNotification(r.message || 'Suggestion appliquée', 'success');
                closeCorrectionModal();
                if (typeof chargerDonnees === 'function') chargerDonnees();
            }).catch(e => {
                console.warn('applyManualCorrection (suggestion) error', e);
                showNotification('Erreur lors de l\'application de la suggestion', 'error');
            });
        return;
    }

    // Sinon : appliquer la saisie manuelle
    const amont = document.getElementById('correction-amont-profil');
    const aval = document.getElementById('correction-aval-profil');
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
document.addEventListener('change', function (e) {
    try {
        if (!e.target || !e.target.id) return;
        if (e.target.id.startsWith('select-anomalies-')) {
            const val = e.target.value;
            if (!val) return;
            const optSelected = e.target.options?.[e.target.selectedIndex];
            const anomType = optSelected?.dataset?.anomalieType || 'conduite';
            if (typeof openCorrectionModal === 'function') {
                setTimeout(() => openCorrectionModal(val, anomType), 300);
            }
        }
    } catch (err) { console.warn('select change handler error', err); }
});

// Correction géométrie (coordonnées GPS)
function applyGeometrieCorrection() {
    const lat = document.getElementById('correction-lat');
    const lng = document.getElementById('correction-lng');
    if (!lat || !lng || !currentCorrectionFid) return;

    const payload = {
        latitude: parseFloat(lat.value),
        longitude: parseFloat(lng.value)
    };
    fetch(`/api/v1/corrections/coords/${encodeURIComponent(currentCorrectionFid)}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
    }).then(res => res.json())
        .then(r => {
            showNotification(r.message || 'Coordonnées corrigées', 'success');
            closeCorrectionModal();
            if (typeof chargerDonnees === 'function') chargerDonnees();
        }).catch(e => {
            showNotification('Erreur correction coords', 'error');
        });
}

// Correction topologie (connexion amont/aval)
function applyTopologieCorrection() {
    const am = document.getElementById('correction-amont');
    const av = document.getElementById('correction-aval');
    if (!am || !av || !currentCorrectionFid) return;

    const payload = {
        noeud_amont: am.value,
        noeud_aval: av.value
    };
    fetch(`/api/v1/corrections/connexion/${encodeURIComponent(currentCorrectionFid)}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
    }).then(res => res.json())
        .then(r => {
            showNotification(r.message || 'Connexion corrigée', 'success');
            closeCorrectionModal();
            if (typeof chargerDonnees === 'function') chargerDonnees();
        }).catch(e => {
            showNotification('Erreur correction topologie', 'error');
        });
}

