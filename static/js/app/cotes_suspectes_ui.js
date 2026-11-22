/**
 * ================================================================================
 * Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
 * Auteur : Dr Abdelhakim KELLOUCHE
 * Date : 2026-11-22
 * Objet : Interface utilisateur du Registre des Cotes & Profondeurs Suspectes
 *         (Human-in-the-Loop Altimétrie & Certification des Silos Verticaux)
 * ================================================================================
 */

(function () {
    let _cotesSuspectesData = [];
    let _filtreStatutActif = 'tous';
    let _termeRecherche = '';

    window.ouvrirModalCotesSuspectes = function () {
        const modal = document.getElementById('modal-cotes-suspectes');
        if (modal) {
            modal.style.display = 'flex';
            window.chargerRegistreCotesSuspectes();
        }
    };

    window.fermerModalCotesSuspectes = function () {
        const modal = document.getElementById('modal-cotes-suspectes');
        if (modal) {
            modal.style.display = 'none';
        }
    };

    window.actualiserBadgeCotesSuspectes = async function () {
        try {
            const token = localStorage.getItem('token') || '';
            const res = await fetch('/api/v1/simulations/cotes-suspectes?statut=a_valider', {
                headers: { 'Authorization': token ? `Bearer ${token}` : '' }
            });
            if (!res.ok) return;
            const data = await res.json();
            const count = data.total || 0;

            const badgeTopbar = document.getElementById('badge-topbar-cotes-count');
            const pillTopbar = document.getElementById('topbar-cotes-suspectes-pill');
            const pillText = document.getElementById('topbar-cotes-count-text');

            if (badgeTopbar) {
                if (count > 0) {
                    badgeTopbar.textContent = count;
                    badgeTopbar.style.display = 'inline-block';
                } else {
                    badgeTopbar.style.display = 'none';
                }
            }

            if (pillTopbar && pillText) {
                if (count > 0) {
                    pillText.textContent = `${count} cote${count > 1 ? 's' : ''} suspecte${count > 1 ? 's' : ''}`;
                    pillTopbar.style.display = 'inline-flex';
                } else {
                    pillTopbar.style.display = 'none';
                }
            }
        } catch (e) {
            console.warn('[CotesSuspectes] Erreur lors de l\'actualisation du badge:', e);
        }
    };

    window.chargerRegistreCotesSuspectes = async function () {
        const tbody = document.getElementById('cotes-suspectes-tbody');
        if (tbody) {
            tbody.innerHTML = `
                <tr>
                    <td colspan="7" style="text-align: center; padding: 36px 14px; color: #94a3b8;">
                        <i class="fas fa-spinner fa-spin" style="font-size: 20px; color: #38bdf8; margin-bottom: 8px; display: block;"></i>
                        Chargement du registre altimétrique...
                    </td>
                </tr>
            `;
        }

        try {
            const token = localStorage.getItem('token') || '';
            const res = await fetch('/api/v1/simulations/cotes-suspectes', {
                headers: { 'Authorization': token ? `Bearer ${token}` : '' }
            });

            if (!res.ok) {
                throw new Error(`HTTP ${res.status}`);
            }

            const data = await res.json();
            _cotesSuspectesData = data.items || [];

            // Mise à jour des compteurs statistiques
            const total = _cotesSuspectesData.length;
            const aValider = _cotesSuspectesData.filter(item => item.statut === 'a_valider').length;
            const valides = _cotesSuspectesData.filter(item => item.statut === 'valide').length;
            const brutes = _cotesSuspectesData.filter(item => item.statut === 'conserve_brut').length;

            const elTotal = document.getElementById('cotes-stat-total');
            const elAValider = document.getElementById('cotes-stat-a-valider');
            const elValide = document.getElementById('cotes-stat-valide');
            const elBrut = document.getElementById('cotes-stat-brut');
            const elBadgePending = document.getElementById('badge-modal-cotes-pending');

            if (elTotal) elTotal.textContent = total;
            if (elAValider) elAValider.textContent = aValider;
            if (elValide) elValide.textContent = valides;
            if (elBrut) elBrut.textContent = brutes;
            if (elBadgePending) elBadgePending.textContent = `${aValider} à certifier`;

            const cAll = document.getElementById('cotes-count-filtre-tous');
            const cPend = document.getElementById('cotes-count-filtre-a-valider');
            const cVal = document.getElementById('cotes-count-filtre-valide');
            const cBrut = document.getElementById('cotes-count-filtre-brut');
            if (cAll) cAll.textContent = total;
            if (cPend) cPend.textContent = aValider;
            if (cVal) cVal.textContent = valides;
            if (cBrut) cBrut.textContent = brutes;

            // Rendu du tableau
            window.rendreTableauCotesSuspectes();

            // Actualisation badge topbar
            window.actualiserBadgeCotesSuspectes();

        } catch (e) {
            console.error('[CotesSuspectes] Erreur lors du chargement:', e);
            if (tbody) {
                tbody.innerHTML = `
                    <tr>
                        <td colspan="7" style="text-align: center; padding: 28px 14px; color: #f87171;">
                            <i class="fas fa-exclamation-triangle" style="font-size: 20px; margin-bottom: 6px; display: block;"></i>
                            Erreur lors du chargement des cotes suspectes : ${e.message}
                        </td>
                    </tr>
                `;
            }
        }
    };

    window.filtrerCotesSuspectes = function (statut) {
        _filtreStatutActif = statut;

        // Mise à jour du style des boutons filtres
        const btns = {
            'tous': document.getElementById('btn-filtre-cotes-tous'),
            'a_valider': document.getElementById('btn-filtre-cotes-a-valider'),
            'valide': document.getElementById('btn-filtre-cotes-valides'),
            'conserve_brut': document.getElementById('btn-filtre-cotes-brutes'),
        };

        for (const [key, btn] of Object.entries(btns)) {
            if (!btn) continue;
            if (key === statut) {
                btn.style.background = 'rgba(56, 189, 248, 0.2)';
                btn.style.borderColor = '#38bdf8';
                btn.style.color = '#38bdf8';
                btn.style.fontWeight = '700';
            } else {
                btn.style.background = 'transparent';
                btn.style.borderColor = 'rgba(255, 255, 255, 0.15)';
                btn.style.color = '#94a3b8';
                btn.style.fontWeight = '600';
            }
        }

        window.rendreTableauCotesSuspectes();
    };

    window.rechercherCoteSuspecte = function (texte) {
        _termeRecherche = (texte || '').trim().toLowerCase();
        window.rendreTableauCotesSuspectes();
    };

    window.rendreTableauCotesSuspectes = function () {
        const tbody = document.getElementById('cotes-suspectes-tbody');
        if (!tbody) return;

        let items = _cotesSuspectesData;

        // Filtre de statut
        if (_filtreStatutActif !== 'tous') {
            items = items.filter(it => it.statut === _filtreStatutActif);
        }

        // Filtre de recherche texte
        if (_termeRecherche) {
            items = items.filter(it =>
                String(it.node_id).toLowerCase().includes(_termeRecherche) ||
                String(it.motif_suspicion || '').toLowerCase().includes(_termeRecherche)
            );
        }

        if (items.length === 0) {
            tbody.innerHTML = `
                <tr>
                    <td colspan="7" style="text-align: center; padding: 40px 14px; color: #94a3b8;">
                        <i class="fas fa-check-circle" style="font-size: 26px; color: #10b981; margin-bottom: 8px; display: block;"></i>
                        Aucune cote suspecte dans cette vue.
                    </td>
                </tr>
            `;
            return;
        }

        let html = '';
        items.forEach((item, idx) => {
            const isPair = idx % 2 === 0;
            const bg = isPair ? 'rgba(30, 41, 59, 0.4)' : 'rgba(15, 23, 42, 0.3)';

            // Statut badge
            let badgeStatut = '';
            if (item.statut === 'valide') {
                badgeStatut = `<span style="font-size: 10px; background: rgba(16, 185, 129, 0.2); color: #34d399; border: 1px solid rgba(16, 185, 129, 0.4); padding: 2px 8px; border-radius: 9999px; font-weight: 700;"><i class="fas fa-check me-1"></i> Certifiée</span>`;
            } else if (item.statut === 'conserve_brut') {
                badgeStatut = `<span style="font-size: 10px; background: rgba(56, 189, 248, 0.2); color: #38bdf8; border: 1px solid rgba(56, 189, 248, 0.4); padding: 2px 8px; border-radius: 9999px; font-weight: 700;"><i class="fas fa-shield me-1"></i> Conservée brute</span>`;
            } else {
                badgeStatut = `<span style="font-size: 10px; background: rgba(245, 158, 11, 0.2); color: #fbbf24; border: 1px solid rgba(245, 158, 11, 0.4); padding: 2px 8px; border-radius: 9999px; font-weight: 700;"><i class="fas fa-clock me-1"></i> À certifier</span>`;
            }

            // Valeur proposée dans l'input
            const valInput = (item.valeur_validee !== null && item.valeur_validee !== undefined)
                ? item.valeur_validee
                : (item.valeur_suggeree !== null && item.valeur_suggeree !== undefined ? item.valeur_suggeree : item.valeur_brute);

            html += `
                <tr style="background: ${bg}; border-bottom: 1px solid rgba(255, 255, 255, 0.05); transition: background 0.15s;" onmouseover="this.style.background='rgba(56, 189, 248, 0.1)'" onmouseout="this.style.background='${bg}'">
                    <!-- Nœud -->
                    <td style="padding: 10px 14px; font-weight: 700; color: #f8fafc;">
                        <span style="display: inline-flex; align-items: center; gap: 6px;">
                            <i class="fas fa-circle-dot" style="color: #38bdf8; font-size: 10px;"></i>
                            <span>Regard ${escapeHtml(item.node_id)}</span>
                        </span>
                    </td>

                    <!-- Champ -->
                    <td style="padding: 10px 14px; color: #cbd5e1;">
                        <span style="font-family: monospace; font-size: 0.74rem; background: rgba(255,255,255,0.06); padding: 2px 6px; border-radius: 4px;">
                            ${escapeHtml(item.champ)}
                        </span>
                    </td>

                    <!-- Valeur Brute -->
                    <td style="padding: 10px 14px; text-align: right; font-weight: 700; color: #f87171;">
                        ${Number(item.valeur_brute).toFixed(2)} m
                        <span title="Anomalie altimétrique (> 15m)" style="margin-left: 4px; font-size: 11px;">⚠️</span>
                    </td>

                    <!-- Motif / Suggestion -->
                    <td style="padding: 10px 14px; color: #e2e8f0; font-size: 0.74rem; max-width: 320px;">
                        <div style="line-height: 1.35;">${escapeHtml(item.motif_suspicion || '')}</div>
                        ${item.valeur_suggeree ? `<div style="color: #34d399; font-weight: 600; margin-top: 2px;">Suggestion : ${Number(item.valeur_suggeree).toFixed(2)} m</div>` : ''}
                    </td>

                    <!-- Saisie / Correction -->
                    <td style="padding: 10px 14px; text-align: center;">
                        <div style="display: inline-flex; align-items: center; gap: 6px;">
                            <input type="number" id="input-cote-${item.node_id}-${item.champ}" step="0.01" min="0.1" max="50" value="${valInput}" style="width: 80px; text-align: center; font-weight: 700; font-size: 0.8rem; background: #0f172a; color: #38bdf8; border: 1px solid rgba(56, 189, 248, 0.4); border-radius: 6px; padding: 4px 6px; outline: none;">
                            <button onclick="validerCoteLigne('${escapeHtml(item.node_id)}', '${escapeHtml(item.champ)}')" title="Certifier cette cote corrigée" style="background: rgba(16, 185, 129, 0.2); border: 1px solid rgba(16, 185, 129, 0.4); color: #34d399; border-radius: 6px; padding: 4px 8px; cursor: pointer; font-size: 11px; font-weight: 700; transition: all 0.15s;" onmouseover="this.style.background='rgba(16, 185, 129, 0.4)'" onmouseout="this.style.background='rgba(16, 185, 129, 0.2)'">
                                <i class="fas fa-check"></i>
                            </button>
                            <button onclick="conserverCoteBruteLigne('${escapeHtml(item.node_id)}', '${escapeHtml(item.champ)}', ${item.valeur_brute})" title="Conserver la valeur brute initiale sans conversion" style="background: rgba(148, 163, 184, 0.15); border: 1px solid rgba(148, 163, 184, 0.3); color: #94a3b8; border-radius: 6px; padding: 4px 6px; cursor: pointer; font-size: 11px;" onmouseover="this.style.background='rgba(148, 163, 184, 0.3)'" onmouseout="this.style.background='rgba(148, 163, 184, 0.15)'">
                                Brut
                            </button>
                        </div>
                    </td>

                    <!-- Statut -->
                    <td style="padding: 10px 14px; text-align: center;">
                        ${badgeStatut}
                    </td>

                    <!-- Actions -->
                    <td style="padding: 10px 14px; text-align: right;">
                        <div style="display: inline-flex; gap: 6px;">
                            <button onclick="localiserNoeudSurCarte('${escapeHtml(item.node_id)}')" title="Localiser le regard sur la carte" style="background: rgba(56, 189, 248, 0.15); border: 1px solid rgba(56, 189, 248, 0.35); color: #38bdf8; border-radius: 6px; padding: 4px 8px; cursor: pointer; font-size: 11px;">
                                <i class="fas fa-map-marker-alt"></i>
                            </button>
                            <button onclick="ouvrirProfilPourNoeud('${escapeHtml(item.node_id)}')" title="Afficher le profil en long traversant cet ouvrage" style="background: rgba(168, 85, 247, 0.15); border: 1px solid rgba(168, 85, 247, 0.35); color: #c084fc; border-radius: 6px; padding: 4px 8px; cursor: pointer; font-size: 11px;">
                                <i class="fas fa-chart-area"></i>
                            </button>
                        </div>
                    </td>
                </tr>
            `;
        });

        tbody.innerHTML = html;
    };

    function _actualiserCompteursLocaux() {
        const total = _cotesSuspectesData.length;
        const aValider = _cotesSuspectesData.filter(item => item.statut === 'a_valider').length;
        const valides = _cotesSuspectesData.filter(item => item.statut === 'valide').length;
        const brutes = _cotesSuspectesData.filter(item => item.statut === 'conserve_brut').length;

        const elTotal = document.getElementById('cotes-stat-total');
        const elAValider = document.getElementById('cotes-stat-a-valider');
        const elValide = document.getElementById('cotes-stat-valide');
        const elBrut = document.getElementById('cotes-stat-brut');
        const elBadgePending = document.getElementById('badge-modal-cotes-pending');

        if (elTotal) elTotal.textContent = total;
        if (elAValider) elAValider.textContent = aValider;
        if (elValide) elValide.textContent = valides;
        if (elBrut) elBrut.textContent = brutes;
        if (elBadgePending) elBadgePending.textContent = `${aValider} à certifier`;

        const cAll = document.getElementById('cotes-count-filtre-tous');
        const cPend = document.getElementById('cotes-count-filtre-a-valider');
        const cVal = document.getElementById('cotes-count-filtre-valide');
        const cBrut = document.getElementById('cotes-count-filtre-brut');
        if (cAll) cAll.textContent = total;
        if (cPend) cPend.textContent = aValider;
        if (cVal) cVal.textContent = valides;
        if (cBrut) cBrut.textContent = brutes;
    }

    window.validerCoteLigne = async function (nodeId, champ) {
        const inp = document.getElementById(`input-cote-${nodeId}-${champ}`);
        if (!inp) return;
        const val = parseFloat(inp.value);
        if (isNaN(val) || val <= 0) {
            alert('Veuillez renseigner une valeur numérique strictement positive.');
            return;
        }

        // Mise à jour optimiste instantanée (0 ms)
        const it = _cotesSuspectesData.find(x => String(x.node_id) === String(nodeId) && x.champ === champ);
        const ancienStatut = it ? it.statut : 'a_valider';
        const ancienneVal = it ? it.valeur_validee : null;
        if (it) {
            it.statut = 'valide';
            it.valeur_validee = val;
            _actualiserCompteursLocaux();
            window.rendreTableauCotesSuspectes();
        }

        try {
            const token = localStorage.getItem('token') || '';
            const res = await fetch('/api/v1/simulations/cotes-suspectes/valider', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': token ? `Bearer ${token}` : ''
                },
                body: JSON.stringify({
                    validations: [{
                        node_id: nodeId,
                        champ: champ,
                        valeur_validee: val,
                        statut: 'valide'
                    }]
                })
            });

            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            window.actualiserBadgeCotesSuspectes();
        } catch (e) {
            if (it) {
                it.statut = ancienStatut;
                it.valeur_validee = ancienneVal;
                _actualiserCompteursLocaux();
                window.rendreTableauCotesSuspectes();
            }
            alert(`Erreur lors de la validation : ${e.message}`);
        }
    };

    window.conserverCoteBruteLigne = async function (nodeId, champ, valBrute) {
        const it = _cotesSuspectesData.find(x => String(x.node_id) === String(nodeId) && x.champ === champ);
        const ancienStatut = it ? it.statut : 'a_valider';
        const ancienneVal = it ? it.valeur_validee : null;
        if (it) {
            it.statut = 'conserve_brut';
            it.valeur_validee = valBrute;
            _actualiserCompteursLocaux();
            window.rendreTableauCotesSuspectes();
        }

        try {
            const token = localStorage.getItem('token') || '';
            const res = await fetch('/api/v1/simulations/cotes-suspectes/valider', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': token ? `Bearer ${token}` : ''
                },
                body: JSON.stringify({
                    validations: [{
                        node_id: nodeId,
                        champ: champ,
                        valeur_validee: valBrute,
                        statut: 'conserve_brut'
                    }]
                })
            });

            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            window.actualiserBadgeCotesSuspectes();
        } catch (e) {
            if (it) {
                it.statut = ancienStatut;
                it.valeur_validee = ancienneVal;
                _actualiserCompteursLocaux();
                window.rendreTableauCotesSuspectes();
            }
            alert(`Erreur lors de la conservation brute : ${e.message}`);
        }
    };

    window.validerToutesSuggestionsCotes = async function () {
        const aValider = _cotesSuspectesData.filter(it => it.statut === 'a_valider');
        if (aValider.length === 0) {
            alert('Toutes les cotes suspectes sont déjà certifiées.');
            return;
        }

        const confirmMsg = `Certifier automatiquement les ${aValider.length} suggestions de correction altimétrique (conversion cm/mm vers mètres) ?`;
        if (!confirm(confirmMsg)) return;

        const payload = aValider.map(it => ({
            node_id: it.node_id,
            champ: it.champ,
            valeur_validee: it.valeur_suggeree !== null && it.valeur_suggeree !== undefined ? it.valeur_suggeree : it.valeur_brute,
            statut: 'valide'
        }));

        // Mise à jour optimiste
        aValider.forEach(it => {
            it.statut = 'valide';
            it.valeur_validee = it.valeur_suggeree !== null && it.valeur_suggeree !== undefined ? it.valeur_suggeree : it.valeur_brute;
        });
        _actualiserCompteursLocaux();
        window.rendreTableauCotesSuspectes();

        try {
            const token = localStorage.getItem('token') || '';
            const res = await fetch('/api/v1/simulations/cotes-suspectes/valider', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': token ? `Bearer ${token}` : ''
                },
                body: JSON.stringify({ validations: payload })
            });

            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            window.actualiserBadgeCotesSuspectes();
        } catch (e) {
            alert(`Erreur lors de la validation en masse : ${e.message}`);
            window.chargerRegistreCotesSuspectes();
        }
    };

    window.localiserNoeudSurCarte = function (nodeId) {
        window.fermerModalCotesSuspectes();
        if (window.ciblerRegardSurCarte) {
            window.ciblerRegardSurCarte(nodeId);
        } else if (window.rechercherEtCiblerNoeud) {
            window.rechercherEtCiblerNoeud(nodeId);
        } else if (window.map) {
            console.log(`[CotesSuspectes] Cible demandée : ${nodeId}`);
        }
    };

    window.ouvrirProfilPourNoeud = function (nodeId) {
        window.fermerModalCotesSuspectes();
        if (window.ouvrirProfilEnLong) {
            window.ouvrirProfilEnLong(nodeId);
        }
    };

    function escapeHtml(str) {
        if (!str) return '';
        return String(str)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#039;');
    }

    // Initialisation au chargement du DOM
    document.addEventListener('DOMContentLoaded', function () {
        setTimeout(window.actualiserBadgeCotesSuspectes, 1500);
    });
})();
