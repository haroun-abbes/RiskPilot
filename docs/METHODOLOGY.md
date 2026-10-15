# Méthodologie quantitative de RiskPilot

Ce document décrit chaque calcul produit par le moteur (`backend/riskpilot/quant/`). Pour chaque formule, on y trouve la définition mathématique, les variables et leurs unités, les conventions, le module d'implémentation, les tests associés et les limites d'interprétation. Aucun chiffre affiché par l'application ne provient d'un autre endroit que ces modules.

Conventions globales :

| Élément | Convention |
|---|---|
| Devise de base | EUR (seule devise de base prise en charge) |
| Signe | P&L > 0 = gain. Perte L = −P&L. **VaR et ES sont des nombres positifs exprimant des pertes.** |
| Rendements | Prix et FX : rendement simple quotidien r_t = P_t/P_{t−1} − 1. Taux et spreads : variation absolue Δx_t = x_t − x_{t−1} (décimal) |
| Annualisation | 252 jours ouvrés, σ_ann = σ_jour · √252 |
| FX | `FX:CCY` = valeur en EUR d'une unité de CCY (EUR par USD). Rendement positif = la devise étrangère s'apprécie |
| Taux, spreads | Décimal (0,025 = 2,5 %), affichés en % ou en points de base (1 bp = 0,0001) |
| Données manquantes | Jamais comblées. Une date où un facteur requis manque est retirée de la fenêtre et signalée |

---

## 1. Calendrier et échéanciers — `quant/daycount.py`

**Fraction d'année** YF(d₁, d₂) :

| Convention | Formule |
|---|---|
| ACT/365F | jours(d₁,d₂) / 365 |
| ACT/360 | jours(d₁,d₂) / 360 |
| 30E/360 (Eurobond) | [360(Y₂−Y₁) + 30(M₂−M₁) + (D₂−D₁)] / 360 avec D = min(D, 30) |
| 30/360 US (Bond basis) | idem, D₁ = 31 → 30 ; D₂ = 31 → 30 seulement si D₁ ≥ 30 |
| ACT/ACT ICMA | jours(d₁,d₂) / (f · jours(t₀, t₁)), où [t₀, t₁] est la période de coupon qui contient d₁ et d₂ |

**Échéancier** : les dates sont générées à rebours depuis la maturité par pas de 12/f mois, toujours calculées depuis la maturité pour éviter la dérive des jours. Si la maturité tombe en fin de mois, toutes les dates sont des fins de mois (règle end-of-month). La liste retournée est `[coupon précédent, coupons suivants, ..., maturité]` avec coupon précédent ≤ règlement < coupon suivant. Un règlement le jour d'un coupon exclut ce coupon : il revient au vendeur.

**Hypothèses** : périodes régulières (pas de premier ni de dernier coupon brisé), dates non ajustées des jours fériés.

**Tests** (`tests/test_bonds.py`) : exemples 30E vs 30 US (15/01 → 31/03 donne 75 jours contre 76), ACT/365F, ACT/360 et ACT/ACT ICMA sur 181 jours, échéancier fin de mois (28/02/2030 → 31/08/2029), règlement un jour de coupon, convention inconnue refusée.

## 2. Obligations à taux fixe — `quant/bonds.py`

Notations pour 100 de nominal : c = taux de coupon annuel (décimal), f = fréquence, C = 100·c/f = coupon par période, y = rendement actuariel composé f fois par an, s = date de règlement, t₀ et t₁ = coupons précédent et suivant.

