/**
 * ================================================================================
 * Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
 * Auteur : Dr Abdelhakim KELLOUCHE
 * Date de création : 2026-11-24
 * Date de modification : 2026-11-27 (V2.2 : export CSV synthèse MOA/MOE)
 * Objet : Tableau récapitulatif, bascule de vues, modales édition/raccordement/cotes — extrait de templates/qualite.html (découpage 600 lignes)
 * ================================================================================
 */

function remplirTableauRecapitulatif() {
    const tbody = document.getElementById('anom-table-tbody');
    if (!tbody) return;

    if (currentQueueList.length === 0) {
        tbody.innerHTML = '<tr><td colspan="4" style="text-align:center; color:#94a3b8;">Aucune donnée</td></tr>';
        return;
    }

    // Affiche les 100 premières lignes pour la performance
    const limit = Math.min(currentQueueList.length, 100);
    let html = '';
    for (let i = 0; i < limit; i++) {
        const p = currentQueueList[i].properties;
        html += `
            <tr onclick="selectionnerLigneTableau(${i})">
                <td><strong>${p.id_conduite || p.cle_anomalie?.substring(0,6)}</strong></td>
                <td>${libelleCategorie(p.categorie)}</td>
                <td><span class="badge-sev badge-${p.severite}">${p.severite}</span></td>
                <td><span class="badge-sev badge-informatif">${p.statut || 'a_traiter'}</span></td>
            </tr>
        `;
    }
    if (currentQueueList.length > 100) {
        html += `<tr><td colspan="4" style="text-align:center; color:#64748b; font-style:italic;">... et ${currentQueueList.length - 100} autres éléments</td></tr>`;
    }
    tbody.innerHTML = html;
}

function selectionnerLigneTableau(index) {
    basculerVuePanel('fiche');
    currentQueueIndex = index;
    afficherFicheAnomalie(currentQueueList[currentQueueIndex], true);
    mettreAJourCompteurQueue();
}

function basculerVuePanel(vue) {
    const tabFiche = document.getElementById('tab-fiche');
    const tabTable = document.getElementById('tab-table');
    const vueFiche = document.getElementById('vue-fiche');
    const vueTable = document.getElementById('vue-table');
    const stepper = document.getElementById('queue-stepper-bar');

    if (vue === 'fiche') {
        tabFiche.classList.add('active');
        tabTable.classList.remove('active');
        vueFiche.style.display = 'block';
        vueTable.style.display = 'none';
        stepper.style.display = 'flex';
    } else {
        tabFiche.classList.remove('active');
        tabTable.classList.add('active');
        vueFiche.style.display = 'none';
        vueTable.style.display = 'block';
        stepper.style.display = 'none';
    }
}

// 10. Navigation Cockpit & Helpers
function retournerCockpit(event) {
    if (event) event.preventDefault();
    if (window.parent && window.parent !== window && typeof window.parent.basculerVueCockpit === 'function') {
        window.parent.basculerVueCockpit('carto');
        return;
    }
    if (window.history.length > 1 && (document.referrer.includes('/map') || document.referrer.includes(window.location.host))) {
        window.history.back();
    } else {
        window.location.href = '/map';
    }
}

function afficherLoading(visible, texte = 'Chargement...') {
    const el = document.getElementById('loading-overlay');
    const txt = document.getElementById('loading-text');
    if (el) el.style.display = visible ? 'flex' : 'none';
    if (txt) txt.textContent = texte;
}

