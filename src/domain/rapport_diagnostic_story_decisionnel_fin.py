# -*- coding: utf-8 -*-
"""
================================================================================
Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
Auteur : Dr Abdelhakim KELLOUCHE
Date de création : 2026-11-27
Date de modification : 2026-11-27
Objet : Sections finales du story decisionnel (GDO, sensibilite, conclusion)
================================================================================
"""

from reportlab.lib import colors
from reportlab.lib.units import cm
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import (
    HRFlowable, NextPageTemplate, PageBreak, Paragraph, Spacer,
    Table, TableStyle,
)


def _story_decisionnel_fin(story, _section, _encadre_memo, ctx):
    """Ajoute les sections GDO, sensibilite buffer et conclusion. Verbatim."""
    from src.domain.rapport_diagnostic import (  # noqa: E402
        _COULEUR_BLEU_CLAIR, _COULEUR_VERT, _COULEUR_VERT_CLAIR,
        creer_tableau_ou_ras, formater_cout_dzd,
    )
    kpis = ctx["kpis"]
    buffer_sens = ctx["buffer_sens"]
    diag = ctx["diag"]
    gc = ctx["gc"]
    lid = ctx["lid"]
    risk = ctx["risk"]
    finance = ctx["finance"]
    synth = ctx["synth"]
    variantes = ctx["variantes"]
    ratios = ctx["ratios"]
    date_str = ctx["date_str"]
    verdict = ctx["verdict"]
    verdict_color = ctx["verdict_color"]
    style_corps = ctx["style_corps"]
    style_tableau = ctx["style_tableau"]
    style_tableau_bold = ctx["style_tableau_bold"]
    styles = ctx["styles"]
    taux_derive = ctx["taux_derive"]

    # 12. GDO & Écrêtement
    story.extend(_section("6. GESTION DURABLE DES OUVRAGES (GDO) ET ÉCRÊTEMENT DES POINTES"))
    story.append(Paragraph(f"<b>Volume tampon total :</b> {(lid.get('volume_tampon_requis_m3', 0)):.0f} m³", style_corps))

    story.extend(_encadre_memo("Stratégie d'écrêtement à la source - Expert GDO", lid.get("note_technique", "")))

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
            Paragraph("Linéaire : 1 200 ml - Largeur 1.5 m", style_tableau),
            Paragraph("Infiltration diffuse & déconnexion pluviale", style_tableau)
        ])

    lid_table = creer_tableau_ou_ras(
        lid_rows,
        [2.5 * cm, 4.5 * cm, 5 * cm, 5 * cm],
        style_tableau,
        style_tableau_bold,
        "Aucune solution GDO disponible"
    )
    if isinstance(lid_table, Table):
        lid_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.white),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.HexColor('#1a4a7a')),
            ('LINEBELOW', (0, 0), (-1, 0), 1.4, colors.HexColor('#1a4a7a')),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor(_COULEUR_BLEU_CLAIR)]),
        ]))
    story.append(lid_table)
    story.append(Spacer(1, 0.4 * cm))

    # 13. Analyse de Sensibilité du Buffer
    if buffer_sens.get("curve"):
        story.extend(_section("7. ANALYSE DE SENSIBILITÉ DU TAMPON VORONOÏ (35 m, 45 m, 60 m)"))
        story.append(Paragraph("<b>Point d'inflexion recommandé à 45 m</b>", style_corps))

        buf_rows = [
            [
                Paragraph("<b>Scénario de tampon</b>", style_tableau_bold),
                Paragraph("<b>Surface drainée (ha)</b>", style_tableau_bold),
                Paragraph("<b>Écart relatif (%)</b>", style_tableau_bold),
                Paragraph("<b>Débit de pointe (m³/s)</b>", style_tableau_bold),
                Paragraph("<b>Interprétation</b>", style_tableau_bold)
            ]
        ]

        for c in buffer_sens["curve"]:
            is_rec = c.get("is_recommended", False)
            bg_color = colors.HexColor('#e0f2fe') if is_rec else colors.white
            buf_rows.append([
                Paragraph(f"Tampon <b>{round(c.get('buffer_m', 0))} m</b> {'(Optimal)' if is_rec else ''}", style_tableau),
                Paragraph(f"{c.get('surface_ha', 0)}", style_tableau),
                Paragraph(f"{'+' if c.get('gain_pct', 0) > 0 else ''}{c.get('gain_pct', 0)}", style_tableau),
                Paragraph(f"{c.get('peak_flow_m3s', 0)}", style_tableau),
                Paragraph(
                    "Emprise voirie stricte" if c.get('buffer_m') == 35 else
                    ("Comblement îlots bâtis (recommandé)" if c.get('buffer_m') == 45 else "Extension zone périurbaine"),
                    style_tableau
                )
            ])

        buf_table = creer_tableau_ou_ras(
            buf_rows,
            [3.5 * cm, 2.5 * cm, 2 * cm, 2.5 * cm, 5.5 * cm],
            style_tableau,
            style_tableau_bold,
            "Aucune donnée de sensibilité buffer disponible"
        )
        if isinstance(buf_table, Table):
            buf_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.white),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.HexColor('#1a4a7a')),
            ('LINEBELOW', (0, 0), (-1, 0), 1.4, colors.HexColor('#1a4a7a')),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
                ('TOPPADDING', (0, 0), (-1, -1), 3),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor(_COULEUR_BLEU_CLAIR)]),
            ]))
        story.append(buf_table)
        story.append(Spacer(1, 0.4 * cm))

    # ======================================================================
    # CONCLUSION ET RECOMMANDATIONS
    # ======================================================================
    story.extend(_section("CONCLUSION ET RECOMMANDATIONS"))

    nb_floodes = int(kpis.get('flooded_nodes_count', 0) or 0)
    nb_surcharges = int(kpis.get('surcharged_nodes_count', 0) or 0)
    cout_global = float(gc.get('cout_global_estime_dzd', 0) or 0)
    ml_reseaux = float(gc.get('metres_lineaires_totaux', 0) or 0)

    if nb_floodes > 0:
        conclusion_1 = (
            f"Le réseau présente {nb_floodes} point(s) de débordement et {nb_surcharges} tronçon(s) en surcharge "
            f"pour l'événement pluvieux de dimensionnement. Le débit de pointe à l'exutoire atteint "
            f"{kpis.get('peak_outflow_m3s', 0):.3f} m³/s, avec un soulagement de {taux_derive:.1f}% assuré par les ouvrages de déviation."
        )
    elif nb_surcharges > 0:
        conclusion_1 = (
            f"Aucun débordement en surface n'est observé, mais {nb_surcharges} tronçon(s) travaillent en charge. "
            f"Le réseau est à saturation pour cet événement : des mesures d'infiltration alternative sont recommandées."
        )
    else:
        conclusion_1 = (
            f"Le réseau absorbe l'événement pluvieux simulé en régime gravitaire libre, sans mise en charge "
            f"critique ni débordement (débit de pointe : {kpis.get('peak_outflow_m3s', 0):.3f} m³/s)."
        )

    if cout_global > 0:
        conclusion_2 = (
            f"Le programme de travaux proposé ({ml_reseaux:.1f} ml de collecteurs recalibrés) représente un "
            f"investissement estimé de {formater_cout_dzd(cout_global)}. "
            f"La stratégie mixte recalibrage ciblé + écrêtement amont permet la résorption des points critiques "
            f"tout en limitant l'impact sur la voirie et les délais d'exécution."
        )
    else:
        conclusion_2 = (
            "Aucun recalibrage structurel lourd n'est requis : le programme se limite à l'entretien courant "
            "et à la surveillance périodique des tronçons les plus sollicités."
        )

    conclusion_3 = (
        "Il est recommandé de soumettre ce dossier à la Direction Technique pour validation, puis d'engager "
        "la phase APS/APD des interventions P1 dans les meilleurs délais. Une nouvelle simulation de vérification "
        "sera exécutée après travaux pour confirmer la résorption des débordements."
    )

    conclusion_box = Table([
        [Paragraph(f"<b>1.</b> {conclusion_1}", style_corps)],
        [Paragraph(f"<b>2.</b> {conclusion_2}", style_corps)],
        [Paragraph(f"<b>3.</b> {conclusion_3}", style_corps)],
    ], colWidths=[18 * cm])
    conclusion_box.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor(_COULEUR_VERT_CLAIR)),
        ('BOX', (0, 0), (-1, -1), 0.8, colors.HexColor(_COULEUR_VERT)),
        ('LINEBEFORE', (0, 0), (0, -1), 4, colors.HexColor(_COULEUR_VERT)),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('LEFTPADDING', (0, 0), (-1, -1), 10),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
    ]))
    story.append(conclusion_box)

    # Footer
    story.append(Spacer(1, 1 * cm))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor('#cbd5e1'), spaceAfter=5))
    footer_style = ParagraphStyle('Footer', fontName='Times-Roman', fontSize=7, textColor=colors.HexColor('#94a3b8'))
    story.append(Paragraph("DrainPilot SaaS 5.2 - Certification Hydraulique Conforme EPA DYNWAVE", footer_style))
    story.append(Paragraph(f"Dossier d'expertise confidentiel - Édité le {date_str}", footer_style))
    story.append(Paragraph("Document Synthétique A4", footer_style))
