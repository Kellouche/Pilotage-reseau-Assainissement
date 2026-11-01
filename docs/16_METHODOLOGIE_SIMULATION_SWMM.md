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

---

## 3. Scénarios Pluviométriques de Sollicitation

Le moteur SWMM 5.2 intègre les sollicitations sous forme de séries temporelles (`[TIMESERIES]`) associées à un pluviomètre numérique (`[RAINGAGES]`) :

| Scénario | Période de Retour $T$ | Durée de Simulation | Intensité de Crête | Forme / Méthode |
|---|---|---|---|---|
| **Pluie Décennale** | $T = 10\text{ ans}$ | 4 heures | $92\text{ mm/h}$ | Montana / Chicago ($r=0.4$) |
| **Pluie Cinquantennale** | $T = 50\text{ ans}$ | 6 heures | $145\text{ mm/h}$ | Crise majeure / Montana |
| **Orage Brutal d'Été** | Événement convectif | 2 heures | $110\text{ mm/h}$ | Pluie courte d'intensité violente |
| **Temps Sec Pur** | Étiage journalier | 24 heures | $0\text{ mm/h}$ | Transit des eaux usées sans ruissellement |

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

---

## 6. Endpoints API Associés

| Endpoint | Méthode | Rôle |
|---|---|---|
| `/api/v1/network/subcatchments` | `GET` | GeoJSON des 59 sous-bassins Voronoï avec surfaces ($ha$), pentes et exutoires. |
| `/api/v1/simulations/scenarios` | `GET` | Liste des scénarios pluviométriques et paramètres du solveur. |
| `/api/v1/simulations/run` | `POST` | Exécute la simulation SWMM 5.2 et renvoie KPIs + cartographies thématiques. |
| `/api/v1/simulations/latest` | `GET` | Récupère instantanément la dernière simulation pour affichage persistant. |
| `/api/v1/simulations/download/inp` | `GET` | Téléchargement du fichier source `.INP` assemblé. |
| `/api/v1/simulations/download/rpt` | `GET` | Téléchargement officiel du rapport de calcul `.RPT` certifié. |

---

## 7. Guide d'Environnement & Stabilisation Technique

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
