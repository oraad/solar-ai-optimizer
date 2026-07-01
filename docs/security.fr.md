# Sécurité

Cette page résume la politique de sécurité du projet. La version canonique est également à
[`SECURITY.md`](https://github.com/oraad/solar-ai-optimizer/blob/main/SECURITY.md) dans le référentiel.

## Versions prises en charge

| Version | Pris en charge |
| ------- | --------- |
| 0.5.x | Oui |

## Signaler une vulnérabilité

Veuillez signaler les problèmes de sécurité **en privé** :

1. Ouvrez un[Avis de sécurité GitHub](https://github.com/oraad/solar-ai-optimizer/security/advisories/new), ou
2. Envoyez un e-mail à **omarraad@gmail.com** avec une description et les étapes de reproduction.

N’ouvrez pas de problèmes publics pour des vulnérabilités non divulguées.

## Conseils de déploiement

- Lors de l'exposition de l'API en dehors de l'entrée Home Assistant, définissez`LOCAL_ADMIN_PASSWORD_HASH` + `SESSION_SECRET`ou`API_TOKEN`et utilisez HTTPS.
- Ensemble`TRUST_INGRESS_HEADERS=true`uniquement lorsque l'application est accessible **exclusivement** via l'entrée HA (pas directement sur le port 8000). Cela définit également`X-Frame-Options: SAMEORIGIN`pour l'iframe de la barre latérale.
- Gardez les jetons de longue durée de Home Assistant définis et tournés. Voir[Configuration de Home Assistant → Jeton d'accès longue durée](home-assistant-setup.md#long-lived-access-token).
- Exécutez en **mode ombre** jusqu'à ce que vous fassiez confiance aux écritures automatisées de l'onduleur.
- L'image Docker par défaut inclut des extras ML/MPC facultatifs ; utiliser`INSTALL_EXTRAS=0`pour une surface d’attaque plus légère si ces fonctionnalités ne sont pas utilisées.
- Ne jamais activer`DEMO_MODE`sur un système connecté à un véritable onduleur.

Détails complets du contrôle d'accès :[Rôles et accès](ingress-auth.md).

## Rôle de spectateur (entrée)

Les utilisateurs non administrateurs de Home Assistant authentifiés via Ingress sont des **visionneurs**. Ils peuvent lire en direct
statut, prévisions et historique, et peut POST des remplacements limités uniquement :

- `shadow_mode`, `pause_engine`, `pause_shedding`, `pause_grid_charge`, `pause_optimization`, `kill_switch` (avec `confirm=true`)

Chaque champ `pause_*` est bidirectionnel : `true` met en pause, `false` reprend.

Les téléspectateurs se voient refuser les lectures de configuration (`GET /api/config`), énumération des entités (`GET /api/entities`),
écritures de configuration, l'Assistant, le code PIN de réserve, les frais de réseau forcés et d'autres itinéraires réservés aux administrateurs.
L'application se fait en back-end ; le tableau de bord cache les contrôles de défense en profondeur.

Ne pas exposer le port`8000`directement si les téléspectateurs ne doivent pas contourner les en-têtes d’identité d’entrée HA.

Présentation pas à pas du tableau de bord :[Tableau de bord du visualiseur](frontend-manual.md#viewer-dashboard).
