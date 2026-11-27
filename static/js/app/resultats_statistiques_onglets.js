/**
 * ================================================================================
 * Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
 * Auteur : Dr Abdelhakim KELLOUCHE
 * Date de création : 2026-11-27
 * Date de modification : 2026-11-27
 * Objet : Onglets et sous-onglets de la modale resultats, filtres par statut, resolution nom metier bassin (extrait de static/js/app/resultats_statistiques.js)
 * ================================================================================
 */

window.basculerOngletResultats = function(tabKey) {
    const tabs = ['kpi', 'details', 'ia'];
    tabs.forEach(t => {
        const pane = document.getElementById('onglet-res-' + t);
        const btn = document.getElementById('tab-btn-res-' + t);
        if (pane) pane.style.display = (t === tabKey) ? 'block' : 'none';
        if (btn) {
            if (t === tabKey) {
                btn.style.borderBottom = '2.5px solid #38bdf8';
                btn.style.color = '#38bdf8';
                btn.style.fontWeight = '700';
            } else {
                btn.style.borderBottom = '2.5px solid transparent';
                btn.style.color = '#94a3b8';
                btn.style.fontWeight = '600';
            }
        }
    });
};

window.basculerSousOngletDetails = function(subKey) {
    const subConduites = document.getElementById('subtab-content-conduites');
    const subRegards = document.getElementById('subtab-content-regards');
    const btnConduites = document.getElementById('btn-subtab-conduites');
    const btnRegards = document.getElementById('btn-subtab-regards');

    if (subKey === 'conduites') {
        if (subConduites) subConduites.style.display = 'block';
        if (subRegards) subRegards.style.display = 'none';
        if (btnConduites) { btnConduites.style.background = '#0284c7'; btnConduites.style.color = '#ffffff'; }
        if (btnRegards) { btnRegards.style.background = 'transparent'; btnRegards.style.color = '#94a3b8'; }
    } else {
        if (subConduites) subConduites.style.display = 'none';
        if (subRegards) subRegards.style.display = 'block';
        if (btnConduites) { btnConduites.style.background = 'transparent'; btnConduites.style.color = '#94a3b8'; }
        if (btnRegards) { btnRegards.style.background = '#0284c7'; btnRegards.style.color = '#ffffff'; }
    }
};

window.filtrerConduitesParStatut = function(statut) {
    window._detailsConduitesFiltreStatut = statut;
    const btns = document.querySelectorAll('.btn-filter-cond');
    btns.forEach(b => {
        b.style.fontWeight = 'normal';
        b.style.boxShadow = 'none';
        b.classList.remove('active');
    });
    if (window.event && window.event.currentTarget) {
        window.event.currentTarget.classList.add('active');
        window.event.currentTarget.style.fontWeight = 'bold';
        window.event.currentTarget.style.boxShadow = '0 0 10px rgba(56,189,248,0.3)';
    }
    window.filtrerTableauDetailsOuvrages();
};

window.filtrerRegardsParStatut = function(statut) {
    window._detailsRegardsFiltreStatut = statut;
    const btns = document.querySelectorAll('.btn-filter-reg');
    btns.forEach(b => {
        b.style.fontWeight = 'normal';
        b.style.boxShadow = 'none';
        b.classList.remove('active');
    });
    if (window.event && window.event.currentTarget) {
        window.event.currentTarget.classList.add('active');
        window.event.currentTarget.style.fontWeight = 'bold';
        window.event.currentTarget.style.boxShadow = '0 0 10px rgba(56,189,248,0.3)';
    }
    window.filtrerTableauDetailsOuvrages();
};

window.filtrerTableauDetailsOuvrages = function() {
    const input = document.getElementById('inp-search-details-ouvrage');
    const q = (input && input.value ? input.value : '').toLowerCase().trim();

    // Filtrage des conduites
    const condRows = document.querySelectorAll('#tbody-details-conduites tr');
    condRows.forEach(row => {
        if (!row.getAttribute('data-id')) return;
        const statut = row.getAttribute('data-statut') || '';
        const id = (row.getAttribute('data-id') || '').toLowerCase();
        const amont = (row.getAttribute('data-amont') || '').toLowerCase();
        const aval = (row.getAttribute('data-aval') || '').toLowerCase();

        const matchStatut = (window._detailsConduitesFiltreStatut === 'tous') || (statut === window._detailsConduitesFiltreStatut);
        const matchSearch = (!q) || id.includes(q) || amont.includes(q) || aval.includes(q);

        row.style.display = (matchStatut && matchSearch) ? '' : 'none';
    });

    // Filtrage des regards
    const regRows = document.querySelectorAll('#tbody-details-regards tr');
    regRows.forEach(row => {
        if (!row.getAttribute('data-id')) return;
        const statut = row.getAttribute('data-statut') || '';
        const id = (row.getAttribute('data-id') || '').toLowerCase();

        const matchStatut = (window._detailsRegardsFiltreStatut === 'tous') || (statut === window._detailsRegardsFiltreStatut);
        const matchSearch = (!q) || id.includes(q);

        row.style.display = (matchStatut && matchSearch) ? '' : 'none';
    });
};

function _resoudreNomMetierBassinResultats(meta) {
    if (!meta) return 'Réseau Complet';
    const cid = (meta.cluster_id !== undefined && meta.cluster_id !== null) ? String(meta.cluster_id).trim() : '';
    const _estIdBrut = (v) => {
        const s = String(v || '').trim();
        if (!s) return true;
        if (/^\d+(\.0)?$/.test(s) || /^Bassin\s+\d+$/i.test(s)) return true;
        return !!(cid && s.toLowerCase() === cid.toLowerCase());
    };
    const candMeta = String(meta.cluster_nom || meta.bassin_nom || '').trim();
    if (!_estIdBrut(candMeta)) return candMeta;
    if (cid && window._bassinNoms && window._bassinNoms[cid] && !_estIdBrut(window._bassinNoms[cid])) {
        return window._bassinNoms[cid];
    }
    const bp = (cid && window._bassinProperties && window._bassinProperties[cid]) ? window._bassinProperties[cid] : null;
    if (bp) {
        const nomGeo = String(bp.nom_affiche || bp.nom || bp.nom_exutoire || bp.bassin_nom || '').trim();
        if (!_estIdBrut(nomGeo)) return nomGeo;
    }
    if (window._clustersData && Array.isArray(window._clustersData.features) && cid) {
        const feat = window._clustersData.features.find(f => f && f.properties && (
            String(f.properties.cluster_id) === cid
            || String(f.properties.exutoire_id) === cid
            || String(f.properties.bassin_ref) === cid
        ));
        if (feat && feat.properties) {
            const fn = String(feat.properties.nom_affiche || feat.properties.nom || feat.properties.nom_exutoire || '').trim();
            if (!_estIdBrut(fn)) return fn;
        }
    }
    return candMeta || (cid ? `Bassin ${cid}` : 'Réseau Complet');
}
