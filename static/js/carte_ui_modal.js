/**
 * ================================================================================
 * Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
 * Auteur : Dr Abdelhakim KELLOUCHE
 * Date de création : 2026-04-20
 * Date de modification : 2026-11-27
 * Objet : Modale de correction : ouverture, suggestion hybride et fermeture
 * ================================================================================
 */

// Minimal modal control (ensure modal opens even if other scripts missing)
function openCorrectionModal(id, type) {
    try {
        // Normaliser l'identifiant : accepter les formats "fid|lat,lng" ou simple "fid"
        let fidCandidate = null;
        if (typeof id === 'string' && id.includes('|')) {
            fidCandidate = id.split('|')[0];
        } else {
            fidCandidate = id;
        }
        // Si l'identifiant reste vide ou non résolvable, afficher une erreur claire
        if (!fidCandidate || fidCandidate === 'Inconnu') {
            if (typeof showError === 'function')
                showError('Impossible de corriger : identifiant invalide ou non reconnu.');
            return;
        }
        // Conserver le fid normalisé pour le reste du flux
        id = fidCandidate;

        // Descriptions et solutions pour chaque type de diagnostic
        const diagnosticSolutions = {
            'geometrie_invalide': {
                title: 'Corriger la position',
                description: 'Corrigez les coordonnées XY du point ou du début de la conduite.',
                solution: 'formulaire_coords',
                suggestionTitle: 'Saisie des coordonnées'
            },
            'conduite_sans_regard': {
                title: 'Ajouter une connexion manquante',
                description: 'Cette conduite n\'est pas connectée à un regard. Créez la connexion en indiquant les nœuds amont et aval.',
                solution: 'formulaire_connexion_with_suggestion',
                suggestionTitle: 'Solution de connexion'
            },
            'troncon_orphelin': {
                title: 'Relier le tronçon orphelin',
                description: 'Ce tronçon est isolé du réseau. Connectez-le aux nœuds amont et aval appropriés.',
                solution: 'formulaire_connexion_with_suggestion',
                suggestionTitle: 'Solution de connexion'
            },
            'incoherence_profondeur': {
                title: 'Corriger l\'incohérence de profondeur',
                description: 'Les profondeurs des nœuds amont et aval sont incohérentes. Ajustez le profil de la conduite.',
                solution: 'formulaire_profil_with_profile',
                suggestionTitle: 'Solution hydraulique'
            },
            'incoherences_amont_aval': {
                title: 'Corriger l\'incohérence amont/aval',
                description: 'Les connexions amont/aval sont manquantes ou incorrectes. Corrigez les nœuds.',
                solution: 'formulaire_connexion_with_suggestion',
                suggestionTitle: 'Solution de connexion'
            },
            'pente_negative': {
                title: 'Corriger la pente négative',
                description: 'La pente est négative. Inversez le profil ou corrigez les profondeurs pour obtenir une pente positive.',
                solution: 'formulaire_profil_with_profile',
                suggestionTitle: 'Solution hydraulique'
            },
            'pente_trop_forte': {
                title: 'Corriger la pente excessive',
                description: 'La pente est trop forte (>50%). Ajustez les profondeurs ou la longueur de la conduite.',
                solution: 'formulaire_profil_with_profile',
                suggestionTitle: 'Solution hydraulique'
            },
            'champs_manquants_conduite': {
                title: 'Compléter les données (conduite)',
                description: 'Des champs essentiels manquent. Complétez les informations de la conduite.',
                solution: 'formulaire_profil_simple',
                suggestionTitle: 'Données manquantes'
            },
            'champs_manquants_regard': {
                title: 'Compléter les données (regard)',
                description: 'Des champs essentiels manquent pour ce regard. Complétez les informations.',
                solution: 'formulaire_coords',
                suggestionTitle: 'Données manquantes'
            }
        };

        const solutionConfig = diagnosticSolutions[type] || {
            title: 'Correction d\'anomalie',
            description: 'Corrigez cette anomalie en saisissant les valeurs appropriées.',
            solution: 'formulaire_profil_with_profile',
            suggestionTitle: 'Proposition'
        };

        // Mettre à jour le titre et la description de la modale
        const titleEl = document.getElementById('modal-title-diagnostic');
        if (titleEl) {
            titleEl.textContent = solutionConfig.title;
        }

        // Mettre à jour le titre de la boîte de suggestion
        const suggestionTitleEl = document.getElementById('suggestion-title');
        if (suggestionTitleEl) {
            suggestionTitleEl.textContent = solutionConfig.suggestionTitle;
        }

        // Parse id value: may be "fid|lat,lng" or just fid or coords
        fidCandidate = null;
        coords = null;
        if (typeof id === 'string' && id.includes('|')) {
            const parts = id.split('|');
            fidCandidate = parts[0];
            const c = parts[1].split(',').map(Number);
            if (c.length === 2 && !isNaN(c[0]) && !isNaN(c[1])) coords = { lat: c[0], lng: c[1] };
        } else if (typeof id === 'string' && id.includes(',')) {
            const c = id.split(',').map(Number);
            if (c.length === 2 && !isNaN(c[0]) && !isNaN(c[1])) coords = { lat: c[0], lng: c[1] };
        } else {
            fidCandidate = id;
        }

        currentCorrectionFid = fidCandidate || null;

        const tgt = document.getElementById('correction-target-id');
        if (tgt) {
            tgt.innerHTML = `<strong>Problème :</strong> ${solutionConfig.description}<br><strong>Cible :</strong> ${fidCandidate || (coords ? coords.lat + ',' + coords.lng : id)}`;
        }

        // Afficher/masquer les sections appropriées
        const profile = document.getElementById('profile-container');
        const suggestionBox = document.getElementById('hybrid-suggestion-box');
        const formCoords = document.getElementById('form-coords');
        const formConnexion = document.getElementById('form-connexion');
        const formProfil = document.getElementById('form-profil');
        const btnApply = document.getElementById('btn-apply-correction');

        // Masquer tous les formulaires par défaut
        if (profile) profile.style.display = 'none';
        if (suggestionBox) suggestionBox.style.display = 'none';
        if (formCoords) formCoords.style.display = 'none';
        if (formConnexion) formConnexion.style.display = 'none';
        if (formProfil) formProfil.style.display = 'none';

        // Afficher la solution appropriée selon le type
        switch (solutionConfig.solution) {
            case 'formulaire_coords':
                // Géométrie: afficher formulaire coordonnées uniquement
                if (formCoords) formCoords.style.display = 'block';
                if (btnApply) btnApply.onclick = () => applyGeometrieCorrection();
                break;

            case 'formulaire_connexion_with_suggestion':
                // Connexion: afficher formulaire + suggestion
                if (suggestionBox) suggestionBox.style.display = 'block';
                if (formConnexion) formConnexion.style.display = 'block';
                if (btnApply) btnApply.onclick = () => applyTopologieCorrection();
                break;

            case 'formulaire_profil_with_profile':
                // Profil avec graphique: afficher profil + formulaire profondeur + suggestion
                if (profile) profile.style.display = 'block';
                if (suggestionBox) suggestionBox.style.display = 'block';
                if (formProfil) formProfil.style.display = 'block';
                if (btnApply) btnApply.onclick = () => applyManualCorrection();
                break;

            case 'formulaire_profil_simple':
                // Profil simple: formulaire profondeur sans graphique
                if (formProfil) formProfil.style.display = 'block';
                if (btnApply) btnApply.onclick = () => applyManualCorrection();
                break;

            default:
                // Défaut: formulaire profil complet
                if (profile) profile.style.display = 'block';
                if (formProfil) formProfil.style.display = 'block';
                if (btnApply) btnApply.onclick = () => applyManualCorrection();
        }

        // Mapper les IDs pour les formulaires profil
        if (formProfil) {
            // Déplacer les valeurs vers les nouveaux IDs
            const am = document.getElementById('correction-amont');
            const av = document.getElementById('correction-aval');
            const amProf = document.getElementById('correction-amont-profil');
            const avProf = document.getElementById('correction-aval-profil');
            if (amProf && avProf) {
                amProf.value = am ? am.value : '';
                avProf.value = av ? av.value : '';
            }
        }

        const modal = document.getElementById('correction-modal');
        if (modal) modal.style.display = 'flex';

        const am = document.getElementById('correction-amont'); 
        const av = document.getElementById('correction-aval');
        if (am) am.value = ''; 
        if (av) av.value = '';

        // Try to fetch profile with candidate fid first
        function tryProfile(fidToTry) {
            return fetch(`/api/v1/corrections/profile/${encodeURIComponent(fidToTry)}`)
                .then(res => {
                    if (!res.ok) throw new Error('Not found');
                    return res.json();
                });
        }

        // Charger les données appropriées selon le type de solution
        if (currentCorrectionFid && (solutionConfig.solution === 'formulaire_profil_with_profile' || solutionConfig.solution === 'formulaire_profil_simple')) {
            // Pour les problèmes de profil: charger le profil et la suggestion
            tryProfile(currentCorrectionFid).then(data => {
                // Tracer le profil réel automatiquement
                if (typeof drawCurrentProfile === 'function') {
                    setTimeout(() => drawCurrentProfile(), 100);
                }
                if (typeof fetchHybridSuggestion === 'function') {
                    fetchHybridSuggestion(currentCorrectionFid, type);
                }
            }).catch(err => {
                // Profil non trouvé - afficher un message
                const content = document.getElementById('hybrid-suggestion-content');
                if (content) content.textContent = 'Données topographiques non disponibles. Veuillez saisir les profondeurs manuellement.';
                const box2 = document.getElementById('hybrid-suggestion-box'); 
                if (box2) box2.style.display = 'block';
            });
        } else if (currentCorrectionFid && (solutionConfig.solution === 'formulaire_connexion_with_suggestion')) {
            // Pour les problèmes de connexion: charger la suggestion de connexion
            if (typeof fetchHybridSuggestion === 'function') {
                fetchHybridSuggestion(currentCorrectionFid, type);
            }
        }
        // Pour formulaire_coords: pas de chargement spécifique requis

    } catch (e) { console.warn('openCorrectionModal error', e); }
}

