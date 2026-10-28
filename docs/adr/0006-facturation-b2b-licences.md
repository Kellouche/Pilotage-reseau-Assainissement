# ADR 0006 — Modèle Commercial B2B / B2G et Gestion Sécurisée des Licences

- **Statut :** Acceptée
- **Date :** 2026-10-28
- **Portée :** Monétisation, Facturation, Licences, Console Opérateur

## Contexte

Dans le secteur de l'assainissement et des travaux publics, les clients principaux (régies communales, établissements publics d'assainissement, bureaux d'études en ingénierie) ne règlent pas leurs prestations par carte bancaire Stripe en ligne :
- Ils fonctionnent selon des procédures administratives strictes : devis proforma, engagement de dépenses, émission d'un Bon de Commande officiel visé par la comptabilité publique, puis virement bancaire après service fait.
- De plus, certains serveurs déployés en réseau privé étanche n'ont pas accès à internet pour interroger un serveur de licence distant.

## Décision

Nous mettons en place un système hybride de monétisation B2B/B2G axé sur **le cycle documentaire réglementaire et l'activation par jetons cryptographiques** :

1. **Génération instantanée de Devis Proforma réglementaire** :
   L'administrateur de l'organisation peut télécharger à tout moment un document PDF officiel de devis proforma (`/organization/license/proforma`) comportant les mentions fiscales réglementaires et le montant dans la devise choisie (DZD ou EUR).
2. **Dépôt et validation du Bon de Commande administratif** :
   Le client dépose le scan du bon de commande officiel signé (`/organization/license/purchase-order`). L'opérateur de la plateforme (SuperAdmin) examine la pièce dans la console d'administration (`/admin/licenses`), approuve la commande et active la licence correspondante.
3. **Jetons de licence autonomes et vérifiables** :
   Les licences peuvent être transmises sous la forme d'un jeton chiffré (`SP-LIC-YYYY-XXXX-XXXX-XXXX`). Ce jeton contient la date d'expiration, le code de plan (`bet`, `exploitation`), le plafond de regards et l'empreinte de l'organisation. L'activation s'effectue en un clic dans l'interface (`/organization/license/activate-token`), y compris sur des installations hors-ligne.
4. **Console d'exploitation SuperAdmin** :
   Un module d'administration réservé (`/admin/*`) permet de superviser l'ensemble du parc d'abonnés, de prolonger les périodes d'évaluation et de basculer manuellement les statuts d'organisations.

## Alternatives écartées

- **Paiement Stripe exclusif par carte bancaire** : Inadapté à 90% des acteurs publics et des régies d'assainissement nationales. Stripe reste conservé comme passerelle optionnelle pour les souscriptions internationales en ligne par carte.
- **Dongle USB physique ou verrouillage machine rigide (MAC address)** : Incompatible avec les architectures de conteneurs cloud modernes.

## Conséquences

- La plateforme est immédiatement commercialisable auprès des administrations et grands comptes sans friction de paiement.
- Le Feature Gating est piloté de façon centralisée et déterministe via le modèle de données de licences en base.
