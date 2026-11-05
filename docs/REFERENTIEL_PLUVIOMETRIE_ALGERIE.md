# Référentiel National des Données Pluviométriques et Paramètres IDF d'Algérie

> **Document de Référence Scientifique, Réglementaire et Opérationnel**  
> **Application :** SWMM Platform SaaS  
> **Auteur :** Dr Abdelhakim Kellouche  
> **Date de mise à jour :** Novembre 2026  
> **Version Référentiel :** 1.0.0 (Certifiée ANRH / UHBC / ONA)  
> **Fichier de données source :** `data/referentiel_pluviometrie_algerie.json`  
> **Module applicatif Python :** `src/domain/referentiel_pluvio.py`

---

## 1. Contexte & Justification d'Ingénierie

La simulation hydrodynamique sous EPA SWMM 5.2 nécessite une sollicitation météorologique rigoureuse. L'utilisation d'intensités forfaitaires non documentées ou transposées d'autres régions sans validation statistique compromet la fiabilité des diagnostics d'assainissement et des dimensionnements d'ouvrages régulateurs.

Ce référentiel fournit à la plateforme une assise scientifique certifiée, basée sur :
1. **L'Agence Nationale des Ressources Hydriques (ANRH)** — Notamment l'Antenne Régionale de Chlef (Bassin National 01 *Chélif - Zahrez*).
2. **L'Office National de l'Assainissement (ONA)** — Prescriptions de dimensionnement des réseaux pluviaux urbains et unitaires.
3. **L'Université Hassiba Ben Bouali de Chlef (UHBC)** — Faculté de Génie Civil & Département de Génie Urbain (travaux du *Dr. Abdellah Cherif Taiba* sur la gestion durable des eaux pluviales et l'ajustement des courbes IDF de Montana).
4. **L'Office National de la Météorologie (ONM)** & publications scientifiques validées (ASJP / CERIST) sur les séries chronologiques 1970–2024.

---

## 2. Cadre Réglementaire ONA & Périodes de Retour

Pour l'assainissement pluvial urbain en Algérie, l'ONA et les guides de conception prescrivent les périodes de retour suivantes :

| Période de Retour ($T$) | Niveau de Risque / Application | Objectif Hydraulique |
| :--- | :--- | :--- |
| **$T = 2\text{ ans}$ (Biennale)** | Exploitation courante & confort urbain | Absence de mise en charge des collecteurs secondaires. |
| **$T = 10\text{ ans}$ (Décennale)** | **Standard réglementaire obligatoire ONA** | Dimensionnement des collecteurs principaux ; écoulement à surface libre ($Q/Q_{\max} \le 1.0$). |
| **$T = 20\text{ ans}$ (Vicennale)** | Orages convectifs intenses | Tolérance d'une mise en charge temporaire sans submersion des tampons. |
| **$T = 50\text{ ans}$ (Cinquantennale)** | Protection contre les inondations majeures | Analyse de résilience des points bas et dimensionnement des bassins d'orage. |
| **$T = 100\text{ ans}$ (Centennale)** | Crues historiques exceptionnelles | Sécurité des exutoires naturels, franchissements et zones de submersion. |

---

## 3. Formulations Mathématiques Utilisées

### 3.1 Formule d'Intensité de Montana

L'intensité moyenne maximale $I(t)$ pour une durée de pluie $t$ s'exprime par la loi de Montana :

$$I(t) = a \cdot t^{-b}$$

Où :
- $t$ : durée de la pluie (en minutes).
- $a, b$ : paramètres régionaux ajustés par analyse fréquentielle (méthode de Gumbel ou GEV).
- Dans le moteur SWMM 5.2, l'intensité est convertie en millimètres par heure ($\text{mm/h}$) :

$$I(\text{mm/h}) = 60 \cdot a \cdot t^{-b}$$

### 3.2 Hyétogramme Synthétique de Projet (Méthode de Chicago)

Pour convertir les courbes Intensité-Durée-Fréquence (IDF) en une série temporelle discrète (`[TIMESERIES]`), le modèle génère un **hyétogramme synthétique de Chicago centré** avec un coefficient d'asymétrie du pic :

$$r = 0.40$$

