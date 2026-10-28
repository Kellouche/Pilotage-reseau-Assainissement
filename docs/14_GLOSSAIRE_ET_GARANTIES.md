# 14 — Glossaire et Garanties Métier (Spécial Non-Informaticien)

> **À qui s'adresse ce document** : aux maîtres d'ouvrage, ingénieurs hydrauliciens et exploitants de réseaux d'assainissement non informaticiens.  
> Il accompagne la [feuille de route SaaS](13_ROADMAP_SAAS.md) et répond à deux questions fondamentales :  
> 1. *« Comment être absolument certain que la transformation en SaaS ne va pas fausser nos calculs de débit, nos pentes ou nos simulations d'inondation qui marchent déjà ? »*  
> 2. *« Que signifient concrètement tous ces termes informatiques (multi-tenant, Celery, S3, JWT, Docker) ? »*  
> **Version** : 1.0 — Octobre 2026.

---

## 1. La Promesse : On déménage l'usine, on ne touche pas aux machines

Le code de calcul actuel fonctionne et détecte déjà avec précision les anomalies de réseau, les clusters hydrauliques et les sens d'écoulement sur plus de 10 000 tronçons. 

La transformation en **SaaS (Logiciel en Ligne par Abonnement)** s'apparente exactement au **déménagement d'une usine industrielle** dans un site moderne, hautement sécurisé, accessible par internet et doté d'une alimentation électrique secourue :
- **On déplace les machines sans les démonter ni altérer leurs réglages** : Le moteur hydraulique EPA SWMM 5.2, les algorithmes géométriques Shapely, le calcul des pentes, la détection des contre-pentes et la méthode NP 650 restent rigoureusement identiques.
- **Ce qui change, c'est uniquement le bâtiment d'accueil** : Où sont stockées les données (base de données sécurisée au lieu de fichiers éparpillés sur un disque local), qui a la clé pour entrer (comptes avec mot de passe chiffré), et comment les calculs s'exécutent (serveurs puissants en arrière-plan au lieu de bloquer l'écran de l'utilisateur).

