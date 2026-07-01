# Solar AI Optimizer — Guide de l'utilisateur du tableau de bord

Ce guide présente le tableau de bord Web Lit servi avec le backend à l'adresse **http://localhost:8000** (ou via le panneau d'entrée du module complémentaire Home Assistant). Les captures d'écran utilisent le thème **sombre** par défaut à 1280×900, sauf indication contraire.

## Commencer

Ouvrez le tableau de bord après[installation](installation.md):

```bash
docker compose up -d --build
```

La barre supérieure affiche l'état de la connexion en direct et le mode de fonctionnement :

- **HA connecté / HA hors ligne** — Lien WebSocket Home Assistant
- **SHADOW / LIVE** — le mode shadow enregistre les actions sans écrire sur l'onduleur
- **RULES / MPC** — moteur de décision actif (MPC revient aux règles si PuLP n'est pas disponible)
- Les pilules d'état telles que **SET LOCATION**, **FORECAST DEGRADED**, **STALE DATA** ou **SOLCAST MISCONFIGURED** mettent en évidence les problèmes de configuration ou de données (administrateur uniquement).

Utilisez le **bascule de thème** (icône soleil/lune) pour basculer entre clair et foncé ; les tableaux sont repeints pour correspondre.

### Ouverture depuis l'entrée Home Assistant

Lorsque vous ouvrez Solar AI à partir de la barre latérale HA (module complémentaire ou hass_ingress), un **boot splash** apparaît immédiatement pendant que l'application vérifie votre session (`GET /api/me`). Cela évite une iframe vide pendant le chargement de JavaScript et pendant l'exécution de la résolution du rôle d'entrée. Le splash disparaît une fois que vous êtes connecté ou que la page de connexion s'affiche.

Sur les téléphones utilisant l'application **Home Assistant Companion**, le tableau de bord respecte les zones de sécurité (encoche, indicateur d'accueil) et utilise des cibles d'appui plus grandes. Voir le[Contrôle qualité des entrées mobiles](mobile-ingress-qa.md)liste de contrôle lors de la validation de la mise en page sur iOS ou Android.

---

## Rôles du tableau de bord {#dashboard-roles}

Il existe **un tableau de bord** pour tous les utilisateurs. Les rôles contrôlent les onglets et les contrôles qui apparaissent, et non les applications ou les URL distinctes.

| Rôle | Accès typique | Onglets |
|------|----------------|------|
| **Administrateur** | Propriétaire de HA,`system-admin`groupe, connexion locale ou`API_TOKEN`| Présentation, Prévisions, Historique, **Assistant**, **Délestage**, **Paramètres** |
| **Visionneuse** | Autres utilisateurs HA via[entrée](ingress-auth.md)| Aperçu, prévisions, historique uniquement |

Résolution des rôles et application de l'API :[Rôles et accès](ingress-auth.md).

### Matrice de fonctionnalités

