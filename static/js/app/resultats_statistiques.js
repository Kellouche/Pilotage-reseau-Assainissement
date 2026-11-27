/**
 * ================================================================================
 * Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
 * Auteur : Dr Abdelhakim KELLOUCHE
 * Date de création : 2026-04-20
 * Date de modification : 2026-11-27
 * Objet : Mise à jour des indicateurs décisionnels, débits hydrologiques et KPIs SWMM
 * ================================================================================
 */

window.mettreAJourIndicateursEtKpisSimulation = function(data) {
    if (!data) return;
    const k = data.kpis || {};
    const coh = k.coherence_hydrologique || {};

            // 3. Mettre à jour les indicateurs KPIs dans la modale
            if (data.kpis) {
                const k = data.kpis;
                const errVal = k.routing_continuity_error_pct || 0;
                const contEl = document.getElementById('kpi-continuity');
                if (contEl) contEl.innerText = (errVal > 0 ? '+' : '') + window.formaterNombre(errVal, 2) + ' %';
                const peakEl = document.getElementById('kpi-peak-outflow');
                if (peakEl) peakEl.innerText = window.formaterNombre(k.peak_outflow_m3s || 0, 3) + ' m³/s';
                
                const peakTimeEl = document.getElementById('kpi-peak-time');
                if (peakTimeEl) peakTimeEl.innerText = k.peak_time_str || '--';

                const maxVelEl = document.getElementById('kpi-max-velocity');
                if (maxVelEl) {
                    const vVal = k.max_velocity_ms || 0;
                    maxVelEl.innerHTML = `${window.formaterNombre(vVal, 2)} m/s <small style="font-size:0.65rem; display:block; color:${k.autocurage_color || '#34d399'}; font-weight:600;">${k.autocurage_statut || 'Autocurage'}</small>`;
                }

                // Ligne 2 : Volumes et Surcharges
                const vRunoffEl = document.getElementById('kpi-vol-runoff');
                if (vRunoffEl) {
                    const rVal = k.total_runoff_volume_m3;
                    vRunoffEl.innerText = (rVal !== undefined && rVal !== null ? Math.round(rVal).toLocaleString('fr-FR') : '--') + ' m³';
                }

                const vInfilEl = document.getElementById('kpi-vol-infil');
                if (vInfilEl) {
                    const iVal = k.total_infiltration_volume_m3;
                    vInfilEl.innerText = (iVal !== undefined && iVal !== null ? Math.round(iVal).toLocaleString('fr-FR') : '--') + ' m³';
                }

                const cEffEl = document.getElementById('kpi-coeff-eff');
                if (cEffEl) cEffEl.innerText = window.formaterNombre(k.effective_runoff_coeff !== undefined ? k.effective_runoff_coeff : 0.70, 2);

                const surchPctEl = document.getElementById('kpi-surcharge-pct');
                if (surchPctEl) surchPctEl.innerText = `${window.formaterNombre(k.surcharged_length_pct || 0, 1)} % (${window.formaterNombre(k.surcharged_length_m || 0, 1)} m)`;

                // Contrôle de cohérence Pluie-Débit (Méthode Rationnelle)
                const coh = k.coherence_pluie_debit;
                if (coh) {
                    const badgeEl = document.getElementById('kpi-coherence-badge');
                    if (badgeEl) {
                        badgeEl.innerText = coh.badge || coh.statut;
                        badgeEl.style.background = (coh.color || '#10b981') + '22';
                        badgeEl.style.color = coh.color || '#10b981';
                        badgeEl.style.border = `1px solid ${coh.color || '#10b981'}55`;
                    }
                    const qSimEl = document.getElementById('kpi-coh-qsim');
                    if (qSimEl) qSimEl.innerText = `${window.formaterNombre(coh.q_simule_m3s, 3)} m³/s`;
                    const qRatEl = document.getElementById('kpi-coh-qrat');
                    if (qRatEl) qRatEl.innerText = `${window.formaterNombre(coh.q_rationnel_m3s, 3)} m³/s (Ratio: ${coh.ratio})`;
                    const msgEl = document.getElementById('kpi-coherence-msg');
                    if (msgEl) msgEl.innerText = coh.message;
                }

                // Module Bilan Hydraulique & Ouvrages Spéciaux : Mise à jour indicateur dans la modale
                const orphBox = document.getElementById('sim-orphelin-kpi-box');
                if (orphBox) {
                    const qDerive = (data.kpis && typeof data.kpis.q_derive_m3s === 'number') ? data.kpis.q_derive_m3s : ((data.kpis && typeof data.kpis.q_deleste_m3s === 'number') ? data.kpis.q_deleste_m3s : 0.0);
                    const qExutoire = (data.kpis && typeof data.kpis.q_exutoire_m3s === 'number') ? data.kpis.q_exutoire_m3s : ((data.kpis && typeof data.kpis.peak_outflow_m3s === 'number') ? data.kpis.peak_outflow_m3s : 0.0);
                    const qGenere = (data.kpis && typeof data.kpis.q_genere_m3s === 'number') ? data.kpis.q_genere_m3s : (qExutoire + qDerive);
                    const nbOrph = (data.kpis && data.kpis.nb_ouvrages_raccordes) || 0;
                    const tauxDerive = (data.kpis && typeof data.kpis.taux_derive_pct === 'number') ? data.kpis.taux_derive_pct : (qGenere > 0 ? ((qDerive / qGenere) * 100.0) : 0.0);
                    const tauxExutoire = (data.kpis && typeof data.kpis.taux_exutoire_pct === 'number') ? data.kpis.taux_exutoire_pct : Math.max(0, 100.0 - tauxDerive);

                    const qGenereStr = window.formaterNombre(qGenere, 3);
                    const qExutoireStr = window.formaterNombre(qExutoire, 3);
                    const qDeriveStr = window.formaterNombre(qDerive, 3);
                    const tauxDeriveStr = window.formaterNombre(tauxDerive, 1);
                    const tauxExutoireStr = window.formaterNombre(tauxExutoire, 1);

                    orphBox.style.display = 'block';
                    const bEl = document.getElementById('kpi-orphelin-badge');
                    const gEl = document.getElementById('kpi-orphelin-qgenere');
                    const eEl = document.getElementById('kpi-orphelin-qexutoire');
                    const qEl = document.getElementById('kpi-orphelin-qdeleste');
                    const dEl = document.getElementById('kpi-orphelin-desc');

                    if (gEl) gEl.innerText = `${qGenereStr} m³/s`;
                    if (eEl) eEl.innerText = `${qExutoireStr} m³/s (${tauxExutoireStr}%)`;

                    if (qDerive > 0) {
                        if (bEl) {
                            bEl.innerText = `Soulagement réseau : ${tauxDeriveStr}%`;
                            bEl.style.background = 'rgba(6, 182, 212, 0.25)';
                            bEl.style.color = '#22d3ee';
                            bEl.style.borderColor = 'rgba(6, 182, 212, 0.5)';
                        }
                        if (qEl) qEl.innerText = `${qDeriveStr} m³/s (${tauxDeriveStr}%)`;
                        if (dEl) dEl.innerHTML = `<i class="fas fa-check-circle text-emerald-400 me-1"></i> <b>${nbOrph} ouvrage(s) spécial(aux) actif(s)</b> : ${qDeriveStr} m³/s captés (${tauxDeriveStr}% du débit produit), soulageant d'autant le collecteur principal.`;
                    } else {
                        if (bEl) {
                            bEl.innerText = `Soulagement réseau : 0,0%`;
                            bEl.style.background = 'rgba(16, 185, 129, 0.2)';
                            bEl.style.color = '#34d399';
                            bEl.style.borderColor = 'rgba(16, 185, 129, 0.4)';
                        }
                        if (qEl) qEl.innerText = `0,000 m³/s (0,0%)`;
                        if (dEl) dEl.innerHTML = `<i class="fas fa-info-circle text-sky-400 me-1"></i> <b>Scénario sans ouvrage spécial raccordé</b> : 100,0% du débit produit (${qGenereStr} m³/s) transite vers le collecteur et l'exutoire principal.`;
                    }
                }

                // Double Échelle de Surface : Urbaine Drainée vs Impluvium Convexe
                const surfUrb = document.getElementById('kpi-surf-urbaine');
                if (surfUrb) surfUrb.innerText = `${(data.meta && data.meta.total_area_ha) ? data.meta.total_area_ha : '--'} ha`;
                const ratioDrain = document.getElementById('kpi-ratio-drainage');
                if (ratioDrain) ratioDrain.innerText = `(Ratio: ${data.meta && data.meta.ratio_drainage_pct ? data.meta.ratio_drainage_pct : 55} %)`;

                // Données hydro-météorologiques certifiées (ANRH / UHBC)
                const pluvioStation = (data.kpis && data.kpis.pluvio_station) || (data.meta && data.meta.pluvio_station) || 'Station ANRH Chlef Siège (010501)';
                const pluvioPeriode = (data.kpis && data.kpis.pluvio_periode_retour) || (data.meta && data.meta.pluvio_periode_retour) || 'T = 10 ans (Décennale)';
                const pluvioImax = (data.kpis && data.kpis.pluvio_intensite_max_mmh) !== undefined ? data.kpis.pluvio_intensite_max_mmh : ((data.meta && data.meta.pluvio_intensite_max_mmh) || 74.9);
                const pluvioPtot = (data.kpis && data.kpis.pluvio_hauteur_totale_mm) || (data.meta && data.meta.pluvio_hauteur_totale_mm) || 42.8;
                const pluvioMontana = (data.kpis && data.kpis.pluvio_montana) || (data.meta && data.meta.pluvio_montana) || 'I(t) = 9.334 · t^(-0.745)';
                const pluvioSource = (data.kpis && data.kpis.pluvio_source) || (data.meta && data.meta.pluvio_source) || 'ANRH Antenne Chlef / UHBC Laboratoire Eau & Environnement (Code 010501)';

                const badgeStEl = document.getElementById('kpi-pluvio-station-badge');
                if (badgeStEl) badgeStEl.innerText = pluvioStation;
                const perEl = document.getElementById('kpi-pluvio-periode');
                if (perEl) perEl.innerText = pluvioPeriode;
                const imaxEl = document.getElementById('kpi-pluvio-imax');
                if (imaxEl) imaxEl.innerText = `${Number(pluvioImax).toFixed(1)} mm/h`;
                const ptotEl = document.getElementById('kpi-pluvio-ptot');
                if (ptotEl) ptotEl.innerText = `${Number(pluvioPtot).toFixed(1)} mm`;
                const montEl = document.getElementById('kpi-pluvio-montana');
                if (montEl) montEl.innerText = pluvioMontana;
                const srcEl = document.getElementById('kpi-pluvio-source-note');
                if (srcEl) srcEl.innerHTML = `<i class="fas fa-database me-1" style="color: #38bdf8;"></i> ${pluvioSource}`;
            }

            const resultsCard = document.getElementById('sim-results-card');
            if (resultsCard) {
                const bassinTitle = document.getElementById('sim-results-bassin-title');
                if (bassinTitle) {
                    const nomResolu = _resoudreNomMetierBassinResultats(data.meta);
                    if (data.meta && (data.meta.cluster_nom || data.meta.cluster_id !== undefined)) {
                        const typoInfo = data.meta.typologie_nom ? ` &bull; 🏷️ ${data.meta.typologie_nom}` : '';
                        bassinTitle.innerHTML = `<i class="fas fa-sitemap me-1"></i> Périmètre simulé : <b>${nomResolu}</b> (Exutoire ${data.meta.cluster_id}) &bull; ${data.meta.junctions_count + 1} regards, ${data.meta.conduits_count} conduites (${data.meta.total_area_ha} ha)${typoInfo}`;
                        bassinTitle.style.display = 'block';
                    } else {
                        const typoInfo = data.meta && data.meta.typologie_nom ? ` &bull; 🏷️ ${data.meta.typologie_nom}` : '';
                        bassinTitle.innerHTML = `<i class="fas fa-globe me-1"></i> Périmètre simulé : <b>Réseau Complet</b> &bull; ${data.meta ? data.meta.conduits_count : ''} conduites${typoInfo}`;
                        bassinTitle.style.display = 'block';
                    }
                }
                resultsCard.style.display = 'block';

                // Personnaliser le nom du fichier .INP et .RPT à télécharger avec le nom du réseau
                const projNom = (window._rawNetworkData && window._rawNetworkData.project_name) || (data.meta && data.meta.project_name) || 'modele_swmm';
                const bassinNom = (data.meta && (data.meta.bassin_nom || data.meta.cluster_nom)) || '';
                const baseNomFichier = (projNom + (bassinNom ? '_' + bassinNom : '')).replace(/[^\w\-_.]+/g, '_').replace(/_+/g, '_').replace(/^_+|_+$/g, '');
                
                const btnInp = document.getElementById('btn-download-inp');
                if (btnInp) {
                    btnInp.setAttribute('download', `${baseNomFichier}.inp`);
                    btnInp.setAttribute('title', `Télécharger le fichier modèle SWMM : ${baseNomFichier}.inp`);
                }
                const btnRpt = document.getElementById('btn-download-rpt');
                if (btnRpt) {
                    btnRpt.setAttribute('download', `${baseNomFichier}.rpt`);
                    btnRpt.setAttribute('title', `Télécharger le rapport de calcul : ${baseNomFichier}.rpt`);
                }
            }

            // Afficher l'analyse de sensibilité du buffer Voronoï
            if (data.buffer_sensitivity && typeof afficherAnalyseSensibiliteBuffer === 'function') {
                afficherAnalyseSensibiliteBuffer(data.buffer_sensitivity, window._activeBufferM);
            }

            // Mettre à jour l'ensemble de l'IHM latérale pour refléter la zone simulée
            mettreAJourIHMZoneSimulee(data);

            // Mettre à jour l'indicateur supérieur de bassin versant (Option 1 : Lecture Hydraulique)
            if (data.meta && data.meta.cluster_id && typeof window.mettreAJourIndicateurBassin === 'function') {
                const kp = data.kpis || {};
                const qMax = (typeof kp.peak_outflow_m3s === 'number') ? kp.peak_outflow_m3s : 0.0;
                const qExutoire = (typeof kp.q_exutoire_m3s === 'number') ? kp.q_exutoire_m3s : qMax;
                const qDerive = (typeof kp.q_derive_m3s === 'number') ? kp.q_derive_m3s : ((typeof kp.q_deleste_m3s === 'number') ? kp.q_deleste_m3s : 0.0);
                const qGenere = (typeof kp.q_genere_m3s === 'number') ? kp.q_genere_m3s : (qExutoire + qDerive);
                const nbRacc = kp.nb_ouvrages_raccordes || 0;
                const tauxDerive = (typeof kp.taux_derive_pct === 'number') ? kp.taux_derive_pct : (qGenere > 0 ? ((qDerive / qGenere) * 100.0) : 0.0);
                const tauxExutoire = (typeof kp.taux_exutoire_pct === 'number') ? kp.taux_exutoire_pct : Math.max(0, 100.0 - tauxDerive);

                window.mettreAJourIndicateurBassin(data.meta.cluster_id, {
                    status: 'simulated',
                    peak_flow: qMax,
                    q_exutoire_m3s: qExutoire,
                    q_derive_m3s: qDerive,
                    q_genere_m3s: qGenere,
                    taux_derive_pct: tauxDerive,
                    taux_exutoire_pct: tauxExutoire,
                    nb_ouvrages_raccordes: nbRacc
                });
            }

            // Centrer et zoomer immédiatement la carte sur la zone simulée
            zoomerSurZoneSimulee(data);

            // Remplir la fenêtre dédiée de restitution des résultats
            if (typeof window.remplirModalResultatsSimulation === 'function') {
                window.remplirModalResultatsSimulation(data);
            }
};

