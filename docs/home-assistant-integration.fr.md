# Intégration Home Assistant personnalisée

Nécessite **Home Assistant Core 2026.7.0+**.

L'intégration HACS Solar AI Optimizer remplace le [paquet YAML fail-safe](home-assistant-failsafe.md) par un code d'appairage, un chien de garde dans HA, une entité Update, des diagnostics et des flux reconfigure/reauth. Elle suit la check-list IQS pour une intégration HACS (pas un badge Core platinum officiel). Voir la [version anglaise](home-assistant-integration.md) pour les tableaux, limitations et exemples.

**Deux chemins d'installation, deux numéros de version :** application Solar (`VERSION` / tags `v*`) vs intégration HACS (`INTEGRATION_VERSION` / tags `integration-v*`). L'app via **Paramètres → Applications** ; l'intégration via HACS en **Integration** (pas Add-on). Détails dans la [version anglaise](home-assistant-integration.md).

**Cas d'usage :** fail-safe de charge réseau si le heartbeat s'arrête, mises à jour via l'entité Update, et automatisations sur le binaire Healthy — détails dans la [version anglaise](home-assistant-integration.md) (section Use cases).

**Installation :** dépôt HACS en tant qu'**Integration**. HACS installe depuis `solar_ai_optimizer.zip` sur les releases GitHub (sélecteur de versions ; stable par défaut).

**Dépannage :** si HACS indique un « dépôt add-on » plutôt qu'une intégration, ajoutez le dépôt comme Integration ou installez manuellement depuis une release avec le zip — voir la [version anglaise](home-assistant-integration.md).

IndiAuth (Solar → HA) reste optionnel dans les réglages Solar et n'est pas requis pour le fail-safe.

Avant d'activer le watchdog de l'intégration, désactivez `packages/solar-optimizer-failsafe.yaml`.

**Désinstallation :** supprimer l'intégration dans l'UI ; supprimer aussi `custom_components/solar_ai_optimizer/` en cas d'install manuelle.
