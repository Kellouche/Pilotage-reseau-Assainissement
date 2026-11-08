/**
 * ================================================================================
 * Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
 * Auteur : Dr Abdelhakim KELLOUCHE
 * Date de création : 2026-04-20
 * Date de modification : 2026-11-08
 * Objet : Catalogue des jeux de données, chargement démo, master et import INP/GPKG
 * ================================================================================
 */

// ==========================================
        // GESTION DU PROJET RÉSEAU & OPTION B
        // ==========================================
        function montrerModalProjet(show) {
            const el = document.getElementById('modal-project');
            if (el) {
                el.style.display = show ? 'flex' : 'none';
                if (show) chargerCatalogueDatasets();
            }
        }
        window.montrerModalProjet = montrerModalProjet;

        window.chargerCatalogueDatasets = async function() {
            const cont = document.getElementById('container-benchmark-datasets');
            const activeCont = document.getElementById('container-active-project');
            if (!cont) return;
            try {
                const token = localStorage.getItem('swmm_access_token');
                const headers = token ? { 'Authorization': `Bearer ${token}` } : {};
                const resp = await fetch('/api/v1/network/datasets?_t=' + Date.now(), { headers, credentials: 'include', cache: 'no-store' });
                const res = await resp.json();

                // Affichage du projet en cours si disponible
                if (activeCont) {
                    if (res && res.active_project) {
                        const ap = res.active_project;
                        activeCont.style.display = 'block';
                        activeCont.innerHTML = `
                            <div style="background: linear-gradient(135deg, rgba(2, 132, 199, 0.18), rgba(15, 23, 42, 0.8)); border: 1.5px solid #0284c7; border-radius: 12px; padding: 14px 18px; display: flex; align-items: center; justify-content: space-between; gap: 14px; box-shadow: 0 4px 16px rgba(2, 132, 199, 0.15);">
                                <div style="flex: 1;">
                                    <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 3px;">
                                        <span style="font-weight: 700; color: #38bdf8; font-size: 0.95rem;">
                                            <i class="fas fa-history me-1"></i> ${ap.name}
                                        </span>
                                        <span style="font-size: 0.68rem; background: rgba(56, 189, 248, 0.25); color: #38bdf8; border: 1px solid rgba(56, 189, 248, 0.5); padding: 2px 7px; border-radius: 4px; font-weight: 800; text-transform: uppercase;">
                                            Projet en cours
                                        </span>
                                    </div>
                                    <div style="font-size: 0.78rem; color: #cbd5e1;">
                                        Reprendre vos travaux sur le réseau en cours d'édition.
                                    </div>
                                    <div style="font-size: 0.72rem; color: #94a3b8; margin-top: 4px;">
                                        <i class="fas fa-network-wired me-1"></i> ${ap.pipes_count} canalisations &bull; <i class="fas fa-bullseye me-1"></i> ${ap.nodes_count} regards
                                    </div>
                                </div>
                                <button onclick="reprendreProjetEnCours();" class="btn btn-sm" style="background: #0284c7; color: white; border: none; font-weight: 700; padding: 9px 18px; border-radius: 8px; cursor: pointer; white-space: nowrap; font-size: 0.85rem; box-shadow: 0 4px 12px rgba(2, 132, 199, 0.4);">
                                    <i class="fas fa-folder-open me-1"></i> Ouvrir ce projet
                                </button>
                            </div>
                        `;
                    } else {
                        activeCont.style.display = 'none';
                        activeCont.innerHTML = '';
                    }
                }

                if (res && res.datasets) {
                    const epaDatasets = res.datasets.filter(ds => ds.category === 'epa_certified' || ds.is_official);
                    const otherDatasets = res.datasets.filter(ds => !(ds.category === 'epa_certified' || ds.is_official));

                    let html = '';
                    if (epaDatasets.length > 0) {
                        html += `
                            <div style="display: grid; grid-template-columns: repeat(auto-fill, minmax(175px, 1fr)); gap: 12px; margin-bottom: 18px;">
                                ${epaDatasets.map(ds => `
                                    <div onclick="chargerJeuDeDonnees('${ds.id}')"
                                         style="background: rgba(255, 255, 255, 0.03); border: 1.5px solid rgba(255, 255, 255, 0.08); border-radius: 12px; padding: 14px 10px; text-align: center; cursor: pointer; transition: all 0.2s ease; display: flex; flex-direction: column; align-items: center; justify-content: space-between;"
                                         onmouseover="this.style.background='rgba(2, 132, 199, 0.12)'; this.style.borderColor='#38bdf8'; this.style.transform='translateY(-2px)';"
                                         onmouseout="this.style.background='rgba(255, 255, 255, 0.03)'; this.style.borderColor='rgba(255, 255, 255, 0.08)'; this.style.transform='translateY(0)';"
                                         title="${ds.description}">
                                        
                                        <div style="width: 48px; height: 48px; border-radius: 12px; background: rgba(56, 189, 248, 0.12); border: 1px solid rgba(56, 189, 248, 0.3); display: flex; align-items: center; justify-content: center; margin-bottom: 8px; font-size: 20px; color: ${ds.icon_color || '#38bdf8'};">
                                            <i class="fas ${ds.icon || 'fa-tint'}"></i>
                                        </div>

                                        <div style="font-weight: 700; color: #f8fafc; font-size: 0.86rem; margin-bottom: 4px; line-height: 1.25; min-height: 32px; display: flex; align-items: center; justify-content: center;">
                                            ${ds.short_name || ds.title}
                                        </div>

                                        <div style="margin-bottom: 6px;">
                                            <span style="font-size: 0.65rem; background: rgba(16, 185, 129, 0.18); color: #34d399; border: 1px solid rgba(16, 185, 129, 0.4); padding: 2px 6px; border-radius: 4px; font-weight: 700; text-transform: uppercase;">
                                                <i class="fas fa-check-circle me-1"></i> EPA Certifié
                                            </span>
                                        </div>

                                        <div style="font-size: 0.70rem; color: #94a3b8; margin-bottom: 10px;">
                                            ${ds.pipes_count} conduites &bull; ${ds.nodes_count} regards
                                        </div>

                                        <button class="btn btn-sm" style="width: 100%; background: #0284c7; color: white; border: none; font-weight: 700; padding: 5px 10px; border-radius: 6px; font-size: 0.75rem; pointer-events: none;">
                                            <i class="fas fa-folder-open me-1"></i> Charger
                                        </button>
                                    </div>
                                `).join('')}
                            </div>
                        `;
                    }

                    if (otherDatasets.length > 0) {
                        html += `
                            <div style="font-weight: 700; font-size: 0.78rem; color: #94a3b8; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 8px; display: flex; align-items: center; gap: 6px;">
                                <i class="fas fa-city"></i> Réseaux d'Exemple &amp; Ville
                            </div>
                            <div style="display: grid; gap: 10px;">
                                ${otherDatasets.map(ds => `
                                    <div style="background: rgba(255, 255, 255, 0.03); border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 12px; padding: 12px 16px; display: flex; align-items: center; justify-content: space-between; gap: 12px;">
                                        <div style="display: flex; align-items: center; gap: 12px; flex: 1;">
                                            <div style="width: 40px; height: 40px; border-radius: 10px; background: ${ds.badge_color}22; border: 1px solid ${ds.badge_color}44; display: flex; align-items: center; justify-content: center; font-size: 18px; color: ${ds.icon_color || ds.badge_color};">
                                                <i class="fas ${ds.icon || 'fa-network-wired'}"></i>
                                            </div>
                                            <div>
                                                <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 2px;">
                                                    <span style="font-weight: 700; color: #f8fafc; font-size: 0.88rem;">${ds.title}</span>
                                                    <span style="font-size: 0.65rem; background: ${ds.badge_color}22; color: ${ds.badge_color}; border: 1px solid ${ds.badge_color}44; padding: 2px 6px; border-radius: 4px; font-weight: 800; text-transform: uppercase;">
                                                        ${ds.badge}
                                                    </span>
                                                </div>
                                                <div style="font-size: 0.76rem; color: #94a3b8;">${ds.description}</div>
                                                <div style="font-size: 0.70rem; color: #64748b; margin-top: 3px;">
                                                    <i class="fas fa-network-wired me-1"></i> ${ds.pipes_count} canalisations &bull; <i class="fas fa-bullseye me-1"></i> ${ds.nodes_count} regards
                                                </div>
                                            </div>
                                        </div>
                                        <button onclick="chargerJeuDeDonnees('${ds.id}')" class="btn btn-sm" style="background: ${ds.badge_color}; color: white; border: none; font-weight: 700; padding: 7px 14px; border-radius: 8px; cursor: pointer; white-space: nowrap; font-size: 0.8rem;">
                                            <i class="fas fa-folder-open me-1"></i> Charger
                                        </button>
                                    </div>
                                `).join('')}
                            </div>
                        `;
                    }

                    cont.innerHTML = html;
                }
            } catch (e) {
                console.warn('Erreur chargement catalogue datasets:', e);
            }
        };

        window.chargerJeuDeDonnees = async function(datasetId) {
            montrerChargement(true);
            try {
                const token = localStorage.getItem('swmm_access_token');
                const headers = { 'Content-Type': 'application/json' };
                if (token) headers['Authorization'] = `Bearer ${token}`;
                const resp = await fetch(`/api/v1/network/load-dataset/${datasetId}`, { method: 'POST', headers, credentials: 'include' });
                const data = await resp.json();
                if (!resp.ok) throw new Error(data.detail || 'Erreur lors du chargement du jeu de données');
                sessionStorage.setItem('projet_charge', 'true');
                montrerModalProjet(false);
                chargerDonneesInitiales();
            } catch (err) {
                alert('Erreur : ' + err.message);
                montrerChargement(false);
            }
        };

        window.chargerReseauDemo = async function() {
            return window.chargerJeuDeDonnees('demo_temoin');
        };

        window.chargerReseauMaster = async function() {
            return window.chargerJeuDeDonnees('ville_complete');
        };

        window.reinitialiserProjetVierge = async function() {
            if (!confirm('Voulez-vous réinitialiser votre projet et vider le réseau affiché ?')) return;
            montrerChargement(true);
            try {
                const token = localStorage.getItem('swmm_access_token');
                const headers = { 'Content-Type': 'application/json' };
                if (token) headers['Authorization'] = `Bearer ${token}`;
                const resp = await fetch('/api/v1/network/reset', { method: 'POST', headers, credentials: 'include' });
                const data = await resp.json();
                if (!resp.ok) throw new Error(data.detail || 'Erreur lors de la réinitialisation');
                sessionStorage.setItem('projet_charge', 'true');
                montrerModalProjet(false);
                chargerDonneesInitiales();
            } catch (err) {
                alert('Erreur : ' + err.message);
                montrerChargement(false);
            }
        };

        window.televerserFichierReseau = async function(event) {
            const file = event.target.files[0];
            if (!file) return;
            const ext = file.name.split('.').pop().toLowerCase();
            if (ext !== 'gpkg' && ext !== 'inp') {
                alert("Format non supporté. Veuillez sélectionner un fichier .inp (EPA SWMM) ou .gpkg (GeoPackage).");
                return;
            }
            montrerChargement(true, `Chargement et analyse du réseau : ${file.name}...`);
            try {
                const formData = new FormData();
                formData.append('file', file);
                const token = localStorage.getItem('swmm_access_token');
                const headers = {};
                if (token) headers['Authorization'] = `Bearer ${token}`;
                const resp = await fetch('/api/v1/network/upload', {
                    method: 'POST',
                    headers,
                    credentials: 'include',
                    body: formData
                });
                const data = await resp.json();
                if (!resp.ok) throw new Error(data.detail || 'Erreur lors du téléversement');
                sessionStorage.setItem('projet_charge', 'true');
                montrerModalProjet(false);
                chargerDonneesInitiales();
            } catch (err) {
                alert('Erreur téléversement : ' + err.message);
                montrerChargement(false);
            } finally {
                if (event.target) event.target.value = '';
            }
        };
        window.televerserGpkg = window.televerserFichierReseau;

        // ==========================================
        // GESTION DU MENU RESSOURCES & AIDE
        // ==========================================
        window.basculerMenuRessources = function(e) {
            if (e) e.stopPropagation();
            const d = document.getElementById('resources-dropdown');
            if (d) d.style.display = (d.style.display === 'block') ? 'none' : 'block';
        };

        window.fermerMenuRessources = function() {
            const d = document.getElementById('resources-dropdown');
            if (d) d.style.display = 'none';
        };

        // ==========================================
        // GESTION DU MENU PROFIL & SÉCURITÉ UTILISATEUR
        // ==========================================
        window.basculerMenuProfil = function(e) {
            if (e) e.stopPropagation();
            const d = document.getElementById('user-profile-dropdown');
            if (d) d.style.display = (d.style.display === 'block') ? 'none' : 'block';
        };

        window.fermerMenuProfil = function() {
            const d = document.getElementById('user-profile-dropdown');
            if (d) d.style.display = 'none';
        };

        // ==========================================
        // GESTION DU MENU ACTIONS & SIMULATION
        // ==========================================
        window.basculerMenuActions = function(e) {
            if (e) e.stopPropagation();
            const d = document.getElementById('actions-dropdown');
            if (d) d.style.display = (d.style.display === 'block') ? 'none' : 'block';
        };

        window.fermerMenuActions = function() {
            const d = document.getElementById('actions-dropdown');
            if (d) d.style.display = 'none';
        };

        window.activerActionsSimulation = function(actif) {
            const itemResults = document.getElementById('action-item-results');
            const itemInterp = document.getElementById('action-item-interpretation');
            
            [itemResults, itemInterp].forEach(el => {
                if (!el) return;
                if (actif) {
                    el.classList.remove('disabled');
                    el.style.opacity = '1';
                    el.style.pointerEvents = 'auto';
                    el.style.cursor = 'pointer';
                } else {
                    el.classList.add('disabled');
                    el.style.opacity = '0.45';
                    el.style.pointerEvents = 'none';
                    el.style.cursor = 'not-allowed';
                }
            });
        };

        window.telechargerModeleInpActif = async function() {
            let notif = null;
            if (typeof afficherNotification === 'function') {
                notif = afficherNotification("Préparation et export du modèle SWMM (.inp)...", "info", 5000);
            }
            try {
                let response = await fetch('/api/v1/network/export/inp');
                if (!response.ok && response.status === 404) {
                    const fallbackResp = await fetch('/api/v1/simulations/download/inp');
                    if (fallbackResp.ok) {
                        response = fallbackResp;
                    }
                }

                if (!response.ok) {
                    const err = await response.json().catch(() => ({}));
                    throw new Error(err.detail || `Erreur (${response.status}) : Impossible de récupérer le fichier de modèle.`);
                }

                const blob = await response.blob();
                let filename = 'modele_swmm.inp';
                const disposition = response.headers.get('content-disposition');
                if (disposition && disposition.includes('filename=')) {
                    const match = disposition.match(/filename="?([^";]+)"?/);
                    if (match && match[1]) filename = match[1];
                } else if (window._rawNetworkData && window._rawNetworkData.project_name) {
                    filename = `${window._rawNetworkData.project_name.replace(/[^\w\-_.]+/g, '_')}.inp`;
                }

                const downloadUrl = window.URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = downloadUrl;
                a.download = filename;
                document.body.appendChild(a);
                a.click();
                document.body.removeChild(a);
                window.URL.revokeObjectURL(downloadUrl);

                if (typeof afficherNotification === 'function') {
                    afficherNotification(`Modèle ${filename} téléchargé avec succès !`, "success", 4000);
                }
            } catch (e) {
                console.error("Erreur lors de l'export INP:", e);
                if (typeof afficherNotification === 'function') {
                    afficherNotification(`Échec du téléchargement du modèle : ${e.message}`, "error", 6000);
                } else {
                    alert(`Échec du téléchargement du modèle : ${e.message}`);
                }
            }
        };

        window.afficherDerniersResultats = function() {
            if (!window._dernierResultatSimulation) {
                alert("Aucun résultat de simulation disponible pour ce réseau. Veuillez d'abord lancer une simulation.");
                return;
            }
            afficherResultatsSimulation(window._dernierResultatSimulation);
            ouvrirModalSimulation();
        };

        window.ouvrirModalInterpretation = function() {
            if (!window._dernierResultatSimulation) {
                alert("Aucun résultat de simulation disponible pour l'interprétation. Veuillez d'abord exécuter une simulation.");
                return;
            }
            const m = document.getElementById('modal-interpretation');
            if (m) {
                m.style.display = 'flex';
                genererRapportInterpretation(window._dernierResultatSimulation);
            }
        };

        window.fermerModalInterpretation = function() {
            const m = document.getElementById('modal-interpretation');
            if (m) m.style.display = 'none';
            if (window.carte && window._dernierResultatSimulation) {
                setTimeout(() => {
                    carte.invalidateSize(true);
                    zoomerSurZoneSimulee(window._dernierResultatSimulation);
                    mettreAJourIHMZoneSimulee(window._dernierResultatSimulation);
                }, 80);
            }
        };
