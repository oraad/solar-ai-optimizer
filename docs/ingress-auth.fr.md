# Entrée et autorisation

Solar AI Optimizer prend en charge trois façons d'authentifier l'accès au tableau de bord et à l'API :

1. **Ingress Home Assistant** — La connexion HA enveloppe l'application ; l'identité de l'utilisateur provient des en-têtes proxy.
2. **Connexion de l'administrateur local** — nom d'utilisateur/mot de passe avec un cookie de session signé pour un accès direct autonome.
3. **Jeton de support API** —`Authorization: Bearer <API_TOKEN>`pour les scripts et l'automatisation.

L'entrée est toujours prioritaire : lorsque des en-têtes d'utilisateurs HA de confiance sont présents, la page de connexion locale est contournée.

## Modèles de déploiement

### A. Autonome avec connexion locale

À utiliser lors de l'exposition directe du tableau de bord (par ex.`http://server:8000`).

```env
LOCAL_ADMIN_USERNAME=admin
LOCAL_ADMIN_PASSWORD_HASH=$2b$12$...   # bcrypt hash; prefer over plain password
SESSION_SECRET=long-random-string
TRUST_INGRESS_HEADERS=false
```

Générez un hachage bcrypt :

```bash
python -c "import bcrypt; print(bcrypt.hashpw(b'your-password', bcrypt.gensalt()).decode())"
```

Le navigateur affiche une page de connexion jusqu'à ce que`POST /api/auth/login`réussit. Déconnectez-vous de **Paramètres → Sécurité API**. Le formulaire de connexion prend en charge l'enregistrement et le remplissage automatique du mot de passe du navigateur (Chrome, Edge, Firefox).

### Réinitialiser le mot de passe de l'administrateur local {#reset-local-admin-password}

Les informations d'identification peuvent être réinitialisées sans modifier manuellement les fichiers d'environnement. Le script de réinitialisation écrit dans`$DATA_DIR/local_auth.env`sur le volume de données ;`run.sh`charge ce fichier au démarrage, en remplaçant l'environnement du conteneur pour les clés d'authentification.

**Docker Compose** (à partir de la racine du dépôt) :

```bash
./scripts/reset-local-password.sh
```

**Proxmox LXC** (à l'intérieur de l'hôte du conteneur) :

```bash
bash /opt/solar-ai-optimizer/reset-local-password.sh
# or, after sourcing solar-common.sh:
solar_reset_local_password
```

Possibilités :`--password PASS`, `--username USER`, `--keep-sessions`, `--no-restart`.

Le script imprime le nouveau nom d'utilisateur et le nouveau mot de passe une fois et redémarre le conteneur par défaut.

### B. Autonome + hass_ingress (Docker)

Les utilisateurs HA accèdent à l'application via la barre latérale HA ; ils n'utilisent pas la page de connexion locale. Conserver la connexion locale pour un accès direct`:8000`accès si le port est publié.

**Conteneur d'optimisation :**

```env
LOCAL_ADMIN_USERNAME=admin
LOCAL_ADMIN_PASSWORD_HASH=...
SESSION_SECRET=...
TRUST_INGRESS_HEADERS=true
```

Ne pas publier le port`8000`publiquement lors de l’utilisation d’un accès d’entrée uniquement.

Lorsque l'entrée est approuvée : module complémentaire natif (`SUPERVISOR_TOKEN`) ou`TRUST_INGRESS_HEADERS=true`— les ensembles backend`X-Frame-Options: SAMEORIGIN`Ainsi, l'iframe de la barre latérale HA peut intégrer le panneau et faire confiance aux en-têtes d'identité de l'utilisateur mandaté. L'accès direct autonome (ni drapeau) conserve`DENY`et ne fait pas confiance aux en-têtes d'entrée.

**Assistant à domicile`configuration.yaml`:**

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

Rechargez l'entrée dans **Outils de développement → YAML → INGRESS**.

Pour[hass_ingress](https://github.com/lovelylain/hass_ingress)(HACS), utilisez`work_mode: ingress`et`ui_mode: normal`. Ne pas utiliser`ui_mode: replace`- ce mode sert à intégrer des pages HA, pas des applications externes. hass_ingress v1.3.0+ prend en charge`$user_id`, `$username`, et`$user_name`dans le`headers`bloc.

### C. Module complémentaire Home Assistant

Quand`SUPERVISOR_TOKEN`est défini, l'entrée est automatiquement approuvée (en-têtes d'utilisateur et cadrage iframe de la barre latérale). La connexion locale est facultative et désactivée par défaut. Ouvrez le panneau à partir de la barre latérale HA.

