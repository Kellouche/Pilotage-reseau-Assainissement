# -*- coding: utf-8 -*-
"""
================================================================================
Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
Auteur : Dr Abdelhakim KELLOUCHE
Date de création : 2026-04-20
Date de modification : 2026-11-09
Objet : Générateur PDF d'ordre de mission terrain et fiche réflexe de crise (BMS)
================================================================================
"""

import io
from datetime import datetime
from typing import Dict, Any, List, Optional
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable


def generer_pdf_ordre_mission_bms(
    simulation_data: Dict[str, Any],
    bms_info: Optional[Dict[str, Any]] = None,
    nom_bassin: Optional[str] = None
) -> bytes:
    """
    Génère un ordre de mission terrain officiel (PDF) pour les équipes d'astreinte de l'ONA
    en amont ou au cours d'un événement météo critique (bulletin météorologique spécial).
    Identifie la liste prioritaire des regards et nœuds du réseau à curer et sécuriser.
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=1.5 * cm,
        rightMargin=1.5 * cm,
        topMargin=1.5 * cm,
        bottomMargin=1.5 * cm,
        title="Ordre de mission terrain - Prévention inondation BMS"
    )

    styles = getSampleStyleSheet()

    # Styles typographiques conformes à la charte DrainPilot
    style_titre_haut = ParagraphStyle(
        'TitreHaut',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=10,
        leading=13,
        alignment=1,
        textColor=colors.HexColor('#0f172a')
    )

    style_bms_badge = ParagraphStyle(
        'BMSBadge',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=14,
        leading=18,
        alignment=1,
        textColor=colors.HexColor('#b45309')
    )

    style_section = ParagraphStyle(
        'SectionTitre',
        parent=styles['Heading2'],
        fontName='Helvetica-Bold',
        fontSize=11,
        leading=15,
        textColor=colors.HexColor('#0369a1'),
        spaceBefore=8,
        spaceAfter=4
    )

    style_corps = ParagraphStyle(
        'CorpsTexte',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=9,
        leading=13,
        textColor=colors.HexColor('#1e293b')
    )

    style_tableau = ParagraphStyle(
        'TableauTexte',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=8,
        leading=11,
        textColor=colors.HexColor('#0f172a')
    )

    style_tableau_bold = ParagraphStyle(
        'TableauTexteBold',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=8,
        leading=11,
        textColor=colors.HexColor('#0f172a')
    )

    story = []

    # 1. Entête République / ONA
    entete_text = (
        "<b>RÉPUBLIQUE ALGÉRIENNE DÉMOCRATIQUE ET POPULAIRE</b><br/>"
        "Ministère de l'Hydraulique — Office National de l'Assainissement (ONA)<br/>"
        "Direction de Zone Chélif — Centre d'Exploitation et d'Assainissement de Chlef<br/>"
        "<b>CELLULE DE VEILLE HYDRO-MÉTÉOROLOGIQUE ET GESTION DE CRISE</b>"
    )
    story.append(Paragraph(entete_text, style_titre_haut))
    story.append(Spacer(1, 0.3 * cm))
    story.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor('#0284c7'), spaceAfter=8))

    # Extraction des données BMS
    bms = bms_info or simulation_data.get("bms_info") or {}
    vigilance = str(bms.get("vigilance") or "orange").upper()
    cumul_mm = bms.get("cumul_mm") or 30.0
    heure_deb = bms.get("heure_debut") or "07:00"
    heure_fin = bms.get("heure_fin") or "21:00"
    duree_h = bms.get("duree_heures") or 14.0
    date_texte = bms.get("date_texte") or datetime.now().strftime("%d/%m/%Y")
    bassin = nom_bassin or simulation_data.get("meta", {}).get("bassin_nom") or "Bassin versant urbain"

    vig_color = colors.HexColor('#ea580c') if vigilance == "ORANGE" else (
        colors.HexColor('#dc2626') if vigilance == "ROUGE" else colors.HexColor('#ca8a04')
    )

    # 2. Titre de la mission
    titre_mission = f"ORDRE DE MISSION TERRAIN : CURAGE PRÉVENTIF & SÉCURISATION DU RÉSEAU"
    story.append(Paragraph(titre_mission, ParagraphStyle(
        'TitreMission',
        fontName='Helvetica-Bold',
        fontSize=12,
        alignment=1,
        textColor=colors.HexColor('#0f172a')
    )))
    story.append(Spacer(1, 0.2 * cm))

    # Encadré d'alerte météo BMS
    bms_alerte_html = (
        f"<b>ALERTE MÉTÉO SPÉCIALE (BMS ONM) — VIGILANCE {vigilance}</b><br/>"
        f"Validité : {date_texte} de <b>{heure_deb}</b> à <b>{heure_fin}</b> ({duree_h} h d'alerte) &bull; "
        f"Hauteur annoncée : <b>{cumul_mm} mm</b>"
    )
    data_encadre_bms = [[Paragraph(bms_alerte_html, ParagraphStyle('BMSAlert', fontName='Helvetica', fontSize=9, leading=13, textColor=vig_color, alignment=1))]]
    t_bms = Table(data_encadre_bms, colWidths=[18 * cm])
    t_bms.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#fff7ed') if vigilance == "ORANGE" else colors.HexColor('#fef2f2')),
        ('BOX', (0, 0), (-1, -1), 1.5, vig_color),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
    ]))
    story.append(t_bms)
    story.append(Spacer(1, 0.3 * cm))

    # 3. Synthèse des calculs prévisionnels SWMM 5.2
    story.append(Paragraph("1. Diagnostic hydraulique prévisionnel (Simulation SWMM 5.2)", style_section))
    peak_q = simulation_data.get("peak_outflow_m3s") or 0.0
    total_vol = simulation_data.get("total_outflow_m3") or 0.0
    flooded_count = simulation_data.get("flooded_nodes_count", 0)
    surcharged_count = simulation_data.get("surcharged_nodes_count", 0)

    synthese_html = (
        f"<b>Périmètre d'intervention :</b> {bassin}<br/>"
        f"<b>Débit de pointe simulé à l'exutoire :</b> {peak_q:.3f} m³/s &bull; "
        f"<b>Volume total estimé en sortie :</b> {total_vol:,.0f} m³<br/>"
        f"<b>Ouvrages vulnérables identifiés :</b> "
        f"<font color='#dc2626'><b>{flooded_count} regard(s) en débordement</b></font> &bull; "
        f"<font color='#ea580c'><b>{surcharged_count} regard(s) en charge hydraulique</b></font>."
    )
    story.append(Paragraph(synthese_html, style_corps))
    story.append(Spacer(1, 0.3 * cm))

    # 4. Liste priorisée des regards et ouvrages à curer
    story.append(Paragraph("2. Liste priorisée des regards critiques à curer et libérer avant le pic", style_section))

    node_results = simulation_data.get("node_results", {})
    flooded_nodes = simulation_data.get("flooded_nodes", [])

    # Construire la liste des regards critiques
    lignes_regards = [
        [
            Paragraph("<b>Identifiant regard</b>", style_tableau_bold),
            Paragraph("<b>Diagnostic SWMM</b>", style_tableau_bold),
            Paragraph("<b>Débit débord. max</b>", style_tableau_bold),
            Paragraph("<b>Priorité</b>", style_tableau_bold),
            Paragraph("<b>Action recommandée</b>", style_tableau_bold)
        ]
    ]

    # Priorité aux regards débordants, puis en charge
    candidats = []
    if flooded_nodes:
        for fn in flooded_nodes:
            if isinstance(fn, dict):
                candidats.append((
                    fn.get("node") or fn.get("name") or "Regard",
                    "Débordement actif",
                    f"{fn.get('peak_flood_flow_cms', 0.0):.3f} m³/s",
                    "P1 - Immédiat",
                    "Curage urgent, ouverture grille et dégagement amont"
                ))
            elif isinstance(fn, str):
                candidats.append((
                    fn,
                    "Débordement actif",
                    "--",
                    "P1 - Immédiat",
                    "Curage hydrocureur haute pression et sécurisation"
                ))

    # Ajouter les regards en charge si la liste est courte
    if len(candidats) < 8 and node_results:
        for nid, ninfo in node_results.items():
            if isinstance(ninfo, dict) and ninfo.get("status") == "surcharged":
                if not any(c[0] == nid for c in candidats):
                    candidats.append((
                        nid,
                        "Mise en charge",
                        "--",
                        "P2 - Vigilance",
                        "Nettoyage avaloir et vérification clapet"
                    ))
            if len(candidats) >= 12:
                break

    # Si aucun regard débordant (ex: réseau capacitif), consigne de vérification générale
    if not candidats:
        candidats.append((
            "Tous regards collecteurs",
            "Capacité nominale",
            "0.000 m³/s",
            "P3 - Routine",
            "Vérification des grilles d'avaloirs et exutoire principal"
        ))

    for item in candidats[:14]:  # limiter pour tenir sur la page
        p_color = colors.HexColor('#dc2626') if "P1" in item[3] else (
            colors.HexColor('#ea580c') if "P2" in item[3] else colors.HexColor('#16a34a')
        )
        lignes_regards.append([
            Paragraph(f"<b>{item[0]}</b>", style_tableau),
            Paragraph(item[1], style_tableau),
            Paragraph(item[2], style_tableau),
            Paragraph(f"<font color='{p_color.hexval()}'><b>{item[3]}</b></font>", style_tableau),
            Paragraph(item[4], style_tableau),
        ])

    table_nodes = Table(lignes_regards, colWidths=[3.2 * cm, 3.2 * cm, 2.6 * cm, 2.8 * cm, 6.2 * cm])
    table_nodes.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#f1f5f9')),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    story.append(table_nodes)
    story.append(Spacer(1, 0.4 * cm))

    # 5. Consignes de sécurité et moyens matériels
    story.append(Paragraph("3. Consignes opérationnelles d'intervention d'urgence", style_section))
    consignes_html = (
        "&bull; <b>Matériel mobilisé :</b> 1 camion hydrocureur combiné, 1 motopompe thermique d'épuisement (débit &ge; 100 m³/h), outillage de levage plaques.<br/>"
        "&bull; <b>Sécurité des agents :</b> Port obligatoire des EPI (gilets haute visibilité fluo, bottes de sécurité étanches, gants anti-coupure et harnais).<br/>"
        "&bull; <b>Signalisation urbaine :</b> Balisage réglementaire des regards ouverts ou des zones inondées à proximité des voies de circulation.<br/>"
        "&bull; <b>Coordination :</b> Rendre compte heure par heure au poste de commandement ONA et signaler tout bouchage majeur au service technique communal."
    )
    story.append(Paragraph(consignes_html, style_corps))
    story.append(Spacer(1, 0.6 * cm))

    # 6. Blocs de signature
    sig_data = [
        [
            Paragraph("<b>Le Chef de Centre d'Assainissement ONA :</b><br/><br/><br/><i>Visa et signature</i>", style_corps),
            Paragraph("<b>Le Chef d'Équipe d'Astreinte Terrain :</b><br/><br/><br/><i>Prise en charge et émargement</i>", style_corps)
        ]
    ]
    sig_table = Table(sig_data, colWidths=[9 * cm, 9 * cm])
    sig_table.setStyle(TableStyle([
        ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 14),
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#f8fafc')),
    ]))
    story.append(sig_table)

    doc.build(story)
    pdf_bytes = buffer.getvalue()
    buffer.close()
    return pdf_bytes
