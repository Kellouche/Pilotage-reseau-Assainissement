# Méthodologie de Partitionnement Hydraulique et Modélisation des Bassins Urbains

## 1. Objectif de la Méthodologie
L'objectif est de transformer une base de données SIG (GeoPackage) en un modèle hydraulique cohérent, capable de segmenter le réseau en **bassins versants exclusifs** rattachés à des exutoires physiques (STEP, Stations, Rejets).

---

## 2. Prérequis Topologiques : La Fondations du Graphe
Pour qu'un algorithme de parcours (type BFS) puisse naviguer dans le réseau, l'intégrité de la donnée est la première condition de réussite.

### A. Continuité Physique (Snapping)
*   **Exigence** : Chaque conduite doit partager un point de coordonnée (X,Y) strictement identique avec le regard ou la conduite adjacente.
*   **Risque** : Une déconnexion invisible (gap) isole tout le réseau amont, créant des "bassins orphelins" ou des résultats sous-estimés (ex: un seul tronçon détecté).
*   **Solution** : Appliquer un nettoyage topologique automatique ("Topological Cleaning") avec une tolérance de 1 à 5 mm.

### B. Orientation Hydraulique (Sens d'Écoulement)
*   **Exigence** : Les lignes doivent être numérisées dans le sens de l'écoulement (Amont vers Aval).
*   **Risque** : Un tronçon dessiné à l'envers agit comme une valve anti-retour pour l'algorithme, bloquant la détection de tout le sous-bassin situé derrière lui.

---

## 3. Paramètres Physiques Critiques (Le "Moteur")
Pour passer d'un schéma topologique à une modélisation réelle, trois paramètres sont indispensables :

### I. Les Altitudes Radier (Invert Elevations)
*   C'est le paramètre décisionnel majeur. En hydraulique gravitaire, la pente dicte la direction, pas le dessin.
*   **Action** : Renseigner les altitudes Z amont et Z aval pour chaque tronçon permet de corriger automatiquement les erreurs d'orientation du SIG.

### II. Les Surfaces Versantes (Subcatchments)
*   Un réseau de tuyaux ne génère pas de débit de lui-même. Le débit provient des surfaces urbaines (toitures, routes).
*   **Action** : Découper le territoire en polygones et lier chaque polygone au **nœud d'injection** (Outlet) le plus proche. C'est cette liaison qui définit l'appartenance réelle d'une zone à un bassin.

### III. Paramètres de Rugosité et Diamètres
*   **Action** : Assurer la cohérence des diamètres et des matériaux (Manning) pour permettre, dans un second temps, le calcul de la capacité (Haut/Bord).

---

## 4. Logique de Partitionnement (Algorithme BFS Multi-Sources)
Notre approche utilise une remontée simultanée depuis tous les exutoires identifiés :
1.  **Identification des Sources** : Repérage de tous les exutoires (Points de sortie).
2.  **BFS Multi-sources** : Chaque exutoire "revendique" les tronçons situés en amont.
3.  **Résolution des Conflits** : En cas de confluence, le tronçon est attribué à l'exutoire le plus proche hydrauliquement (distance de parcours).
4.  **Exclusivité** : Chaque tronçon appartient à un seul et unique bassin, garantissant une sectorisation claire pour la maintenance et l'exploitation.

---

## 5. Diagnostic et Validation
Si un bassin paraît trop petit ou incomplet :
1.  **Vérifier les Orphelins** : Consulter le nombre de tronçons non connectés.
2.  **Test de Connectivité** : Vérifier graphiquement les jonctions au point de rupture.
3.  **Inversion de sens** : Contrôler si les flèches du réseau pointent bien vers l'exutoire.

---

## 6. Conclusion : Vers la Simulation SWMM
Cette méthodologie constitue l'étape 0 de toute modélisation sérieuse. Une fois la topologie assainie et les bassins validés, le passage au format `.inp` de SWMM devient une simple formalité technique, permettant alors de simuler des pluies et de prédire les risques de débordement.

---
*Document Méthodologique - Plateforme de Pilotage Réseau d'Assainissement*
