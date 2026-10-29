# Grille Tarifaire & Définition Métier des Plans — SWMM Platform SaaS

> **Version** : 2.0 (Segmentation par la valeur métier en Assainissement & Gestion des Eaux Pluviales)  
> **Date** : Octobre 2026  
> **Cible de mise en œuvre** : Phase 3 (Monétisation, Feature Gating & Quotas d'Exploitation)  
> **Zone monétaire principale** : Dinars Algériens (DZD) et Euros (EUR)

---

## 1. Principes Directeurs de la Segmentation

La politique tarifaire de **SWMM Platform SaaS** n'est pas indexée sur des métriques purement informatiques, mais sur la **valeur opérationnelle délivrée** aux différents profils du secteur de l'assainissement :

1. **L'Étudiant ou le Chercheur Universitaire** étudie la mécanique des fluides, les équations d'onde de Saint-Venant et les lois de Manning-Strickler. Il manipule de petits sous-réseaux d'apprentissage, n'a aucun regard physique sous la chaussée et ne produit pas d'études réglementaires opposables.
2. **Le Bureau d'Études (BET) & Ingénieriste Conseil** réalise des schémas directeurs d'assainissement (SDA), des études de zonage pluvial, des calculs de dimensionnement de bassins de rétention et des dossiers d'autorisation loi sur l'eau. Il a besoin d'auditer rapidement des réseaux entiers (jusqu'à 15 000 regards), de croiser la géométrie avec le MNT et de générer des modèles SWMM 5.2 certifiés avec des rapports d'audit prêts pour les comités de pilotage.
3. **L'Entreprise de Gestion de l'Assainissement ou la Régie Communale** assure l'exploitation, la maintenance et la pérennité du patrimoine d'assainissement communal au quotidien. Ses priorités opérationnelles sont le suivi patrimonial continu de l'infrastructure, l'enregistrement des inspections terrain et des incidents (curages, obstructions, casses, réfections), l'historique d'audit des interventions et le contrôle continu de conformité hydraulique (autocurage NP 650, fonctionnement des postes de relevage et ouvrages spéciaux).

---

## 2. Version Démo (Essai 14 jours) & Matrice Comparative des Niveaux de Service

