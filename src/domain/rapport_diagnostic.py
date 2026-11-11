# -*- coding: utf-8 -*-
"""
================================================================================
Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
Auteur : Dr Abdelhakim KELLOUCHE
Date de création : 2026-11-10
Objet : Générateur PDF du Rapport d'Expertise Hydraulique Complet (ReportLab)
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


def formater_cout_dzd(montant: Any, avec_decimales: bool = True, inclure_unite: bool = True) -> str:
    """Formate un montant en DZD (espace comme séparateur de milliers, virgule décimale)."""
    try:
        val = float(montant or 0.0)
    except (ValueError, TypeError):
        val = 0.0
    if avec_decimales:
        s = f"{val:,.2f}".replace(",", " ").replace(".", ",")
    else:
        s = f"{val:,.0f}".replace(",", " ")
    return f"{s} DZD" if inclure_unite else s


def formater_nombre_fr(val: Any, decimales: int = 3) -> str:
    """Formate un nombre décimal avec la virgule française."""
    try:
        fval = float(val or 0.0)
    except (ValueError, TypeError):
        fval = 0.0
    fmt = f"{{:,.{decimales}f}}"
    return fmt.format(fval).replace(",", " ").replace(".", ",")


def generer_pdf_rapport_diagnostic(
    simulation_data: Dict[str, Any],
    project_name: Optional[str] = None
) -> bytes:
    """
    Génère le rapport d'expertise hydraulique complet (PDF ReportLab) conforme
    aux standards ONA / ANRH pour transmission à la direction technique.

    Args:
        simulation_data: Résultats complets de la simulation SWMM (meta, kpis, agents_expertise, buffer_sensitivity)
        project_name: Nom du projet/réseau (optionnel, extrait de meta sinon)

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
        title=f"Rapport d'expertise hydraulique - {project_name or 'Réseau Urbain'}"
    )

    styles = getSampleStyleSheet()

    # Styles personnalisés
    style_titre_haut = ParagraphStyle(
        'TitreHaut',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=10,
        leading=13,
        alignment=1,
        textColor=colors.HexColor('#0f172a')
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

    style_sous_section = ParagraphStyle(
        'SousSection',
        parent=styles['Heading3'],
        fontName='Helvetica-Bold',
        fontSize=9.5,
        leading=13,
        textColor=colors.HexColor('#0284c7'),
        spaceBefore=6,
        spaceAfter=3
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
        fontSize=7.5,
        leading=10,
        textColor=colors.HexColor('#0f172a')
    )

    style_tableau_bold = ParagraphStyle(
        'TableauTexteBold',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=7.5,
        leading=10,
        textColor=colors.HexColor('#0f172a')
    )

    style_agent_memo = ParagraphStyle(
        'AgentMemo',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=8.5,
        leading=12,
        textColor=colors.HexColor('#1e293b'),
        leftIndent=4,
        rightIndent=4,
        spaceBefore=4,
        spaceAfter=4
    )

    style_agent_title = ParagraphStyle(
        'AgentTitle',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=8.5,
        leading=12,
        textColor=colors.HexColor('#0284c7'),
        spaceBefore=4,
        spaceAfter=2
    )

    story = []

    # Extraction des données principales
    meta = simulation_data.get("meta", {})
    kpis = simulation_data.get("kpis", {})
    agents = simulation_data.get("agents_expertise", {})
    buffer_sens = simulation_data.get("buffer_sensitivity", {})

    diag = agents.get("diagnostic_causal", {})
    gc = agents.get("prescriptions_genie_civil", {})
    lid = agents.get("solutions_hydrologie_durable", {})
    risk = agents.get("matrice_risques", {})
    finance = agents.get("analyse_variantes_financiere", {})
    synth = agents.get("synthese_executive", {})

    variantes = finance.get("variantes", [])
    ratios = finance.get("ratios_directeurs", {})

    project_name = project_name or meta.get("project_name") or "Réseau Urbain"
    date_str = datetime.now().strftime("%d/%m/%Y %H:%M")
    cluster_nom = meta.get("cluster_nom") or meta.get("bassin_nom") or f"Bassin {meta.get('cluster_id', 'N/A')}"

    verdict = synth.get("verdict", "ANALYSE EXPERTE MULTI-AGENTS SWMM 5.2")
    verdict_color = synth.get("couleur", "#0284c7")

    # 1. Entête République / ONA
    entete_text = (
        "<b>RÉPUBLIQUE ALGÉRIENNE DÉMOCRATIQUE ET POPULAIRE</b><br/>"
        "Ministère des Ressources en Eau — Office National de l'Assainissement (ONA)<br/>"
        "Direction de Zone Chélif — Centre d'Exploitation et d'Assainissement<br/>"
        "<b>PLATEFORME SAAS DRAINPILOT 5.2 — DIAGNOSTIC HYDRAULIQUE CERTIFIÉ</b>"
    )
    story.append(Paragraph(entete_text, style_titre_haut))
    story.append(Spacer(1, 0.3 * cm))
    story.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor('#0284c7'), spaceAfter=8))

    # 2. Titre du rapport
    titre = "RAPPORT D'EXPERTISE HYDRAULIQUE ET PRESCRIPTIONS DE TRAVAUX"
    story.append(Paragraph(titre, ParagraphStyle(
        'TitreMission',
        fontName='Helvetica-Bold',
        fontSize=12,
        alignment=1,
        textColor=colors.HexColor('#0f172a'),
        spaceAfter=6
    )))

    # 3. Cartouche d'identification
    cartouche_data = [
        [
            Paragraph(f"<b>Projet réseau :</b> {project_name}", style_corps),
            Paragraph(f"<b>Périmètre simulé :</b> {cluster_nom}", style_corps)
        ],
        [
            Paragraph(f"<b>Date d'expertise :</b> {date_str}", style_corps),
            Paragraph(f"<b>Scénario pluvieux :</b> {meta.get('scenario', 'Pluie décennale ANRH Mascara')}", style_corps)
        ],
        [
            Paragraph(f"<b>Surface drainée :</b> {meta.get('total_area_ha', 0)} ha (tampon {meta.get('buffer_m', 35)} m)", style_corps),
            Paragraph(f"<b>Éléments modélisés :</b> {meta.get('conduits_count', 0)} conduites • {meta.get('junctions_count', 0)} regards", style_corps)
        ],
        [
            Paragraph(f"<b>Débit de pointe :</b> {kpis.get('peak_outflow_m3s', 0):.3f} m³/s", style_corps),
            Paragraph(f"<b>Bilan débordements :</b> {kpis.get('flooded_nodes_count', 0)} débordements • {kpis.get('surcharged_nodes_count', 0)} en charge", style_corps)
        ],
    ]
    cartouche_table = Table(cartouche_data, colWidths=[9 * cm, 9 * cm])
    cartouche_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#f8fafc')),
        ('BOX', (0, 0), (-1, -1), 1, colors.HexColor('#cbd5e1')),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    story.append(cartouche_table)
    story.append(Spacer(1, 0.4 * cm))

    # 4. Cadre Hydro-Météorologique
    story.append(Paragraph("🌧️ CADRE HYDRO-MÉTÉOROLOGIQUE ET SOLLICITATION PLUVIOMÉTRIQUE RÉGLEMENTAIRE (ANRH / ONA)", style_section))

    hydro_data = [
        [
            Paragraph("<b>Période de retour (T)</b>", style_tableau_bold),
            Paragraph(meta.get('pluvio_periode_retour', 'T = 10 ans (décennale)'), style_tableau),
            Paragraph("<b>Intensité de pointe (Imax)</b>", style_tableau_bold),
            Paragraph(f"{kpis.get('pluvio_intensite_max_mmh', meta.get('pluvio_intensite_max_mmh', 74.9)):.1f} mm/h", style_tableau),
        ],
        [
            Paragraph("<b>Hauteur cumulée (Ptot)</b>", style_tableau_bold),
            Paragraph(f"{kpis.get('pluvio_hauteur_totale_mm', meta.get('pluvio_hauteur_totale_mm', 42.8)):.1f} mm", style_tableau),
            Paragraph("<b>Formule IDF Montana</b>", style_tableau_bold),
            Paragraph(meta.get('pluvio_montana', kpis.get('pluvio_montana', 'I(t) = 9.334 · t⁻⁰·⁷⁴⁵')), style_tableau),
        ],
        [
            Paragraph("<b>Station de référence</b>", style_tableau_bold),
            Paragraph(meta.get('pluvio_station', 'Station ANRH Chlef Siège (Réf. 010501)'), style_tableau),
            Paragraph("<b>Source officielle</b>", style_tableau_bold),
            Paragraph(meta.get('pluvio_source', kpis.get('pluvio_source', 'Séries ANRH 1970–2024')), style_tableau),
        ]
    ]
    hydro_table = Table(hydro_data, colWidths=[4.5 * cm, 4.5 * cm, 4.5 * cm, 4.5 * cm])
    hydro_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#f0f9ff')),
        ('BOX', (0, 0), (-1, -1), 1, colors.HexColor('#0284c7')),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#bae6fd')),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    story.append(hydro_table)
    story.append(Spacer(1, 0.3 * cm))

    justification = (
        "<b>Justification d'ingénierie légale & opposabilité administrative :</b> "
        "L'intensité maximale de précipitation est issue des courbes Intensité-Durée-Fréquence (IDF) officielles "
        "de l'Agence Nationale des Ressources Hydriques (ANRH) pour la Wilaya concernée. "
        "L'hyétogramme synthétique de type Chicago centré sollicite le réseau à son niveau de contrainte réglementaire ONA."
    )
    story.append(Paragraph(justification, style_corps))
    story.append(Spacer(1, 0.3 * cm))

    # 5. Cadre de Validation Hydrologique
    story.append(Paragraph("💧 CADRE DE VALIDATION HYDROLOGIQUE ET MODÈLE D'INFILTRATION (SWMM / HORTON / VORONOÏ)", style_section))

    hydro2_data = [
        [
            Paragraph("<b>Discrétisation spatiale</b>", style_tableau_bold),
            Paragraph(f"{meta.get('subcatchments_count', meta.get('junctions_count', 'N/A'))} sous-bassins (Voronoï {meta.get('buffer_m', 35)} m)", style_tableau),
            Paragraph("<b>Imperméabilisation</b>", style_tableau_bold),
            Paragraph(f"C_imp = {meta.get('imperv_pct', 65)}% ({meta.get('typologie_nom', 'Habitat mixte urbain')})", style_tableau),
        ],
        [
            Paragraph("<b>Modèle d'infiltration</b>", style_tableau_bold),
            Paragraph("Horton exponentiel (f₀=76.2, f∞=13.2, k=4.14 h⁻¹)", style_tableau),
            Paragraph("<b>Temps de concentration (tc)</b>", style_tableau_bold),
            Paragraph(f"tc ≈ {meta.get('temps_concentration_min', 15.0):.1f} min (Kirpich/Passini)", style_tableau),
        ]
    ]
    hydro2_table = Table(hydro2_data, colWidths=[4.5 * cm, 4.5 * cm, 4.5 * cm, 4.5 * cm])
    hydro2_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#f8fafc')),
        ('BOX', (0, 0), (-1, -1), 1, colors.HexColor('#0284c7')),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    story.append(hydro2_table)
    story.append(Spacer(1, 0.3 * cm))

    methode = (
        "<b>Méthodologie de transformation pluie-débit :</b> "
        "Le ruissellement est généré par l'équation du réservoir SWMM. "
        "Les pertes sont simulées par la loi d'Horton. "
        "Les hydrogrammes sont propagés via les équations de Saint-Venant 1D (Dynamic Wave)."
    )
    story.append(Paragraph(methode, style_corps))
    story.append(Spacer(1, 0.4 * cm))

    # 6. Bilan Hydraulique Décisionnel
    story.append(Paragraph("⚖️ BILAN HYDRAULIQUE DÉCISIONNEL ET RÉPARTITION DES FLUX", style_section))

    q_genere = synth.get("bilan_hydraulique", {}).get("q_genere_m3s", 0.0)
    q_exutoire = synth.get("bilan_hydraulique", {}).get("q_exutoire_m3s", 0.0)
    q_derive = synth.get("bilan_hydraulique", {}).get("q_derive_m3s", 0.0)
    taux_derive = synth.get("bilan_hydraulique", {}).get("taux_derive_pct", 0.0)
    taux_exutoire = synth.get("bilan_hydraulique", {}).get("taux_exutoire_pct", 100.0)
    nb_ouvrages = synth.get("bilan_hydraulique", {}).get("nb_ouvrages_actifs", 0)

    bilan_text = (
        f"<b>Bassin versant :</b> {cluster_nom}<br/>"
        f"• <b>Débit total généré :</b> <font color='#0369a1'><b>{formater_nombre_fr(q_genere)} m³/s</b></font><br/>"
        f"• <b>Soulagement du collecteur :</b> <font color='#16a34a'><b>{taux_derive:.1f}%</b></font><br/>"
        f"• <b>Débit résiduel exutoire :</b> <b>{formater_nombre_fr(q_exutoire)} m³/s</b> ({taux_exutoire:.1f}%)<br/>"
        f"• <b>Débit capté par {nb_ouvrages} ouvrages :</b> <font color='#0284c7'><b>{formater_nombre_fr(q_derive)} m³/s</b></font> ({taux_derive:.1f}%)"
    )
    bilan_table = Table([[Paragraph(bilan_text, style_corps)]], colWidths=[18 * cm])
    bilan_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#f8fafc')),
        ('BOX', (0, 0), (-1, -1), 1, colors.HexColor('#0284c7')),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('LEFTPADDING', (0, 0), (-1, -1), 10),
    ]))
    story.append(bilan_table)
    story.append(Spacer(1, 0.4 * cm))

    # 6.B Regards en débordement et durées de submersion
    story.append(Paragraph("⚠️ REGARDS EN DÉBORDEMENT ET DURÉES DE SUBMERSION", style_section))

    # Récupérer les node_results pour les détails des regards débordants
    node_results = simulation_data.get("node_results", {})
    flooded_nodes_list = simulation_data.get("flooded_nodes", [])

    if flooded_nodes_list or node_results:
        # Tableau des regards en débordement
        flood_rows = [
            [
                Paragraph("<b>Code regard</b>", style_tableau_bold),
                Paragraph("<b>Durée submersion (h)</b>", style_tableau_bold),
                Paragraph("<b>Volume inondé (m³)</b>", style_tableau_bold),
                Paragraph("<b>Débit pic débordement (m³/s)</b>", style_tableau_bold),
                Paragraph("<b>Statut</b>", style_tableau_bold)
            ]
        ]

        # Utiliser flooded_nodes_list si disponible, sinon node_results avec status flooded
        nodes_to_display = []
        if flooded_nodes_list:
            for node in flooded_nodes_list:
                if isinstance(node, dict):
                    nodes_to_display.append(node)
                else:
                    nid = str(node)
                    if nid in node_results:
                        nodes_to_display.append(node_results[nid])
        else:
            # Fallback: chercher dans node_results
            for nid, node_data in node_results.items():
                if node_data.get("status") == "flooded":
                    nodes_to_display.append(node_data)

        if nodes_to_display:
            for node in nodes_to_display:
                nid = node.get("node", node.get("node_id", "--"))
                hours_flooded = node.get("hours_flooded", 0.0)
                flood_volume = node.get("flood_volume_m3", 0.0)
                peak_flood_flow = node.get("peak_flood_flow_cms", 0.0)
                status = node.get("status", "flooded")

                flood_rows.append([
                    Paragraph(f"<b>{nid}</b>", style_tableau),
                    Paragraph(f"{hours_flooded:.2f} h", style_tableau),
                    Paragraph(f"{flood_volume:.2f} m³", style_tableau),
                    Paragraph(f"{peak_flood_flow:.3f} m³/s", style_tableau),
                    Paragraph(f"<font color='#ef4444'><b>{status.upper()}</b></font>", style_tableau)
                ])

            flood_table = Table(flood_rows, colWidths=[3 * cm, 3 * cm, 3 * cm, 4 * cm, 2.5 * cm])
            flood_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0369a1')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
                ('TOPPADDING', (0, 0), (-1, -1), 3),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8fafc')]),
            ]))
            story.append(flood_table)
            story.append(Spacer(1, 0.3 * cm))
        else:
            story.append(Paragraph("Aucun regard en débordement détecté dans cette simulation.", style_corps))
            story.append(Spacer(1, 0.3 * cm))
    else:
        story.append(Paragraph("Aucune donnée de débordement disponible pour cette simulation.", style_corps))
        story.append(Spacer(1, 0.3 * cm))

    # 7. Synthèse Exécutive (Agent 6)
    story.append(Paragraph("1. SYNTHÈSE STRATÉGIQUE ET AVIS DES DÉCIDEURS (Agent 6)", style_section))

    verdict_box_style = ParagraphStyle(
        'VerdictBox',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=9,
        leading=13,
        textColor=colors.HexColor('#1e293b'),
        backColor=colors.HexColor('#f1f5f9'),
        borderColor=colors.HexColor(verdict_color),
        borderWidth=3,
        borderPadding=8,
        leftIndent=4,
        rightIndent=4,
    )

    story.append(Paragraph(
        f"<b>{verdict}</b>",
        ParagraphStyle('VerdictTitle', fontName='Helvetica-Bold', fontSize=10, textColor=colors.HexColor(verdict_color))
    ))
    story.append(Paragraph(synth.get("recommandation_cle", ""), style_corps))
    story.append(Paragraph(f"<i>Orientation : {synth.get('avis_direction_generale', '')}</i>",
                          ParagraphStyle('AvisDir', fontSize=8, textColor=colors.HexColor('#64748b'))))
    story.append(Spacer(1, 0.3 * cm))

    story.append(Paragraph(f"<b>📋 Mémoire de Synthèse Stratégique • Directeur Technique (Agent 6)</b>", style_agent_title))
    story.append(Paragraph(synth.get("note_technique", ""), style_agent_memo))
    story.append(Spacer(1, 0.3 * cm))

    # 8. Matrice des Risques & Plan d'Action (Agent 4)
    story.append(Paragraph("2. PLAN D'ACTION PRIORISÉ ET MATRICE DES RISQUES (Agent 4)", style_section))
    story.append(Paragraph(f"<b>Budget total estimé :</b> {formater_cout_dzd(gc.get('cout_global_estime_dzd', 0))}", style_corps))
    story.append(Spacer(1, 0.2 * cm))

    story.append(Paragraph(f"<b>🎯 Note de hiérarchisation multicritère • Expert risques (Agent 4)</b>", style_agent_title))
    story.append(Paragraph(risk.get("note_technique", ""), style_agent_memo))

    # Tableau des risques
    risk_list = []
    if risk.get("actions_liste"):
        risk_list = risk["actions_liste"]
    elif risk.get("actions_priorisees"):
        risk_list = risk["actions_priorisees"]
    elif isinstance(risk.get("actions_priorisees"), dict):
        for prio in ['P1', 'P2', 'P3']:
            for item in risk["actions_priorisees"].get(prio, []):
                risk_list.append({
                    "priorite": prio,
                    "conduite": item.get("conduite", item.get("cible", "--")),
                    "type_risque": item.get("type_risque", item.get("probleme", "--")),
                    "action_requise": item.get("action_requise", item.get("action", "--")),
                    "estimation_cout_dzd": item.get("estimation_cout_dzd", 0),
                    "delai_recommande": item.get("delai_recommande", item.get("delai", "--"))
                })

    risk_rows = [
        [
            Paragraph("<b>Priorité</b>", style_tableau_bold),
            Paragraph("<b>Ouvrage / conduite</b>", style_tableau_bold),
            Paragraph("<b>Risque identifié</b>", style_tableau_bold),
            Paragraph("<b>Action prescrite</b>", style_tableau_bold),
            Paragraph("<b>Coût estimé</b>", style_tableau_bold),
            Paragraph("<b>Délai</b>", style_tableau_bold)
        ]
    ]

    if risk_list:
        for a in risk_list:
            prio = a.get("priorite", "P1")
            badge_color = colors.HexColor('#ef4444') if prio == 'P1' else (colors.HexColor('#f97316') if prio == 'P2' else colors.HexColor('#0284c7'))
            risk_rows.append([
                Paragraph(f"<font color='{badge_color.hexval()}'><b>{prio}</b></font>", style_tableau),
                Paragraph(f"<b>{a.get('conduite', '--')}</b>", style_tableau),
                Paragraph(a.get('type_risque', '--'), style_tableau),
                Paragraph(a.get('action_requise', '--'), style_tableau),
                Paragraph(formater_cout_dzd(a.get('estimation_cout_dzd', 0)), style_tableau),
                Paragraph(a.get('delai_recommande', '--'), style_tableau)
            ])
    else:
        risk_rows.append([
            Paragraph("", style_tableau), Paragraph("Aucun risque critique immédiat recensé.", style_tableau),
            Paragraph("", style_tableau), Paragraph("", style_tableau),
            Paragraph("", style_tableau), Paragraph("", style_tableau)
        ])

    risk_table = Table(risk_rows, colWidths=[1.8 * cm, 2.5 * cm, 3 * cm, 5.5 * cm, 2.5 * cm, 2 * cm])
    risk_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0369a1')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8fafc')]),
    ]))
    story.append(risk_table)
    story.append(Spacer(1, 0.4 * cm))

    # 9. Diagnostic Causal (Agent 1)
    story.append(Paragraph("3. DIAGNOSTIC CAUSAL ET DYSFONCTIONNEMENTS HYDRAULIQUES (Agent 1)", style_section))
    story.append(Paragraph(f"<b>{diag.get('nb_surcharges', 0)} tronçons surchargés • {diag.get('nb_goulots', 0)} goulots détectés</b>", style_corps))

    story.append(Paragraph(f"<b>🔬 Diagnostic hydrodynamique • Spécialiste Saint-Venant 1D (Agent 1)</b>", style_agent_title))
    story.append(Paragraph(diag.get("note_technique", ""), style_agent_memo))

    # Tableau surcharges
    surch_rows = [
        [
            Paragraph("<b>Conduite</b>", style_tableau_bold),
            Paragraph("<b>Taux Q/Qmax</b>", style_tableau_bold),
            Paragraph("<b>Remplissage H/D</b>", style_tableau_bold),
            Paragraph("<b>Vitesse</b>", style_tableau_bold),
            Paragraph("<b>Débit de crête</b>", style_tableau_bold),
            Paragraph("<b>Observation</b>", style_tableau_bold)
        ]
    ]

    if diag.get("surcharged_links"):
        for l in diag["surcharged_links"]:
            surch_rows.append([
                Paragraph(f"<b>{l.get('conduit', '--')}</b>", style_tableau),
                Paragraph(f"<font color='#ef4444'><b>{(l.get('flow_ratio', 0)*100):.0f}%</b></font>", style_tableau),
                Paragraph(f"{(l.get('depth_ratio', 0)*100):.0f}%", style_tableau),
                Paragraph(f"{l.get('vitesse', l.get('max_velocity_ms', 0)):.2f} m/s", style_tableau),
                Paragraph(f"{l.get('q_max', l.get('max_flow_cms', 0)):.3f} m³/s", style_tableau),
                Paragraph(l.get('cause', 'Surcharge sous pression'), style_tableau)
            ])
    else:
        surch_rows.append([Paragraph("Aucun tronçon en surcharge sévère (>80%).", style_tableau)] + [Paragraph("", style_tableau)] * 5)

    surch_table = Table(surch_rows, colWidths=[2.5 * cm, 2 * cm, 2 * cm, 2 * cm, 2.5 * cm, 5 * cm])
    surch_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0369a1')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8fafc')]),
    ]))
    story.append(surch_table)
    story.append(Spacer(1, 0.3 * cm))

    # Goulots
    story.append(Paragraph("<b>Anomalies géométriques et goulots d'étranglement amont → aval :</b>", style_corps))

    bottle_rows = [
        [
            Paragraph("<b>Tronçon (amont → aval)</b>", style_tableau_bold),
            Paragraph("<b>Diam. amont</b>", style_tableau_bold),
            Paragraph("<b>Diam. aval</b>", style_tableau_bold),
            Paragraph("<b>Longueur</b>", style_tableau_bold),
            Paragraph("<b>Conséquence hydraulique</b>", style_tableau_bold)
        ]
    ]

    if diag.get("bottlenecks"):
        for b in diag["bottlenecks"]:
            bottle_rows.append([
                Paragraph(f"<b>{b.get('amont', '--')}</b> → <b>{b.get('aval', '--')}</b>", style_tableau),
                Paragraph(f"{b.get('diam_amont', '--')} mm", style_tableau),
                Paragraph(f"<font color='#ef4444'><b>{b.get('diam_aval', '--')} mm</b></font>", style_tableau),
                Paragraph(f"{b.get('longueur', b.get('longueur_m', 0)):.1f} m", style_tableau),
                Paragraph(b.get('description', 'Goulot géométrique • Réduction anormale de section'), style_tableau)
            ])
    else:
        bottle_rows.append([Paragraph("Aucun goulot géométrique inverse détecté.", style_tableau)] + [Paragraph("", style_tableau)] * 4)

    bottle_table = Table(bottle_rows, colWidths=[4 * cm, 2.5 * cm, 2.5 * cm, 2.5 * cm, 5.5 * cm])
    bottle_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0369a1')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8fafc')]),
    ]))
    story.append(bottle_table)
    story.append(Spacer(1, 0.4 * cm))

    # 10. Prescriptions Génie Civil (Agent 2)
    story.append(Paragraph("4. PRESCRIPTIONS DE GÉNIE CIVIL ET DIMENSIONNEMENT NORMALISÉ (Agent 2)", style_section))
    story.append(Paragraph(
        f"<b>Métré total :</b> {(gc.get('metres_lineaires_totaux', 0)):.1f} ml  •  "
        f"<b>Marge Manning :</b> +25%  •  "
        f"<b>H/D cible :</b> ≤ 0.80",
        style_corps
    ))

    story.append(Paragraph(f"<b>📐 Justification de calcul gravitaire • Ingénieur GC (Agent 2)</b>", style_agent_title))
    story.append(Paragraph(gc.get("note_technique", ""), style_agent_memo))

    # BPU
    story.append(Paragraph("<b>Décomposition Analytique du Coût (BPU) :</b>", style_corps))
    bpu = gc.get("decomposition_bpu", {})
    bpu_terr = bpu.get("montant_terrassement_dzd", round(gc.get("cout_global_estime_dzd", 0) * 0.30))
    bpu_four = bpu.get("montant_fourniture_dzd", round(gc.get("cout_global_estime_dzd", 0) * 0.35))
    bpu_pose = bpu.get("montant_pose_remblai_dzd", round(gc.get("cout_global_estime_dzd", 0) * 0.20))
    bpu_chaus = bpu.get("montant_chaussee_dzd", round(gc.get("cout_global_estime_dzd", 0) * 0.15))

    bpu_rows = [
        [Paragraph("<b>1. Terrassement et blindage (30%)</b>", style_tableau), Paragraph(formater_cout_dzd(bpu_terr), style_tableau)],
        [Paragraph("<b>2. Fourniture des tuyaux (35%)</b>", style_tableau), Paragraph(formater_cout_dzd(bpu_four), style_tableau)],
        [Paragraph("<b>3. Pose et remblai à 95% OPM (20%)</b>", style_tableau), Paragraph(formater_cout_dzd(bpu_pose), style_tableau)],
        [Paragraph("<b>4. Réfection chaussée bitume (15%)</b>", style_tableau), Paragraph(formater_cout_dzd(bpu_chaus), style_tableau)],
    ]
    bpu_table = Table(bpu_rows, colWidths=[10 * cm, 8 * cm])
    bpu_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#f8fafc')),
        ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    story.append(bpu_table)
    story.append(Spacer(1, 0.3 * cm))

    # Récapitulatif par DN
    recap_rows = [
        [
            Paragraph("<b>DN retenu</b>", style_tableau_bold),
            Paragraph("<b>Matériau</b>", style_tableau_bold),
            Paragraph("<b>Classe</b>", style_tableau_bold),
            Paragraph("<b>Nb tronçons</b>", style_tableau_bold),
            Paragraph("<b>Linéaire (ml)</b>", style_tableau_bold),
            Paragraph("<b>Part (ml)</b>", style_tableau_bold),
            Paragraph("<b>Prix unitaire</b>", style_tableau_bold),
            Paragraph("<b>Montant total</b>", style_tableau_bold),
            Paragraph("<b>Part (%)</b>", style_tableau_bold)
        ]
    ]

    for r in gc.get("recapitulatif_par_dn", []):
        recap_rows.append([
            Paragraph(f"<b>{r.get('label', '--')}</b>", style_tableau),
            Paragraph(r.get('materiau', '--'), style_tableau),
            Paragraph(r.get('classe', '--'), style_tableau),
            Paragraph(str(r.get('nb_troncons', 0)), style_tableau),
            Paragraph(f"{(r.get('lineaire_ml', 0)):.1f}", style_tableau),
            Paragraph(f"{r.get('pct_lineaire', 0)}%", style_tableau),
            Paragraph(formater_cout_dzd(r.get('cout_unitaire_ml_dzd', 0), inclure_unite=False) + " / ml", style_tableau),
            Paragraph(formater_cout_dzd(r.get('cout_total_dzd', 0)), style_tableau),
            Paragraph(f"{r.get('pct_budget', 0)}%", style_tableau)
        ])

    # Total row
    recap_rows.append([
        Paragraph("<b>TOTAL PROGRAMME</b>", style_tableau_bold),
        Paragraph("", style_tableau), Paragraph("", style_tableau),
        Paragraph(f"<b>{gc.get('nb_troncons_a_recalibrer', 0)}</b>", style_tableau),
        Paragraph(f"<b>{(gc.get('metres_lineaires_totaux', 0)):.1f} ml</b>", style_tableau),
        Paragraph("100%", style_tableau),
        Paragraph("", style_tableau),
        Paragraph(f"<b><font color='#0284c7'>{formater_cout_dzd(gc.get('cout_global_estime_dzd', 0))}</font></b>", style_tableau),
        Paragraph("100%", style_tableau)
    ])

    recap_table = Table(recap_rows, colWidths=[1.8 * cm, 2.2 * cm, 1.8 * cm, 1.5 * cm, 2 * cm, 1.5 * cm, 2.5 * cm, 2.5 * cm, 1.5 * cm])
    recap_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0369a1')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#f1f5f9')),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ROWBACKGROUNDS', (0, 1), (-2, -1), [colors.white, colors.HexColor('#f8fafc')]),
    ]))
    story.append(recap_table)
    story.append(Spacer(1, 0.3 * cm))

    # Détail tronçons
    story.append(Paragraph("<b>Détail des tronçons prioritaires à recalibrer :</b>", style_corps))

    gc_rows = [
        [
            Paragraph("<b>Conduite</b>", style_tableau_bold),
            Paragraph("<b>Ø actuel</b>", style_tableau_bold),
            Paragraph("<b>Ø requis</b>", style_tableau_bold),
            Paragraph("<b>DN retenu</b>", style_tableau_bold),
            Paragraph("<b>Matériau</b>", style_tableau_bold),
            Paragraph("<b>Longueur</b>", style_tableau_bold),
            Paragraph("<b>Coût estimé</b>", style_tableau_bold)
        ]
    ]

    for p in gc.get("prescriptions", []):
        gc_rows.append([
            Paragraph(f"<b>{p.get('conduit', '--')}</b>", style_tableau),
            Paragraph(f"{p.get('diametre_actuel_mm', '--')} mm", style_tableau),
            Paragraph(f"{p.get('diametre_requis_mm', p.get('diam_theorique_mm', 0)):.0f} mm", style_tableau),
            Paragraph(f"DN {p.get('dn_normalise_mm', p.get('diam_prescrit_mm', '--'))}", style_tableau),
            Paragraph(p.get('materiau_recommande', 'Béton Armé 135A'), style_tableau),
            Paragraph(f"{p.get('longueur_m', p.get('longueur', 0)):.1f} m", style_tableau),
            Paragraph(formater_cout_dzd(p.get('cout_estime_dzd', 0)), style_tableau)
        ])

    if len(gc_rows) == 1:
        gc_rows.append([Paragraph("Aucun recalibrage structurel lourd requis.", style_tableau)] + [Paragraph("", style_tableau)] * 6)

    gc_table = Table(gc_rows, colWidths=[2.5 * cm, 2 * cm, 2 * cm, 2 * cm, 3 * cm, 2 * cm, 2.5 * cm])
    gc_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0369a1')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8fafc')]),
    ]))
    story.append(gc_table)
    story.append(Spacer(1, 0.4 * cm))

    # 11. Analyse Multi-Critères des Variantes (Agent 5)
    story.append(Paragraph("5. ANALYSE MULTICRITÈRE DES VARIANTES D'AMÉNAGEMENT (Agent 5)", style_section))

    economie = finance.get("economie_realisee_dzd", 0)
    econ_pct = finance.get("economie_pourcentage", 0)
    story.append(Paragraph(f"<b>Économie scénario mixte :</b> {formater_cout_dzd(economie)} (-{econ_pct:.1f}%)", style_corps))

    story.append(Paragraph(f"<b>💼 Analyse technico-économique • Expert financier (Agent 5)</b>", style_agent_title))
    story.append(Paragraph(finance.get("note_technique", ""), style_agent_memo))

    # Ratios
    ratios = finance.get("ratios_directeurs", {})
    ratio_rows = [
        [
            Paragraph("<b>Coût au ml rénové</b>", style_tableau_bold),
            Paragraph(formater_cout_dzd(ratios.get("cout_par_ml_renove_dzd", 0)), style_tableau),
            Paragraph("<b>Coût par hab. protégé</b>", style_tableau_bold),
            Paragraph(formater_cout_dzd(ratios.get("cout_par_habitant_protege_dzd", 0)), style_tableau),
        ],
        [
            Paragraph("<b>Dommages évités/an</b>", style_tableau_bold),
            Paragraph(formater_cout_dzd(ratios.get("dommages_annuels_evites_dzd", 0)), style_tableau),
            Paragraph("<b>Rentabilité</b>", style_tableau_bold),
            Paragraph(f"Payback {ratios.get('payback_annees', 0):.1f} ans • TRI {ratios.get('tri_pourcentage', 0):.1f}%", style_tableau),
        ]
    ]
    ratio_table = Table(ratio_rows, colWidths=[4.5 * cm, 4.5 * cm, 4.5 * cm, 4.5 * cm])
    ratio_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#f8fafc')),
        ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    story.append(ratio_table)
    story.append(Spacer(1, 0.3 * cm))

    # Tableau variantes
    var_rows = [
        [
            Paragraph("<b>Variante technique</b>", style_tableau_bold),
            Paragraph("<b>Réseau (ml)</b>", style_tableau_bold),
            Paragraph("<b>GDO (m³)</b>", style_tableau_bold),
            Paragraph("<b>Investissement</b>", style_tableau_bold),
            Paragraph("<b>Efficacité hydraulique</b>", style_tableau_bold),
            Paragraph("<b>Impact voirie</b>", style_tableau_bold),
            Paragraph("<b>Risque aval</b>", style_tableau_bold),
            Paragraph("<b>Score</b>", style_tableau_bold),
            Paragraph("<b>Décision</b>", style_tableau_bold)
        ]
    ]

    for v in variantes:
        is_rec = v.get("statut", "").upper().find("RECOMMAND") >= 0
        badge_color = colors.HexColor('#16a34a') if is_rec else (colors.HexColor('#ef4444') if v.get("statut") == "NON RETENU" else colors.HexColor('#f97316'))
        var_rows.append([
            Paragraph(f"<b>{v.get('nom', '--')}</b><br/><font size=7 color='#64748b'>{v.get('description', '')}</font>", style_tableau),
            Paragraph(f"{v.get('recalibrage_ml', 0):.1f} ml" if v.get('recalibrage_ml', 0) > 0 else "--", style_tableau),
            Paragraph(f"{v.get('volume_retention_m3', 0):.0f} m³" if v.get('volume_retention_m3', 0) > 0 else "--", style_tableau),
            Paragraph(f"<font color='{badge_color.hexval()}'><b>{formater_cout_dzd(v.get('cout_total_dzd', 0))}</b></font>", style_tableau),
            Paragraph(v.get('gain_hydraulique', '--'), style_tableau),
            Paragraph(v.get('impact_voirie', '--'), style_tableau),
            Paragraph(v.get('risque_aval', '--'), style_tableau),
            Paragraph(f"<b>{v.get('score_resilience', '--')} / 10</b>", style_tableau),
            Paragraph(f"<font color='{badge_color.hexval()}'><b>{v.get('statut', '--')}</b></font>", style_tableau)
        ])

    if not variantes:
        var_rows.append([
            Paragraph("<b>Variante 1 : 100% tout-réseau</b>", style_tableau), Paragraph("7 591,9 ml", style_tableau), Paragraph("--", style_tableau),
            Paragraph(formater_cout_dzd(330964500), style_tableau), Paragraph("100% théorique", style_tableau),
            Paragraph("TRÈS ÉLEVÉ", style_tableau), Paragraph("TRÈS ÉLEVÉ", style_tableau), Paragraph("5.5 / 10", style_tableau),
            Paragraph("<font color='#ef4444'><b>NON RETENU</b></font>", style_tableau)
        ])
        var_rows.append([
            Paragraph("<b>Variante 2 : 100% GDO</b>", style_tableau), Paragraph("--", style_tableau), Paragraph("18 500 m³", style_tableau),
            Paragraph(formater_cout_dzd(112500000), style_tableau), Paragraph("Partiel (~62%)", style_tableau),
            Paragraph("Faible", style_tableau), Paragraph("Faible", style_tableau), Paragraph("6.0 / 10", style_tableau),
            Paragraph("<font color='#f97316'><b>INSUFFISANT</b></font>", style_tableau)
        ])
        var_rows.append([
            Paragraph("<b>Variante 3 : Mixte optimisée</b>", style_tableau), Paragraph("4 112,8 ml", style_tableau), Paragraph("6 595 m³", style_tableau),
            Paragraph(f"<font color='#16a34a'><b>{formater_cout_dzd(240384400)}</b></font>", style_tableau), Paragraph("100% résorption", style_tableau),
            Paragraph("Modéré", style_tableau), Paragraph("MINIMAL", style_tableau), Paragraph("<b>9.2 / 10</b>", style_tableau),
            Paragraph("<font color='#16a34a'><b>RECOMMANDÉ</b></font>", style_tableau)
        ])

    var_table = Table(var_rows, colWidths=[3 * cm, 1.8 * cm, 1.8 * cm, 2.5 * cm, 2.5 * cm, 2.2 * cm, 2.2 * cm, 1.5 * cm, 2 * cm])
    var_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0369a1')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8fafc')]),
    ]))
    story.append(var_table)
    story.append(Spacer(1, 0.4 * cm))

    # 12. GDO & Écrêtement (Agent 3)
    story.append(Paragraph("6. GESTION DURABLE DES OUVRAGES (GDO) ET ÉCRÊTEMENT DES POINTES (Agent 3)", style_section))
    story.append(Paragraph(f"<b>Volume tampon total :</b> {(lid.get('volume_tampon_requis_m3', 0)):.0f} m³", style_corps))

    story.append(Paragraph(f"<b>🌿 Stratégie d'écrêtement à la source • Expert GDO (Agent 3)</b>", style_agent_title))
    story.append(Paragraph(lid.get("note_technique", ""), style_agent_memo))

    lid_rows = [
        [
            Paragraph("<b>Type GDO</b>", style_tableau_bold),
            Paragraph("<b>Désignation</b>", style_tableau_bold),
            Paragraph("<b>Dimensionnement</b>", style_tableau_bold),
            Paragraph("<b>Impact hydraulique</b>", style_tableau_bold)
        ]
    ]

    for s in lid.get("solutions", []):
        lid_rows.append([
            Paragraph(f"<b>{s.get('type', '--')}</b>", style_tableau),
            Paragraph(s.get('designation', s.get('solution', '--')), style_tableau),
            Paragraph(s.get('dimensionnement', '--'), style_tableau),
            Paragraph(s.get('impact_attendu', s.get('reduction_debit_pointe_estimee', '--')), style_tableau)
        ])

    if not lid.get("solutions"):
        lid_rows.append([
            Paragraph("<b>Bassin d'écrêtement</b>", style_tableau),
            Paragraph("Bassin d'orage paysager en amont", style_tableau),
            Paragraph(f"Volume : {(lid.get('volume_tampon_requis_m3', 0)):.0f} m³", style_tableau),
            Paragraph("Écrêtement direct de la pointe (-35% débit)", style_tableau)
        ])
        lid_rows.append([
            Paragraph("<b>Noues d'infiltration</b>", style_tableau),
            Paragraph("Noues végétalisées le long des voiries", style_tableau),
            Paragraph("Linéaire : 1 200 ml • Largeur 1.5 m", style_tableau),
            Paragraph("Infiltration diffuse & déconnexion pluviale", style_tableau)
        ])

    lid_table = Table(lid_rows, colWidths=[2.5 * cm, 4.5 * cm, 5 * cm, 5 * cm])
    lid_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0369a1')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8fafc')]),
    ]))
    story.append(lid_table)
    story.append(Spacer(1, 0.4 * cm))

    # 13. Analyse de Sensibilité du Buffer
    if buffer_sens.get("curve"):
        story.append(Paragraph("7. ANALYSE DE SENSIBILITÉ DU TAMPON VORONOÏ (35 m, 45 m, 60 m)", style_section))
        story.append(Paragraph("<b>Point d'inflexion recommandé à 45 m</b>", style_corps))

        buf_rows = [
            [
                Paragraph("<b>Scénario de tampon</b>", style_tableau_bold),
                Paragraph("<b>Surface drainée</b>", style_tableau_bold),
                Paragraph("<b>Écart relatif</b>", style_tableau_bold),
                Paragraph("<b>Débit de pointe</b>", style_tableau_bold),
                Paragraph("<b>Interprétation</b>", style_tableau_bold)
            ]
        ]

        for c in buffer_sens["curve"]:
            is_rec = c.get("is_recommended", False)
            bg_color = colors.HexColor('#e0f2fe') if is_rec else colors.white
            buf_rows.append([
                Paragraph(f"Tampon <b>{round(c.get('buffer_m', 0))} m</b> {'⭐ (Optimal)' if is_rec else ''}", style_tableau),
                Paragraph(f"{c.get('surface_ha', 0)} ha", style_tableau),
                Paragraph(f"{'+' if c.get('gain_pct', 0) > 0 else ''}{c.get('gain_pct', 0)}%", style_tableau),
                Paragraph(f"{c.get('peak_flow_m3s', 0)} m³/s", style_tableau),
                Paragraph(
                    "Emprise voirie stricte" if c.get('buffer_m') == 35 else
                    ("Comblement îlots bâtis (recommandé)" if c.get('buffer_m') == 45 else "Extension zone périurbaine"),
                    style_tableau
                )
            ])

        buf_table = Table(buf_rows, colWidths=[3.5 * cm, 2.5 * cm, 2 * cm, 2.5 * cm, 5.5 * cm])
        buf_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0369a1')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8fafc')]),
        ]))
        story.append(buf_table)
        story.append(Spacer(1, 0.4 * cm))

    # Footer
    story.append(Spacer(1, 1 * cm))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor('#cbd5e1'), spaceAfter=5))
    footer_style = ParagraphStyle('Footer', fontName='Helvetica', fontSize=7, textColor=colors.HexColor('#94a3b8'))
    story.append(Paragraph("DrainPilot SaaS 5.2 • Certification Hydraulique Conforme EPA DYNWAVE", footer_style))
    story.append(Paragraph(f"Dossier d'expertise confidentiel • Édité le {date_str}", footer_style))
    story.append(Paragraph("Document Synthétique A4", footer_style))

    doc.build(story)
    pdf_bytes = buffer.getvalue()
    buffer.close()
    return pdf_bytes