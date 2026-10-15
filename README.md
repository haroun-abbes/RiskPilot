# RiskPilot

Plateforme d'analyse des risques de marché et de crédit d'un portefeuille multi-actifs : import et validation de positions, expositions, VaR et Expected Shortfall historiques et paramétriques, backtesting, stress tests hypothétiques et historiques, analytique obligataire, attribution du risque, surveillance de marché par règles d'alerte, Decision Brief exportable en PDF et CSV.

RiskPilot est un outil d'analyse et de simulation. Il n'exécute aucun ordre et ne fournit aucune recommandation d'investissement. Les données fournies sont **synthétiques** et explicitement signalées comme telles.

## Architecture

```
riskpilot/
├── backend/                      Python 3.12+, FastAPI
│   ├── riskpilot/quant/          Moteur quantitatif pur (NumPy/SciPy), sans web ni base de données
│   │   ├── daycount.py           Conventions de décompte, échéanciers
│   │   ├── bonds.py              Prix, rendement, duration, convexité
│   │   ├── instruments.py        Schémas de positions par type d'instrument
│   │   ├── engine.py             Valorisation, mapping facteurs, revalorisation, simulation historique
│   │   ├── risk_measures.py      VaR/ES, contributions, volatilité, covariance, backtest
│   │   └── stress.py             Scénarios hypothétiques et rejeux historiques
│   ├── riskpilot/data/           Générateur synthétique, connecteur BCE, import CSV, qualité
│   ├── riskpilot/portfolio/      Import CSV/Excel, mapping, validation, démo
│   ├── riskpilot/services/       Orchestration (aucune formule), persistance
│   ├── riskpilot/reports/        Decision Brief (PDF ReportLab, CSV)
│   ├── riskpilot/api/            Routes REST et schémas Pydantic
│   ├── alembic/                  Migrations
│   └── tests/                    pytest (unitaires et parcours API)
├── frontend/                     Next.js 16, React 19, TypeScript, Tailwind 4, ECharts, Zustand, SWR
│   └── src/app/<page>/           Overview, Portfolio, Risk, Stress, Fixed Income, Market, Attribution, Reports, Data, Settings
├── e2e/smoke.py                  Test de bout en bout dans un vrai navigateur (Playwright)
└── docs/                         Méthodologie, modèle de données, limites, démo de 5 minutes
```

### Choix structurants

1. **Le moteur de calcul est isolé** (`quant/`). L'API et l'interface n'implémentent aucune formule. Le moteur se teste seul, et chaque chiffre affiché remonte à une fonction documentée.
2. **Mapping sur facteurs de risque et revalorisation complète.** Chaque position est reliée à des facteurs : prix, FX, ténors de courbe, spreads IG/HY. La VaR historique revalorise réellement les obligations au rendement choqué. La version linéaire (delta) ne sert qu'au modèle paramétrique et à la décomposition d'Euler.
3. **La provenance est une donnée de premier rang.** Chaque jeu de données porte une provenance (`SYNTHETIC`, `HISTORICAL_REAL`, `DELAYED`), une source et des conditions d'utilisation. Chaque résultat porte les empreintes des entrées, la version du moteur et la date de calcul. Une barre hachurée signale les données synthétiques sur tous les écrans.
4. **Pas de comblement silencieux.** Une donnée manquante exclut la date ou la position, et l'exclusion est signalée. Aucun prix n'est inventé.
5. **Pas de secret côté navigateur.** Le frontend n'appelle que `/api/*` sur son origine ; Next.js relaie côté serveur vers FastAPI.

## Installation et lancement (développement)

Prérequis : Python 3.12 ou plus, Node.js 20 ou plus.

```bash
# 1. Backend
cd backend
python -m venv .venv && source .venv/bin/activate      # Windows : .venv\Scripts\activate
pip install -r requirements-dev.txt
cp .env.example .env                                    # facultatif, valeurs par défaut utilisables
uvicorn riskpilot.main:app --port 8000 --timeout-keep-alive 75
```

Au premier démarrage, l'API applique les migrations, génère le jeu synthétique et crée le portefeuille de démonstration, les scénarios intégrés, deux listes de surveillance et quatre règles d'alerte. Documentation interactive de l'API : http://localhost:8000/docs

