/**
 * ================================================================================
 * Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
 * Auteur : Dr Abdelhakim KELLOUCHE
 * Date de création : 2026-11-24
 * Objet : État global, initialisation carte Leaflet, chargement données et synthèse — extrait de templates/qualite.html (découpage 600 lignes)
 * ================================================================================
 */

// État Global V2.1
const API_BASE = '/api/v1/qualite';
let currentSynthese = null;
let currentAnomaliesGeoJSON = null;
let currentQueueList = [];
let currentQueueIndex = 0;

let map = null;
let clusterGroup = null;
let fineNetworkGroup = null;
let _fineReseauReq = 0;
let selectedMarker = null;
let highlightMarker = null;
let globalBoundsReseau = null;
let activeGeoJsonLayers = {};

// Libellés métier explicites (adieu codes techniques N2/N3)
function libelleCategorie(cat) {
    const mapLib = {
        'inversions_sens_ecoulement': 'Contre-pente / Inversion de sens',
        'pentes_suspectes': 'Pente suspecte',
        'deconnexions_spatiales': 'Déconnexion spatiale',
        'champs_manquants': 'Attributs obligatoires manquants',
        'conduites_sans_regards': 'Conduite sans regard',
        'troncons_orphelins': 'Tronçon orphelin',
        'donnees_manquantes': 'Altimétrie incomplète (cotes/points topo)'
    };
    return mapLib[cat] || (cat || '').replace('_', ' ');
}

// Action recommandée par catégorie d'anomalie — miroir du LIBELLES
// de api/routes/qualite.py. Le hint « Action prioritaire » du bandeau
// suit l'anomalie affichée au lieu de rester figé sur le top global.
const ACTION_PAR_CATEGORIE = {
    'conduites_sans_regards': 'Raccorder les conduites orphelines à un nœud',
    'troncons_orphelins': 'Vérifier l\'isolement des tronçons orphelins',
    'champs_manquants': 'Compléter les attributs manquants (diamètre, matériau, longueur)',
    'geometries_invalides': 'Réparer les géométries corrompues',
    'pentes_suspectes': 'Valider les pentes certifiées NGF sur le terrain',
    'incoherences_amont_aval': 'Corriger les inversions de radier NGF',
    'inversions_sens_ecoulement': 'Recouper le sens d\'écoulement avec le sens de la pente du terrain',
    'deconnexions_spatiales': 'Contrôler les identifiants d\'extrémités suspects',
    'discontinuites_pose': 'Vérifier la continuité de pose (profondeurs PROF_FE)',
    'capacite_debit': 'Contrôler la capacité de débit des tronçons',
    'donnees_manquantes': 'Compléter l\'altimétrie (campagne topo / récolement)'
};
let _topActionGlobalHtml = null;

// Initialisation dès chargement DOM
document.addEventListener('DOMContentLoaded', () => {
    initLeafletMap();
    initEventHandlers();
    chargerDonneesQualite(false);
});

// 1. Initialisation de la carte Leaflet
function initLeafletMap() {
    // Centre par défaut Algérie (Chlef : 36.166, 1.334)
    map = L.map('map', {
        center: [36.166, 1.334],
        zoom: 14,
        zoomControl: true
    });

    // Fond de carte OpenStreetMap standard (fiable et rapide)
    const osm = L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '&copy; OpenStreetMap contributors',
        maxZoom: 19
    }).addTo(map);

    const satellite = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', {
        attribution: '&copy; Esri World Imagery',
        maxZoom: 19
    });

    L.control.layers({
        "Plan Standard (OSM)": osm,
        "Satellite (Esri)": satellite
    }, null, { position: 'topleft' }).addTo(map);

    // Groupe Clusterisé MarkerCluster avec stylage personnalisé par sévérité
    clusterGroup = L.markerClusterGroup({
        chunkedLoading: true,
        maxClusterRadius: 40,
        iconCreateFunction: function (cluster) {
            const markers = cluster.getAllChildMarkers();
            let hasCritique = false;
            let hasMajeure = false;
            let hasMineure = false;

            markers.forEach(m => {
                const sev = m.options.severite;
                if (sev === 'critique') hasCritique = true;
                else if (sev === 'majeure') hasMajeure = true;
                else if (sev === 'mineure') hasMineure = true;
            });

            let cls = 'cluster-neutre';
            if (hasCritique) cls = 'cluster-critique';
            else if (hasMajeure) cls = 'cluster-majeure';
            else if (hasMineure) cls = 'cluster-mineure';

            return L.divIcon({
                html: `<div>${cluster.getChildCount()}</div>`,
                className: `cluster-marker-custom ${cls}`,
                iconSize: L.point(34, 34)
            });
        }
    });
    map.addLayer(clusterGroup);

    // « Fine réseau » volatile : contexte local du tronçon suspect
    // (conduites + nœuds dans un rayon réduit). Ajouté en dernier pour
    // rester au premier plan ; vidé à chaque changement d'anomalie.
    fineNetworkGroup = L.layerGroup().addTo(map);
}

