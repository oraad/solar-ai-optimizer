# Configuration

Configuration des couches Solar AI Optimizer à partir de plusieurs sources. Le panneau **Paramètres** dans
le tableau de bord est la principale interface pour les opérateurs.

## Sources de configuration

| Source | Objectif |
|--------|---------|
| **Paramètres de l'interface utilisateur** | Configuration principale : connexion HA, fuseau horaire du site, carte des entités, batterie, réserve, prévisions, contrôle |
| `config/config.yaml`(dans l'image) | Valeurs par défaut de base ; Remplacements de l'interface utilisateur stockés dans le volume de données |
| `config.runtime.yaml`(volume de données) | Modifications persistantes de l'interface utilisateur (fusion profonde sur la base) |
| `.env`/ Composer`environment`| Secrets, indicateurs de fonctionnalités, jeton API facultatif |
| Module complémentaire HA`options.json`| Mappé aux variables d'environnement par`run.sh`lors de l'exécution en tant que module complémentaire |

Sections clés (toutes modifiables dans Paramètres) :

- Connexion Home Assistant
- **Site** — Fuseau horaire IANA ou **Auto** (depuis Open-Meteo à la latitude/longitude du site) ; coordonnées du site ; détermine les limites des jours de prévision, les périodes d'apprentissage de charge/température, l'affichage du tableau de bord et les horodatages API/WebSocket (doit correspondre au fuseau configuré dans Home Assistant)
- Carte des entités de l'onduleur (lecture des capteurs + écriture des commandes)
- Spécifications de la batterie et politique de réserve
- Fournisseur de prévisions, panneaux photovoltaïques, modèle de température
- Contrôle du timing et du mode moteur (`rules`ou`mpc`)
- **Le sous-système active** —`engine.enabled`(réserve/MPC/prévision),`grid_charge.enabled`(écritures de charge du réseau de l'onduleur),`load_shedding.enabled`(changements de niveaux) ; chacun peut être basculé indépendamment dans Paramètres ou dans l'onglet Délestage
- Sécurité intégrée — arrêt charge réseau au maximum (le chien de garde HA en cas de crash est l'intégration HACS)

Le **Délestage** se configure dans l'onglet dédié **Délestage** (et non dans Paramètres).
Voir[Guide utilisateur du tableau de bord → Niveaux de délestage](frontend-manual.md#load-shedding-tiers).

Voir[Configuration de l'assistant à domicile](home-assistant-setup.md)pour le mappage de connexion et d'entité,
et[Guide d'utilisation du tableau de bord → Paramètres](frontend-manual.md#settings)pour une présentation pas à pas de l'interface utilisateur.

## Variables d'environnement facultatives

Documenté dans [`.env.example`](https://github.com/oraad/solar-ai-optimizer/blob/main/.env.example).
Remplacements courants :

| Variables | Objectif |
|----------|---------|
| `HA_BASE_URL` / `HA_TOKEN`| Connexion Home Assistant (ou définie dans l'interface utilisateur) |
| `SHADOW_MODE` | `true`= observer uniquement (par défaut) |
| `LOCAL_ADMIN_PASSWORD_HASH` / `SESSION_SECRET`| Connexion administrateur local pour un accès autonome |
| `TRUST_INGRESS_HEADERS`| Faites confiance aux en-têtes d'utilisateur d'entrée HA et autorisez l'iframe de la barre latérale (`SAMEORIGIN`; automatique sur le module complémentaire) |
| `API_TOKEN`| Jeton porteur pour les scripts ; protège l'API lorsqu'elle est définie |
| `CORS_ORIGINS`| Origines CORS séparées par des virgules (par défaut`*`) |
| `ML_LOAD_ENABLED`| Prévisions de charge augmentant le gradient (nécessite Sklearn dans l'image) |
| `DEMO_MODE`| **Documents uniquement** — télémétrie synthétique ; jamais en production |

Quand`API_TOKEN`est défini, saisissez la même valeur dans **Paramètres → Sécurité API**.

## Solcast (fournisseur solaire en option)

Dans Paramètres, définissez **prévision → fournisseur** sur`solcast`. Les informations d'identification ne sont **pas** stockées dans
la configuration de l'interface utilisateur - définissez les variables d'environnement (ou les options du module complémentaire HA) :

| Variables | Objectif |
|----------|---------|
| `SOLCAST_API_KEY`| Jeton au porteur de votre compte Solcast |
| `SOLCAST_RESOURCE_ID`| ID du site sur le toit à partir du tableau de bord Solcast |

Les deux doivent être définis lorsque le fournisseur est`solcast`; sinon l'application revient à Open-Meteo
et affiche un avertissement de mauvaise configuration.

## Enregistrement

| Variables | Valeurs | Par défaut |
|----------|--------|---------|
| `LOG_LEVEL`| DEBUG, INFO, AVERTISSEMENT, ERREUR | INFOS |
| `LOG_FORMAT` | `text`, `json`| texte |

Ensemble`LOG_FORMAT=json`pour les agrégateurs de journaux de production (un objet JSON par ligne).

## Modes moteur

| Mode | Descriptif |
|------|-------------|
| `rules`| Moteur de règles par défaut — réserve dynamique, utilisation réactive de la grille |
| `mpc`| Expédition de batterie LP en option (nécessite PuLP dans l'image) |

Définissez **Moteur → mode** dans Paramètres. MPC revient aux règles si PuLP n'est pas disponible.

### Réserve et charge adaptative

`reserve.critical_load_w` et `min_autonomy_hours` forment la base de survie configurée. Avec `adaptive_load_enabled` (activé par défaut), le plancher d'autonomie et le pont solaire utilisent aussi une moyenne récente de charge maison (`load_power` sur `adaptive_load_window_minutes`) et, en décharge, `max(0, -battery_power)` — le signal adaptatif est **max(moyenne charge, moyenne décharge)**. L'ordre des priorités module la part de cette moyenne au-dessus du critique. `adaptive_load_cap_w` plafonne les watts effectifs (défaut : 3× critique). Voir [decision-cycle.md](decision-cycle.md).

### Fenêtre d'opportunité réseau

Dans **Paramètres → Charge réseau**, configurez la durée typique de présence (`max_continuous_present_minutes`, défaut 120) et la décote (`grid_window_safety_factor`, 0,75). Les coupures ≤ `max_outage_ignore_minutes` (30) restent dans une même opportunité ; `grid_present=false` en direct arrête toujours la charge. `max_grid_import_w` / `max_grid_import_entity` (entité HA `number`, W ou kW) plafonnent les ampères de planification si le site est plus serré que l'onduleur.

### Ordre de priorité d'optimisation

Dans **Paramètres → Moteur**, réorganisez`priority_order`(par défaut : résilience, économies,
autosuffisance). La liste doit inclure chaque valeur exactement une fois. Exemple dans
`config.runtime.yaml`:

```yaml
engine:
  mode: rules
  priority_order:
    - resilience
    - savings
    - self_sufficiency
```

Les priorités de rang supérieur influencent les tampons de réserve, la notation du risque de panne d'électricité et le MPC.
poids objectifs et force du facteur de rampe de charge du réseau. **Économies** signifie
utilisation opportuniste du réseau lorsqu’il est présent – ​​pas d’optimisation du temps d’utilisation ou des tarifs.

## Délestage

Configurez les niveaux dans l'onglet **Délestage** du tableau de bord. Chaque niveau peut contrôler
plusieurs interrupteurs d'alimentation (`switch.*`ou`input_boolean.*`) qui jette et restaure
ensemble en utilisant l'hystérésis SOC. Les hangars **prioritaires** inférieurs sont les premiers.

Entités compagnons sur le même appareil Home Assistant (climatisation, sélection, ventilateur, etc.)
sont découverts automatiquement et pris en photo lors de la perte ; ils sont restaurés lorsque
le niveau revient. Les appareils qui étaient **éteints avant la perte** ne sont jamais éteints
allumé par restauration.

Les instantanés sont capturés **une fois par épisode de délestage** (première fois qu'une entité
d'alimentation est coupée) et conservés jusqu'à la restauration, l'effacement ou le prune de
configuration. Les cycles de délestage suivants pendant que l'interrupteur reste éteint ne
re-capturent pas et n'écrasent pas cet instantané. Un instantané peut être capturé même lorsque
le watchdog d'écriture HA est périmé ; l'écriture OFF attend toujours que HA soit frais.

| Champ | Objectif |
|-------|---------|
| `restore_enabled`| Restaurer sur SOC lorsque`soc >= restore_above_soc` |
| `restore_on_grid`| Restaurer lorsque la grille est présente (si l'indicateur global est activé) |
| `state_entities`| Carte facultative de l'entité de puissance → ID d'entité compagnon |

Omettre une clé dans`state_entities`pour découvrir automatiquement les compagnons ; ensemble`[]`pour
perte par interrupteur uniquement. Les instantanés persistent sous le volume de données et sont élagués
lorsque la configuration des niveaux change.

API (administrateur) :`GET /api/shed/device-companions?entity_id=…`prévisualise la découverte ;
`GET /api/shed/snapshots`répertorie l’état stocké avant la perte.

Voir[Configuration de Home Assistant → Délestage](home-assistant-setup.md#load-shedding)
pour des exemples d’entités.

## Extras de construction Docker

L'image par défaut installe les extras de la phase 3/4 (PuLP, scikit-learn, numpy) via`INSTALL_EXTRAS=1`.
Pour une image épurée :

```bash
docker compose build --build-arg INSTALL_EXTRAS=0
```

## Sauvegarde des données

Le`solar-data`Volume Docker (ou module complémentaire`/data`) contient :

- `solar.db`— télémétrie et historique d'audit
- `config.runtime.yaml`- Remplacements de la configuration de l'interface utilisateur
- `model.json`— Biais de prévision appris / profil de charge
- `shed_snapshots.json` — état pré-délestage en attente

Sauvegardez ce volume avant les mises à niveau. Voir[Déploiement Proxmox → Sauvegarde](proxmox.md#backup)
pour un exemple de commande tar.

## Mise à niveau

```bash
docker compose up -d --build
```

La mutation des points de terminaison de l'API nécessite`Authorization: Bearer <token>`quand`API_TOKEN`est réglé.