!!! info "Les rôles en un coup d'oeil"
Les utilisateurs **Admin** voient les cinq onglets du tableau de bord (y compris Assistant et Paramètres).
Les utilisateurs **Viewer** voient uniquement la présentation, les prévisions et l'historique, avec des remplacements limités sur la présentation.
Voir le[Guide d'utilisation du tableau de bord → Rôles du tableau de bord](frontend-manual.md#dashboard-roles)pour les captures d'écran et la matrice complète des fonctionnalités.

## Administrateur vs spectateur (utilisateurs entrants)

| Rôle | Comment déterminé | Tableau de bord |
|------|----------------|-----------|
| **Administrateur** | Propriétaire HA ou`system-admin`groupe; ou`ADMIN_USER_IDS`liste verte | Tableau de bord complet (Aperçu, Prévisions, Historique, Assistant, Paramètres) |
| **Visionneuse** | Autres utilisateurs HA via l'entrée | Présentation, Prévisions et Historique uniquement : contrôles limités de l'opérateur sur Présentation |

Les téléspectateurs peuvent **mettre en pause/reprendre** le moteur et chaque sous-système (délestage, charge réseau, optimisation) et activer le **kill switch** (avec confirmation). Ils ne peuvent pas épingler le SOC de réserve, forcer la facturation du réseau, exécuter un cycle de contrôle, actualiser les prévisions, effacer les remplacements, basculer shadow/live dans l'UI, utiliser l'Assistant ou ouvrir les paramètres.

Les routes d'API en mutation appliquent les mêmes limites sur le backend. Les API de configuration et de modèle restent réservées aux administrateurs.

Liste d'autorisation facultative pour les bris de glace :

```env
ADMIN_USER_IDS=abc123,def456
```

## Référence API

| Point de terminaison | Authentification | Descriptif |
|----------|------|-------------|
| `GET /api/me`| Séance | Utilisateur et rôle actuels |
| `POST /api/auth/login`| Publique | Connexion de l'administrateur local ; définit un cookie |
| `POST /api/auth/logout`| Publique | Efface le cookie de session |
| `GET /api/auth/status`| Publique |`{ local_auth_enabled, login_required }` |
| `GET /api/health`| Publique | Sonde de vivacité |
| `GET /api/config`| Administrateur | Configuration complète du tableau de bord (spectateurs refusés) |
| `GET /api/entities`| Administrateur | Liste d'entités HA pour la saisie semi-automatique des paramètres |
| `POST /api/override`| Séance | Admin : tout champ de remplacement ; téléspectateur : `shadow_mode`, `pause_engine`, `pause_shedding`, `pause_grid_charge`, `pause_optimization`, `kill_switch` (`kill_switch` nécessite `confirm=true`) |

## Liste de contrôle de sécurité

- Utiliser`LOCAL_ADMIN_PASSWORD_HASH`, pas simple`LOCAL_ADMIN_PASSWORD`, en production.
- Ensemble`SESSION_SECRET`à une longue valeur aléatoire lorsque l'authentification locale est activée.
- Ensemble`SESSION_COOKIE_SECURE=true`lorsqu'il est servi via HTTPS.
- Garder`API_TOKEN`pour CI/scripts ; il accorde un accès administrateur sans la page de connexion.
- Bloquer l'accès LAN direct au port`8000`lorsque tous les utilisateurs doivent passer par l’entrée HA.

## Dépannage

### Le propriétaire ou l'administrateur voit le badge VIEWER

1. Ouvrez DevTools → Réseau et vérifiez`GET .../api/me`. Attendre`auth_mode: "ingress"`et`is_admin: true`pour les propriétaires de HA.
2. Si`is_admin`est faux, vérifiez les journaux de l'optimiseur pour`config/auth/list failed`ou`Failed to fetch HA config/auth/list`.
3. Assurez-vous que le jeton HA de longue durée (env`HA_TOKEN`ou **Paramètres → Connexion Home Assistant**) a été créé à partir d'un compte administrateur/propriétaire — l'API de liste d'utilisateurs nécessite des informations d'identification d'administrateur sur le jeton.
4. Bris de glace : réglé`ADMIN_USER_IDS=<your-user-id>`(copie`user_id`depuis`/api/me`) et redémarrez le conteneur.

### Une iframe vide ou une interface utilisateur HA clignote à l'intérieur du panneau lors du premier chargement {#blank-iframe-or-ha-ui-flashes-inside-the-panel-on-first-load}

**Iframe vide avant l'apparition de Solar AI :** les versions actuelles affichent un message de démarrage de marque (« Vérification de l'accès… ») dès que l'iframe d'entrée charge le HTML, avant l'exécution de JavaScript. Mettez à niveau vers **v0.5.7+** si vous voyez toujours un espace blanc.

** Frontend HA brièvement à l'intérieur du panneau : ** commun avec hass_ingress lorsque l'URL d'entrée n'a pas de barre oblique finale – les chemins d'accès relatifs aux actifs sont résolus en`/api/ingress/assets/...`au lieu de`/api/ingress/<panel>/assets/...`, chargeant brièvement l'interface de HA.

1. Utiliser`work_mode: ingress`et`ui_mode: normal`dans la configuration de votre panneau hass_ingress.
2. Dans DevTools → Réseau, confirmez le chargement des bundles JS depuis`/api/ingress/<panel>/assets/...`, pas`/api/ingress/assets/...`.
3. Les versions actuelles injectent un`<base href>`et une redirection par barre oblique finale dans le HTML du tableau de bord pour éviter cela ; mettez à niveau si vous voyez toujours le flash sur une image plus ancienne.
