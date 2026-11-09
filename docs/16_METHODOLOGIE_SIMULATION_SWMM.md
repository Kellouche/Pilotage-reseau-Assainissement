# Méthodologie & Architecture de Simulation EPA SWMM 5.2

> **Document de référence scientifique et opérationnel**  
> **Auteur :** Dr Abdelhakim Kellouche  
> **Application :** SWMM Platform SaaS  
> **Version :** 2.2.0  
> **Date :** 01 Novembre 2026  

---

## 1. Objectifs & Cadre Scientifique

Ce document formalise l'intégration du moteur de calcul officiel **EPA SWMM 5.2** (Storm Water Management Model) au sein de la plateforme web **SWMM Platform SaaS**.

Contrairement aux approches forfaitaires simplifiées (méthode rationnelle statique), le module implémente :
1. Une **décomposition hydrologique surfacique rigoureuse** par polygones de Voronoï rattachés aux regards de visite.
2. Une infiltration dynamique selon le modèle de **Horton**.
3. La résolution hydrodynamique complète des **équations de Saint-Venant 1D** en régime non permanent via l'algorithme d'onde dynamique (**Dynamic Wave - DYNWAVE**).
4. La traduction cartographique interactive des surcharges, débits de pointe et inondations en surface.

---

## 2. Démarche Hydrologique & Sectorisation de Surface

### 2.1 Découpage spatial par polygones de Voronoï / Thiessen

Chaque regard de visite $N_i$ constitue le récepteur hydrologique d'un sous-bassin versant élémentaire $SB_i$.

* **Algorithme géométrique** :
  $$\mathcal{V}(N_i) = \{ p \in \Omega \mid \|p - N_i\| \le \|p - N_j\|, \forall j \ne i \}$$
  L'enveloppe $\Omega$ est bornée par le buffer morphologique du réseau (35 mètres autour de chaque canalisation et regard).
* **Propriétés physiques calculées par sous-bassin** :
  * **Surface drainée** $A$ (calculée en hectares $ha$ et $m^2$).
  * **Largeur hydraulique caractéristique** $W$ :
    $$W = \sqrt{A_{\text{sub}}}$$
  * **Pente moyenne** $S$ : extraite du modèle altimétrique ($0.5\%$ par défaut).
  * **Coefficient d'imperméabilisation** : $70\%$ en zone urbaine dense.

### 2.2 Modèle d'Infiltration de Horton

L'infiltration de l'eau météorique dans le sol est calculée selon la loi différentielle de Horton :

$$f(t) = f_c + (f_0 - f_c) e^{-k t}$$

Où :
* $f_0 = 75.0\text{ mm/h}$ : Capacité d'infiltration initiale (sol sec).
* $f_c = 10.0\text{ mm/h}$ : Capacité d'infiltration ultime à saturation.
* $k = 4.0\text{ h}^{-1}$ : Constante de décroissance.
* Temps de ressuyage complet : $7.0\text{ jours}$.

### 2.3 Système de Codification & Numérotation des Entités (Regards, SB, Tronçons)

Pour garantir une interopérabilité sans faille entre le SIG patrimonial de la ville, le modèle mathématique EPA SWMM 5.2 et les équipes d'exploitation terrain, la codification repose sur des règles strictes :

1. **Regards de visite (Junctions dans SWMM)** :
   * **Règle** : Les nœuds conservent **exactement leur identifiant patrimonial SIG d'origine** (attribut `Code`, ex. `2653`, `2654`, `6033`, etc.).
   * **Justification d'ingénierie** : Une renumérotation arbitraire (1, 2, 3...) briserait le lien avec les plans de récolement et les fiches d'inspection télévisée (ITV). L'exploitant intervenant sur la chaussée doit retrouver immédiatement le regard physique n° 2653.

2. **Sous-bassins versants élémentaires (Subcatchments dans SWMM)** :
   * **Règle** : Chaque sous-bassin porte le préfixe normalisé `SB_` suivi du code du regard qui constitue son exutoire :
     $$\text{ID}_{\text{Subcatchment}} = \text{"SB\_"} + \text{Code}_{\text{Regard}}$$
   * **Exemple** : Le sous-bassin versant drainant vers le regard `2653` est nommé **`SB_2653`** avec `Outlet = 2653`.
   * **Signification de `SB`** : Acronyme universel pour **Sub-Basin / SubCatchment** imposé par la nomenclature EPA SWMM.
   * **Avantage** : En inspectant n'importe quel polygone vert sur la carte ou dans le rapport `.rpt`, l'ingénieur identifie instantanément l'ouvrage récepteur sans avoir à chercher de table de correspondance.

