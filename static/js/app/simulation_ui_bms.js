/**
 * ================================================================================
 * Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
 * Auteur : Dr Abdelhakim KELLOUCHE
 * Date de création : 2026-11-27
 * Date de modification : 2026-11-27
 * Objet : Module BMS (Bulletin Meteorologique Special ONM) : bascule mode pluie, telegramme, ordre de mission (extrait de static/js/app/simulation_ui.js)
 * ================================================================================
 */

        window.basculerModePluie = function(mode) {
            window._modePluieActif = mode;
            const btnProjet = document.getElementById('tab-mode-pluie-projet');
            const btnBms = document.getElementById('tab-mode-pluie-bms');
            const secProjet = document.getElementById('section-pluie-projet');
            const secBms = document.getElementById('section-pluie-bms');
            const badgeStation = document.getElementById('sim-pluvio-station-badge');

            if (mode === 'bms') {
                if (btnProjet) {
                    btnProjet.style.background = 'transparent';
                    btnProjet.style.color = '#94a3b8';
                }
                if (btnBms) {
                    btnBms.style.background = '#ea580c';
                    btnBms.style.color = 'white';
                }
                if (secProjet) secProjet.style.display = 'none';
                if (secBms) secBms.style.display = 'block';
                if (badgeStation) badgeStation.innerText = 'Mode alerte météo (BMS ONM)';
                window.onChangementParametresBMS();
            } else {
                if (btnProjet) {
                    btnProjet.style.background = '#0284c7';
                    btnProjet.style.color = 'white';
                }
                if (btnBms) {
                    btnBms.style.background = 'transparent';
                    btnBms.style.color = '#94a3b8';
                }
                if (secProjet) secProjet.style.display = 'block';
                if (secBms) secBms.style.display = 'none';
                const scenSel = document.getElementById('sim-select-scenario');
                const curVal = scenSel ? scenSel.value : 'pluie_decennale';
                window.onChangementScenarioPluie(curVal);
            }
        };

        window.setBMSCumul = function(val) {
            const inp = document.getElementById('sim-bms-cumul-mm');
            if (inp) {
                inp.value = String(val);
                window.onChangementParametresBMS();
            }
        };

        window.onChangementParametresBMS = function() {
            const radJaune = document.getElementById('lbl-bms-vigilance-jaune');
            const radOrange = document.getElementById('lbl-bms-vigilance-orange');
            const radRouge = document.getElementById('lbl-bms-vigilance-rouge');
            const inputVigilance = document.querySelector('input[name="bms-vigilance"]:checked');
            const vigilance = inputVigilance ? inputVigilance.value : 'orange';

            // Ajustement visuel des 3 pilules de vigilance
            [
                { el: radJaune, val: 'jaune', col: '#eab308', bg: 'rgba(234, 179, 8, 0.25)', border: '1.5px solid #eab308' },
                { el: radOrange, val: 'orange', col: '#fb923c', bg: 'rgba(249, 115, 22, 0.25)', border: '1.5px solid #f97316' },
                { el: radRouge, val: 'rouge', col: '#f87171', bg: 'rgba(239, 68, 68, 0.25)', border: '1.5px solid #ef4444' }
            ].forEach(cfg => {
                if (!cfg.el) return;
                if (cfg.val === vigilance) {
                    cfg.el.style.background = cfg.bg;
                    cfg.el.style.border = cfg.border;
                    cfg.el.style.fontWeight = '800';
                } else {
                    cfg.el.style.background = 'rgba(255, 255, 255, 0.04)';
                    cfg.el.style.border = '1px solid rgba(255, 255, 255, 0.12)';
                    cfg.el.style.fontWeight = '600';
                }
            });

            const cumulInput = document.getElementById('sim-bms-cumul-mm');
            const cumul = parseFloat((cumulInput && cumulInput.value) || 30.0);
            const hDeb = document.getElementById('sim-bms-heure-debut') ? document.getElementById('sim-bms-heure-debut').value : '07:00';
            const hFin = document.getElementById('sim-bms-heure-fin') ? document.getElementById('sim-bms-heure-fin').value : '21:00';
            const profil = document.getElementById('sim-bms-profil') ? document.getElementById('sim-bms-profil').value : 'cloche';

            // Calcul de la durée en heures
            let duree = 14.0;
            try {
                const [h1, m1] = hDeb.split(':').map(Number);
                const [h2, m2] = hFin.split(':').map(Number);
                let t1 = h1 + m1 / 60.0;
                let t2 = h2 + m2 / 60.0;
                if (t2 <= t1) t2 += 24.0;
                duree = Math.round((t2 - t1) * 10) / 10;
            } catch (_) {}

            const dureeBadge = document.getElementById('sim-bms-duree-badge');
            if (dureeBadge) dureeBadge.textContent = `⏱️ ${duree} h d'alerte`;

            // Estimation de crête indicative
            let iMaxEstime = 0.0;
            if (profil === 'uniforme') {
                iMaxEstime = Math.round((cumul / Math.max(1.0, duree)) * 10) / 10;
            } else if (profil === 'orage_concentre') {
                iMaxEstime = Math.round(((cumul * 0.75) / 2.0) * 10) / 10;
            } else {
                iMaxEstime = Math.round(((cumul / Math.max(1.0, duree)) * 2.4) * 10) / 10;
            }

            const previewText = document.getElementById('sim-bms-preview-text');
            const previewBox = document.getElementById('sim-bms-preview-note');
            const borderCol = (vigilance === 'rouge') ? '#ef4444' : ((vigilance === 'jaune') ? '#eab308' : '#f97316');
            if (previewBox) previewBox.style.borderLeftColor = borderCol;

            const symbole = (vigilance === 'rouge') ? '🔴' : ((vigilance === 'jaune') ? '🟡' : '🟠');
            if (previewText) {
                previewText.innerHTML = `${symbole} <b>Alerte BMS Vigilance ${vigilance.charAt(0).toUpperCase() + vigilance.slice(1)} :</b> ` +
                    `cumul de <b>${cumul.toFixed(1)} mm</b> prévu entre <b>${hDeb}</b> et <b>${hFin}</b> (${duree} h). ` +
                    `Intensité de crête estimée : <b>${iMaxEstime.toFixed(1)} mm/h</b>.`;
            }

            // Mettre à jour la durée de calcul globale dans la modale
            const dureeSel = document.getElementById('sim-select-duree');
            if (dureeSel) {
                const simDuree = Math.min(24.0, Math.ceil(duree + 1.0));
                let optFound = false;
                for (let i = 0; i < dureeSel.options.length; i++) {
                    if (parseFloat(dureeSel.options[i].value) === simDuree) {
                        dureeSel.selectedIndex = i;
                        optFound = true;
                        break;
                    }
                }
                if (!optFound) {
                    dureeSel.value = simDuree >= 20 ? '24.0' : (simDuree >= 10 ? '12.0' : '6.0');
                }
            }
        };

        window.basculerSaisieTelegrammeBMS = function() {
            const c = document.getElementById('sim-bms-telegramme-container');
            if (c) {
                c.style.display = (c.style.display === 'none' || !c.style.display) ? 'block' : 'none';
                if (c.style.display === 'block') {
                    const txt = document.getElementById('sim-bms-telegramme-texte');
                    if (txt) txt.focus();
                }
            }
        };

        window.analyserEtAppliquerTelegrammeBMS = function() {
            const txtEl = document.getElementById('sim-bms-telegramme-texte');
            const texte = (txtEl && txtEl.value) ? txtEl.value.trim() : '';
            if (!texte) {
                window.dialogueAlerte("Veuillez coller le texte officiel du bulletin météorologique spécial (ONM).", 'info');
                return;
            }

            // 1. Détection du niveau de vigilance (jaune, orange, rouge)
            let vigTrouve = null;
            if (/\b(rouge|red)\b/i.test(texte)) {
                vigTrouve = 'rouge';
            } else if (/\b(orange)\b/i.test(texte)) {
                vigTrouve = 'orange';
            } else if (/\b(jaune|yellow)\b/i.test(texte)) {
                vigTrouve = 'jaune';
            }
            if (vigTrouve) {
                const rad = document.querySelector(`input[name="bms-vigilance"][value="${vigTrouve}"]`);
                if (rad) rad.checked = true;
            }

            // 2. Détection du cumul de pluie (ex: "30 à 50 mm", "40 mm", "20-40 mm")
            const regPlage = /(\d+(?:[.,]\d+)?)\s*(?:à|a|-|\/)\s*(\d+(?:[.,]\d+)?)\s*mm/i;
            const regUnique = /(\d+(?:[.,]\d+)?)\s*mm/i;
            let cumulTrouve = null;

            const matchPlage = texte.match(regPlage);
            if (matchPlage) {
                const c1 = parseFloat(matchPlage[1].replace(',', '.'));
                const c2 = parseFloat(matchPlage[2].replace(',', '.'));
                // Retenir la borne supérieure de l'averse ou la moyenne
                cumulTrouve = Math.max(c1, c2);
            } else {
                const matchUnique = texte.match(regUnique);
                if (matchUnique) {
                    cumulTrouve = parseFloat(matchUnique[1].replace(',', '.'));
                }
            }

            if (cumulTrouve && !isNaN(cumulTrouve) && cumulTrouve > 0) {
                const cumulInput = document.getElementById('sim-bms-cumul-mm');
                if (cumulInput) cumulInput.value = String(Math.round(cumulTrouve));
            }

            // 3. Détection des heures de validité (ex: "de 07h00 à 21h00", "07:00 au 21:00")
            const regHeures = /(?:de|a partir de|du)?\s*(\d{1,2})[h:](\d{2})?\s*(?:à|a|-|au|\/)\s*(\d{1,2})[h:](\d{2})?/i;
            const matchH = texte.match(regHeures);
            if (matchH) {
                const h1 = String(parseInt(matchH[1], 10)).padStart(2, '0');
                const m1 = String(parseInt(matchH[2] || '0', 10)).padStart(2, '0');
                const h2 = String(parseInt(matchH[3], 10)).padStart(2, '0');
                const m2 = String(parseInt(matchH[4] || '0', 10)).padStart(2, '0');

                const debEl = document.getElementById('sim-bms-heure-debut');
                const finEl = document.getElementById('sim-bms-heure-fin');
                if (debEl) debEl.value = `${h1}:${m1}`;
                if (finEl) finEl.value = `${h2}:${m2}`;
            }

            // 4. Détection de date (ex: "12/11/2026", "12-11-2026")
            const regDate = /(\d{1,2})[\/\-.](\d{1,2})[\/\-.](\d{4})/;
            const matchDate = texte.match(regDate);
            if (matchDate) {
                const j = String(parseInt(matchDate[1], 10)).padStart(2, '0');
                const m = String(parseInt(matchDate[2], 10)).padStart(2, '0');
                const a = matchDate[3];
                const dateEl = document.getElementById('sim-bms-date');
                if (dateEl) dateEl.value = `${a}-${m}-${j}`;
            }

            // Fermer l'encadré et actualiser
            const cont = document.getElementById('sim-bms-telegramme-container');
            if (cont) cont.style.display = 'none';

            window.onChangementParametresBMS();
        };

        window.telechargerOrdreMissionTerrain = function() {
            window.location.href = '/api/v1/simulations/bms/ordre-mission-pdf';
        };

        window.basculerInfobulleBMS = function(event) {
            if (event) event.stopPropagation();
            const pop = document.getElementById('topbar-bms-popover');
            if (!pop) return;
            const estVisible = (pop.style.display === 'block');
            if (typeof window.fermerTousLesMenusTopbar === 'function') {
                window.fermerTousLesMenusTopbar(estVisible ? null : 'bms');
            }
            pop.style.display = estVisible ? 'none' : 'block';
        };

        window.fermerInfobulleBMS = function(event) {
            if (event) event.stopPropagation();
            const pop = document.getElementById('topbar-bms-popover');
            if (pop) pop.style.display = 'none';
        };

        // Fermer l'infobulle au clic extérieur
        document.addEventListener('click', function(e) {
            const pop = document.getElementById('topbar-bms-popover');
            const pill = document.getElementById('topbar-bms-pill');
            if (pop && pop.style.display === 'block') {
                if (!pop.contains(e.target) && (!pill || !pill.contains(e.target))) {
                    pop.style.display = 'none';
                }
            }
        });
