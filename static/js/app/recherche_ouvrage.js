/**
 * ============================================================================
 * DrainPilot 5.2 — Recherche rapide d'un regard ou d'un tronçon par numéro
 * Palette flottante (bouton 🔍 de la toolbar ou Ctrl+K) : résultats issues
 * de GET /api/v1/simulations/recherche-element — lecture seule.
 * ============================================================================
 */
(function () {
    'use strict';

    let _timer = null;
    let _seq = 0;
    let _pulseLayer = null;

    function _injecterStylePulse() {
        if (document.getElementById('style-pulse-regard')) return;
        const st = document.createElement('style');
        st.id = 'style-pulse-regard';
        st.textContent = `
            .pulse-regard-wrap { position: relative; width: 34px; height: 34px; }
            .pulse-regard-core {
                position: absolute; left: 50%; top: 50%; width: 14px; height: 14px;
                transform: translate(-50%, -50%);
                background: #f59e0b; border: 2.5px solid #fff; border-radius: 50%;
                box-shadow: 0 0 10px rgba(245,158,11,0.9); z-index: 2;
            }
            .pulse-regard-ring {
                position: absolute; left: 50%; top: 50%; width: 34px; height: 34px;
                transform: translate(-50%, -50%); border-radius: 50%;
                border: 3px solid #f59e0b; opacity: 0.9; z-index: 1;
                animation: pulseRing 1.1s ease-out infinite;
            }
            @keyframes pulseRing {
                0%   { transform: translate(-50%,-50%) scale(0.35); opacity: 0.95; }
                100% { transform: translate(-50%,-50%) scale(1.15); opacity: 0; }
            }
            .pulse-regard-wrap.fade-out { transition: opacity 0.6s; opacity: 0; }
            .pulse-regard-label {
                background: rgba(15,23,42,0.95); color: #fbbf24;
                border: 1px solid rgba(245,158,11,0.55); font-weight: 700;
                font-size: 11px; padding: 2px 8px; border-radius: 6px;
                box-shadow: 0 2px 8px rgba(0,0,0,0.45); white-space: nowrap;
            }
            .pulse-regard-label::before { display: none; }
        `;
        document.head.appendChild(st);
    }

    // Marqueur pulsatile temporaire (~6 s) pour identifier l'ouvrage
    // trouvé parmi les autres regards de la carte.
    function _surlignerOuvrage(lng, lat, label) {
        const carte = _carte();
        if (!carte || typeof L === 'undefined' || lng == null || lat == null) return;
        _injecterStylePulse();
        if (_pulseLayer) {
            try { carte.removeLayer(_pulseLayer); } catch (e) { /* noop */ }
            _pulseLayer = null;
        }
        const icon = L.divIcon({
            className: 'pulse-regard-icon',
            html: '<div class="pulse-regard-wrap"><div class="pulse-regard-ring"></div><div class="pulse-regard-core"></div></div>',
            iconSize: [34, 34],
            iconAnchor: [17, 17],
        });
        _pulseLayer = L.marker([lat, lng], { icon: icon, zIndexOffset: 1000 }).addTo(carte);
        if (label) {
            _pulseLayer.bindTooltip(String(label), {
                permanent: true, direction: 'top', offset: [0, -20],
                className: 'pulse-regard-label'
            });
        }
        setTimeout(() => {
            if (_pulseLayer) {
                const el = _pulseLayer.getElement && _pulseLayer.getElement();
                if (el) el.classList.add('fade-out');
                setTimeout(() => {
                    try { if (_pulseLayer) carte.removeLayer(_pulseLayer); } catch (e) { /* noop */ }
                    _pulseLayer = null;
                }, 700);
            }
        }, 6000);
    }

    function _palette() { return document.getElementById('palette-recherche-ouvrage'); }
    function _input() { return document.getElementById('input-recherche-ouvrage'); }
    function _box() { return document.getElementById('resultats-recherche-ouvrage'); }
    function _carte() {
        return (typeof window.carte !== 'undefined' && window.carte)
            || (typeof window.map !== 'undefined' && window.map)
            || (typeof carte !== 'undefined' ? carte : null);
    }

    window.basculerPaletteRecherche = function () {
        const p = _palette();
        if (!p) return;
        const ouvrir = p.style.display === 'none';
        p.style.display = ouvrir ? 'block' : 'none';
        if (ouvrir) {
            const inp = _input();
            if (inp) { inp.value = ''; setTimeout(() => inp.focus(), 30); }
            const b = _box();
            if (b) { b.innerHTML = '<div style="padding:10px 14px;color:#64748b;font-size:0.75rem;">Tapez un numéro de regard ou de tronçon…</div>'; }
        }
    };

    window.fermerPaletteRecherche = function () {
        const p = _palette();
        if (p) p.style.display = 'none';
    };

    function centrerCarte(lng, lat, label) {
        const carte = _carte();
        if (carte && lng != null && lat != null && typeof carte.setView === 'function') {
            try { carte.setView([lat, lng], 18); } catch (e) { /* noop */ }
        }
        _surlignerOuvrage(lng, lat, label);
    }

    function _ouvrirPanneauProfil() {
        const panel = document.getElementById('panel-profil-long');
        if (panel && panel.style.display === 'none') {
            panel.style.display = 'flex';
            if (typeof _centrerPanelProfil === 'function') _centrerPanelProfil();
        }
    }

    function _remplirRegardProfil(code, role) {
        const inpA = document.getElementById('input-profil-amont');
        const inpB = document.getElementById('input-profil-aval');
        if (role === 'amont') {
            if (inpA) inpA.value = code;
            if (typeof synchroniserInputProfilAmont === 'function') synchroniserInputProfilAmont(code);
        } else {
            if (inpB) inpB.value = code;
            if (typeof synchroniserInputProfilAval === 'function') synchroniserInputProfilAval(code);
        }
    }

    window._rechercheChoisirRegard = function (it, role) {
        window.fermerPaletteRecherche();
        centrerCarte(it.lng, it.lat, it.libelle);
        _remplirRegardProfil(it.id, role);
        _ouvrirPanneauProfil();
        // Si les deux regards sont connus, lancer le profil directement
        const a = (document.getElementById('input-profil-amont') || {}).value || '';
        const b = (document.getElementById('input-profil-aval') || {}).value || '';
        if (a.trim() && b.trim() && typeof rafraichirProfilLong === 'function') {
            rafraichirProfilLong();
        }
    };

    window._rechercheProfilTroncon = function (it) {
        window.fermerPaletteRecherche();
        centrerCarte(it.lng, it.lat, it.libelle);
        _remplirRegardProfil(it.amont, 'amont');
        _remplirRegardProfil(it.aval, 'aval');
        _ouvrirPanneauProfil();
        if (typeof rafraichirProfilLong === 'function') rafraichirProfilLong();
    };

    window.rechercherOuvrage = function (q) {
        const box = _box();
        if (!box) return;
        const requete = (q || '').trim();
        if (requete.length < 2) {
            box.innerHTML = '<div style="padding:10px 14px;color:#64748b;font-size:0.75rem;">Tapez au moins 2 caractères…</div>';
            return;
        }
        clearTimeout(_timer);
        _timer = setTimeout(() => _executer(requete), 300);
    };

    function _esc(s) {
        return String(s == null ? '' : s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
    }

    function _executer(requete) {
        const seq = ++_seq;
        const box = _box();
        if (!box) return;
        fetch(`/api/v1/simulations/recherche-element?q=${encodeURIComponent(requete)}`)
            .then(r => r.ok ? r.json() : Promise.reject(new Error('HTTP ' + r.status)))
            .then(data => {
                if (seq !== _seq) return;
                const res = (data && data.resultats) || [];
                if (!res.length) {
                    box.innerHTML = '<div style="padding:10px 14px;color:#94a3b8;font-size:0.78rem;">Aucun regard ou tronçon trouvé pour « ' + requete.replace(/</g, '&lt;') + ' ».</div>';
                    return;
                }
                box.innerHTML = res.map((it, i) => {
                    const icon = it.type === 'troncon' ? 'fa-arrows-alt-h' : 'fa-map-marker-alt';
                    const color = it.type === 'troncon' ? '#38bdf8' : '#34d399';
                    const actions = it.type === 'troncon'
                        ? `<button class="btn-recherche-action" onclick="_rechercheProfilTroncon(${JSON.stringify(it).replace(/"/g, '&quot;')})" style="background:rgba(56,189,248,0.18);border:1px solid rgba(56,189,248,0.4);color:#38bdf8;border-radius:6px;padding:3px 10px;font-size:0.7rem;font-weight:700;cursor:pointer;">Profil</button>`
                        : `<button class="btn-recherche-action" onclick="_rechercheChoisirRegard(${JSON.stringify(it).replace(/"/g, '&quot;')},'amont')" style="background:rgba(52,211,153,0.15);border:1px solid rgba(52,211,153,0.4);color:#34d399;border-radius:6px;padding:3px 9px;font-size:0.7rem;font-weight:700;cursor:pointer;">Amont</button>
                           <button class="btn-recherche-action" onclick="_rechercheChoisirRegard(${JSON.stringify(it).replace(/"/g, '&quot;')},'aval')" style="background:rgba(56,189,248,0.15);border:1px solid rgba(56,189,248,0.4);color:#38bdf8;border-radius:6px;padding:3px 9px;font-size:0.7rem;font-weight:700;cursor:pointer;">Aval</button>`;
                    return `<div class="resultat-recherche-ouvrage" data-idx="${i}" style="display:flex;align-items:center;gap:8px;padding:8px 14px;cursor:pointer;" onmouseenter="this.style.background='rgba(56,189,248,0.1)'" onmouseleave="this.style.background='transparent'">
                        <i class="fas ${icon}" style="color:${color};width:16px;text-align:center;font-size:0.75rem;"></i>
                        <div style="flex:1;min-width:0;">
                            <div style="color:#e2e8f0;font-weight:600;font-size:0.8rem;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">${_esc(it.libelle)}</div>
                            ${it.sous_titre ? `<div style="color:#64748b;font-size:0.68rem;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">${_esc(it.sous_titre)}</div>` : ''}
                        </div>
                        <button class="btn-recherche-action" onclick="event.stopPropagation();centrerDepuisRecherche(${JSON.stringify({lng: it.lng, lat: it.lat, libelle: it.libelle}).replace(/"/g, '&quot;')})" title="Centrer la carte" style="background:transparent;border:1px solid rgba(255,255,255,0.15);color:#94a3b8;border-radius:6px;padding:3px 8px;font-size:0.7rem;cursor:pointer;"><i class="fas fa-map-marker-alt"></i></button>
                        ${actions}
                    </div>`;
                }).join('');
                // Clic sur la ligne = action principale (tronçon → profil, regard → aval)
                box.querySelectorAll('.resultat-recherche-ouvrage').forEach(el => {
                    el.addEventListener('click', (ev) => {
                        if (ev.target.closest('.btn-recherche-action')) return;
                        const it = res[parseInt(el.dataset.idx, 10)];
                        if (it.type === 'troncon') window._rechercheProfilTroncon(it);
                        else window._rechercheChoisirRegard(it, 'aval');
                    });
                });
            })
            .catch(() => {
                if (seq !== _seq) return;
                box.innerHTML = '<div style="padding:10px 14px;color:#f87171;font-size:0.78rem;">Recherche indisponible.</div>';
            });
    }

    window.centrerDepuisRecherche = function (pos) {
        window.fermerPaletteRecherche();
        centrerCarte(pos.lng, pos.lat, pos.libelle);
    };

    // Raccourcis clavier : Ctrl+K / Échap
    document.addEventListener('keydown', (e) => {
        if ((e.ctrlKey || e.metaKey) && (e.key === 'k' || e.key === 'K')) {
            e.preventDefault();
            window.basculerPaletteRecherche();
        } else if (e.key === 'Escape') {
            window.fermerPaletteRecherche();
        }
    });

    // Clic en dehors de la palette → fermeture
    document.addEventListener('click', (e) => {
        const p = _palette();
        if (p && p.style.display !== 'none' && !p.contains(e.target)
            && e.target.id !== 'btn-recherche-ouvrage' && !e.target.closest('#btn-recherche-ouvrage')) {
            p.style.display = 'none';
        }
    });
})();
