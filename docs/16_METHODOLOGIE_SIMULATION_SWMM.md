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

## 8. Guide d'Environnement & Stabilisation Technique

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