### 2.0 Version Démo (Évaluation Gratuite Sans Engagement)
Chaque nouvelle organisation dispose automatiquement à l'inscription d'un accès complet d'évaluation :
* **Durée** : **14 jours** (prolongeable par l'administrateur de plateforme).
* **Plafond réseau** : Jusqu'à **2 000 regards et canalisations** (dimensionné pour tester une commune moyenne ou un sous-bassin réel).
* **Fonctionnalités incluses** : Moteur de contrôle qualité, détection des anomalies topologiques, aperçu cartographique Leaflet, calcul des pentes et simulation SWMM 5.2 d'initiation.
* **Issue de l'évaluation** : À la fin des 14 jours, l'organisation choisit sa formule définitive parmi les trois offres ci-dessous.

---

### 2.1 Matrice Comparative des Formules

| Critères & Droits | **1. Académique & Recherche** | **2. Bureau d'Études (BET)** | **3. Entreprises de Gestion & Régies Communales** |
|---|---|---|---|
| **Cible professionnelle** | Universités, instituts d'hydraulique, chercheurs, étudiants | Cabinets d'ingénierie, BET hydraulique urbaine, experts VRD | Entreprises de gestion d'assainissement, régies communales, services techniques |
| **Tarif d'accès** | **0 DZD / mois** (Usage strictement non commercial) | **45 000 DZD / mois** (ou 450 000 DZD / an) | **Sur devis / Convention annuelle d'exploitation** |
| **Objectif opérationnel** | Enseignement, validation théorique, recherche | Études de dimensionnement, schémas directeurs, récolement | Exploitation continue, gestion patrimoniale, suivi incidents & curages |
| **Mode de souscription** | Validation sur email universitaire (`.edu`, `.univ`) | Souscription en ligne, Bon de Commande / Devis Proforma | Bon de commande régie / collectivité ou marché de service |
| **Plafond réseau** | 500 regards max | 15 000 regards par projet | Réseau communal complet (patrimoine global) |
| **Journal terrain & incidents** | ❌ Non inclus | ❌ Non inclus | **Inclus** (Signalement incidents, inspections d'ouvrages) |
| **Historique & Traçabilité (Audit)**| 7 jours glissants | 90 jours | **Historique patrimonial permanent (Audit Trail)** |
| **Découpage Bassins MNT / DEM** | ❌ Non inclus | **Inclus** (Grilles MNT jusqu'à 50 Mo) | **Inclus** (Très haute résolution) |
| **Export modèle `.inp` SWMM** | Limité (avec filigrane pédagogique) | **Inclus en plein accès** | **Inclus en plein accès** |
| **Rapports d'Audit & Synthèse** | ❌ Filigrane *"Usage Pédagogique"* | **Inclus** (PDF certifié avec logo du BET) | **Inclus** (Rapports complets d'exploitation) |
| **Supervision des ouvrages** | Modélisation ponctuelle | Modélisation ponctuelle | **Suivi continu des postes de relevage, STEP et déversoirs** |
| **Comptes & Collaborateurs** | 1 compte chercheur individuel | 5 comptes ingénieurs d'études | Multi-comptes adaptés (Bureau d'exploitation & Terrain) |
| **Calculs SWMM simultanés** | 1 calcul à la fois (file standard) | 3 calculs simultanés | File prioritaire dédiée |
| **Support & Accompagnement** | Communauté & FAQ en ligne | Support technique par email (< 24h ouvrées) | Support technique prioritaire & accompagnement régie |

---

## 3. Matrice Technique des Droits (Feature Gating)

Dans le moteur SaaS de la plateforme (`api/core/quotas.py`), chaque organisation locataire est rattachée à un code de plan strict :
- `demo` : Évaluation 14 jours.
- `education` : Académique et recherche.
- `bet` : Bureau d'études et ingénierie.
- `exploitation` : Régie d'assainissement et collectivité.

### 3.1 Dictionnaire de Quotas et Décorateurs
Chaque requête vers l'API est interceptée par un validateur de quotas (`check_quota`) avant exécution des calculs lourds :

```python
PLAN_QUOTAS = {
    "demo": {
        "max_nodes": 2000,
        "max_projects": 3,
        "max_users": 2,
        "concurrent_simulations": 1,
        "has_mnt_analysis": True,
        "has_mobile_access": False,
        "has_custom_reports": False,
        "retention_days": 14,
    },
    "education": {
        "max_nodes": 500,
        "max_projects": 3,
        "max_users": 1,
        "concurrent_simulations": 1,
        "has_mnt_analysis": False,
        "has_mobile_access": False,
        "has_custom_reports": False,
        "retention_days": 30,
    },
    "bet": {
        "max_nodes": 15000,
        "max_projects": 25,
        "max_users": 5,
        "concurrent_simulations": 3,
        "has_mnt_analysis": True,
        "has_mobile_access": False,
        "has_custom_reports": True,
        "retention_days": 365,
    },
    "exploitation": {
        "max_nodes": 999999,
        "max_projects": 999999,
        "max_users": 999999,
        "concurrent_simulations": 10,
        "has_mnt_analysis": True,
        "has_mobile_access": True,
        "has_custom_reports": True,
        "retention_days": 3650,
    },
}
```

---

## 4. Cycle de Vie des Abonnements et Facturation B2B / B2G

Pour répondre aux contraintes administratives des marchés publics, des régies d'assainissement et des bureaux d'études, la plateforme supporte nativement un double canal de facturation :

### 4.1 Parcours Administratif B2B / B2G (Devis & Bon de Commande)
1. **Émission de Facture Proforma** :
   Le directeur ou l'administrateur de l'organisation télécharge directement depuis son espace client (`/organization/license/proforma`) un devis officiel réglementaire chiffré en Dinars Algériens (DZD) ou Euros (EUR) mentionnant les identifiants fiscaux légaux.
2. **Dépôt du Bon de Commande (BC)** :
   L'organisme dépose son Bon de Commande officiel signé et visé (`/organization/license/purchase-order`).
3. **Validation par l'Opérateur Plateforme** :
   L'administrateur général (SuperAdmin) examine la pièce justificative dans la console de régulation (`/admin/licenses`), valide la commande et émet un jeton de licence sécurisé.
4. **Activation de la Licence** :
   La licence officielle est activée dès la validation ou par saisie d'une clé de licence unique de format :  
   `SP-LIC-2026-XXXX-XXXX-XXXX`

### 4.2 Protection Anti-Abus du Plan Recherche
Pour empêcher toute utilisation commerciale déguisée de l'offre Académique gratuite :
- L'inscription requiert une adresse email institutionnelle (blocage strict des domaines publics : gmail, yahoo, hotmail, etc.).
- Les exports cartographiques et les fichiers SWMM générés sous ce plan comportent un filigrane indélébile :  
  `« Document Pédagogique Non Contractuel — Usage Réservé Recherche & Enseignement »`.
