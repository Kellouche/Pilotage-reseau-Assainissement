/**
 * ================================================================================
 * Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
 * Auteur : Dr Abdelhakim KELLOUCHE
 * Date de création : 2026-04-20
 * Date de modification : 2026-11-08
 * Objet : Gestion du profil utilisateur, sécurité, changement de mot de passe et déconnexion
 * ================================================================================
 */

window.ouvrirModalProfil = function(onglet) {
            fermerMenuProfil();
            const m = document.getElementById('modal-user-profile');
            if (m) {
                m.style.display = 'flex';
                basculerOngletProfil(onglet || 'infos');
            }
        };

        window.fermerModalProfil = function() {
            const m = document.getElementById('modal-user-profile');
            if (m) m.style.display = 'none';
            const f1 = document.getElementById('profile-info-feedback');
            if (f1) f1.style.display = 'none';
            const f2 = document.getElementById('profile-pass-feedback');
            if (f2) f2.style.display = 'none';
        };

        window.basculerOngletProfil = function(onglet) {
            const tabInfo = document.getElementById('tab-profile-info');
            const tabPass = document.getElementById('tab-profile-password');
            const btnInfo = document.getElementById('tab-btn-profile-info');
            const btnPass = document.getElementById('tab-btn-profile-pass');

            if (onglet === 'password') {
                if (tabInfo) tabInfo.style.display = 'none';
                if (tabPass) tabPass.style.display = 'block';
                if (btnInfo) { btnInfo.style.borderColor = 'transparent'; btnInfo.style.color = '#94a3b8'; }
                if (btnPass) { btnPass.style.borderColor = '#38bdf8'; btnPass.style.color = '#38bdf8'; }
            } else {
                if (tabInfo) tabInfo.style.display = 'block';
                if (tabPass) tabPass.style.display = 'none';
                if (btnInfo) { btnInfo.style.borderColor = '#38bdf8'; btnInfo.style.color = '#38bdf8'; }
                if (btnPass) { btnPass.style.borderColor = 'transparent'; btnPass.style.color = '#94a3b8'; }
            }
        };

        window.enregistrerModifProfil = async function() {
            const name = document.getElementById('profile-edit-name').value;
            const fb = document.getElementById('profile-info-feedback');
            if (!fb) return;
            fb.style.display = 'block';
            fb.style.background = 'rgba(56, 189, 248, 0.15)';
            fb.style.color = '#38bdf8';
            fb.innerHTML = '<i class="fas fa-spinner fa-spin me-1"></i> Enregistrement en cours...';

            const token = localStorage.getItem('swmm_access_token');
            const headers = { 'Content-Type': 'application/json' };
            if (token) headers['Authorization'] = `Bearer ${token}`;

            try {
                const resp = await fetch('/api/v1/auth/profile', {
                    method: 'PATCH',
                    headers,
                    credentials: 'include',
                    body: JSON.stringify({ full_name: name })
                });
                const d = await resp.json();
                if (!resp.ok) throw new Error(d.detail || 'Erreur lors de la mise à jour');
                fb.style.background = 'rgba(52, 211, 153, 0.15)';
                fb.style.color = '#34d399';
                fb.innerHTML = '<i class="fas fa-check-circle me-1"></i> Profil mis à jour avec succès !';
                
                const uNameEl = document.getElementById('nav-user-name');
                if (uNameEl) uNameEl.textContent = name;
                const dNameEl = document.getElementById('dropdown-full-name');
                if (dNameEl) dNameEl.textContent = name;
                setTimeout(() => fermerModalProfil(), 1200);
            } catch(err) {
                fb.style.background = 'rgba(239, 68, 68, 0.15)';
                fb.style.color = '#f87171';
                fb.innerHTML = `<i class="fas fa-exclamation-triangle me-1"></i> ${err.message}`;
            }
        };

        window.enregistrerNouveauMotDePasse = async function() {
            const cur = document.getElementById('pass-current').value;
            const nPass = document.getElementById('pass-new').value;
            const cPass = document.getElementById('pass-confirm').value;
            const fb = document.getElementById('profile-pass-feedback');
            if (!fb) return;
            fb.style.display = 'block';

            if (!cur) {
                fb.style.background = 'rgba(239, 68, 68, 0.15)';
                fb.style.color = '#f87171';
                fb.innerHTML = '<i class="fas fa-exclamation-triangle me-1"></i> Renseignez votre mot de passe actuel.';
                return;
            }
            if (nPass.length < 8) {
                fb.style.background = 'rgba(239, 68, 68, 0.15)';
                fb.style.color = '#f87171';
                fb.innerHTML = '<i class="fas fa-exclamation-triangle me-1"></i> Le nouveau mot de passe doit comporter au moins 8 caractères.';
                return;
            }
            if (nPass !== cPass) {
                fb.style.background = 'rgba(239, 68, 68, 0.15)';
                fb.style.color = '#f87171';
                fb.innerHTML = '<i class="fas fa-exclamation-triangle me-1"></i> Les mots de passe ne correspondent pas.';
                return;
            }

            fb.style.background = 'rgba(56, 189, 248, 0.15)';
            fb.style.color = '#38bdf8';
            fb.innerHTML = '<i class="fas fa-spinner fa-spin me-1"></i> Mise à jour du mot de passe...';

            const token = localStorage.getItem('swmm_access_token');
            const headers = { 'Content-Type': 'application/json' };
            if (token) headers['Authorization'] = `Bearer ${token}`;

            try {
                const resp = await fetch('/api/v1/auth/change-password', {
                    method: 'POST',
                    headers,
                    credentials: 'include',
                    body: JSON.stringify({ current_password: cur, new_password: nPass })
                });
                const d = await resp.json();
                if (!resp.ok) throw new Error(d.detail || 'Erreur lors de la modification');
                fb.style.background = 'rgba(52, 211, 153, 0.15)';
                fb.style.color = '#34d399';
                fb.innerHTML = '<i class="fas fa-check-circle me-1"></i> Mot de passe mis à jour avec succès !';
                document.getElementById('pass-current').value = '';
                document.getElementById('pass-new').value = '';
                document.getElementById('pass-confirm').value = '';
                setTimeout(() => fermerModalProfil(), 1500);
            } catch(err) {
                fb.style.background = 'rgba(239, 68, 68, 0.15)';
                fb.style.color = '#f87171';
                fb.innerHTML = `<i class="fas fa-exclamation-triangle me-1"></i> ${err.message}`;
            }
        };

        window.executerDeconnexion = async function() {
            try {
                await fetch('/api/v1/auth/logout', { method: 'POST', credentials: 'include' });
            } catch(e) {}
            localStorage.removeItem('swmm_access_token');
            localStorage.removeItem('swmm_refresh_token');
            sessionStorage.removeItem('projet_charge');
            sessionStorage.removeItem('choisir_projet_apres_login');
            window.location.href = '/login';
        };

        // ==========================================
        // INITIALISATION BARRE SAAS & SESSION
        // ==========================================
        async function initSaaSNavbar() {
            const loadingEl = document.getElementById('nav-auth-loading');
            const userEl = document.getElementById('nav-auth-user');
            const guestEl = document.getElementById('nav-auth-guest');
            const orgNameEl = document.getElementById('nav-org-name');
            const userNameEl = document.getElementById('nav-user-name');
            const avatarEl = document.getElementById('nav-user-avatar');

            try {
                let token = localStorage.getItem('swmm_access_token');
                if (token && !document.cookie.includes('access_token=')) {
                    document.cookie = `access_token=${token}; path=/; max-age=604800; SameSite=Lax`;
                }
                let headers = token ? { 'Authorization': `Bearer ${token}` } : {};
                let resp = await fetch('/api/v1/auth/me', { headers, credentials: 'include' });

                // Si le jeton d'accès a expiré, tenter un rafraîchissement transparent via refresh_token
                if (!resp.ok && (resp.status === 401 || resp.status === 403)) {
                    try {
                        const rToken = localStorage.getItem('swmm_refresh_token');
                        const refResp = await fetch('/api/v1/auth/refresh', {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            credentials: 'include',
                            body: JSON.stringify(rToken ? { refresh_token: rToken } : {})
                        });
                        if (refResp.ok) {
                            const refData = await refResp.json();
                            if (refData.access_token) {
                                token = refData.access_token;
                                localStorage.setItem('swmm_access_token', token);
                                document.cookie = `access_token=${token}; path=/; max-age=604800; SameSite=Lax`;
                                headers = { 'Authorization': `Bearer ${token}` };
                                resp = await fetch('/api/v1/auth/me', { headers, credentials: 'include' });
                            }
                        }
                    } catch (eRef) {
                        console.warn('Échec renouvellement session:', eRef);
                    }
                }

                if (resp.ok) {
                    const data = await resp.json();
                    if (token) {
                        document.cookie = `access_token=${token}; path=/; max-age=604800; SameSite=Lax`;
                    }
                    if (loadingEl) loadingEl.style.display = 'none';
                    if (userEl) userEl.style.display = 'flex';
                    if (guestEl) guestEl.style.display = 'none';

                    if (orgNameEl && data.active_organization) {
                        orgNameEl.textContent = `${data.active_organization.name} [${(data.active_organization.billing_plan || 'BET').toUpperCase()}]`;
                    }
                    
                    const name = data.user.full_name || data.user.email;
                    if (userNameEl) userNameEl.textContent = name;
                    if (avatarEl) {
                        const initial = (data.user.full_name ? data.user.full_name.charAt(0) : data.user.email.charAt(0)).toUpperCase();
                        avatarEl.textContent = initial;
                    }

                    // Mettre à jour les informations du dropdown et du profil
                    const dName = document.getElementById('dropdown-full-name');
                    if (dName) dName.textContent = data.user.full_name || 'Utilisateur';
                    const dEmail = document.getElementById('dropdown-user-email');
                    if (dEmail) dEmail.textContent = data.user.email;
                    const dRole = document.getElementById('dropdown-user-role');
                    if (dRole) {
                        dRole.textContent = data.user.is_superadmin ? 'SuperAdmin' : ((data.active_organization && data.active_organization.role) || 'Ingénieur');
                    }
                    const editEmail = document.getElementById('profile-edit-email');
                    if (editEmail) editEmail.value = data.user.email;
                    const editName = document.getElementById('profile-edit-name');
                    if (editName) editName.value = data.user.full_name || '';

                    if (data.user && data.user.is_superadmin) {
                        const supEl = document.getElementById('option-superadmin');
                        if (supEl) supEl.style.display = 'flex';
                    }
                    return;
                }
            } catch (e) {
                console.warn('Session anonyme:', e);
            }
            if (loadingEl) loadingEl.style.display = 'none';
            if (userEl) userEl.style.display = 'none';
            if (guestEl) guestEl.style.display = 'flex';
        }
