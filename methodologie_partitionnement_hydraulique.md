# Méthodologie de Partitionnement Hydraulique et Modélisation des Bassins Urbains

## 1. Objectif de la Méthodologie
L'objectif est de transformer une base de données SIG (GeoPackage) en un modèle hydraulique cohérent, capable de segmenter le réseau en **bassins versants exclusifs** rattachés à des exutoires physiques (STEP, Stations, Rejets).

---

## 2. Prérequis Topologiques : La Fondation du Graphe
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
Cette méthodologie constitue l'étape 0 de toute modélisation sérieuse. Une fois la topologie assainie et les bassins validés, le réseau est prêt pour la construction du modèle hydrologique et hydraulique sous EPA SWMM 5.2.

---

## 7. Règles de nomenclature et de création

La plateforme distingue explicitement deux objets :

* **Bassin collecté du réseau** : ensemble de tronçons orientés qui convergent
  vers un exutoire physique identifié (rejet, déversoir, station ou STEP).
* **Bassin versant de surface** : zone hydrologique issue d'un MNT/DEM et de
  surfaces contributives affectées à un nœud d'injection.

Un bassin collecté ne peut donc pas être créé à partir d'un point isolé, d'un
nœud mort non identifié ou d'un exutoire implicite. Il doit contenir au moins
un tronçon et son exutoire doit être présent dans le graphe des ouvrages.
Les sorties sans exutoire physique restent des anomalies ou des composantes
orphelines à corriger ; elles ne sont pas des bassins hydrauliques valides.

Le nom affiché suit le format :
`Bassin hydraulique — <type d'exutoire> <nom/adresse> — rues: <voies drainées>`.
Lorsque l'adresse ou la rue est absente, l'identifiant de l'ouvrage est
conservé afin de garantir un nom non ambigu et traçable.

---

## 8. Transition Méthodologique : Du Graphe SIG au Modèle Dynamique EPA SWMM 5.2

Pour dépasser le stade de l'analyse spatiale statique et faire fonctionner le véritable solveur hydrodynamique EPA SWMM 5.2, la chaîne de traitement formalise les transferts physiques entre la surface du bassin et le collecteur souterrain.

```
+-----------------------------------------------------------------------------------+
|                        1. HYDROLOGIE DE SURFACE (Pluie-Débit)                     |
|  Pluie synthétique (Montana/Chicago) ---> Sous-bassins versants élémentaires      |
|  Pertes par Infiltration (Horton)  ---> Ruissellement net vers regards d'injection|
+-----------------------------------------------------------------------------------+
                                          |
                                          v  [Nœuds d'injection / Jonctions]
+-----------------------------------------------------------------------------------+
|                        2. HYDRAULIQUE SOUTERRAINE (Transport 1D)                  |
|  Équations de Saint-Venant complètes (DYNWAVE) dans le graphe orienté             |
|  Ouvrages spéciaux : Déversoirs d'orage, Pompes, Stockages, Exutoires contrôlés   |
+-----------------------------------------------------------------------------------+
                                          |
                                          v  [Fichier binaire de résultats .out]
+-----------------------------------------------------------------------------------+
|                        3. RESTITUTION DYNAMIQUE & AIDE À LA DÉCISION              |
|  Animation temporelle (Time Slider) : propagation de l'onde de crue               |
|  Coloration dynamique (Taux de charge y/D, vitesses, débordements de voirie)     |
|  Profils en long animés avec ligne piézométrique en charge                        |
+-----------------------------------------------------------------------------------+
```

### 8.1 Génération Automatique des Sous-Bassins Versants Élémentaires (`[SUBCATCHMENTS]`)
Un réseau de canalisations sans hydrologie de surface reste sec. La plateforme découpe l'espace urbain en sous-bassins élémentaires associés à chaque regard :
1. **Partitionnement polygonal de Voronoï / Thiessen** : Chaque regard d'assainissement devient le centre d'une cellule de surface contributive, bornée par l'enveloppe du bassin hydraulique urbain détecté.
2. **Attribution au nœud d'injection (`Outlet`)** : La totalité des eaux de ruissellement générées sur ce sous-bassin se déverse dans le regard central.
3. **Largeur caractéristique hydraulique ($W$)** :
   $$W = \frac{\text{Surface}}{L_{\max}}$$
   où $L_{\max}$ représente la plus grande longueur de parcours de surface vers le regard.
4. **Pente moyenne de surface ($S$)** : Déduite automatiquement par croisement zonal avec le MNT raster local (interpolation bilinéaire des altitudes).
5. **Coefficient d'imperméabilisation ($\%Imperv$)** :
   * Zones imperméables ($70\text{ à }90\,\%$) : voiries, toitures et enrobés urbains.
   * Zones perméables ($10\text{ à }30\,\%$) : espaces verts, cœurs d'îlots végétalisés, terrains vagues.

