/**
 * ================================================================================
 * Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
 * Auteur : Dr Abdelhakim KELLOUCHE
 * Date de création : 2026-04-20
 * Date de modification : 2026-11-27
 * Objet : Diagnostic asynchrone du réseau (progression, annulation)
 * ================================================================================
 */

let diagnosticsLoaded = false;
let abortController = null;
let diagnosticInterval = null;
let diagnosticStartTime = 0;

function lancerDiagnostic(targetTab) {
    console.log("Démarrage du diagnostic pour :", targetTab);

    // Afficher la modale bloquante
    const modal = document.getElementById('diagnostic-modal');
    if (modal) modal.style.display = 'flex';

    const progressBar = document.getElementById('diagnostic-progress-bar');
    const percentText = document.getElementById('diagnostic-percent');
    const chronoText = document.getElementById('diagnostic-chrono');
    const statusMsg = document.getElementById('diagnostic-status-msg');

    if (progressBar) progressBar.style.width = '0%';
    if (percentText) percentText.textContent = '0%';
    if (chronoText) chronoText.textContent = 'Temps écoulé : 0.0s';
    if (statusMsg) statusMsg.textContent = "Initialisation de l'analyse...";

    // Annuler tout diagnostic précédent
    if (diagnosticInterval) clearInterval(diagnosticInterval);
    if (abortController) abortController.abort();

    abortController = new AbortController();
    diagnosticStartTime = Date.now();

    // Lancer le timer pour animer la barre de progression et le chrono
    diagnosticInterval = setInterval(() => {
        const elapsedMs = Date.now() - diagnosticStartTime;
        const elapsedSec = (elapsedMs / 1000).toFixed(1);
        if (chronoText) chronoText.textContent = `Temps écoulé : ${elapsedSec}s`;

        // Progression simulée asymptotique (0% -> 95%)
        let progress = 0;
        if (elapsedMs < 2000) {
            progress = (elapsedMs / 2000) * 40; // 0% à 40% en 2s
        } else if (elapsedMs < 5000) {
            progress = 40 + ((elapsedMs - 2000) / 3000) * 35; // 40% à 75% en 3s
        } else {
            progress = 75 + (1 - Math.exp(-(elapsedMs - 5000) / 10000)) * 20; // asymptotique vers 95%
        }

        const progressInt = Math.min(95, Math.floor(progress));
        if (progressBar) progressBar.style.width = progressInt + '%';
        if (percentText) percentText.textContent = progressInt + '%';

        // Messages de statut dynamiques basés sur le temps écoulé
        let msg = "Initialisation de l'analyse...";
        if (elapsedMs > 12000) {
            msg = "Finalisation et calcul des scores...";
        } else if (elapsedMs > 8000) {
            msg = "Calcul de la topologie du graphe...";
        } else if (elapsedMs > 5000) {
            msg = "Vérification des anomalies de pente...";
        } else if (elapsedMs > 3000) {
            msg = "Analyse des connexions amont/aval...";
        } else if (elapsedMs > 1500) {
            msg = "Chargement du modèle de réseau...";
        }
        if (statusMsg) statusMsg.textContent = msg;
    }, 100);

    // Inventaire des éléments orphelins (regards isolés + tronçons hors
    // graphe/sans exutoire) — fetché en parallèle du diagnostic qualité.
    const _promesseOrphelins = fetch(`${API_BASE_URL}/api/v1/network/orphelins`, { signal: abortController.signal })
        .then(r => (r && r.ok) ? r.json() : null)
        .catch(() => null);

    // Lancer la requête API réelle
    fetch(`${API_BASE_URL}/api/v1/qualite/analyse`, { signal: abortController.signal })
        .then(async (response) => {
            if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
            return response.json();
        })
        .then(async (anomData) => {
            const _orphelins = await _promesseOrphelins;
            if (_orphelins && typeof fusionnerOrphelins === 'function') {
                try { fusionnerOrphelins(anomData, _orphelins); }
                catch (e) { console.warn('Fusion orphelins impossible:', e); }
            }
            console.log("Diagnostic calculé avec succès", anomData);

            // Stopper le chrono
            clearInterval(diagnosticInterval);
            diagnosticInterval = null;

            // Afficher 100% de progression
            if (progressBar) progressBar.style.width = '100%';
            if (percentText) percentText.textContent = '100%';
            if (statusMsg) statusMsg.textContent = "Calcul terminé !";

            // Fermer la modale après un court délai pour que l'utilisateur voie les 100%
            setTimeout(() => {
                if (modal) modal.style.display = 'none';
            }, 500);
            showNotification('Diagnostic terminé !', 'success');

            // Traitement différé : laisser le navigateur respirer entre chaque étape
            // pour éviter de geler l'interface pendant le traitement de 3 Mo de données
            const steps = [];

            // Étape 1 : intégrer les anomalies dans la carte
            steps.push(() => {
                if (typeof buildAnomaliesMaps === 'function') buildAnomaliesMaps(anomData);
                if (typeof updateAnomaliesLayers === 'function') updateAnomaliesLayers();
            });

            // Étape 2 : peupler les listes d'anomalies (async pour pré-charger les suggestions)
            steps.push(async () => {
                try {
                    if (typeof populateAnomaliesLists === 'function') await populateAnomaliesLists(anomData.anomalies || anomData);
                } catch (e) {
                    console.warn('populateAnomaliesLists fallback failed', e);
                }
                try {
                    if (typeof rendreListeOrphelins === 'function') rendreListeOrphelins();
                } catch (e) {
                    console.warn('rendreListeOrphelins failed', e);
                }
            });

            // Étape 3 : mettre à jour les compteurs de tous les onglets
            steps.push(() => {
                Object.keys(tabMappings).forEach(tab => {
                    if (typeof calculateTabStats === 'function') calculateTabStats(tab);
                });
            });

            // Étape 4 : mettre à jour les scores
            steps.push(() => {
                if (typeof updateStats === 'function') updateStats();
            });

            // Étape 5 : finaliser
            steps.push(() => {
                diagnosticsLoaded = true;
                document.querySelectorAll('.tab-btn').forEach(btn => {
                    btn.classList.remove('pending');
                });
                if (typeof switchTabReal === 'function') {
                    switchTabReal(targetTab);
                }
            });

            // Exécuter chaque étape en cédant la main au navigateur entre chaque
            // Gère aussi les étapes async (ex: populateAnomaliesLists avec pré-chargement suggestions)
            async function runStep(index) {
                if (index >= steps.length) return;
                // requestAnimationFrame garantit que le DOM est rendu avant de toucher les éléments
                requestAnimationFrame(async () => {
                    try {
                        await steps[index]();
                    } catch (e) {
                        console.error(`Erreur étape traitement ${index}:`, e);
                    }
                    runStep(index + 1);
                });
            }

            runStep(0);
        })
        .catch((error) => {
            if (error.name === 'AbortError') {
                console.log("Opération annulée par l'utilisateur.");
                return; // Géré par annulerDiagnostic()
            }
            console.error("Erreur lors de l'analyse :", error);

            clearInterval(diagnosticInterval);
            diagnosticInterval = null;

            if (modal) modal.style.display = 'none';
            showNotification(`Erreur d'analyse: ${error.message}`, 'error');
        });
}

function annulerDiagnostic() {
    console.log("Annulation du diagnostic...");

    if (abortController) {
        abortController.abort();
        abortController = null;
    }

    if (diagnosticInterval) {
        clearInterval(diagnosticInterval);
        diagnosticInterval = null;
    }

    const modal = document.getElementById('diagnostic-modal');
    if (modal) modal.style.display = 'none';

    showNotification("Opération annulée par l'utilisateur.", 'warning');
}