// 2. Gestion des Événements & Raccourcis Clavier
function initEventHandlers() {
    // Raccourcis clavier J / K (navigation) et Z (zoomer sur anomalie)
    window.addEventListener('keydown', (e) => {
        if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA' || e.target.tagName === 'SELECT') return;
        if (e.key === 'j' || e.key === 'J' || e.key === 'ArrowDown') {
            e.preventDefault();
            naviguerQueue(1);
        } else if (e.key === 'k' || e.key === 'K' || e.key === 'ArrowUp') {
            e.preventDefault();
            naviguerQueue(-1);
        } else if (e.key === 'z' || e.key === 'Z') {
            e.preventDefault();
            zoomerSurAnomalieActive();
        }
    });

    document.getElementById('btn-prev').addEventListener('click', () => naviguerQueue(-1));
    document.getElementById('btn-next').addEventListener('click', () => naviguerQueue(1));

    document.getElementById('btn-force-refresh').addEventListener('click', () => {
        chargerDonneesQualite(true);
    });

    // Filtres réactifs
    ['filter-categorie', 'filter-severite', 'filter-statut'].forEach(id => {
        document.getElementById(id).addEventListener('change', () => {
            filtrerEtMettreAJourCarte();
        });
    });

    document.getElementById('chk-toggle-n3').addEventListener('change', () => {
        const inclureN3 = document.getElementById('chk-toggle-n3').checked;
        // Si l'utilisateur active N3 et qu'on n'a pas encore téléchargé les données manquantes, on recharge le GeoJSON complet
        const aDonneesManquantes = currentAnomaliesGeoJSON?.features?.some(f => f.properties?.categorie === 'donnees_manquantes');
        if (inclureN3 && !aDonneesManquantes) {
            chargerDonneesQualite(false);
        } else {
            filtrerEtMettreAJourCarte();
        }
    });
}

// 3. Récupération des Données (Synthèse + GeoJSON)
async function chargerDonneesQualite(forceRefresh = false) {
    afficherLoading(true, forceRefresh ? 'Recalcul complet sans cache...' : 'Chargement de la qualité V2.1...');
    try {
        const token = localStorage.getItem('swmm_access_token');
        const headers = token ? { 'Authorization': `Bearer ${token}` } : {};

        // A. Synthèse immédiate (KPIs affichés sans attendre la cartographie)
        const synUrl = `${API_BASE}/synthese${forceRefresh ? '?force_refresh=true' : ''}`;
        const respSyn = await fetch(synUrl, { headers, credentials: 'include' });
        if (!respSyn.ok) {
            const errPayload = await respSyn.json().catch(() => ({}));
            const detail = errPayload.detail || `HTTP ${respSyn.status}`;
            throw new Error(`Erreur synthèse (${detail})`);
        }
        currentSynthese = await respSyn.json();
        afficherSynthese(currentSynthese);

        // B. GeoJSON ciblé (par défaut ~180 Ko au lieu de 5 Mo si N3 désactivé)
        const inclureN3 = document.getElementById('chk-toggle-n3')?.checked || false;
        const geoUrl = `${API_BASE}/anomalies.geojson?inclure_manquants=${inclureN3}${forceRefresh ? '&force_refresh=true' : ''}`;
        const respGeo = await fetch(geoUrl, { headers, credentials: 'include' });
        if (!respGeo.ok) {
            const errPayload = await respGeo.json().catch(() => ({}));
            const detail = errPayload.detail || `HTTP ${respGeo.status}`;
            throw new Error(`Erreur GeoJSON (${detail})`);
        }
        currentAnomaliesGeoJSON = await respGeo.json();

        // Filtrage et affichage initial
        filtrerEtMettreAJourCarte();

    } catch (err) {
        console.error('[QUALITE] Erreur chargement:', err);
        const ficheEl = document.getElementById('fiche-container');
        if (ficheEl) {
            ficheEl.innerHTML = `
                <div style="background: rgba(239, 68, 68, 0.1); border: 1px solid rgba(239, 68, 68, 0.3); border-radius: 8px; padding: 20px; margin: 15px; text-align: center;">
                    <div style="font-size: 1.5rem; margin-bottom: 8px;">⚠️</div>
                    <h4 style="color: #f87171; margin-bottom: 8px; font-size: 1rem;">Impossible de charger les données qualité</h4>
                    <p style="color: var(--text-muted); font-size: 0.85rem; margin-bottom: 15px;">${err.message}</p>
                    <button onclick="chargerDonneesQualite(true)" class="btn-refresh" style="display: inline-flex; margin: 0 auto;">
                        <span>↻</span> Réessayer l'analyse
                    </button>
                </div>
            `;
        }
    } finally {
        afficherLoading(false);
    }
}

