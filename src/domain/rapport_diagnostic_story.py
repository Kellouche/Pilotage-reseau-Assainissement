# -*- coding: utf-8 -*-
"""
================================================================================
Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
Auteur : Dr Abdelhakim KELLOUCHE
Date de création : 2026-11-27
Date de modification : 2026-11-27
Objet : Construction du story ReportLab du rapport d'expertise hydraulique
         (extrait de src/domain/rapport_diagnostic.py)
================================================================================
"""

import io
import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.utils import ImageReader
from reportlab.platypus import (
    HRFlowable, Image, NextPageTemplate, PageBreak, Paragraph, Spacer,
    Table, TableStyle,
)


from src.domain.rapport_diagnostic_story_decisionnel import _story_decisionnel


def _construire_story_rapport(
    simulation_data: Dict[str, Any],
    project_name: Optional[str],
    styles: Any,
    style_section: ParagraphStyle,
    style_corps: ParagraphStyle,
    style_tableau: ParagraphStyle,
    style_tableau_bold: ParagraphStyle,
    style_agent_memo: ParagraphStyle,
    style_agent_title: ParagraphStyle,
) -> Tuple[List[Any], List[Dict[str, Any]], int]:
    """Construit le story ReportLab complet (ex-closure _construire_story).

    Corps deplace verbatim ; les styles et donnees sont passes
    explicitement. Retourne (story, sections_marquees, idx_apres_garde).
    """
    from src.domain.rapport_diagnostic import (  # noqa: E402  (import tardif anti-cycle)
        _MarqueurSection,
        _COULEUR_BLEU, _COULEUR_BLEU_CLAIR, _COULEUR_GRIS,
        _COULEUR_NAVY, _COULEUR_NOIR, _COULEUR_VERT, _COULEUR_VERT_CLAIR,
        creer_tableau_ou_ras, formater_cout_dzd, formater_nombre_fr,
        _generer_carte_reseau_png,
    )
    story = []

    # Registre des sections pour le sommaire (rempli à la 1re passe de build)
    sections_marquees = []

    def _section(titre):
        entree = {"titre": titre, "page": None}
        sections_marquees.append(entree)
        return [
            _MarqueurSection(entree),
            Paragraph(titre, style_section),
            HRFlowable(width="100%", thickness=1.2, color=colors.HexColor(_COULEUR_BLEU), spaceBefore=1, spaceAfter=6),
        ]

    def _encadre_memo(titre, texte):
        """Encadré « mémo » style guide : filet bleu à gauche sur fond clair."""
        if not texte:
            return []
        inner = Table([
            [Paragraph(f"<b>{titre}</b>", style_agent_title)],
            [Paragraph(texte, style_agent_memo)],
        ], colWidths=[17.5 * cm])
        inner.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor(_COULEUR_BLEU_CLAIR)),
            ('BOX', (0, 0), (-1, -1), 0.7, colors.HexColor(_COULEUR_BLEU)),
            ('LINEBEFORE', (0, 0), (0, -1), 3, colors.HexColor(_COULEUR_BLEU)),
            ('TOPPADDING', (0, 0), (-1, -1), 5),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
            ('LEFTPADDING', (0, 0), (-1, -1), 8),
            ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        ]))
        return [inner, Spacer(1, 0.3 * cm)]

    # Extraction des données principales
    # simulation_data peut être soit kpis directement, soit une structure avec meta/kpis/agents_expertise
    meta = simulation_data.get("meta", {})
    # Si simulation_data a une clé "kpis", l'utiliser, sinon utiliser simulation_data directement
    kpis = simulation_data.get("kpis", simulation_data)
    # agents_expertise peut être dans kpis ou dans simulation_data
    agents = kpis.get("agents_expertise", simulation_data.get("agents_expertise", {}))
    buffer_sens = kpis.get("buffer_sensitivity", simulation_data.get("buffer_sensitivity", {}))

    diag = agents.get("diagnostic_causal", {})
    gc = agents.get("prescriptions_genie_civil", {})
    lid = agents.get("solutions_hydrologie_durable", {})
    risk = agents.get("matrice_risques", {})
    finance = agents.get("analyse_variantes_financiere", {})
    synth = agents.get("synthese_executive", {})

    variantes = finance.get("variantes", [])
    ratios = finance.get("ratios_directeurs", {})

    nom_projet = project_name or meta.get("project_name") or "Réseau Urbain"
    date_str = datetime.now().strftime("%d/%m/%Y %H:%M")
    cluster_nom = meta.get("cluster_nom") or meta.get("bassin_nom") or f"Bassin {meta.get('cluster_id', 'N/A')}"

    verdict = synth.get("verdict", "ANALYSE EXPERTE MULTI-AGENTS SWMM 5.2")
    verdict_color = synth.get("couleur", "#2d7ab3")

    # ======================================================================
    # PAGE DE GARDE (style « guide pro »)
    # ======================================================================
    def _kicker(texte):
        # Espacement des lettres à l'intérieur de chaque mot, espace normal entre les mots
        return " ".join(" ".join(mot) for mot in texte.split(" "))

    kicker = "  ·  ".join([
        _kicker("RAPPORT D'EXPERTISE"),
        _kicker("SIMULATION EPA SWMM 5.2"),
        _kicker("ANALYSE HYDRAULIQUE CERTIFIEE")
    ])
    style_kicker = ParagraphStyle(
        'Kicker', parent=styles['Normal'], fontName='Times-Bold',
        fontSize=10, leading=14, alignment=1, textColor=colors.HexColor(_COULEUR_NAVY),
        spaceAfter=10
    )
    style_garde_titre = ParagraphStyle(
        'GardeTitre', parent=styles['Normal'], fontName='Times-Bold',
        fontSize=40, leading=46, alignment=1, textColor=colors.HexColor(_COULEUR_NAVY),
        spaceAfter=6
    )
    style_garde_sous_titre = ParagraphStyle(
        'GardeSousTitre', parent=styles['Normal'], fontName='Times-Italic',
        fontSize=14, leading=19, alignment=1, textColor=colors.HexColor(_COULEUR_NOIR),
        spaceAfter=4
    )
    style_garde_meta = ParagraphStyle(
        'GardeMeta', parent=styles['Normal'], fontName='Times-Italic',
        fontSize=9.5, leading=13, alignment=1, textColor=colors.HexColor(_COULEUR_GRIS)
    )

    story.append(Spacer(1, 3.2 * cm))

    # Entête institutionnelle
    entete_text = (
        "<b>RÉPUBLIQUE ALGÉRIENNE DÉMOCRATIQUE ET POPULAIRE</b><br/>"
        "Ministère des Ressources en Eau - Office National de l'Assainissement (ONA)<br/>"
        "Direction de Zone Chélif - Centre d'Exploitation et d'Assainissement"
    )
    story.append(Paragraph(entete_text, style_garde_meta))
    story.append(Spacer(1, 0.5 * cm))
    story.append(HRFlowable(width="60%", thickness=1, color=colors.HexColor(_COULEUR_BLEU), spaceBefore=2, spaceAfter=14))

    # Kicker + titre + sous-titre
    story.append(Paragraph(kicker, style_kicker))
    story.append(Paragraph("EXPERTISE HYDRAULIQUE", style_garde_titre))
    story.append(Paragraph("et prescriptions de travaux", style_garde_sous_titre))
    story.append(Spacer(1, 0.5 * cm))

    # Bandeau verdict
    style_verdict_garde = ParagraphStyle(
        'VerdictGarde', parent=styles['Normal'], fontName='Times-Bold',
        fontSize=11, leading=15, alignment=1, textColor=colors.HexColor(verdict_color)
    )
    verdict_box = Table([[Paragraph(f"{verdict}", style_verdict_garde)]], colWidths=[18 * cm])
    verdict_box.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor(_COULEUR_BLEU_CLAIR)),
        ('LINEABOVE', (0, 0), (-1, 0), 2.5, colors.HexColor(verdict_color)),
        ('LINEBELOW', (0, 0), (-1, -1), 2.5, colors.HexColor(verdict_color)),
        ('TOPPADDING', (0, 0), (-1, -1), 7),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 7),
    ]))
    story.append(verdict_box)
    story.append(Spacer(1, 0.6 * cm))

    # Cartouche d'identification
    cartouche_data = [
        [
            Paragraph(f"<b>Projet réseau :</b> {nom_projet}", style_corps),
            Paragraph(f"<b>Périmètre simulé :</b> {cluster_nom}", style_corps)
        ],
        [
            Paragraph(f"<b>Date d'expertise :</b> {date_str}", style_corps),
            Paragraph(f"<b>Scénario pluvieux :</b> {meta.get('scenario', 'Pluie décennale ANRH Mascara')}", style_corps)
        ],
        [
            Paragraph(f"<b>Surface drainée :</b> {meta.get('total_area_ha', 0)} ha (tampon {meta.get('buffer_m', 35)} m)", style_corps),
            Paragraph(f"<b>Éléments modélisés :</b> {meta.get('conduits_count', 0)} conduites - {meta.get('junctions_count', 0)} regards", style_corps)
        ],
        [
            Paragraph(f"<b>Débit de pointe :</b> {kpis.get('peak_outflow_m3s', 0):.3f} m³/s", style_corps),
            Paragraph(f"<b>Bilan débordements :</b> {kpis.get('flooded_nodes_count', 0)} débordements - {kpis.get('surcharged_nodes_count', 0)} en charge", style_corps)
        ],
    ]
    cartouche_table = Table(cartouche_data, colWidths=[9 * cm, 9 * cm])
    cartouche_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor(_COULEUR_BLEU_CLAIR)),
        ('BOX', (0, 0), (-1, -1), 1, colors.HexColor('#cbd5e1')),
        ('LINEBEFORE', (0, 0), (0, -1), 3, colors.HexColor(_COULEUR_NAVY)),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e5e7eb')),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    story.append(cartouche_table)
    story.append(Spacer(1, 0.5 * cm))

    story.append(Paragraph(
        f"Édition {date_str} - DrainPilot SaaS 5.2 - Document confidentiel d'aide à la décision",
        style_garde_meta
    ))
    story.append(Spacer(1, 1.2 * cm))
    story.append(PageBreak())
    idx_apres_garde = len(story)  # position d'insertion du sommaire

    # 4. Cadre Hydro-Météorologique
    story.extend(_section("CADRE HYDRO-MÉTÉOROLOGIQUE ET SOLLICITATION PLUVIOMÉTRIQUE RÉGLEMENTAIRE (ANRH / ONA)"))

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
            Paragraph(meta.get('pluvio_montana', kpis.get('pluvio_montana', 'I(t) = 9.334 * t^-0.745')), style_tableau),
        ],
        [
            Paragraph("<b>Station de référence</b>", style_tableau_bold),
            Paragraph(meta.get('pluvio_station', 'Station ANRH Chlef Siège (Réf. 010501)'), style_tableau),
            Paragraph("<b>Source officielle</b>", style_tableau_bold),
            Paragraph(meta.get('pluvio_source', kpis.get('pluvio_source', 'Séries ANRH 1970-2024')), style_tableau),
        ]
    ]
    hydro_table = Table(hydro_data, colWidths=[4.5 * cm, 4.5 * cm, 4.5 * cm, 4.5 * cm])
    hydro_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor(_COULEUR_BLEU_CLAIR)),
        ('BOX', (0, 0), (-1, -1), 1, colors.HexColor('#2d7ab3')),
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
    story.extend(_section("CADRE DE VALIDATION HYDROLOGIQUE ET MODÈLE D'INFILTRATION (SWMM / HORTON / VORONOÏ)"))

    hydro2_data = [
        [
            Paragraph("<b>Discrétisation spatiale</b>", style_tableau_bold),
            Paragraph(f"{meta.get('subcatchments_count', meta.get('junctions_count', 'N/A'))} sous-bassins (Voronoï {meta.get('buffer_m', 35)} m)", style_tableau),
            Paragraph("<b>Imperméabilisation</b>", style_tableau_bold),
            Paragraph(f"C_imp = {meta.get('imperv_pct', 65)}% ({meta.get('typologie_nom', 'Habitat mixte urbain')})", style_tableau),
        ],
        [
            Paragraph("<b>Modèle d'infiltration</b>", style_tableau_bold),
            Paragraph("Horton exponentiel (f0=76.2, finf=13.2, k=4.14 h-1)", style_tableau),
            Paragraph("<b>Temps de concentration (tc)</b>", style_tableau_bold),
            Paragraph(f"tc ~ {meta.get('temps_concentration_min', 15.0):.1f} min (Kirpich/Passini)", style_tableau),
        ]
    ]
    hydro2_table = Table(hydro2_data, colWidths=[4.5 * cm, 4.5 * cm, 4.5 * cm, 4.5 * cm])
    hydro2_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor(_COULEUR_BLEU_CLAIR)),
        ('BOX', (0, 0), (-1, -1), 1, colors.HexColor('#2d7ab3')),
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
    story.extend(_section("BILAN HYDRAULIQUE DÉCISIONNEL ET RÉPARTITION DES FLUX"))

    # Récupérer le bilan hydraulique depuis différentes sources possibles
    bilan_hydraulique = {}
    if kpis.get("bilan_hydraulique"):
        bilan_hydraulique = kpis["bilan_hydraulique"]
    elif synth.get("bilan_hydraulique"):
        bilan_hydraulique = synth["bilan_hydraulique"]

    # Récupérer les valeurs avec fallback sur les KPIs directs
    # Priorité : bilan_hydraulique -> kpis direct -> calcul depuis peak_outflow
    q_genere = bilan_hydraulique.get("q_genere_m3s") or kpis.get("q_genere_m3s") or kpis.get("debit_total_genere_m3s")
    q_exutoire = bilan_hydraulique.get("q_exutoire_m3s") or kpis.get("q_exutoire_m3s") or kpis.get("debit_maintenu_reseau_principal_m3s") or kpis.get("peak_outflow_m3s", 0.0)
    q_derive = bilan_hydraulique.get("q_derive_m3s") or kpis.get("q_derive_m3s") or kpis.get("q_deleste_m3s") or kpis.get("debit_devie_ouvrages_speciaux_m3s", 0.0)
    taux_derive = bilan_hydraulique.get("taux_derive_pct") or kpis.get("taux_derive_pct") or kpis.get("taux_soulagement_reseau_pct") or kpis.get("taux_reduction_charge_pct", 0.0)
    taux_exutoire = bilan_hydraulique.get("taux_exutoire_pct") or kpis.get("taux_exutoire_pct") or kpis.get("taux_exutoire_pct", 100.0)
    nb_ouvrages = bilan_hydraulique.get("nb_ouvrages_actifs") or kpis.get("nb_ouvrages_raccordes") or kpis.get("nb_ouvrages_actifs", 0)

    # Valeurs par défaut si toujours None
    q_genere = q_genere if q_genere is not None else 0.0
    q_exutoire = q_exutoire if q_exutoire is not None else 0.0
    q_derive = q_derive if q_derive is not None else 0.0
    taux_derive = taux_derive if taux_derive is not None else 0.0
    taux_exutoire = taux_exutoire if taux_exutoire is not None else 100.0
    nb_ouvrages = nb_ouvrages if nb_ouvrages is not None else 0

    bilan_text = (
        f"<b>Bassin versant :</b> {cluster_nom}<br/>"
        f"- <b>Débit total généré :</b> <font color='#1a4a7a'><b>{formater_nombre_fr(q_genere)} m³/s</b></font><br/>"
        f"- <b>Soulagement du collecteur :</b> <font color='#16a34a'><b>{taux_derive:.1f}%</b></font><br/>"
        f"- <b>Débit résiduel exutoire :</b> <b>{formater_nombre_fr(q_exutoire)} m³/s</b> ({taux_exutoire:.1f}%)<br/>"
        f"- <b>Débit capté par {nb_ouvrages} ouvrages :</b> <font color='#2d7ab3'><b>{formater_nombre_fr(q_derive)} m³/s</b></font> ({taux_derive:.1f}%)"
    )
    bilan_table = Table([[Paragraph(bilan_text, style_corps)]], colWidths=[18 * cm])
    bilan_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor(_COULEUR_BLEU_CLAIR)),
        ('BOX', (0, 0), (-1, -1), 1, colors.HexColor('#2d7ab3')),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('LEFTPADDING', (0, 0), (-1, -1), 10),
    ]))
    story.append(bilan_table)
    story.append(Spacer(1, 0.4 * cm))

    # 6.B Regards en débordement et durées de submersion
    story.extend(_section("REGARDS EN DÉBORDEMENT ET DURÉES DE SUBMERSION"))

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
                    Paragraph(f"{hours_flooded:.2f}", style_tableau),
                    Paragraph(f"{flood_volume:.2f}", style_tableau),
                    Paragraph(f"{peak_flood_flow:.3f}", style_tableau),
                    Paragraph(f"<font color='#ef4444'><b>{'INONDÉ' if status == 'flooded' else status.upper()}</b></font>", style_tableau)
                ])

            flood_table = Table(flood_rows, colWidths=[3 * cm, 3 * cm, 3 * cm, 4 * cm, 2.5 * cm])
            flood_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.white),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.HexColor('#1a4a7a')),
            ('LINEBELOW', (0, 0), (-1, 0), 1.4, colors.HexColor('#1a4a7a')),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
                ('TOPPADDING', (0, 0), (-1, -1), 3),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor(_COULEUR_BLEU_CLAIR)]),
            ]))
            story.append(flood_table)
            story.append(Spacer(1, 0.3 * cm))
        else:
            story.append(Paragraph("Aucun regard en débordement détecté dans cette simulation.", style_corps))
            story.append(Spacer(1, 0.3 * cm))
    else:
        story.append(Paragraph("Aucune donnée de débordement disponible pour cette simulation.", style_corps))
        story.append(Spacer(1, 0.3 * cm))

    # 6.C Cartographie du réseau (image PNG générée depuis le GeoPackage source)
    # Le PNG est mis en cache entre les deux passes de build (mesure + finale)
    if not hasattr(_construire_story_rapport, "_carte_png"):
        _construire_story_rapport._carte_png = _generer_carte_reseau_png(simulation_data)
    if _construire_story_rapport._carte_png:
        # Page paysage dédiée à la cartographie pour maximiser le fond de carte
        story.append(NextPageTemplate('Paysage'))
        story.append(PageBreak())
        story.extend(_section("CARTOGRAPHIE DU RÉSEAU"))
        try:
            w_px, h_px = ImageReader(io.BytesIO(_construire_story_rapport._carte_png)).getSize()
        except Exception:
            w_px, h_px = 2200, 1400
        largeur = 25.5 * cm
        hauteur = largeur * (h_px / max(w_px, 1))
        hauteur_max = 14.6 * cm
        if hauteur > hauteur_max:
            hauteur = hauteur_max
            largeur = hauteur * (w_px / max(h_px, 1))
        img_carte = Image(io.BytesIO(_construire_story_rapport._carte_png), width=largeur, height=hauteur)
        img_carte.hAlign = "CENTER"
        story.append(img_carte)
        story.append(Spacer(1, 0.2 * cm))
        style_legende_fig = ParagraphStyle(
            'LegendeFigure', parent=style_corps, alignment=1, fontSize=9.5)
        story.append(Paragraph(
            "<i>Réseau d'assainissement après simulation</i>",
            style_legende_fig))
        story.append(Spacer(1, 0.4 * cm))
        # Le gabarit Paysage revient automatiquement au Portrait en fin de page
        story.append(PageBreak())

    # 7. Synthèse Exécutive
    ctx = {
        "kpis": kpis,
        "buffer_sens": buffer_sens,
        "diag": diag,
        "gc": gc,
        "lid": lid,
        "risk": risk,
        "finance": finance,
        "synth": synth,
        "variantes": variantes,
        "ratios": ratios,
        "date_str": date_str,
        "verdict": verdict,
        "verdict_color": verdict_color,
        "style_corps": style_corps,
        "style_tableau": style_tableau,
        "style_tableau_bold": style_tableau_bold,
        "styles": styles,
        "taux_derive": taux_derive,
    }
    _story_decisionnel(story, _section, _encadre_memo, ctx)
    return story, sections_marquees, idx_apres_garde