// ============================================================
// 10bis. Export synthétique MOA/MOE (CSV par dimension)
// ============================================================
function exporterRapportQualiteCSV() {
    const syn = currentSynthese;
    if (!syn) {
        alert('Aucune synthèse chargée — lancez d\'abord l\'analyse qualité.');
        return;
    }

    const lignes = [];
    const _csv = (v) => {
        const s = (v === null || v === undefined) ? '' : String(v);
        return /[;"\n]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s;
    };
    const section = (titre) => lignes.push('', `## ${titre}`);
    const kv = (k, v) => lignes.push(`${_csv(k)};${_csv(v)}`);

    section('Synthese');
    kv('Projet', syn.nom_projet || 'Projet actif');
    kv('Date analyse', syn.date_analyse || '');
    kv('Moteur', syn.moteur || '');
    kv('Verdict', syn.verdict || '');

    section('Reseau');
    const r = syn.reseau || {};
    kv('Regards', r.nb_regards);
    kv('Conduites', r.nb_conduites);
    kv('Rejets', r.nb_rejets);
    kv('Longueur totale (m)', r.longueur_totale_m);

    section('Scores par dimension (%)');
    const s = syn.scores || {};
    kv('Score global', s.global);
    kv('Topologie', s.topologie);
    kv('Hydraulique', s.hydraulique);
    kv('Completude', s.completude);
    kv('Geometrie', s.geometrie);
    const alti = syn.altimetrie || {};
    kv('Altimetrie (score qualite)', alti.score_qualite);
    kv('Altimetrie (couverture %)', alti.couverture_pct);
    kv('Altimetrie (donnees manquantes)', alti.nb_donnees_manquantes);

    section('Anomalies');
    const a = syn.anomalies || {};
    kv('Total anomalies', a.total);
    kv('A traiter', a.nb_a_traiter);
    kv('Informatif (bruit complete)', a.nb_informatif);
    Object.entries(a.par_severite || {}).forEach(([sev, n]) => kv(`Severite ${sev}`, n));
    Object.entries(a.par_categorie || {}).forEach(([cat, n]) => kv(`Categorie ${libelleCategorie(cat)}`, n));

    section('Criticite par troncon (top 20)');
    lignes.push('id_conduite;score;nb_anomalies;severite_max');
    const crit = Object.entries(syn.criticite_troncons || {})
        .sort((x, y) => (y[1].score || 0) - (x[1].score || 0))
        .slice(0, 20);
    crit.forEach(([id, c]) => lignes.push(`${_csv(id)};${c.score ?? ''};${c.nb_anomalies ?? ''};${c.severite_max ?? ''}`));

    if (_orphelinsStats) {
        section('Orphelins reseau (graphe)');
        kv('Noeuds orphelins', _orphelinsStats.noeuds_orphelins);
        kv('Troncons orphelins', _orphelinsStats.troncons_orphelins);
        kv('Aretes orphelines (composante sans exutoire)', _orphelinsStats.aretes_orphelines_composante);
    }

    const blob = new Blob(['﻿' + lignes.join('\r\n')], { type: 'text/csv;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const aEl = document.createElement('a');
    const stamp = (syn.date_analyse || new Date().toISOString()).replace(/[:.]/g, '-').slice(0, 19);
    aEl.href = url;
    aEl.download = `qualite_${(syn.nom_projet || 'projet').replace(/\s+/g, '_')}_${stamp}.csv`;
    document.body.appendChild(aEl);
    aEl.click();
    document.body.removeChild(aEl);
    URL.revokeObjectURL(url);
}

// ============================================================
// 11. Actions de Correction Directe (Lot 4)
// ============================================================
function ouvrirModalEditionAttributs(idConduite, cleAnomalie, diametreActuel, materiauActuel, distanceM) {
    document.getElementById('edit-id-conduite').value = idConduite || '';
    document.getElementById('edit-cle-anomalie').value = cleAnomalie || '';
    document.getElementById('modal-edit-title').innerHTML = `<i class="fa-solid fa-pen-to-square" style="color:#38bdf8; margin-right:8px;"></i> Modifier la conduite ${idConduite || ''}`;
    document.getElementById('edit-diametre').value = diametreActuel || '';
    document.getElementById('edit-materiau').value = materiauActuel || '';
    document.getElementById('edit-longueur').value = distanceM || '';
    document.getElementById('edit-justification').value = '';

    const modal = document.getElementById('modal-edit-conduite');
    if (modal) modal.style.display = 'flex';
}

function fermerModalEditionAttributs() {
    const modal = document.getElementById('modal-edit-conduite');
    if (modal) modal.style.display = 'none';
}

async function sauvegarderEditionAttributs() {
    const idConduite = document.getElementById('edit-id-conduite').value;
    const cleAnomalie = document.getElementById('edit-cle-anomalie').value;
    const diametre = document.getElementById('edit-diametre').value;
    const materiau = document.getElementById('edit-materiau').value;
    const longueur = document.getElementById('edit-longueur').value;
    const justification = document.getElementById('edit-justification').value;

    if (!idConduite) {
        alert('Identifiant de conduite manquant.');
        return;
    }

    const payload = {
        cle_anomalie: cleAnomalie,
        commentaire: justification || 'Attributs mis à jour depuis le cockpit qualité'
    };
    if (diametre && !isNaN(parseFloat(diametre))) payload.diametre = parseFloat(diametre);
    if (materiau) payload.materiau = materiau;
    if (longueur && !isNaN(parseFloat(longueur))) payload.longueur = parseFloat(longueur);

    fermerModalEditionAttributs();
    afficherLoading(true, `Enregistrement des attributs pour ${idConduite}...`);

    try {
        const token = localStorage.getItem('swmm_access_token');
        const headers = {
            'Content-Type': 'application/json',
            ...(token ? { 'Authorization': `Bearer ${token}` } : {})
        };

        const resp = await fetch(`${API_BASE}/conduites/${encodeURIComponent(idConduite)}`, {
            method: 'PATCH',
            headers: headers,
            credentials: 'include',
            body: JSON.stringify(payload)
        });

        if (!resp.ok) {
            const err = await resp.json().catch(() => ({}));
            throw new Error(err.detail || `HTTP ${resp.status}`);
        }

        // Succès : mise à jour locale de l'anomalie
        const item = currentQueueList.find(x => x.properties.cle_anomalie === cleAnomalie || x.properties.id_conduite === idConduite);
        if (item) {
            item.properties.statut = 'corrige';
            if (payload.diametre) item.properties.diametre = payload.diametre;
            if (payload.materiau) item.properties.materiau = payload.materiau;
            item.properties.description = `✓ Attributs corrigés (${payload.diametre ? 'diamètre=' + payload.diametre + 'mm' : ''} ${payload.materiau ? 'matériau=' + payload.materiau : ''})`;
            afficherFicheAnomalie(item, false);
        }

        afficherLoading(false);
        alert(`✓ Conduite ${idConduite} modifiée avec succès dans le GeoPackage.\nStatut marqué comme corrigé.`);
    } catch (err) {
        afficherLoading(false);
        console.error('Erreur modification conduite:', err);
        alert(`Erreur lors de la modification : ${err.message}`);
    }
}

async function inverserSensEcoulement(idConduite, cleAnomalie, amont, aval) {
    if (!idConduite) return;

    const confirmMsg = `Confirmez-vous l'inversion du sens d'écoulement pour la conduite ${idConduite} ?\n\nNouveau sens : ${aval} ➔ ${amont}\n(L'anomalie de contre-pente sera résolue et marquée comme corrigée).`;
    if (!confirm(confirmMsg)) return;

    afficherLoading(true, `Inversion du sens pour ${idConduite}...`);

    try {
        const token = localStorage.getItem('swmm_access_token');
        const headers = {
            'Content-Type': 'application/json',
            ...(token ? { 'Authorization': `Bearer ${token}` } : {})
        };

        const resp = await fetch(`${API_BASE}/conduites/${encodeURIComponent(idConduite)}/inverser-sens`, {
            method: 'POST',
            headers: headers,
            credentials: 'include',
            body: JSON.stringify({
                cle_anomalie: cleAnomalie,
                commentaire: `Inversion de sens d'écoulement validée (${amont}➔${aval} devenu ${aval}➔${amont})`
            })
        });

        if (!resp.ok) {
            const err = await resp.json().catch(() => ({}));
            throw new Error(err.detail || `HTTP ${resp.status}`);
        }

        const resData = await resp.json();

        // Succès : mise à jour locale
        const item = currentQueueList.find(x => x.properties.cle_anomalie === cleAnomalie || x.properties.id_conduite === idConduite);
        if (item) {
            item.properties.id_amont = resData.nouvel_amont;
            item.properties.id_aval = resData.nouvel_aval;
            item.properties.statut = 'corrige';
            item.properties.description = `✓ Sens d'écoulement inversé : ${resData.nouvel_amont} ➔ ${resData.nouvel_aval}`;
            afficherFicheAnomalie(item, false);
        }

        afficherLoading(false);
        alert(`✓ Sens d'écoulement inversé avec succès pour ${idConduite} !\nNouveau sens : ${resData.nouvel_amont} ➔ ${resData.nouvel_aval}.`);
    } catch (err) {
        afficherLoading(false);
        console.error('Erreur inversion sens:', err);
        alert(`Erreur lors de l'inversion : ${err.message}`);
    }
}

// ============================================================
// 12. Actions de Raccordement Topologique (Nœuds Amont / Aval)
// ============================================================
let suggestionsNoeudsActuelles = { amont: null, aval: null };

async function ouvrirModalRaccordementNoeuds(idConduite, cleAnomalie, amontActuel, avalActuel) {
    document.getElementById('raccord-id-conduite').value = idConduite || '';
    document.getElementById('raccord-cle-anomalie').value = cleAnomalie || '';
    document.getElementById('modal-raccord-title').innerHTML = `<i class="fa-solid fa-link" style="color:#818cf8; margin-right:8px;"></i> Raccordement topologique — Tronçon ${idConduite || ''}`;
    document.getElementById('raccord-amont').value = amontActuel || '';
    document.getElementById('raccord-aval').value = avalActuel || '';
    document.getElementById('raccord-justification').value = '';

    const sAm = document.getElementById('raccord-suggestion-amont');
    const sAv = document.getElementById('raccord-suggestion-aval');
    if (sAm) sAm.style.display = 'none';
    if (sAv) sAv.style.display = 'none';
    suggestionsNoeudsActuelles = { amont: null, aval: null };

    const modal = document.getElementById('modal-raccordement-noeuds');
    if (modal) modal.style.display = 'flex';

    // Appel API pour chercher par analyse spatiale les nœuds les plus proches
    try {
        const token = localStorage.getItem('swmm_access_token');
        const headers = token ? { 'Authorization': `Bearer ${token}` } : {};
        const resp = await fetch(`${API_BASE}/conduites/${encodeURIComponent(idConduite)}/noeuds-candidats`, {
            headers: headers,
            credentials: 'include'
        });
        if (resp.ok) {
            const data = await resp.json();
            if (data.amont_proche && data.amont_proche.id) {
                suggestionsNoeudsActuelles.amont = data.amont_proche.id;
                if (sAm) {
                    sAm.style.display = 'flex';
                    document.getElementById('raccord-text-amont').innerHTML = `<i class="fa-solid fa-crosshairs"></i> Nœud le plus proche : <strong>${data.amont_proche.id}</strong> (${data.amont_proche.distance_m} m)`;
                }
            }
            if (data.aval_proche && data.aval_proche.id) {
                suggestionsNoeudsActuelles.aval = data.aval_proche.id;
                if (sAv) {
                    sAv.style.display = 'flex';
                    document.getElementById('raccord-text-aval').innerHTML = `<i class="fa-solid fa-crosshairs"></i> Nœud le plus proche : <strong>${data.aval_proche.id}</strong> (${data.aval_proche.distance_m} m)`;
                }
            }
        }
    } catch (err) {
        console.warn('Impossible de charger les suggestions de nœuds:', err);
    }
}

function fermerModalRaccordementNoeuds() {
    const modal = document.getElementById('modal-raccordement-noeuds');
    if (modal) modal.style.display = 'none';
}

function appliquerSuggestionNoeud(type) {
    if (type === 'amont' && suggestionsNoeudsActuelles.amont) {
        document.getElementById('raccord-amont').value = suggestionsNoeudsActuelles.amont;
    } else if (type === 'aval' && suggestionsNoeudsActuelles.aval) {
        document.getElementById('raccord-aval').value = suggestionsNoeudsActuelles.aval;
    }
}

async function sauvegarderRaccordementNoeuds() {
    const idConduite = document.getElementById('raccord-id-conduite').value;
    const cleAnomalie = document.getElementById('raccord-cle-anomalie').value;
    const nouvelAmont = document.getElementById('raccord-amont').value.trim();
    const nouvelAval = document.getElementById('raccord-aval').value.trim();
    const justification = document.getElementById('raccord-justification').value.trim();

    if (!idConduite) {
        alert('Identifiant de conduite manquant.');
        return;
    }
    if (!nouvelAmont || !nouvelAval) {
        alert('Veuillez renseigner à la fois le nœud amont et le nœud aval.');
        return;
    }

    fermerModalRaccordementNoeuds();
    afficherLoading(true, `Mise à jour du raccordement pour ${idConduite}...`);

    try {
        const token = localStorage.getItem('swmm_access_token');
        const headers = {
            'Content-Type': 'application/json',
            ...(token ? { 'Authorization': `Bearer ${token}` } : {})
        };

        const payload = {
            id_amont: nouvelAmont,
            id_aval: nouvelAval,
            cle_anomalie: cleAnomalie,
            commentaire: justification || `Raccordement topologique mis à jour (${nouvelAmont} ➔ ${nouvelAval})`
        };

        const resp = await fetch(`${API_BASE}/conduites/${encodeURIComponent(idConduite)}`, {
            method: 'PATCH',
            headers: headers,
            credentials: 'include',
            body: JSON.stringify(payload)
        });

        if (!resp.ok) {
            const err = await resp.json().catch(() => ({}));
            throw new Error(err.detail || `HTTP ${resp.status}`);
        }

        // Succès : mise à jour locale
        const item = currentQueueList.find(x => x.properties.cle_anomalie === cleAnomalie || x.properties.id_conduite === idConduite);
        if (item) {
            item.properties.id_amont = nouvelAmont;
            item.properties.id_aval = nouvelAval;
            item.properties.statut = 'corrige';
            item.properties.description = `✓ Raccordement rétabli : ${nouvelAmont} ➔ ${nouvelAval}`;
            afficherFicheAnomalie(item, false);
        }

        afficherLoading(false);
        alert(`✓ Raccordement topologique mis à jour avec succès pour ${idConduite} !\nAmont: ${nouvelAmont} | Aval: ${nouvelAval}\nStatut marqué comme corrigé.`);
    } catch (err) {
        afficherLoading(false);
        console.error('Erreur raccordement topologique:', err);
        alert(`Erreur lors du raccordement : ${err.message}`);
    }
}

// ============================================================
// 13. Actions d'Ajustement Altimétrique & Fil d'Eau
// ============================================================
function ouvrirModalCotesAlti(idConduite, cleAnomalie, profAmActuel, profAvActuel) {
    document.getElementById('alti-id-conduite').value = idConduite || '';
    document.getElementById('alti-cle-anomalie').value = cleAnomalie || '';
    document.getElementById('modal-alti-title').innerHTML = `<i class="fa-solid fa-ruler-vertical" style="color:#2dd4bf; margin-right:8px;"></i> Cotes de fil d'eau — Tronçon ${idConduite || ''}`;
    document.getElementById('alti-prof-am').value = profAmActuel || '';
    document.getElementById('alti-prof-av').value = profAvActuel || '';
    document.getElementById('alti-justification').value = '';

    const modal = document.getElementById('modal-cotes-alti');
    if (modal) modal.style.display = 'flex';
}

function fermerModalCotesAlti() {
    const modal = document.getElementById('modal-cotes-alti');
    if (modal) modal.style.display = 'none';
}

async function sauvegarderCotesAlti() {
    const idConduite = document.getElementById('alti-id-conduite').value;
    const cleAnomalie = document.getElementById('alti-cle-anomalie').value;
    const profAm = document.getElementById('alti-prof-am').value;
    const profAv = document.getElementById('alti-prof-av').value;
    const justification = document.getElementById('alti-justification').value.trim();

    if (!idConduite) {
        alert('Identifiant de conduite manquant.');
        return;
    }

    fermerModalCotesAlti();
    afficherLoading(true, `Enregistrement des cotes pour ${idConduite}...`);

    try {
        const token = localStorage.getItem('swmm_access_token');
        const headers = {
            'Content-Type': 'application/json',
            ...(token ? { 'Authorization': `Bearer ${token}` } : {})
        };

        const payload = {
            cle_anomalie: cleAnomalie,
            commentaire: justification || 'Profondeurs de fil d\'eau ajustées'
        };
        if (profAm && !isNaN(parseFloat(profAm))) payload.prof_fe_am = parseFloat(profAm);
        if (profAv && !isNaN(parseFloat(profAv))) payload.prof_fe_av = parseFloat(profAv);

        const resp = await fetch(`${API_BASE}/conduites/${encodeURIComponent(idConduite)}`, {
            method: 'PATCH',
            headers: headers,
            credentials: 'include',
            body: JSON.stringify(payload)
        });

        if (!resp.ok) {
            const err = await resp.json().catch(() => ({}));
            throw new Error(err.detail || `HTTP ${resp.status}`);
        }

        const item = currentQueueList.find(x => x.properties.cle_anomalie === cleAnomalie || x.properties.id_conduite === idConduite);
        if (item) {
            item.properties.statut = 'corrige';
            item.properties.description = `✓ Cotes fil d'eau mises à jour (Amont: ${profAm || '?'} m, Aval: ${profAv || '?'} m)`;
            afficherFicheAnomalie(item, false);
        }

        afficherLoading(false);
        alert(`✓ Cotes de fil d'eau mises à jour avec succès pour ${idConduite}.\nStatut marqué comme corrigé.`);
    } catch (err) {
        afficherLoading(false);
        console.error('Erreur cotes fil d\'eau:', err);
        alert(`Erreur lors de l'enregistrement des cotes : ${err.message}`);
    }
}
