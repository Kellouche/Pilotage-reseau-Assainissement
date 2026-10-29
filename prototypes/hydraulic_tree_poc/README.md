# Prototype d'arbre hydraulique

Ce dossier est indépendant de l'application principale. Il sert à tester la
reconstruction d'un sous-réseau amont autour d'une station réelle du
GeoPackage.

## Exécution

Depuis la racine du dépôt :

```powershell
python prototypes/hydraulic_tree_poc/run_trial.py
```

Le prototype utilise par défaut la station `SR_HH02` et un rayon de 1 200 m.
Les résultats sont écrits dans `prototypes/hydraulic_tree_poc/output/`.

Le prototype ne fabrique aucun polygone de bassin hydraulique validé. Il produit :

- le sous-réseau extrait ;
- l'arbre amont orienté selon `ID_AMONT` → `ID_AVAL` ;
- les branches et leur ordre opérationnel ;
- les ruptures d'identifiants, cycles et feuilles.
- deux géométries provisoires : l'empreinte réseau et une enveloppe urbaine estimée.

Par défaut, le raccordement le plus proche est seulement une proposition.
Pour tester une correction manuelle :

```powershell
python prototypes/hydraulic_tree_poc/run_trial.py --station SR_HH02 --outlet 7746
```

Le rapport indique alors `connection_decision.mode = manual_cli`.
