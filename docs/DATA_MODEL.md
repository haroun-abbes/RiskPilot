# Modèle de données

Schéma SQLAlchemy : `backend/riskpilot/db/models.py`. Migration initiale : `backend/alembic/versions/`. Les migrations sont appliquées automatiquement au démarrage de l'API (`alembic upgrade head`). Les séries de marché sont stockées en CSV dans `RISKPILOT_DATA_DIR/datasets/` ; la table `datasets` ne garde que leurs métadonnées et leur empreinte.

| Table | Rôle | Champs clés |
|---|---|---|
| `portfolios` | Instantané de portefeuille | `id`, `name`, `base_currency` (EUR), `as_of` (date de valorisation), `provenance` (`SYNTHETIC`, `USER_IMPORT`), `source_filename`, `content_hash` |
| `positions` | Positions d'un portefeuille | `portfolio_id` (FK, cascade), `seq`, `position_id`, `instrument_type`, `payload` (JSON, schéma propre à chaque type) |
| `datasets` | Jeu de données de marché | `id`, `name`, `provenance` (`SYNTHETIC`, `HISTORICAL_REAL`, `DELAYED`), `source`, `license_note`, `frequency`, `file_path`, `content_hash`, `factor_meta` (JSON) |
| `import_sessions` | Fichier importé en attente de validation | `header`, `rows` (JSON). Supprimé après confirmation |
| `scenarios` | Scénarios de stress | `kind` (`hypothetical`, `historical`), `definition` (JSON validé), `is_builtin` (lecture seule) |
| `watchlists` | Listes de surveillance | `factors` (liste d'identifiants de facteurs) |
| `alert_rules` | Règles d'alerte | `factor`, `rule_type`, `direction`, `threshold` (unités décimales), `lookback`, `active` |
| `alert_events` | Historique des déclenchements | `rule_id`, `dataset_id`, `obs_date`, `value`, `message` |
| `reports` | Decision Briefs | `params`, `results` (JSON complet), `portfolio_hash`, `dataset_hash`, `engine_version`, `created_at` |

## Schéma des positions (`payload`) par instrument

| Type | Champs obligatoires | Champs optionnels |
|---|---|---|
| `EQUITY`, `ETF` | `id`, `ticker`, `quantity` (négative = vente à découvert), `price` (devise locale), `currency` | `name`, `sector`, `issuer`, `country`, `risk_proxy` |
| `BOND_FIXED` | `id`, `nominal`, `clean_price` (% du pair), `coupon_rate` (décimal en base ; **en pourcent dans le fichier importé**), `frequency` (1, 2, 4, 12), `maturity`, `currency` | `daycount` (défaut ACT/ACT ICMA, signalé), `issuer`, `rating`, `sector`, `country`, `is_sovereign` |
| `FX_CASH` | `id`, `currency`, `amount` | `name` |

Types refusés à l'import avec une explication : `BOND_FLOAT` ou `FRN`, `OPTION`, `FUTURE`, `SWAP`, `CDS`.

## Identifiants de facteurs (colonnes d'un jeu de données)

| Motif | Exemple | Niveau stocké | Variation |
|---|---|---|---|
| `EQ:<TICKER>` | `EQ:SXEU` | prix en devise locale | rendement simple |
| `FX:<CCY>` | `FX:USD` | EUR par unité de devise | rendement simple |
| `IR:<CCY>:<ténor>` | `IR:EUR:10Y` | taux décimal | différence absolue |
| `CS:<CCY>:<IG\|HY>` | `CS:EUR:HY` | spread décimal | différence absolue |

## Isolation et sécurité

Cette version est **mono-utilisateur, sans comptes**. Pour un déploiement multi-utilisateurs, il faut ajouter :
- une colonne `owner_id` sur `portfolios`, `scenarios`, `watchlists`, `alert_rules` et `reports` ;
- une authentification (OIDC) dans FastAPI ;
- un filtrage systématique des requêtes par `owner_id`.

Ce travail est listé dans les limites connues.