// 4. Affichage de la synthèse & KPI
function afficherSynthese(syn) {
    if (!syn) return;

    // En-tête : nom du projet + effectifs du réseau (la version du
    // moteur n'apporte rien à l'utilisateur — badge masqué).
    const _r = syn.reseau || {};
    const _fmt = (n) => (n === null || n === undefined) ? '—' : Number(n).toLocaleString('fr-FR');
    const _nomProjet = syn.nom_projet || 'Projet Actif';
    document.getElementById('header-projet-name').textContent =
        `${_nomProjet} — ${_fmt(_r.nb_conduites)} conduites · ${_fmt(_r.nb_regards)} regards`;
    const _vEl = document.getElementById('header-gpkg-version');
    if (_vEl) _vEl.style.display = 'none';

    // Verdict
    const elVerdict = document.getElementById('kpi-verdict');
    elVerdict.textContent = syn.verdict ? syn.verdict.toUpperCase().replace('_', ' ') : 'INCONNU';
    if (syn.verdict === 'conforme') elVerdict.className = 'kpi-pill pill-success';
    else if (syn.verdict === 'a_surveiller') elVerdict.className = 'kpi-pill pill-warning';
    else elVerdict.className = 'kpi-pill pill-danger';

    // Scores
    const scores = syn.scores || {};
    document.getElementById('kpi-score-topo').textContent = `${scores.topologie ?? '--'}%`;
    if (syn.connectivite) {
        document.getElementById('kpi-topo-detail').textContent = `Résolu: ${syn.connectivite.taux_resolution_pct ?? 0}%`;
    }

    const alti = syn.altimetrie || {};
    document.getElementById('kpi-score-alti').textContent = `${scores.hydraulique ?? '--'}%`;
    document.getElementById('kpi-alti-detail').textContent = `À compléter: ${alti.nb_donnees_manquantes ?? 0}`;

    // Anomalies
    const anom = syn.anomalies || {};
    const ouvertes = (anom.par_severite?.critique || 0) + (anom.par_severite?.majeure || 0) + (anom.par_severite?.mineure || 0);
    document.getElementById('kpi-anom-ouvertes').textContent = ouvertes;
    document.getElementById('kpi-anom-total').textContent = `Total: ${anom.total ?? 0}`;

    // Top action globale (secours quand aucune anomalie n'est affichée)
    const topActions = syn.top_actions || [];
    const hintEl = document.getElementById('top-action-hint');
    if (topActions.length > 0) {
        _topActionGlobalHtml = `<strong>Action prioritaire :</strong> ${topActions[0].libelle} (${topActions[0].nb_ouvertes} cas)`;
    } else {
        _topActionGlobalHtml = null;
    }
    if (hintEl) {
        hintEl.innerHTML = _topActionGlobalHtml || '';
    }
}

