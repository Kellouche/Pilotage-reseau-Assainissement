/**
 * ================================================================================
 * Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
 * Auteur : Dr Abdelhakim KELLOUCHE
 * Date de création : 2026-11-27
 * Date de modification : 2026-11-27
 * Objet : Etat physique du reseau (colmatage et vieillissement) : presets et configuration (extrait de static/js/app/simulation_ui.js)
 * ================================================================================
 */

        // ============================================================
        // État physique du réseau (Colmatage & Vieillissement — Schéma A)
        // ============================================================
        const ETAT_PRESETS_BASE = {
            nominal: { scenario_nom: 'nominal', colmatage_pct: 0, facteur_vieillissement: 1.0, cible_colmatage: 'tout_reseau', seuil_pente_pct: 0.5 },
            exploite: { scenario_nom: 'exploite', colmatage_pct: 10, facteur_vieillissement: 1.20, cible_colmatage: 'faibles_pentes', seuil_pente_pct: 0.5 },
            critique: { scenario_nom: 'critique', colmatage_pct: 25, facteur_vieillissement: 1.45, cible_colmatage: 'faibles_pentes', seuil_pente_pct: 0.5 }
        };
        let _activeEtatPresetName = 'nominal';

        function _chargerPresetsEtatCustom() {
            try {
                const raw = localStorage.getItem('drainpilot_etat_presets_v1');
                return raw ? JSON.parse(raw) : {};
            } catch (e) {
                return {};
            }
        }

        function _sauverPresetsEtatCustom(map) {
            try {
                localStorage.setItem('drainpilot_etat_presets_v1', JSON.stringify(map));
            } catch (e) {}
        }

        window.rendrePresetsEtatCustom = function() {
            const container = document.getElementById('sim-etat-saved-list');
            if (!container) return;
            const customMap = _chargerPresetsEtatCustom();
            const keys = Object.keys(customMap);
            if (keys.length === 0) {
                container.style.display = 'none';
                container.innerHTML = '';
                return;
            }
            container.style.display = 'flex';
            container.innerHTML = keys.map(k => {
                const isActive = _activeEtatPresetName === k;
                const borderCol = isActive ? '#38bdf8' : 'rgba(255,255,255,0.18)';
                const bgCol = isActive ? 'rgba(56,189,248,0.18)' : 'rgba(15,23,42,0.65)';
                return `
                    <div style="display:inline-flex; align-items:center; gap:6px; padding:4px 8px; border-radius:999px; border:1px solid ${borderCol}; background:${bgCol}; font-size:0.72rem; color:#e2e8f0;">
                        <span style="cursor:pointer; font-weight:600;" onclick="selectionnerPresetEtatReseau('${k.replace(/'/g, "\\'")}')">${k}</span>
                        <span style="cursor:pointer; color:#94a3b8; font-weight:700;" onclick="supprimerPresetEtatReseau('${k.replace(/'/g, "\\'")}')" title="Supprimer ce scénario">&times;</span>
                    </div>
                `;
            }).join('');
        };

        window.selectionnerPresetEtatReseau = function(nomPreset, toggleDrawer = false) {
            const drawer = document.getElementById('sim-etat-drawer');
            const customMap = _chargerPresetsEtatCustom();
            const preset = ETAT_PRESETS_BASE[nomPreset] || customMap[nomPreset];

            _activeEtatPresetName = nomPreset;

            // Style des pilules principales
            document.querySelectorAll('.sim-etat-pill').forEach(btn => {
                const p = btn.getAttribute('data-preset');
                const active = (p === nomPreset) || (p === 'personnalise' && !ETAT_PRESETS_BASE[nomPreset]);
                btn.style.border = active ? '1.5px solid #38bdf8' : '1px solid rgba(255,255,255,0.14)';
                btn.style.background = active ? 'rgba(56, 189, 248, 0.16)' : 'rgba(15, 23, 42, 0.7)';
                btn.style.color = active ? '#f8fafc' : '#cbd5e1';
            });

            if (nomPreset === 'personnalise') {
                if (drawer) {
                    drawer.style.display = (toggleDrawer && drawer.style.display === 'block') ? 'none' : 'block';
                }
            } else if (preset) {
                if (drawer && !toggleDrawer) drawer.style.display = 'none';
                const rngCol = document.getElementById('sim-etat-colmatage-range');
                const rngVie = document.getElementById('sim-etat-vieillissement-range');
                const inpSeuil = document.getElementById('sim-etat-seuil-pente');
                if (rngCol) rngCol.value = preset.colmatage_pct;
                if (rngVie) rngVie.value = preset.facteur_vieillissement;
                if (inpSeuil) inpSeuil.value = preset.seuil_pente_pct ?? 0.5;
                document.querySelectorAll('input[name="sim-etat-cible"]').forEach(r => {
                    r.checked = (r.value === (preset.cible_colmatage || 'tout_reseau'));
                });
                if (preset.appliquer_depots_sig !== undefined) {
                    const chkSig = document.getElementById('sim-chk-depots-sig');
                    if (chkSig) chkSig.checked = !!preset.appliquer_depots_sig;
                }
            }

            window.rendrePresetsEtatCustom();
            window.mettreAJourResumeEtatReseau();
        };

        window.onSliderEtatReseauChange = function() {
            _activeEtatPresetName = 'personnalise';
            document.querySelectorAll('.sim-etat-pill').forEach(btn => {
                const active = btn.getAttribute('data-preset') === 'personnalise';
                btn.style.border = active ? '1.5px solid #38bdf8' : '1px solid rgba(255,255,255,0.14)';
                btn.style.background = active ? 'rgba(56, 189, 248, 0.16)' : 'rgba(15, 23, 42, 0.7)';
            });
            window.mettreAJourResumeEtatReseau();
        };

        window.mettreAJourResumeEtatReseau = function() {
            const col = parseFloat(document.getElementById('sim-etat-colmatage-range')?.value || 0);
            const vie = parseFloat(document.getElementById('sim-etat-vieillissement-range')?.value || 1.0);
            const chkSig = document.getElementById('sim-chk-depots-sig')?.checked || false;
            const cibleEl = document.querySelector('input[name="sim-etat-cible"]:checked');
            const cible = cibleEl ? cibleEl.value : 'tout_reseau';
            const seuil = parseFloat(document.getElementById('sim-etat-seuil-pente')?.value || 0.5);

            const valColEl = document.getElementById('sim-etat-colmatage-val');
            const valVieEl = document.getElementById('sim-etat-vieillissement-val');
            const exEl = document.getElementById('sim-etat-rugosite-exemple');
            const badge = document.getElementById('sim-etat-badge-resume');

            if (valColEl) valColEl.textContent = `${col} %`;
            if (valVieEl) valVieEl.textContent = `×${vie.toFixed(2)}`;
            if (exEl) {
                const beton = (0.013 * vie).toFixed(3);
                const pvc = (0.011 * vie).toFixed(3);
                exEl.textContent = `Béton : 0.013 → ${beton} • PVC : 0.011 → ${pvc}`;
            }

            if (badge) {
                const isNominal = (col === 0 && Math.abs(vie - 1.0) < 1e-4 && !chkSig);
                if (isNominal) {
                    badge.textContent = 'Nominal (Curé)';
                    badge.style.color = '#10b981';
                    badge.style.background = 'rgba(16, 185, 129, 0.15)';
                    badge.style.borderColor = 'rgba(16, 185, 129, 0.35)';
                } else {
                    const parts = [];
                    if (col > 0) parts.push(`${col}% dépôt${cible === 'faibles_pentes' ? ' (<' + seuil + '%)' : ''}`);
                    if (vie > 1.0) parts.push(`n ×${vie.toFixed(2)}`);
                    if (chkSig) parts.push('+SIG');
                    badge.textContent = parts.join(' • ');
                    badge.style.color = (col >= 20 || vie >= 1.4) ? '#f87171' : '#fbbf24';
                    badge.style.background = (col >= 20 || vie >= 1.4) ? 'rgba(239, 68, 68, 0.15)' : 'rgba(245, 158, 11, 0.15)';
                    badge.style.borderColor = (col >= 20 || vie >= 1.4) ? 'rgba(239, 68, 68, 0.4)' : 'rgba(245, 158, 11, 0.4)';
                }
            }
        };

        window.enregistrerPresetEtatReseau = function() {
            const inpNom = document.getElementById('sim-etat-nom-custom');
            const nom = (inpNom?.value || '').trim();
            if (!nom) {
                alert('Veuillez saisir un nom pour votre scénario.');
                return;
            }
            const cfg = window.lireConfigurationEtatReseau();
            cfg.scenario_nom = nom;
            const map = _chargerPresetsEtatCustom();
            map[nom] = cfg;
            _sauverPresetsEtatCustom(map);
            if (inpNom) inpNom.value = '';
            window.selectionnerPresetEtatReseau(nom);
        };

        window.supprimerPresetEtatReseau = function(nom) {
            const map = _chargerPresetsEtatCustom();
            delete map[nom];
            _sauverPresetsEtatCustom(map);
            if (_activeEtatPresetName === nom) {
                window.selectionnerPresetEtatReseau('nominal');
            } else {
                window.rendrePresetsEtatCustom();
            }
        };

        window.lireConfigurationEtatReseau = function() {
            const col = parseFloat(document.getElementById('sim-etat-colmatage-range')?.value || 0);
            const vie = parseFloat(document.getElementById('sim-etat-vieillissement-range')?.value || 1.0);
            const chkSig = document.getElementById('sim-chk-depots-sig')?.checked || false;
            const cibleEl = document.querySelector('input[name="sim-etat-cible"]:checked');
            const cible = cibleEl ? cibleEl.value : 'tout_reseau';
            const seuil = parseFloat(document.getElementById('sim-etat-seuil-pente')?.value || 0.5);

            return {
                scenario_nom: _activeEtatPresetName || 'personnalise',
                colmatage_pct: col,
                facteur_vieillissement: vie,
                cible_colmatage: cible,
                seuil_pente_pct: seuil,
                appliquer_depots_sig: chkSig
            };
        };

        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', () => {
                if (typeof window.rendrePresetsEtatCustom === 'function') window.rendrePresetsEtatCustom();
                const selB = document.getElementById('sim-select-bassin');
                if (selB) {
                    selB.addEventListener('change', () => {
                        if (typeof window.chargerInfosDwfSimulation === 'function') {
                            window.chargerInfosDwfSimulation(selB.value);
                        }
                    });
                }
            });
        } else {
            window.rendrePresetsEtatCustom();
            const selB = document.getElementById('sim-select-bassin');
            if (selB) {
                selB.addEventListener('change', () => {
                    if (typeof window.chargerInfosDwfSimulation === 'function') {
                        window.chargerInfosDwfSimulation(selB.value);
                    }
                });
            }
        }
