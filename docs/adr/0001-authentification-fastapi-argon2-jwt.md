# ADR 0001 — Authentification FastAPI, Argon2id et Double Session JWT/Cookie

- **Statut :** Acceptée
- **Date :** 2026-10-28
- **Portée :** Sécurité, Gestion des utilisateurs, API & Sessions

## Contexte

Dans sa version POC initiale, `swmm-platform-poc` ne disposait d'aucun mécanisme d'authentification ni de contrôle d'accès : les routes API et les pages de cartographie étaient ouvertes sans restriction. Pour transformer l'application en plateforme SaaS multi-tenant commerciale, il est impératif d'identifier chaque utilisateur avec certitude, de protéger ses données d'assainissement et de distinguer les accès navigateur web (ingénieurs au bureau) des accès mobiles (agents sur le terrain).

## Décision

Nous adoptons une architecture d'authentification unifiée intégrée à FastAPI reposant sur :
1. **Hachage des mots de passe avec Argon2id** via `pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")`. Argon2id offre la meilleure résistance connue aux attaques par force brute et par GPU/ASIC.
2. **Double mécanisme de session selon le client** :
   - **Pour les navigateurs Web** : Cookies HTTP-Only, Secure et SameSite (`Lax`) contenant un jeton de session chiffré, protégeant nativement l'utilisateur contre les failles XSS.
   - **Pour l'application mobile Flutter et les intégrations API** : Jeton Bearer JWT (JSON Web Token) standard passé dans l'en-tête `Authorization: Bearer <token>`, avec rafraîchissement périodique (access token court de 60 min + refresh token long de 30 jours révocable en base).
3. **Modèle d'autorisation basé sur les rôles (RBAC)** :
   - `superadmin` : Opérateur SaaS de la plateforme (vue globale, gestion des licences et du parc clients).
   - `admin` (Owner de l'organisation) : Responsable du compte d'entreprise, gestion des collaborateurs et de la facturation.
   - `engineer` : Ingénieur hydraulicien, importateur de réseaux, lanceur de simulations SWMM et éditeur de variantes.
   - `field_operator` : Technicien mobile terrain, restreint à la consultation cartographique et à la mise à jour des attributs/anomalies géolocalisées.
   - `viewer` : Observateur en lecture seule (tableaux de bord et rapports).

## Alternatives écartées

- **HTTP Basic Auth classique** : Vulnérable, non adapté aux sessions web interactives et fastidieux pour les flux mobiles.
- **OAuth2 / OpenID Connect exclusif (Keycloak, Auth0)** : Trop lourd à déployer et maintenir pour le périmètre MVP et incompatible avec certains déploiements souverains déconnectés sans accès internet externe.

## Conséquences

- Toutes les routes de l'API sont protégées par défaut par la dépendance FastAPI `Depends(get_current_active_user)`.
- L'oubli de protection sur une nouvelle route constitue une anomalie de sécurité bloquante détectée en CI.
- L'expérience mobile est fluide (authentification unique avec persistance sécurisée du refresh token dans le `FlutterSecureStorage`).
