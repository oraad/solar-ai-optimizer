# MCP (protocole de contexte de modèle)

Solar AI Optimizer expose une option[PCM](https://modelcontextprotocol.io/)serveur afin que les agents d'IA (curseur, automatisations du SDK) puissent lire l'état de l'optimiseur, dépanner les décisions et appliquer les mêmes remplacements sécurisés que le tableau de bord.

MCP est un **plan de contrôle side-car** : il ne remplace pas la boucle de contrôle en temps réel. Toutes les écritures passent par l'existant`Executor`, le mode ombre et`Override`modèle de sécurité.

## Quand utiliser MCP par rapport au tableau de bord

| Utilisez MCP lorsque | Utilisez le tableau de bord lorsque |
|--------------|------------------------|
| Débogage de la logique du moteur avec un agent IA | Contrôle quotidien de l'opérateur |
| Corréler les décisions avec l'historique du curseur | Graphiques visuels et paramètres de l'interface utilisateur |
| Remplacements de script avec authentification du porteur | Rôles d'observateur/administrateur d'entrée HA |

## Liste de contrôle de sécurité

- **Jeton du porteur = administrateur complet.**`API_TOKEN`et`MCP_TOKEN`accordez le même accès de mutation qu’un administrateur local.
- Ensemble`MCP_TOKEN`séparément de`API_TOKEN`afin que vous puissiez révoquer l'accès de l'agent sans interrompre les scripts CI. Les deux jetons sont acceptés pour l'authentification REST et WebSocket ; stdio`ApiBackend`appelle l'API REST avec le jeton configuré.
- Paramètre`MCP_TOKEN`seul (sans`API_TOKEN`) active la porte d'authentification et protège les points de terminaison REST.
- Sur les déploiements autonomes, **jamais** défini`MCP_ENABLED=true`sans`MCP_TOKEN`ou`API_TOKEN`.
- Sur le module complémentaire HA,`mcp_enabled`par défaut`false`. Activer uniquement sur les réseaux de confiance.
- HTTP MCP (`/mcp`) accepte **Bearer uniquement** — pas de cookies d'entrée.
- Le kill switch nécessite`confirm_kill_switch=true`(MCP) ou`confirm=true`(REPOS).
- Traitez les sorties de l'outil comme non fiables (les noms d'entités peuvent contenir du texte d'injection rapide).

## Configuration du curseur (stdio)

1. Démarrez l'optimiseur :`docker compose up -d solar`
2. Définissez un jeton :`export SOLAR_MCP_TOKEN=your-secret`(doit correspondre`API_TOKEN`ou`MCP_TOKEN`sur le conteneur)
3. Copiez [`.cursor/mcp.json.example`](../.cursor/mcp.json.example) à la configuration MCP de votre utilisateur ou de votre projet et ajustez les chemins.
4. Redémarrez le curseur → Paramètres → MCP → vérifier`solar-ai-optimizer`est connecté.

Le serveur stdio utilise le`mcp`compose le profil et parle à l'API en cours d'exécution à`http://host.docker.internal:8000`.

## HTTP distant (diffusion)

```yaml
environment:
  MCP_ENABLED: "true"
  MCP_TOKEN: "change-me"
  # MCP_HTTP_PATH: /mcp   # optional, default /mcp
```

Le montage est refusé en mode autonome si aucun jeton n'est configuré. Terminez TLS au niveau de votre proxy inverse ou de votre entrée HA.

## Catalogue d'outils

### Niveau 1 – commencez ici

| Outil | Objectif |
|------|---------|
| `solar_get_status`| Télémétrie en direct, décision, mode ombre |
| `solar_explain_decision`| Trace médico-légale complète (entrées → raisonnement → exécution) |
| `solar_simulate_decision`| Décision d'essai sans écriture |
| `solar_get_engine_config`| Configuration efficace rédigée |
| `solar_apply_override`| Appliquer`Override`champs |
| `solar_clear_override`| Effacer les remplacements |

### Niveau 2 — analyse approfondie

`solar_get_forecast`, `solar_get_plan`, `solar_get_grid_stats`, outils d'histoire,`solar_get_shed_snapshots`.

### Niveau 3 – mutation

`solar_trigger_cycle`, `solar_refresh_forecast`, `solar_update_config`, `solar_ask`.

## Manuel de dépannage

1. **`solar_explain_decision`** — trouver la couche : prévision dégradée ? remplacement actif ? Une solution de repli MPC ? vous avez sauté l'écriture ?
2. **`solar_get_engine_config`** — vérifier les tampons de réserve,`priority_order`, le sous-système est activé.
3. **`solar_get_decision_history`** + **`solar_get_telemetry_window`** — bug piloté par les entrées ou logique.
4. **`solar_simulate_decision`** — teste une hypothèse de configuration sans écritures en direct.
5. Si les clés de justification indiquent un bug de règle, corrigez le code dans`backend/app/engine/`.

### Exemples travaillés

**Réserve trop élevée :** Dans la trace, comparez`decision.reserve.solar_bridge_soc`contre`autonomy_floor_soc`. Vérifier`inputs.forecast.degraded_reasons`et`engine.priority_weights`.

**Écritures ignorées :** Vérifiez`execution.results[].skipped_reason`pour`shadow_mode`, HA obsolète ou capacité non mappée.

**MPC de secours :** Vérifiez`ops.metrics.mpc_fallbacks`et`engine.mpc_unavailable`.

## Points de terminaison de débogage REST

Administrateur uniquement (mêmes données que les outils d'investigation MCP) :

- `GET /api/debug/trace?sections=decision,execution,engine`
- `POST /api/debug/simulate`(à taux limité)

## Variables d'environnement

| Variables | Par défaut | Objectif |
|----------|---------|---------|
| `MCP_ENABLED` | `false`| Montez le HTTP Streamable sur`/mcp` |
| `MCP_HTTP_PATH` | `/mcp`| Chemin HTTP |
| `MCP_TOKEN` | `""`| Jeton du porteur d'agent ; retombe sur`API_TOKEN` |
| `SOLAR_API_URL` | `http://127.0.0.1:8000`| URL de base de l'API client stdio |

Voir aussi[Configuration](configuration.md).
