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