3. **Canalisations (Conduits dans SWMM)** :
   * **Règle dans le fichier .inp** : Codification indexée `C_1`, `C_2`, ..., `C_58`.
   * **Règle dans l'interface et les popups** : Affichage prioritaire du parcours topologique amont-aval : **`ID_AMONT ➔ ID_AVAL`** (ex. `2674 ➔ 2673`), avec diamètre ($mm$) et longueur ($m$).

4. **Exutoire principal (Outfall dans SWMM)** :
   * Identifié par le code du regard le plus proche géographiquement du point de rejet vers le milieu récepteur.

---

## 3. Scénarios Pluviométriques de Sollicitation & Référentiel Certifié

Le moteur SWMM 5.2 s'appuie désormais sur le **Référentiel National des Données Pluviométriques d'Algérie** certifié ANRH / UHBC / ONA (voir [`REFERENTIEL_PLUVIOMETRIE_ALGERIE.md`](REFERENTIEL_PLUVIOMETRIE_ALGERIE.md)).

Les sollicitations sont générées dynamiquement sous forme de séries temporelles (`[TIMESERIES]`) selon la loi de Montana $I(t) = 60 \cdot a \cdot t^{-b}$ et le modèle de Chicago centré ($r=0.40$), associées au pluviomètre numérique SWMM (`[RAINGAGES]`).

### 3.1 Sollicitations de Référence — Station ANRH Chlef Siège (Code 010501 - UHBC)

| Scénario | Période de Retour $T$ | Durée Simulation | Intensité Crête ($I_{\max}$) | Formule de Montana (UHBC / ANRH) | Hauteur $P_{24}$ |
|---|---|---|---|---|---|
| **Pluie Décennale** (Standard ONA) | $T = 10\text{ ans}$ | 4 heures | **$74.9\text{ mm/h}$** | $I(t) = 9.334 \cdot t^{-0.745}$ ($t_c = 15\text{ min}$) | $56.0\text{ mm}$ |
| **Pluie Cinquantennale** (Crise Majeure) | $T = 50\text{ ans}$ | 4 heures | **$120.0\text{ mm/h}$** | $I(t) = 15.795 \cdot t^{-0.760}$ | $81.0\text{ mm}$ |
| **Pluie Centennale** (Crue Historique) | $T = 100\text{ ans}$ | 4 heures | **$144.5\text{ mm/h}$** | $I(t) = 19.338 \cdot t^{-0.764}$ | $94.0\text{ mm}$ |
| **Pluie Biennale** (Exploitation) | $T = 2\text{ ans}$ | 4 heures | **$45.0\text{ mm/h}$** | $I(t) = 5.250 \cdot t^{-0.720}$ | $34.0\text{ mm}$ |
| **Orage Brutal d'Été** (Convectif) | $T \approx 20\text{ ans}$ | 2 heures | **$92.5\text{ mm/h}$** | Averse orageuse convective ($a=11.823$) | $66.5\text{ mm}$ |
| **Temps Sec Pur** | Étiage DWF | 24 heures | **$0.0\text{ mm/h}$** | Transit exclusif des eaux usées sans ruissellement | $0.0\text{ mm}$ |

### 3.2 Flexibilité & Saisie Manuelle Ingénieur

* **Sélecteur de stations** : Couvre 7 stations de la Wilaya de Chlef (Chlef Siège, Oum Drou, Oued Fodda, Bénaïria, Domaine Si Tayeb, Ténès, Boukadir) et d'autres bassins régionaux.
* **Surcharge de l'intensité ($I_{\max}$)** : L'ingénieur peut ajuster l'intensité de crête directement dans l'interface pour tester des scénarios d'inondation personnalisés.
* **Traçabilité intégrale** : Chaque simulation conserve et affiche dans ses métadonnées et son rapport la station retenue, le code ANRH, les coefficients de Montana et la pluie journalière $P_{24}$.

---

## 4. Résolution Hydraulique 1D (Saint-Venant — DYNWAVE)

### 4.1 Équations fondamentales

L'onde dynamique (**DYNWAVE**) résout simultanément les équations de continuité et de quantité de mouvement 1D :

$$\frac{\partial A_c}{\partial t} + \frac{\partial Q}{\partial x} = 0$$

