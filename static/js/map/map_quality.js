(() => {
    const state = window.mapState;

    function initQuality() {
        lancerAnalyseQualite();
    }

    async function lancerAnalyseQualite() {
        try {
            const response = await fetch('/api/v1/qualite/analyse');
            if (!response.ok) throw new Error(`HTTP ${response.status}`);
            const rapport = await response.json();
            console.log('[Qualité] Analyse lancée automatiquement', rapport);

            const scores = rapport.scores_qualite || {};
            const global = scores.global || {};

            if (global.score_qualite !== undefined) {
                const scoreEl = document.getElementById('quality-score');
                const container = document.getElementById('quality-score-container');
                const breakdown = document.getElementById('quality-breakdown');

                if (scoreEl) scoreEl.textContent = global.score_qualite.toFixed(1) + '%';
                if (container) container.style.display = 'block';

                if (breakdown) {
                    breakdown.innerHTML = qualityBreakdown(rapport.anomalies || {}) + '<hr style="margin: 8px 0; border-color: rgba(255,255,255,0.2);">';
                }
            }

            window.mostrerChargement(false);
        } catch (error) {
            console.error('[Qualité] Erreur analyse auto:', error);
            window.mostrerChargement(false);
        }
    }

    function qualityBreakdown(anomalies) {
        const icons = {
            pente_negative: 'fas fa-exclamation-triangle',
            pente_trop_forte: 'fas fa-angle-double-up',
            conduites_sans_regards: 'fas fa-link',
            troncons_orphelins: 'fas fa-cut',
            champs_manquants: 'fas fa-asterisk',
            geometries_invalides: 'fas fa-map-marker-alt'
        };
        const colors = {
            pente_negative: '#e74c3c',
            pente_trop_forte: '#e67e22',
            conduites_sans_regards: '#3498db',
            troncons_orphelins: '#9b59b6',
            champs_manquants: '#f1c40f',
            geometries_invalides: '#e74c3c'
        };

        return Object.entries(anomalies).map(([type, items]) => {
            const count = Array.isArray(items) ? items.length : 0;
            return `<div style="margin: 4px 0;"><i class="${icons[type] || 'fas fa-circle'}" style="color: ${colors[type] || '#fff'}; width: 16px;"></i> ${type}: <b>${count}</b></div>`;
        }).join('');
    }

    window.initQuality = initQuality;
    window.lancerAnalyseQualite = lancerAnalyseQualite;
})();