| Fonctionnalité | Administrateur | Visionneuse |
|---------|:-----:|:------:|
| Aperçu du statut et de la décision en direct | Oui | Oui |
| Prévisions et historique | Oui | Oui |
| Bascule ombre/live | Oui | Oui (API uniquement ; pas affiché dans l'UI spectateur) |
| Pause all / Resume all (moteur) | Oui | Oui |
| Pause / reprise par sous-système (délestage, charge réseau, optimisation) | Oui | Oui |
| Kill switch (avec confirmation) | Oui | Oui |
| Broche de réserve, charge de réseau, suppression des remplacements | Oui | Non |
| Exécuter le cycle de contrôle, actualiser les prévisions | Oui | Non |
| Assistant (LLM) | Oui | Non |
| Paramètres/config/entités | Oui | Non |
| Bannières d'état de configuration (SET LOCATION, etc.) | Oui | Caché |
| Temps de décharge de la batterie lors de la présentation | Oui | Oui |

---

## Tableau de bord d'administration

Les administrateurs voient les six onglets et le panneau **Remplacements** complet dans la vue d'ensemble.

![Overview tab with status strip and navigation](../images/frontend/overview.png)

### Aperçu (administrateur)

L'onglet Présentation est la salle de contrôle :

| Zone | Objectif |
|------|---------|
| **Aperçu du héros** | Grande barre SOC de batterie avec marqueur de réserve et pilule de risque de panne de courant |
| **Cartes de statut** | PV en direct, charge, réseau et télémétrie associée |
| **Statistiques de la grille** | Statistiques récentes de disponibilité du réseau |
| **Décision et justification** | Réserve cible actuelle, score de risque, actions planifiées et détails du hangar (développer **Détails**) |
| **Remplacements** | Shadow/live, pause, kill switch, broche de réserve, charge du réseau, cycle d'exécution — regroupés par section |

Lisez d'abord le panneau **Décision** : il explique *pourquoi* l'optimiseur a choisi sa réserve et ses actions actuelles. Utilisez les liens **Afficher l'historique du délestage** ou **Configurer le délestage** lorsque les actions de délestage sont actives.

### Panneau de remplacement (administrateur) {#overrides-panel-admin}

Les administrateurs obtiennent le panneau de commande complet :

- **Shadow / Live** — démarrez dans l'ombre ; ne passez à la vie qu'après avoir fait confiance aux décisions
- **Tout mettre en pause** / **Tout reprendre** — arrêter ou redémarrer tous les sous-systèmes (délestage, charge réseau, optimisation)
- **Pause / reprise par sous-système** — bascules délestage, charge réseau et optimisation (affichées pour tous les rôles)
- **Avancé** (admin uniquement) — shadow/live et effacer les remplacements
- **Interrupteur d'arrêt** — arrêt d'urgence ; charge du réseau au maximum (lorsque activé) et restauration du niveau de délestage (nécessite une confirmation)
- **Réserve de remplacement** — force temporairement un SOC cible minimum (%)
- **Forcer les frais de réseau** — remplacement opportuniste de la recharge du réseau (masqué lorsque les frais de réseau sont désactivés)
- **Cycle d'exécution** / **Actualiser les prévisions** – déclencheurs manuels
- **Effacer les remplacements** — réinitialiser les remplacements de l'opérateur après le kill switch

![Overrides panel](../images/frontend/overrides.png)

### Prévisions, Historique, Assistant, Délestage, Paramètres (admin)

Les administrateurs utilisent **Prévisions** et **Historique** de la même manière que les spectateurs (voir ci-dessous), plus :

- **Assistant** — Discussion LLM sur les décisions récentes ; commande facultative appliquer
- **Délestage de charge** : niveaux, seuils SOC, découverte d'entités associées, options de restauration et préréglage de **déploiement en mode hangar uniquement** (désactive la charge et l'optimisation du réseau ; réserve consultative facultative)
- **Paramètres** — La connexion HA, les entités, la batterie, les prévisions, le **moteur** / **la charge du réseau** activent les bascules, etc.

![Assistant chat panel](../images/frontend/assistant.png)

![Settings panel (sidebar navigation — Engine section)](../images/frontend/settings.png)

---

## Tableau de bord du visualiseur {#viewer-dashboard}

Lorsque vous vous connectez via l'entrée Home Assistant en tant qu'utilisateur non-administrateur, le tableau de bord s'exécute en mode **visualiseur** :

![Viewer Overview — three tabs and VIEWER badge](../images/frontend/viewer-overview.png)

- **Onglets :** Aperçu, prévisions et historique uniquement – pas d'assistant, de délestage ou de paramètres
- **Barre supérieure :** Badge **VIEWER** ; votre nom d'affichage HA peut apparaître sous le titre de l'application
- **Aperçu des remplacements :** **Tout mettre en pause**, **Tout reprendre**, bascules pause/reprise par sous-système et kill switch (avec confirmation) — pas de broche de réserve, forçage charge réseau, cycle d'exécution, bascule shadow/live ni effacer les remplacements
- **Bannières en lecture seule** dans la vue d'ensemble lorsqu'un administrateur a épinglé un SOC de réserve ou forcé des frais de réseau : les spectateurs voient le remplacement actif mais ne peuvent pas le modifier.
- **Prévision de l'état vide** — si l'emplacement n'est pas configuré, le graphique affiche un message demandant à un administrateur de définir la latitude/longitude dans les paramètres (les spectateurs ne peuvent pas ouvrir les paramètres).
- **Délai de décharge de la batterie** dans la vue d'ensemble utilise les données d'état en temps réel – aucun accès aux paramètres n'est requis

Les téléspectateurs ne peuvent pas épingler le SOC de réserve, forcer la facturation du réseau, exécuter un cycle de contrôle, actualiser les prévisions, effacer les remplacements, utiliser l'Assistant ou modifier la configuration.

Voir[Rôles et accès](ingress-auth.md)pour savoir comment les rôles d'administrateur et de spectateur sont déterminés.

---

## Aperçu