$$\frac{\partial Q}{\partial t} + \frac{\partial}{\partial x} \left(\frac{Q^2}{A_c}\right) + g A_c \frac{\partial H}{\partial x} + g A_c S_f = 0$$

Où :
* $A_c$ : Section mouillée de la conduite ($m^2$).
* $Q$ : Débit instantané ($m^3/s$).
* $H$ : Cote piézométrique ($m$).
* $S_f = \frac{n^2 |Q| Q}{A_c^2 R_h^{4/3}}$ : Pente de frottement de Manning-Strickler ($n=0.013$ pour le béton).

### 4.2 Critère de validation & Bilan de continuité massique

Selon les normes de l'US EPA, une simulation hydrodynamique n'est scientifiquement valide que si l'erreur de bilan de masse (**Mass Continuity Error**) reste strictement inférieure à $\pm 5\%$.

Sur le réseau témoin (`data/demo_reseau.gpkg`) :
* **Erreur de continuité de routage** : **$-0.166\%$** (Excellente précision numérique).
* **Erreur de ruissellement** : **$-4.182\%$** (Parfaitement conforme $< 5\%$).
* **Temps de calcul** : $\approx 1.0\text{ seconde}$ sur machine standard.

---

## 5. Cartographie Thématique & Post-Traitement des Résultats

Le rapport de calcul officiel SWMM (`.rpt`) fait l'objet d'un parsing certifié pour alimenter les couches thématiques Leaflet :

### 5.1 Taux de charge des canalisations ($Q / Q_{max}$)

| Taux de charge | Couleur | Statut Hydraulique | Interprétation d'Ingénierie |
|---|---|---|---|
| **$Q/Q_{max} < 50\%$** | 🟢 `#10b981` | Normal | Capacité largement suffisante, écoulement à surface libre sain. |
| **$50\% \le Q/Q_{max} < 80\%$** | 🟡 `#facc15` | Modéré | Fonctionnement capacitaire satisfaisant. |
| **$80\% \le Q/Q_{max} < 100\%$** | 🟠 `#f97316` | Critique | Conduite proche du point de saturation. |
| **$Q/Q_{max} \ge 100\%$ ou $H/D \ge 1.0$** | 🔴 `#ef4444` | Surcharge | Conduite en charge hydraulique (mise sous pression). |

### 5.2 Surcharges et Débordements des Regards de Visite

* **Regards en mise en charge (orange)** : L'eau monte dans la cheminée du regard au-dessus de la génératrice supérieure de la canalisation sans atteindre la cote du terrain naturel ($COTETN$).
* **Regards en débordement / inondation (rouge)** : L'eau submerge le tampon de voirie ($COTETN$) et inonde la chaussée. L'analyse quantifie :
  * La **durée d'inondation** en heures ($h$).
  * Le **débit de pointe débordé** ($m^3/s$).
  * Le **volume total refoulé sur chaussée** ($m^3$).

### 5.3 Légende Cartographique Interactive & Sémiologie Graphique

L'application intègre une légende cartographique flottante (ancrée en bas à droite de la carte Leaflet, minimisable à tout moment), structurée en 3 blocs d'ingénierie :
1. **Taux de charge des canalisations ($Q/Q_{\max}$)** :
   * 🟢 Vert `< 50%` : Écoulement libre à surface libre sain.
   * 🟡 Jaune `50% - 80%` : Sollicitation modérée.
   * 🟠 Orange `80% - 100%` : Capacité critique, proche de la mise en charge.
   * 🔴 Rouge `> 100%` : Conduite en charge hydraulique (mise sous pression).
2. **Statut des regards de visite** :
   * 🟠 Pastille orange : Surcharge hydraulique (confinée dans la cheminée).
   * 🔴 Pastille rouge clignotante : Débordement au sol / inondation voirie.
3. **Composantes spatiales et hydrologiques** :
   * 🟩 Polygones de Voronoï : Délimitation surfacique des sous-bassins ($ha$).
   * ➤ Chevrons bleus cyan : Sens d'écoulement Amont $\rightarrow$ Aval.

### 5.4 Sens d'Écoulement Vectoriel Discret (Amont ➔ Aval)

Afin d'éviter toute saturation visuelle de la carte tout en offrant une lecture directionnelle infaillible, le sens d'écoulement est modélisé comme suit :
* **Calcul trigonométrique vectoriel** : L'angle de rotation $\theta$ est calculé au point médian de chaque conduite à partir des coordonnées exactes des regards amont et aval :
  $$\theta = \operatorname{atan2}(-\Delta y, \, \Delta x \cdot \cos(\text{lat})) \times \frac{180}{\pi}$$