function closeCorrectionModal() {
    const modal = document.getElementById('correction-modal');
    if (modal) modal.style.display = 'none';
}

// Stub functions for modal correction flow
function fetchHybridSuggestion(id, type) {
    const box = document.getElementById('hybrid-suggestion-box');
    const content = document.getElementById('hybrid-suggestion-content');
    if (!box || !content) return;
    box.style.display = 'block';
    content.textContent = 'Analyse en cours...';

    currentCorrectionFid = id;
    currentSuggestionPayload = null;

    // Messages adapté selon le type de diagnostic
    const typeMessages = {
        'pente_negative': 'Solution : inverser ou augmenter les profondeurs pour obtenir une pente positive',
        'pente_trop_forte': 'Solution : réduire la différence de profondeur ou augmenter la longueur pour diminuer la pente',
        'incoherence_profondeur': 'Solution : harmoniser les profondeurs des nœuds amont et aval',
        'incoherences_amont_aval': 'Solution : vérifier et corriger les connexions amont/aval',
        'conduite_sans_regard': 'Solution : connecter cette conduite à un nœud (regard/station/ouvrage) amont et aval',
        'troncon_orphelin': 'Solution : intégrer ce tronçon orphelin au réseau en créant les connexions'
    };

    // Call backend suggestion endpoint
    fetch(`/api/v1/corrections/hybride/suggest?fid=${encodeURIComponent(id)}&anomalie_type=${encodeURIComponent(type || '')}`)
        .then(res => res.json())
        .then(data => {
            currentSuggestionPayload = data;
            if (!data || !data.suggestion) {
                content.textContent = typeMessages[type] || 'Veuillez saisir manuellement la correction appropriée.';
                return;
            }

            const s = data.suggestion;
            const typeMsg = typeMessages[type] || 'Solution hydraulique proposée';
            
            // Build detailed suggestion display with metrics
            const cappedNote = (s.capped) ? '<div style="color:#b36b00;font-size:12px;margin-top:6px;">⚠️ Proposition limitée par contraintes hydrauliques (cappée). Vérifier avant application.</div>' : '';
            
            // Adapter le contenu selon le type
            let solutionDisplay = '';
            if (type && (type.includes('pente') || type.includes('profondeur') || type.includes('coherence'))) {
                // Pour les problèmes de profil/pente
                solutionDisplay = `
                    <div style="font-size:13px;color:#2c5aa0;"><strong>💧 Solution hydraulique :</strong></div>
                    <div style="font-size:12px;margin-top:4px;">${typeMsg}</div>
                    <div style="margin-top:8px;font-size:12px;background:#e8f4f8;padding:6px;border-radius:4px;">
                        <strong>Profondeur amont proposée :</strong> ${s.prof_fe_am ? s.prof_fe_am + ' m' : '—'} <br>
                        <strong>Profondeur aval proposée :</strong> ${s.prof_fe_av ? s.prof_fe_av + ' m' : '—'} <br>
                        <strong>Pente résultante :</strong> ${s.pente_pourcent ? s.pente_pourcent.toFixed(2) + ' %' : '—'}
                    </div>
                    <div style="margin-top:6px;font-size:11px;color:#666">Confiance: ${s.confidence || 'indisponible'} — Sources: ${data.suggestion.source_count || 0}</div>
                    ${cappedNote}
                `;
            } else if (type && type.includes('conduite_sans_regard')) {
                // Pour connexion manquante
                solutionDisplay = `
                    <div style="font-size:13px;color:#2c5aa0;"><strong>🔗 Solution de connexion :</strong></div>
                    <div style="font-size:12px;margin-top:4px;">${typeMsg}</div>
                    <div style="margin-top:8px;font-size:12px;background:#e8f4f8;padding:6px;border-radius:4px;">
                        <strong>Nœud amont suggéré :</strong> ${s.noeud_amont || '—'} <br>
                        <strong>Nœud aval suggéré :</strong> ${s.noeud_aval || '—'} <br>
                        <strong>Type de nœud :</strong> ${s.type_noeud || 'regard'}
                    </div>
                    <div style="margin-top:6px;font-size:11px;color:#666">Confiance: ${s.confidence || 'indisponible'}</div>
                `;
            } else {
                // Affichage par défaut
                solutionDisplay = `
                    <div style="font-size:13px;">${s.message || 'Proposition'}</div>
                    <div style="margin-top:6px;font-size:13px;"><strong>Pente proposée:</strong> ${s.pente_pourcent ? s.pente_pourcent + ' %' : '—'}</div>
                    <div style="margin-top:4px;font-size:13px;"><strong>Amont / Aval proposés:</strong> ${s.prof_fe_am || '—'} / ${s.prof_fe_av || '—'}</div>
                    <div style="margin-top:6px;font-size:12px;color:#666">Confiance: ${s.confidence || 'indisponible'} — Sources: ${data.suggestion.source_count || 0}</div>
                    ${cappedNote}
                `;
            }

            content.innerHTML = solutionDisplay;

            // Fill inputs if suggestion available
            if (s.available) {
                const am = document.getElementById('correction-amont-profil');
                const av = document.getElementById('correction-aval-profil');
                if (am && av) {
                    if (s.prof_fe_am) am.value = s.prof_fe_am;
                    if (s.prof_fe_av) av.value = s.prof_fe_av;
                }
            }

            // Tracer automatiquement le profil (réel + proposé) quand la suggestion est chargée
            if (typeof drawCurrentProfile === 'function') {
                setTimeout(() => drawCurrentProfile(), 200);
            }
        })
        .catch(e => {
            console.warn('fetchHybridSuggestion error', e);
            content.textContent = typeMessages[type] || 'Veuillez saisir manuellement la correction appropriée.';
        });
}
