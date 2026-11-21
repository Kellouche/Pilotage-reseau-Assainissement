/**
 * ================================================================================
 * Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
 * Auteur : Dr Abdelhakim KELLOUCHE
 * Date de création : 2026-04-20
 * Date de modification : 2026-11-08
 * Objet : Synchronisation du bandeau de bassin, zoom proportionnel et dropdown
 * ================================================================================
 */

// ==========================================
        // FIABILITÉ DU MODÈLE (agent garde-fou hydraulicien)
        // ==========================================
        const _FIABILITE_META = {
            'SAIN':       { label: 'Modèle sain',      icon: '🟢', color: '#34d399', bg: 'rgba(52,211,153,0.15)',  border: 'rgba(52,211,153,0.45)' },
            'A_VERIFIER': { label: 'À vérifier',      icon: '🟠', color: '#fbbf24', bg: 'rgba(251,191,36,0.15)',  border: 'rgba(251,191,36,0.45)' },
            'DEGRADE':    { label: 'Modèle dégradé',  icon: '🔴', color: '#f87171', bg: 'rgba(248,113,113,0.15)', border: 'rgba(248,113,113,0.45)' },
        };

        // Extrait le verdict du garde-fou depuis une réponse simulation
        // (forme complète /bassin|/run, liste /simulations ou cache).
        window._fiabiliteDepuisSimulation = function(sim) {
            if (!sim) return null;
            if (sim.fiabilite_modele) return sim.fiabilite_modele;
            const rs = sim.result_summary || sim.summary_kpis || {};
            if (rs.fiabilite_modele) return rs.fiabilite_modele;
            const ae = sim.agents_expertise || {};
            const gf = ae.controle_modele_hydraulique || {};
            return gf.fiabilite_modele || null;
        };

        window._anomaliesDepuisSimulation = function(sim) {
            if (!sim) return [];
            const ae = sim.agents_expertise || {};
            const gf = ae.controle_modele_hydraulique || {};
            return gf.anomalies || [];
        };

        // Met à jour le badge de fiabilité de la pilule topbar.
        function _majBadgeFiabiliteTopbar(verdict, anomalies) {
            const el = document.getElementById('topbar-bassin-fiabilite');
            if (!el) return;
            const meta = _FIABILITE_META[verdict];
            if (!meta) { el.style.display = 'none'; return; }
            el.style.display = 'inline-block';
            el.textContent = `${meta.icon} ${meta.label}`;
            el.style.color = meta.color;
            el.style.background = meta.bg;
            el.style.borderColor = meta.border;
            const msgs = (anomalies || []).map(a => `• [${a.severite || '?'}] ${a.message || a.code || ''}`).join('\n');
            el.title = msgs
                ? `Fiabilité du modèle : ${verdict}\n${msgs}`
                : `Fiabilité du modèle : ${verdict} (agent garde-fou hydraulicien)`;
        }

        // Charge une fois la liste des simulations pour connaître la
        // fiabilité de chaque bassin, puis décore le sélecteur.
        let _fiabiliteChargee = false;
        function _chargerFiabiliteParBassin() {
            if (_fiabiliteChargee) { _decorerOptionsFiabilite(); return; }
            _fiabiliteChargee = true;
            const token = localStorage.getItem('swmm_access_token');
            const headers = token ? { 'Authorization': `Bearer ${token}` } : {};
            fetch('/api/v1/simulations?limit=200', { headers, credentials: 'include' })
                .then(r => r.ok ? r.json() : [])
                .then(list => {
                    window._fiabiliteParBassin = {};
                    const curProjId = (window._contexteSpatial && window._contexteSpatial.projectId)
                        || (window._rawNetworkData && (window._rawNetworkData.project_id || window._rawNetworkData.project_name))
                        || null;
                    (Array.isArray(list) ? list : []).forEach(s => {
                        if (!s || s.status !== 'completed') return;
                        if (curProjId && s.project_id && String(s.project_id) !== String(curProjId)) return;
                        const cid = s.cluster_id !== undefined && s.cluster_id !== null ? String(s.cluster_id) : null;
                        if (!cid) return;
                        const verdict = window._fiabiliteDepuisSimulation(s);
                        if (!verdict) return;
                        // Conserver la simulation la plus récente par bassin
                        const prev = window._fiabiliteParBassin[cid];
                        const tNew = s.completed_at || s.created_at || '';
                        const tOld = prev ? (prev.completed_at || prev.created_at || '') : '';
                        if (!prev || tNew >= tOld) window._fiabiliteParBassin[cid] = s;
                    });
                    _decorerOptionsFiabilite();
                })
                .catch(() => {});
        }

        // Préfixe les options du sélecteur de bassins d'une pastille
        // colorée selon la fiabilité de la dernière simulation.
        function _decorerOptionsFiabilite() {
            const map = window._fiabiliteParBassin || {};
            const sel = document.getElementById('bassin-select');
            if (!sel) return;
            Array.from(sel.options).forEach(opt => {
                if (!opt.value) return;
                if (opt.dataset.labelBase === undefined) opt.dataset.labelBase = opt.textContent;
                const sim = map[String(opt.value)];
                // Vérifier que la simulation correspond effectivement à ce bassin avant d'afficher un verdict
                const estConforme = sim && (typeof _simCorrespondAuBassin === 'function' ? _simCorrespondAuBassin(sim, String(opt.value)) : true);
                const verdict = estConforme ? window._fiabiliteDepuisSimulation(sim) : null;
                const meta = verdict ? _FIABILITE_META[verdict] : null;
                opt.textContent = meta ? `${meta.icon} ${opt.dataset.labelBase}` : opt.dataset.labelBase;
            });
        }
        window._decorerOptionsFiabilite = _decorerOptionsFiabilite;

        // ==========================================
        // SYNCHRONISATION INDICATEUR BASSIN / BASSINS EN COURS
        // ==========================================
        // Résout le nom métier d'un bassin : priorise bassin_nom/cluster_nom
        // des métadonnées de simulation (ex. « Chorfa ») plutôt que
        // l'identifiant positionnel cluster_id (« Bassin 0 »).
        function _nomMetierBassin(cidStr, meta) {
            const _depuis = (m) => {
                if (!m) return '';
                return String(m.bassin_nom || m.cluster_nom || '').trim();
            };
            const direct = _depuis(meta);
            if (direct) return direct;
            const _cands = [];
            if (window._simulationsCache && cidStr) {
                _cands.push(window._simulationsCache[cidStr]);
                const _bn = window._bassinNoms && window._bassinNoms[cidStr];
                if (_bn) _cands.push(window._simulationsCache[_bn]);
            }
            if (window._dernierResultatSimulation) _cands.push(window._dernierResultatSimulation);
            for (const _c of _cands) {
                const _cm = (_c && _c.meta) || null;
                if (!_cm) continue;
                const _cidM = String(_cm.cluster_id !== undefined && _cm.cluster_id !== null ? _cm.cluster_id : '');
                const _nm = _depuis(_cm);
                // N'emprunter le nom que si l'identité correspond
                if (_nm && (cidStr === _cidM || _nm === cidStr || _nm.toLowerCase() === String(cidStr).toLowerCase() || !_cidM)) {
                    return _nm;
                }
            }
            if (window._bassinNoms && cidStr && window._bassinNoms[cidStr]) return window._bassinNoms[cidStr];
            const _p = window._bassinProperties && cidStr ? window._bassinProperties[cidStr] : null;
            if (_p) {
                const _pn = String(_p.nom_affiche || _p.nom || _p.nom_exutoire || _p.bassin_nom || '').trim();
                if (_pn && !/^Bassin\s+\d+$/i.test(_pn)) return _pn;
            }
            return cidStr ? `Bassin ${cidStr}` : 'Tous les bassins';
        }

        // Identité stable d'un bassin du réseau affiché : exutoire_id et
        // bassin_ref résolus depuis le dropdown (#bassin-select porte
        // data-exutoire-id / data-bassin-ref) ou les propriétés GeoJSON.
        // Le NOM d'un bassin n'est jamais une identité : plusieurs bassins
        // homonymes (« Chorfa ») coexistent dans un même réseau.
        function _identiteBassinStable(cidStr) {
            const cid = (cidStr === null || cidStr === undefined) ? '' : String(cidStr).trim();
            if (!cid) return { exutoireId: '', basinRef: '' };
            const sel = document.getElementById('bassin-select');
            if (sel) {
                for (const opt of sel.options) {
                    if (String(opt.value) === cid) {
                        return {
                            exutoireId: String(opt.dataset.exutoireId || '').trim().toLowerCase(),
                            basinRef: String(opt.dataset.bassinRef || '').trim().toLowerCase()
                        };
                    }
                }
            }
            const p = window._bassinProperties && window._bassinProperties[cid];
            if (p) {
                const ex = (p.exutoire_id !== undefined && p.exutoire_id !== null)
                    ? String(p.exutoire_id).trim().toLowerCase() : '';
                const br = p.bassin_ref ? String(p.bassin_ref).trim().toLowerCase()
                    : (ex ? 'exutoire:' + ex : '');
                return { exutoireId: ex, basinRef: br };
            }
            return { exutoireId: '', basinRef: '' };
        }

        // La simulation `sim` appartient-elle au bassin `cidStr` ?
        // Correspondance par IDENTITÉ STABLE uniquement : cluster_id
        // positionnel exact, exutoire_id ou bassin_ref. meta.cluster_id
        // d'une simulation ciblée est dans l'espace exutoire
        // (ex. « 0_rejets_346980 »), pas dans l'espace cluster_id.
        function _simCorrespondAuBassin(sim, cidStr) {
            const m = sim && sim.meta;
            const cid = (cidStr === null || cidStr === undefined) ? '' : String(cidStr).trim();
            if (!m || !cid) return false;
            const cidLow = cid.toLowerCase();
            const mCid = String(m.cluster_id !== undefined && m.cluster_id !== null ? m.cluster_id : '').trim().toLowerCase();
            if (!mCid) return false;
            if (mCid === cidLow) return true;
            const exSim = new Set();
            const refSim = new Set();
            for (const v of [m.exutoire_noeud, m.exutoire_id, m.bassin_ref]) {
                const s = (v === undefined || v === null) ? '' : String(v).trim().toLowerCase();
                if (!s) continue;
                if (s.indexOf('exutoire:') === 0) refSim.add(s); else exSim.add(s);
            }
            exSim.add(mCid);                    // meta.cluster_id peut être un exutoire
            refSim.add('exutoire:' + mCid);
            const idB = _identiteBassinStable(cid);
            if (idB.exutoireId && exSim.has(idB.exutoireId)) return true;
            if (idB.bassinRef) {
                if (refSim.has(idB.bassinRef)) return true;
                const nu = idB.bassinRef.indexOf('exutoire:') === 0
                    ? idB.bassinRef.slice(9) : idB.bassinRef;
                if (exSim.has(nu)) return true;
            }
            return false;
        }
        window._simCorrespondAuBassin = _simCorrespondAuBassin;

        // Retrouve l'option #bassin-select (cluster_id positionnel) qui
        // correspond à la simulation dont la meta porte un identifiant
        // potentiellement dans l'espace exutoire. Retourne null si aucune
        // correspondance ou si plusieurs bassins candidats existent
        // (jamais de devinette entre homonymes).
        window._optionBassinPourMetaSim = function(meta) {
            const sel = document.getElementById('bassin-select');
            if (!sel || !meta) return null;
            const mid = String(meta.cluster_id !== undefined && meta.cluster_id !== null ? meta.cluster_id : '').trim().toLowerCase();
            const mEx = String(meta.exutoire_noeud || meta.exutoire_id || '').trim().toLowerCase();
            const mRef = String(meta.bassin_ref || '').trim().toLowerCase();
            const cibles = new Set([mid, mEx, mRef].filter(Boolean));
            if (!cibles.size) return null;
            let trouve = null;
            let ambigue = false;
            for (const opt of sel.options) {
                if (!opt.value) continue;
                const v = String(opt.value).trim().toLowerCase();
                const ex = String(opt.dataset.exutoireId || '').trim().toLowerCase();
                const br = String(opt.dataset.bassinRef || '').trim().toLowerCase();
                const brNu = br.indexOf('exutoire:') === 0 ? br.slice(9) : br;
                const ok = cibles.has(v) || cibles.has(ex) || cibles.has(br) || cibles.has(brNu)
                    || cibles.has('exutoire:' + v);
                if (ok) {
                    if (trouve !== null && trouve !== opt.value) { ambigue = true; break; }
                    trouve = opt.value;
                }
            }
            return ambigue ? null : trouve;
        };

        window.mettreAJourIndicateurBassin = function(clusterId, state = {}) {
            const topPill = document.getElementById('topbar-bassin-pill');
            const topIcon = document.getElementById('topbar-bassin-icon');
            const topText = document.getElementById('topbar-bassin-text');
            const topBadge = document.getElementById('topbar-bassin-badge');
            const topFiab = document.getElementById('topbar-bassin-fiabilite');
            const topReset = document.getElementById('topbar-bassin-reset-btn');
            if (topFiab) topFiab.style.display = 'none';

            const cidStr = (clusterId !== null && clusterId !== undefined && clusterId !== '') ? String(clusterId) : null;
            const totalBassins = (window._clustersData && window._clustersData.clusters_crees) || (window._bassinNoms ? Object.keys(window._bassinNoms).length : '--') || '--';

            // État 1 : Simulation en cours
            if (state.status === 'simulating') {
                const nom = _nomMetierBassin(cidStr, state && state.meta ? state.meta : null);
                if (topIcon) topIcon.innerHTML = '<i class="fas fa-circle-notch fa-spin" style="color: #fbbf24;"></i>';
                if (topText) topText.innerHTML = `Simulation en cours : <span style="color: #fbbf24; font-weight: 700;">${nom}</span>`;
                if (topBadge) {
                    topBadge.innerText = 'CALCUL SWMM 5.2';
                    topBadge.style.background = 'rgba(245, 158, 11, 0.2)';
                    topBadge.style.color = '#f59e0b';
                }
                if (topReset) topReset.style.display = 'none';
                return;
            }

            // Détection automatique si le bassin possède une simulation active ou mise en cache.
            // Les payloads persistés (/bassin/{id}, /resultat, historique)
            // portent status='success' et les débits dans .kpis — on les
            // accepte aussi, sinon une sim affichée serait étiquetée
            // « (non simulé) » à tort.
            let simActive = null;
            const _flows = (state && state.kpis) ? state.kpis : state;
            const _aDebits = !!(_flows && (_flows.q_genere_m3s !== undefined || _flows.peak_flow !== undefined || _flows.q_exutoire_m3s !== undefined));
            if (_aDebits && (state.status === 'simulated' || state.status === 'success' || state.conduit_results)) {
                simActive = state;
            } else if (cidStr) {
                // Correspondance par identité stable uniquement : le nom
                // du bassin ne suffit pas (homonymes « Chorfa »…).
                const lastSim = window._dernierResultatSimulation;
                if (lastSim && lastSim.meta && _simCorrespondAuBassin(lastSim, cidStr)) {
                    simActive = lastSim;
                }
                if (!simActive && window._simulationsCache) {
                    for (const _k of Object.keys(window._simulationsCache)) {
                        const _cand = window._simulationsCache[_k];
                        if (_cand && _cand.status !== 'failed' && _simCorrespondAuBassin(_cand, cidStr)) {
                            simActive = _cand;
                            break;
                        }
                    }
                }
            }

            // État 2 : Simulation terminée avec succès (Affichage des métriques hydrauliques complètes)
            if (simActive) {
                const kp = simActive.kpis || simActive;
                const m = simActive.meta || {};
                const nom = _nomMetierBassin(cidStr, m);

                const qExutoire = (kp.q_exutoire_m3s !== undefined) ? parseFloat(kp.q_exutoire_m3s) : (kp.peak_flow ? parseFloat(kp.peak_flow) : (kp.peak_outflow_m3s ? parseFloat(kp.peak_outflow_m3s) : 0.0));
                const qDerive = (kp.q_derive_m3s !== undefined) ? parseFloat(kp.q_derive_m3s) : (kp.q_deleste_ls ? (parseFloat(kp.q_deleste_ls) / 1000.0) : (kp.q_deleste_m3s ? parseFloat(kp.q_deleste_m3s) : 0.0));
                const qGenere = (kp.q_genere_m3s !== undefined) ? parseFloat(kp.q_genere_m3s) : (qExutoire + qDerive);
                const nbRacc = parseInt(kp.nb_ouvrages_raccordes || 0, 10);
                const tauxDerive = (kp.taux_derive_pct !== undefined) ? parseFloat(kp.taux_derive_pct) : (qGenere > 0 ? ((qDerive / qGenere) * 100.0) : 0.0);
                const tauxExutoire = (kp.taux_exutoire_pct !== undefined) ? parseFloat(kp.taux_exutoire_pct) : Math.max(0, 100.0 - tauxDerive);

                const qGenereStr = window.formaterNombre(qGenere, 3);
                const qExutoireStr = window.formaterNombre(qExutoire, 3);
                const qDeriveStr = window.formaterNombre(qDerive, 3);
                const tauxDeriveStr = window.formaterNombre(tauxDerive, 1);
                const tauxExutoireStr = window.formaterNombre(tauxExutoire, 1);

                if (topIcon) topIcon.innerHTML = '<i class="fas fa-water" style="color: #34d399;"></i>';
                if (topText) topText.innerHTML = `Bassin : <span style="color: #34d399; font-weight: 700;">${nom}</span>`;
                if (topBadge) topBadge.style.display = 'none';
                if (topFiab) topFiab.style.display = 'none';
                if (topReset) topReset.style.display = 'inline-block';
                if (typeof window.actualiserDropdownBassin === 'function') {
                    window.actualiserDropdownBassin();
                }
                return;
            }

            // État 3 : Aucun bassin individuel sélectionné (Mode Réseau Global)
            if (!cidStr) {
                if (topIcon) topIcon.innerHTML = '<i class="fas fa-network-wired" style="color: #38bdf8;"></i>';
                if (topText) topText.innerHTML = `Bassins : <span style="color: #38bdf8; font-weight: 700;">Tous les bassins</span>`;
                if (topBadge) {
                    topBadge.style.display = 'inline-block';
                    topBadge.innerText = `${totalBassins} BV`;
                    topBadge.style.background = 'rgba(56, 189, 248, 0.15)';
                    topBadge.style.color = '#38bdf8';
                }
                if (topFiab) topFiab.style.display = 'none';
                if (topReset) topReset.style.display = 'none';
                if (typeof window.actualiserDropdownBassin === 'function') {
                    window.actualiserDropdownBassin();
                }
                return;
            }

            // État 3bis : Ouvrage / Exutoire isolé sans réseau collecteur amont
            const estIsole = Boolean(window._bassinsIsoleIds && window._bassinsIsoleIds.has(cidStr));
            if (estIsole) {
                const nomIsole = (window._bassinNoms && window._bassinNoms[cidStr]) || `Ouvrage ${cidStr}`;
                if (topIcon) topIcon.innerHTML = '<i class="fas fa-map-pin" style="color: #fbbf24;"></i>';
                if (topText) topText.innerHTML = `Ouvrage isolé : <span style="color: #fbbf24; font-weight: 700;">${nomIsole}</span>`;
                if (topBadge) {
                    topBadge.style.display = 'inline-block';
                    topBadge.innerText = 'ISOLÉ (NON SIMULABLE)';
                    topBadge.style.background = 'rgba(245, 158, 11, 0.2)';
                    topBadge.style.color = '#fbbf24';
                }
                if (topFiab) topFiab.style.display = 'none';
                if (topReset) topReset.style.display = 'inline-block';
                if (typeof window.actualiserDropdownBassin === 'function') {
                    window.actualiserDropdownBassin();
                }
                const legNonSim = document.getElementById('sim-floating-legend');
                if (legNonSim) {
                    legNonSim.classList.remove('active-legend');
                    legNonSim.style.display = 'none';
                }
                return;
            }

            // État 4 : Un bassin individuel est sélectionné (Extraction robuste des métadonnées)
            let nom = (window._bassinNoms && window._bassinNoms[cidStr]) ? window._bassinNoms[cidStr] : `Bassin ${cidStr}`;
            let surfHa = '';
            let nbRegards = '';
            let nbConduites = '';
            let longStr = '';
            let bColor = '#38bdf8';

            // 1. Recherche prioritaire dans le dictionnaire direct indexé
            let p = window._bassinProperties ? window._bassinProperties[cidStr] : null;
            if (!p && window._bassinProperties && window._bassinNoms && window._bassinNoms[cidStr]) {
                p = window._bassinProperties[window._bassinNoms[cidStr]];
            }

            // 2. Recherche de secours dans les couches GeoJSON
            if (!p && couches && couches.bassins) {
                couches.bassins.eachLayer(l => {
                    const f = l.feature;
                    if (f && f.properties && f.properties.type === 'bassin_urbain') {
                        if (String(f.properties.cluster_id) === cidStr || String(f.properties.nom) === cidStr) {
                            p = f.properties;
                        }
                    }
                });
            }
            if (!p && window._activeClusterLayer) {
                window._activeClusterLayer.eachLayer(l => {
                    const f = l.feature;
                    if (f && f.properties && f.properties.type === 'bassin_urbain') {
                        if (String(f.properties.cluster_id) === cidStr || String(f.properties.nom) === cidStr) {
                            p = f.properties;
                        }
                    }
                });
            }
            if (!p && window._clustersData && Array.isArray(window._clustersData.features)) {
                const match = window._clustersData.features.find(f => f.properties && f.properties.type === 'bassin_urbain' && (String(f.properties.cluster_id) === cidStr || String(f.properties.nom) === cidStr));
                if (match) p = match.properties;
            }

            if (p) {
                if (p.nom) nom = p.nom;
                if (p.surface_ha !== undefined && p.surface_ha !== null) surfHa = `${Number(p.surface_ha).toFixed(2)} ha`;
                if (p.nb_regards !== undefined && p.nb_regards !== null) nbRegards = `${p.nb_regards} reg.`;
                if (p.nb_conduites !== undefined) nbConduites = `${p.nb_conduites} cond.`;
                else if (p.nb_troncons !== undefined) nbConduites = `${p.nb_troncons} cond.`;
                if (p.longueur_totale_m) longStr = `(${Math.round(p.longueur_totale_m)} m)`;
                if (p.couleur) bColor = p.couleur;
            }

            if (topIcon) topIcon.innerHTML = `<i class="fas fa-draw-polygon" style="color: ${bColor};"></i>`;
            if (topText) topText.innerHTML = `Bassin : <span style="color: #f8fafc; font-weight: 700;">${nom}</span>`;
            if (topBadge) {
                topBadge.style.display = 'inline-block';
                topBadge.innerText = surfHa || (nbRegards ? `${nbRegards}` : `ID ${cidStr}`);
                topBadge.style.background = 'rgba(56, 189, 248, 0.15)';
                topBadge.style.color = '#38bdf8';
            }
            if (topFiab) topFiab.style.display = 'none';
            if (topReset) topReset.style.display = 'inline-block';
            if (typeof window.actualiserDropdownBassin === 'function') {
                window.actualiserDropdownBassin();
            }

            // Masquer immédiatement la légende car sans objet pour un bassin non simulé
            const legNonSim = document.getElementById('sim-floating-legend');
            if (legNonSim) {
                legNonSim.classList.remove('active-legend');
                legNonSim.style.display = 'none';
            }
        };

        // GESTION AUTOMATIQUE DE L'AFFICHAGE DE SIMULATION PAR BASSIN
        // Garantit la cohérence stricte : n'affiche jamais la simulation d'un autre bassin
        window.gererAffichageSimulationPourBassin = function(clusterId) {
            const leg = document.getElementById('sim-floating-legend');
            const legTitle = document.querySelector('#sim-floating-legend span');

            if (!clusterId) {
                // Mode Réseau Global : nettoyer l'affichage des résultats SWMM
                if (typeof reinitialiserAffichageSimulation === 'function') {
                    reinitialiserAffichageSimulation();
                }
                if (leg) {
                    leg.classList.remove('active-legend');
                    leg.style.display = 'none';
                }
                if (legTitle) legTitle.innerHTML = `<i class="fas fa-layer-group me-1"></i> Légende SWMM 5.2`;
                return;
            }

            const cidStr = String(clusterId);
            const nomBassin = (window._bassinNoms && window._bassinNoms[cidStr]) || cidStr;

            // 1. Vérifier si la simulation actuellement affichée correspond déjà à ce bassin
            //    (identité stable : cluster_id / exutoire / bassin_ref — jamais le nom)
            if (window._dernierResultatSimulation && _simCorrespondAuBassin(window._dernierResultatSimulation, cidStr)) {
                const m = window._dernierResultatSimulation.meta || {};
                const mNom = String(m.bassin_nom || m.cluster_nom || '');
                if (leg) {
                    leg.classList.add('active-legend');
                    leg.style.display = 'block';
                }
                if (legTitle) {
                    legTitle.innerHTML = `<i class="fas fa-layer-group me-1"></i> SWMM 5.2 — ${mNom || nomBassin}`;
                }
                return;
            }

            // 2. Nettoyage immédiat : ne jamais laisser flotter la simulation d'un autre bassin
            if (typeof reinitialiserAffichageSimulation === 'function') {
                reinitialiserAffichageSimulation();
            }
            if (leg) {
                leg.classList.remove('active-legend');
                leg.style.display = 'none';
            }

            // 3. Vérifier si ce bassin a une simulation dans le cache client
            //    (identité stable — la clé « nom » du cache est ambiguë entre
            //    bassins homonymes, on vérifie toujours meta avant d'accepter)
            let cached = null;
            if (window._simulationsCache) {
                const _direct = window._simulationsCache[cidStr] || (nomBassin && window._simulationsCache[nomBassin]);
                if (_direct && _simCorrespondAuBassin(_direct, cidStr)) {
                    cached = _direct;
                } else {
                    for (const _k of Object.keys(window._simulationsCache)) {
                        const _cand = window._simulationsCache[_k];
                        if (_cand && _cand.status === 'success' && _simCorrespondAuBassin(_cand, cidStr)) {
                            cached = _cand;
                            break;
                        }
                    }
                }
            }

            if (cached && cached.status === 'success' && cached.conduit_results && Object.keys(cached.conduit_results).length > 0) {
                window._dernierResultatSimulation = cached;
                afficherResultatsSimulation(cached);
                if (leg) {
                    leg.classList.add('active-legend');
                    leg.style.display = 'block';
                }
                if (legTitle) {
                    const dispNom = (cached.meta && (cached.meta.cluster_nom || cached.meta.bassin_nom)) || nomBassin;
                    legTitle.innerHTML = `<i class="fas fa-layer-group me-1"></i> SWMM 5.2 — ${dispNom}`;
                }
                if (typeof window.mettreAJourIndicateurBassin === 'function') {
                    window.mettreAJourIndicateurBassin(cidStr, cached);
                }
                return;
            }

            // 3. Interroger le serveur pour charger la simulation enregistrée de ce bassin
            const token = localStorage.getItem('swmm_access_token');
            const headers = token ? { 'Authorization': `Bearer ${token}` } : {};
            fetch('/api/v1/simulations/bassin/' + encodeURIComponent(cidStr), { headers, credentials: 'include' })
                .then(r => r.json())
                .then(d => {
                    // Vérifier que l'utilisateur est toujours sur ce bassin
                    if (_selectedClusterId !== cidStr) return;

                    if (d && d.status === 'success' && d.conduit_results && Object.keys(d.conduit_results).length > 0) {
                        if (!window._simulationsCache) window._simulationsCache = {};
                        window._simulationsCache[cidStr] = d;
                        if (nomBassin) window._simulationsCache[nomBassin] = d;
                        if (window._fiabiliteParBassin) window._fiabiliteParBassin[cidStr] = d;
                        window._dernierResultatSimulation = d;
                        afficherResultatsSimulation(d);
                        if (leg) {
                            leg.classList.add('active-legend');
                            leg.style.display = 'block';
                        }
                        if (legTitle) {
                            const dispNom = (d.meta && (d.meta.cluster_nom || d.meta.bassin_nom)) || nomBassin;
                            legTitle.innerHTML = `<i class="fas fa-layer-group me-1"></i> SWMM 5.2 — ${dispNom}`;
                        }
                        if (typeof window.mettreAJourIndicateurBassin === 'function') {
                            window.mettreAJourIndicateurBassin(cidStr, d);
                        }
                    } else {
                        // Aucun calcul sauvegardé pour ce bassin : nettoyer les résultats précédents
                        if (typeof reinitialiserAffichageSimulation === 'function') {
                            reinitialiserAffichageSimulation();
                        }
                        if (leg) {
                            leg.classList.remove('active-legend');
                            leg.style.display = 'none';
                        }
                        if (typeof window.mettreAJourIndicateurBassin === 'function') {
                            window.mettreAJourIndicateurBassin(cidStr, { status: 'unsimulated' });
                        }
                    }
                })
                .catch(err => {
                    console.warn("Vérification simulation bassin:", err);
                    if (_selectedClusterId === cidStr) {
                        if (typeof reinitialiserAffichageSimulation === 'function') {
                            reinitialiserAffichageSimulation();
                        }
                        if (leg) {
                            leg.classList.remove('active-legend');
                            leg.style.display = 'none';
                        }
                        if (typeof window.mettreAJourIndicateurBassin === 'function') {
                            window.mettreAJourIndicateurBassin(cidStr, { status: 'unsimulated' });
                        }
                    }
                });
        };

        window.reinitialiserSelectionBassin = function(e) {
            if (e && e.stopPropagation) e.stopPropagation();
            _selectedClusterId = null;
            const sel = document.getElementById('bassin-select');
            if (sel) sel.value = '';
            const selIsole = document.getElementById('isoles-select');
            if (selIsole) selIsole.value = '';
            const infoIsole = document.getElementById('isoles-info');
            if (infoIsole) infoIsole.style.display = 'none';
            window._selectedIsolateId = null;
            const simSel = document.getElementById('sim-select-bassin');
            if (simSel) simSel.value = '';
            highlightCluster(null, window._activeClusterLayer || couches.bassins);
            afficherInfoBassin(null);
            if (window._activeClusterLayer && window._activeClusterLayer.getBounds && window._activeClusterLayer.getBounds().isValid()) {
                carte.fitBounds(window._activeClusterLayer.getBounds(), { padding: [50, 50] });
            }
            window.mettreAJourIndicateurBassin(null);
        };

        function highlightCluster(clusterId, geojsonLayer) {
            _selectedClusterId = (clusterId === null || clusterId === undefined || clusterId === '') ? null : String(clusterId);
            window._selectedClusterId = _selectedClusterId;
            window.mettreAJourIndicateurBassin(_selectedClusterId);
            // Sous-bassins Voronoï : refiltrer surfaces/ha sur le bassin choisi
            if (typeof window.filtrerSousBassinsPourBassin === 'function') {
                window.filtrerSousBassinsPourBassin(_selectedClusterId);
            }

            // Mémoriser le dernier bassin ouvert, cloisonné par projet —
            // permet à l'application de se rouvrir sur le même bassin.
            try {
                const _pn = (window._rawNetworkData && (window._rawNetworkData.project_name || window._rawNetworkData.project_id)) || null;
                if (_selectedClusterId) {
                    localStorage.setItem('drainpilot_dernier_bassin', JSON.stringify({ projet: _pn, cluster: _selectedClusterId }));
                } else {
                    localStorage.removeItem('drainpilot_dernier_bassin');
                }
            } catch (e) {}

            // Synchroniser les dropdowns si l'appel vient du clic carte
            if (typeof window.synchroniserSelectionBassinOuIsole === 'function') {
                window.synchroniserSelectionBassinOuIsole(_selectedClusterId);
            } else {
                const sel = document.getElementById('bassin-select');
                if (sel && sel.value !== (_selectedClusterId || '')) {
                    sel.value = _selectedClusterId || '';
                }
            }
            afficherInfoBassin(_selectedClusterId);

            // Synchronisation intelligente et sécurisée de l'affichage de simulation
            if (typeof window.gererAffichageSimulationPourBassin === 'function') {
                window.gererAffichageSimulationPourBassin(_selectedClusterId);
            }

            // Maintenir systématiquement cochés et affichés les rejets et la STEP lors du changement de réseau
            if (couches && couches.rejets && !carte.hasLayer(couches.rejets)) couches.rejets.addTo(carte);
            const elRejSync = document.getElementById('f-rejets');
            if (elRejSync) elRejSync.checked = true;

            if (couches && couches.step && !carte.hasLayer(couches.step)) couches.step.addTo(carte);
            const elStepSync = document.getElementById('f-step');
            if (elStepSync) elStepSync.checked = true;

            geojsonLayer = geojsonLayer || window._activeClusterLayer || (typeof couches !== 'undefined' ? couches.bassins : null);
            if (!geojsonLayer) return;

            geojsonLayer.eachLayer(layer => {
                const feature = layer.feature;
                if (!feature) return;

                // Cas 1 : Tronçons (LineString / MultiLineString)
                if (feature.geometry && (feature.geometry.type === 'LineString' || feature.geometry.type === 'MultiLineString')) {
                    const fCid = feature.properties ? String(feature.properties.cluster_id) : '';
                    const cColor = feature.properties ? feature.properties.couleur || '#38bdf8' : '#38bdf8';

                    if (_selectedClusterId === null) {
                        // Vue globale : toutes les conduites ont la couleur de leur bassin
                        layer.setStyle({ color: cColor, weight: 2.4, opacity: 0.85 });
                    } else if (fCid === _selectedClusterId) {
                        // Conduite du bassin sélectionné : mise en valeur éclatante
                        layer.setStyle({ color: cColor, weight: 4.5, opacity: 1.0 });
                        try { layer.bringToFront(); } catch(e) {}
                    } else {
                        // Autre bassin : grisé et discret
                        layer.setStyle({ color: '#475569', weight: 1.2, opacity: 0.18 });
                    }
                }
                // Cas 2 : Polygones de Bassins Versants
                else if (feature.properties && feature.properties.type === 'bassin_urbain') {
                    const fCid = feature.properties ? String(feature.properties.cluster_id) : '';
                    const bColor = feature.properties ? feature.properties.couleur || '#38bdf8' : '#38bdf8';

                    if (_selectedClusterId === null) {
                        // Vue globale : tous les bassins versants colorés
                        layer.setStyle({
                            color: bColor,
                            fillColor: bColor,
                            fillOpacity: 0.18,
                            weight: 1.8,
                            dashArray: '5, 4'
                        });
                    } else if (fCid === _selectedClusterId) {
                        const isSim = (layer._isSimulatedBassin === true) || _simCorrespondAuBassin(window._dernierResultatSimulation, fCid)
                            || (window._simulationsCache && Object.keys(window._simulationsCache).some(_k => {
                                const _c = window._simulationsCache[_k];
                                return _c && _c.status === 'success' && _simCorrespondAuBassin(_c, fCid);
                            }));
                        if (isSim) {
                            // Bassin simulé : maintien impératif de la teinte bleu ciel
                            layer.setStyle({ color: '#0284c7', fillColor: '#38bdf8', fillOpacity: 0.20, weight: 3.5, dashArray: '7, 4' });
                        } else {
                            // Bassin non simulé : actif avec bordure nette et couleur du cluster
                            layer.setStyle({ color: '#ffffff', fillColor: bColor, fillOpacity: 0.45, weight: 3.5, dashArray: null });
                        }
                        try { layer.bringToFront(); } catch(e) {}
                    } else {
                        // Les 78 autres bassins versants : grisés
                        layer.setStyle({
                            color: '#64748b',
                            fillColor: '#334155',
                            fillOpacity: 0.04,
                            weight: 0.8,
                            dashArray: '4, 4'
                        });
                    }
                }
            });

            // Harmoniser également la couche des sous-bassins Voronoï avec la sélection
            if (typeof couches !== 'undefined' && couches.subcatchments && typeof couches.subcatchments.eachLayer === 'function') {
                couches.subcatchments.eachLayer(sbLayer => {
                    const feat = sbLayer.feature;
                    if (!feat || !feat.properties) return;
                    const sbBassinId = (feat.properties.id_bassin !== undefined && feat.properties.id_bassin !== null) ? String(feat.properties.id_bassin) : null;
                    const isOrph = feat.properties.is_orphelin === 1 || feat.properties.is_orphelin === true || !sbBassinId;
                    
                    if (_selectedClusterId === null) {
                        // Vue globale : style standard
                        if (isOrph) {
                            sbLayer.setStyle({ color: '#f59e0b', fillColor: '#f59e0b', fillOpacity: 0.15, weight: 1.0, dashArray: '3, 3' });
                        } else {
                            sbLayer.setStyle({ color: '#059669', fillColor: '#10b981', fillOpacity: 0.18, weight: 1.5, dashArray: '4, 4' });
                        }
                    } else if (sbBassinId === _selectedClusterId) {
                        // Sous-bassin du bassin sélectionné : mise en valeur en arrière-plan du bassin versant
                        sbLayer.setStyle({ color: '#10b981', fillColor: '#10b981', fillOpacity: 0.38, weight: 2.2, dashArray: null });
                    } else {
                        // Autre sous-bassin : estompé
                        sbLayer.setStyle({ color: '#64748b', fillColor: '#334155', fillOpacity: 0.02, opacity: 0.12, weight: 0.5, dashArray: '4, 4' });
                    }
                });
            }
        }

        /**
         * Restaure le dernier bassin ouvert au chargement du réseau.
         * Cloisonné par projet : un bassin d'un autre projet/organisation
         * n'est jamais restauré. Sans effet si le cluster n'existe plus.
         */
        window.restaurerDernierBassin = function () {
            try {
                const brut = localStorage.getItem('drainpilot_dernier_bassin');
                if (!brut) return;
                const d = JSON.parse(brut);
                if (!d || !d.cluster) return;
                const projetCourant = (window._rawNetworkData && (window._rawNetworkData.project_name || window._rawNetworkData.project_id)) || null;
                if (d.projet && projetCourant && String(d.projet) !== String(projetCourant)) return;
                const cid = String(d.cluster);

                // Le cluster doit exister dans le réseau fraîchement chargé
                let existe = false;
                const sel = document.getElementById('bassin-select');
                if (sel) {
                    for (let i = 0; i < sel.options.length; i++) {
                        if (sel.options[i].value === cid) { existe = true; break; }
                    }
                }
                if (!existe && window._clustersData) {
                    existe = !!(window._clustersData[cid] || window._clustersData[Number(cid)]);
                }
                if (!existe) return;

                highlightCluster(cid, window._activeClusterLayer || (typeof couches !== 'undefined' ? couches.bassins : null));
                const gl = window._activeClusterLayer || (typeof couches !== 'undefined' ? couches.bassins : null);
                if (gl && gl.getBounds && gl.getBounds().isValid()) {
                    carte.fitBounds(gl.getBounds(), { padding: [50, 50], maxZoom: 17 });
                }
            } catch (e) {}
        };

        // Synchronise la sélection entre le sélecteur de bassins collecteurs
        // et le sélecteur d'ouvrages/exutoires isolés.
        window.synchroniserSelectionBassinOuIsole = function(cid) {
            const sel = document.getElementById('bassin-select');
            const selIsole = document.getElementById('isoles-select');
            const infoIsole = document.getElementById('isoles-info');
            const cidStr = (cid !== null && cid !== undefined) ? String(cid) : '';

            if (!cidStr) {
                if (sel) sel.value = '';
                if (selIsole) selIsole.value = '';
                if (infoIsole) infoIsole.style.display = 'none';
                window._selectedIsolateId = null;
                return;
            }

            const estIsole = Boolean(window._bassinsIsoleIds && window._bassinsIsoleIds.has(cidStr));

            if (estIsole) {
                if (sel) sel.value = '';
                if (selIsole) selIsole.value = cidStr;
                if (infoIsole) infoIsole.style.display = 'block';
                window._selectedIsolateId = cidStr;
            } else {
                if (sel) sel.value = cidStr;
                if (selIsole) selIsole.value = '';
                if (infoIsole) infoIsole.style.display = 'none';
                window._selectedIsolateId = null;
            }
        };

        function peuplerDropdownBassins(geojsonData, clusterLayer) {
            const sel = document.getElementById('bassin-select');
            const selIsole = document.getElementById('isoles-select');
            const secIsole = document.getElementById('isoles-section');
            const badgeIsole = document.getElementById('badge-isoles-count');
            const infoIsole = document.getElementById('isoles-info');

            _bassinBounds = {};
            _bassinNoms = {};

            // Extraire les bassins (polygones) et construire leurs bounds
            const bassins = geojsonData.features.filter(f => f.properties && f.properties.type === 'bassin_urbain');

            // Séparation stricte : collecteurs simulables vs ouvrages/exutoires isolés
            const collecteurs = [];
            const isoles = [];

            bassins.forEach(f => {
                const cid = f.properties.cluster_id;
                let nom = f.properties.nom || `Bassin ${cid}`;
                // Rendre les identifiants techniques SIG plus conviviaux (ex. 0_rejets_346980 -> Exutoire 346980)
                nom = nom.replace(/^(\d+)_rejets_(\w+)/i, 'Exutoire $2');
                nom = nom.replace(/^(\d+)_ouvrages_speciaux_(\w+)/i, 'Ouvrage $2');
                f.properties.nom_affiche = nom;

                _bassinNoms[String(cid)] = nom;
                if (!window._bassinProperties) window._bassinProperties = {};
                window._bassinProperties[String(cid)] = f.properties;
                // Protection anti-collision homonymes (ex. Carmella 93 ha vs Carmella 0.35 ha) :
                // Ne stocker par clé textuelle 'nom' QUE si non encore enregistré, ou si le candidat actuel a plus de regards
                if (nom) {
                    const existant = window._bassinProperties[String(nom)];
                    if (!existant || (parseInt(f.properties.nb_regards || 0) > parseInt(existant.nb_regards || 0))) {
                        window._bassinProperties[String(nom)] = f.properties;
                        _bassinNoms[String(nom)] = nom;
                    }
                }

                const nbReg = parseInt(f.properties.nb_regards || 0);
                const nbCond = parseInt(f.properties.nb_conduites || 0);
                const surf = parseFloat(f.properties.surface_ha || 0.0);

                // Seuil strict pour les collecteurs simulables :
                // Doit comporter au moins 3 regards ET 3 conduites (ou surface >= 1.0 ha avec au moins 2 conduites).
                // Tout élément avec 1 ou 2 regards est classé dans les ouvrages et exutoires isolés (non simulables).
                const estCollecteur = (nbReg >= 3 && nbCond >= 3) || (surf >= 1.0 && nbCond >= 2);

                if (estCollecteur) {
                    f.properties.est_isole = false;
                    collecteurs.push(f);
                } else {
                    f.properties.est_isole = true;
                    isoles.push(f);
                }
            });

            window._bassinsCollecteurs = collecteurs;
            window._bassinsIsoles = isoles;
            window._bassinsIsoleIds = new Set(isoles.map(f => String(f.properties.cluster_id)));

            // Tri alphabétique strict des deux listes (par nom affiché)
            const triAlphabetique = (a, b) => {
                const nomA = (a.properties.nom_affiche || a.properties.nom || '').trim().toLowerCase();
                const nomB = (b.properties.nom_affiche || b.properties.nom || '').trim().toLowerCase();
                return nomA.localeCompare(nomB, 'fr', { sensitivity: 'base', numeric: true });
            };

            collecteurs.sort(triAlphabetique);
            isoles.sort(triAlphabetique);

            // 1. Peuplement du sélecteur principal (#bassin-select) — STRICTEMENT QUE LES BASSINS COLLECTEURS
            sel.innerHTML = `<option value="">-- Choisir un bassin versant (${collecteurs.length}) --</option>`;
            collecteurs.forEach(f => {
                const cid = f.properties.cluster_id;
                const nom = f.properties.nom_affiche || f.properties.nom || `Bassin ${cid}`;
                const surf = f.properties.surface_ha !== undefined ? ` (${f.properties.surface_ha} ha)` : '';
                const reg = (f.properties.nb_regards && f.properties.nb_regards > 0) ? ` • ${f.properties.nb_regards} reg.` : '';
                const opt = document.createElement('option');
                opt.value = cid;
                if (f.properties.bassin_ref) opt.dataset.bassinRef = f.properties.bassin_ref;
                if (f.properties.exutoire_id !== undefined && f.properties.exutoire_id !== null) {
                    opt.dataset.exutoireId = f.properties.exutoire_id;
                }
                opt.textContent = `${nom}${surf}${reg}`;
                sel.appendChild(opt);
            });

            // 2. Peuplement de la sous-section dédiée aux ouvrages et exutoires isolés (Option A)
            if (selIsole && secIsole) {
                if (isoles.length > 0) {
                    secIsole.style.display = 'block';
                    if (badgeIsole) badgeIsole.textContent = `${isoles.length}`;
                    selIsole.innerHTML = `<option value="">-- Choisir un ouvrage isolé (${isoles.length}) --</option>`;
                    isoles.forEach(f => {
                        const cid = f.properties.cluster_id;
                        const nom = f.properties.nom_affiche || f.properties.nom || `Ouvrage ${cid}`;
                        const surf = f.properties.surface_ha !== undefined ? ` (${f.properties.surface_ha} ha)` : '';
                        const reg = (f.properties.nb_regards && f.properties.nb_regards > 0) ? ` • ${f.properties.nb_regards} reg.` : '';
                        const opt = document.createElement('option');
                        opt.value = cid;
                        if (f.properties.bassin_ref) opt.dataset.bassinRef = f.properties.bassin_ref;
                        if (f.properties.exutoire_id !== undefined && f.properties.exutoire_id !== null) {
                            opt.dataset.exutoireId = f.properties.exutoire_id;
                        }
                        opt.textContent = `📍 ${nom}${surf}${reg}`;
                        selIsole.appendChild(opt);
                    });

                    selIsole.onchange = function() {
                        const cid = this.value;
                        if (sel) sel.value = ''; // Réinitialiser le sélecteur de bassins collecteurs
                        window._selectedIsolateId = cid || null;

                        if (infoIsole) {
                            infoIsole.style.display = cid ? 'block' : 'none';
                        }

                        if (!cid) {
                            highlightCluster(null, clusterLayer);
                            afficherInfoBassin(null);
                            return;
                        }

                        const finalCid = cid.startsWith('M_') ? cid : parseInt(cid);
                        highlightCluster(finalCid, clusterLayer);
                        afficherInfoBassin(finalCid);
                        zoomerSurBassin(finalCid, clusterLayer);
                    };
                } else {
                    secIsole.style.display = 'none';
                    selIsole.innerHTML = '<option value="">-- Aucun ouvrage isolé --</option>';
                    if (badgeIsole) badgeIsole.textContent = '0';
                    if (infoIsole) infoIsole.style.display = 'none';
                }
            }

            // Calculer les bounds de chaque bassin depuis le layer Leaflet (si disponible)
            if (clusterLayer && typeof clusterLayer.eachLayer === 'function') {
                clusterLayer.eachLayer(layer => {
                    const feature = layer.feature;
                    if (!feature || feature.properties.type !== 'bassin_urbain') return;
                    const cid = feature.properties.cluster_id;
                    try {
                        const b = (typeof layer.getBounds === 'function') ? layer.getBounds() : null;
                        if (b && typeof b.isValid === 'function' && b.isValid()) {
                            _bassinBounds[cid] = b;
                            _bassinBounds[String(cid)] = b;
                            if (!isNaN(parseInt(cid))) _bassinBounds[parseInt(cid)] = b;
                        }
                    } catch(e) {}
                });
            }

            // Badges de fiabilité : charger la liste des simulations
            // (une seule fois) pour préfixer les bassins simulés.
            _chargerFiabiliteParBassin();
            window._bassinBounds = _bassinBounds;
            window._bassinNoms = _bassinNoms;

            // Mettre à jour dynamiquement le badge avec le nombre de bassins collecteurs
            const totalCollecteurs = collecteurs.length;
            const badge = document.getElementById('badge-subcatchments-count');
            if (badge && totalCollecteurs > 0) {
                const curText = badge.innerText || '';
                const parts = curText.split('•');
                const sbPart = parts.length > 1 ? parts[parts.length - 1].trim() : (curText.includes('SB') ? curText : '');
                badge.innerText = `${totalCollecteurs} BV${sbPart ? ' • ' + sbPart : ''}`;
            }

            // Afficher la section
            document.getElementById('bassin-section').style.display = 'block';

            // Écouteur du dropdown unique (onchange direct pour éviter les doublons d'écouteurs)
            sel.onchange = function() {
                const cid = this.value;
                if (selIsole) selIsole.value = '';
                if (infoIsole) infoIsole.style.display = 'none';
                window._selectedIsolateId = null;

                // Activer le bouton supprimer SI c'est un bassin manuel
                const btnDelete = document.getElementById('btn-delete-bassin');
                if (btnDelete) {
                    if (cid && String(cid).startsWith('M_')) {
                        btnDelete.disabled = false;
                        btnDelete.style.color = '#e74c3c';
                    } else {
                        btnDelete.disabled = true;
                        btnDelete.style.color = '';
                    }
                }

                if (!cid) {
                    highlightCluster(null, clusterLayer);
                    afficherInfoBassin(null);
                    return;
                }

                const finalCid = cid.startsWith('M_') ? cid : parseInt(cid);
                highlightCluster(finalCid, clusterLayer);
                afficherInfoBassin(finalCid);
                zoomerSurBassin(finalCid, clusterLayer);
            };
        }

        // ==========================================
        // GESTION DU MENU DÉROULANT HIÉRARCHIQUE BASSIN (TOPBAR)
        // ==========================================

        window.basculerMenuBassin = function(e) {
            if (e) {
                if (e.target && e.target.closest('#topbar-bassin-reset-btn')) return;
                e.stopPropagation();
            }
            const d = document.getElementById('topbar-bassin-dropdown');
            if (!d) return;
            const isVisible = d.style.display === 'block';
            if (typeof window.fermerTousLesMenusTopbar === 'function') {
                window.fermerTousLesMenusTopbar(isVisible ? null : 'bassin');
            }
            if (!isVisible) {
                if (typeof window.actualiserDropdownBassin === 'function') {
                    window.actualiserDropdownBassin();
                }
                d.style.display = 'block';
                const chev = document.getElementById('topbar-bassin-chevron');
                if (chev) chev.style.transform = 'rotate(180deg)';
            } else {
                window.fermerMenuBassin();
            }
        };

        window.fermerMenuBassin = function() {
            const d = document.getElementById('topbar-bassin-dropdown');
            if (d) d.style.display = 'none';
            const chev = document.getElementById('topbar-bassin-chevron');
            if (chev) chev.style.transform = 'rotate(0deg)';
        };

        window.actualiserDropdownBassin = function() {
            const dropdown = document.getElementById('topbar-bassin-dropdown');
            if (!dropdown) return;

            const _esc = function(s) {
                return (typeof window.dwfEchapperHtml === 'function')
                    ? window.dwfEchapperHtml(s)
                    : String(s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
            };

            const cidStr = (window._selectedClusterId !== null && window._selectedClusterId !== undefined && window._selectedClusterId !== '')
                ? String(window._selectedClusterId) : null;
            const totalBassins = (window._clustersData && window._clustersData.clusters_crees)
                || (window._bassinNoms ? Object.keys(window._bassinNoms).length : '--') || '--';

            // 1. Vue globale (aucun bassin sélectionné)
            if (!cidStr) {
                const projNom = (window._rawNetworkData && (window._rawNetworkData.project_name || window._rawNetworkData.project_id)) || 'Réseau urbain';
                dropdown.innerHTML = `
                    <div style="padding: 12px 16px; border-bottom: 1px solid rgba(255,255,255,0.1); background: rgba(255,255,255,0.03);">
                        <div style="font-weight: 800; font-size: 13px; color: #38bdf8; display: flex; align-items: center; gap: 8px;">
                            <i class="fas fa-network-wired"></i> Vue globale du réseau
                        </div>
                        <div style="font-size: 11px; color: #94a3b8; margin-top: 3px;">
                            ${_esc(projNom)} · <b>${totalBassins} bassins versants</b>
                        </div>
                    </div>
                    <div style="padding: 12px 16px; font-size: 12px; color: #cbd5e1; line-height: 1.5;">
                        <p style="margin: 0 0 12px 0; color: #94a3b8; font-size: 11px;">
                            Sélectionnez un bassin versant sur la carte pour inspecter ses résultats détaillés, ou configurez et lancez une simulation.
                        </p>
                        <button type="button" onclick="fermerMenuBassin(); if (typeof ouvrirModalSimulation === 'function') ouvrirModalSimulation(true);" style="width: 100%; padding: 8px 12px; background: rgba(56, 189, 248, 0.15); border: 1px solid rgba(56, 189, 248, 0.4); color: #38bdf8; border-radius: 6px; font-size: 11px; font-weight: 700; cursor: pointer; display: flex; align-items: center; justify-content: center; gap: 7px;">
                            <i class="fas fa-play"></i> Configurer et lancer une simulation
                        </button>
                    </div>
                `;
                return;
            }

            // 1bis. Vue Ouvrage/Exutoire isolé sans réseau collecteur amont (non simulable)
            if (cidStr && window._bassinsIsoleIds && window._bassinsIsoleIds.has(cidStr)) {
                const nomIsole = (window._bassinNoms && window._bassinNoms[cidStr]) || `Ouvrage ${cidStr}`;
                const bpIsole = (window._bassinProperties && window._bassinProperties[cidStr]) || {};
                const typOuv = bpIsole.exutoire_type ? String(bpIsole.exutoire_type).toUpperCase() : 'EXUTOIRE';
                dropdown.innerHTML = `
                    <div style="padding: 12px 14px; border-bottom: 1px solid rgba(255,255,255,0.1); background: rgba(245, 158, 11, 0.05);">
                        <div style="font-weight: 800; font-size: 13px; color: #fbbf24; display: flex; align-items: center; gap: 7px;">
                            <i class="fas fa-map-pin"></i> ${_esc(nomIsole)}
                        </div>
                        <div style="font-size: 11px; color: #94a3b8; margin-top: 3px;">
                            Ouvrage ponctuel isolé (${typOuv}) · Aucun réseau collecteur amont
                        </div>
                    </div>
                    <div style="padding: 12px 14px;">
                        <div style="margin: 4px 0 14px 0; padding: 10px 12px; background: rgba(245, 158, 11, 0.12); border: 1px solid rgba(245, 158, 11, 0.3); border-radius: 6px; font-size: 11px; color: #fbbf24; line-height: 1.45;">
                            <div style="font-weight: 800; display: flex; align-items: center; gap: 6px; margin-bottom: 4px;">
                                <i class="fas fa-ban"></i> Non simulable sous SWMM 5.2
                            </div>
                            Cet élément est un exutoire ou regard ponctuel isolé ne disposant d'aucune canalisation collectrice connectée. Les calculs hydrauliques 1D (Saint-Venant) ne peuvent pas lui être appliqués.
                        </div>
                        <div style="display: flex; gap: 6px; padding-top: 8px; border-top: 1px solid rgba(255,255,255,0.08);">
                            <button type="button" disabled title="Simulation impossible sur un ouvrage isolé" style="flex: 1.2; padding: 6px 10px; background: rgba(255, 255, 255, 0.04); border: 1px solid rgba(255, 255, 255, 0.1); color: #64748b; border-radius: 6px; font-size: 11px; font-weight: 700; cursor: not-allowed; display: flex; align-items: center; justify-content: center; gap: 5px;">
                                <i class="fas fa-ban"></i> Non simulable
                            </button>
                            <button type="button" onclick="fermerMenuBassin(); reinitialiserSelectionBassin();" title="Revenir à la vue globale du réseau" style="flex: 0.8; padding: 6px 6px; background: rgba(255, 255, 255, 0.05); border: 1px solid rgba(255, 255, 255, 0.15); color: #cbd5e1; border-radius: 6px; font-size: 11px; font-weight: 600; cursor: pointer; display: flex; align-items: center; justify-content: center; gap: 5px;">
                                <i class="fas fa-globe"></i> Réseau
                            </button>
                        </div>
                    </div>
                `;
                return;
            }

            // 2. Recherche de la simulation associée à ce bassin
            let simActive = null;
            const lastSim = window._dernierResultatSimulation;
            if (lastSim && lastSim.meta && typeof _simCorrespondAuBassin === 'function' && _simCorrespondAuBassin(lastSim, cidStr)) {
                simActive = lastSim;
            }
            if (!simActive && window._simulationsCache) {
                for (const _k of Object.keys(window._simulationsCache)) {
                    const _cand = window._simulationsCache[_k];
                    if (_cand && _cand.status !== 'failed' && typeof _simCorrespondAuBassin === 'function' && _simCorrespondAuBassin(_cand, cidStr)) {
                        simActive = _cand;
                        break;
                    }
                }
            }

            const m = (simActive && simActive.meta) ? simActive.meta : {};
            const kp = (simActive && simActive.kpis) ? simActive.kpis : (simActive || {});
            const nom = (typeof _nomMetierBassin === 'function') ? _nomMetierBassin(cidStr, m) : `Bassin ${cidStr}`;

            // Propriétés du bassin
            const bp = (window._bassinProperties && window._bassinProperties[cidStr]) || {};
            const nbRegards = m.junctions_count || bp.nb_regards || bp.nodes_count || '--';
            const nbTroncons = m.conduits_count || bp.nb_canalisations || bp.pipes_count || '--';
            const surfaceHa = m.total_area_ha ? Number(m.total_area_ha).toFixed(1) : (bp.surface_ha ? Number(bp.surface_ha).toFixed(1) : '--');

            // --- ÉLÉMENT 1 : Simulation (Scénario / Période de retour) ---
            let simBlock = '';
            if (simActive) {
                const tRetour = kp.pluvio_periode_retour || m.pluvio_periode_retour || 'T = 2 ans (Biennale)';
                const scenNom = kp.pluvio_scenario_nom || m.pluvio_scenario_nom || m.scenario || 'Pluie de projet';
                const duree = m.duree_heures || kp.duree_heures || 2;
                simBlock = `
                    <div style="margin-bottom: 8px;">
                        <div style="font-size: 12px; font-weight: 700; color: #38bdf8; display: flex; align-items: center; gap: 7px;">
                            <i class="fas fa-cloud-showers-heavy" style="font-size: 11px;"></i> Simulation : ${_esc(tRetour)}
                        </div>
                        <div style="font-size: 11px; color: #94a3b8; margin-top: 2px; padding-left: 18px;">
                            ${_esc(scenNom)} (${duree} h)
                        </div>
                    </div>
                `;
            } else {
                simBlock = `
                    <div style="margin-bottom: 8px;">
                        <div style="font-size: 12px; font-weight: 600; color: #94a3b8; display: flex; align-items: center; gap: 7px;">
                            <i class="fas fa-info-circle" style="font-size: 11px;"></i> Aucune simulation active
                        </div>
                        <div style="font-size: 11px; color: #64748b; margin-top: 2px; padding-left: 18px;">
                            Ce bassin n'a pas encore été calculé
                        </div>
                    </div>
                `;
            }

            // --- ÉLÉMENT 2 : Modèle sain / Diagnostic Garde-fou & DWF ---
            let diagBlock = '';
            const verdict = window._fiabiliteDepuisSimulation ? window._fiabiliteDepuisSimulation(simActive) : 'SAIN';
            const metaFiab = _FIABILITE_META[verdict] || _FIABILITE_META['SAIN'];

            // Analyse DWF
            let dwfTxt = 'DWF : Aucun injecté (0 L/s)';
            let dwfColor = '#94a3b8';
            let dwfSub = '';
            const provDwf = (simActive && simActive.provenance && simActive.provenance.apports_dwf)
                || (simActive && simActive.kpis && simActive.kpis.provenance ? simActive.kpis.provenance.apports_dwf : null)
                || (m && m.apports_dwf ? { injectes: m.apports_dwf, ignores: m.apports_dwf_ignores || [] } : null);

            if (provDwf) {
                const nInj = Array.isArray(provDwf.injectes) ? provDwf.injectes.length : 0;
                const nIgn = Array.isArray(provDwf.ignores) ? provDwf.ignores.length : 0;
                let qTot = 0;
                if (Array.isArray(provDwf.injectes)) {
                    provDwf.injectes.forEach(a => {
                        const q = parseFloat(a.debit_moyen_m3s || 0);
                        if (isFinite(q)) qTot += q;
                    });
                }
                const qLs = (qTot * 1000).toFixed(1);
                if (nInj > 0) {
                    dwfTxt = `DWF : <b>${nInj} injecté${nInj > 1 ? 's' : ''} (${qLs} L/s)</b>`;
                    dwfColor = '#06b6d4';
                    if (nIgn > 0) dwfSub = `<span style="color:#fbbf24; font-size:10px; display:block; margin-top:2px;">⚠️ ${nIgn} exclu(s) hors bassin</span>`;
                } else if (nIgn > 0) {
                    dwfTxt = `DWF : Aucun injecté`;
                    dwfColor = '#fbbf24';
                    dwfSub = `<span style="color:#fbbf24; font-size:10px; display:block; margin-top:2px;">⚠️ ${nIgn} exclu(s) (regard hors bassin)</span>`;
                }
            } else if (window._dwfSimulationInfo && window._dwfSimulationInfo.actifs > 0) {
                dwfTxt = `DWF : ${window._dwfSimulationInfo.actifs} configuré(s)`;
                dwfColor = '#6ee7b7';
            }

            diagBlock = `
                <div style="margin-bottom: 10px;">
                    <div style="font-size: 12px; font-weight: 700; color: ${metaFiab.color}; display: flex; align-items: center; gap: 7px;">
                        <span>${metaFiab.icon}</span> <span>${metaFiab.label}</span>
                    </div>
                    <!-- Sous-élément DWF indenté -->
                    <div style="margin-top: 5px; margin-left: 20px; padding-left: 8px; border-left: 2px solid rgba(6, 182, 212, 0.4);">
                        <div style="font-size: 11px; color: ${dwfColor}; display: flex; align-items: center; justify-content: space-between;">
                            <span><i class="fas fa-faucet-drip me-1" style="color: #06b6d4;"></i> ${dwfTxt}</span>
                            <button type="button" onclick="fermerMenuBassin(); ouvrirModalApportsDwf();" style="background: transparent; border: none; color: #38bdf8; font-size: 10px; text-decoration: underline; cursor: pointer; padding: 0 4px;">
                                Gérer
                            </button>
                        </div>
                        ${dwfSub}
                    </div>
                </div>
            `;

            // Résolution optimale de l'identifiant stable pour l'historique
            let idHistorique = cidStr;
            if (window._bassinProperties && window._bassinProperties[cidStr]) {
                const bp = window._bassinProperties[cidStr];
                idHistorique = bp.exutoire_id || bp.bassin_ref || bp.cluster_id || cidStr;
            }

            dropdown.innerHTML = `
                <div style="padding: 12px 14px; border-bottom: 1px solid rgba(255,255,255,0.1); background: rgba(255,255,255,0.03);">
                    <div style="font-weight: 800; font-size: 13px; color: #34d399; display: flex; align-items: center; gap: 7px;">
                        <i class="fas fa-water"></i> ${_esc(nom)}
                    </div>
                    <div style="font-size: 11px; color: #94a3b8; margin-top: 3px;">
                        ${nbRegards} regards · ${nbTroncons} canalisations · ${surfaceHa} ha
                    </div>
                </div>

                <div style="padding: 12px 14px;">
                    <div style="font-size: 10px; font-weight: 800; text-transform: uppercase; letter-spacing: 0.5px; color: #64748b; margin-bottom: 8px;">
                        État d'analyse du bassin
                    </div>
                    ${simBlock}
                    ${diagBlock}

                    <div style="display: flex; gap: 6px; padding-top: 10px; border-top: 1px solid rgba(255,255,255,0.08); margin-top: 8px;">
                        <button type="button" onclick="reSimulerBassin('${_esc(cidStr)}');" title="Configurer et relancer une simulation pour ce bassin" style="flex: 1.2; padding: 6px 10px; background: rgba(56, 189, 248, 0.15); border: 1px solid rgba(56, 189, 248, 0.35); color: #38bdf8; border-radius: 6px; font-size: 11px; font-weight: 700; cursor: pointer; display: flex; align-items: center; justify-content: center; gap: 5px;">
                            <i class="fas fa-play"></i> ${simActive ? 'Re-simuler' : 'Simuler'}
                        </button>
                        <button type="button" onclick="fermerMenuBassin(); if (typeof ouvrirModalSimulationsBassin === 'function') ouvrirModalSimulationsBassin('${_esc(idHistorique)}', false);" title="Consulter l'historique des calculs enregistrés pour ce bassin" style="flex: 1; padding: 6px 8px; background: rgba(255, 255, 255, 0.05); border: 1px solid rgba(255, 255, 255, 0.15); color: #94a3b8; border-radius: 6px; font-size: 11px; font-weight: 600; cursor: pointer; display: flex; align-items: center; justify-content: center; gap: 5px;">
                            <i class="fas fa-history"></i> Historique
                        </button>
                        <button type="button" onclick="fermerMenuBassin(); reinitialiserSelectionBassin();" title="Revenir à la vue globale du réseau" style="flex: 0.8; padding: 6px 6px; background: rgba(255, 255, 255, 0.05); border: 1px solid rgba(255, 255, 255, 0.15); color: #cbd5e1; border-radius: 6px; font-size: 11px; font-weight: 600; cursor: pointer; display: flex; align-items: center; justify-content: center; gap: 5px;">
                            <i class="fas fa-globe"></i> Réseau
                        </button>
                    </div>
                </div>
            `;
        };

        /**
         * Re-simuler un bassin : ouvre directement la modale de configuration et
         * de lancement de simulation en pré-sélectionnant ce bassin, SANS détour
         * par l'historique des simulations.
         */
        window.reSimulerBassin = function(clusterId) {
            const cidStr = String(clusterId || '').trim();
            if (typeof window.fermerMenuBassin === 'function') window.fermerMenuBassin();
            if (cidStr && window._bassinsIsoleIds && window._bassinsIsoleIds.has(cidStr)) {
                if (typeof window.showToast === 'function') {
                    window.showToast("Cet ouvrage est un élément isolé sans réseau collecteur amont : simulation SWMM impossible.", "warning");
                }
                return;
            }
            if (cidStr) {
                const bSel = document.getElementById('bassin-select');
                if (bSel) bSel.value = cidStr;
                const simSel = document.getElementById('sim-select-bassin');
                if (simSel) {
                    simSel.value = cidStr;
                    try { simSel.dispatchEvent(new Event('change')); } catch (_) {}
                }
                try { window._selectedClusterId = cidStr; } catch (_) {}
            }
            if (typeof window.ouvrirModalSimulation === 'function') {
                window.ouvrirModalSimulation(true);
            }
        };

        // Fermeture automatique au clic extérieur
        document.addEventListener('click', (e) => {
            const d = document.getElementById('topbar-bassin-dropdown');
            const pill = document.getElementById('topbar-bassin-pill');
            if (d && d.style.display === 'block') {
                if (!d.contains(e.target) && (!pill || !pill.contains(e.target))) {
                    window.fermerMenuBassin();
                }
            }
        });