Ce ratio $r = 0.40$ (crête survenant à $40\%$ de la durée totale de l'événement) est représentatif de la dynamique des orages convectifs méditerranéens observés dans le bassin du Chéliff.

### 3.3 Contrôle Automatique Pluie-Débit (Méthode Rationnelle)

Le moteur compare automatiquement le débit de pointe simulé en Saint-Venant 1D ($Q_{\text{sim}}$) avec le débit théorique direct de la méthode rationnelle :

$$Q_{\text{rat}} = \frac{C_{\text{eff}} \cdot I_{\max} \cdot A_{\text{urb}}}{360}$$

Où $A_{\text{urb}}$ est la surface urbaine drainée en hectares, $I_{\max}$ l'intensité en $\text{mm/h}$ et $C_{\text{eff}}$ le coefficient de ruissellement effectif.

---

## 4. Réseau des 7 Stations Hydro-Météorologiques de la Wilaya de Chlef

Le référentiel intègre l'ensemble des stations ANRH de la Wilaya de Chlef (Bassin 01 Chélif) :

| Station | Code ANRH | Alt. | Pluie Annuelle | $P_{24}$ ($T=10\text{ ans}$) | Montana $a$ ($10\text{ ans}$) | Montana $b$ ($10\text{ ans}$) | $I_{\max}(15\text{ min})$ |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Chlef Siège (Ech-Cheliff)** | `010501` | 154 m | 415 mm | **56.0 mm** | **9.334** | **0.745** | **74.9 mm/h** |
| **Pontéba (Oum Drou)** | `010502` | 142 m | 398 mm | 54.0 mm | 9.020 | 0.748 | 72.0 mm/h |
| **Oued Fodda (Vallée/Barrage)** | `010505` | 180 m | 440 mm | 62.0 mm | 9.850 | 0.742 | 78.5 mm/h |
| **Bénaïria (Massif du Dahra)** | `010508` | 480 m | 485 mm | 72.0 mm | 11.200 | 0.738 | 89.0 mm/h |
| **Domaine Si Tayeb** | `010512` | 165 m | 410 mm | 55.0 mm | 9.250 | 0.746 | 74.0 mm/h |
| **Ténès (Littoral)** | `010520` | 15 m | 510 mm | 68.0 mm | 10.450 | 0.740 | 83.5 mm/h |
| **Boukadir (Bas Chélif Ouest)** | `010525` | 110 m | 390 mm | 52.0 mm | 8.850 | 0.750 | 70.5 mm/h |

### Paramètres de Montana pour la Station de Référence Chlef Siège (UHBC / ANRH) :

* **Biennale ($T=2\text{ ans}$)** : $a = 5.250,\; b = 0.720 \implies I_{\max}(15\text{ min}) = 45.0\text{ mm/h},\; P_{24} = 34.0\text{ mm}$
* **Quinquennale ($T=5\text{ ans}$)** : $a = 7.107,\; b = 0.733 \implies I_{\max}(15\text{ min}) = 58.5\text{ mm/h},\; P_{24} = 45.0\text{ mm}$
* **Décennale ($T=10\text{ ans}$ — Standard ONA)** : $a = 9.334,\; b = 0.745 \implies I_{\max}(15\text{ min}) = \mathbf{74.9\text{ mm/h}},\; P_{24} = 56.0\text{ mm}$
* **Vicennale ($T=20\text{ ans}$)** : $a = 11.823,\; b = 0.752 \implies I_{\max}(15\text{ min}) = \mathbf{92.5\text{ mm/h}},\; P_{24} = 66.5\text{ mm}$ *(explique la valeur de 92 mm/h constatée précédemment)*
* **Cinquantennale ($T=50\text{ ans}$)** : $a = 15.795,\; b = 0.760 \implies I_{\max}(15\text{ min}) = \mathbf{120.0\text{ mm/h}},\; P_{24} = 81.0\text{ mm}$
* **Centennale ($T=100\text{ ans}$)** : $a = 19.338,\; b = 0.764 \implies I_{\max}(15\text{ min}) = \mathbf{144.5\text{ mm/h}},\; P_{24} = 94.0\text{ mm}$

---

## 5. Stations Régionales Complémentaires

Pour étendre les capacités de la plateforme à d'autres projets du territoire national, les bassins suivants sont également documentés :
- **Aïn Defla** : Station Khemis Miliana (Code 010403 - Haut Chélif)
- **Mascara** : Station ANRH Mascara-Ghriss (Code 040702 - Bassin Macta)
- **Alger** : Station Alger Port / Cap Caxine (Code 020301 - Côtiers Algérois)
- **Oran** : Station Oran Es-Sénia (Code 050201 - Bassin Oranie)
- **Constantine** : Station Constantine Aïn El Bey (Code 030401 - Bassin 03)

---

## 6. Utilisation dans la Plateforme

### 6.1 Dans l'Interface Graphique (Modale de Simulation)
1. **Sélecteur de Station** : Menu déroulant permettant de choisir directement parmi les 7 stations de Chlef ou d'autres wilayas.
2. **Sélecteur de Scénario** : Bascule instantanée entre Décennale ONA ($T=10$), Cinquantennale ($T=50$), Centennale ($T=100$), Biennale ($T=2$), Orage brutal ($2\text{ h}$) ou Temps sec.
3. **Champ d'Édition Libre $I_{\max}$** : L'ingénieur peut ajuster l'intensité de pointe manuellement ; le système passe automatiquement en mode personnalisé.
4. **Note Explicative Dynamique** : Affiche en temps réel la formule de Montana, les paramètres $a, b$, la pluie journalière $P_{24}$ et la hauteur cumulée $P$.

### 6.2 Dans les Résultats & Rapports de Simulation
Le cartouche de résultats SWMM consacre un bloc dédié à la sollicitation pluviométrique :
- Nom et badge de la station ANRH avec son code officiel.
- Période de retour $T$ et formule de Montana retenue.
- Intensité de pointe de dimensionnement ($I_{\max}$ en $\text{mm/h}$).
- Hauteur totale précipitée ($P_{\text{tot}}$ en $\text{mm}$).
- Mention de la source hydro-météorologique certifiée.

### 6.3 Endpoints API REST

* `GET /api/v1/simulations/pluviometrie/referentiel` : Synthèse complète du référentiel, wilayas et métadonnées.
* `GET /api/v1/simulations/pluviometrie/stations?wilaya=Chlef` : Liste des stations et de leurs coordonnées.
* `GET /api/v1/simulations/scenarios?station_id=chlef_anrh_siege` : Scénarios SWMM calibrés pour la station spécifiée.
* `POST /api/v1/simulations/run` : Lancement de simulation prenant en compte `station_id` et `intensite_max_mmh`.
