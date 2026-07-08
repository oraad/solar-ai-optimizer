# Déploiement Proxmox

Déployez **Solar AI Optimizer** sur Proxmox VE à l'aide d'un[scripts-communautaires](https://github.com/community-scripts/ProxmoxVE)-assistant de style qui crée un LXC (Debian ou Alpine), installe Docker et exécute l'image GHCR publiée.

Pour d'autres chemins d'installation, voir[Installation](installation.md).

## Installation rapide (Debian)

Exécutez sur votre **hôte Proxmox** (en tant que root) :

```bash
bash -c "$(curl -fsSL https://raw.githubusercontent.com/oraad/solar-ai-optimizer/main/proxmox/ct/solar-ai-optimizer.sh)"
```

Les dispositions de l'assistant :

- Debian 13 LXC avec **nesting** et **keyctl** (requis pour Docker-in-LXC)
- Docker Engine + plugin Compose
- Conteneur`solar-optimizer`depuis`ghcr.io/oraad/solar-ai-optimizer:latest`
- Volume Docker persistant`solar-data`monté à`/app/data`

Ouvrez le tableau de bord à`http://<lxc-ip>:8000`.

**Home Assistant :** Installez l'[intégration HACS](https://oraad.github.io/solar-ai-integration/home-assistant-integration/) depuis [`oraad/solar-ai-integration`](https://github.com/oraad/solar-ai-integration). Générez un code d'appairage dans les paramètres Solar, puis ajoutez l'intégration dans HA (Core 2026.7.0+).

Le script d'installation écrit`/opt/solar-ai-optimizer/solar.env`avec`TRUST_INGRESS_HEADERS=true`(fait confiance aux en-têtes et aux ensembles d'utilisateurs d'entrée HA`X-Frame-Options: SAMEORIGIN`pour le panneau de la barre latérale) et les informations d'identification de l'administrateur local générées automatiquement. Le nom d'utilisateur et le mot de passe sont imprimés une seule fois à la fin de l'installation — enregistrez-les.

## Installation rapide (Alpine)

Pour un système d'exploitation de base LXC plus petit, utilisez plutôt l'assistant Alpine :

```bash
bash -c "$(curl -fsSL https://raw.githubusercontent.com/oraad/solar-ai-optimizer/main/proxmox/ct/solar-ai-optimizer-alpine.sh)"
```

Les dispositions du magicien alpin :

- Alpine 3.23 LXC (disque de 4 Go par défaut) avec **nesting** et **keyctl**
- Moteur Docker via`apk`(Service OpenRC,`json-file`draveur)
- Même`solar-optimizer`conteneur et`solar-data`volume comme chemin Debian

Utilisez le **script Alpine pour les mises à jour** sur les installations Alpine (le script in-LXC`update`la commande pointe automatiquement vers le script correspondant).

## Post-installation

1. **Enregistrez le mot de passe de l'administrateur local** affiché à la fin de l'installation (le nom d'utilisateur est par défaut`admin`). Utilisez-le pour vous connecter à`http://<lxc-ip>:8000`lorsque vous n'utilisez pas l'entrée HA.
2. Ouvrez **Paramètres** et définissez votre[URL de Home Assistant et jeton de longue durée](home-assistant-setup.md#long-lived-access-token).
3. Cartographiez les entités, l'emplacement et les paramètres de la batterie de l'onduleur.
4. Laissez **SHADOW MODE** activé jusqu'à ce que vous fassiez confiance aux décisions (par défaut).
5. En option, définissez`API_TOKEN`dans`/opt/solar-ai-optimizer/solar.env`sur le LXC et la même valeur dans **Paramètres → Sécurité API**.

La réexécution de l'assistant de mise à jour sur une installation qui dispose déjà d'informations d'identification d'administrateur local n'effectue **pas** de rotation du mot de passe. Pour réinitialiser le mot de passe :

```bash
bash /opt/solar-ai-optimizer/reset-local-password.sh
```

Voir[Entrée et autorisation – Réinitialiser le mot de passe de l'administrateur local](ingress-auth.md#reset-local-admin-password).

## Mise à jour

Réexécutez le script d'assistance que vous avez utilisé pour l'installation sur le conteneur existant (flux de mise à jour des scripts de communauté).

**Debian LXC :**

```bash
bash -c "$(curl -fsSL https://raw.githubusercontent.com/oraad/solar-ai-optimizer/main/proxmox/ct/solar-ai-optimizer.sh)"
```

**Alpine LXC :**

```bash
bash -c "$(curl -fsSL https://raw.githubusercontent.com/oraad/solar-ai-optimizer/main/proxmox/ct/solar-ai-optimizer-alpine.sh)"
```

Cela extrait la dernière image, recrée le`solar-optimizer`récipient et préserve le`solar-data`volume. Il migre également les anciennes installations : si`TRUST_INGRESS_HEADERS`ou les informations d'identification de l'administrateur local sont manquantes`solar.env`, ils sont ajoutés automatiquement et tout nouveau mot de passe est affiché une fois. Chaque exécution de mise à jour réécrit également`/usr/bin/update`pour pointer vers ce référentiel (corrige les anciennes installations qui pointaient vers des scripts de communauté).

Depuis **à l'intérieur du LXC**, vous pouvez également exécuter :

```bash
update
```

Cette commande exécute le même script d'assistance solaire (pas les scripts de communauté). Les fonctions d'assistance sont vendues sous [`proxmox/vendor/community-scripts/`](https://github.com/oraad/solar-ai-optimizer/tree/main/proxmox/vendor/community-scripts) et chargé via`SOLAR_REPO_RAW`au moment de l'exécution.

Ou mettez à jour manuellement dans le LXC (incluez le socket Docker et les indicateurs de mise à jour automatique afin
**Paramètres → Mises à jour logicielles → Mettre à jour maintenant** continue de fonctionner) :

```bash
docker pull ghcr.io/oraad/solar-ai-optimizer:latest
docker stop solar-optimizer && docker rm solar-optimizer
docker run -d --name solar-optimizer --restart unless-stopped \
  --env-file /opt/solar-ai-optimizer/solar.env \
  -v solar-data:/app/data \
  -p 8000:8000 \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -e SELF_UPDATE_ENABLED=true \
  -e SELF_UPDATE_ENV_FILE=/opt/solar-ai-optimizer/solar.env \
  -e SELF_UPDATE_IMAGE=ghcr.io/oraad/solar-ai-optimizer:latest \
  ghcr.io/oraad/solar-ai-optimizer:latest
```

!!! tip "Préférez l'assistant"
Le`update`la commande ou le script d'assistance côté hôte exécute le même flux d'extraction et de recréation
et est moins sujet aux erreurs que le manuel`docker run`.

## Sauvegarde {#backup}

Sauvegardez le volume Docker avant les mises à niveau :

```bash
docker run --rm -v solar-data:/data -v $(pwd):/backup alpine \
  tar czf /backup/solar-data-backup.tar.gz -C /data .
```

Fichiers importants :`solar.db`, `config.runtime.yaml`, `model.json`.

## Mise à jour du tableau de bord en un clic

Nouveau Proxmox installe, monte le socket Docker et définit`SELF_UPDATE_ENABLED=true`sur le
`solar-optimizer`récipient. Les administrateurs peuvent ouvrir **Paramètres → Mises à jour logicielles** pour consulter la version.
notes et cliquez sur **Mettre à jour maintenant** (même flux d'extraction et de recréation que`update`).

!!! warning "Accès au socket Docker"
Montage`/var/run/docker.sock`accorde une racine efficace sur le LXC. L'API de mise à jour est
administrateur uniquement, mais activez-le uniquement sur les hôtes en qui vous avez confiance. Réexécutez l'assistant d'installation/mise à jour
script pour appliquer le montage de socket sur les anciennes installations LXC.

La mise à jour en un clic nécessite **v0.5.5 ou plus récente** (l'image inclut la CLI Docker via le
`docker-cli`emballer). Images v0.5.2–0.5.4 sur Debian Trixie installées`docker.io`, lequel
ne fournit plus`/usr/bin/docker`. Si vous voyez *" Docker CLI n'est pas disponible dans ce
conteneur"*, extrayez **v0.5.5+** et recréez (`update`ou le manuel`docker run`au-dessus de).

Dashboard **Install** renomme le conteneur en cours d'exécution, démarre la nouvelle image, attend
`/api/health`, et revient au conteneur précédent si la vérification de l'état échoue. Progrès
(couches, tentatives d'intégrité) apparaît sous **Paramètres → Mises à jour logicielles**. Journaux d'assistance :
`/app/data/.update-logs/latest.log`à l'intérieur du`solar-data`volume.

## Dépannage

| Problème | Vérifier |
|-------|--------|
| *Docker CLI n'est pas disponible dans ce conteneur* (Paramètres → Mises à jour logicielles) | Corrigé dans **v0.5.5+** (`docker-cli`sur l'image). Sur les versions 0.5.2 à 0.5.4,`docker exec solar-optimizer command -v docker`est vide même après la recréation. Courir`update`après avoir extrait la v0.5.5+, ou recréer avec le manuel complet`docker run`drapeaux (prise +`SELF_UPDATE_*`env). |
| Panneau de barre latérale vierge /`X-Frame-Options: deny` | `TRUST_INGRESS_HEADERS=true`dans`/opt/solar-ai-optimizer/solar.env`; entrée`url`doit pointer vers`http://<lxc-ip>:8000`(pas votre URL HA) ; mettre à jour une image actuelle et recharger l'entrée dans HA |
| Docker ne démarre pas dans LXC | Besoins en conteneurs`nesting=1`et`keyctl=1`(défini par défaut dans le script d'assistance) ; sur Alpine, vérifiez également`rc-service docker status` |
| Impossible de joindre Home Assistant | LXC doit être acheminé vers HA sur votre réseau local ; utilisez HA IP au lieu de mDNS si nécessaire |
| Le contrôle de santé échoue |`docker logs solar-optimizer`à l'intérieur du LXC |
| Port 8000 utilisé | Modifier le mappage d'hôte dans`/opt/solar-ai-optimizer/solar.env`déploiement ou modifier le`docker run`port |
| **502** après le tableau de bord **Installer** | Vérifier`/app/data/.update-logs/latest.log`sur le`solar-data`volume. Si la restauration échoue, exécutez`update`à l'intérieur du LXC ou recréez-le manuellement avec le fichier complet`docker run`drapeaux (prise +`SELF_UPDATE_*`env). |
| La mise à jour du tableau de bord a semblé terminée, puis le service est tombé en panne | Restez sur Paramètres jusqu'à ce que la liste des étapes soit terminée. Les contrôles de santé échoués déclenchent une restauration automatique lorsque cela est possible ; sinon, utilisez **Restore** à partir de la sauvegarde de pré-installation. |

## Fourchette / branche

Pointez sur votre propre référence git :

```bash
export SOLAR_REPO_RAW="https://raw.githubusercontent.com/you/solar-ai-optimizer/your-branch"
bash -c "$(curl -fsSL ${SOLAR_REPO_RAW}/proxmox/ct/solar-ai-optimizer.sh)"          # Debian
bash -c "$(curl -fsSL ${SOLAR_REPO_RAW}/proxmox/ct/solar-ai-optimizer-alpine.sh)"   # Alpine
```

## Futur : Proxmox OCI natif (PVE 9.1+)

Proxmox VE 9.1+ peut exécuter des images OCI à partir de GHCR en tant qu'application LXC. Cette fonctionnalité est toujours un
**aperçu technologique** — les mises à jour nécessitent de recréer le CT et il n'y a pas de prise en charge de Docker Compose.

L'image publiée est **prête pour OCI** (exécutable`ENTRYPOINT`, étiquettes standards,`VOLUME /app/data`, configuration basée sur l'environnement).

Étapes manuelles pour les premiers utilisateurs du PVE 9.1+ :

1. **Stockage → Modèles CT → Extraire du registre OCI** —`ghcr.io/oraad/solar-ai-optimizer:latest`
2. **Créez CT** à partir de ce modèle (`--ostype unmanaged`).
3. Ajouter un point de montage **`mp0` → `/app/data`** (4 Go+ recommandés).
4. Dans **Options → Environnement**, définissez au minimum :
   - `SHADOW_MODE=true`
   - `DATA_DIR=/app/data`
   - `DATABASE_URL=sqlite+aiosqlite:////app/data/solar.db`
5. Démarrez le CT et ouvrez`http://<ct-ip>:8000`.

Jusqu'à ce que la prise en charge OCI arrive à maturité, l'assistant **Docker-in-LXC** ci-dessus est le chemin de production recommandé.

## Fichiers du référentiel

| Chemin | Rôle |
|------|------|
| [`proxmox/ct/solar-ai-optimizer.sh`](https://github.com/oraad/solar-ai-optimizer/blob/main/proxmox/ct/solar-ai-optimizer.sh) | Script hôte — Debian LXC (par défaut) |
| [`proxmox/ct/solar-ai-optimizer-alpine.sh`](https://github.com/oraad/solar-ai-optimizer/blob/main/proxmox/ct/solar-ai-optimizer-alpine.sh) | Script hôte — Alpine LXC |
| [`proxmox/install/solar-ai-optimizer-install.sh`](https://github.com/oraad/solar-ai-optimizer/blob/main/proxmox/install/solar-ai-optimizer-install.sh) | Fonctionne à l'intérieur du nouveau LXC |
| [`proxmox/lib/solar-common.sh`](https://github.com/oraad/solar-ai-optimizer/blob/main/proxmox/lib/solar-common.sh) | Image partagée/assistants de déploiement |
| [`proxmox/vendor/community-scripts/`](https://github.com/oraad/solar-ai-optimizer/tree/main/proxmox/vendor/community-scripts) | Assistants de scripts communautaires fournis (épinglés en amont) |

La copie canonique de ce guide vit sur le[site de documentation](https://oraad.github.io/solar-ai-optimizer/proxmox/). Le référentiel conserve également [`proxmox/README.md`](https://github.com/oraad/solar-ai-optimizer/blob/main/proxmox/README.md) pour la navigation sur GitHub.
