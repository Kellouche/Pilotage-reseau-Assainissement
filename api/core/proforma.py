# -*- coding: utf-8 -*-
"""
Module api.core.proforma : Génération des factures proforma et bons de commande officiels en PDF.
Conforme aux règles de facturation B2B / B2G en Algérie (Dinars Algériens - DZD) pour les directions
de l'hydraulique, collectivités et bureaux d'études VRD.
Conforme à ADR 0006 et Roadmap SaaS Phase 3.2.

Auteur : Dr Abdelhakim Kellouche / Antigravity
Date : Octobre 2026
"""

import io
from datetime import datetime
from typing import Optional
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable


def amount_to_french_words(amount: float) -> str:
    """
    Convertit un montant numérique en dinars algériens en toutes lettres selon les règles
    grammaticales françaises (norme administrative et comptable algérienne).
    Exemple : 486000.0 -> 'Quatre cent quatre-vingt-six mille Dinars Algériens'
    """
    units = ['', 'un', 'deux', 'trois', 'quatre', 'cinq', 'six', 'sept', 'huit', 'neuf']
    teens = ['dix', 'onze', 'douze', 'treize', 'quatorze', 'quinze', 'seize', 'dix-sept', 'dix-huit', 'dix-neuf']
    tens = ['', 'dix', 'vingt', 'trente', 'quarante', 'cinquante', 'soixante', 'soixante', 'quatre-vingt', 'quatre-vingt']

    def _convert_below_hundred(num: int) -> str:
        if num < 10:
            return units[num]
        elif num < 20:
            return teens[num - 10]
        else:
            t = num // 10
            u = num % 10
            if t in (7, 9):
                prefix = tens[t]
                suffix = teens[u]
                if t == 7 and u == 1:
                    return 'soixante-et-onze'
                return f'{prefix}-{suffix}'
            else:
                prefix = tens[t]
                if u == 0:
                    return prefix + ('s' if prefix == 'quatre-vingt' else '')
                elif u == 1 and t != 8:
                    return f'{prefix}-et-un'
                else:
                    return f'{prefix}-{units[u]}'

    def _convert_below_thousand(num: int) -> str:
        if num < 100:
            return _convert_below_hundred(num)
        c = num // 100
        rem = num % 100
        c_str = 'cent' if c == 1 else f'{units[c]} cent'
        if rem == 0:
            return c_str + ('s' if c > 1 else '')
        else:
            return f'{c_str} {_convert_below_hundred(rem)}'

    def _convert_integer(n: int) -> str:
        if n == 0:
            return 'zéro'
        parts = []
        billions = n // 1000000000
        n %= 1000000000
        millions = n // 1000000
        n %= 1000000
        thousands = n // 1000
        rem = n % 1000

        if billions > 0:
            b_str = 'un milliard' if billions == 1 else f'{_convert_below_thousand(billions)} milliards'
            parts.append(b_str)
        if millions > 0:
            m_str = 'un million' if millions == 1 else f'{_convert_below_thousand(millions)} millions'
            parts.append(m_str)
        if thousands > 0:
            th_str = 'mille' if thousands == 1 else f'{_convert_below_thousand(thousands)} mille'
            parts.append(th_str)
        if rem > 0:
            parts.append(_convert_below_thousand(rem))

        return ' '.join(parts)

    dinars = int(round(amount, 2))
    centimes = int(round((amount - dinars) * 100))
    if centimes < 0:
        centimes = 0

    dinars_words = _convert_integer(dinars)
    res = dinars_words[0].upper() + dinars_words[1:] + ' Dinars Algériens'
    if centimes > 0:
        centimes_words = _convert_integer(centimes)
        res += f' et {centimes_words} centimes'
    return res