// ================================================================================
// CONTRÔLEUR DE LA MODALE DÉDIÉE DE RÉSULTATS SWMM 5.2 (Figma-grade HD)
// ================================================================================

window._detailsConduitesFiltreStatut = 'tous';
window._detailsRegardsFiltreStatut = 'tous';

window.basculerAutoOpenResults = function(checked) {
    localStorage.setItem('swmm_auto_open_results', checked ? 'true' : 'false');
};

window.ouvrirModalResultatsSimulation = function() {
    const modal = document.getElementById('modal-resultats-simulation');
    if (!modal) return;

    const chk = document.getElementById('chk-auto-open-results');
    if (chk) {
        chk.checked = (localStorage.getItem('swmm_auto_open_results') !== 'false');
    }

    if (window._dernierResultatSimulation) {
        window.remplirModalResultatsSimulation(window._dernierResultatSimulation);
    }
    modal.style.display = 'flex';
};

window.fermerModalResultatsSimulation = function() {
    const modal = document.getElementById('modal-resultats-simulation');
    if (modal) modal.style.display = 'none';
};

// Affichage d'un toast interactif permettant de rouvrir la modale de résultats après navigation
window.afficherToastRetourResultats = function(message) {
    let toast = document.getElementById('toast-retour-modal-resultats');
    if (!toast) {
        toast = document.createElement('div');
        toast.id = 'toast-retour-modal-resultats';
        toast.style.cssText = 'position:fixed;top:68px;left:50%;transform:translateX(-50%);z-index:10600;background:rgba(15,23,42,0.94);backdrop-filter:blur(12px);border:1px solid rgba(56,189,248,0.45);border-radius:30px;padding:8px 18px;color:#f8fafc;font-size:0.8rem;box-shadow:0 10px 25px -5px rgba(0,0,0,0.5),0 0 15px rgba(56,189,248,0.25);display:flex;align-items:center;gap:12px;';
        document.body.appendChild(toast);
    }
    toast.innerHTML = `
        <div style="display:flex;align-items:center;gap:8px;">
            <i class="fas fa-bullseye" style="color:#38bdf8;"></i>
            <span>${message}</span>
        </div>
        <button type="button" onclick="window.ouvrirModalResultatsSimulation();document.getElementById('toast-retour-modal-resultats').style.display='none';" style="background:linear-gradient(135deg,#0284c7,#0369a1);border:1px solid rgba(255,255,255,0.25);color:white;border-radius:20px;padding:4px 12px;font-size:0.75rem;font-weight:700;cursor:pointer;display:flex;align-items:center;gap:6px;box-shadow:0 2px 6px rgba(0,0,0,0.3);">
            <i class="fas fa-table-cells"></i>
            <span>Rouvrir Résultats</span>
        </button>
        <button type="button" onclick="document.getElementById('toast-retour-modal-resultats').style.display='none';" style="background:transparent;border:none;color:#94a3b8;cursor:pointer;padding:0 4px;font-size:0.85rem;" title="Fermer">
            <i class="fas fa-times"></i>
        </button>
    `;
    toast.style.display = 'flex';
};