Partagé par l'administrateur et le spectateur (les contrôles diffèrent – voir[Panneau de remplacement (administrateur)](#overrides-panel-admin)et[Tableau de bord du visualiseur](#viewer-dashboard)).

![Overview layout with decision and overrides](../images/frontend/overview.png)

---

## Prévision

L'onglet **Prévisions** affiche un graphique de prévision de l'énergie solaire et de la charge sur 48 heures, des **Insights** (énergie solaire excédentaire, fenêtre de charge de pointe, piste de réserve) et les totaux d'énergie quotidiens.

- Les séries **Solar / Load** utilisent l'axe de puissance gauche (watts).
- **Température** (si configurée) utilise un axe °C séparé à droite
- Les pilules avertissent d'un **demain nuageux** ou d'une **prévision dégradée** (survolez pour les raisons)
- Les administrateurs peuvent **Actualiser** les prévisions manuellement à partir de cet onglet

Administrateurs : définissez la latitude, la longitude, les générateurs photovoltaïques et le fournisseur de prévisions du site sous **Paramètres** si le graphique est vide. Visionneuses : contactez un administrateur si le graphique affiche un message de configuration.

![Forecast chart and grid statistics](../images/frontend/forecast.png)

---

## Histoire

L'historique combine des graphiques de télémétrie et des tableaux d'audit. Choisissez une **fenêtre horaire** (6h-7j) et un sous-onglet :

| Sous-onglet | Contenu |
|---------|----------|
| **Chronologie** | SOC (%), puissance (W), températures optionnelles et ombrage en cas de panne de réseau |
| **Décisions** | Les décisions passées comportant des risques et des actions perdues comptent |
| **Activité** | Écritures récentes de l'onduleur, écritures de délestage et événements du réseau (segment de commutation à l'intérieur de l'onglet) |

![History telemetry chart](../images/frontend/history-chart.png)

![History decisions table](../images/frontend/history-decisions.png)

---

## Assistant

**Administrateur uniquement.** L'Assistant répond aux questions sur les décisions récentes et peut appliquer des **commandes analysées** lorsque vous activez **Autoriser l'Assistant à appliquer des commandes de contrôle**.

Exemples :

- "Pourquoi avez-vous facturé le réseau ?"
- "Régler la réserve à 60%" (avec Appliquer coché)
- « Engage kill switch confirm » (dangereux — nécessite un texte de confirmation explicite)

Les tentatives de kill-switch bloquées affichent une bannière rouge expliquant l'exigence de confirmation.

---

## Paramètres {#settings}

**Administrateur uniquement.** Toute la configuration d'exécution est modifiée ici et conservée dans le`solar-data`volume. Utilisez **Enregistrer les modifications** après les modifications.

Principales rubriques :

| Rubrique | Que configurer |
|---------|-------------------|
| **Connexion Home Assistant** | URL, jeton, vérification SSL |
| **Site** | **Fuseau horaire** — liste IANA consultable ou **Auto** (Open-Meteo à l'emplacement du site). **Latitude/longitude** pour les API solaires et météorologiques. S’applique aux totaux quotidiens prévus, aux horodatages de l’historique/des graphiques et au regroupement de charge/température du back-end. |
| **Sécurité** | Entité Heartbeat, arrêt de la charge du réseau au maximum |
| **Sécurité des API** | Jeton API stocké dans le navigateur lorsque`API_TOKEN`est défini sur le serveur |
| **Préférences d'affichage** | **Langue** (English, العربية, Français) et **format de date** pour ce navigateur : paramètres régionaux par défaut, JJ/MM/AA ou AAAA-MM-JJ (ISO). L'arabe définit la disposition de droite à gauche. S'applique aux tables d'historique, aux axes/curseurs des graphiques et aux dates de sortie. Les justifications de décision, les erreurs d'API, les messages de mise à jour du système et les solutions heuristiques de secours de l'assistant suivent la langue sélectionnée lors de l'envoi du tableau de bord.`X-Solar-Locale`au back-end. Changer de langue reconnecte le WebSocket en direct et récupère l'historique. Les invites du système Ollama et les réponses heuristiques sont sauvegardées dans un catalogue par langue ; la sortie du modèle peut encore varier. Les lignes de l'historique stockées avant la migration i18n peuvent afficher le texte ignoré en anglais jusqu'à ce qu'elles soient récupérées à nouveau ; l'API normalise les chaînes héritées connues lorsque cela est possible. |
| **Batterie / Réserve / Prévisions / Contrôle** | Paramètres physiques et algorithmiques |
| **Générateurs photovoltaïques** | Inclinaison, azimut et kWc par réseau |
| **Moteur** | Mode règles vs MPC ; Ordre **priorité optimisation** (résilience, économies, autosuffisance) |
| **Température** | Modèle de charge de chauffage/refroidissement et capteur extérieur |
| **Carte des entités de l'onduleur** | Entités HA pour les capteurs de lecture et les contrôles d'écriture |
| **Frais de réseau** | Ordre de rampe et de facteur pour la recharge du réseau |

Configurez le **délestage** dans l'onglet dédié **Délestage** (et non dans Paramètres).

### Ajout d'une langue de tableau de bord (contributeurs) {#adding-a-dashboard-language-contributors}

1. Copier`frontend/src/locales/en.json`à`frontend/src/locales/<id>.json`et traduisez toutes les valeurs de chaîne.
2. Ajoutez un`LocaleMeta`entrée dans`frontend/src/locales/manifest.ts` (`id`, `nativeName`, `dir`, `match`préfixes).
3. Ajoutez un chargeur dans`LOCALE_LOADERS`dans le même fichier.
4. Courez`docker compose run --rm frontend-test`— le test de parité locale échoue si les clés sont manquantes.

Les champs d'entité prennent en charge la saisie semi-automatique lorsque Home Assistant est connecté. Voir[Configuration de l'assistant à domicile](home-assistant-setup.md).

