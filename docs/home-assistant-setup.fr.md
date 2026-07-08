# Configuration de l'assistant à domicile

Solar AI Optimizer s'intègre à Home Assistant en tant qu'**application externe** — c'est
**pas** une intégration personnalisée HACS ou`custom_components/`plate-forme. L'optimiseur se connecte
sur REST et WebSocket, mappe les entités de l'onduleur à partir des paramètres et utilise éventuellement un petit
HA **Package YAML** pour une automatisation sécurisée des pulsations.

Choisissez votre chemin de déploiement :

| Chemin | Quand utiliser |
|------|-------------|
| [Application Superviseur](#supervisor-add-on)| HAOS ou Supervisé — recommandé pour la plupart des utilisateurs HA |
| [Docker + hass_ingress](#docker-with-hass_ingress)| Conteneur autonome sur le même réseau que HA |
| [Docker autonome](#standalone-docker)| Direct`:8000`accéder; connexion facultative de l'administrateur local |

Après la connexion, complétez[mappage d'entité](#inverter-entity-discovery)et éventuellement
[importer le package de sécurité](#home-assistant-packages).

---

## Jeton d'accès longue durée {#long-lived-access-token}

Requis pour les déploiements Docker et Proxmox (l'application HA utilise automatiquement le jeton Supervisor lorsque les champs sont laissés vides).

1. Dans Home Assistant, ouvrez votre **Profil** (avatar en bas à gauche).
2. Faites défiler jusqu'à **Sécurité** → **Jetons d'accès longue durée**.
3. Cliquez sur **Créer un jeton**, nommez-le (par ex.`solar-ai-optimizer`), et copiez le jeton immédiatement — il n'est affiché qu'une seule fois.
4. Dans le tableau de bord de l'optimiseur → **Paramètres → Connexion Home Assistant** :
- **URL :**`http://homeassistant.local:8123`ou votre IP HA (par ex.`http://192.168.1.10:8123`)
- **Jeton :** collez le jeton de longue durée
- **Vérifier SSL :** activer si HA utilise HTTPS avec un certificat valide

Pour l'**application HA**, laissez l'URL/le jeton vide pour utiliser `http://supervisor/core` et `SUPERVISOR_TOKEN`.

Faites pivoter périodiquement les jetons et révoquez les jetons inutilisés à partir de la même page de sécurité.

---

## Application Superviseur {#supervisor-add-on}

[![Ouvrez votre instance Home Assistant et affichez la boîte de dialogue d'ajout de dépôt.](https://my.home-assistant.io/badges/redirect_repository.svg)](https://my.home-assistant.io/redirect/repository/?owner=oraad&repository=solar-ai-optimizer)

1. **Paramètres → Applications → Boutique d'applications → ⋮ → Dépôts personnalisés** → ajouter :
   ```
   https://github.com/oraad/solar-ai-optimizer
   ```
2. Installez **Solar AI Optimizer** et démarrez-le.
3. Ouvrez le **panneau d'entrée** à partir de la barre latérale HA.
4. Dans **Paramètres**, configurez la latitude/longitude, les panneaux photovoltaïques et[entités onduleurs](#inverter-entity-discovery).

L'application télécharge `ghcr.io/oraad/solar-ai-optimizer` depuis GHCR (étiquette de version du manifeste) ; pas de build sur l'hôte HA.

Les options de l'application (interface utilisateur du superviseur) sont mappées aux variables d'environnement via `run.sh` :

| Option de l'application | Variable d'environnement |
|---------------|---------------------|
| `shadow_mode` | `SHADOW_MODE` |
| `log_level` | `LOG_LEVEL` |
| `ha_base_url` / `ha_token` | `HA_BASE_URL` / `HA_TOKEN` |
| `solcast_api_key` | `SOLCAST_API_KEY` |
| `api_token` | `API_TOKEN` |

Ingress est automatiquement approuvé lors de son exécution en tant qu'application Superviseur (`SUPERVISOR_TOKEN`); ensemble `TRUST_INGRESS_HEADERS=true` pour les déploiements externes Docker/Proxmox. Cela permet l'identité de l'utilisateur mandaté et `X-Frame-Options: SAMEORIGIN` pour le panneau de la barre latérale.
Voir[Rôles et accès](ingress-auth.md)pour le comportement de l'administrateur par rapport au spectateur.

---

## Docker avec hass_ingress {#docker-with-hass_ingress}

À utiliser lorsque l'optimiseur s'exécute en tant que conteneur distinct mais que les utilisateurs HA doivent l'ouvrir à partir de la barre latérale HA.

### 1. Conteneur optimiseur

Exemple`docker-compose.yml`service sur le même réseau Docker que Home Assistant :

```yaml
services:
  solar-ai-optimizer:
    image: ghcr.io/oraad/solar-ai-optimizer:latest
    container_name: solar-ai-optimizer
    restart: unless-stopped
    environment:
      SHADOW_MODE: "true"
      TRUST_INGRESS_HEADERS: "true"
      DATA_DIR: /app/data
      DATABASE_URL: sqlite+aiosqlite:////app/data/solar.db
      # Optional direct admin access to :8000 (keep port unpublished if ingress-only):
      # LOCAL_ADMIN_USERNAME: admin
      # LOCAL_ADMIN_PASSWORD_HASH: ...
      # SESSION_SECRET: ...
    volumes:
      - solar-data:/app/data
    networks:
      - homeassistant
    # Do not publish 8000 publicly when using ingress-only access.

networks:
  homeassistant:
    external: true   # or shared with your HA stack

volumes:
  solar-data:
```

Configurez l'URL/le jeton HA dans **Paramètres** après le premier démarrage, ou définissez`HA_BASE_URL` / `HA_TOKEN`dans`environment`.

### 2. Blocage d'entrée Home Assistant

Ajouter à`configuration.yaml`:

```yaml
ingress:
  solar_ai:
    title: Solar AI
    icon: mdi:solar-power-variant
    require_admin: false
    work_mode: ingress
    url: http://solar-ai-optimizer:8000
    headers:
      X-Remote-User-Id: $user_id
      X-Remote-User-Name: $username
      X-Remote-User-Display-Name: $user_name
```

Recharger l'entrée : **Outils de développement → YAML → INGRESS**.

Nécessite`TRUST_INGRESS_HEADERS=true`sur l'optimiseur afin que HA puisse intégrer le panneau dans la barre latérale (`X-Frame-Options: SAMEORIGIN`).

Modèles d'authentification complète :[Rôles et accès](ingress-auth.md).

---

## Docker autonome {#standalone-docker}

```bash
docker compose up -d --build
```

Ouvrez **http://localhost:8000** directement. Activez éventuellement la connexion de l'administrateur local via
`LOCAL_ADMIN_PASSWORD_HASH`et`SESSION_SECRET`(voir[Configuration](configuration.md)).

Définissez l'URL et le jeton HA dans **Paramètres** – aucun wrapper d'entrée requis.

---

## Forfaits Assistant à domicile {#home-assistant-packages}

Les packages vous permettent de diviser la configuration YAML en fichiers sous`config/packages/`.

### Activer les packages dans configuration.yaml {#enable-packages-in-configurationyaml}

Si ce n'est pas déjà présent :

```yaml
homeassistant:
  packages: !include_dir_named packages
```

Redémarrez Home Assistant ou rechargez la configuration de base après avoir ajouté ce bloc.

### Package de battement de coeur sécurisé

Copiez l'exemple de package dans votre configuration HA :

```
config/packages/solar-optimizer-failsafe.yaml
```

Fichier source dans le référentiel :
[`examples/home-assistant/packages/solar-optimizer-failsafe.yaml`](https://github.com/oraad/solar-ai-optimizer/blob/main/examples/home-assistant/packages/solar-optimizer-failsafe.yaml)

Le package crée :

| Entité | Objectif |
|--------|---------|
| `input_datetime.solar_optimizer_heartbeat`| Horodatage du battement de coeur (pulsé par l'optimiseur) |
| `input_number.solar_optimizer_max_grid_charge_a`| Courant de charge maximum du réseau pour une automatisation de sécurité |
| `binary_sensor.solar_optimizer_healthy`| Capteur de modèle (périmé si battement de coeur > 120 s) |

Avant de recharger, modifiez les espaces réservés :

- `switch.YOUR_GRID_CHARGE_ENTITY`— identique à Paramètres → Onduleur → Activation de la charge du réseau
- `number.YOUR_MAX_GRID_CHARGE_CURRENT`— identique à Paramètres → Onduleur → Courant de charge maximum du réseau
- `input_number.solar_optimizer_max_grid_charge_a`**initial** — correspond à Paramètres → Charge du réseau → Courant de charge maximum du réseau (A)

Rechargez les **helpers**, les **modèles** et les **automatisations**. Configurez ensuite le côté optimiseur :
[Sécurité intégrée de Home Assistant](https://oraad.github.io/solar-ai-integration/home-assistant-failsafe/).

---

## Découverte de l'entité onduleur {#inverter-entity-discovery}

L'optimiseur utilise une **carte d'entité indépendante du fournisseur** dans Paramètres → Carte d'entité de l'onduleur.
Les capacités logiques (SOC de la batterie, puissance photovoltaïque, activation de la charge du réseau, etc.) correspondent à votre HA
identifiants d’entité. Lorsque HA est connecté, les champs proposent la **complétion automatique** à partir d'entités actives.

Utilisez **Outils de développement → États** pour rechercher les ID d'entité. Les tableaux ci-dessous sont des **points de départ**
— la dénomination varie selon la version d'intégration et le modèle d'appareil.

### Lire les capteurs

| Capacité | Deye/Sunsynk (MSA) | Victron (Vénus / HA) | Growatt |
|------------|----------------------|----------------------|---------|
| `pv_power` | `sensor.*_pv*_power`ou`sensor.*_solar_power` | `sensor.*_pv_power` | `sensor.*_pv_power` |
| `load_power` | `sensor.*_load_power` | `sensor.*_ac_consumption` | `sensor.*_load_power` |
| `battery_soc` | `sensor.*_battery_soc` | `sensor.*_soc` | `sensor.*_battery_soc` |
| `battery_power` | `sensor.*_battery_power` | `sensor.*_battery_power` | `sensor.*_battery_power` |
| `grid_power` | `sensor.*_grid_power` | `sensor.*_grid_power` | `sensor.*_grid_power` |
| `grid_present` | `binary_sensor.*_grid_connected` | `binary_sensor.*_ac_input` | `binary_sensor.*_grid_status` |
| `battery_temp` | `sensor.*_battery_temperature` | `sensor.*_battery_temperature` | `sensor.*_battery_temp` |

### Écrire des contrôles

| Capacité | Deye/Sunsynk (MSA) | Victron | Growatt |
|------------|----------------------|---------|---------|
| `grid_charge_enable` | `switch.*_grid_charge`| spécifique à l'intégration |`switch.*_grid_charge` |
| `max_grid_charge_current` | `number.*_grid_charge_current` | `number.*_max_charge_current` | `number.*_max_grid_charge` |

### Délestage {#load-shedding}

Chaque niveau accepte **plusieurs entités de commutation** (pompe de piscine + chauffage, interrupteur d'alimentation CA, etc.).
Utiliser`switch.*`ou`input_boolean.*`entités chargées du contrôle du pouvoir.

Les **entités associées** (climatisation, sélection, ventilateur, etc.) sur le même appareil Home Assistant sont
découvert automatiquement et instantané lors de la perte ; ils sont restaurés lorsque le niveau
revient. Les appareils qui étaient **éteints avant la perte** ne sont jamais activés par la restauration.

Options par niveau :

| Champ | Objectif |
|-------|---------|
| `restore_enabled`| Restaurer sur SOC lorsque`soc >= restore_above_soc` |
| `restore_on_grid`| Restaurer lorsque la grille est présente (si l'indicateur global est activé) |
| `state_entities`| Carte de remplacement facultative de l'entité de puissance → ID d'entité compagnon |

Omettre une clé dans`state_entities`pour découvrir automatiquement les compagnons ; ensemble`[]`pour interrupteur uniquement.

Configurez dans l'onglet **Délestage** du tableau de bord. Les entités **écriture** de charge du réseau ne sont pas requises pour les déploiements avec délestage uniquement (utilisez le préréglage de délestage uniquement sur cet onglet). Vous avez toujours besoin de capteurs **read** de l'onduleur pour le SOC de la batterie et la présence du réseau.

Voir[Guide utilisateur du tableau de bord → Niveaux de délestage](frontend-manual.md#load-shedding-tiers).

### Température extérieure (facultatif)

Paramètres → Prévisions → Température → **Entité de capteur extérieur** — n'importe lequel`sensor.*`rapport
°C pour une prévision de charge en fonction de la température.

---

## Liste de contrôle de vérification

1. La barre supérieure du tableau de bord affiche **HA connecté** (pas hors ligne).
2. Les cartes d'état de présentation affichent les valeurs SOC, PV et de charge en direct.
3. L'onglet Prévisions affiche un graphique sur 48 heures (nécessite latitude/longitude dans Paramètres).
4. Paramètres des champs d'entité à saisie semi-automatique lors de la saisie (nécessite un jeton valide).
5. Sécurité intégrée :`input_datetime.solar_optimizer_heartbeat`mises à jour dans les outils HA Developer (si le package est importé).

## Dépannage

| Symptôme | Que vérifier |
|---------|----------------|
| **HA hors ligne** | URL accessible depuis le conteneur ; jeton valide ; Le paramètre SSL correspond à HA |
| **Cartes de statut vides** | Lire les entités mappées correctement ; entités non`unavailable`en HA |
| **Aucune prévision** | Ensemble latitude/longitude ; pas`0,0` |
| **Échec des écritures** | Écrire les entités mappées ; mode ombre désactivé ; HA accessible |
| **Entrée 401/403** |`TRUST_INGRESS_HEADERS=true`; L'URL d'entrée correspond au nom d'hôte du conteneur |

## Guides associés

- [Installation](installation.md)— Docker, application HA, Proxmox
- [Sécurité intégrée de Home Assistant](https://oraad.github.io/solar-ai-integration/home-assistant-failsafe/) — réglage du rythme cardiaque
- [Rôles et accès](ingress-auth.md)— administrateur contre spectateur
- [Configuration](configuration.md)- variables d'environnement et persistance
