# Limites connues

## Données
- Le jeu de démonstration est **synthétique** (émetteurs fictifs). Les résultats illustrent la méthode, pas un marché réel.
- **Connecteur BCE** : il est écrit et testé sur une réponse simulée au format SDMX-CSV documenté, mais **l'appel réel n'a pas pu être validé** dans l'environnement de développement (sortie réseau bloquée, erreur 403 du proxy, que l'application affiche telle quelle). Validez-le en local avec *Data Sources → Test connection*.
- Il n'existe pas de source d'actions réelles intégrée : aucune API gratuite n'autorise la redistribution. Les historiques réels s'importent en CSV, avec une provenance déclarée.
- Rien n'est affiché en temps réel. Toutes les séries sont des valeurs de fin de journée.

## Modèles
- **Horizon** : la VaR et l'ES à h jours sont obtenues par mise à l'échelle √h des chiffres à 1 jour, ce qui suppose des P&L i.i.d. de moyenne nulle.
- Simulation historique à poids égaux : il n'y a ni filtrage de volatilité (FHS) ni pondération temporelle.
- Les positions sont supposées constantes. Le backtest porte donc sur un P&L hypothétique, pas sur un P&L réel.
- **Modèle paramétrique** : delta-normal, moyenne nulle, sans convexité ni effets croisés.
- Il n'existe pas de décomposition exacte de l'ES historique par facteur en revalorisation complète. L'application montre à la place l'ES stand-alone par classe et la décomposition d'Euler delta-normale.
- **Obligations** :
  - taux fixe in fine uniquement ;
  - périodes régulières, dates non ajustées ;
  - pas de défaut ni de recouvrement ;
  - le risque de spread est capté par deux buckets de notation (IG, HY) par devise, et non émetteur par émetteur ;
  - le G-spread est une approximation, ni Z-spread ni OAS.
- La courbe de la BCE est une courbe zéro-coupon AAA. L'utiliser comme benchmark de rendement actuariel est une approximation.
- **Stress tests** : instantanés, sans portage, roll-down ni rebalancement. Les scénarios hypothétiques intégrés sont stylisés et ne reconstituent aucune crise historique.
- Devise de base fixée à l'EUR.

## Produit
- Application mono-utilisateur, sans authentification. À déployer derrière un contrôle d'accès ; l'isolation multi-utilisateurs est décrite dans `DATA_MODEL.md`.
- Les commentaires du Decision Brief sont produits par des règles déterministes. **Aucun modèle de langage n'est intégré** : une interprétation générée par IA pourrait être ajoutée plus tard, en ne recevant que le JSON des résultats.
- La pile PostgreSQL (docker-compose) n'a pas été exécutée dans l'environnement de développement : les tests tournent sur SQLite. Le schéma est portable (SQLAlchemy, Alembic), mais il faut faire un premier démarrage de contrôle.
- L'interface est en anglais. La documentation est en français.
