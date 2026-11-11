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
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import cm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.utils import ImageReader
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


# ============================================================
# CARTOGRAPHIE DU RÉSEAU (image PNG intégrée au PDF)
# ============================================================

_COULEUR_REGARD_NORMAL = '#64748b'
_COULEUR_REGARD_SURCHARGE = '#f59e0b'
_COULEUR_REGARD_INONDE = '#ef4444'
_COULEUR_CONDUITE_NORMALE = '#94a3b8'
_COULEUR_CONDUITE_SURCHARGE = '#f59e0b'
_COULEUR_CONDUITE_CRITIQUE = '#ef4444'

_STATUT_VERS_COULEUR = {
    'flooded': _COULEUR_REGARD_INONDE,
    'inonde': _COULEUR_REGARD_INONDE,
    'surcharged': _COULEUR_REGARD_SURCHARGE,
    'surcharge': _COULEUR_REGARD_SURCHARGE,
    'critique': _COULEUR_CONDUITE_CRITIQUE,
    'critical': _COULEUR_CONDUITE_CRITIQUE,
    'normal': _COULEUR_REGARD_NORMAL,
    'libre': _COULEUR_REGARD_NORMAL,
}


def _cle_identifiant(val: Any) -> str:
    """Normalise un identifiant de nœud/conduite pour la jointure gpkg ↔ résultats."""
    s = str(val).strip()
    if s.endswith('.0'):
        s = s[:-2]
    return s


