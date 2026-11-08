"""
================================================================================
Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
Auteur : Dr Abdelhakim KELLOUCHE
Date de création : 2026-04-20
Date de modification : 2026-11-08
Objet : Tests de la terminologie GDO et de la persistance des simulations
================================================================================
"""

import re
from pathlib import Path

def _get_full_cockpit_content():
    base = Path(__file__).resolve().parent.parent
    content = (base / "templates" / "index.html").read_text(encoding="utf-8")
    for p in (base / "templates" / "partials").glob("*.html"):
        content += "\n" + p.read_text(encoding="utf-8")
    for j in (base / "static" / "js" / "app").glob("*.js"):
        content += "\n" + j.read_text(encoding="utf-8")
    for c in (base / "static" / "css").glob("*.css"):
        content += "\n" + c.read_text(encoding="utf-8")
    return content

def test_absence_sfn_and_presence_gdo():
    """Vérifie l'éradication du terme SFN au profit de GDO dans le code métier et les templates."""
    base_dir = Path(__file__).resolve().parent.parent
    
    # Fichiers et corpus à inspecter
    files_to_check = [
        (base_dir / "src" / "domain" / "agents_expertise.py", (base_dir / "src" / "domain" / "agents_expertise.py").read_text(encoding="utf-8")),
        (base_dir / "templates" / "index.html", _get_full_cockpit_content())
    ]
    
    for fpath, content in files_to_check:
        # 1. Vérifier l'absence totale de SFN comme acronyme ou mot complet
        sfn_matches = re.findall(r"\bSFN\b", content)
        assert len(sfn_matches) == 0, f"Présence du terme SFN détectée dans {fpath.name}: {len(sfn_matches)} occurrences trouvées"
        
        # 2. Vérifier l'absence de "solutions fondées sur la nature"
        assert "solutions fondées sur la nature" not in content.lower(), f"'solutions fondées sur la nature' détecté dans {fpath.name}"
        
        # 3. Vérifier la présence de GDO
        assert "GDO" in content or "gdo" in content.lower(), f"Terme GDO absent de {fpath.name}"

def test_simulation_persistance_and_french_case():
    """Vérifie la présence du cache multi-clé, la synchronisation du bandeau et la casse française."""
    index_html = _get_full_cockpit_content()
    
    # 1. Cache de simulation et synchronisation
    assert "_simulationsCache" in index_html, "Cache _simulationsCache manquant dans templates/index.html"
    assert "mettreAJourIndicateurBassin" in index_html, "Fonction mettreAJourIndicateurBassin manquante"
    assert "Soulagement réseau :" in index_html or "Soulagement du collecteur principal :" in index_html
    
    # 2. Ne jamais afficher un 'ID [cluster_id]' brut dans le badge de bassin
    assert "topBadge.innerText = surfHa || 'ID ' + cidStr;" not in index_html, "Le fallback brut 'ID ' + cidStr ne doit plus exister"
    
    # 3. Casse française standard (pas d'anglicisme Title Case dans les libellés clés)
    assert "Simulation Hydrodynamique SWMM 5.2" not in index_html, "Title Case anglais détecté dans le modal de calcul"
    assert "Simulation hydrodynamique" in index_html, "Formulation française attendue"
    assert "1. Synthèse Stratégique &amp; Avis Décideurs" not in index_html, "Title Case anglais détecté dans le rapport"
    assert "1. Synthèse stratégique et avis des décideurs" in index_html, "Formulation française attendue pour la synthèse"
    assert "Plan d'Action Priorisé" not in index_html, "Title Case anglais détecté pour le plan d'action"
    assert "Plan d'action priorisé" in index_html
    assert "Bilan Débordements" not in index_html
    assert "Bilan des débordements" in index_html

