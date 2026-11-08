# -*- coding: utf-8 -*-
"""
================================================================================
Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
Auteur : Dr Abdelhakim KELLOUCHE
Date de création : 2026-04-20
Date de modification : 2026-11-08
Objet : Script de décomposition modulaire intégrale du cockpit frontend (<600l/fichier)
================================================================================
"""

import os
import subprocess
import jinja2
from pathlib import Path

CANONICAL_HTML_HEADER = """<!--
================================================================================
Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
Auteur : Dr Abdelhakim KELLOUCHE
Date de création : 2026-04-20
Date de modification : 2026-11-08
Objet : {objet}
================================================================================
-->\n"""

CANONICAL_JS_HEADER = """/**
 * ================================================================================
 * Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
 * Auteur : Dr Abdelhakim KELLOUCHE
 * Date de création : 2026-04-20
 * Date de modification : 2026-11-08
 * Objet : {objet}
 * ================================================================================
 */\n\n"""

def save_js(path, objet, code):
    full = CANONICAL_JS_HEADER.format(objet=objet) + code.strip() + "\n"
    with open(path, "w", encoding="utf-8") as out:
        out.write(full)
    cnt = len(full.splitlines())
    res = subprocess.run(["node", "--check", path], capture_output=True, text=True)
    status = "OK" if res.returncode == 0 else f"ERR: {res.stderr.strip()[:100]}"
    print(f"JS Module    : {Path(path).name:<32} : {cnt:>4} l. [{status}]")
    assert cnt <= 600, f"{path} exceeds 600 lines ({cnt})"
    assert res.returncode == 0, f"Syntax error in {path}: {res.stderr}"

