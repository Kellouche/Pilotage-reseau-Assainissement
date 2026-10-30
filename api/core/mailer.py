# -*- coding: utf-8 -*-
"""
Nom Auteur : Dr Abdelhakim Kellouche
Nom de l'application : SWMM Platform SaaS
Numéro version : 2.1.0
Date de création : 29-10-2026
Date de modification : 30-10-2026

Module api.core.mailer : Service d'expédition des e-mails transactionnels et codes d'activation.
Prend en charge la configuration SMTP standard ou le mode simulation en développement local.
"""

import os
import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional, Tuple
from config.settings import ROOT_DIR
from dotenv import load_dotenv

logger = logging.getLogger(__name__)


def _get_smtp_config() -> Tuple[Optional[str], int, Optional[str], Optional[str], str, bool]:
    """Charge dynamiquement la configuration SMTP depuis les variables d'environnement / .env."""
    load_dotenv(dotenv_path=ROOT_DIR / ".env", override=False)
    host = os.getenv("SMTP_HOST")
    port = int(os.getenv("SMTP_PORT", "587"))
    user = os.getenv("SMTP_USER")
    password = os.getenv("SMTP_PASSWORD")
    sender = os.getenv("SMTP_FROM", user or "activation@swmm-platform.dz")
    tls = os.getenv("SMTP_TLS", "true").lower() == "true"
    return host, port, user, password, sender, tls


def send_activation_email(to_email: str, code: str, full_name: str = "") -> bool:
    """
    Expédie l'e-mail contenant le code d'activation à 6 chiffres.
    Si le serveur SMTP est configuré, envoie le courriel réel.
    Sinon, bascule en mode simulation locale pour le développement.
    """
    smtp_host, smtp_port, smtp_user, smtp_password, smtp_from, smtp_tls = _get_smtp_config()
    subject = f"SWMM Platform — Code d'activation : {code}"

    # Corps HTML de l'email
    html_content = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #f1f5f9; margin: 0; padding: 24px; color: #1e293b; }}
  .card {{ background-color: #ffffff; border-radius: 12px; max-width: 520px; margin: 0 auto; padding: 32px; box-shadow: 0 4px 12px rgba(0,0,0,0.06); border: 1px solid #e2e8f0; }}
  .logo {{ text-align: center; margin-bottom: 24px; color: #0284c7; font-size: 28px; font-weight: 800; }}
  .code-box {{ background-color: #f0f9ff; border: 2px dashed #0284c7; border-radius: 8px; padding: 18px; text-align: center; margin: 24px 0; }}
  .code {{ font-size: 32px; font-weight: 800; letter-spacing: 6px; color: #0369a1; }}
  .footer {{ font-size: 12px; color: #94a3b8; text-align: center; margin-top: 24px; border-top: 1px solid #e2e8f0; padding-top: 16px; }}
</style>
</head>
<body>
  <div class="card">
    <div class="logo">🌊 SWMM Platform</div>
    <h3 style="margin-top: 0; color: #0f172a;">Activation de votre compte</h3>
    <p>Bonjour {full_name or 'Cher ingénieur'},</p>
    <p>Merci de vous être inscrit sur <strong>SWMM Platform</strong>. Pour valider votre adresse e-mail et activer votre espace de travail, veuillez saisir le code de vérification suivant :</p>
    
    <div class="code-box">
      <div class="code">{code}</div>
      <small style="color: #64748b; display: block; margin-top: 6px;">Ce code est valable pendant 15 minutes.</small>
    </div>

    <p style="font-size: 13px; color: #64748b;">Si vous n'êtes pas à l'origine de cette demande, vous pouvez ignorer cet e-mail en toute sécurité.</p>
    
    <div class="footer">
      SWMM Platform SaaS — Plateforme d'audit capacitaire et de modélisation hydraulique.<br>
      Fascicule 70 &amp; Norme Algérienne NP 650.
    </div>
  </div>
</body>
</html>
"""

    text_content = f"""Bonjour {full_name or ''},

Votre code d'activation SWMM Platform est : {code}
Ce code est valable pendant 15 minutes.

SWMM Platform SaaS
"""

    # 1. Mode Production avec SMTP réel configuré
    if smtp_host and smtp_user and smtp_password:
        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = smtp_from
            msg["To"] = to_email

            msg.attach(MIMEText(text_content, "plain", "utf-8"))
            msg.attach(MIMEText(html_content, "html", "utf-8"))

            logger.info("Tentative d'envoi SMTP à %s via %s:%s...", to_email, smtp_host, smtp_port)
            server = smtplib.SMTP(smtp_host, smtp_port, timeout=12)
            if smtp_tls:
                server.starttls()
            server.login(smtp_user, smtp_password)
            server.sendmail(smtp_from, [to_email], msg.as_string())
            server.quit()

            logger.info("Email d'activation expédié avec succès à %s", to_email)
            print(f"[MAILER] Email réel expédié avec succès à {to_email}")
            return True
        except Exception as e:
            logger.error("Erreur lors de l'envoi SMTP réel à %s : %s", to_email, e)
            print(f"[MAILER] ERREUR envoi SMTP réel à {to_email}: {e}")

    # 2. Mode Développement / Simulation locale (fallback)
    print("\n" + "=" * 60)
    print("📧 [SWMM Platform — Simulation d'envoi d'e-mail]")
    print(f"Destinataire : {to_email}")
    print(f"Objet        : {subject}")
    print(f"Code généré  : {code}")
    print("Durée        : Valable 15 minutes")
    if not (smtp_host and smtp_user and smtp_password):
        print("Note         : Serveur SMTP non configuré dans .env. Mode simulation actif.")
    print("=" * 60 + "\n", flush=True)

    return True
