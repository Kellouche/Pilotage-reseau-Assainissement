/**
 * ================================================================================
 * Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
 * Auteur : Dr Abdelhakim KELLOUCHE
 * Date de création : 2026-04-20
 * Date de modification : 2026-11-08
 * Objet : Démarrage et initialisation de l'application cockpit au chargement DOM
 * ================================================================================
 */

// ==========================================
        // INITIALISATION ET DÉMARRAGE DU COCKPIT
        // ==========================================
        function initialiserCockpit() {
            // 1. Initialiser le profil utilisateur et la barre SaaS
            if (typeof initSaaSNavbar === 'function') {
                initSaaSNavbar();
            }

            // 2. Gestion du choix de projet ou chargement direct sur F5
            const urlParams = new URLSearchParams(window.location.search);
            const flagChoix = sessionStorage.getItem('choisir_projet_apres_login') === 'true' ||
                              sessionStorage.getItem('projet_charge') !== 'true' ||
                              urlParams.get('choix') === '1';

            if (flagChoix) {
                sessionStorage.removeItem('choisir_projet_apres_login');
                if (typeof montrerModalProjet === 'function') {
                    montrerModalProjet(true);
                }
                const miniStats = document.getElementById('mini-stats');
                if (miniStats) {
                    miniStats.innerHTML = '<span style="color: #38bdf8;"><i class="fas fa-folder-open me-1"></i> Choisissez un projet ou modèle certifié</span>';
                }
                montrerChargement(false);
            } else {
                // Rechargement direct (F5 lors d'une session de travail active)
                if (typeof chargerDonneesInitiales === 'function') {
                    chargerDonneesInitiales();
                }
            }
        }

        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', initialiserCockpit);
        } else {
            initialiserCockpit();
        }