// 5. Filtrage et mise à jour de la carte + file
function filtrerEtMettreAJourCarte() {
    if (!currentAnomaliesGeoJSON || !currentAnomaliesGeoJSON.features) return;

    const catFiltre = document.getElementById('filter-categorie').value;
    const sevFiltre = document.getElementById('filter-severite').value;
    const statFiltre = document.getElementById('filter-statut').value;
    const inclureN3 = document.getElementById('chk-toggle-n3').checked;

    clusterGroup.clearLayers();
    currentQueueList = [];
    const markersToAdd = [];

    const bounds = L.latLngBounds([]);

    currentAnomaliesGeoJSON.features.forEach(feat => {
        const p = feat.properties;
        const coords = feat.geometry?.coordinates;
        if (!coords || coords.length < 2) return;

        // Filtres
        if (catFiltre && p.categorie !== catFiltre) return;
        if (sevFiltre && p.severite !== sevFiltre) return;
        if (statFiltre && (p.statut || 'a_traiter') !== statFiltre) return;

        // Filtre N3 Données Manquantes (désactivé par défaut)
        if (p.categorie === 'donnees_manquantes' && !inclureN3 && !catFiltre && sevFiltre !== 'informatif') {
            return;
        }

        const lat = coords[1];
        const lon = coords[0];
        const latLng = L.latLng(lat, lon);
        bounds.extend(latLng);

        // Couleur icône
        let color = 'var(--sev-informatif)';
        if (p.severite === 'critique') color = 'var(--sev-critique)';
        else if (p.severite === 'majeure') color = 'var(--sev-majeure)';
        else if (p.severite === 'mineure') color = 'var(--sev-mineure)';

        const marker = L.circleMarker(latLng, {
            radius: p.severite === 'critique' ? 7 : (p.severite === 'majeure' ? 6 : 4),
            fillColor: color,
            color: '#ffffff',
            weight: 1.5,
            opacity: 1,
            fillOpacity: 0.9,
            severite: p.severite
        });

        // Popup rapide
        marker.bindPopup(`
            <div style="font-size:12px; min-width:200px;">
                <div style="font-weight:700; margin-bottom:4px; color:${color};">${libelleCategorie(p.categorie).toUpperCase()}</div>
                <div><strong>Tronçon:</strong> ${p.id_conduite || p.cle_anomalie?.substring(0,8)}</div>
                <div style="margin:4px 0; color:#334155;">${p.description || ''}</div>
                <div style="display:flex; justify-content:space-between; margin-top:6px; align-items:center;">
                    <span class="badge-sev badge-${p.severite}">${p.severite}</span>
                    <span style="font-size:11px; font-weight:600;">Statut: ${p.statut || 'a_traiter'}</span>
                </div>
            </div>
        `);

        marker.on('click', () => {
            const idx = currentQueueList.findIndex(item => item.properties.cle_anomalie === p.cle_anomalie);
            if (idx >= 0) {
                currentQueueIndex = idx;
                afficherFicheAnomalie(currentQueueList[currentQueueIndex], false);
                mettreAJourCompteurQueue();
            }
        });

        markersToAdd.push(marker);
        currentQueueList.push({ feature: feat, marker: marker, properties: p });
    });

    // Ajout ultra-rapide par lots via addLayers
    if (markersToAdd.length > 0) {
        clusterGroup.addLayers(markersToAdd);
    }

    // Ajuster la vue carte si des points existent
    if (bounds.isValid() && currentQueueList.length > 0) {
        globalBoundsReseau = bounds;
        map.fitBounds(bounds, { padding: [30, 30], maxZoom: 16 });
    }

    // Réinitialiser la file navigable avec zoom direct sur l'anomalie
    currentQueueIndex = 0;
    if (currentQueueList.length > 0) {
        afficherFicheAnomalie(currentQueueList[0], true);
    } else {
        if (highlightMarker) {
            map.removeLayer(highlightMarker);
            highlightMarker = null;
        }
        effacerContexteReseau();
        const hintElVide = document.getElementById('top-action-hint');
        if (hintElVide) hintElVide.innerHTML = _topActionGlobalHtml || '';
        document.getElementById('fiche-container').innerHTML = `
            <div style="color:var(--text-muted); text-align:center; padding:40px 10px;">
                Aucune anomalie ne correspond aux filtres sélectionnés.
            </div>
        `;
    }
    mettreAJourCompteurQueue();
    remplirTableauRecapitulatif();
}

// 6. Navigation dans la file
