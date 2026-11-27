/**
 * ================================================================================
 * Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
 * Auteur : Dr Abdelhakim KELLOUCHE
 * Date de création : 2026-04-20
 * Date de modification : 2026-11-27
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
            // Un identifiant nu (« 459 », « Bassin 459 ») n'est pas un nom
            // métier : meta.bassin_nom peut contenir le cluster_id brut.
            const _ressembleAId = (n) => {
                const s = String(n || '').trim();
                if (!s) return true;
                if (/^\d+$/.test(s) || /^Bassin\s+\d+$/i.test(s)) return true;
                return !!(cidStr && (s === String(cidStr) || s.toLowerCase() === String(cidStr).toLowerCase()));
            };
            const _depuis = (m) => {
                if (!m) return '';
                const n = String(m.bassin_nom || m.cluster_nom || '').trim();
                return _ressembleAId(n) ? '' : n;
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
        window._nomMetierBassin = _nomMetierBassin;

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
                try { window._selectedClusterNom = nom; } catch (_) {}
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
