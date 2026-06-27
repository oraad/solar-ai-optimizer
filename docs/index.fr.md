# Optimiseur d'IA solaire

Un cerveau auto-hébergé et indépendant du fournisseur pour Home Assistant qui prévoit l'énergie solaire et la charge,
contrôle ensuite les paramètres de charge/décharge de l'onduleur hybride pour garder votre maison alimentée
pannes de réseau imprévisibles.

## Liens rapides

| Sujet | Guide |
|-------|--------|
| **Installer** |[Installation et démarrage rapide](installation.md)— Docker, Compose, module complémentaire, Proxmox |
| **Tableau de bord** |[Guide d'utilisation du tableau de bord](frontend-manual.md)— procédure pas à pas pour l'administrateur et le spectateur |
| **Mobile (application HA)** |[Contrôle qualité des entrées mobiles](mobile-ingress-qa.md)— Liste de contrôle de l'application compagnon |
| **Assistant à domicile** |[Configuration haute disponibilité](home-assistant-setup.md) · [Package de sécurité](home-assistant-failsafe.md) |
| **Contrôle d'accès** |[Rôles et accès](ingress-auth.md)— administrateur contre spectateur |
| **Configuration** |[Configuration](configuration.md) · [`.env.example`](https://github.com/oraad/solar-ai-optimizer/blob/main/.env.example) |
| **Proxmox** |[Déploiement Proxmox](proxmox.md) |
| **Sécurité** |[Politique de sécurité](security.md) |
| **Source** |[Dépôt GitHub](https://github.com/oraad/solar-ai-optimizer) · [Journal des modifications](https://github.com/oraad/solar-ai-optimizer/blob/main/CHANGELOG.md) |

## Commencer

Nouveau dans le projet ? Commencez par **[Installation et démarrage rapide](installation.md)**.

Le chemin local le plus rapide :

```bash
docker compose up -d --build
```

Ouvrez **http://localhost:8000**. L'application démarre en **mode ombre** (aucune écriture de l'onduleur).

## Priorités

Ordre par défaut (configurable dans **Paramètres → Moteur**) :

1. **Résilience** : ne jamais interrompre les charges critiques
2. **Économies** — utilisation opportuniste du réseau lorsqu'il est disponible (pas d'optimisation tarifaire)
3. **Autosuffisance** : minimisez le gaspillage d'énergie solaire

Réorganisez la liste pour mettre l’accent sur les différents compromis. L'ordre par défaut préserve le
la position axée sur la résilience décrite ci-dessus.

L'optimiseur ne prédit **pas** la disponibilité du réseau. Il prévoit le solaire et la charge, défend
une réserve de batterie conservatrice et réagit lorsque la grille apparaît.

## Architecture

```
Home Assistant ──WebSocket──▶ Ingest ──▶ SQLite
        ▲                              │
        │ REST                         ▼
   Control Executor ◀── Engine ◀── Forecasters
        │
        ▼
   FastAPI + Lit dashboard
```

Voir[Configuration](configuration.md)pour les sources de paramètres,[Sécurité](security.md)pour
le renforcement du déploiement et le[LISEZMOI sur GitHub](https://github.com/oraad/solar-ai-optimizer#readme)
pour plus de détails sur l'API et les notes de sécurité.

## Langues de documentation

Ce site est publié en **English** (par défaut), **Français** et **العربية**. Utilisez le
sélecteur de langue dans l’en-tête du site pour changer les paramètres régionaux. Les pages arabes utilisent une disposition de droite à gauche.

**Contributeurs :** Sources anglaises dans`docs/*.md`sont canoniques. Après avoir édité l'anglais :

1. Réexécuter`python scripts/translate_docs.py`pour les pages concernées (ou`--force`pour tous).
2. Courez`python scripts/check_docs_i18n.py`et`mkdocs build --strict`localement.
3. Pour ajouter une langue : étendre`docs/i18n/locales.yaml`, ajouter`nav_translations`et une langue
entrée dans`mkdocs.yml`, puis exécutez le script de traduction.

Les pages traduites automatiquement sont un point de départ – améliorez`.fr.md` / `.ar.md`fichiers directement
quand tu peux. Les chaînes de l'interface utilisateur du tableau de bord sont distinctes ; voir
[Ajout d'une langue de tableau de bord](frontend-manual.md#adding-a-dashboard-language-contributors)
dans le guide de l'utilisateur.