* **Sémiologie graphique non intrusive** : Chevrons discrets (`➤`), de 13px, couleur cyan (`#38bdf8`), opacité à 85%, assortis de la propriété CSS `pointer-events: none` afin de ne jamais gêner la sélection ou l'interrogation des regards et conduites.
* **Débrayage utilisateur** : La couche est masquée par défaut et activable d'un clic via les volets Réseau et Résultats de simulation.

---

## 6. Compréhension & Diagnostic des Phénomènes Hydrauliques Complexes

Cette section fournit les fondements scientifiques nécessaires aux exploitants et hydrauliciens pour interpréter les résultats fournis par le moteur EPA SWMM 5.2.

### 6.1 Distinction Physique : Surcharge (*Node Surcharge*) vs Débordement (*Node Flooding*)

Dans le formalisme hydrodynamique de SWMM, l'état d'un nœud (regard de visite) est déterminé par la position relative de la **ligne piézométrique** ($HGL$ – *Hydraulic Grade Line*) par rapport à la géométrie de l'ouvrage :

```
             Cote Tampon / Terrain Naturel (Rim Elevation : z_tampon)
     ═════════════════════════════════════════════════════════════════  ◄── Surface Voirie
                     │                      │
                     │    Cheminée du       │  ▲  Zone de SURCHARGE
                     │      regard          │  │  (Eau sous pression confinée
                     │                      │  ▼   dans l'ouvrage souterrain)
     ────────┬───────┴──────────────────────┴───────┬────────
             │   Génératrice Supérieure (Crown)     │  ◄── Sommet conduite (z_radier + D)
             │          (Conduite)                  │
     ────────┴──────────────────────────────────────┴────────  ◄── Radier (Invert : z_radier)
```

#### A. La Surcharge (*Node Surcharge* ou *Mise en charge*)
* **Condition mathématique** :
  $$z_{\text{radier}} + D < H_{\text{piezo}} \le z_{\text{tampon}}$$
* **Interprétation hydraulique** :
  1. La conduite d'évacuation est remplie à 100% de sa section géométrique ($H/D = 1$).
  2. L'écoulement cesse d'être à surface libre (régime gravitaire de Manning-Strickler) et passe en **régime sous pression**.
  3. L'excès de charge dynamique et piézométrique force la colonne d'eau à remonter à l'intérieur de la cheminée verticale du regard.
  4. **Impact environnemental et urbain** : Tant que la ligne piézométrique ne dépasse pas la cote tampon ($z_{\text{tampon}}$), **il n'y a aucun débordement en surface ni inondation sur la voirie**. Le regard agit comme un tube piézométrique fermé.

#### B. Le Débordement (*Node Flooding* ou *Inondation de voirie*)
* **Condition mathématique** :
  $$H_{\text{piezo}} > z_{\text{tampon}}$$
* **Interprétation hydraulique** :
  1. La capacité de stockage verticale de la cheminée du regard est totalement dépassée.
  2. La pression expulse l'eau par les ouvertures du tampon (ou soulève la fonte de voirie).
  3. L'eau jaillit hors de l'ouvrage et s'écoule à l'air libre sur la chaussée.
  4. **Gestion dans SWMM** :
     * En mode par défaut (`Ponding = NO`), le débit excédentaire est comptabilisé comme "perdu" du réseau souterrain. SWMM chiffre avec exactitude le débit crête refoulé ($m^3/s$), la durée de la submersion ($h$) et le volume total inondé ($m^3$).
     * En mode étalement de surface (`Ponding = YES`), une zone de stockage superficiel temporaire permet à l'eau inondée de réintégrer le réseau lorsque la ligne piézométrique souterraine redescend.

---

### 6.2 Analyse du « Paradoxe Hydraulique » : Débordement en Amont vs Exutoire Calme

Une observation fréquente déroute les exploitants : **comment un réseau peut-il déborder ou entrer en forte surcharge en tête de bassin (loin en amont), alors que les collecteurs avals et l'exutoire principal affichent un taux de charge très modéré ($< 50\%$) ?**

Ce comportement n'est pas une anomalie de calcul, mais la conséquence directe de **4 lois physiques et hydrodynamiques couplées** :