// Localisation instantanée avec centrage fluide et impulsion visuelle
window.localiserElementSurCarte = function(type, id) {
    if (!id) return;
    const strId = String(id).trim();
    const cleanId = strId.endsWith('.0') ? strId.slice(0, -2) : strId;

    window.fermerModalResultatsSimulation();

    const carte = (typeof window.carte !== 'undefined' && window.carte)
        || (typeof window.map !== 'undefined' && window.map)
        || (typeof carte !== 'undefined' ? carte : null);
    if (!carte) return;

    if (type === 'regard') {
        let coords = null;
        let targetLayer = null;

        if (typeof couches !== 'undefined' && couches.res_regards && couches.res_regards.eachLayer) {
            couches.res_regards.eachLayer(l => {
                if (coords) return;
                const p = (l.feature && l.feature.properties) || {};
                const code = String(p.Code || p.code || p.CODE || p.id || '').trim();
                const cl = code.endsWith('.0') ? code.slice(0, -2) : code;
                if (cl === cleanId || code === strId) {
                    const ll = l.getLatLng ? l.getLatLng() : null;
                    if (ll) { coords = { lng: ll.lng, lat: ll.lat }; targetLayer = l; }
                }
            });
        }

        if (!coords && typeof couches !== 'undefined' && couches.regards && couches.regards.eachLayer) {
            couches.regards.eachLayer(l => {
                if (coords) return;
                const p = (l.feature && l.feature.properties) || {};
                const code = String(p.Code || p.code || p.CODE || p.id || '').trim();
                const cl = code.endsWith('.0') ? code.slice(0, -2) : code;
                if (cl === cleanId || code === strId) {
                    const ll = l.getLatLng ? l.getLatLng() : null;
                    if (ll) { coords = { lng: ll.lng, lat: ll.lat }; targetLayer = l; }
                }
            });
        }

        if (!coords && window._rawNetworkData && window._rawNetworkData.couches && window._rawNetworkData.couches.regards && Array.isArray(window._rawNetworkData.couches.regards.features)) {
            const feats = window._rawNetworkData.couches.regards.features;
            for (let i = 0; i < feats.length; i++) {
                const f = feats[i];
                const p = f.properties || {};
                const code = String(p.Code || p.code || p.CODE || p.id || '').trim();
                const cl = code.endsWith('.0') ? code.slice(0, -2) : code;
                if ((cl === cleanId || code === strId) && f.geometry && Array.isArray(f.geometry.coordinates)) {
                    coords = { lng: f.geometry.coordinates[0], lat: f.geometry.coordinates[1] };
                    break;
                }
            }
        }

        if (coords) {
            window._rechercheCentrageJusqua = Date.now() + 8000;
            if (typeof carte.flyTo === 'function') {
                carte.flyTo([coords.lat, coords.lng], 18, { duration: 1.2 });
            } else if (typeof carte.setView === 'function') {
                carte.setView([coords.lat, coords.lng], 18);
            }

            const pulseIcon = L.divIcon({
                className: 'pulse-temp-marker',
                html: '<div style="position:relative;width:34px;height:34px;"><div style="position:absolute;left:50%;top:50%;width:34px;height:34px;transform:translate(-50%,-50%);border-radius:50%;border:3px solid #f59e0b;animation:pulseRing 1.1s ease-out infinite;"></div><div style="position:absolute;left:50%;top:50%;width:14px;height:14px;transform:translate(-50%,-50%);background:#f59e0b;border:2.5px solid #fff;border-radius:50%;box-shadow:0 0 10px rgba(245,158,11,0.9);"></div></div>',
                iconSize: [34, 34],
                iconAnchor: [17, 17]
            });
            const m = L.marker([coords.lat, coords.lng], { icon: pulseIcon }).addTo(carte);
            m.bindTooltip(`Regard ${strId}`, { permanent: true, direction: 'top' });
            setTimeout(() => { try { carte.removeLayer(m); } catch(_) {} }, 6000);

            if (targetLayer && typeof targetLayer.openPopup === 'function') {
                setTimeout(() => { try { targetLayer.openPopup(); } catch(_) {} }, 1250);
            }
            window.afficherToastRetourResultats(`Regard <b>${strId}</b> centré sur la carte.`);
        } else {
            if (typeof window.dialogueAlerte === 'function') {
                window.dialogueAlerte(`Coordonnées du regard ${strId} introuvables.`, 'info');
            }
        }
    } else if (type === 'conduite') {
        let targetLayer = null;
        let bounds = null;

        if (typeof couches !== 'undefined' && couches.res_conduites && couches.res_conduites.eachLayer) {
            couches.res_conduites.eachLayer(l => {
                if (targetLayer) return;
                const p = (l.feature && l.feature.properties) || {};
                const cid = String(p.link_id || p.ID || p.id || p.Name || '').trim();
                if (cid === strId) {
                    targetLayer = l;
                    if (l.getBounds) bounds = l.getBounds();
                }
            });
        }

        if (!targetLayer && typeof couches !== 'undefined' && couches.conduites && couches.conduites.eachLayer) {
            couches.conduites.eachLayer(l => {
                if (targetLayer) return;
                const p = (l.feature && l.feature.properties) || {};
                const cid = String(p.ID || p.id || p.Name || p.link_id || '').trim();
                if (cid === strId) {
                    targetLayer = l;
                    if (l.getBounds) bounds = l.getBounds();
                }
            });
        }

        if (targetLayer && bounds) {
            window._rechercheCentrageJusqua = Date.now() + 8000;
            if (typeof carte.flyToBounds === 'function') {
                carte.flyToBounds(bounds, { maxZoom: 18, padding: [60, 60], duration: 1.2 });
            } else if (typeof carte.fitBounds === 'function') {
                carte.fitBounds(bounds, { maxZoom: 18, padding: [60, 60] });
            }
            if (typeof targetLayer.openPopup === 'function') {
                setTimeout(() => { try { targetLayer.openPopup(); } catch(_) {} }, 1250);
            }
            window.afficherToastRetourResultats(`Tronçon <b>${strId}</b> centré sur la carte.`);
        } else {
            if (typeof window.dialogueAlerte === 'function') {
                window.dialogueAlerte(`Tracé de la conduite ${strId} introuvable.`, 'info');
            }
        }
    }
};

