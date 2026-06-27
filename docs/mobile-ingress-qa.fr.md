# Contrôle qualité des entrées mobiles (Home Assistant Companion)

Utilisez cette liste de contrôle lors de la validation du tableau de bord dans l’iframe d’entrée de l’application HA Companion (module complémentaire natif ou hass_ingress).

## Installation

1. Ouvrez **Solar AI** à partir de la barre latérale HA sur un téléphone (application iOS et/ou Android Companion).
2. Testez les comptes **admin** et **viewer** si possible.

## Mise en page et défilement

- [ ] Pas de double barre de défilement verticale (HA Chrome + le contenu de l'application défilent ensemble naturellement).
- [ ] La barre supérieure reste collante ; le contenu ne se trouve pas sous l’encoche de l’appareil.
- [ ] Le contenu inférieur et les toasts effacent l'indicateur d'accueil / la barre inférieure HA.

## Navigation

- [ ] Les onglets principaux défilent horizontalement si nécessaire ; les étiquettes restent visibles (pas uniquement les icônes).
- Les boutons d'onglet [ ] sont faciles à appuyer (environ 44 px de haut).
- [ ] Les sous-onglets de l'historique (Graphique, Décisions, Événements de la grille, …) défilent horizontalement sur des écrans étroits.

## Barre d'état (largeur ≤ 600 px)

- [ ] Pilules principales visibles : HA, LIVE/SHADOW, PAUSED (si actif), VIEWER (le cas échéant).
- [ ] Les alertes secondaires se transforment en un menu **N alertes** ; Le menu s'ouvre et répertorie les éléments.
- [ ] La bascule de thème reste accessible.

## Panneaux de contenu

- [ ] Les cartes de présentation s'empilent dans une seule colonne.
- [ ] Le graphique historique s'affiche à une hauteur réduite ; légende lisible.
- [ ] Les tableaux d'historique défilent horizontalement sans casser la mise en page.
- [ ] Conseils d'information (ⓘ) s'ouvrent en appuyant sur et rejettent en appuyant sur un robinet extérieur ou en s'échappant.
- [ ] Les contrôles segmentés de remplacement peuvent être tapés.
- [ ] La saisie du chat de l'assistant reste au-dessus du clavier/de la zone de sécurité.

## Régression (ordinateur de bureau)

- [ ] Autonome`http://localhost:8000`et l'entrée du bureau dans la barre latérale HA semble toujours correcte à 1280 × 900.

## Captures d'écran automatisées

Avec la pile de démonstration en cours d'exécution :

```bash
docker compose --profile docs run --rm docs-screenshots
```

Ou localement depuis`frontend/`après une fois`npm ci`et`npx playwright install chromium`:

```bash
npm run docs:screenshots
```

Les captures mobiles (largeur 390 px, hauteur du contenu) sont écrites dans`docs/images/frontend/mobile-*.png`.

![Mobile Overview (390px wide)](../images/frontend/mobile-overview.png)
