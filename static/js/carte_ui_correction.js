/**
 * ================================================================================
 * Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
 * Auteur : Dr Abdelhakim KELLOUCHE
 * Date de création : 2026-04-20
 * Date de modification : 2026-11-27
 * Objet : Corrections manuelles et profil altimétrique de la conduite sélectionnée
 * ================================================================================
 */

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
