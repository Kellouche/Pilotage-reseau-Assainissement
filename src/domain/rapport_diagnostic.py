# -*- coding: utf-8 -*-
"""
================================================================================
Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
Auteur : Dr Abdelhakim KELLOUCHE
Date de création : 2026-11-10
Date de modification : 2026-11-27
Objet : Générateur PDF du Rapport d'Expertise Hydraulique Complet (ReportLab)
================================================================================
"""

import io
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import cm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.utils import ImageReader

from src.domain.rapport_carte_reseau import _generer_carte_reseau_png  # noqa: F401
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable,
    PageBreak, Flowable, Image, BaseDocTemplate, PageTemplate, Frame,
    NextPageTemplate,
)
from reportlab.pdfgen import canvas as pdf_canvas

# Palette « guide pro » (référence : documents commerciaux soignés)
_COULEUR_NAVY = '#1a4a7a'
_COULEUR_BLEU = '#2d7ab3'
_COULEUR_VERT = '#2e7d32'
_COULEUR_GRIS = '#6b7280'
_COULEUR_BLEU_CLAIR = '#edf3fa'
_COULEUR_VERT_CLAIR = '#eef4ee'
_COULEUR_NOIR = '#1a1a1a'


class _CanvasNumerote(pdf_canvas.Canvas):
    """Canvas ReportLab : en-tête courant, pied de page et pagination « Page X / Y »."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._etats_sauvegardes = []

    def showPage(self):
        self._etats_sauvegardes.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        total_pages = len(self._etats_sauvegardes)
        for etat in self._etats_sauvegardes:
            self.__dict__.update(etat)
            self._dessiner_pagination(total_pages)
            pdf_canvas.Canvas.showPage(self)
        pdf_canvas.Canvas.save(self)

    def _dessiner_pagination(self, total_pages):
        self.saveState()
        w_page, h_page = self._pagesize
        if self._pageNumber > 1:
            # En-tête courant (absent de la page de garde)
            self.setFont("Times-Roman", 7)
            self.setFillColor(colors.HexColor(_COULEUR_GRIS))
            self.drawString(1.5 * cm, h_page - 0.9 * cm,
                            "DrainPilot 5.2 - Rapport d'expertise hydraulique SWMM")
            self.drawRightString(w_page - 1.5 * cm, h_page - 0.9 * cm,
                                 "EPA SWMM 5.2 - Saint-Venant 1D")
            self.setStrokeColor(colors.HexColor('#e5e7eb'))
            self.setLineWidth(0.5)
            self.line(1.5 * cm, h_page - 1.05 * cm, w_page - 1.5 * cm, h_page - 1.05 * cm)
        # Pagination centrée en pied de page
        self.setFont("Times-Roman", 7)
        self.setFillColor(colors.HexColor(_COULEUR_GRIS))
        self.drawCentredString(w_page / 2.0, 0.9 * cm, f"Page {self._pageNumber} / {total_pages}")
        self.restoreState()


class _MarqueurSection(Flowable):
    """Flowable invisible qui enregistre le numéro de page où une section démarre."""

    def __init__(self, entree):
        super().__init__()
        self._entree = entree
        self.width = 0
        self.height = 0.01

    def wrap(self, aw, ah):
        return (0, self.height)

    def draw(self):
        self._entree["page"] = self.canv.getPageNumber()


def formater_cout_dzd(montant: Any, avec_decimales: bool = True, inclure_unite: bool = True) -> str:
    """Formate un montant en DA (espace comme séparateur de milliers, virgule décimale)."""
    try:
        val = float(montant or 0.0)
    except (ValueError, TypeError):
        val = 0.0
    if avec_decimales:
        s = f"{val:,.2f}".replace(",", " ").replace(".", ",")
    else:
        s = f"{val:,.0f}".replace(",", " ")
    return f"{s} DA" if inclure_unite else s


def formater_nombre_fr(val: Any, decimales: int = 3) -> str:
    """Formate un nombre décimal avec la virgule française."""
    try:
        fval = float(val or 0.0)
    except (ValueError, TypeError):
        fval = 0.0
    fmt = f"{{:,.{decimales}f}}"
    return fmt.format(fval).replace(",", " ").replace(".", ",")


def creer_tableau_ou_ras(rows: List[List[Any]], col_widths: List[float], style_tableau: Any, style_tableau_bold: Any, message_ras: str = "RAS") -> Any:
    """
    Crée un tableau ReportLab ou retourne un message RAS si le tableau est vide.
    
    Args:
        rows: Liste des lignes du tableau (chaque ligne est une liste de Paragraph)
        col_widths: Largeurs des colonnes en cm
        style_tableau: Style pour les cellules normales
        style_tableau_bold: Style pour les cellules en gras
        message_ras: Message à afficher si le tableau est vide
        
    Returns:
        Table ou Paragraph avec message RAS
    """
    # Vérifier si le tableau a des données (plus que l'en-tête)
    if len(rows) <= 1:
        return Paragraph(f"<b>{message_ras}</b>", style_tableau)
    
    return Table(rows, colWidths=col_widths)


def _creer_document_pdf(buffer: io.BytesIO, titre: Optional[str] = None) -> BaseDocTemplate:
    """Document PDF avec gabarits portrait (A4) et paysage (A4) pour la cartographie."""
    doc = BaseDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=1.5 * cm,
        rightMargin=1.5 * cm,
        topMargin=1.5 * cm,
        bottomMargin=1.5 * cm,
        title=titre or "Rapport d'expertise hydraulique",
    )
    frame_port = Frame(1.5 * cm, 1.5 * cm, A4[0] - 3 * cm, A4[1] - 3 * cm, id='normal')
    lw_pays, lh_pays = landscape(A4)
    frame_pays = Frame(1.5 * cm, 1.5 * cm, lw_pays - 3 * cm, lh_pays - 3 * cm, id='paysage')
    doc.addPageTemplates([
        PageTemplate(id='Portrait', frames=frame_port, pagesize=A4),
        PageTemplate(id='Paysage', frames=frame_pays, pagesize=landscape(A4),
                     autoNextPageTemplate='Portrait'),
    ])
    return doc


def _flowable_carte_reseau(simulation_data: Dict[str, Any]) -> Optional[Image]:
    """Retourne un flowable Image ReportLab de la cartographie, ou None."""
    png = _generer_carte_reseau_png(simulation_data)
    if not png:
        return None
    try:
        w_px, h_px = ImageReader(io.BytesIO(png)).getSize()
    except Exception:
        return None
    largeur = 17.5 * cm
    hauteur = largeur * (h_px / max(w_px, 1))
    hauteur_max = 13.0 * cm
    if hauteur > hauteur_max:
        hauteur = hauteur_max
        largeur = hauteur * (w_px / max(h_px, 1))
    img = Image(io.BytesIO(png), width=largeur, height=hauteur)
    img.hAlign = "CENTER"
    return img


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
    doc = _creer_document_pdf(
        buffer,
        titre=f"Rapport d'expertise hydraulique - {project_name or 'Réseau Urbain'}"
    )

    styles = getSampleStyleSheet()

    # Styles personnalisés
    style_section = ParagraphStyle(
        'SectionTitre',
        parent=styles['Heading2'],
        fontName='Times-Bold',
        fontSize=14,
        leading=18,
        textColor=colors.HexColor('#1a4a7a'),
        spaceBefore=12,
        spaceAfter=6
    )

    style_sous_section = ParagraphStyle(
        'SousSection',
        parent=styles['Heading3'],
        fontName='Times-Bold',
        fontSize=10.5,
        leading=14,
        textColor=colors.HexColor('#2d7ab3'),
        spaceBefore=6,
        spaceAfter=3
    )

    style_corps = ParagraphStyle(
        'CorpsTexte',
        parent=styles['Normal'],
        fontName='Times-Roman',
        fontSize=11,
        leading=15,
        textColor=colors.HexColor('#1e293b'),
        alignment=4  # Justifié
    )

    style_tableau = ParagraphStyle(
        'TableauTexte',
        parent=styles['Normal'],
        fontName='Times-Roman',
        fontSize=8.5,
        leading=11,
        textColor=colors.HexColor('#0f172a'),
        alignment=4  # Justifié
    )

    style_tableau_bold = ParagraphStyle(
        'TableauTexteBold',
        parent=styles['Normal'],
        fontName='Times-Bold',
        fontSize=8.5,
        leading=11,
        textColor=colors.HexColor('#0f172a'),
        alignment=4  # Justifié
    )

    style_agent_memo = ParagraphStyle(
        'AgentMemo',
        parent=styles['Normal'],
        fontName='Times-Roman',
        fontSize=10.5,
        leading=14,
        textColor=colors.HexColor('#1e293b'),
        leftIndent=4,
        rightIndent=4,
        spaceBefore=4,
        spaceAfter=4,
        alignment=4  # Justifié
    )

    style_agent_title = ParagraphStyle(
        'AgentTitle',
        parent=styles['Normal'],
        fontName='Times-Bold',
        fontSize=10.5,
        leading=14,
        textColor=colors.HexColor('#2d7ab3'),
        spaceBefore=4,
        spaceAfter=2
    )

    def _construire_story():
        from src.domain.rapport_diagnostic_story import _construire_story_rapport
        return _construire_story_rapport(
            simulation_data, project_name, styles,
            style_section, style_corps, style_tableau, style_tableau_bold,
            style_agent_memo, style_agent_title,
        )

    story_mesure, sections_marquees, idx_apres_garde = _construire_story()
    # ======================================================================
    # SOMMAIRE — double passe : 1re passe pour mesurer les pages réelles des
    # sections, puis insertion du sommaire (1 page) et décalage +1.
    # ======================================================================
    buffer_mesure = io.BytesIO()
    doc_mesure = _creer_document_pdf(buffer_mesure)
    doc_mesure.build(story_mesure, canvasmaker=_CanvasNumerote)
    buffer_mesure.close()

    style_toc_titre = ParagraphStyle(
        'TocTitre', fontName='Times-Bold', fontSize=18, leading=24,
        alignment=1, textColor=colors.HexColor(_COULEUR_NAVY),
        spaceAfter=10
    )
    style_toc_page = ParagraphStyle(
        'TocPage', fontName='Times-Roman', fontSize=9.5, leading=13,
        textColor=colors.HexColor(_COULEUR_GRIS)
    )
    toc_rows = [[Paragraph("<b>SOMMAIRE</b>", style_toc_titre), ""]]
    for entree in sections_marquees:
        page_reelle = (entree["page"] or 1) + 1
        toc_rows.append([
            Paragraph(entree["titre"].replace(" & ", " et "), style_corps),
            Paragraph(str(page_reelle), style_toc_page),
        ])
    toc_table = Table(toc_rows, colWidths=[15.5 * cm, 2 * cm])
    toc_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LINEBELOW', (0, 1), (-1, -2), 0.4, colors.HexColor('#e2e8f0')),
        ('LINEBELOW', (0, -1), (-1, -1), 1.2, colors.HexColor(_COULEUR_NAVY)),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LEFTPADDING', (0, 0), (0, -1), 0),
        ('RIGHTPADDING', (-1, 0), (-1, -1), 0),
        ('ALIGN', (-1, 0), (-1, -1), 'RIGHT'),
    ]))
    toc_flowables = [Spacer(1, 1.5 * cm), toc_table]

    story_final, _, _ = _construire_story()
    story_final = (
        story_final[:idx_apres_garde]
        + toc_flowables
        + [PageBreak()]
        + story_final[idx_apres_garde:]
    )
    doc.build(story_final, canvasmaker=_CanvasNumerote)
    pdf_bytes = buffer.getvalue()
    buffer.close()
    return pdf_bytes
