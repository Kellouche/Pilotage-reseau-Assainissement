/**
 * ================================================================================
 * Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
 * Auteur : Dr Abdelhakim KELLOUCHE
 * Date de création : 2026-11-24
 * Date de modification : 2026-11-24
 * Objet : Rendu graphique Chart.js du profil en long hydraulique (afficherProfilLong) — extrait de profil_long.js (découpage 600 lignes)
 * ================================================================================
 */

/**
 * Rendu graphique Chart.js et mise à jour de l'interface
 */
function afficherProfilLong(data) {
    if (!data || !data.segments || data.segments.length === 0) return;

    // Un nouveau profil remplace toute couche d'anomalies
    _retirerAnomaliesProfil();

    // 1. Badges d'en-tête
    const bTroncons = document.getElementById('badge-profil-troncons');
    const bLongueur = document.getElementById('badge-profil-longueur');
    const bSurcharges = document.getElementById('badge-profil-surcharges');

    if (bTroncons) {
        bTroncons.textContent = `${data.nb_troncons} tronçons`;
        bTroncons.style.display = 'inline-block';
    }
    if (bLongueur) {
        bLongueur.textContent = `${data.longueur_totale_m} m`;
        bLongueur.style.display = 'inline-block';
    }
    if (bSurcharges) {
        bSurcharges.textContent = `${data.conduites_en_charge} conduite${data.conduites_en_charge > 1 ? 's' : ''} en charge`;
        bSurcharges.style.display = data.conduites_en_charge > 0 ? 'inline-block' : 'none';
    }

    // 1a. Badge de provenance altimétrique : le profil déclare si les cotes
    // radier proviennent du SIG réel, du terrain interpolé (IDW) ou d'un
    // modèle synthétique — critique pour interpréter les écarts radier/terrain.
    const bAlt = document.getElementById('badge-profil-altimetrie');
    if (bAlt) {
        const alt = data.altimetrie || null;
        if (alt && alt.mode && alt.mode !== 'indisponible') {
            const _conf = {
                sig_reel:     { bg: 'rgba(52,211,153,0.18)',  color: '#34d399', icone: 'fa-check-double' },
                terrain_idw:  { bg: 'rgba(251,191,36,0.18)',  color: '#fbbf24', icone: 'fa-mountain' },
                synthetique:  { bg: 'rgba(248,113,113,0.20)', color: '#f87171', icone: 'fa-exclamation-triangle' },
            }[alt.mode] || { bg: 'rgba(148,163,184,0.18)', color: '#94a3b8', icone: 'fa-info-circle' };
            let _txt = alt.label || 'Altimétrie';
            if (alt.ecart_radier_terrain_med_m != null && alt.mode === 'synthetique') {
                _txt += ` — écart ~${alt.ecart_radier_terrain_med_m} m`;
            }
            bAlt.innerHTML = `<i class="fas ${_conf.icone}"></i> ${_txt}`;
            bAlt.style.display = 'inline-block';
            bAlt.style.background = _conf.bg;
            bAlt.style.color = _conf.color;
            bAlt.style.border = `1px solid ${_conf.color}`;
            bAlt.title = (alt.avertissement || '') +
                (alt.source ? `\nSource : ${alt.source}` : '') +
                (alt.ecart_radier_terrain_max_m != null
                    ? `\nÉcart radier↔terrain : médiane ${alt.ecart_radier_terrain_med_m} m, max ${alt.ecart_radier_terrain_max_m} m`
                    : '');
        } else {
            bAlt.style.display = 'none';
        }
    }

    // 1b. Bandeau fiabilité du modèle sous-jacent (garde-fou hydraulicien)
    const _fiabBanner = document.getElementById('profil-fiabilite-banner');
    const _fiabTexte = document.getElementById('profil-fiabilite-texte');
    if (_fiabBanner && _fiabTexte) {
        const _verdict = data.fiabilite_modele;
        const _anomalies = data.modelisation_anomalies || [];
        const _meta = {
            'A_VERIFIER': { icon: 'fas fa-shield-alt', label: 'à vérifier', color: '#fbbf24', bg: 'rgba(251,191,36,0.12)' },
            'DEGRADE':    { icon: 'fas fa-shield-alt', label: 'dégradé',    color: '#f87171', bg: 'rgba(248,113,113,0.12)' },
        }[_verdict];
        if (_meta) {
            _fiabBanner.style.display = 'flex';
            _fiabBanner.style.color = _meta.color;
            _fiabBanner.style.background = _meta.bg;
            _fiabBanner.innerHTML = `<i class="${_meta.icon}"></i><span>Profil basé sur un modèle à fiabilité ${_meta.label} — ${_anomalies.length} anomalie(s) détectée(s) par le garde-fou hydraulicien</span>`;
            _fiabBanner.title = _anomalies.map(a => `• ${a.message || a.code || ''}`).join('\n');
        } else {
            _fiabBanner.style.display = 'none';
        }
    }

    // 1c. Synthèse des anomalies hydrauliques du profil — distincte de la
    // fiabilité du modèle : un modèle SAIN peut avoir des contre-pentes,
    // débordements ou dépôts. Rend l'anomalie impossible à manquer.
    const _resAnom = document.getElementById('profil-anomalies-resume');
    const _txtAnom = document.getElementById('profil-anomalies-texte');
    if (_resAnom && _txtAnom) {
        const _sa = data.synthese_anomalies || null;
        const _nf = (_sa && _sa.forts) || 0;
        const _nm = (_sa && _sa.moyens) || 0;
        const _nt = (_sa && _sa.total) || 0;
        if (_nt > 0) {
            const _types = Object.entries((_sa && _sa.types_majeurs) || {})
                .map(([t, c]) => `${_libelleTypeAnomalie(t)} ×${c}`)
                .join(', ');
            _txtAnom.textContent = `${_nf} anomalie(s) critique(s) — avérée(s) par les données/SWMM, ` +
                `${_nm} modérée(s) — risque(s) à surveiller` +
                (_types ? ` — ${_types}` : '') +
                `. Survolez les jalons ◆ sur le graphique.`;
            _resAnom.style.display = 'flex';
            const _alerte = _nf > 0;
            _resAnom.style.color = _alerte ? '#f87171' : '#fbbf24';
            _resAnom.style.background = _alerte ? 'rgba(248,113,113,0.12)' : 'rgba(251,191,36,0.12)';
            _resAnom.title = ((_sa && _sa.messages_forts) || []).join('\n');
        } else {
            _resAnom.style.display = 'none';
        }
    }

    // 2. Alertes et recommandations
    const alertContainer = document.getElementById('profil-alertes-container');
    const alertList = document.getElementById('profil-alertes-list');
    if (alertContainer && alertList) {
        if (data.alertes && data.alertes.length > 0) {
            alertContainer.style.display = 'flex';
            alertList.innerHTML = data.alertes.map(a => `
                <div class="alerte-card ${a.type}">
                    <div class="alerte-msg">${a.message}</div>
                    ${a.observations ? `<div class="alerte-obs" style="font-size: 0.72rem; color: #cbd5e1; margin: 2px 0;">• ${a.observations}</div>` : ''}
                    <div class="alerte-reco">💡 ${a.recommandation}</div>
                </div>
            `).join('');
        } else {
            alertContainer.style.display = 'none';
        }
    }

    // 3. Tracé sur la carte Leaflet
    _surlignerCheminCarte(data.segments);

    // 4. Préparer les données pour Chart.js
    // Étiquettes X sur deux lignes : ligne 1 = n° regard, ligne 2 = distance cumulée
    const labels = data.segments.map(s => `${s.node_id}\n${Math.round(s.distance_m)} m`);
    const aTerrain = data.segments.some(s => s.z_terrain != null);
    // P3 — terrain interpolé satellite (IDW topo) : affichage seul,
    // distinct du terrain vérifié (z_terrain) pour ne jamais être
    // confondu avec une cote altimétrique réelle.
    const aTerrainInterp = data.segments.some(s => s.z_terrain_interp != null);
    const aSommet = data.segments.some(s => s.z_sommet_regard != null);
    const terrainData = data.segments.map(s => ({ x: s.distance_m, y: s.z_terrain }));
    const terrainInterpData = data.segments.map(s => ({ x: s.distance_m, y: s.z_terrain_interp }));
    const sommetData = data.segments.map(s => ({ x: s.distance_m, y: s.z_sommet_regard }));
    const genSupData = data.segments.map(s => ({ x: s.distance_m, y: s.z_gen_superieure }));
    const radierData = data.segments.map(s => ({ x: s.distance_m, y: s.z_radier }));
    const eauConduiteData = data.segments.map(s => ({ x: s.distance_m, y: s.z_eau_conduite !== undefined && s.z_eau_conduite !== null ? s.z_eau_conduite : s.z_radier }));
    const hglData = data.segments.map(s => ({ x: s.distance_m, y: s.z_hgl }));

    const _estDebordement = s => s.hgl_regime === 'debordement'
        || (s.node_status === 'flooded' && data.hgl_base !== 'instant');
    const _estSurcharge = s => s.hgl_regime === 'surcharge'
        || (s.hgl_regime !== 'debordement' && s.z_hgl != null && s.z_gen_superieure != null && s.z_hgl > s.z_gen_superieure);

    // Classification couleur et taille des points HGL (🟢 Libre / 🟡 Surcharge / 🔴 Débordement)
    const hglPointColors = data.segments.map(s => {
        if (_estDebordement(s)) {
            return '#dc2626';
        } else if (_estSurcharge(s)) {
            return '#f97316';
        }
        return '#10b981';
    });

    const hglPointRadius = data.segments.map(s => {
        if (_estDebordement(s)) return 7;
        if (_estSurcharge(s)) return 5.5;
        return 4;
    });

    const ctx = document.getElementById('canvas-profil-long');
    if (!ctx) return;

    // ── Axe des cotes : pas rond fixe adaptatif à l'amplitude ──────────
    // Graduations entières et constantes par profil (ex. 100, 102, 104 m)
    // pour une lecture fiable : le pas est le plus petit palier rond
    // donnant au plus ~10 intervalles.
    const _toutesCotes = [];
    for (const _d of [terrainData, terrainInterpData, sommetData, genSupData, radierData, eauConduiteData, hglData]) {
        for (const _p of _d) {
            if (_p && _p.y != null && isFinite(_p.y)) _toutesCotes.push(_p.y);
        }
    }
    let _yMin = Infinity, _yMax = -Infinity;
    for (const _y of _toutesCotes) {
        if (_y < _yMin) _yMin = _y;
        if (_y > _yMax) _yMax = _y;
    }
    if (!isFinite(_yMin) || !isFinite(_yMax) || _yMax <= _yMin) {
        _yMin = 0; _yMax = 1;
    }
    const _amplitude = _yMax - _yMin;
    const _pasCandidats = [0.1, 0.2, 0.25, 0.5, 1, 2, 5, 10, 20, 50];
    let _pasCote = _pasCandidats[_pasCandidats.length - 1];
    for (const _p of _pasCandidats) {
        if (_amplitude / _p <= 10) { _pasCote = _p; break; }
    }
    const _nbGraduations = Math.ceil(_amplitude / _pasCote) + 1;
    // Hauteur du graphique dimensionnée sur le nombre de graduations
    // (~24 px par palier + marge pour les étiquettes X), bornée
    // pour ne pas masquer la carte.
    const _hauteurChart = Math.min(540, Math.max(260, _nbGraduations * 24 + 40));
    const _panelProfil = document.getElementById('panel-profil-long');
    if (_panelProfil) {
        _panelProfil.style.height = `${Math.min(700, _hauteurChart + 110)}px`;
    }

    if (window.profilLongState.chartInstance) {
        window.profilLongState.chartInstance.destroy();
    }

    // Motif de hachures diagonales pour la colonne de charge piézométrique (HGL > Plan d'eau réel)
    const patternHachures = _creerPatternHachures('rgba(239, 68, 68, 0.45)', 'rgba(245, 158, 11, 0.08)', 10);

    // Création du graphique Chart.js avec Plan d'Eau Réel dans la Conduite et Zone de Charge Hachurée
    window.profilLongState.chartInstance = new Chart(ctx, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [
                ...(aTerrain ? [{
                    label: 'Terrain naturel (MNT)',
                    data: terrainData,
                    borderColor: '#10b981',
                    backgroundColor: 'transparent',
                    borderWidth: 2.2,
                    pointRadius: 4.5,
                    pointBackgroundColor: '#10b981',
                    fill: false,
                    tension: 0.1
                }] : []),
                ...(aTerrainInterp ? [{
                    label: 'Terrain interpolé IDW (topo — approximatif, ≠ fond de regard)',
                    data: terrainInterpData,
                    borderColor: '#38bdf8',
                    backgroundColor: 'transparent',
                    borderWidth: 1.8,
                    borderDash: [6, 4],
                    pointRadius: 0,
                    fill: false,
                    tension: 0.1
                }] : []),
                ...(aSommet ? [{
                    label: 'Plan de surverse (seuil de débordement SWMM)',
                    data: sommetData,
                    borderColor: '#0d9488',
                    backgroundColor: 'transparent',
                    borderWidth: 1.8,
                    borderDash: [2, 3],
                    pointRadius: 0,
                    fill: false,
                    tension: 0
                }] : []),
                {
                    label: 'Génératrice supérieure (haut de conduite)',
                    data: genSupData,
                    borderColor: '#64748b',
                    borderWidth: 1.5,
                    borderDash: [5, 4],
                    pointRadius: 2.5,
                    pointBackgroundColor: '#64748b',
                    fill: false,
                    tension: 0
                },
                {
                    label: "Fil d'eau (cote radier)",
                    data: radierData,
                    borderColor: '#475569',
                    backgroundColor: 'rgba(100, 116, 139, 0.10)',
                    borderWidth: 2.5,
                    pointRadius: 4.5,
                    pointBackgroundColor: data.segments.map(s => s.node_color || '#475569'),
                    fill: '-1', // Matérialise le vide physique intérieur de la conduite
                    tension: 0
                },
                {
                    label: "Plan d'eau réel dans la conduite (WSP / hauteur d'eau)",
                    data: eauConduiteData,
                    borderColor: '#0284c7',
                    backgroundColor: 'rgba(14, 165, 233, 0.45)', // Remplissage bleu eau translucide
                    borderWidth: 2.5,
                    pointRadius: 3.5,
                    pointBackgroundColor: '#0284c7',
                    fill: '-1', // Remplit vers le radier (Dataset 2)
                    tension: 0
                },
                {
                    label: 'Ligne de charge HGL (zone de surpression hachurée)',
                    data: hglData,
                    borderColor: '#f59e0b',
                    backgroundColor: patternHachures, // Hachures diagonales d'alerte entre WSP et HGL
                    borderWidth: 3.5,
                    pointRadius: hglPointRadius,
                    pointBackgroundColor: hglPointColors,
                    pointBorderColor: '#ffffff',
                    pointBorderWidth: 1.5,
                    fill: '-1', // Hachure la zone de mise en charge vers le Plan d'eau réel (Dataset 3)
                    tension: 0.15
                },
                {
                    label: 'Alerte : débordement confirmé (SWMM)',
                    // Points objets systématiques (jamais null) : Chart.js
                    // rejette les entrées null mélangées en mode objet.
                    // Visibilité pilotée par pointRadius.
                    data: data.segments.map(s => ({
                        x: s.distance_m,
                        y: (s.z_hgl != null ? s.z_hgl : (s.z_sommet_regard != null ? s.z_sommet_regard : s.z_radier))
                    })),
                    showLine: false,
                    pointStyle: 'triangle',
                    pointRadius: data.segments.map(s => _estDebordement(s) ? 9 : 0),
                    pointHoverRadius: 12,
                    pointBackgroundColor: '#ef4444',
                    pointBorderColor: '#ffffff',
                    pointBorderWidth: 2
                },
                {
                    label: 'Anomalies du profil (jalons)',
                    // Jalons ◆ par nœud : une anomalie est accrochée au
                    // nœud aval du tronçon concerné (voir backend
                    // `anomalies` / `resume_anomalies`). Couleur = pire
                    // sévérité du nœud ; rayon 0 quand aucune anomalie.
                    data: data.segments.map((s, idx) => ({
                        x: labels[idx],
                        y: (s.z_radier != null ? s.z_radier : (s.z_hgl != null ? s.z_hgl : (s.z_terrain_interp != null ? s.z_terrain_interp : s.z_terrain)))
                    })),
                    showLine: false,
                    pointStyle: 'rectRot',
                    pointRadius: data.segments.map(s => (s.anomalies && s.anomalies.length) ? 9 : 0),
                    pointHoverRadius: 13,
                    pointBackgroundColor: data.segments.map(s => {
                        const an = s.anomalies || [];
                        if (!an.length) return 'transparent';
                        const sev = an.some(a => a.severite === 'fort') ? 'fort'
                            : an.some(a => a.severite === 'moyen') ? 'moyen'
                            : an.some(a => a.severite === 'faible') ? 'faible' : 'info';
                        return { fort: '#ef4444', moyen: '#f59e0b', faible: '#fb923c', info: '#38bdf8' }[sev];
                    }),
                    pointBorderColor: '#ffffff',
                    pointBorderWidth: 2
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            animation: { duration: 350 },
            interaction: {
                mode: 'index',
                intersect: false
            },
            plugins: {
                legend: {
                    position: 'top',
                    labels: {
                        color: '#cbd5e1',
                        font: { size: 11, family: 'Plus Jakarta Sans', weight: '600' },
                        boxWidth: 14,
                        padding: 10
                    }
                },
                tooltip: {
                    backgroundColor: 'rgba(15, 23, 42, 0.96)',
                    titleColor: '#38bdf8',
                    bodyColor: '#e2e8f0',
                    borderColor: 'rgba(56, 189, 248, 0.4)',
                    borderWidth: 1.5,
                    padding: 12,
                    displayColors: false,
                    // N'afficher l'infobulle que sur les points des regards (dataset HGL)
                    filter: function(tooltipItem) {
                        const lbl = tooltipItem.dataset && tooltipItem.dataset.label;
                        return lbl === 'Ligne de charge HGL (zone de surpression hachuree)'
                            || lbl === 'Ligne de charge HGL (zone de surpression hachurée)'
                            || lbl === 'Anomalies du profil (jalons)';
                    },
                    callbacks: {
                        title: function(items) {
                            if (!items.length) return '';
                            const idx = items[0].dataIndex;
                            const s = data.segments[idx];
                            return `Regard : ${s.node_id} (Distance : ${s.distance_m} m)`;
                        },
                        label: function(item) {
                            const s = data.segments[item.dataIndex];
                            if (!s) return '';
                            const _lblDs = item.dataset && item.dataset.label;
                            if (_lblDs === 'Anomalies du profil (jalons)') {
                                const an = s.anomalies || [];
                                if (!an.length) return '';
                                // État seul (sévérité + type) — les messages
                                // complets restent dans le volet alertes et
                                // le rapport exporté, pas dans l'infobulle.
                                return '⚠ ' + an.map(a => _etatAnomalie(a)).join('  •  ');
                            }
                            if (_estDebordement(s)) {
                                return `🔴 État : Débordement confirmé par SWMM (eau déversée en surface)`;
                            } else if (s.hgl_regime === 'inondation') {
                                return `🟠 État : Niveau ≥ terrain naturel (sans débordement mesuré)`;
                            } else if (_estSurcharge(s)) {
                                return `🟠 État : Conduite en surcharge`;
                            } else if (s.hgl_regime === 'inconnu' || s.z_hgl == null) {
                                return `⚪ État : Donnée hydraulique indisponible`;
                            }
                            return `🟢 État : Écoulement libre`;
                        }
                    }
                }
            },
            scales: {
                x: {
                    type: 'category',
                    grid: { color: 'rgba(255, 255, 255, 0.06)' },
                    ticks: {
                        color: '#94a3b8',
                        font: { size: 9, family: 'JetBrains Mono' },
                        // Étiquettes horizontales sur deux lignes
                        // (n° regard / distance cumulée) ; autoSkip
                        // masque les labels qui se chevaucheraient.
                        autoSkip: true,
                        maxRotation: 0,
                        minRotation: 0,
                        padding: 2
                    },
                    title: {
                        display: true,
                        text: "Distance cumulée depuis l'amont (mètres)",
                        color: '#64748b',
                        font: { size: 11 }
                    }
                },
                y: {
                    grid: { color: 'rgba(255, 255, 255, 0.08)' },
                    min: Math.floor(_yMin / _pasCote) * _pasCote,
                    max: Math.ceil(_yMax / _pasCote) * _pasCote,
                    ticks: {
                        color: '#94a3b8',
                        font: { size: 10, family: 'JetBrains Mono' },
                        stepSize: _pasCote,
                        autoSkip: false
                    },
                    title: {
                        display: true,
                        text: 'Altitude (mètres)',
                        color: '#64748b',
                        font: { size: 11 }
                    }
                }
            }
        }
    });
}