#### 1. L'effet d'échelle du diamètre (Loi de Manning-Strickler en puissance $D^{8/3}$)
* En tête de réseau (amont), les diamètres sont étroits (ex. $\varnothing 200\text{ mm}$ à $\varnothing 300\text{ mm}$).
* À l'approche de l'exutoire, le collecteur principal est un émissaire large (ex. $\varnothing 800\text{ mm}$ à $\varnothing 1200\text{ mm}$).
* La capacité de transport maximale à pleine section d'une conduite circulaire s'exprime par :
  $$Q_{\text{max}} = K \cdot S^{1/2} \cdot \left(\frac{\pi D^2}{4}\right) \cdot \left(\frac{D}{4}\right)^{2/3} = \frac{\pi K S^{1/2}}{4 \cdot 4^{2/3}} \cdot D^{8/3} \approx C \cdot D^{2.67}$$
* **Conséquence quantitative** :
  * Pour un diamètre passant de $\varnothing 250\text{ mm}$ à $\varnothing 800\text{ mm}$ (ratio de 3.2), la capacité d'évacuation est multipliée par :
    $$\left(\frac{800}{250}\right)^{8/3} = 3.2^{2.67} \approx 22.3$$
  * Le collecteur aval évacue **plus de 22 fois plus d'eau** qu'une conduite amont pour une pente similaire. Il dispose donc d'une marge de sécurité capacitaire colossale.

#### 2. Le goulot d'étranglement de pente motrice ($S$)
* La capacité d'une canalisation est proportionnelle à la racine carrée de sa pente motrice : $Q \propto \sqrt{S}$.
* Si un tronçon amont présente une pente très faible (ex. $0.1\%$ ou $0.05\%$) ou un contre-dénivelé local, sa capacité réelle s'effondre. L'eau ne s'évacue pas assez vite, ce qui crée une retenue hydraulique amont immédiate.
* Inversement, si le collecteur aval vers l'exutoire bénéficie d'une pente dynamique confortable ($1.0\%$ à $2.5\%$), l'écoulement s'y effectue à grande vitesse sans encombrement.

#### 3. Le temps de concentration ($t_c$) et le déphasage des pointes
* **Sous-bassins amont** : De faible étendue ($0.1$ à $0.5\text{ ha}$), leur temps de concentration est ultra-court ($t_c \sim 5\text{ à }10\text{ minutes}$). Lorsque survient le pic d'intensité de la pluie décennale (ex. $92\text{ mm/h}$), l'intégralité du ruissellement amont converge **simultanément et brutalement** vers le regard de tête, provoquant une pointe instantanée ingérable par la petite canalisation.
* **Exutoire aval** : L'exutoire draine l'ensemble des 13 hectares du bassin. Les hydrogrammes des sous-bassins amont mettent du temps à voyager dans les conduites (temps de transfert hydraulique). Ce temps étale l'arrivée des débits : la pointe globale à l'exutoire est retardée et bien plus amortie que la somme brute des pointes amont.

#### 4. Le laminage et l'amortissement d'onde par Saint-Venant 1D
* Le moteur DYNWAVE de SWMM 5.2 résout les équations dynamiques complètes incluant les termes d'inertie $\frac{\partial}{\partial x}\left(\frac{Q^2}{A}\right)$ et de pression $g A \frac{\partial H}{\partial x}$.
* Lorsque les conduites amont s'engorgent et que l'eau remonte dans les regards (ou déborde en voirie), **ces ouvrages agissent physiquement comme des bassins de rétention temporaires (stockage en ligne)**.
* Ce phénomène de laminage tronque le pic de crue : une fraction volumique est temporairement piégée en amont, ce qui lisse l'hydrogramme transmis vers l'aval. L'onde de crue qui parvient à l'exutoire est aplatie et étalée, évitant ainsi toute saturation de l'émissaire terminal.

---

## 7. Endpoints API Associés

| Endpoint | Méthode | Rôle |
|---|---|---|
| `/api/v1/network/subcatchments` | `GET` | GeoJSON des 59 sous-bassins Voronoï avec surfaces ($ha$), pentes et exutoires. |
| `/api/v1/simulations/scenarios` | `GET` | Liste des scénarios pluviométriques et paramètres du solveur. |
| `/api/v1/simulations/run` | `POST` | Exécute la simulation SWMM 5.2 et renvoie KPIs + cartographies thématiques. |
| `/api/v1/simulations/latest` | `GET` | Récupère instantanément la dernière simulation pour affichage persistant. |
| `/api/v1/simulations/download/inp` | `GET` | Téléchargement du fichier source `.INP` assemblé. |
| `/api/v1/simulations/download/rpt` | `GET` | Téléchargement officiel du rapport de calcul `.RPT` certifié. |

