# La boucle de mesure — prouver, ou se taire

```bash
python3 tools/demo_evolution.py     # trois vagues simulées, comparaison, rapport client
```

---

## 1. Le piège central : un avant/après ne prouve rien

Si la part de citation passe de 1,8 % à 12 %, cela peut venir de notre
publication. Ou d'un changement de modèle chez l'éditeur. Ou de la disparition
d'un concurrent. Ou de la saison. Ou du bruit d'échantillonnage.

Vendre *« depuis la publication, vous êtes cité dans 42 % des requêtes »* sur
cette base serait une affirmation causale tirée de la forme de preuve la plus
faible qui existe. Une promesse fausse de trop détruirait la crédibilité qui est
notre seul actif.

## 2. La sortie était déjà dans l'architecture : le groupe témoin

Nous mesurons une **cohorte entière** alors que nous n'en traitons qu'une partie.
Les entreprises non traitées absorbent tout ce qui affecte le marché entier.

```
effet = (traités après − traités avant) − (témoins après − témoins avant)
```

C'est aussi un bien meilleur argument commercial : *« vous avez gagné 13 points
de plus que des entreprises comparables qui n'ont rien changé »* est infiniment
plus solide que *« vous avez gagné 27 points »*.

Le champ `treated_since` sur chaque entité du panel partage la cohorte. Sans
témoins, **aucune variation n'est déclarée établie** : le code refuse.

## 3. Le piège que j'ai découvert en construisant ce module

La **part de citation est compositionnelle** : les parts somment à 100 %. Quand
une entreprise traitée gagne de la part, les témoins en perdent *mécaniquement*,
sans que rien ne leur soit arrivé.

Or la double différence suppose exactement l'inverse : que le traitement
n'affecte pas les témoins. Appliquée à une part, elle sous-estime l'effet, et
surtout elle déclarait « établies » des baisses chez des témoins inactifs. La
première version de ce module produisait exactement ce défaut, visible dans la
sortie : un témoin marqué `etabli` à −3,1 %.

**L'effet attribuable est donc estimé sur le taux de présence**, qui n'est pas
compositionnel : un moteur peut citer trois entreprises ou cinq, et la présence
de l'une ne retire rien à celle de l'autre. La part reste publiée, mais comme
**description**, jamais comme estimation causale.

## 4. Deux mesures du bruit, cumulatives

Une variation n'est rapportable que si elle franchit **les deux** :

**L'intervalle de confiance apparié.** Rééchantillonnage des prompts avec remise,
1 000 tirages, déterministe. Le panier étant figé, les deux vagues portent sur
les mêmes questions : on tire **un seul** échantillon et on calcule la différence
dessus. Apparier élimine la variance commune et resserre l'intervalle, là où deux
tirages indépendants la doubleraient.

**Le plancher de bruit empirique.** Neuvième décile des variations absolues
observées **chez les témoins**. Si les entreprises qui n'ont rien fait bougent de
neuf points d'une vague à l'autre, une hausse de six points chez un traité ne
veut rien dire, quel que soit son intervalle.

D'où trois verdicts : `etabli`, `sous le bruit`, `non concluant`.

## 5. Ce que le code refuse

`check_comparable()` lève `Incomparable` plutôt que de produire un delta faux :

| Refus | Pourquoi |
|---|---|
| Paniers différents | les questions ont changé, les parts ne se comparent pas |
| Panel modifié | une part de citation est relative aux entités suivies |
| Moteurs différents | chaque éditeur a son propre comportement |
| Ordre inversé | une vague postérieure doit être postérieure |

Les vagues archivent les observations **prompt par prompt**, jamais les parts
agrégées : sans le détail, ni le rééchantillonnage ni une contestation ne
seraient possibles plus tard.

## 6. La valorisation, et son plafond

`modelled_value()` traduit un gain de **part** en euros. Trois disciplines :

- **sur la part, pas sur la présence** : un gain de présence de treize points ne
  signifie pas capter treize pour cent de la demande du marché ;
- **plafonné par la capacité** (`max_monthly_deals`) : sans ce plafond, toute
  valorisation d'un gain de visibilité suppose une entreprise à capacité
  infinie, ce qui produit des chiffres flatteurs et faux — l'erreur commise puis
  corrigée dans `docs/METHODE.md` ;
- **jamais présentée comme du chiffre d'affaires attribué** : aucune vente n'est
  rattachée à une citation, et le rapport le dit à chaque fois.

## 7. Le rapport mensuel

C'est le produit, pas un outil de débogage interne. Il ne dit jamais « grâce à
nous » — un test l'interdit. Il compte en **questions**, pas en pourcentages :

```
CE QUI A CHANGÉ
  Vous étiez cité sur 29 questions sur 45. Vous l'êtes maintenant sur 41.
  Part de la voix de votre marché : 12,6 % vers 23,1 %.

COMPARAISON AVEC LES ENTREPRISES QUI N'ONT RIEN CHANGÉ
  Nous suivons 16 entreprises comparables qui n'ont pas publié de nouvelles données.
  Écart attribuable : +13,2 % de présence au-delà de leur propre évolution.

CE QUE CE RAPPORT NE DIT PAS
  Nous ne contrôlons aucun éditeur et ne garantissons aucune position.
  Les réponses brutes sont archivées et consultables.
```

Quand la variation est sous le bruit, le rapport le dit et **ne la compte pas**.
C'est ce refus qui rend croyables les mois où l'on compte.

## 8. Limite connue de la démonstration

Le moteur simulé attribue un nombre de places **fixe** (deux à quatre) par
réponse. La présence y reste donc partiellement compositionnelle, et un témoin
peut y apparaître en baisse « établie ». C'est une limite du simulateur, pas de
la méthode : un moteur réel cite un nombre variable de sources. Ce résidu
disparaîtra sur données réelles, et c'est précisément ce que la première vague
réelle permettra de vérifier.
