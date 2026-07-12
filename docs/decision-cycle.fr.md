# Comment un cycle de contrôle décide

Chaque boucle est **détecter → décider → exécuter → vérifier**.

1. **Entrées** — télémétrie, prévision, stats réseau (digest stocké sur la décision).
2. **Réserve** — les règles calculent le pont solaire vs le plancher d'autonomie ; le MPC ou une consigne opérateur peut remplacer la cible (`source` : `rules` | `mpc` | `operator`). Le risque utilise la cible **effective**.
3. **Charge réseau** — la chaîne de plafonds réactif/rampe fixe l'activation et les ampères ; le facteur liant est le plafond le plus bas.
4. **Délestage** — politique SOC/réseau ; restaurations uniquement pour les entités avec un instantané de délestage.
5. **Exécution** — écritures HA hors mode ombre et hors pause d'écriture (`paused_grid_charge` / `paused_shedding`). La planification continue lorsque l'optimisation est « en pause ».
6. **Vérification** — l'aperçu affiche prévu vs appliqué pour la réserve et la charge réseau ; joindre l'historique par `cycle_id`.

Si l'aperçu ne correspond pas au comportement attendu, utilisez **Live forensics** (admin) ou MCP `solar_explain_decision` avec la section `causality` — voir [mcp.md](mcp.md).
