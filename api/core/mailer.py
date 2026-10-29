# -*- coding: utf-8 -*-
"""
Nom Auteur : Dr Abdelhakim Kellouche
Nom de l'application : SWMM Platform SaaS
Numéro version : 2.1.0
Date de création : 29-10-2026
Date de modification : 29-10-2026

Module api.core.mailer : Service d'expédition des e-mails transactionnels et codes d'activation.
Prend en charge la configuration SMTP standard ou le mode simulation en développement local.
"""

import os
import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional

logger = logging.getLogger(__name__)

# Paramètres SMTP configurables via l'environnement
SMTP_HOST: Optional[str] = os.getenv("SMTP_HOST")
SMTP_PORT: int = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER: Optional[str] = os.getenv("SMTP_USER")
SMTP_PASSWORD: Optional[str] = os.getenv("SMTP_PASSWORD")
SMTP_FROM: str = os.getenv("SMTP_FROM", "activation@swmm-platform.dz")
SMTP_TLS: bool = os.getenv("SMTP_TLS", "true").lower() == "true"


def send_activation_email(to_email: str, code: str, full_name: str = "") -> bool:
    """
    Expédie l'e-mail contenant le code d'activation à 6 chiffres.
    Si le serveur SMTP n'est pas configuré, bascule gracieusement en mode simulation.
    """
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

    # 1. Mode Production avec SMTP actif
    if SMTP_HOST and SMTP_USER:
        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = SMTP_FROM
            msg["To"] = to_email

            msg.attach(MIMEText(text_content, "plain", "utf-8"))
            msg.attach(MIMEText(html_content, "html", "utf-8"))

            server = smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10)
            if SMTP_TLS:
                server.starttls()
            if SMTP_PASSWORD:
                server.login(SMTP_USER, SMTP_PASSWORD)
            server.sendmail(SMTP_FROM, [to_email], msg.as_string())
            server.quit()

            logger.info("Email d'activation expédié avec succès à %s", to_email)
            return True
        except Exception as e:
            logger.error("Erreur lors de l'envoi SMTP à %s : %s", to_email, e)

    # 2. Mode Développement / Simulation locale
    print("\n" + "=" * 60)
    print("📧 [SWMM Platform — Simulation d'envoi d'e-mail]")
    print(f"Destinataire : {to_email}")
    print(f"Objet        : {subject}")
    print(f"Code généré  : {code}")
    print("Durée        : Valable 15 minutes")
    print("=" * 60 + "\n", flush=True)

    return True