```bash
# 2. Frontend (second terminal)
cd frontend
npm install
cp .env.example .env.local                               # RISKPILOT_API_URL=http://127.0.0.1:8000
npm run dev                                              # http://localhost:3000
```

## Tests

```bash
cd backend && python -m pytest -q          # 67 tests : moteur, import, API, alertes, rapports
cd frontend && npx tsc --noEmit && npx eslint src
# bout en bout (backend et frontend lancés) :
python -m playwright install chromium
python e2e/smoke.py --shots ./e2e-shots
```

Le test de bout en bout couvre les parcours suivants, à 1440 px et à 390 px :
- import invalide bloqué, puis import valide ;
- VaR et tiroir méthodologique ;
- création et exécution d'un scénario ;
- analyse d'une obligation ;
- génération du brief et téléchargement du PDF ;
- absence de débordement horizontal et d'erreur navigateur.

## Variables d'environnement

| Variable | Où | Défaut | Rôle |
|---|---|---|---|
| `DATABASE_URL` | backend | SQLite dans `RISKPILOT_DATA_DIR` | Ex. `postgresql+psycopg://user:pwd@host:5432/riskpilot` |
| `RISKPILOT_DATA_DIR` | backend | `backend/data` | Base SQLite et CSV des jeux de données |
| `CORS_ORIGINS` | backend | `http://localhost:3000` | Seulement si l'API est appelée directement |
| `ENABLE_ECB_PROVIDER` | backend | `true` | Active le connecteur BCE |
| `ECB_BASE_URL`, `ECB_TIMEOUT_S` | backend | API publique, 15 s | Connecteur BCE |
| `RISKPILOT_API_URL` | frontend (build et serveur) | `http://127.0.0.1:8000` | Cible du proxy `/api/*` |

Aucune clé d'API n'est nécessaire.

## Déploiement

**Docker Compose** (PostgreSQL, API et web) :

```bash
POSTGRES_PASSWORD=<mot-de-passe> docker compose up --build    # http://localhost:3000
```

**Hébergement séparé** :
- Le backend est une image Docker standard (Render, Fly.io, Railway, Cloud Run…) avec un volume persistant pour `RISKPILOT_DATA_DIR` et une base PostgreSQL managée.
- Le frontend se déploie sur Vercel ou tout hébergeur Node, avec `RISKPILOT_API_URL` défini **au build** : les rewrites Next.js sont figées à la compilation.
- L'application n'a pas d'authentification. Placez-la derrière un contrôle d'accès (SSO du fournisseur, proxy d'authentification).

## Données de marché

| Source | Provenance | Statut |
|---|---|---|
| Générateur synthétique (graine 42) | SYNTHETIC | Toujours disponible ; actions, ETF, FX, courbes EUR/USD, spreads |
| BCE Data Portal (taux de référence FX, courbe AAA zone euro) | HISTORICAL_REAL | Validé en réel (15/10/2026) : 10 séries depuis 2021, mise à jour via *Data Sources* |
| Import CSV (`date, EQ:XXX, FX:USD, IR:EUR:10Y, CS:EUR:IG…`) | Déclarée par l'utilisateur | Contrôle qualité bloquant en cas d'erreur |

Les données de la BCE sont des valeurs de référence publiées vers 16 h, jamais du temps réel. Leur réutilisation est autorisée en citant « Source: ECB Data Portal ».

## Documentation

- [docs/METHODOLOGY.md](docs/METHODOLOGY.md) : chaque formule, ses conventions, ses tests et ses limites
- [docs/DATA_MODEL.md](docs/DATA_MODEL.md) : schéma de la base, des positions et des facteurs
- [docs/LIMITATIONS.md](docs/LIMITATIONS.md) : limites connues
- [docs/DEMO.md](docs/DEMO.md) : scénario de démonstration de 5 minutes et questions probables

## Dépendances

- **Backend** : FastAPI, Pydantic, SQLAlchemy, Alembic, NumPy, pandas, SciPy, httpx, openpyxl, ReportLab (versions figées dans `requirements.txt`).
- **Frontend** : Next.js, React, Tailwind CSS, ECharts, Zustand, SWR, IBM Plex Sans (auto-hébergée via @fontsource, aucun appel à Google Fonts).
