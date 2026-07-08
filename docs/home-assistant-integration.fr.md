# Intégration Home Assistant personnalisée

Nécessite **Home Assistant Core 2026.3.0+**.

L'intégration HACS Solar AI Optimizer remplace le [paquet YAML fail-safe](home-assistant-failsafe.md) par un code d'appairage, un chien de garde dans HA, et une entité Update. Voir la [version anglaise](home-assistant-integration.md) pour le détail des étapes ; le flux est identique (HACS → appairage → options fail-safe).

IndiAuth (Solar → HA) reste optionnel dans les réglages Solar et n'est pas requis pour le fail-safe.

Avant d'activer le watchdog de l'intégration, désactivez `packages/solar-optimizer-failsafe.yaml`.
