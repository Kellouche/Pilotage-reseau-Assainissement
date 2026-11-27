/**
 * ================================================================================
 * Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
 * Auteur : Dr Abdelhakim KELLOUCHE
 * Date de création : 2026-11-27
 * Date de modification : 2026-11-27
 * Objet : Logique d'inscription / vérification email de la page de souscription
 * ================================================================================
 */

    const FORMULAS = {
        demo: {
            title: "DrainPilot",
            subtitle: "Essai Démo (14 jours gratuits sans engagement)",
            btnText: "Activer mon essai gratuit (14 jours)",
            orgLabel: "Nom de votre organisation",
            orgPlaceholder: "Bureau d'études ou service technique",
            emailLabel: "Adresse email professionnelle",
            emailPlaceholder: "nom@entreprise.com",
            emailHelp: "",
            renderSummary: () => `
                <div class="d-flex justify-content-between align-items-center">
                    <div>
                        <span class="badge bg-dark me-2">Essai Démo</span>
                        <span class="text-muted small">Évaluation 14 jours sans engagement</span>
                    </div>
                    <div class="h5 fw-bold text-dark mb-0">0 DZD</div>
                </div>
            `
        },
        education: {
            title: "DrainPilot",
            subtitle: "Offre Académique & Recherche (Universités et recherche)",
            btnText: "Valider mon inscription académique",
            orgLabel: "Université / Faculté / Laboratoire",
            orgPlaceholder: "Université des Sciences et de la Technologie",
            emailLabel: "Adresse email universitaire",
            emailPlaceholder: "prenom.nom@univ-alger.dz",
            emailHelp: "Adresse email universitaire requise (.univ.dz, .edu...).",
            renderSummary: () => `
                <div class="d-flex justify-content-between align-items-center">
                    <div>
                        <span class="badge bg-secondary me-2">Académique</span>
                        <span class="text-muted small">Recherche & enseignement (email universitaire requis)</span>
                    </div>
                    <div class="h5 fw-bold text-dark mb-0">0 DZD <span class="fs-6 fw-normal text-muted">/ permanent</span></div>
                </div>
            `
        },
        bet: {
            title: "DrainPilot",
            subtitle: "Offre Bureau d'Études (BET) — Modélisation et audit capacitaire",
            btnText: "Confirmer ma commande BET",
            orgLabel: "Raison sociale du Bureau d'Études VRD",
            orgPlaceholder: "Cabinet d'Ingénierie & VRD",
            emailLabel: "Adresse email professionnelle",
            emailPlaceholder: "contact@bet-ingenierie.dz",
            emailHelp: "",
            renderSummary: () => `
                <div class="d-flex justify-content-between align-items-center mb-2">
                    <div>
                        <span class="badge bg-primary me-2">Bureau d'Études</span>
                        <span class="text-muted small">Licence professionnelle</span>
                    </div>
                    <div class="h5 fw-bold text-primary mb-0" id="betDisplayPrice">450 000 DZD / an</div>
                </div>
                <div class="row g-2">
                    <div class="col-6">
                        <label class="form-check p-2 rounded border bg-white mb-0 w-100" style="cursor: pointer;">
                            <input class="form-check-input ms-0 me-2" type="radio" name="betPeriod" id="betAnnual" value="annual" checked onchange="updateBetPrice()">
                            <span class="small"><strong>Annuel</strong> (450 000 DZD/an)</span>
                        </label>
                    </div>
                    <div class="col-6">
                        <label class="form-check p-2 rounded border bg-white mb-0 w-100" style="cursor: pointer;">
                            <input class="form-check-input ms-0 me-2" type="radio" name="betPeriod" id="betMonthly" value="monthly" onchange="updateBetPrice()">
                            <span class="small"><strong>Mensuel</strong> (45 000 DZD/mois)</span>
                        </label>
                    </div>
                </div>
            `
        },
        exploitation: {
            title: "DrainPilot",
            subtitle: "Offre Régies & Entreprises — Système modulaire à la carte",
            btnText: "Valider ma commande modulaire",
            orgLabel: "Nom de la Régie Communale ou Service Municipal",
            orgPlaceholder: "Régie Communale d'Assainissement",
            emailLabel: "Adresse email du service",
            emailPlaceholder: "technique@regie-assainissement.dz",
            emailHelp: "",
            renderSummary: () => `
                <div class="d-flex justify-content-between align-items-center mb-2">
                    <div>
                        <span class="badge bg-success me-2">Régies & Entreprises</span>
                        <span class="text-muted small">Système Modulaire communal</span>
                    </div>
                    <div class="h5 fw-bold text-success mb-0" id="modulaireTotalPrice">650 000 DZD / an</div>
                </div>
                <div class="d-flex flex-column gap-1 mb-2">
                    <label class="form-check p-2 rounded border bg-white mb-0 d-flex justify-content-between align-items-center" style="cursor: pointer;">
                        <div>
                            <input class="form-check-input ms-0 me-2" type="checkbox" id="modA" checked onchange="calcModularTotal()">
                            <span class="small fw-semibold">Module A — Application mobile</span>
                        </div>
                        <span class="badge bg-light text-dark border">250 000 DZD/an</span>
                    </label>
                    <label class="form-check p-2 rounded border bg-white mb-0 d-flex justify-content-between align-items-center" style="cursor: pointer;">
                        <div>
                            <input class="form-check-input ms-0 me-2" type="checkbox" id="modB" checked onchange="calcModularTotal()">
                            <span class="small fw-semibold">Module B — Diagnostic autocurage NP 650</span>
                        </div>
                        <span class="badge bg-light text-dark border">200 000 DZD/an</span>
                    </label>
                    <label class="form-check p-2 rounded border bg-white mb-0 d-flex justify-content-between align-items-center" style="cursor: pointer;">
                        <div>
                            <input class="form-check-input ms-0 me-2" type="checkbox" id="modC" checked onchange="calcModularTotal()">
                            <span class="small fw-semibold">Module C — Modélisation SWMM & MNT</span>
                        </div>
                        <span class="badge bg-light text-dark border">350 000 DZD/an</span>
                    </label>
                </div>
                <label class="form-check p-2 rounded border bg-white mb-0" style="cursor: pointer;">
                    <input class="form-check-input ms-0 me-2" type="checkbox" id="chkConvention" onchange="calcModularTotal()">
                    <span class="small">Convention pour mission spécifique</span>
                </label>
            `
        }
    };

    function setFormula(planKey) {
        if (!FORMULAS[planKey]) planKey = 'demo';
        document.getElementById('billingPlan').value = planKey;

        document.querySelectorAll('.formula-tab').forEach(tab => tab.classList.remove('active'));
        const activeTab = document.getElementById(`tab-${planKey}`);
        if (activeTab) activeTab.classList.add('active');

        const cfg = FORMULAS[planKey];

        document.getElementById('orderTitle').textContent = "DrainPilot";
        document.getElementById('orderSubtitle').textContent = cfg.subtitle;
        document.getElementById('btnSubmitText').textContent = cfg.btnText;

        document.getElementById('orgLabel').textContent = cfg.orgLabel;
        document.getElementById('orgName').placeholder = cfg.orgPlaceholder;
        document.getElementById('emailLabel').textContent = cfg.emailLabel;
        document.getElementById('email').placeholder = cfg.emailPlaceholder;

        const emailHelp = document.getElementById('emailHelpText');
        if (cfg.emailHelp) {
            emailHelp.textContent = cfg.emailHelp;
            emailHelp.classList.remove('d-none');
        } else {
            emailHelp.classList.add('d-none');
        }

        const summaryBox = document.getElementById('summaryBox');
        summaryBox.className = `summary-box ${planKey}-theme`;
        summaryBox.innerHTML = cfg.renderSummary();

        if (planKey === 'exploitation') {
            calcModularTotal();
        }
    }

    function updateBetPrice() {
        const isAnnual = document.getElementById('betAnnual').checked;
        const priceEl = document.getElementById('betDisplayPrice');
        if (isAnnual) {
            priceEl.textContent = '450 000 DZD / an';
        } else {
            priceEl.textContent = '45 000 DZD / mois';
        }
    }

    function calcModularTotal() {
        const isConvention = document.getElementById('chkConvention') && document.getElementById('chkConvention').checked;
        const priceEl = document.getElementById('modulaireTotalPrice');
        const btnText = document.getElementById('btnSubmitText');

        if (isConvention) {
            priceEl.textContent = 'Sur convention';
            btnText.textContent = 'Demander une convention personnalisée';
            return;
        }

        const a = document.getElementById('modA') && document.getElementById('modA').checked;
        const b = document.getElementById('modB') && document.getElementById('modB').checked;
        const c = document.getElementById('modC') && document.getElementById('modC').checked;

        if (a && b && c) {
            priceEl.textContent = '650 000 DZD / an (Pack)';
            btnText.textContent = 'Valider ma commande Pack Intégral';
        } else {
            let total = 0;
            let count = 0;
            if (a) { total += 250000; count++; }
            if (b) { total += 200000; count++; }
            if (c) { total += 350000; count++; }

            if (count === 0) {
                priceEl.textContent = '0 DZD';
                btnText.textContent = 'Sélectionnez au moins un module';
            } else {
                priceEl.textContent = `${total.toLocaleString('fr-FR')} DZD / an`;
                btnText.textContent = `Valider ma sélection (${count} module${count > 1 ? 's' : ''})`;
            }
        }
    }

    window.addEventListener('DOMContentLoaded', () => {
        const urlParams = new URLSearchParams(window.location.search);
        const planParam = urlParams.get('plan');
        const validPlans = ['demo', 'education', 'bet', 'exploitation'];
        const initialPlan = (planParam && validPlans.includes(planParam.toLowerCase())) ? planParam.toLowerCase() : 'demo';
        setFormula(initialPlan);

        const emailParam = urlParams.get('email');
        if (emailParam) {
            const emailInp = document.getElementById('email');
            if (emailInp) {
                emailInp.value = emailParam;
                document.getElementById('fullName').focus();
            }
        }
    });

    const form = document.getElementById('registerForm');
    const alertBox = document.getElementById('alertBox');
    const alertMsg = document.getElementById('alertMsg');
    const btnSubmit = document.getElementById('btnSubmit');

    // Vérification préventive de l'email au défocus
    const emailInput = document.getElementById('email');
    emailInput.addEventListener('blur', async () => {
        const val = emailInput.value.trim().toLowerCase();
        if (val && val.includes('@') && val.includes('.')) {
            try {
                const resp = await fetch(`/api/v1/auth/check-email?email=${encodeURIComponent(val)}`);
                if (resp.ok) {
                    const res = await resp.json();
                    if (res.exists) {
                        alertMsg.innerHTML = `<i class="fas fa-exclamation-triangle me-1"></i> Cette adresse email est déjà enregistrée. <a href="/login?email=${encodeURIComponent(val)}" class="alert-link fw-bold ms-1">Se connecter directement</a>`;
                        alertBox.classList.remove('d-none');
                    }
                }
            } catch (e) {
                // silencieux
            }
        }
    });

    form.addEventListener('submit', async (e) => {
        e.preventDefault();
        alertBox.classList.add('d-none');

        const pwd = document.getElementById('password').value;
        const pwdConfirm = document.getElementById('password_confirm').value;

        if (pwd !== pwdConfirm) {
            alertMsg.innerHTML = '<i class="fas fa-exclamation-circle me-1"></i> Les mots de passe saisis ne sont pas identiques.';
            alertBox.classList.remove('d-none');
            return;
        }

        const plan = document.getElementById('billingPlan').value;
        const orgType = plan === 'education' ? 'academique' : (plan === 'exploitation' ? 'regie' : 'bet');

        if (plan === 'education') {
            const emailVal = document.getElementById('email').value.trim().toLowerCase();
            const isEdu = emailVal.includes('.edu') || emailVal.includes('.univ') || emailVal.includes('.ac.') || emailVal.includes('polytech');
            if (!isEdu) {
                alertMsg.textContent = "L'offre Académique & Recherche requiert une adresse email universitaire (.univ.dz, .edu...). Pour les bureaux d'études, veuillez sélectionner l'offre Bureau d'Études.";
                alertBox.classList.remove('d-none');
                return;
            }
        }

        btnSubmit.disabled = true;
        const originalBtnText = btnSubmit.innerHTML;
        btnSubmit.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>Traitement...';

        try {
            const emailVal = document.getElementById('email').value.trim();
            const resp = await fetch('/api/v1/auth/register', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    email: emailVal,
                    password: pwd,
                    full_name: document.getElementById('fullName').value.trim(),
                    org_name: document.getElementById('orgName').value.trim(),
                    billing_plan: plan,
                    org_type: orgType
                })
            });

            const data = await resp.json();

            if (!resp.ok) {
                const detail = data.detail || 'Erreur lors de la création de la commande';
                if (detail.includes('existe déjà')) {
                    alertMsg.innerHTML = `<i class="fas fa-user-check me-1"></i> Un compte existe déjà pour cette adresse email. <a href="/login?email=${encodeURIComponent(emailVal)}" class="alert-link fw-bold ms-1">Cliquez ici pour vous connecter</a>`;
                    alertBox.classList.remove('d-none');
                    btnSubmit.disabled = false;
                    btnSubmit.innerHTML = originalBtnText;
                    return;
                }
                throw new Error(detail);
            }

            currentRegisteredEmail = emailVal;

            if (data.requires_verification) {
                localStorage.removeItem('swmm_access_token');
                document.cookie = "access_token=; path=/; max-age=0";
                document.getElementById('step-register').classList.add('d-none');
                document.getElementById('step-verify').classList.remove('d-none');
                const formulaNav = document.querySelector('.formula-nav');
                if (formulaNav) formulaNav.classList.add('d-none');
                document.getElementById('orderSubtitle').textContent = "Validation de sécurité par code d'activation";
                document.getElementById('verify-email-display').textContent = emailVal;

                if (data.dev_code) {
                    document.getElementById('devCodeDisplay').textContent = data.dev_code;
                    document.getElementById('devCodeBox').classList.remove('d-none');
                } else {
                    document.getElementById('devCodeBox').classList.add('d-none');
                }
                btnSubmit.disabled = false;
                btnSubmit.innerHTML = originalBtnText;
                setTimeout(() => document.getElementById('activationCode').focus(), 150);
                return;
            }

            if (data.access_token) {
                localStorage.setItem('swmm_access_token', data.access_token);
                document.cookie = `access_token=${data.access_token}; path=/; max-age=604800; SameSite=Lax`;
            }

            window.location.href = '/map';

        } catch (err) {
            alertMsg.textContent = err.message;
            alertBox.classList.remove('d-none');
            btnSubmit.disabled = false;
            btnSubmit.innerHTML = originalBtnText;
        }
    });

    let currentRegisteredEmail = "";

    window.retourFormulaireInscription = function() {
        document.getElementById('step-verify').classList.add('d-none');
        document.getElementById('step-register').classList.remove('d-none');
        const formulaNav = document.querySelector('.formula-nav');
        if (formulaNav) formulaNav.classList.remove('d-none');
        document.getElementById('orderSubtitle').textContent = "Formulaire de commande & création d'organisation";
    };

    window.renvoyerCodeActivation = async function() {
        if (!currentRegisteredEmail) {
            currentRegisteredEmail = document.getElementById('email').value.trim();
        }
        if (!currentRegisteredEmail) return;

        const btnResend = document.getElementById('btnResend');
        btnResend.disabled = true;
        const origResendHtml = btnResend.innerHTML;
        btnResend.innerHTML = '<span class="spinner-border spinner-border-sm me-1"></span>Envoi...';

        try {
            const resp = await fetch('/api/v1/auth/resend-code', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ email: currentRegisteredEmail })
            });
            const data = await resp.json();
            if (!resp.ok) {
                throw new Error(data.detail || "Erreur lors du renvoi.");
            }
            if (data.dev_code) {
                document.getElementById('devCodeDisplay').textContent = data.dev_code;
                document.getElementById('devCodeBox').classList.remove('d-none');
            }
            verifyAlertBox.className = "alert alert-success small py-2";
            verifyAlertMsg.innerHTML = '<i class="fas fa-check-circle me-1"></i> Un nouveau code d\'activation (valable 15 minutes) a été envoyé par e-mail.';
            verifyAlertBox.classList.remove('d-none');
            document.getElementById('activationCode').value = '';
            document.getElementById('activationCode').focus();

            let seconds = 30;
            btnResend.innerHTML = `<i class="fas fa-check text-success me-1"></i> Envoyé (${seconds}s)`;
            const timer = setInterval(() => {
                seconds -= 1;
                if (seconds <= 0) {
                    clearInterval(timer);
                    btnResend.disabled = false;
                    btnResend.innerHTML = '<i class="fas fa-redo me-1"></i> Renvoyer un code';
                } else {
                    btnResend.innerHTML = `<i class="fas fa-hourglass-half me-1"></i> Renvoyer (${seconds}s)`;
                }
            }, 1000);
        } catch (e) {
            verifyAlertBox.className = "alert alert-danger small py-2";
            verifyAlertMsg.textContent = 'Erreur lors du renvoi : ' + e.message;
            verifyAlertBox.classList.remove('d-none');
            btnResend.disabled = false;
            btnResend.innerHTML = origResendHtml;
        }
    };

    const verifyForm = document.getElementById('verifyForm');
    const verifyAlertBox = document.getElementById('verifyAlertBox');
    const verifyAlertMsg = document.getElementById('verifyAlertMsg');
    const btnVerifySubmit = document.getElementById('btnVerifySubmit');

    verifyForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        verifyAlertBox.classList.add('d-none');

        const codeVal = document.getElementById('activationCode').value.trim();
        if (!codeVal || codeVal.length < 4) {
            verifyAlertMsg.textContent = "Veuillez saisir le code d'activation reçu.";
            verifyAlertBox.classList.remove('d-none');
            return;
        }

        btnVerifySubmit.disabled = true;
        const origText = btnVerifySubmit.innerHTML;
        btnVerifySubmit.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>Vérification...';

        try {
            const resp = await fetch('/api/v1/auth/verify-email', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    email: currentRegisteredEmail,
                    code: codeVal
                })
            });

            const data = await resp.json();
            if (!resp.ok) {
                throw new Error(data.detail || "Code d'activation invalide ou expiré.");
            }

            if (data.access_token) {
                localStorage.setItem('swmm_access_token', data.access_token);
                document.cookie = `access_token=${data.access_token}; path=/; max-age=604800; SameSite=Lax`;
            }

            // Redirection immédiate vers le workspace cartographique
            window.location.href = '/map';

        } catch (err) {
            const isExpired = err.message && err.message.toLowerCase().includes('expiré');
            if (isExpired) {
                verifyAlertBox.className = "alert alert-warning small py-2";
                verifyAlertMsg.innerHTML = `<i class="fas fa-hourglass-end me-1"></i> ${err.message} <button type="button" class="btn btn-sm btn-outline-danger ms-2 py-0 px-2 fw-semibold" onclick="renvoyerCodeActivation()"><i class="fas fa-redo-alt me-1"></i>Renvoyer un nouveau code</button>`;
            } else {
                verifyAlertBox.className = "alert alert-danger small py-2";
                verifyAlertMsg.textContent = err.message;
            }
            verifyAlertBox.classList.remove('d-none');
            btnVerifySubmit.disabled = false;
            btnVerifySubmit.innerHTML = origText;
        }
    });
