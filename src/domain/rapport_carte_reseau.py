# -*- coding: utf-8 -*-
"""
================================================================================
Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
Auteur : Dr Abdelhakim KELLOUCHE
Date de création : 2026-11-27
Date de modification : 2026-11-27
Objet : Génération de la cartographie PNG du réseau pour le rapport PDF (matplotlib Agg)
================================================================================
"""

import io
import re
from pathlib import Path
from typing import Any, Dict, Optional


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

    # ---- Fond de carte (comme la vue Leaflet) ----
    # CartoDB Positron en priorité (politique d'usage compatible apps),
    # OpenStreetMap en repli avec User-Agent identifiant DrainPilot.
    _basemap_ok = False
    try:
        import contextily as ctx
        _providers = [
            (ctx.providers.CartoDB.Positron, {}),
            (ctx.providers.OpenStreetMap.Mapnik,
             {"headers": {"User-Agent": "DrainPilot/5.2 - plateforme assainissement"}}),
        ]
        for _provider, _opts in _providers:
            if _basemap_ok:
                break
            try:
                if not rotation_90:
                    ctx.add_basemap(ax, source=_provider, crs="EPSG:32631",
                                    reset_extent=False, attribution=False,
                                    zorder=-1, **_opts)
                    _basemap_ok = bool(ax.images)
                else:
                    # Carte pivotée : raster récupéré en CRS d'origine puis affiché
                    # via le même transform de rotation que les géométries
                    marge = 0.05
                    bx0 = xmin_d - marge * span_x_data
                    by0 = ymin_d - marge * span_y_data
                    bx1 = xmax_d + marge * span_x_data
                    by1 = ymax_d + marge * span_y_data
                    fig_tmp, ax_tmp = plt.subplots(figsize=(8, 8))
                    try:
                        ax_tmp.set_xlim(bx0, bx1)
                        ax_tmp.set_ylim(by0, by1)
                        ctx.add_basemap(ax_tmp, source=_provider, crs="EPSG:32631",
                                        reset_extent=False, attribution=False,
                                        **_opts)
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
                continue
    except Exception:
        _basemap_ok = False
    if _basemap_ok:
        ax.text(0.995, 0.008, "© OpenStreetMap contributors, © CARTO",
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
