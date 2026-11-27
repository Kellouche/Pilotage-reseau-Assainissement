# -*- coding: utf-8 -*-
"""
================================================================================
Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
Auteur : Dr Abdelhakim KELLOUCHE
Date de création : 2026-11-27
Date de modification : 2026-11-27
Objet : Sections decisionnelles du story ReportLab (extrait de
         src/domain/rapport_diagnostic_story.py)
================================================================================
"""

from reportlab.lib import colors
from reportlab.lib.units import cm
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import (
    HRFlowable, NextPageTemplate, PageBreak, Paragraph, Spacer,
    Table, TableStyle,
)

from src.domain.rapport_diagnostic_story_decisionnel_fin import _story_decisionnel_fin


def _story_decisionnel(story, _section, _encadre_memo, ctx):
    """Ajoute les sections decisionnelles (synthese, plan d'action, finances,
    recommandations, conclusion) au story. Corps deplace verbatim."""
    from src.domain.rapport_diagnostic import (  # noqa: E402  (import tardif anti-cycle)
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

    story.extend(_section("1. SYNTHÈSE STRATÉGIQUE ET AVIS DES DÉCIDEURS"))

    verdict_box_style = ParagraphStyle(
        'VerdictBox',
        parent=styles['Normal'],
        fontName='Times-Roman',
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
        ParagraphStyle('VerdictTitle', fontName='Times-Bold', fontSize=10, textColor=colors.HexColor(verdict_color))
    ))
    story.append(Paragraph(synth.get("recommandation_cle", ""), style_corps))
    story.append(Paragraph(f"<i>Orientation : {synth.get('avis_direction_generale', '')}</i>",
                          ParagraphStyle('AvisDir', fontName='Times-Italic', fontSize=8, textColor=colors.HexColor('#64748b'))))
    story.append(Spacer(1, 0.3 * cm))

    story.extend(_encadre_memo("Mémoire de Synthèse Stratégique - Directeur Technique", synth.get("note_technique", "")))
    story.append(Spacer(1, 0.3 * cm))

    # 8. Matrice des Risques & Plan d'Action
    story.extend(_section("2. PLAN D'ACTION PRIORISÉ ET MATRICE DES RISQUES"))
    story.append(Paragraph(f"<b>Budget total estimé :</b> {formater_cout_dzd(gc.get('cout_global_estime_dzd', 0))}", style_corps))
    story.append(Spacer(1, 0.2 * cm))

    story.extend(_encadre_memo("Note de hiérarchisation multicritère - Expert risques", risk.get("note_technique", "")))

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
            Paragraph("<b>Coût estimé (DA)</b>", style_tableau_bold),
            Paragraph("<b>Délai</b>", style_tableau_bold)
        ]
    ]

    if risk_list:
        for a in risk_list:
            prio = a.get("priorite", "P1")
            badge_color = colors.HexColor('#ef4444') if prio == 'P1' else (colors.HexColor('#f97316') if prio == 'P2' else colors.HexColor('#2d7ab3'))
            risk_rows.append([
                Paragraph(f"<font color='{badge_color.hexval()}'><b>{prio}</b></font>", style_tableau),
                Paragraph(f"<b>{a.get('conduite', '--')}</b>", style_tableau),
                Paragraph(a.get('type_risque', '--'), style_tableau),
                Paragraph(a.get('action_requise', '--'), style_tableau),
                Paragraph(formater_cout_dzd(a.get('estimation_cout_dzd', 0), inclure_unite=False), style_tableau),
                Paragraph(a.get('delai_recommande', '--'), style_tableau)
            ])

    risk_table = creer_tableau_ou_ras(
        risk_rows,
        [1.8 * cm, 2.5 * cm, 3 * cm, 5.5 * cm, 2.5 * cm, 2 * cm],
        style_tableau,
        style_tableau_bold,
        "Aucun risque critique immédiat recensé"
    )
    if isinstance(risk_table, Table):
        risk_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.white),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.HexColor('#1a4a7a')),
            ('LINEBELOW', (0, 0), (-1, 0), 1.4, colors.HexColor('#1a4a7a')),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor(_COULEUR_BLEU_CLAIR)]),
        ]))
    story.append(risk_table)
    story.append(Spacer(1, 0.4 * cm))

    # 9. Diagnostic Causal
    story.extend(_section("3. DIAGNOSTIC CAUSAL ET DYSFONCTIONNEMENTS HYDRAULIQUES"))
    story.append(Paragraph(f"<b>{diag.get('nb_surcharges', 0)} tronçons surchargés - {diag.get('nb_goulots', 0)} goulots détectés</b>", style_corps))

    story.extend(_encadre_memo("Diagnostic hydrodynamique - Spécialiste Saint-Venant 1D", diag.get("note_technique", "")))

    # Tableau surcharges
    surch_rows = [
        [
            Paragraph("<b>Conduite</b>", style_tableau_bold),
            Paragraph("<b>Taux Q/Qmax (%)</b>", style_tableau_bold),
            Paragraph("<b>Remplissage H/D (%)</b>", style_tableau_bold),
            Paragraph("<b>Vitesse (m/s)</b>", style_tableau_bold),
            Paragraph("<b>Débit de crête (m³/s)</b>", style_tableau_bold),
            Paragraph("<b>Observation</b>", style_tableau_bold)
        ]
    ]

    if diag.get("surcharged_links"):
        for l in diag["surcharged_links"]:
            surch_rows.append([
                Paragraph(f"<b>{l.get('conduit', '--')}</b>", style_tableau),
                Paragraph(f"<font color='#ef4444'><b>{(l.get('flow_ratio', 0)*100):.0f}</b></font>", style_tableau),
                Paragraph(f"{(l.get('depth_ratio', 0)*100):.0f}", style_tableau),
                Paragraph(f"{l.get('vitesse', l.get('max_velocity_ms', 0)):.2f}", style_tableau),
                Paragraph(f"{l.get('q_max', l.get('max_flow_cms', 0)):.3f}", style_tableau),
                Paragraph(l.get('cause', 'Surcharge sous pression'), style_tableau)
            ])

    surch_table = creer_tableau_ou_ras(
        surch_rows,
        [2.5 * cm, 2 * cm, 2 * cm, 2 * cm, 2.5 * cm, 5 * cm],
        style_tableau,
        style_tableau_bold,
        "Aucun tronçon en surcharge sévère (>80%)"
    )
    if isinstance(surch_table, Table):
        surch_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.white),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.HexColor('#1a4a7a')),
            ('LINEBELOW', (0, 0), (-1, 0), 1.4, colors.HexColor('#1a4a7a')),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor(_COULEUR_BLEU_CLAIR)]),
        ]))
    story.append(surch_table)
    story.append(Spacer(1, 0.3 * cm))

    # Goulots
    story.append(Paragraph("<b>Anomalies géométriques et goulots d'étranglement amont -> aval :</b>", style_corps))

    if diag.get("bottlenecks"):
        bottle_rows = [
            [
                Paragraph("<b>Tronçon (amont -> aval)</b>", style_tableau_bold),
                Paragraph("<b>Diam. amont (mm)</b>", style_tableau_bold),
                Paragraph("<b>Diam. aval (mm)</b>", style_tableau_bold),
                Paragraph("<b>Longueur (m)</b>", style_tableau_bold),
                Paragraph("<b>Conséquence hydraulique</b>", style_tableau_bold)
            ]
        ]
        for b in diag["bottlenecks"]:
            bottle_rows.append([
                Paragraph(f"<b>{b.get('amont', '--')}</b> -> <b>{b.get('aval', '--')}</b>", style_tableau),
                Paragraph(f"{b.get('diam_amont', '--')}", style_tableau),
                Paragraph(f"<font color='#ef4444'><b>{b.get('diam_aval', '--')}</b></font>", style_tableau),
                Paragraph(f"{b.get('longueur', b.get('longueur_m', 0)):.1f}", style_tableau),
                Paragraph(b.get('description', 'Goulot géométrique - Réduction anormale de section'), style_tableau)
            ])
        bottle_table = creer_tableau_ou_ras(
            bottle_rows,
            [4 * cm, 2.5 * cm, 2.5 * cm, 2.5 * cm, 5.5 * cm],
            style_tableau,
            style_tableau_bold,
            "Aucun goulot géométrique inverse détecté"
        )
        if isinstance(bottle_table, Table):
            bottle_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.white),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.HexColor('#1a4a7a')),
            ('LINEBELOW', (0, 0), (-1, 0), 1.4, colors.HexColor('#1a4a7a')),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
                ('TOPPADDING', (0, 0), (-1, -1), 3),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor(_COULEUR_BLEU_CLAIR)]),
            ]))
        story.append(bottle_table)
    else:
        story.append(Paragraph("<b>RAS</b> - Aucun goulot géométrique inverse détecté.", style_corps))
    story.append(Spacer(1, 0.4 * cm))

    # 10. Prescriptions Génie Civil
    story.extend(_section("4. PRESCRIPTIONS DE GÉNIE CIVIL ET DIMENSIONNEMENT NORMALISÉ"))
    story.append(Paragraph(
        f"<b>Métré total :</b> {(gc.get('metres_lineaires_totaux', 0)):.1f} ml  -  "
        f"<b>Marge Manning :</b> +25%  -  "
        f"<b>H/D cible :</b> <= 0.80",
        style_corps
    ))

    story.extend(_encadre_memo("Justification de calcul gravitaire - Ingénieur GC", gc.get("note_technique", "")))

    # BPU
    story.append(Paragraph("<b>Décomposition Analytique du Coût (BPU) :</b>", style_corps))
    bpu = gc.get("decomposition_bpu", {})
    bpu_terr = bpu.get("montant_terrassement_dzd", round(gc.get("cout_global_estime_dzd", 0) * 0.30))
    bpu_four = bpu.get("montant_fourniture_dzd", round(gc.get("cout_global_estime_dzd", 0) * 0.35))
    bpu_pose = bpu.get("montant_pose_remblai_dzd", round(gc.get("cout_global_estime_dzd", 0) * 0.20))
    bpu_chaus = bpu.get("montant_chaussee_dzd", round(gc.get("cout_global_estime_dzd", 0) * 0.15))

    bpu_rows = [
        [Paragraph("<b>Poste de dépense</b>", style_tableau_bold), Paragraph("<b>Montant (DA)</b>", style_tableau_bold)],
        [Paragraph("<b>1. Terrassement et blindage (30%)</b>", style_tableau), Paragraph(formater_cout_dzd(bpu_terr, inclure_unite=False), style_tableau)],
        [Paragraph("<b>2. Fourniture des tuyaux (35%)</b>", style_tableau), Paragraph(formater_cout_dzd(bpu_four, inclure_unite=False), style_tableau)],
        [Paragraph("<b>3. Pose et remblai à 95% OPM (20%)</b>", style_tableau), Paragraph(formater_cout_dzd(bpu_pose, inclure_unite=False), style_tableau)],
        [Paragraph("<b>4. Réfection chaussée bitume (15%)</b>", style_tableau), Paragraph(formater_cout_dzd(bpu_chaus, inclure_unite=False), style_tableau)],
    ]
    bpu_table = Table(bpu_rows, colWidths=[10 * cm, 8 * cm])
    bpu_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor(_COULEUR_BLEU_CLAIR)),
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
            Paragraph("<b>Linéaire (m)</b>", style_tableau_bold),
            Paragraph("<b>Part (%)</b>", style_tableau_bold),
            Paragraph("<b>Prix unitaire (DA/ml)</b>", style_tableau_bold),
            Paragraph("<b>Montant total (DA)</b>", style_tableau_bold),
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
            Paragraph(f"{r.get('pct_lineaire', 0)}", style_tableau),
            Paragraph(formater_cout_dzd(r.get('cout_unitaire_ml_dzd', 0), inclure_unite=False), style_tableau),
            Paragraph(formater_cout_dzd(r.get('cout_total_dzd', 0), inclure_unite=False), style_tableau),
            Paragraph(f"{r.get('pct_budget', 0)}", style_tableau)
        ])

    # Total row
    recap_rows.append([
        Paragraph("<b>TOTAL PROGRAMME</b>", style_tableau_bold),
        Paragraph("", style_tableau), Paragraph("", style_tableau),
        Paragraph(f"<b>{gc.get('nb_troncons_a_recalibrer', 0)}</b>", style_tableau),
        Paragraph(f"<b>{(gc.get('metres_lineaires_totaux', 0)):.1f}</b>", style_tableau),
        Paragraph("100%", style_tableau),
        Paragraph("", style_tableau),
        Paragraph(f"<b><font color='#2d7ab3'>{formater_cout_dzd(gc.get('cout_global_estime_dzd', 0), inclure_unite=False)}</font></b>", style_tableau),
        Paragraph("100%", style_tableau)
    ])

    recap_table = Table(recap_rows, colWidths=[1.8 * cm, 2.2 * cm, 1.8 * cm, 1.5 * cm, 2 * cm, 1.5 * cm, 2.5 * cm, 2.5 * cm, 1.5 * cm])
    recap_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.white),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.HexColor('#1a4a7a')),
            ('LINEBELOW', (0, 0), (-1, 0), 1.4, colors.HexColor('#1a4a7a')),
        ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#f1f5f9')),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ROWBACKGROUNDS', (0, 1), (-2, -1), [colors.white, colors.HexColor(_COULEUR_BLEU_CLAIR)]),
    ]))
    story.append(recap_table)
    story.append(Spacer(1, 0.3 * cm))

    # Détail tronçons
    story.append(Paragraph("<b>Détail des tronçons prioritaires à recalibrer :</b>", style_corps))

    gc_rows = [
        [
            Paragraph("<b>Conduite</b>", style_tableau_bold),
            Paragraph("<b>Ø actuel (mm)</b>", style_tableau_bold),
            Paragraph("<b>Ø requis (mm)</b>", style_tableau_bold),
            Paragraph("<b>DN retenu</b>", style_tableau_bold),
            Paragraph("<b>Matériau</b>", style_tableau_bold),
            Paragraph("<b>Longueur (m)</b>", style_tableau_bold),
            Paragraph("<b>Coût estimé (DA)</b>", style_tableau_bold)
        ]
    ]

    for p in gc.get("prescriptions", []):
        gc_rows.append([
            Paragraph(f"<b>{p.get('conduit', '--')}</b>", style_tableau),
            Paragraph(f"{p.get('diametre_actuel_mm', '--')}", style_tableau),
            Paragraph(f"{p.get('diametre_requis_mm', p.get('diam_theorique_mm', 0)):.0f}", style_tableau),
            Paragraph(f"DN {p.get('dn_normalise_mm', p.get('diam_prescrit_mm', '--'))}", style_tableau),
            Paragraph(p.get('materiau_recommande', 'Béton Armé 135A'), style_tableau),
            Paragraph(f"{p.get('longueur_m', p.get('longueur', 0)):.1f}", style_tableau),
            Paragraph(formater_cout_dzd(p.get('cout_estime_dzd', 0), inclure_unite=False), style_tableau)
        ])

    gc_table = creer_tableau_ou_ras(
        gc_rows,
        [2.5 * cm, 2 * cm, 2 * cm, 2 * cm, 3 * cm, 2 * cm, 2.5 * cm],
        style_tableau,
        style_tableau_bold,
        "Aucun recalibrage structurel lourd requis"
    )
    if isinstance(gc_table, Table):
        gc_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.white),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.HexColor('#1a4a7a')),
            ('LINEBELOW', (0, 0), (-1, 0), 1.4, colors.HexColor('#1a4a7a')),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor(_COULEUR_BLEU_CLAIR)]),
        ]))
    story.append(gc_table)
    story.append(Spacer(1, 0.4 * cm))

    # 11. Analyse Multi-Critères des Variantes
    story.extend(_section("5. ANALYSE MULTICRITÈRE DES VARIANTES D'AMÉNAGEMENT"))

    economie = finance.get("economie_realisee_dzd", 0)
    econ_pct = finance.get("economie_pourcentage", 0)
    story.append(Paragraph(f"<b>Économie scénario mixte :</b> {formater_cout_dzd(economie)} (-{econ_pct:.1f}%)", style_corps))

    story.extend(_encadre_memo("Analyse technico-économique - Expert financier", finance.get("note_technique", "")))

    # Ratios
    ratios = finance.get("ratios_directeurs", {})
    ratio_rows = [
        [
            Paragraph("<b>Coût au ml rénové (DA/ml)</b>", style_tableau_bold),
            Paragraph(formater_cout_dzd(ratios.get("cout_par_ml_renove_dzd", 0), inclure_unite=False), style_tableau),
            Paragraph("<b>Coût par hab. protégé (DA)</b>", style_tableau_bold),
            Paragraph(formater_cout_dzd(ratios.get("cout_par_habitant_protege_dzd", 0), inclure_unite=False), style_tableau),
        ],
        [
            Paragraph("<b>Dommages évités/an (DA)</b>", style_tableau_bold),
            Paragraph(formater_cout_dzd(ratios.get("dommages_annuels_evites_dzd", 0), inclure_unite=False), style_tableau),
            Paragraph("<b>Rentabilité</b>", style_tableau_bold),
            Paragraph(f"Payback {ratios.get('payback_annees', 0):.1f} ans - TRI {ratios.get('tri_pourcentage', 0):.1f}%", style_tableau),
        ]
    ]
    ratio_table = Table(ratio_rows, colWidths=[4.5 * cm, 4.5 * cm, 4.5 * cm, 4.5 * cm])
    ratio_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor(_COULEUR_BLEU_CLAIR)),
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
            Paragraph("<b>Investissement (DA)</b>", style_tableau_bold),
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
            Paragraph(f"{v.get('recalibrage_ml', 0):.1f}" if v.get('recalibrage_ml', 0) > 0 else "--", style_tableau),
            Paragraph(f"{v.get('volume_retention_m3', 0):.0f}" if v.get('volume_retention_m3', 0) > 0 else "--", style_tableau),
            Paragraph(f"<font color='{badge_color.hexval()}'><b>{formater_cout_dzd(v.get('cout_total_dzd', 0), inclure_unite=False)}</b></font>", style_tableau),
            Paragraph(v.get('gain_hydraulique', '--'), style_tableau),
            Paragraph(v.get('impact_voirie', '--'), style_tableau),
            Paragraph(v.get('risque_aval', '--'), style_tableau),
            Paragraph(f"<b>{v.get('score_resilience', '--')} / 10</b>", style_tableau),
            Paragraph(f"<font color='{badge_color.hexval()}'><b>{v.get('statut', '--')}</b></font>", style_tableau)
        ])

    if not variantes:
        var_rows.append([
            Paragraph("<b>Variante 1 : 100% tout-réseau</b>", style_tableau), Paragraph("7 591,9", style_tableau), Paragraph("--", style_tableau),
            Paragraph(formater_cout_dzd(330964500, inclure_unite=False), style_tableau), Paragraph("100% théorique", style_tableau),
            Paragraph("TRÈS ÉLEVÉ", style_tableau), Paragraph("TRÈS ÉLEVÉ", style_tableau), Paragraph("5.5 / 10", style_tableau),
            Paragraph("<font color='#ef4444'><b>NON RETENU</b></font>", style_tableau)
        ])
        var_rows.append([
            Paragraph("<b>Variante 2 : 100% GDO</b>", style_tableau), Paragraph("--", style_tableau), Paragraph("18 500", style_tableau),
            Paragraph(formater_cout_dzd(112500000, inclure_unite=False), style_tableau), Paragraph("Partiel (~62%)", style_tableau),
            Paragraph("Faible", style_tableau), Paragraph("Faible", style_tableau), Paragraph("6.0 / 10", style_tableau),
            Paragraph("<font color='#f97316'><b>INSUFFISANT</b></font>", style_tableau)
        ])
        var_rows.append([
            Paragraph("<b>Variante 3 : Mixte optimisée</b>", style_tableau), Paragraph("4 112,8", style_tableau), Paragraph("6 595", style_tableau),
            Paragraph(f"<font color='#16a34a'><b>{formater_cout_dzd(240384400, inclure_unite=False)}</b></font>", style_tableau), Paragraph("100% résorption", style_tableau),
            Paragraph("Modéré", style_tableau), Paragraph("MINIMAL", style_tableau), Paragraph("<b>9.2 / 10</b>", style_tableau),
            Paragraph("<font color='#16a34a'><b>RECOMMANDÉ</b></font>", style_tableau)
        ])

    var_table = Table(var_rows, colWidths=[3 * cm, 1.8 * cm, 1.8 * cm, 2.5 * cm, 2.5 * cm, 2.2 * cm, 2.2 * cm, 1.5 * cm, 2 * cm])
    var_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.white),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.HexColor('#1a4a7a')),
            ('LINEBELOW', (0, 0), (-1, 0), 1.4, colors.HexColor('#1a4a7a')),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor(_COULEUR_BLEU_CLAIR)]),
    ]))
    story.append(var_table)
    story.append(Spacer(1, 0.4 * cm))
    _story_decisionnel_fin(story, _section, _encadre_memo, ctx)
