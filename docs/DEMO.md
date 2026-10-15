# Scénario de démonstration (5 minutes)

Les chiffres indiqués correspondent au jeu **synthétique** fourni : portefeuille de démonstration valorisé le 14/10/2026, confiance 99 %, horizon 1 jour, fenêtre 500 jours. Annoncez-le d'emblée : *« Les données sont synthétiques et les émetteurs fictifs. Ce que je montre, c'est la méthode et l'outil, pas un marché réel. »*

## 0:00 – Le contexte (30 s)

Ouvrez **Overview**.
- Montrez la barre de contexte hachurée : elle signale en permanence des données synthétiques. Chaque chiffre est relié à un portefeuille, un jeu de données, des paramètres, une empreinte et une version du moteur (pastilles en bas de page).
- Indicateurs clés : environ 15,1 M€ nets, VaR historique 99 % à 1 jour d'environ 156 k€ (1,03 %), ES d'environ 219 k€.

## 0:30 – Import d'un portefeuille (60 s)

**Portfolio**, onglet **Import a portfolio**.
1. Glissez `e2e/fixtures/invalid_portfolio.csv`, puis cliquez sur **Validate**. L'outil refuse :
   - un identifiant en double ;
   - un prix négatif ;
   - une fréquence de coupon de 3 ;
   - une obligation à taux variable (« not valued by this engine ») ;
   - une devise inconnue.
   Le bouton **Confirm import** reste désactivé.
2. Téléchargez le modèle CSV, réimportez-le et confirmez. Le nouveau portefeuille devient le portefeuille actif sur toutes les pages.
3. Dans le tableau des positions, montrez la colonne des facteurs de risque. Kestrel Robotics est rattachée à un proxy (aucun historique propre) : c'est signalé, et non inventé.

## 1:30 – Risk Analytics (75 s)

- Comparez historique et paramétrique : 156 k€ contre 119 k€. L'écart d'environ 30 % s'explique par une kurtosis en excès de 4,8 : le modèle normal sous-estime la queue de distribution.
- Ouvrez le bouton **Method** de la VaR : formule (quantile empirique, k = n(1−α) = 5, donc 6ᵉ pire perte), hypothèses, limites (« pas une perte maximale »).
- Backtest : 2 exceptions pour 2,5 attendues, p-value de Kupiec de 0,74, zone verte de Bâle.
- Positions : les obligations souveraines ont une contribution à l'ES **négative**. Elles couvrent le portefeuille les jours de stress (fuite vers la qualité). Même chose pour la vente à découvert sur Meridian.

## 2:45 – Stress Lab (60 s)

- Comparez « Rates +100bp » (−528 k€, −3,5 %), « Credit spread widening » (−136 k€), « Combined risk-off » (−764 k€, −5,1 %) et le rejeu de la fenêtre de stress du jeu de données (−714 k€).
- Cliquez sur « Combined risk-off » pour afficher la cascade. Actions −1,0 M€, taux +286 k€ (la baisse des taux amortit le choc), spreads −176 k€, FX +143 k€, puis l'effet croisé. Le scénario représente 1,1 fois l'ES 10 jours.
- Créez un scénario « EUR +50bp, pentification » : 50 bp en parallèle et +50 bp sur le 30 ans. Enregistrez-le : il est revalorisé immédiatement.
- Insistez sur la distinction : hypothétique ≠ historique. Le rejeu hérite de la provenance synthétique.

## 3:45 – Fixed Income (45 s)

- Dans **Bonds in portfolio**, cliquez sur **Analyse** pour Volta Energie 4,125 % 2034.
- Montrez :
  - prix clean, coupon couru, prix dirty ;
  - rendement actuariel et G-spread contre la courbe ;
  - duration modifiée et convexité, avec leur contrôle par différences finies ;
  - le graphique « exact vs duration vs duration + convexité » ;
  - le tableau des flux, dont la somme redonne le prix dirty.

## 4:30 – Attribution et brief (30 s)

- **Risk Attribution** :
  - Les actions représentent environ 25 % de la valeur brute mais 63 % de l'ES (barre bleue contre barre grise).
  - Les taux pèsent 58 k€ d'ES stand-alone mais seulement 6 k€ de VaR Euler : c'est la diversification.
- **Reports** : générez le brief en incluant trois scénarios, puis téléchargez le PDF et les CSV. Les paramètres et les empreintes figurent en en-tête.

## Questions probables

- **Pourquoi la revalorisation complète plutôt que la duration ?** Elle capte la convexité, et le moteur montre l'écart entre les deux.
- **Pourquoi ES et pas seulement VaR ?** L'ES est sous-additive et sensible à la forme de la queue (FRTB : ES 97,5 %).
- **Limites ?** Voir `docs/LIMITATIONS.md` : mise à l'échelle √h, fenêtre à poids égaux, positions constantes, données synthétiques.
