/**
 * ================================================================================
 * Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
 * Auteur : Dr Abdelhakim KELLOUCHE
 * Objet : Module de dialogues modaux (confirmation / information / alerte)
 *        remplaçant les boîtes natives alert() et confirm() du navigateur.
 *
 * API :
 *   window.dialogueConfirmer({ titre, message, type, libelleValider, libelleIgnorer })
 *       -> Promise<boolean>  (true = Valider, false = Ignorer/Fermer/Échap)
 *   window.dialogueNotifier({ titre, message, type })
 *       -> Promise<void>     (information, un seul bouton Fermer)
 *   window.dialogueAlerte(message, type)
 *       -> Promise<void>     (raccourci pour les anciens alert())
 *
 * Types : 'info' | 'confirmation' | 'danger' | 'succes' | 'erreur'
 * ================================================================================
 */
(function () {
    'use strict';

    const _TYPES = {
        info:         { icon: 'fa-info-circle',    color: '#38bdf8', bg: 'rgba(56,189,248,0.14)',  bordure: 'rgba(56,189,248,0.45)',  defaut: 'Information' },
        confirmation: { icon: 'fa-question-circle', color: '#fbbf24', bg: 'rgba(251,191,36,0.14)',  bordure: 'rgba(251,191,36,0.45)',  defaut: 'Confirmation' },
        danger:       { icon: 'fa-exclamation-triangle', color: '#f87171', bg: 'rgba(248,113,113,0.14)', bordure: 'rgba(248,113,113,0.45)', defaut: 'Suppression' },
        succes:       { icon: 'fa-check-circle',   color: '#34d399', bg: 'rgba(52,211,153,0.14)',  bordure: 'rgba(52,211,153,0.45)',  defaut: 'Succès' },
        erreur:       { icon: 'fa-times-circle',   color: '#f87171', bg: 'rgba(248,113,113,0.14)', bordure: 'rgba(248,113,113,0.45)',  defaut: 'Erreur' },
    };
    // Alias usuels
    _TYPES.avertissement = _TYPES.confirmation;
    _TYPES.warning = _TYPES.confirmation;
    _TYPES.suppression = _TYPES.danger;
    _TYPES.success = _TYPES.succes;
    _TYPES.error = _TYPES.erreur;

    let _modal = null;
    let _resolveActif = null;
    let _nettoyerEvenements = null;

    function _construireModal() {
        if (_modal) return _modal;
        _modal = document.createElement('div');
        _modal.id = 'modal-dialogue-app';
        _modal.style.cssText = 'display:none;position:fixed;inset:0;background:rgba(2,6,23,0.72);backdrop-filter:blur(5px);z-index:4000;align-items:center;justify-content:center;';
        _modal.innerHTML = `
            <div class="dlg-carte" role="dialog" aria-modal="true" style="background:#1e293b;border:1px solid rgba(255,255,255,0.16);border-radius:14px;width:92%;max-width:460px;box-shadow:0 25px 60px rgba(0,0,0,0.65);overflow:hidden;">
                <div class="dlg-entete" style="display:flex;align-items:center;gap:12px;padding:14px 18px;border-bottom:1px solid rgba(255,255,255,0.1);">
                    <div class="dlg-icone" style="width:38px;height:38px;border-radius:10px;display:flex;align-items:center;justify-content:center;font-size:17px;flex-shrink:0;"><i class="fas fa-info-circle"></i></div>
                    <div class="dlg-titre" style="flex:1;font-weight:800;font-size:0.95rem;color:#f8fafc;"></div>
                    <button type="button" class="dlg-fermer" title="Fermer" style="background:transparent;border:none;color:#94a3b8;font-size:20px;cursor:pointer;line-height:1;padding:2px 6px;">&times;</button>
                </div>
                <div class="dlg-message" style="padding:18px;font-size:0.86rem;color:#cbd5e1;line-height:1.55;max-height:50vh;overflow-y:auto;white-space:pre-line;"></div>
                <div class="dlg-pied" style="display:flex;justify-content:flex-end;gap:10px;padding:12px 18px;border-top:1px solid rgba(255,255,255,0.1);background:rgba(15,23,42,0.5);"></div>
            </div>`;
        document.body.appendChild(_modal);

        _modal.addEventListener('click', (e) => {
            if (e.target === _modal) _clore(false);
        });
        _modal.querySelector('.dlg-fermer').addEventListener('click', () => _clore(false));
        _modal.querySelector('.dlg-carte').addEventListener('click', (e) => e.stopPropagation());
        return _modal;
    }

    function _clore(valeur) {
        if (!_resolveActif) return;
        const res = _resolveActif;
        _resolveActif = null;
        if (_nettoyerEvenements) { _nettoyerEvenements(); _nettoyerEvenements = null; }
        if (_modal) _modal.style.display = 'none';
        res(valeur);
    }

    /**
     * Dialogue de confirmation : deux boutons « Valider » / « Ignorer ».
     * opts: { titre, message, type, libelleValider, libelleIgnorer }
     * Retourne Promise<boolean>.
     */
    window.dialogueConfirmer = function (opts) {
        opts = opts || {};
        const type = _TYPES[opts.type] || _TYPES.confirmation;
        const modal = _construireModal();

        modal.querySelector('.dlg-icone').className = 'dlg-icone fas ' + type.icon;
        modal.querySelector('.dlg-icone').style.cssText = `width:38px;height:38px;border-radius:10px;display:flex;align-items:center;justify-content:center;font-size:17px;flex-shrink:0;background:${type.bg};color:${type.color};border:1px solid ${type.bordure};`;
        modal.querySelector('.dlg-titre').textContent = opts.titre || type.defaut;
        modal.querySelector('.dlg-message').textContent = opts.message || '';

        const pied = modal.querySelector('.dlg-pied');
        pied.innerHTML = '';
        // libelleIgnorer === null → notification simple : pas de bouton Ignorer
        if (opts.libelleIgnorer !== null) {
            const btnIgnorer = document.createElement('button');
            btnIgnorer.type = 'button';
            btnIgnorer.textContent = opts.libelleIgnorer || 'Ignorer';
            btnIgnorer.style.cssText = 'padding:7px 18px;background:rgba(255,255,255,0.07);border:1px solid rgba(255,255,255,0.18);color:#e2e8f0;border-radius:8px;font-size:0.82rem;font-weight:600;cursor:pointer;';
            btnIgnorer.addEventListener('click', () => _clore(false));
            pied.appendChild(btnIgnorer);
        }

        const btnValider = document.createElement('button');
        btnValider.type = 'button';
        btnValider.textContent = opts.libelleValider || 'Valider';
        const couleurVal = opts.type === 'danger' || opts.type === 'suppression' || opts.type === 'erreur'
            ? 'linear-gradient(135deg,#dc2626,#b91c1c)'
            : 'linear-gradient(135deg,#0284c7,#0369a1)';
        btnValider.style.cssText = `padding:7px 18px;background:${couleurVal};border:none;color:#fff;border-radius:8px;font-size:0.82rem;font-weight:700;cursor:pointer;`;
        btnValider.addEventListener('click', () => _clore(true));

        pied.appendChild(btnValider);

        modal.style.display = 'flex';
        return new Promise((resolve) => {
            _resolveActif = resolve;
            const surTouche = (e) => {
                if (e.key === 'Escape') { e.preventDefault(); _clore(false); }
                else if (e.key === 'Enter') { e.preventDefault(); _clore(true); }
            };
            document.addEventListener('keydown', surTouche, true);
            _nettoyerEvenements = () => document.removeEventListener('keydown', surTouche, true);
            setTimeout(() => btnValider.focus(), 30);
        });
    };

    /**
     * Notification simple (un bouton « Fermer ») : information, succès, erreur.
     * opts: { titre, message, type }
     */
    window.dialogueNotifier = function (opts) {
        opts = opts || {};
        const type = _TYPES[opts.type] || _TYPES.info;
        return window.dialogueConfirmer({
            titre: opts.titre || type.defaut,
            message: opts.message || '',
            type: opts.type || 'info',
            libelleValider: 'Fermer',
            libelleIgnorer: null,
        }).then(() => undefined);
    };

    /**
     * Raccourci pour remplacer les anciens alert(message) :
     * dialogueAlerte(message) ou dialogueAlerte(message, 'erreur').
     */
    window.dialogueAlerte = function (message, type) {
        return window.dialogueNotifier({ message: String(message || ''), type: type || 'info' });
    };
})();