| Ce qui va changer (Le bâtiment / L'infrastructure) | Ce qui ne changera jamais (Les machines / Le cœur physique) |
|---|---|
| **Stockage des réseaux** : Fichiers locaux sur disque dur (`.db`, dossiers locaux) $\rightarrow$ Base PostgreSQL/PostGIS centralisée et entrepôt d'objets sécurisé (S3/MinIO). | **Le moteur hydraulique** : EPA SWMM 5.2 officiel via `pyswmm` et le C-Toolkit standard. |
| **Sécurité d'accès** : Accès libre en local $\rightarrow$ Cloisonnement étanche : chaque entreprise ou régie ne voit et ne modifie que ses propres réseaux. | **Les lois physiques** : Équations de Saint-Venant, formule de Manning-Strickler pour l'écoulement gravitaire, calcul NP 650. |
| **Exécution des calculs** : L'écran se figeait pendant les gros calculs $\rightarrow$ Les calculs tournent en arrière-plan sans ralentir votre navigation. | **La détection d'anomalies** : Règles de contrôle des contre-pentes, diamètres nuls, nœuds orphelins et sauts de cote. |
| **Accès au logiciel** : Installation complexe sur un PC d'ingénieur $\rightarrow$ Simple connexion via Google Chrome ou Firefox sans aucune installation. | **L'analyse topologique** : Détection des clusters hydrauliques, graphe amont-aval et délimitation des bassins versants. |
| **Relevés de terrain** : Feuilles papier et ressaisie manuelle $\rightarrow$ Application mobile synchronisée directement avec le réseau central. | **Les résultats scientifiques** : Cotes piézométriques, débits de pointe, hauteurs d'eau et volumes de débordement. |

---

## 2. Le Filet de Sécurité : 5 Couches de Protection

Pour garantir qu'aucun bug informatique ne s'infiltre dans vos résultats hydrauliques au cours de la transformation SaaS, nous déployons un dispositif de contrôle qualité en **5 couches étanches** :

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                       LE FILET DE SÉCURITÉ EN 5 COUCHES                     │
├─────────────────────────────────────────────────────────────────────────────┤
│ 1. PHOTO DE RÉFÉRENCE (« Golden Master ») : Valeurs figées avant travaux   │
│ 2. CONTRÔLE AUTOMATIQUE SYSTÉMATIQUE : Tests de non-régression au millimètre│
│ 3. JALONS AVEC VALIDATION HUMAINE : Approbation explicite à chaque phase    │
│ 4. RETOUR ARRIÈRE PERMANENT (Git) : Restauration instantanée possible       │
│ 5. AUDIT TRAIL TOTAL : Journalisation infalsifiable de chaque calcul        │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Couche 1 — La Photo de Référence (« Golden Master »)
Avant d'écrire la moindre ligne de code de transformation SaaS, nous exécutons l'intégralité des calculs sur un jeu de données réel et complet (le réseau témoin de plus de 10 000 tronçons). Nous enregistrons et figeons cette photo officielle :
- Liste exhaustive et coordonnées exactes des anomalies détectées.
- Pentes calculées sur chaque tronçon au millimètre près.
- Nombre de clusters et de sous-bassins identifiés.
- Débits et hydrogrammes générés par le moteur SWMM 5.2.

### Couche 2 — Tests Automatisés de Non-Régression
À chaque ajout de fonctionnalité ou modification de code, une batterie de tests automatiques rejoue les calculs sur le réseau témoin et compare point par point les résultats avec la photo de référence. Si un écart dépasse les tolérances strictes (ex. écart de cote $> 1 \text{ mm}$ ou débit $> 0{,}01\%$), **la mise à jour est immédiatement bloquée**.

### Couche 3 — Validation Humaine par Jalon
Aucune phase de la feuille de route ne sera considérée comme terminée sans une démonstration concrète et une validation formelle par le responsable métier.

### Couche 4 — Traçabilité Git & Retour Arrière Permanent
Chaque modification est enregistrée dans l'historique versionné Git avec un commentaire explicite. À tout instant, il est possible de revenir en arrière d'un clic vers l'état stable précédent sans aucune perte de travail.

### Couche 5 — Audit Trail et Reproductibilité
Toute modification apportée à un réseau (que ce soit depuis l'interface web ou depuis l'application mobile terrain) est journalisée : auteur, date, heure, ancienne valeur, nouvelle valeur et motif de l'intervention.

---

## 3. Glossaire Pédagogique (Métier & Informatique)

### 3.1 Termes Métier de l'Assainissement
- **Cote de radier** : Altitude du fond intérieur de la canalisation ou du regard. C'est la cote déterminante pour calculer la pente d'écoulement de l'eau par gravité.
- **Contre-pente** : Anomalie grave où le radier aval est plus haut que le radier amont, ce qui oblige l'eau à stagner ou à refluer en arrière, favorisant l'envasement et les odeurs.
- **Saut de pente (ou dénivelée)** : Différence de cote brutale au niveau d'un regard entre la conduite entrante et la conduite sortante (chute hydraulique).
- **Écoulement à surface libre** : Écoulement gravitaire où l'eau n'occupe pas toute la section de la conduite (contact avec l'air). Si la canalisation se remplit totalement, elle entre « en charge », ce qui accroît le risque de mise sous pression et de refoulement.
- **Formule de Manning-Strickler** : Équation mathématique fondamentale ($V = K \cdot R_h^{2/3} \cdot I^{1/2}$) reliant la vitesse de l'eau ($V$), la rugosité de la conduite ($K$), le rayon hydraulique ($R_h$) et la pente ($I$).
- **Méthode NP 650** : Formule empirique normalisée pour estimer le débit nominal d'une conduite circulaire en assainissement : $Q \approx 3{,}1 \cdot D^{2{,}2}$ (avec $D$ le diamètre).
- **EPA SWMM 5.2 (Storm Water Management Model)** : Moteur de simulation dynamique de renommée mondiale développé par l'Agence Américaine de Protection de l'Environnement (EPA), capable de simuler en régime transitoire les crues pluviales, la propagation des ondes de crue et les débordements en surface.
- **MNT / DEM (Modèle Numérique de Terrain)** : Grille raster représentant l'altitude du sol naturel à l'échelle d'un territoire, indispensable pour tracer les crêtes de bassins versants réels et anticiper les trajectoires de ruissellement.
- **Cluster hydraulique** : Regroupement topologique connexe de canalisations et regards s'écoulant vers un même point bas ou exutoire.
- **Rejet / Exutoire (Outfall)** : Point terminal du réseau d'assainissement où les eaux sont déversées dans un cours d'eau, un milieu récepteur ou envoyées vers une station d'épuration (STEP).

### 3.2 Termes Informatiques de la Transformation SaaS
- **SaaS (Software as a Service)** : Logiciel accessible en ligne via un simple navigateur internet, sans aucune installation locale sur votre ordinateur. Les mises à jour et les sauvegardes sont automatiques et gérées sur le serveur.
- **Multi-Tenant (Multi-Locataire)** : Architecture logicielle où plusieurs entreprises, régies ou clients partagent la même plateforme informatique tout en étant **rigoureusement et hermétiquement isolés** les uns des autres via un identifiant d'organisation (`org_id`). L'entreprise A ne peut sous aucun prétexte voir ou modifier les réseaux de l'entreprise B.
- **FastAPI** : Cadre logiciel Python moderne, ultra-rapide et standardisé, utilisé pour construire l'API (moteur d'échange de données) de la plateforme.
- **PostgreSQL + PostGIS** : La base de données relationnelle et spatiale de référence dans l'industrie, capable de stocker et d'interroger instantanément des millions de géométries géographiques (coordonnées GPS, polylignes de conduites, surfaces de bassins).
- **Celery & Redis** : Système de gestion de tâches asynchrones en arrière-plan. Lorsqu'une simulation SWMM ou un traitement MNT prend 2 minutes, Celery le prend en charge sur un serveur dédié pendant que votre écran reste immédiatement réactif.
- **Stockage d'objets S3 / MinIO** : Système de stockage ultra-fiable conçu pour archiver les fichiers volumineux (rasters MNT `.tif`, fichiers GeoPackage `.gpkg`, rapports d'audit PDF et historiques de simulation `.out`).
- **Argon2id & JWT** : Les standards de chiffrement les plus robustes au monde pour protéger les mots de passe et sécuriser les sessions de travail des utilisateurs.
- **RBAC (Role-Based Access Control)** : Contrôle d'accès basé sur les rôles permettant de définir qui a le droit de modifier un réseau (Administrateur, Ingénieur), qui ne peut que le consulter (Observateur), et qui effectue les saisies sur le terrain (Opérateur mobile).
- **Docker & Docker Compose** : Technologie de conteneurisation permettant d'emballer toute la plateforme (base de données, serveurs, moteurs de calcul) dans une « boîte virtuelle » prête à démarrer en une seule commande sur n'importe quel serveur cloud ou machine locale.