def generate_proforma_pdf(
    org_name: str,
    contact_name: str,
    contact_email: str,
    plan: str = "bet",
    duration_months: int = 12,
    proforma_ref: Optional[str] = None,
    doc_type: str = "proforma",
) -> bytes:
    """
    Génère le document PDF officiel d'un Devis estimatif ou d'une Facture Proforma.

    Args:
        org_name: Raison sociale de l'organisation ou régie cliente.
        contact_name: Nom du responsable ou ingénieur référent.
        contact_email: Email de contact.
        plan: Formule demandée ('bet' ou 'exploitation').
        duration_months: Durée d'engagement (6, 12, 24, 36 mois).
        proforma_ref: Référence personnalisée optionnelle.
        doc_type: 'devis' ou 'proforma' (définit l'en-tête et les mentions juridiques).

    Returns:
        Octets bruts du fichier PDF généré.
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=1.5 * cm,
        rightMargin=1.5 * cm,
        topMargin=1.5 * cm,
        bottomMargin=1.5 * cm,
    )

    styles = getSampleStyleSheet()

    bold_style = ParagraphStyle(
        'BoldText',
        parent=styles['Normal'],
        fontSize=9,
        fontName='Helvetica-Bold',
        textColor=colors.HexColor('#1e293b'),
    )
    normal_style = ParagraphStyle(
        'NormalText',
        parent=styles['Normal'],
        fontSize=9,
        textColor=colors.HexColor('#334155'),
        leading=13,
    )

    story = []

    now = datetime.now()
    clean_type = "devis" if "devis" in doc_type.lower() else "proforma"
    prefix = "DEV" if clean_type == "devis" else "PROFORMA"
    ref = proforma_ref or f"{prefix}-{now.year}-{now.month:02d}-{now.strftime('%H%M%S')}"

    doc_title = "DEVIS ESTIMATIF OFFICIEL" if clean_type == "devis" else "FACTURE PROFORMA"
    doc_badge_color = "#0284c7" if clean_type == "devis" else "#0369a1"

    # 1. En-tête : Informations Légales SWMM Platform Solutions & Référence
    header_data = [
        [
            Paragraph(
                "<b>SWMM Platform Solutions</b><br/>"
                "Plateforme SaaS d'Ingénierie d'Assainissement & Saint-Venant<br/>"
                "Registre du Commerce (RC) : 16/00-0987654B26<br/>"
                "NIF : 002616098765432 — NIS : 002616098765432<br/>"
                "RIB BNA (Agence Alger-Centre) : 001 00624 0300 000123 45",
                normal_style
            ),
            Paragraph(
                f"<font color='{doc_badge_color}' size='14'><b>{doc_title}</b></font><br/>"
                f"<b>N° Réf :</b> <font color='#0f172a'><b>{ref}</b></font><br/>"
                f"<b>Date d'émission :</b> {now.strftime('%d/%m/%Y')}<br/>"
                f"<b>Validité de l'offre :</b> 60 jours calendaires",
                normal_style
            )
        ]
    ]
    header_table = Table(header_data, colWidths=[10 * cm, 8 * cm])
    header_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
    ]))
    story.append(header_table)
    story.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor('#0284c7'), spaceAfter=14, spaceBefore=4))

    # 2. Bloc Client & Modalités
    delivery_mode = "Bon pour Accord sur devis ou Bon de Commande" if clean_type == "devis" else "Bon de Commande Administratif ou Virement Bancaire"
    client_data = [
        [
            Paragraph("<b>CLIENT / ORGANISATION DESTINATAIRE :</b>", bold_style),
            Paragraph("<b>CONDITIONS DE RÈGLEMENT & LIVRAISON :</b>", bold_style)
        ],
        [
            Paragraph(
                f"<b>Organisme :</b> {org_name}<br/>"
                f"<b>Contact Référent :</b> {contact_name or 'Direction Technique / Commission Marchés'}<br/>"
                f"<b>Email :</b> {contact_email or 'contact@client.dz'}",
                normal_style
            ),
            Paragraph(
                f"Mode : {delivery_mode}<br/>"
                "Devise : Dinars Algériens (DZD / DA)<br/>"
                "Délai d'activation : Immédiat dès validation administrative",
                normal_style
            )
        ]
    ]
    client_table = Table(client_data, colWidths=[10 * cm, 8 * cm])
    client_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#f8fafc')),
        ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
    ]))
    story.append(client_table)
    story.append(Spacer(1, 14))

    # 3. Détail des Prestations
    clean_plan = plan.lower().strip()
    if clean_plan in ("exploitation", "entreprise", "regie"):
        plan_label = "Convention SWMM Platform - Entreprises de Gestion & Régies Communales"
        plan_desc = (
            "Convention annuelle d'exploitation pour entreprises de gestion de l'assainissement et régies communales. "
            "Modélisation hydraulique de l'ensemble du réseau communal, diagnostics de conformité et autocurage "
            "NP 650 / Fascicule 70, découpage des bassins versants sur MNT et simulations complètes SWMM 5.2."
        )
        monthly_ht = 180000.0
    else:
        # Formule BET par défaut
        plan_label = "Abonnement SWMM Platform Bureau d'Études Techniques (BET)"
        plan_desc = (
            "Formule professionnelle pour bureaux d'études VRD et ingénierie assainissement (jusqu'à 15 000 regards). "
            "Audits de conformité réglementaire Fascicule 70, profils en long hydrauliques, découpage de bassins MNT, "
            "exports officiels EPA SWMM .inp et fiches de calcul sans filigrane."
        )
        monthly_ht = 45000.0

    total_ht = monthly_ht * duration_months
    remise_text = ""
    if clean_plan == "bet" and duration_months >= 12:
        years = duration_months // 12
        remainder = duration_months % 12
        total_ht = (years * 450000.0) + (remainder * monthly_ht)
        remise_text = " (Tarif préférentiel annuel de 450 000 DA HT / an, soit 2 mois offerts pour engagement 12 mois)"

    tva = total_ht * 0.19
    total_ttc = total_ht + tva

    # 4. Tableau des Postes
    items_header = [
        Paragraph("<b>Désignation de la Prestation Logicielle</b>", bold_style),
        Paragraph("<b>Période</b>", bold_style),
        Paragraph("<b>P.U. Mensuel HT</b>", bold_style),
        Paragraph("<b>Montant HT (DZD)</b>", bold_style),
    ]
    items_row = [
        Paragraph(f"<b>{plan_label}</b><br/><font color='#475569'>{plan_desc}{remise_text}</font>", normal_style),
        Paragraph(f"<b>{duration_months} mois</b>", normal_style),
        Paragraph(f"{monthly_ht:,.2f} DA".replace(',', ' '), normal_style),
        Paragraph(f"<b>{total_ht:,.2f} DA</b>".replace(',', ' '), normal_style),
    ]

    items_table = Table([items_header, items_row], colWidths=[9 * cm, 2.3 * cm, 3.3 * cm, 3.4 * cm])
    items_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0284c7')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
    ]))
    story.append(items_table)
    story.append(Spacer(1, 14))

    # 5. Synthèse Financière
    totals_data = [
        ["Total Général Hors Taxes (HT) :", f"{total_ht:,.2f} DA".replace(',', ' ')],
        ["Taxe sur la Valeur Ajoutée (T.V.A. 19.00%) :", f"{tva:,.2f} DA".replace(',', ' ')],
        ["TOTAL GÉNÉRAL TOUTES TAXES COMPRISES (TTC) :", f"{total_ttc:,.2f} DA".replace(',', ' ')],
    ]
    totals_table = Table(totals_data, colWidths=[11.5 * cm, 6.5 * cm])
    totals_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'RIGHT'),
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('TEXTCOLOR', (0, 2), (-1, 2), colors.HexColor('#0369a1')),
        ('LINEABOVE', (0, 2), (-1, 2), 1, colors.HexColor('#0284c7')),
    ]))
    story.append(totals_table)
    story.append(Spacer(1, 14))

    # 6. Arrêté en toutes lettres
    montant_en_lettres = amount_to_french_words(total_ttc)
    formatted_numeric = f"{total_ttc:,.2f} DA TTC".replace(',', ' ')
    doc_nom = "le présent devis estimatif" if clean_type == "devis" else "la présente facture proforma"
    mention_text = f"Arrêté {doc_nom} à la somme totale de : <b>{montant_en_lettres}</b> ({formatted_numeric})."
    story.append(Paragraph(mention_text, normal_style))
    story.append(Spacer(1, 14))

    # 7. Instructions pour l'engagement & Signature
    if clean_type == "devis":
        footer_instructions = (
            "<b>Procédure de Validation du Devis :</b><br/>"
            "1. Pour acceptation, apposer la mention manuscrite « Bon pour Accord », date, cachet et signature.<br/>"
            "2. Retourner l'exemplaire signé ou établir votre Bon de Commande avec la référence <b>" + ref + "</b>.<br/>"
            "3. Dès transmission, votre espace de travail et votre clé de licence sont activés."
        )
        footer_sign = (
            "<b>Pour acceptation du Devis :</b><br/>"
            "<i>Mention manuscrite « Bon pour Accord », cachet et signature autorisée</i>"
        )
    else:
        footer_instructions = (
            "<b>Procédure d'Engagement & Souscription :</b><br/>"
            "1. Établir votre Bon de Commande administratif en mentionnant la référence <b>" + ref + "</b>.<br/>"
            "2. Transmettre le document scanné visé et tamponné sur votre portail <i>Licence & Facturation</i>.<br/>"
            "3. Dès réception, votre licence officielle et votre clé d'activation sont activées immédiatement."
        )
        footer_sign = (
            "<b>Pour SWMM Platform Solutions</b><br/>"
            "Direction Commerciale & Relations Marchés<br/><br/>"
            "<i>Document officiel proforma établi pour valoir ce que de droit.</i>"
        )

    footer_data = [
        [
            Paragraph(footer_instructions, normal_style),
            Paragraph(footer_sign, normal_style)
        ]
    ]
    footer_table = Table(footer_data, colWidths=[11 * cm, 7 * cm])
    footer_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#f8fafc')),
        ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
    ]))
    story.append(footer_table)

    doc.build(story)
    return buffer.getvalue()


def generate_purchase_order_pdf(order) -> bytes:
    """
    Génère un document PDF officiel attestant du Bon de Commande / Engagement Budgétaire
    pour une organisation abonnée (utilisé pour archivage et prévisualisation légale).
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=1.5 * cm,
        rightMargin=1.5 * cm,
        topMargin=1.5 * cm,
        bottomMargin=1.5 * cm,
    )

    styles = getSampleStyleSheet()

    bold_style = ParagraphStyle(
        'POBoldText',
        parent=styles['Normal'],
        fontSize=9,
        fontName='Helvetica-Bold',
        textColor=colors.HexColor('#1e293b'),
    )
    normal_style = ParagraphStyle(
        'PONormalText',
        parent=styles['Normal'],
        fontSize=9,
        textColor=colors.HexColor('#334155'),
        leading=13,
    )
    title_style = ParagraphStyle(
        'POTitle',
        parent=styles['Normal'],
        fontSize=14,
        fontName='Helvetica-Bold',
        textColor=colors.HexColor('#0f172a'),
        alignment=1,
        spaceAfter=15,
    )

    story = []

    order_ref = getattr(order, 'order_ref', 'BC-OFFICIEL')
    entity_name = getattr(order, 'entity_name', 'Client SWMM Platform')
    contact_name = getattr(order, 'contact_name', '') or 'Direction Technique'
    contact_email = getattr(order, 'contact_email', '') or 'contact@client.dz'
    target_plan = getattr(order, 'target_plan', 'bet').upper()
    duration_months = getattr(order, 'duration_months', 12)
    amount_dzd = float(getattr(order, 'amount_dzd', 0.0) or 0.0)
    created_at = getattr(order, 'created_at', datetime.now())
    created_str = created_at.strftime('%d/%m/%Y') if hasattr(created_at, 'strftime') and created_at else str(created_at)
    status_raw = str(getattr(order, 'status', 'approved')).lower()

    if status_raw == 'approved':
        status_display = "<font color='#16a34a'><b>VALIDÉ / CONFORME</b></font>"
    elif status_raw == 'rejected':
        status_display = "<font color='#dc2626'><b>REJETÉ / NON CONFORME</b></font>"
    else:
        status_display = "<font color='#d97706'><b>EN ATTENTE D'INSTRUCTION</b></font>"

    # En-tête officiel
    header_data = [
        [
            Paragraph(
                "<b>RÉPUBLIQUE ALGÉRIENNE DÉMOCRATIQUE ET POPULAIRE</b><br/>"
                "<b>ORGANISME SOUSCRIPTEUR / CLIENT</b><br/>"
                f"<b>{entity_name}</b><br/>"
                f"Contact : {contact_name} ({contact_email})",
                normal_style
            ),
            Paragraph(
                f"<b>BON DE COMMANDE ADMINISTRATIF</b><br/>"
                f"Réf. Engagement : <font color='#0284c7'><b>{order_ref}</b></font><br/>"
                f"Date d'émission : <b>{created_str}</b><br/>"
                f"Statut d'instruction : {status_display}",
                normal_style
            )
        ]
    ]
    t_header = Table(header_data, colWidths=[10 * cm, 8 * cm])
    t_header.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
    ]))
    story.append(t_header)
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor('#0284c7'), spaceAfter=14))

    # Titre central
    story.append(Paragraph("ENGAGEMENT DE COMMANDE — LICENCE SWMM PLATFORM SAAS", title_style))

    # Tableau récapitulatif
    recap_data = [
        [Paragraph("<b>Paramètre</b>", bold_style), Paragraph("<b>Détail de la souscription</b>", bold_style)],
        [Paragraph("Formule souscrite", normal_style), Paragraph(f"<b>{target_plan}</b>", normal_style)],
        [Paragraph("Durée d'engagement", normal_style), Paragraph(f"<b>{duration_months} mois</b>", normal_style)],
        [Paragraph("Montant de l'engagement", normal_style), Paragraph(f"<b>{amount_dzd:,.2f} DA</b>".replace(',', ' '), normal_style)],
        [Paragraph("Clé d'activation générée", normal_style), Paragraph(f"<code>{getattr(order, 'license_token', None) or 'En attente'}</code>", normal_style)],
    ]
    t_recap = Table(recap_data, colWidths=[6 * cm, 12 * cm])
    t_recap.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#f1f5f9')),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
    ]))
    story.append(t_recap)

    doc.build(story)
    return buffer.getvalue()