### Priorités moteur et optimisation

Sous **Engine**, choisissez **Rules** ou **MPC**, puis réorganisez les **priorités d'optimisation**.
(le plus élevé en premier) :

1. **Résilience** — des réserves tampons plus importantes et une réponse plus forte au risque de panne d'électricité
2. **Économies** — tarification du réseau plus opportuniste lorsque le réseau est présent (pas d'optimisation tarifaire/TOU)
3. **Autosuffisance** – garniture solaire plus solide dans la rampe de charge du réseau ; préfère le photovoltaïque à la recharge du réseau

Le résumé sous la liste reflète la commande active. L'ordre par défaut correspond à celui
position du produit : résilience → épargne → autosuffisance. Charge de réseau **ordre de facteur**
(dans la section Tarifs du réseau) s'applique toujours ; les priorités déterminent l'importance de chaque facteur
le seau influence la chaîne du capuchon.

### Niveaux de délestage {#load-shedding-tiers}

Ouvrez l'onglet **Délestage de charge** pour configurer les niveaux. Chaque niveau peut contrôler ** plusieurs puissances
interrupteurs** (par exemple pompe de piscine + chauffage, ou un interrupteur d'alimentation secteur). Toutes les entités dans un hangar de niveau
et restaurer ensemble en utilisant la même hystérésis SOC. Le numéro **priorité** inférieur est perdu en premier.
Les blocs de niveau sont **réduits par défaut** ; la ligne récapitulative affiche le nom du niveau, le SOC perdu,
priorité et nombre d'appareils : cliquez pour développer l'éditeur complet.

Lorsque vous choisissez une entité d'alimentation, les compagnons sur le même appareil HA (climatisation, sélection, ventilateur, etc.)
sont **découverts automatiquement** et répertoriés sous cette entité (les sections complémentaires sont également
début effondré). Supprimez les compagnons indésirables ou
utilisez **Tout effacer** pour la suppression des commutateurs uniquement. Les appareils qui étaient éteints avant la perte restent allumés
restaurer.

Basculements par niveau :

- **Restauration automatique sur SOC** : restauration lorsque le SOC dépasse le seuil du niveau
- **Restaurer lorsque la grille est présente** — restaurer lorsque la grille est détectée (si l'indicateur global est activé)

![Load shedding tab](../images/frontend/load-shedding.png)

![Load-shedding tier editor with multiple entities](../images/frontend/settings-load-shedding.png)

Les sections **Avancé** en bas prennent en charge l'édition JSON brute, l'importation/exportation de modèles et le recyclage ML.

### Mises à jour logicielles

Sous **Mises à jour logicielles** (admin), le tableau de bord répertorie les versions récentes de GitHub avec
Notes de version **au format Markdown**. Sur les hôtes de mise à jour automatique Docker, utilisez **Install** sur n'importe quel
version stable. Les rétrogradations affichent un avertissement supplémentaire ; un`/app/data`la sauvegarde est créée avant
chaque installation. Si le service ne revient pas après une installation, utilisez **Restore** depuis le
section sauvegardes. Utilisez **Vérifier les mises à jour** pour actualiser la liste des versions. La barre supérieure
Le badge **MISE À JOUR** apparaît lorsqu'une version plus récente est disponible.

Les installations du module complémentaire Home Assistant sont mises à jour via Supervisor (la liste des versions est informative).

!!! note "Version illustrée"
L'installation en un clic nécessite **v0.5.5+** (Docker CLI dans l'image). Les versions 0.5.2 à 0.5.4 nécessitent un
manuel`docker pull`et recréer une fois - voir[Installation](installation.md).

### Notifications de pain grillé

Les actions d'enregistrement, de connexion, de remplacement et de mise à jour affichent de brefs messages toast au bas de
l'écran (chargement du spinner, puis succès ou erreur). Les erreurs restent visibles quelques secondes
plus long que les messages de réussite.

---

## Dépannage

| Symptôme | Que vérifier |
|---------|----------------|
| **HA hors ligne** | Paramètres → URL/jeton de Home Assistant ; réseau du conteneur à HA |
| ** DÉFINIR L'EMPLACEMENT ** | Prévoir la latitude/longitude dans Paramètres |
| **SOLCAST MAL CONFIGURÉ** |`SOLCAST_API_KEY`et`SOLCAST_RESOURCE_ID`dans l'environnement / options complémentaires |
| **DONNÉES périmées** | Entités HA dans la carte de l'onduleur ;`ha_stale_after_seconds`en contrôle |
| **Bannière d'erreurs API** | Jeton API dans Paramètres → Sécurité API ; CORS si vous utilisez une origine distincte |
| Cartes vides | Attendez l'historique de télémétrie ; élargir la fenêtre Historique |
| **VIEWER** mais nécessite des paramètres | Demandez à un administrateur HA ou utilisez la connexion de l'administrateur local pour un accès direct |
| Iframe vide lors de l'ouverture de l'entrée | Mettez à niveau vers **v0.5.7+** pour le démarrage ; voir[dépannage d'entrée](ingress-auth.md#blank-iframe-or-ha-ui-flashes-inside-the-panel-on-first-load) |
| Double barre de défilement dans l'application HA | Fixed in **v0.5.7+** (`background-attachment`et`100vh`ajustements de mise en page); voir[Contrôle qualité des entrées mobiles](mobile-ingress-qa.md) |

---

## Régénération des captures d'écran {#regenerating-screenshots}

!!! danger "DEMO_MODE est réservé aux documents"
Ne jamais courir`DEMO_MODE`sur un système connecté à un véritable onduleur.

Après les modifications de l'interface utilisateur, actualisez les images de ce manuel :

```bash
docker compose -f docker-compose.yml -f docker-compose.demo.yml up -d --build
docker compose exec solar python -m scripts.seed_demo
docker compose restart solar
```

Capturez ensuite des captures d'écran (Docker — fonctionne sans Node/npm local) :

```bash
# One-time, or after frontend/package-lock.json changes:
docker compose --profile docs run --rm docs-screenshots npm ci

# Every regen (demo stack must be running on port 8000):
docker compose --profile docs run --rm docs-screenshots
```

Depuis`frontend/`tu peux aussi courir`npm run docs:screenshots:docker`.

Ou avec un nœud local installé (une fois`npm ci` + `npx playwright install chromium`) :

```bash
cd frontend
npm ci
npx playwright install chromium
npm run docs:screenshots
```

<details><summary>Remplacement hérité (lent : réinstalle les navigateurs à chaque exécution)</summary>

```bash
docker run --rm --add-host=host.docker.internal:host-gateway \
  -v "$(pwd)/frontend:/ui" -v "$(pwd)/docs:/docs" \
  -e SCREENSHOT_BASE_URL=http://host.docker.internal:8000 \
  -w /ui node:26-trixie \
  bash -lc "npm ci && npx playwright install --with-deps chromium && npm run docs:screenshots"
```

Sous Windows PowerShell, utilisez`c:/Projects/solar/frontend`chemins de style au lieu de`$(pwd)`.

</détails>

Validez les fichiers mis à jour sous`docs/images/frontend/`ainsi que toute modification manuelle du texte. Les captures incluent les ordinateurs de bureau (1 280 × 900) et les appareils mobiles (`mobile-*.png`, 390×844) — notamment`load-shedding.png`, `settings-load-shedding.png`, et`mobile-load-shedding.png`. Le script de capture attend le chargement des données en direct, des graphiques et de la configuration avant chaque prise de vue (pas de délai de mise en veille fixe).