### 8.2 Modélisation de l'Infiltration et des Dépressions (`[INFILTRATION]` & `[SUBAREAS]`)
Les pertes initiales et continues de surface sont modélisées selon la méthode de Horton :
$$f(t) = f_c + (f_0 - f_c) \cdot e^{-k \cdot t}$$
* **$f_0$** (capacité d'infiltration initiale) : $75.0\text{ mm/h}$ (sol sec).
* **$f_c$** (capacité d'infiltration à saturation) : $10.0\text{ mm/h}$.
* **$k$** (taux de décroissance) : $4.0\text{ h}^{-1}$.
* **Stockage de dépression ($D_{\text{store}}$)** : $1.5\text{ mm}$ sur zone imperméable, $5.0\text{ mm}$ sur zone perméable.
* **Rugosités de Manning de surface** : $N_{\text{imperv}} = 0.015$, $N_{\text{perv}} = 0.250$.

### 8.3 Sollicitations Météorologiques et Pluies de Projet (`[RAINGAGES]` & `[TIMESERIES]`)
Pour dimensionner ou diagnostiquer les insuffisances de réseau, la plateforme génère des hyétogrammes étalonnés :
1. **Loi de Montana locale** :
   $$i(t) = a(T) \cdot t^{-b(T)}$$
   pour les périodes de retour décennale ($T = 10\text{ ans}$), cinquantennale ($T = 50\text{ ans}$) et vicennale ($T = 20\text{ ans}$).
2. **Pluie synthétique symétrique (Type Chicago)** : Répartition de l'intensité avec pointe au tiers ou à la moitié de la durée de l'averse (durée standard $2\text{ h}$ ou $4\text{ h}$, pas de temps de discrétisation $5\text{ min}$).
3. **Pluies réelles de terrain** : Importation de chroniques pluviométriques enregistrées (format temps/hauteur) pour le recalage post-orage.

### 8.4 Débits de Temps Sec et Régime Unitaire / Séparatif (`[DWF]`)
En assainissement unitaire ou eaux usées strictes :
* Dotation volumétrique moyenne : $150\text{ L/habitant/jour}$ ou débit métrique par regard source.
* Profils horaires journaliers (*Diurnal Patterns*) pour reproduire la pointe du matin ($07\text{h}-09\text{h}$), le creux d'après-midi et la pointe du soir ($19\text{h}-21\text{h}$).

### 8.5 Singularités Hydrauliques et Ouvrages Spéciaux
Le transport ne se résume pas à des conduites circulaires :
* **Déversoirs d'orage (`[WEIRS]`)** : Crête de déversement orientée vers le milieu naturel ou un exutoire secondaire pour écrêter les débits unitaires de pointe.
* **Stations de relevage / Pompes (`[PUMPS]`)** : Courbe caractéristique $Q = f(\Delta H)$ et gestion des seuils marche/arrêt dans les bâches de pompage.
* **Bassins de rétention (`[STORAGE]`)** : Courbe surface/hauteur $A = f(z)$ pour modéliser le stockage tampon et les surverses.
* **Conditions aux limites d'exutoires (`[OUTFALLS]`)** : Exutoires libres (`FREE`), avec clapet anti-retour (`GATED`), ou à cote imposée (`FIXED` ou `STAGE`) lors de crues d'oued en aval.

### 8.6 Résolution Numérique : Onde Dynamique (`DYNWAVE`) via `pyswmm`
Pour refléter la physique réelle des écoulements transitoires en réseau urbain, la plateforme impose le solveur complet d'onde dynamique (**Saint-Venant 1D**) :
* **Équations résolues** : Conservation de la masse et de la quantité de mouvement (termes d'accélération convective et locale, frottement, gradient de pression).
* **Phénomènes physiques capturés** : Mise en charge sous pression des canalisations, ondes de retour d'aval (*backwater effects*), oscillations de niveau dans les cheminées d'équilibre, débordements en surface avec rétention temporaire sur voirie (`ALLOW_PONDING YES`).
* **Exécution native C via `pyswmm`** : La simulation s'exécute directement via le binding C embarqué de l'EPA SWMM 5.2, garantissant une exécution native sans dépendance à un exécutable externe en ligne de commande.

### 8.7 Post-Traitement des Résultats Binaires (`.out`) et KPIs d'Ingénierie
L'exploitation des résultats ne s'arrête pas au fichier texte `.rpt`. Le moteur extrait les séries chronologiques complètes depuis le fichier binaire `.out` :
* **Taux de charge maximal ($y_{\max} / D$)** : Cartographie des conduites saturées ($y/D \ge 1.0$) et sous pression.
* **Volumes et durées d'inondation de voirie** : Volume cumulé ($V_{\text{flood}}$ en $\text{m}^3$) et durée de submersion pour chaque regard défaillant.
* **Vérification dynamique d'autocurage** : Identification des conduites où la vitesse reste inférieure à $0.60\text{ m/s}$ au pic de temps sec (risque d'envasement prédictif).
* **Bilan de continuité** : Validation de l'erreur massique ($< 1.0\,\%$ exigé pour certifier la convergence du calcul).

### 8.8 Restitution Temporelle et Ergonomie Décisionnelle dans le Cockpit
1. **Curseur temporel (Time Slider)** : Navigation fluide le long des 24 heures de la simulation avec interpolation dynamique de l'état du réseau.
2. **Animation thématique de la carte Leaflet** :
   * Canalisations en vert ($y/D < 0.70$), orange ($0.70 \le y/D < 1.0$), violet clignotant ($y/D \ge 1.0$ - mise en charge).
   * Regards en rouge pulsation dès l'apparition d'un débit de débordement ($Q_{\text{debord}} > 0$).
3. **Hydrogrammes interactifs** : Graphique dynamique (Chart.js) au clic sur n'importe quel collecteur ou nœud, affichant l'évolution conjointe du débit $Q(t)$, de la vitesse $V(t)$ et du tirant d'eau $y(t)$.
4. **Profil en long hydraulique animé** : Visualisation en coupe montrant la surface libre monter, atteindre la couronne du tuyau et déborder au niveau du tampon lors du passage de l'onde de crue.
