# Installation et démarrage rapide

Solar AI Optimizer est livré sous la forme d’une seule image Docker. Choisissez le chemin de déploiement qui
s'adapte à votre environnement : tous les chemins desservent le tableau de bord et l'API sur le **port 8000** et
démarrez en **mode ombre** (observation uniquement ; aucun onduleur n'écrit jusqu'à ce que vous passiez en direct).

!!! warning "Le mode ombre d'abord"
Chaque chemin est par défaut **SHADOW MODE**. Surveillez les décisions un jour ou deux avant
activation du contrôle en direct à partir du panneau **Overrides** du tableau de bord.

## Choisissez votre déploiement

| Méthode | Idéal pour | Persistance |
|--------|----------|-------------|
| [Docker Composer](#docker-compose-recommended)| Développeur, homelab, hôte Docker générique |`solar-data`volumes |
| [Docker (image GHCR)](#docker-standalone-image)| Conteneur unique, pas de Compose |`solar-data`volumes |
| [Application Home Assistant](#home-assistant-add-on)| HAOS / Supervisé | Superviseur`/data` |
| [Proxmox LXC](#proxmox-lxc)| Laboratoire domestique Proxmox VE | Volume Docker dans LXC |

Voir aussi :[Configuration de l'assistant à domicile](home-assistant-setup.md) · [Configuration](configuration.md) · [`.env.example`](https://github.com/oraad/solar-ai-optimizer/blob/main/.env.example)

---

## Docker Compose (recommandé) {#docker-compose-recommended}

!!! tip "Recommandé pour la plupart des utilisateurs"
Une commande, une configuration persistante et des mises à niveau faciles. Non`.env`ou`config.yaml`requis -
configurez tout à partir du panneau **Paramètres** du tableau de bord.

**Prérequis :** Docker Engine avec Compose v2.

```bash
git clone https://github.com/oraad/solar-ai-optimizer.git
cd solar-ai-optimizer
docker compose up -d --build
```

Ouvrez **http://localhost:8000**.

Pour exécuter des tests backend ou frontend :

```bash
docker compose run --rm test
docker compose run --rm frontend-test
```

**Pytest local (sans Docker) :** nécessite **Python 3.14+** (`bash scripts/check-python.sh`).
Depuis`backend/`, installer`requirements.txt` + `requirements-dev.txt`, puis exécutez
`python -m pytest tests/ -q`. Cela correspond à CI lors de l'utilisation des dépendances de développement du dépôt.
Sous Windows, si vous avez`pytest-homeassistant-custom-component`installé globalement pour HA
travail sur des composants personnalisés, cela peut bloquer les sockets asyncio et provoquer`SocketBlockedError`ou
`ProactorEventLoop ... _ssock`erreurs. Ce projet est`pytest.ini`désactive cela
plugin automatiquement ; vous pouvez également le désinstaller ou passer`-p no:homeassistant`.

Les remplacements d'environnement facultatifs entrent en jeu`docker-compose.yml` `environment:`ou un`.env`déposer
(voir[Configuration](configuration.md)).

### Mises à jour du tableau de bord (facultatif)

Les administrateurs peuvent rechercher de nouvelles versions sous **Paramètres → Mises à jour logicielles**. Le panneau répertorie
versions stables récentes avec des notes de version formatées. Sur les hôtes de mise à jour automatique Docker, choisissez
**Installer** sur n'importe quelle version (mise à niveau ou rétrogradation) ; une sauvegarde des données est créée automatiquement
avant chaque installation. Utilisez **Restore** dans la section des sauvegardes si une installation échoue.

Pour activer les **mises à jour en un clic** à partir du tableau de bord (extraire l'image et recréer le conteneur),
utilisez la superposition de mise à jour automatique. Cela monte le socket Docker hôte dans le conteneur d'application -
à utiliser uniquement sur des hôtes homelab de confiance :

```bash
docker compose -f docker-compose.yml -f docker-compose.self-update.yml up -d
```

Chaque installation de broches`SELF_UPDATE_IMAGE`à la balise sélectionnée (par ex.`ghcr.io/oraad/solar-ai-optimizer:0.5.8`).
Pour suivre`:latest`encore une fois, installez la dernière version à partir du sélecteur ou définissez la variable d'environnement manuellement
lors de la recréation du conteneur.

Le panneau Paramètres affiche la progression étape par étape (y compris le pourcentage d’extraction d’image). Le service est
**brièvement hors ligne** pendant l'échange de conteneur ; si la nouvelle version échoue à son contrôle de santé,
le conteneur précédent est restauré automatiquement. En cas d'échec, vérifiez
`/app/data/.update-logs/latest.log`sur le volume de données.

!!! note "Version illustrée"
L'installation en un clic nécessite **v0.5.5 ou plus récente** (l'image inclut la CLI Docker via
    `docker-cli`). Les versions inférieures à la v0.5.5 ne peuvent pas être installées via le sélecteur de tableau de bord.
Si vous avez activé la mise à jour automatique sur les versions 0.5.2 à 0.5.4, exécutez`docker pull`et recréer le conteneur
une fois manuellement avant d'utiliser le sélecteur de version.

---

## Docker (image autonome) {#docker-standalone-image}

!!! info "Image prédéfinie"
Utilisez-le lorsque vous ne voulez pas de Docker Compose. La même image GHCR alimente chaque chemin de déploiement.

**Prérequis :** Moteur Docker.

Tirez et courez :

```bash
docker pull ghcr.io/oraad/solar-ai-optimizer:latest

docker run -d --name solar-optimizer --restart unless-stopped \
  -v solar-data:/app/data \
  -p 8000:8000 \
  -e SHADOW_MODE=true \
  ghcr.io/oraad/solar-ai-optimizer:latest
```

Construire localement :

```bash
docker build -t solar-ai-optimizer .
docker run -d --name solar-optimizer --restart unless-stopped \
  -v solar-data:/app/data \
  -p 8000:8000 \
  ghcr.io/oraad/solar-ai-optimizer:latest
```

Ouvrez **http://localhost:8000**. Documentation de l'API : **http://localhost:8000/docs**.

Pour les **mises à jour du tableau de bord en un clic** sur un hôte autonome (pas de Compose), incluez le Docker
socket, indicateurs de mise à jour automatique et bilan de santé :

```bash
docker run -d --name solar-optimizer --restart unless-stopped \
  -v solar-data:/app/data \
  -p 8000:8000 \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -e SHADOW_MODE=true \
  -e SELF_UPDATE_ENABLED=true \
  -e SELF_UPDATE_IMAGE=ghcr.io/oraad/solar-ai-optimizer:latest \
  --health-cmd="curl -fsS http://localhost:8000/api/health || exit 1" \
  --health-interval=30s --health-timeout=5s --health-retries=3 --health-start-period=25s \
  ghcr.io/oraad/solar-ai-optimizer:latest
```

Coutume`docker run`les options (volumes supplémentaires, réseaux) au-delà de cette recette ne sont pas conservées
par installation en un clic - utiliser le manuel`docker pull`+ recréer pour ces configurations.

---

## Application Home Assistant {#home-assistant-add-on}

!!! tip "Meilleure intégration de Home Assistant"
Panneau d'entrée natif, jeton de superviseur automatique et aucun câblage manuel d'URL HA lorsque
les informations d'identification sont laissées vides dans les options de l'application.

**Prérequis :** Système d'exploitation Home Assistant ou installation supervisée avec accès à la boutique d'applications.

[![Ouvrez votre instance Home Assistant et affichez la boîte de dialogue d'ajout de dépôt.](https://my.home-assistant.io/badges/redirect_repository.svg)](https://my.home-assistant.io/redirect/repository/?owner=oraad&repository=solar-ai-optimizer)

1. **Paramètres → Applications → Boutique d'applications → ⋮ → Dépôts personnalisés** → ajouter :
   ```
   https://github.com/oraad/solar-ai-optimizer
   ```
2. Installez **Solar AI Optimizer** depuis la boutique.
3. Démarrez l'application et ouvrez le **panneau d'entrée** à partir de la barre latérale HA (icône : panneau solaire).

L'application télécharge l'image préconstruite `ghcr.io/oraad/solar-ai-optimizer` (étiquette correspondant à la
`version` du manifeste) — pas de compilation sur l'hôte HA. L'état persiste sous `/data`
(base de données, configuration d'exécution, modèle appris). Les options de l'application sont mappées aux variables d'environnement
via `run.sh` (mode shadow, niveau de journalisation, clés Solcast, jeton API, etc.).

La `version` du manifeste doit correspondre à une [version publiée](https://github.com/oraad/solar-ai-optimizer/releases) sur GHCR.

Câblage HA complet (entités, packages, authentification d'entrée) :[Configuration de l'assistant à domicile](home-assistant-setup.md).

---

## Proxmox LXC {#proxmox-lxc}

!!! info "One-liner sur Proxmox VE"
L'assistant de style scripts communautaires crée un LXC Debian ou Alpine avec Docker-in-LXC
(nesting + keyctl), extrait l'image GHCR et expose le port 8000.

**Prérequis :** Hôte Proxmox VE avec accès root shell.

Sur l'**hôte Proxmox** (Debian 13 Trixie LXC — par défaut) :

```bash
bash -c "$(curl -fsSL https://raw.githubusercontent.com/oraad/solar-ai-optimizer/main/proxmox/ct/solar-ai-optimizer.sh)"
```

Ou pour une base Alpine LXC plus petite :

```bash
bash -c "$(curl -fsSL https://raw.githubusercontent.com/oraad/solar-ai-optimizer/main/proxmox/ct/solar-ai-optimizer-alpine.sh)"
```

Ouvrez **http://&lt;lxc-ip&gt;:8000**.

Mises à jour, sauvegardes, remplacements de fork/branch et futures notes OCI :
[Déploiement Proxmox](proxmox.md).

---

## Liste de contrôle post-installation

Après tout chemin de déploiement :

1. Ouvrez le tableau de bord → **Paramètres**
2. **Connect Home Assistant** (URL + jeton de longue durée) — ignorez si vous utilisez le module complémentaire avec le câblage du superviseur par défaut
3. Définissez la **latitude/longitude du site** et les **tableaux photovoltaïques** (requis pour les prévisions solaires)
4. Mappez les **entités de lecture/écriture de l'onduleur** dans Paramètres → Carte des entités de l'onduleur
5. Laissez le **mode ombre** activé ; confirmer Les décisions générales semblent raisonnables
6. Importez éventuellement le[package HA de sécurité](https://oraad.github.io/solar-ai-integration/home-assistant-failsafe/)et activez le rythme cardiaque dans Paramètres → Sécurité intégrée
7. Passez au contrôle **live** uniquement lorsque vous faites confiance à l'optimiseur

Prochaines étapes :

- [Guide d'utilisation du tableau de bord](frontend-manual.md)- procédure pas à pas onglet par onglet
- [Rôles et accès](ingress-auth.md)— administrateur contre spectateur
- [Configuration de l'assistant à domicile](home-assistant-setup.md)— jetons, packages, découverte d'entités

---

## Mode démo (documentation / captures d'écran uniquement)

!!! danger "Ne jamais utiliser en production"
    `DEMO_MODE`injecte la télémétrie synthétique et signale HA comme connecté pour la capture d'écran
et les flux de travail de documentation. Ne **pas** activer sur un système qui contrôle un véritable onduleur.

Pour les responsables régénérant les captures d'écran du tableau de bord :

```bash
docker compose -f docker-compose.yml -f docker-compose.demo.yml up -d --build
docker compose exec solar python -m scripts.seed_demo
docker compose restart solar
docker compose --profile docs run --rm docs-screenshots npm ci   # once, or after lockfile changes
docker compose --profile docs run --rm docs-screenshots
```

Voir[Guide d'utilisation du tableau de bord → Régénération des captures d'écran](frontend-manual.md#regenerating-screenshots).

### Réinitialiser le mot de passe de l'administrateur local

Lorsque la connexion locale est activée, réinitialisez les informations d'identification à partir de la racine du dépôt :

```bash
./scripts/reset-local-password.sh
```

Voir[Entrée et autorisation → Réinitialiser le mot de passe de l'administrateur local](ingress-auth.md#reset-local-admin-password).
