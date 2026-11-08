import pytest
import re
from pathlib import Path

def test_bassin_tooltip_content():
    """Valide que le template index.html définit bien la fonction genererTooltipBassinVersantHtml
    avec les métadonnées requises par le métier : Type, Surface, Regards, Conduites avec linéaire,
    et la classe CSS sim-bassin-tooltip à fond noir.
    """
    html_path = Path("templates/index.html")
    content = html_path.read_text(encoding="utf-8")

    assert "window.genererTooltipBassinVersantHtml" in content, "genererTooltipBassinVersantHtml doit être défini"
    assert "sim-bassin-tooltip" in content, "La classe CSS sim-bassin-tooltip doit être utilisée"
    assert "DEVERSOIR_ORAGE" in content, "Le type DEVERSOIR_ORAGE doit être géré"
    assert "🏷️ Type :" in content, "L'indicateur Type doit être présent"
    assert "📐 Surface :" in content, "L'indicateur Surface doit être présent"
    assert "📍 Regards :" in content, "L'indicateur Regards doit être présent"
    assert "📏 Conduites :" in content, "L'indicateur Conduites avec métré linéaire doit être présent"


def test_tooltip_persistence_no_destructive_dom():
    """Valide qu'il n'y a pas de manipulation DOM destructrice Leaflet
    qui masquerait définitivement l'infobulle après le 1er survol.
    """
    html_path = Path("templates/index.html")
    content = html_path.read_text(encoding="utf-8")

    assert "tipEl.style.display = 'none'" not in content, "Ne doit pas altérer le display DOM des tooltips Leaflet"
    assert "pane.querySelectorAll('.leaflet-tooltip').forEach(el => el.remove())" not in content, "Ne doit pas supprimer les nœuds internes de Leaflet"


def test_map_extended_zoom_level():
    """Valide que la carte permet un zoom profond (niveau 22 avec maxNativeZoom 19)
    pour inspecter finement le réseau au-delà du zoom 18 par défaut.
    """
    html_path = Path("templates/index.html")
    content = html_path.read_text(encoding="utf-8")

    assert "maxZoom: 22" in content, "maxZoom 22 doit être configuré sur la carte"
    assert "maxNativeZoom: 19" in content, "maxNativeZoom 19 doit être configuré sur le tileLayer"


def test_toolbar_tooltip_left_orientation():
    """Valide que les infobulles des icônes de la barre d'outils d'édition à droite
    sont orientées à GAUCHE de l'icône pour ne jamais être cachées par le bord de l'écran.
    """
    html_path = Path("templates/index.html")
    content = html_path.read_text(encoding="utf-8")

    assert ".tool-tip:hover::after" in content, "Le style de survol .tool-tip:hover::after doit exister"
    assert "right: calc(100% + 12px)" in content, "L'infobulle doit être positionnée à gauche de l'icône"
    assert "left: auto" in content, "left: auto doit annuler l'ancien positionnement à droite"


def test_bassin_tooltip_left_direction():
    """Valide que les infobulles des bassins s'affichent avec direction 'left'
    pour une ergonomie optimale.
    """
    html_path = Path("templates/index.html")
    content = html_path.read_text(encoding="utf-8")

    assert "direction: 'left'" in content, "direction: 'left' doit être spécifié pour les tooltips de bassins"