- **Fraction de période restante** : w = 1 − YF(t₀, s) / YF(t₀, t₁)
- **Nombre de périodes jusqu'au flux k** : n_k = k − 1 + w ; **temps en années** : t_k = n_k / f
- **Prix dirty (valeur actuelle des flux)** : P(y) = Σ_k CF_k · (1 + y/f)^(−n_k), avec CF_k = C, et C + 100 pour le dernier flux
- **Coupon couru** : AI = 100 · c · YF(t₀, s) (sous la convention de l'obligation)
- **Prix clean** : P_clean = P − AI. C'est le prix coté. Le prix dirty est le montant réellement payé.
- **Rendement actuariel** : racine de P(y) − (P_clean + AI) = 0 par la méthode de Brent sur [−50 %, 200 %], tolérance 10⁻¹⁴. Une erreur explicite est levée si aucun rendement ne reproduit le prix.
- **Duration de Macaulay** (années) : D_mac = Σ t_k PV_k / P
- **Duration modifiée** : D_mod = D_mac / (1 + y/f) = −(1/P) dP/dy
- **Convexité** : C_x = (1/P) d²P/dy² = Σ PV_k · t_k (t_k + 1/f) / [P (1 + y/f)²]
- **DV01** (pour 100 de nominal, en points de prix) : D_mod · P / 10 000
- **Approximation** : ΔP/P ≈ −D_mod Δy + ½ C_x Δy²

Le moteur calcule aussi une **duration et une convexité effectives** par différences finies (±1 bp), affichées comme contrôle croisé dans l'interface.

**Pourquoi clean et dirty ?** Le prix dirty chute du montant du coupon à chaque détachement. Coter clean retire cette dent de scie : la variation du prix coté ne reflète alors que la variation de rendement.

**Ne pas confondre** : y est le rendement de l'obligation. Il inclut un taux de référence souverain et une prime de crédit et de liquidité. Le **G-spread** affiché vaut y − y_gouv(T), où y_gouv est interpolé linéairement sur la courbe du jeu de données à la maturité T. C'est une approximation : ni Z-spread, ni OAS, et la courbe (par exemple la courbe zéro-coupon AAA de la BCE) n'a pas forcément la même convention de composition que l'obligation.

**Tests** (17 au total) :
- 10 ans, coupon annuel 5 %, rendement 6 % à une date de coupon : prix = 92,6399. Ce résultat est vérifié contre la formule fermée de l'annuité, calculée indépendamment.
- Obligation semestrielle comparée à la même formule fermée.
- Obligation au pair à une date de coupon : clean = 100.
- Zéro-coupon : D_mac = T, P = 100/(1+y)^T, C = T(T+1)/(1+y)².
- Coupon couru en 30E/360 et en ACT/ACT ICMA, calculé à la main.
- Prix dirty entre deux coupons, recalculé indépendamment à partir des jours exacts.
- Aller-retour rendement → prix → rendement à 10⁻¹¹ près, y compris pour des rendements négatifs.
- Prix strictement décroissant et convexe en y, vérifié sur 200 points.
- Duration et convexité analytiques égales aux différences finies (écart relatif inférieur à 10⁻⁶ et 10⁻⁴).
- À ±100 bp, l'approximation duration + convexité est plus précise que la duration seule, avec une erreur inférieure à 5·10⁻⁴.
- Entrées invalides refusées.

**Limites** : pas de coupon brisé, pas d'ajustement des jours fériés, pas d'ex-dividend period, remboursement in fine au pair, pas de défaut. Les obligations à taux variable, callables ou indexées sont **refusées à l'import** avec un message explicite, plutôt qu'approximées.

## 3. Mapping des positions sur les facteurs de risque — `quant/engine.py`

| Instrument | Valeur (EUR) | Facteurs |
|---|---|---|
| Action / ETF | V = q · P · X | `EQ:<ticker>` (ou `EQ:<proxy>` si une série proxy est déclarée), `FX:<ccy>` |
| Obligation à taux fixe | V = N/100 · P_dirty(y₀) · X | `IR:<ccy>:<ténor>` (les deux ténors encadrant la maturité, pondérés), `CS:<ccy>:<IG/HY>` selon la notation (aucun pour un souverain), `FX:<ccy>` |
| Cash en devise | V = A · X | `FX:<ccy>` (aucun si EUR) |

y₀ est le rendement implicite du prix clean importé. La variation de rendement d'une obligation vaut :

Δy = Σ_j w_j(T) Δr_j + Δs_bucket

où w_j(T) sont les poids d'interpolation linéaire de la courbe à la maturité T (extrapolation plate aux extrémités).

Une position **sans facteur disponible est exclue** des mesures de risque. Son motif est affiché (série de prix manquante, devise sans taux de change, courbe absente). Le taux de couverture (part de la valeur brute réellement mesurée) est publié.

**Revalorisation** pour des mouvements (r_e, r_x, Δy) :
- Action : V₁ = V₀ (1 + r_e)(1 + r_x)
- Obligation : V₁ = N/100 · P_dirty(y₀ + Δy) · X(1 + r_x), soit une **revalorisation complète**
- Cash : V₁ = V₀ (1 + r_x)

**P&L linéarisé** (utilisé uniquement par le modèle paramétrique) : V₀(r_e + r_x) pour une action, V₀(−D_mod Δy + r_x) pour une obligation.

**Sensibilités** affichées : delta de 1 % sur les actions et le FX (V₀ · 1 %), DV01 par ténor clé (−w_j · DV01), CS01 (−DV01). La somme des DV01 par ténor clé redonne le DV01 total (testé).

## 4. Simulation historique, VaR et ES — `quant/risk_measures.py`

**Scénarios** : pour chaque jour t de la fenêtre (500 jours par défaut), les mouvements de facteurs observés entre t−1 et t sont appliqués aux positions **d'aujourd'hui**, puis chaque position est revalorisée. On obtient une matrice P&L[t, i] de dimension T × N, et le P&L du portefeuille en est la somme par ligne.

**VaR historique** : avec n scénarios, α le niveau de confiance et k = n(1 − α), les pertes sont triées par ordre décroissant L[1] ≥ … ≥ L[n].

VaR_α = L[⌊k⌋ + 1] = inf{ l : F̂_n(l) ≥ α }

C'est le quantile empirique, sans interpolation. Avec 500 jours à 99 %, k = 5 et la VaR est la 6ᵉ pire perte.

**Expected Shortfall historique** (estimateur d'Acerbi et Tasche, 2002) :

ES_α = (1/k) · [ Σ_{i ≤ ⌊k⌋} L[i] + (k − ⌊k⌋) · L[⌊k⌋ + 1] ]

C'est la moyenne des 100(1 − α) % pires résultats. L'estimateur gère un k non entier (250 jours à 99 % donnent k = 2,5), il est cohérent et vérifie toujours ES ≥ VaR.

**VaR et ES paramétriques (delta-normal)** : σ² = 1ᵀ Σ 1, où Σ est la covariance empirique (ddof = 1) des P&L linéarisés des positions.

VaR = z_α σ − μ    ES = σ · φ(z_α)/(1 − α) − μ

avec μ = 0 par défaut, un choix documenté pour les horizons courts.

**Horizon** : X_h = X_1 · √h. Cette mise à l'échelle n'est valable que si les P&L quotidiens sont indépendants, identiquement distribués et de moyenne nulle. Elle est **signalée dans chaque résultat** qui l'utilise.

**Seuils de données** :
- Moins de 100 observations, ou k < 1 : **aucun chiffre historique n'est produit**, et le motif est affiché.
- Moins de 250 observations, ou k < 5 : le chiffre est produit, accompagné d'un avertissement.

**Diagnostics publiés** :
- asymétrie et kurtosis en excès du P&L
- corrélation entre P&L en revalorisation complète et P&L delta
- bénéfice de diversification

Sur le jeu synthétique, la kurtosis en excès vaut environ 4,8, ce qui explique une VaR historique supérieure d'environ 30 % à la VaR normale.

**Tests** (`tests/test_risk_measures.py`, 16) :
- Pertes 1..500 : VaR à 99 % = 495, ES = 498.
- k fractionnaire : VaR = 248, ES = (250 + 249 + 0,5·248)/2,5.
- Définition du quantile vérifiée sur données aléatoires.
- Convention de signe : un portefeuille qui ne fait que des gains a une VaR négative.
- ES ≥ VaR sur 150 tirages.
- Données insuffisantes refusées, NaN refusés.
- Valeurs de référence normales : z₀,₉₉ = 2,3263, ES₀,₉₉ = 2,6652σ, ES₀,₉₇₅ = 2,3378σ.
- Mise à l'échelle √h.
- Reproductibilité.

**Limites** :
- La VaR **n'est pas une perte maximale**.
- La simulation historique ignore les événements absents de la fenêtre.
- Les poids sont égaux dans le temps : aucune pondération de la volatilité récente.
- Les positions sont supposées constantes sur l'horizon.

## 5. Volatilité, covariance, corrélation

- Volatilité historique annualisée : sd(r, ddof = 1) · √252. Pour les taux et les spreads, elle est exprimée en bp par an.
- EWMA (RiskMetrics) : s²_t = λ s²_{t−1} + (1 − λ) r²_{t−1}, avec λ = 0,94 et une initialisation sur la variance des 20 premières observations.
- Covariance et corrélation calculées sur les variations de facteurs alignées (aucune date manquante). La symétrie et la valeur propre minimale de la covariance sont affichées.

Tests : covariance égale à `np.cov`, symétrique et définie positive ; diagonale de corrélation égale à 1 et |ρ| ≤ 1.

## 6. Contributions au risque — `component_*` et `services/analytics.py`

- **Contribution à l'ES historique (décomposition exacte)** : CES_i = −Σ_t w_t P&L_{t,i}, où w_t vaut 1/k sur les ⌊k⌋ pires jours du portefeuille et (k − ⌊k⌋)/k sur le suivant. Par construction Σ_i CES_i = ES. Une contribution négative signale une couverture.
- **Contribution d'Euler à la VaR delta-normale** : CVaR_i = z_α (Σ1)_i / σ_p, et Σ_i CVaR_i = VaR (théorème d'Euler pour une mesure homogène de degré 1).
- **Par groupe** (classe d'actifs, émetteur, secteur, devise, pays) : simple somme des contributions individuelles, exacte grâce à l'additivité.
- **Par facteur** : on décompose le P&L linéarisé en colonnes facteur par facteur, f_t = exposition_f · Δf_t. La somme de ces colonnes reproduit exactement le P&L delta, ce qui permet d'appliquer Euler sur les facteurs.
- **Par classe de facteurs en revalorisation complète** : ES « stand-alone » obtenu en ne faisant bouger qu'une classe de facteurs à la fois. Leur somme moins l'ES total donne le bénéfice de diversification. Une décomposition exacte de l'ES historique par facteur n'existe pas en revalorisation complète, à cause des effets croisés (par exemple action × FX). L'interface le dit explicitement.

L'application ne présente **jamais** une allocation en valeur de marché comme une contribution au risque : les deux sont affichées côte à côte.

**Tests** :
- La somme des contributions ES est égale à l'ES, de même pour la somme des contributions Euler, des contributions par groupe et des contributions par facteur (`tests/test_risk_measures.py`, `tests/test_api.py`).

## 7. Backtesting — `backtest_historical_var`, `kupiec_pof`

On calcule une VaR historique 1 jour glissante, estimée sur les `window` jours précédents. Elle est comparée au P&L hypothétique du lendemain, positions constantes, sur les 250 derniers jours. On compte une exception quand la perte dépasse la VaR.

**Test de Kupiec (POF)** :

LR = −2 ln[(1−p)^{n−x} p^x] + 2 ln[(1−x/n)^{n−x} (x/n)^x] ~ χ²(1), avec p = 1 − α

**Zones de Bâle** (250 observations, 99 %) : vert de 0 à 4 exceptions, jaune de 5 à 9, rouge à partir de 10. Elles ne sont affichées que dans ce cas précis.

**Limites** : le P&L backtesté est hypothétique (positions d'aujourd'hui), et 250 observations donnent un test de faible puissance.

## 8. Stress tests — `quant/stress.py`

Deux natures de scénarios, strictement séparées dans les données et dans l'interface.

**Hypothétique** :
- Actions : choc de rendement avec la priorité ticker > secteur > pays > tous.
- Taux : choc en bp par devise, qui combine un parallèle et des points par ténor. Ces points sont interpolés linéairement à la maturité de chaque obligation, plats au-delà des bornes.
- Spreads : choc en bp par bucket IG/HY. Les souverains ne reçoivent pas de choc de spread.
- FX : rendement de la devise en EUR.

**Rejeu historique** : mouvements cumulés du jeu de données entre deux dates. Pour EQ et FX, le mouvement vaut L_fin/L_début − 1 ; pour IR et CS, il vaut L_fin − L_début. Sa provenance est celle du jeu de données : un rejeu sur données synthétiques est un épisode synthétique, et l'application l'indique.

**Calcul** :
- Revalorisation instantanée complète, sans portage, roll-down ni rebalancement.
- Pour chaque obligation, l'approximation duration-convexité est affichée à côté de la revalorisation complète.
- La cascade (waterfall) choque une classe de facteurs à la fois, et le reste est publié comme **effet croisé**. La somme des composantes égale donc toujours le total (testé).
- Chaque scénario est comparé à une référence d'échelle : l'ES historique 99 % à 10 jours.

**Le scénario « Combined risk-off » est stylisé** : il ne prétend reproduire aucune crise historique. Un choc uniforme des taux ne reproduit pas une crise réelle.

## 9. Alertes — `alerts.py`

Les règles sont déterministes :
- **niveau** : x_t comparé à un seuil ;
- **variation sur L jours** : rendement pour EQ et FX, différence absolue pour IR et CS ;
- **z-score** : mouvement du jour divisé par l'écart-type des 250 mouvements précédents, en excluant le jour t. Il ne regarde donc jamais le futur.

Les directions possibles sont : au-dessus, en dessous, des deux côtés. Le message d'alerte est un gabarit, jamais un texte généré.

Tests : `tests/test_alerts.py`.

## 10. Qualité des données — `data/quality.py`

Contrôles appliqués à chaque série :
- valeurs manquantes dans la plage ;
- trous de plus de 5 jours calendaires ;
- au moins 5 valeurs identiques consécutives (flux figé) ;
- prix non positifs ;
- taux supérieurs à 50 % (probablement exprimés en pourcent) ;
- mouvements au-delà de 8 écarts-types robustes (MAD × 1,4826).

Rien n'est corrigé automatiquement. Un jeu de données importé qui contient des erreurs bloquantes est refusé.

## 11. Données synthétiques — `data/synthetic.py`

- Deux facteurs de marché actions (EU, US) avec une volatilité GARCH(1,1) (α = 0,08, β = 0,90) et des innovations de Student à 5 degrés de liberté, corrélées à 0,75.
- Actions : r_i = β_i m + σ_i ε_i.
- Courbes EUR et USD : facteurs de niveau et de pente avec rappel à la moyenne.
- Spreads IG et HY : s'élargissent quand les actions baissent.
- FX : USD, CHF et JPY se comportent en valeurs refuges.
- Un épisode de stress scripté à partir du 24/03/2025.
- Graine fixe (42) : le jeu de données est reproductible.

Tous les émetteurs et tickers sont **fictifs**, ce qui empêche toute confusion avec des cotations réelles.

## 12. Reproductibilité

Chaque résultat transporte :
- les paramètres de calcul ;
- l'empreinte SHA-256 (tronquée) du portefeuille et du jeu de données ;
- la version du moteur ;
- l'horodatage du calcul.

Le Decision Brief stocke ces éléments avec ses résultats. Deux briefs générés avec les mêmes entrées donnent des indicateurs identiques (testé).