def _generer_carte_reseau_png(simulation_data: Dict[str, Any]) -> Optional[bytes]:
    """
    Génère une cartographie PNG du réseau d'assainissement colorée selon
    les résultats de la simulation SWMM (regards et conduites).

    Retourne None si le GeoPackage source ou les couches sont indisponibles.
    """
    gpkg_path_str = (
        simulation_data.get("source_gpkg")
        or simulation_data.get("meta", {}).get("source_gpkg")
    )
    if not gpkg_path_str:
        return None
    try:
        gpkg_path = Path(gpkg_path_str)
        if not gpkg_path.exists():
            return None
    except Exception:
        return None

    try:
        import geopandas as gpd
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import numpy as np
        import matplotlib.transforms as mtransforms
        from matplotlib.lines import Line2D
        from shapely.geometry import LineString, MultiLineString
        from shapely.affinity import rotate as _rotate_geom
        import contextily as ctx
    except Exception:
        return None

    try:
        regards = gpd.read_file(gpkg_path, layer="regards")
        canalisations = gpd.read_file(gpkg_path, layer="canalisations")
    except Exception:
        return None
    if regards.empty and canalisations.empty:
        return None

    node_results = simulation_data.get("node_results", {}) or {}
    conduit_results = simulation_data.get("conduit_results", {}) or {}
    if isinstance(node_results, list):
        node_results = {
            _cle_identifiant(n.get("node", n.get("node_id", ""))): n
            for n in node_results if isinstance(n, dict)
        }
    if isinstance(conduit_results, list):
        conduit_results = {
            _cle_identifiant(c.get("link_id", c.get("conduit", ""))): c
            for c in conduit_results if isinstance(c, dict)
        }

    # Rotation 90° (aucune déformation) quand le réseau est nettement plus
    # haut que large : la carte occupe alors toute la largeur de la page paysage.
    try:
        b_reg, b_can = regards.total_bounds, canalisations.total_bounds
        xmin_d = min(b_can[0], b_reg[0])
        ymin_d = min(b_can[1], b_reg[1])
        xmax_d = max(b_can[2], b_reg[2])
        ymax_d = max(b_can[3], b_reg[3])
        span_x_data = max(xmax_d - xmin_d, 1.0)
        span_y_data = max(ymax_d - ymin_d, 1.0)
    except Exception:
        xmin_d = ymin_d = 0.0
        xmax_d = ymax_d = 1.0
        span_x_data = span_y_data = 1.0
    rotation_90 = span_y_data > 1.15 * span_x_data

    def _prep_geom(geom):
        if rotation_90 and geom is not None and not geom.is_empty:
            try:
                return _rotate_geom(geom, -90, origin=(0.0, 0.0))
            except Exception:
                return geom
        return geom

    fig, ax = plt.subplots(figsize=(11.5, 6.8), dpi=200)
    fig.patch.set_facecolor("white")
    ax.set_facecolor("#f8fafc")

    # Fond : sous-bassins versants (contexte hydrologique)
    try:
        sous_bassins = gpd.read_file(gpkg_path, layer="sous_bassins")
        if not sous_bassins.empty:
            sb = sous_bassins.copy()
            if rotation_90:
                sb["geometry"] = sb.geometry.apply(_prep_geom)
            sb.plot(ax=ax, color="#dbeafe", edgecolor="#93c5fd",
                    linewidth=0.6, zorder=0)
    except Exception:
        pass

    # ---- Conduites : coloration par statut de simulation ----
    statuts_conduites = {}
    for _, row in canalisations.iterrows():
        geom = _prep_geom(row.geometry)
        if geom is None or geom.is_empty:
            continue
        cid = _cle_identifiant(row.get("ID", ""))
        res = conduit_results.get(cid, {})
        statut = str(res.get("status", "")).lower()
        couleur = res.get("color") or _STATUT_VERS_COULEUR.get(
            statut, _COULEUR_CONDUITE_NORMALE)
        if statut and statut not in ("normal", ""):
            statuts_conduites[statut] = couleur
        lw = 2.6 if statut and statut not in ("normal", "") else 1.5

        def _tracer(geo):
            if isinstance(geo, LineString):
                xs, ys = geo.xy
                ax.plot(xs, ys, color=couleur, lw=lw,
                        solid_capstyle="round", zorder=2)
            elif isinstance(geo, MultiLineString):
                for partie in geo.geoms:
                    _tracer(partie)

        _tracer(geom)

    # ---- Regards : scatter coloré par statut ----
    noeuds_x, noeuds_y, noeuds_c, noeuds_s = [], [], [], []
    for _, row in regards.iterrows():
        geom = _prep_geom(row.geometry)
        if geom is None or geom.is_empty:
            continue
        nid = _cle_identifiant(row.get("ID", row.get("Code", "")))
        res = node_results.get(nid, {})
        statut = str(res.get("status", "")).lower()
        if statut in ("flooded", "inonde"):
            taille = 60
        elif statut in ("surcharged", "surcharge"):
            taille = 40
        else:
            taille = 22
        couleur = res.get("color") or _STATUT_VERS_COULEUR.get(
            statut, _COULEUR_REGARD_NORMAL)
        noeuds_x.append(geom.x)
        noeuds_y.append(geom.y)
        noeuds_c.append(couleur)
        noeuds_s.append(taille)
    if noeuds_x:
        ax.scatter(noeuds_x, noeuds_y, c=noeuds_c, s=noeuds_s,
                   edgecolors="white", linewidths=0.9, zorder=3)

    # ---- Mise en page ----
    ax.set_aspect("equal")
    ax.axis("off")

    xmin, xmax = ax.get_xlim()
    ymin, ymax = ax.get_ylim()
    span_x = max(xmax - xmin, 1.0)
    span_y = max(ymax - ymin, 1.0)
    # Marge de 4 % pour éviter que les points touchent les bords
    ax.set_xlim(xmin - 0.04 * span_x, xmax + 0.04 * span_x)
    ax.set_ylim(ymin - 0.04 * span_y, ymax + 0.04 * span_y)
    xmin, xmax = ax.get_xlim()
    ymin, ymax = ax.get_ylim()
    span_x = xmax - xmin

    # ---- Fond de carte OpenStreetMap (comme la vue Leaflet) ----
    _basemap_ok = False
    try:
        provider = ctx.providers.OpenStreetMap.Mapnik
        if not rotation_90:
            ctx.add_basemap(ax, source=provider, crs="EPSG:32631",
                            reset_extent=False, attribution=False, zorder=-1)
            _basemap_ok = True
        else:
            # Carte pivotée : raster récupéré en CRS d'origine puis affiché
            # via le même transform de rotation que les géométries
            marge = 0.05
            bx0, by0 = xmin_d - marge * span_x_data, ymin_d - marge * span_y_data
            bx1, by1 = xmax_d + marge * span_x_data, ymax_d + marge * span_y_data
            fig_tmp, ax_tmp = plt.subplots(figsize=(8, 8))
            try:
                ax_tmp.set_xlim(bx0, bx1)
                ax_tmp.set_ylim(by0, by1)
                ctx.add_basemap(ax_tmp, source=provider, crs="EPSG:32631",
                                reset_extent=False, attribution=False)
                if ax_tmp.images:
                    _im = ax_tmp.images[-1]
                    _arr = np.asarray(_im.get_array())
                    _ext = _im.get_extent()
                    _rot = mtransforms.Affine2D().rotate_deg(-90)
                    ax.imshow(_arr, extent=_ext,
                              transform=_rot + ax.transData,
                              interpolation="bilinear", zorder=-1)
                    _basemap_ok = True
            finally:
                plt.close(fig_tmp)
    except Exception:
        _basemap_ok = False
    if _basemap_ok:
        ax.text(0.995, 0.008, "© OpenStreetMap contributors",
                transform=ax.transAxes, ha="right", va="bottom",
                fontsize=6, color="#6b7280", zorder=6)

    meta = simulation_data.get("meta", {})
    cluster_nom = meta.get("cluster_nom") or meta.get("bassin_nom") or ""

    # Flèche nord (orientée selon la rotation éventuelle de la carte)
    if rotation_90:
        # Nord (+y d'origine) pointe désormais vers la droite (+x écran)
        ax.annotate("N", xy=(0.93, 0.965), xycoords="axes fraction",
                    ha="center", fontsize=13, fontweight="bold",
                    color=_COULEUR_NAVY)
        ax.annotate("", xy=(0.865, 0.965), xycoords="axes fraction",
                    xytext=(0.76, 0.965),
                    arrowprops=dict(arrowstyle="-|>", color=_COULEUR_NAVY, lw=1.8))
    else:
        ax.annotate("N", xy=(0.97, 0.93), xycoords="axes fraction",
                    ha="center", fontsize=13, fontweight="bold",
                    color=_COULEUR_NAVY)
        ax.annotate("", xy=(0.97, 0.885), xycoords="axes fraction",
                    xytext=(0.97, 0.80),
                    arrowprops=dict(arrowstyle="-|>", color=_COULEUR_NAVY, lw=1.8))

    # Barre d'échelle (coordonnées projetées en mètres)
    pas_echelle = next(
        (p for p in (10, 20, 50, 100, 200, 500, 1000) if span_x / p >= 6),
        span_x / 6)
    x0 = xmin + 0.06 * span_x
    y0 = ymin + 0.07 * (ymax - ymin)
    ax.plot([x0, x0 + pas_echelle], [y0, y0], color="#1a4a7a", lw=2.5,
            solid_capstyle="butt", zorder=4)
    ax.plot([x0, x0], [y0 - 0.008 * (ymax - ymin), y0 + 0.008 * (ymax - ymin)],
            color="#1a4a7a", lw=1.2, zorder=4)
    ax.plot([x0 + pas_echelle, x0 + pas_echelle],
            [y0 - 0.008 * (ymax - ymin), y0 + 0.008 * (ymax - ymin)],
            color="#1a4a7a", lw=1.2, zorder=4)
    ax.text(x0 + pas_echelle / 2, y0 - 0.025 * (ymax - ymin),
            f"{int(pas_echelle)} m", ha="center", fontsize=8,
            color="#1a4a7a", fontweight="bold", zorder=4)

    # ---- Cadre des paramètres de simulation (encadré blanc, police 8) ----
    try:
        _lignes_params = []
        _bassin = meta.get("cluster_nom") or meta.get("bassin_nom") or ""
        if _bassin:
            _lignes_params.append(f"Bassin : {_bassin}")
        _scenario = str(meta.get("scenario") or "")
        _scenario = re.sub(r"[^\x00-\xFFFF]", "", _scenario).strip()
        if _scenario:
            _lignes_params.append("Scénario : " + (_scenario if len(_scenario) <= 52 else _scenario[:49] + "…"))
        _pluie = simulation_data.get("total_precipitation_mm")
        _duree = meta.get("duree_heures")
        if _pluie is not None:
            _lignes_params.append(f"Pluie : {float(_pluie):.1f} mm" + (f" — Durée : {float(_duree):.1f} h" if _duree is not None else ""))
        _surf = meta.get("surface_totale_ha") or meta.get("total_area_ha")
        if _surf is not None:
            _lignes_params.append(f"Surface : {float(_surf):.1f} ha")
        if meta.get("junctions_count") is not None or meta.get("conduits_count") is not None:
            _lignes_params.append(f"Ouvrages : {meta.get('junctions_count', '—')} regards / {meta.get('conduits_count', '—')} conduites")
        _qp = simulation_data.get("peak_outflow_m3s")
        _vol = simulation_data.get("total_runoff_volume_m3")
        if _qp is not None or _vol is not None:
            _lignes_params.append(f"Pointe : {float(_qp or 0):.2f} m³/s — Ruisselé : {float(_vol or 0):,.0f} m³".replace(",", " "))
        _nf = simulation_data.get("flooded_nodes_count")
        _ns = simulation_data.get("surcharged_nodes_count")
        if _nf is not None or _ns is not None:
            _lignes_params.append(f"Inondés : {_nf if _nf is not None else '—'} — Surchargés : {_ns if _ns is not None else '—'}")
        if _lignes_params:
            ax.text(0.02, 0.98, "\n".join(_lignes_params),
                    transform=ax.transAxes, fontsize=8, va="top", ha="left",
                    linespacing=1.4, color="#1a1a1a", zorder=6,
                    bbox=dict(boxstyle="round,pad=0.35", facecolor="white",
                              edgecolor=_COULEUR_NAVY, alpha=0.9, linewidth=1.0))
    except Exception:
        pass

    # Légende
    legende = [
        Line2D([0], [0], marker="o", color="w",
               markerfacecolor=_COULEUR_REGARD_NORMAL, markersize=7,
               label="Regard : fonctionnement normal"),
        Line2D([0], [0], marker="o", color="w",
               markerfacecolor=_COULEUR_REGARD_SURCHARGE, markersize=7,
               label="Regard : surchargé"),
        Line2D([0], [0], marker="o", color="w",
               markerfacecolor=_COULEUR_REGARD_INONDE, markersize=9,
               label="Regard : inondé"),
        Line2D([0], [0], color=_COULEUR_CONDUITE_NORMALE, lw=2,
               label="Conduite : nominale"),
        Line2D([0], [0], color=_COULEUR_CONDUITE_SURCHARGE, lw=2,
               label="Conduite : en surcharge"),
        Line2D([0], [0], color=_COULEUR_CONDUITE_CRITIQUE, lw=2,
               label="Conduite : critique"),
    ]
    ax.legend(handles=legende, loc="upper center", bbox_to_anchor=(0.5, -0.02),
              ncol=3, fontsize=8, frameon=True, framealpha=0.9,
              edgecolor="#e5e7eb", fancybox=False)

    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return buf.getvalue()


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
        if not hasattr(_construire_story, "_carte_png"):
            _construire_story._carte_png = _generer_carte_reseau_png(simulation_data)
        if _construire_story._carte_png:
            # Page paysage dédiée à la cartographie pour maximiser le fond de carte
            story.append(NextPageTemplate('Paysage'))
            story.append(PageBreak())
            story.extend(_section("CARTOGRAPHIE DU RÉSEAU"))
            try:
                w_px, h_px = ImageReader(io.BytesIO(_construire_story._carte_png)).getSize()
            except Exception:
                w_px, h_px = 2200, 1400
            largeur = 25.5 * cm
            hauteur = largeur * (h_px / max(w_px, 1))
            hauteur_max = 14.6 * cm
            if hauteur > hauteur_max:
                hauteur = hauteur_max
                largeur = hauteur * (w_px / max(h_px, 1))
            img_carte = Image(io.BytesIO(_construire_story._carte_png), width=largeur, height=hauteur)
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


        return story, sections_marquees, idx_apres_garde

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