// Ouverture directe du profil en long depuis le tableau de résultats
window.ouvrirProfilDepuisModal = function(type, id, uNode, dNode) {
    window.fermerModalResultatsSimulation();

    let amont = uNode;
    let aval = dNode;

    if (type === 'regard' || (!amont && !aval)) {
        const nid = String(id).trim();
        const cleanNid = nid.endsWith('.0') ? nid.slice(0, -2) : nid;

        const simData = window._dernierResultatSimulation || {};
        const cRes = simData.conduit_results || {};

        let incomingAmont = null;
        let outgoingAval = null;

        Object.values(cRes).forEach(c => {
            const u = String(c.u_node || '').trim();
            const d = String(c.d_node || '').trim();
            const uCl = u.endsWith('.0') ? u.slice(0, -2) : u;
            const dCl = d.endsWith('.0') ? d.slice(0, -2) : d;

            if (uCl === cleanNid || u === nid) {
                if (!outgoingAval) outgoingAval = d;
            }
            if (dCl === cleanNid || d === nid) {
                if (!incomingAmont) incomingAmont = u;
            }
        });

        if (incomingAmont && outgoingAval) {
            amont = incomingAmont;
            aval = outgoingAval;
        } else if (outgoingAval) {
            amont = nid;
            aval = outgoingAval;
        } else if (incomingAmont) {
            amont = incomingAmont;
            aval = nid;
        } else {
            amont = nid;
            aval = nid;
        }
    }

    if (!amont || !aval) {
        if (typeof window.dialogueAlerte === 'function') {
            window.dialogueAlerte(`Impossible de déterminer l'axe amont-aval pour l'ouvrage ${id}.`, 'info');
        }
        return;
    }

    const inpA = document.getElementById('input-profil-amont');
    const inpB = document.getElementById('input-profil-aval');
    if (inpA) inpA.value = amont;
    if (inpB) inpB.value = aval;

    if (typeof window.synchroniserInputProfilAmont === 'function') window.synchroniserInputProfilAmont(amont);
    if (typeof window.synchroniserInputProfilAval === 'function') window.synchroniserInputProfilAval(aval);

    const panel = document.getElementById('panel-profil-long');
    if (panel) {
        panel.style.display = 'flex';
        if (typeof _centrerPanelProfil === 'function') _centrerPanelProfil();
        if (typeof _initProfilLongDraggable === 'function') _initProfilLongDraggable();
    }

    if (typeof chargerProfilLong === 'function') {
        chargerProfilLong(amont, aval);
    }

    window.afficherToastRetourResultats(`Profil en long tracé de <b>${amont}</b> &rarr; <b>${aval}</b>.`);
};