---

## 9. Variante 0 : Raccordements Opportunistes & Ouvrages Spéciaux Orphelins

Lors de l'analyse cartographique d'un sous-bassin saturé, le système détecte automatiquement les **ouvrages spéciaux orphelins** présents dans le SIG à proximité immédiate (Stations de relevage, Déversoirs d'orage DVO, Trop-pleins de secours) qui ne sont pas topologiquement reliés au réseau principal.

### 9.1 Règles de Génie Civil & Hydraulique Automatisées

1. **Non-cisaillement des canalisations existantes** :
   Le tracé de raccordement candidat est analysé spatialement contre la géométrie du réseau (`cand_line.crosses(network_geom)`). Tout tracé traversant une canalisation existante est rejeté au profit du regard d'accès direct le plus proche sans cisaillement.

2. **Appariement Station de Relevage + Trop-plein de secours** :
   Lorsqu'un trop-plein est situé à moins de 30 m d'une station de relevage, ils forment un complexe unitaire. Le système aligne automatiquement le regard de tête du trop-plein sur celui de la station (ex. Regard 7197 à Hay Houria) afin d'éviter tout croisement en ciseaux et d'assurer une évacuation gravitaire des pointes de crue sans refoulement.

3. **Cadrage cartographique et clarté décisionnelle** :
   Lors de la restitution des résultats SWMM :
   * Le zoom de la carte Leaflet est automatiquement verrouillé et centré sur le périmètre exact du cluster simulé (`fitBounds(res_conduites.getBounds())`).
   * Les couches SIG globales de la ville (rejets directs distants, ouvrages hors zone, STEP) sont masquées pour éviter toute confusion visuelle.
   * Si l'ingénieur décoche les raccordements, aucun collecteur de secours n'est injecté dans le modèle `.INP` et aucun tracé n'apparaît sur la carte.

4. **Indicateurs clés de délestage (KPIs)** :
   Le cockpit et le bandeau supérieur affichent distinctement le débit délesté par les ouvrages de secours (`+XXX L/s`), permettant au décideur d'évaluer immédiatement l'efficacité de la Variante 0 face au goulot d'étranglement de l'exutoire principal.

---

## 10. Interopérabilité Universelle EPA SWMM 5.2 (.INP)

### 10.1 Export Calibré pour EPA SWMM Desktop GUI
Afin de garantir une ouverture directe et sans manipulation dans le logiciel officiel EPA SWMM 5.2 Desktop (`epaswmm5.exe`), l'exportateur `.inp` injecte automatiquement la section cartographique :
```ini
[MAP]
DIMENSIONS  xmin  ymin  xmax  ymax
Units       Meters
```
Les dimensions sont calculées dynamiquement sur l'emprise UTM du réseau avec une marge de 8%, permettant un centrage immédiat dès l'ouverture du fichier dans le logiciel officiel.

### 10.2 Ingestion Universelle de Fichiers .INP Externes
DrainPilot accepte le téléversement direct de fichiers `.inp` externes provenant de n'importe quel bureau d'études ou outil de CAO/SIG (EPA SWMM, PCSWMM, Civil 3D, InfoWorks) :
* **Parsing modulaire** (`src/domain/inp_parser.py`) : Extraction des sections `[JUNCTIONS]`, `[OUTFALLS]`, `[STORAGE]`, `[CONDUITS]`, `[XSECTIONS]`, `[SUBCATCHMENTS]`, `[COORDINATES]`, `[VERTICES]`, `[POLYGONS]`.
* **Détection automatique du CRS** : Reconnaissance des projections métriques (UTM Zone 31N Algérie - EPSG:32631) ou géographiques (WGS84).
* **Génération GeoPackage standardisée** : Conversion instantanée en couches exploitables par l'ensemble des modules DrainPilot (carte interactive, découpage Voronoï, simulation native, graphes de pente et audit IA).



---

## 11. Profil en Long Hydraulique, Plan d'Eau Réel (WSP) et Ligne de Charge (HGL)

Le module de profil en long hydraulique restitue le comportement de l'écoulement gravitaire et en charge le long de n'importe quel axe d'assainissement entre un regard amont et un regard aval.

### 11.1 Algorithme d'Extraction du Chemin Topologique
1. **Recherche de chemin orienté (Dijkstra)** :
   À partir du graphe topologique orienté amont $\rightarrow$ aval du cluster simulé, l'algorithme recherche le plus court chemin hydraulique continu reliant le nœud amont (`node_amont`) au nœud aval (`node_aval`).
2. **Reconstitution des cotes altimétriques absolues** :
   Pour chaque regard $i$ de la branche :
   * **Cote radier (fil d'eau)** : $z_{\text{radier}, i}$ (en mètres NGF).
   * **Génératrice supérieure (extrados / haut de conduite)** : 
     $$z_{\text{haut}, i} = z_{\text{radier}, i} + \frac{D_i}{1000}$$
   * **Cote du terrain naturel (MNT / tampon)** : $z_{\text{terrain}, i} = z_{\text{radier}, i} + \text{Profondeur}_i$.
3. **Ligne de charge hydraulique réelle (HGL - Hydraulic Grade Line)** :
   Extraite directement de la simulation dynamique EPA SWMM 5.2 :
   $$HGL_i = z_{\text{radier}, i} + y_{\max, i}$$
   où $y_{\max, i}$ est la hauteur d'eau maximale calculée au nœud $i$ par la résolution de Saint-Venant 1D.

### 11.2 Représentation Graphique aux Standards d'Ingénierie
* **Plan d'eau réel dans les canalisations (Water Surface Profile - WSP)** :
  La conduite est représentée par un rectangle fermé entre le radier et l'extrados. Une couche bleue semi-transparente matérialise le remplissage d'eau réel :
  $$y_{\text{eau}} = \min(y_{\text{noeud}}, D)$$
  permettant d'identifier immédiatement si l'écoulement est à surface libre (partiellement rempli) ou à pleine section.
* **Zone de mise en charge sous pression (Hachurage distinctif)** :
  Lorsque $HGL > z_{\text{haut}}$, la conduite fonctionne sous pression. La colonne d'eau remonte dans la cheminée du regard : la zone d'énergie piézométrique comprise entre l'extrados de la canalisation et la ligne $HGL$ est visualisée avec un motif de hachures diagonales bleues.
* **Détection du débordement en surface** :
  Lorsque :
  $$HGL \ge z_{\text{terrain}}$$
  le regard est en situation de débordement critique au sol. Une pastille rouge vif et une alerte de crise sont générées automatiquement.
* **Édition interactive & flexibilité** :
  L'utilisateur peut définir la branche soit en cliquant sur deux regards sur la carte, soit en éditant directement les champs de texte **Amont :** et **Aval :** du panneau pour recalculer instantanément le profil.

---

## 12. Propagation Temporelle de l'Onde de Crue (Time Slider Dynamique)

### 12.1 Extraction des Séries Temporelles SWMM 5.2
Lors de chaque simulation dynamique sous pluie d'orage Chicago/Montana, le solveur enregistre les chroniques temporelles $Q(t)$ et $y(t)$ à chaque pas de calcul (typiquement toutes les 1 à 5 minutes sur une durée de 2 à 4 heures).

### 12.2 Animation & Synchronisation Cartographique
1. **Hydrogramme interactif d'exutoire** :
   Un graphique vectoriel interactif affiche la courbe de débit à l'exutoire principal $Q_{\text{out}}(t)$. Un curseur temporel vertical orange indique la position courante $T$ dans l'épisode pluvieux.
2. **Mise à jour dynamique de la cartographie Leaflet** :
   À chaque déplacement du curseur (ou en lecture automatique) :
   * **Canalisations** : La couleur de chaque tronçon s'adapte dynamiquement selon son taux de charge instantané :
     * Vert : $Q(t) / Q_{\max} < 50\%$ (écoulement sain et libre)
     * Jaune : $50\% \le Q(t) / Q_{\max} < 80\%$ (charge modérée)
     * Orange : $80\% \le Q(t) / Q_{\max} < 100\%$ (charge critique)
     * Rouge : $Q(t) / Q_{\max} \ge 100\%$ (mise en charge sous pression)
   * **Regards de visite** : Les regards surchargés ou débordants au pas de temps $T$ sont mis en exergue par des cercles de couleur proportionnels à la charge.
3. **Indicateurs de crise en temps réel** :
   Le bandeau inférieur affiche en continu :
   * Débit instantané à l'exutoire ($m^3/s$).
   * Nombre de tronçons en surcharge au pas de temps courant.
   * Nombre de regards en débordement effectif au sol.
4. **Commandes de lecture** :
   Boutons Play / Pause, glissière temporelle navigable et sélecteur de vitesse d'accélération ($1\times, 2\times, 5\times$).

---

## 13. Rapport d'Expertise Technique A4 & Analyse Multi-Agents (PDF)

### 13.1 Architecture de Restitution Autonome (Zero-Dependency)
Pour garantir une indépendance absolue vis-à-vis d'outils de conversion serveur lourds (tels que Chromium headless ou wkhtmltopdf), le module d'impression repose sur une génération HTML A4 d'ingénierie vectorielle directe avec déclenchement natif de l'impression / sauvegarde PDF du navigateur (`window.print()`).

### 13.2 Consolidation des 5 Domaines d'Expertise IA
Le rapport compile de manière exhaustive les analyses des 5 agents spécialisés :
1. **Agent 1 — Diagnostic Causal & Hydraulique** :
   Identification des causes primaires de dysfonctionnement (insuffisance de pente, goulots d'étranglement géométriques avec $D_{\text{aval}} < D_{\text{amont}}$, refoulement aval et mises en charge).
2. **Agent 2 — Prescriptions Génie Civil & Recalibrage** :
   Recommandations de diamètres normalisés (DN 400 à DN 1200), matériaux prescrits (Béton Armé 135A, PEHD annelé), linéaires métriques et estimation des coûts unitaires de terrassement et pose.
3. **Agent 3 — Solutions d'Hydrologie Durable (GDO)** :
   Dimensionnement des bassins d'orage et d'écrêtement amont ($m^3$), noues d'infiltration végétalisées le long des voiries et évaluation de l'abattement du débit de pointe.
4. **Agent 4 — Matrice de Risques & Priorités d'Intervention** :
   Classement hiérarchisé des travaux selon la criticité :
   * **P1 (Urgence absolue - 3 mois)** : Risques avérés d'inondation de caves, chaussées primaires ou coupure de voiries d'intérêt national (ex. RN4).
   * **P2 (Moyen terme - 12 mois)** : Résorption des goulots structurels majeurs.
   * **P3 (Maintenance programmée)** : Curage régulier, réfection des joints et calage de tampons.
5. **Agent 5 — Analyse Technico-Économique Multi-Critères & Décision d'Investissement** :
   Comparatif rigoureux de 3 variantes d'aménagement :
   * *Variante 1* : 100% Tout-Réseau (Recalibrage lourd sans rétention — investissement massif et perturbation de voirie maximale).
   * *Variante 2* : 100% GDO pures (Bassins de rétention sans recalibrage — protection partielle insuffisante).
   * *Variante 3 (Recommandée)* : Mixte optimisée (Recalibrage ciblé des goulots structurants + bassin d'écrêtement régulé — résorption intégrale avec économie budgétaire substantielle).

### 13.3 Décomposition BPU & Indicateurs Décisionnels
* **Bordereau des Prix Unitaires (BPU)** :
  Décomposition analytique en 4 postes de dépenses :
  * Terrassement et blindage de tranchée ($30\%$)
  * Fourniture des tuyaux ($35\%$)
  * Pose et remblai compacté à $95\%$ OPM ($20\%$)
  * Réfection de chaussée en béton bitumineux ($15\%$)
* **Ratios directeurs socio-économiques** :
  * Coût au mètre linéaire rénové ($\text{DZD/ml}$).
  * Coût par habitant équivalent protégé ($\text{DZD/hab}$).
  * Dommages annuels moyens évités (EAD - *Expected Annual Damages*, en $\text{DZD/an}$).
  * Période de retour sur investissement (*Payback* en années).
  * Taux de Rentabilité Interne (TRI en $\%$) et Valeur Actuelle Nette actualisée à 20 ans (VAN).

---

### 7.1 Exécution native sans virtualenv
L'application fonctionne directement sur l'environnement Python standard du système sans exiger l'activation d'un environnement virtuel (`.venv`).

### 7.2 Stabilisation OpenBLAS sous Windows
Pour éviter toute défaillance d'allocation mémoire multithread (`OpenBLAS error: Memory allocation still failed after 10 retries`), les scripts initialisent systématiquement :
```python
import os
os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"
os.environ["OMP_NUM_THREADS"] = "1"
```
Cette variable doit impérativement être déclarée avant tout import de `geopandas`, `scipy` ou `numpy`.