def build_modules():
    src_file = "templates/index.original.html" if Path("templates/index.original.html").exists() else "templates/index.html"
    with open(src_file, "r", encoding="utf-8") as f:
        lines = f.readlines()

    os.makedirs("templates/partials", exist_ok=True)
    os.makedirs("static/js/app", exist_ok=True)
    os.makedirs("static/css", exist_ok=True)

    # 1. HTML Partials
    partials = [
        ("templates/partials/sim_blocking_overlay.html", 437, 489, "Overlay plein écran de verrouillage et chronomètre pendant le calcul SWMM"),
        ("templates/partials/topbar.html", 489, 631, "Barre supérieure de navigation SaaS, sélecteur de projet et indicateur central de bassin"),
        ("templates/partials/sidebar_engineering.html", 639, 737, "Panneau latéral d'ingénierie : calques réseau physique, hydrologie et sélection de bassin"),
        ("templates/partials/toolbar_edit.html", 737, 754, "Barre d'outils flottante d'édition hydraulique et sectorisation manuelle"),
        ("templates/partials/modal_edit_attribute.html", 761, 778, "Modale flottante d'édition interactive des attributs des regards et conduites"),
        ("templates/partials/modal_project.html", 7244, 7357, "Modale de sélection de projet réseau, modèles certifiés EPA et téléversement"),
        ("templates/partials/modal_user_profile.html", 7357, 7423, "Modale de gestion du profil utilisateur et mot de passe SaaS"),
        ("templates/partials/modal_simulation.html", 7423, 7852, "Modale de paramétrage de pluie, stations ANRH et déclenchement SWMM 5.2"),
        ("templates/partials/modal_interpretation.html", 7852, 7894, "Modale d'interprétation multi-agents et restitution décisionnelle"),
    ]

    for filename, start, end, objet in partials:
        chunk = "".join(lines[start:end])
        content = CANONICAL_HTML_HEADER.format(objet=objet) + chunk
        with open(filename, "w", encoding="utf-8") as pf:
            pf.write(content)
        cnt = len(content.splitlines())
        print(f"HTML Partial : {filename:<45} : {cnt:>4} lignes")
        assert cnt <= 600, f"{filename} dépasse 600 lignes ({cnt})"

    # 2. Modules JavaScript
    # 2.1 common.js
    save_js("static/js/app/common.js", "Utilitaires de formatage monétaire DZD, cockpit view, overlays et menus navbar", "".join(lines[781:1151]))

    # 2.2 dessin_manuel.js
    save_js("static/js/app/dessin_manuel.js", "Outils de dessin géométrique et sectorisation manuelle de bassins versants", "".join(lines[1151:1457]))

    # 2.3 carte_reseau.js
    save_js("static/js/app/carte_reseau.js", "Initialisation des calques réseau, styles graphiques et infobulles des ouvrages", "".join(lines[1457:1751]))

    # 2.4 bassins_detection.js
    save_js("static/js/app/bassins_detection.js", "Préchargement silencieux, infobulles enrichies et partitionnement des bassins", "".join(lines[1751:2195]))

    # 2.5 bassins_selection.js
    save_js("static/js/app/bassins_selection.js", "Synchronisation du bandeau de bassin, zoom proportionnel et dropdown", "".join(lines[2195:2711]))

    # 2.6 edition_attributs.js
    save_js("static/js/app/edition_attributs.js", "Popups détaillés des tronçons et formulaire d'édition des attributs SIG", "".join(lines[2711:3110]))

    # 2.7 gestion_projet.js
    save_js("static/js/app/gestion_projet.js", "Catalogue des jeux de données, chargement démo, master et import INP/GPKG", "".join(lines[3110:3475]))

    # 2.8 rapport_sections.js
    doc_chunk = "".join(lines[3770:4240])
    rapport_sections_code = f"""
window._construireHtmlRapportDiagnostic = function(simData, meta, k, agents, bufferSens, diag, gc, lid, risk, finance, synth, variantes, ratios, contError, surchargedNodes, floodedNodes, peakOutflow, nbConduites, nbNormal, nbVigilance, nbSurcharge, verdict, verdictCouleur, pName, clusterNom, dateStr) {{
    {doc_chunk.strip()}
    return docHtml;
}};
"""
    save_js("static/js/app/rapport_sections.js", "Modèle HTML et sections analytiques du rapport d'expertise A4 (GDO, BPU, variantes)", rapport_sections_code)

    # 2.9 rapport_print.js
    head_print = "".join(lines[3475:3770])
    tail_print = "".join(lines[4240:4254])
    rapport_print_code = head_print + """
            const docHtml = window._construireHtmlRapportDiagnostic(simData, meta, k, agents, bufferSens, diag, gc, lid, risk, finance, synth, variantes, ratios, contError, surchargedNodes, floodedNodes, peakOutflow, nbConduites, nbNormal, nbVigilance, nbSurcharge, verdict, verdictCouleur, pName, clusterNom, dateStr);
""" + tail_print
    save_js("static/js/app/rapport_print.js", "Génération et impression du rapport d'expertise technique officiel A4", rapport_print_code)

    # 2.10 multi_agents_recommandations.js
    interp_chunk = "".join(lines[4415:4993])
    interp_sections_code = f"""
window._construireHtmlCorpsInterpretation = function(simData, k, cRes, nRes, meta, agents, bufferSens, diag, gc, lid, risk, finance, synth, variantes, ratios, contError, surchargedNodes, floodedNodes, peakOutflow, nbConduites, nbNormal, nbVigilance, nbSurcharge, verdict, verdictCouleur) {{
    {interp_chunk.strip()}
    return html;
}};
"""
    save_js("static/js/app/multi_agents_recommandations.js", "Modèle HTML des onglets experts du collège multi-agents (Diagnostic, GDO, Risques, Finances)", interp_sections_code)

    # 2.11 multi_agents_sensibilite.js
    head_sens = "".join(lines[4254:4415])
    tail_sens = "".join(lines[4993:5015])
    multi_agents_sens_code = head_sens + """
            let html = window._construireHtmlCorpsInterpretation(simData, k, cRes, nRes, meta, agents, bufferSens, diag, gc, lid, risk, finance, synth, variantes, ratios, contError, surchargedNodes, floodedNodes, peakOutflow, nbConduites, nbNormal, nbVigilance, nbSurcharge, verdict, verdictCouleur);
""" + tail_sens
    save_js("static/js/app/multi_agents_sensibilite.js", "Analyse de sensibilité du buffer, modale multi-agents et restitution décisionnelle", multi_agents_sens_code)

    # 2.12 profil_saas.js
    save_js("static/js/app/profil_saas.js", "Gestion du profil utilisateur, sécurité, changement de mot de passe et déconnexion", "".join(lines[5015:5251]))

    # 2.13 resultats_couches.js
    save_js("static/js/app/resultats_couches.js", "Calques cartographiques de résultats : flèches de sens, sous-bassins et focus", "".join(lines[5251:5761]))

    # 2.14 resultats_statistiques.js
    stats_body = "".join(lines[6138:6336])
    stats_code = f"""
window.mettreAJourIndicateursEtKpisSimulation = function(data) {{
    if (!data) return;
    const k = data.kpis || {{}};
    const coh = k.coherence_hydrologique || {{}};
{stats_body}
}};
"""
    save_js("static/js/app/resultats_statistiques.js", "Mise à jour des indicateurs décisionnels, débits hydrologiques et KPIs SWMM", stats_code)

    # 2.15 resultats_affichage.js
    aff_head = "".join(lines[5761:6138])
    aff_tail = "".join(lines[6336:6342])
    res_aff_code = aff_head + """
            if (typeof window.mettreAJourIndicateursEtKpisSimulation === 'function') {
                window.mettreAJourIndicateursEtKpisSimulation(data);
            }
""" + aff_tail
    save_js("static/js/app/resultats_affichage.js", "Affichage des résultats hydrauliques SWMM, coloration des conduites et surcharges", res_aff_code)

    # 2.16 resultats_actions.js
    save_js("static/js/app/resultats_actions.js", "Réinitialisation de la simulation, masquage des couches et restitution au chargement", "".join(lines[6345:6659]))

    # 2.17 simulation_ui.js
    save_js("static/js/app/simulation_ui.js", "Modale de simulation SWMM, sélection pluviométrique et raccordements orphelins", "".join(lines[6659:7203]))

    # 2.18 app_init.js
    save_js("static/js/app/app_init.js", "Démarrage et initialisation de l'application cockpit au chargement DOM", "".join(lines[7203:7243]))

    # 3. Assembler le gabarit templates/index.html compact (< 85 lignes)
    index_content = """<!--
================================================================================
Projet : DrainPilot 5.2 - Plateforme d'Assainissement Urbain & Calcul SWMM
Auteur : Dr Abdelhakim KELLOUCHE
Date de création : 2026-04-20
Date de modification : 2026-11-08
Objet : Cockpit cartographique et SIG modulaire de simulation hydraulique SWMM 5.2
================================================================================
-->
<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>DrainPilot 5.2 - Cockpit Cartographique & Simulation SWMM</title>
    <!-- Fonts -->
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=JetBrains+Mono:wght@500;700;800&display=swap" rel="stylesheet">
    <!-- FontAwesome -->
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <!-- Leaflet CSS -->
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
    <!-- Cockpit Custom CSS Dédié -->
    <link rel="stylesheet" href="/static/css/cockpit.css">
</head>
<body>
    <!-- Overlay de verrouillage simulation -->
    {% include "partials/sim_blocking_overlay.html" %}

    <!-- Topbar & Indicateur Dynamique -->
    {% include "partials/topbar.html" %}

    <div id="app-workspace">
        <!-- Panneau d'Ingénierie Latéral -->
        {% include "partials/sidebar_engineering.html" %}

        <!-- Barre d'outils d'édition hydraulique -->
        {% include "partials/toolbar_edit.html" %}

        <!-- Carte Leaflet Principale -->
        <div id="map"></div>
    </div> <!-- fin app-workspace -->

    <!-- Vue Intégrée Contrôle Qualité -->
    <div id="container-qualite-cockpit" style="display: none; width: 100%; height: calc(100vh - 52px); background: #0f172a;">
        <iframe id="iframe-qualite" src="" style="width: 100%; height: 100%; border: none;"></iframe>
    </div>

    <!-- Modales Partials -->
    {% include "partials/modal_edit_attribute.html" %}
    {% include "partials/modal_project.html" %}
    {% include "partials/modal_user_profile.html" %}
    {% include "partials/modal_simulation.html" %}
    {% include "partials/modal_interpretation.html" %}

    <!-- Bibliothèques Externes -->
    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>

    <!-- Modules Applicatifs JavaScript Découpés (<600 lignes) -->
    <script src="/static/js/app/common.js"></script>
    <script src="/static/js/app/dessin_manuel.js"></script>
    <script src="/static/js/app/carte_reseau.js"></script>
    <script src="/static/js/app/bassins_detection.js"></script>
    <script src="/static/js/app/bassins_selection.js"></script>
    <script src="/static/js/app/edition_attributs.js"></script>
    <script src="/static/js/app/gestion_projet.js"></script>
    <script src="/static/js/app/rapport_sections.js"></script>
    <script src="/static/js/app/rapport_print.js"></script>
    <script src="/static/js/app/multi_agents_recommandations.js"></script>
    <script src="/static/js/app/multi_agents_sensibilite.js"></script>
    <script src="/static/js/app/profil_saas.js"></script>
    <script src="/static/js/app/resultats_couches.js"></script>
    <script src="/static/js/app/resultats_statistiques.js"></script>
    <script src="/static/js/app/resultats_affichage.js"></script>
    <script src="/static/js/app/resultats_actions.js"></script>
    <script src="/static/js/app/simulation_ui.js"></script>
    <script src="/static/js/app/app_init.js"></script>
</body>
</html>
"""
    with open("templates/index.html", "w", encoding="utf-8") as f:
        f.write(index_content.strip() + "\n")

    cnt_index = len(index_content.splitlines())
    print(f"\nIndex Principal: templates/index.html                           : {cnt_index:>4} lignes")
    assert cnt_index <= 600, f"index.html dépasse 600 lignes ({cnt_index})"

    # 4. Vérifier le rendu Jinja2
    env = jinja2.Environment(loader=jinja2.FileSystemLoader("templates"), autoescape=False)
    tpl = env.get_template("index.html")
    rendered = tpl.render()
    assert 'topbar-bassin-container' in rendered, "topbar-bassin-container absent du rendu Jinja"
    assert 'sim-blocking-overlay' in rendered, "sim-blocking-overlay absent du rendu Jinja"
    assert 'map' in rendered, "map absent du rendu Jinja"
    print(f"Validation Jinja2 réussie : rendu assemblé de {len(rendered.splitlines())} lignes.")

if __name__ == "__main__":
    build_modules()
