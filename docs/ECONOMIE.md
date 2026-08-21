# Économie du modèle

Toutes les valeurs de ce document sont produites par `tools/economics.py`. Le
modèle est du code testé (`tests/test_economics.py`, 17 tests) plutôt qu'un
tableur, pour la même raison que la Part de Citation est calculée et non
estimée : un chiffre dont on ne peut pas montrer le calcul n'est pas un
argument.

```bash
python3 tools/economics.py                          # scénario de référence, 24 mois
python3 tools/economics.py --convert-rate 0.010     # test de rupture sur la conversion
python3 tools/economics.py --exclusif-slots-per-month 2 --months 36
```

## 0. Pourquoi l'offre a changé de forme, deux fois

L'offre initiale avait trois paliers, tous payants (349 € / 749 € / 1 490 €),
vendus par un seul mouvement commercial sortant. Premier changement : un
palier gratuit et un forfait accessible à 19 €, calibrés sur le rapport de
marché fourni (Webflow Premium à **25 $**, Base44 à partir de **40 $**) —
détail dans l'historique de ce document.

**Second changement, plus important : le gratuit est publié.** La première
version du palier gratuit constituait et vérifiait le dossier sans jamais le
distribuer — repli tentant pour protéger la conversion, mais qui casse
mécaniquement le pari central du produit. La position plateforme ne vaut que
si le registre est la source la plus **complète**, pas la plus rentable par
entrée : un agent qui cherche « plombiers à Lyon » et n'en trouve que les
abonnés payants n'a aucune raison de préférer ce registre au web scrappé.
Chaque restriction d'accès affaiblit exactement ce qui rend le registre
précieux — le même raisonnement mécanique qui a déjà fait sortir
l'exclusivité du registre (`docs/PLAN.md` §1). Il y a aussi un problème de
perception : « payez pour exister » est le modèle des annuaires
professionnels payants des années 2000, un modèle que tout prospect
sceptique reconnaît et fuit.

**La frontière retenue suit le coût de vérification, pas la visibilité.** Le
Gratuit publie la fiche **minimale** : identité vérifiée automatiquement
(nom, catégorie, zone, SIREN), page publique et JSON-LD, pour toute
entreprise, sans exception. Le Forfait vend la fiche **complète** :
chantiers vérifiés sur pièce, budgets constatés, certifications, treillis de
pages, mesure de citation périodique — tout ce qui exige une vérification
**humaine**, qui ne s'automatise pas. Le gratuit publié est aussi le
meilleur canal d'acquisition : chaque fiche minimale est une porte
d'entrée vers le diagnostic et l'upsell, ce qu'une fiche non publiée ne
pouvait pas être.

**Ce que coûte la vérification automatique — la question qui décidait si le
gratuit est soutenable.** L'identité d'une entreprise française (SIREN,
raison sociale, adresse, code NAF) se vérifie via
[`recherche-entreprises.api.gouv.fr`](https://recherche-entreprises.api.gouv.fr/docs/)
(DINUM/SocialGouv, données Sirene de l'INSEE) : **gratuite, publique, sans
authentification**, avec une limite de l'ordre de 7 requêtes par seconde —
largement suffisant à l'échelle de ce modèle (quelques centaines
d'inscriptions par mois, §2). Le coût marginal de la vérification elle-même
est donc **nul** ; `cost_free_per_user` (1 €/mois, §1) ne couvre que
l'ingestion et le stockage, pas un poste de vérification qui n'existe pas.
C'est ce qui rend le gratuit publié soutenable à grande échelle : le seul
coût qui grandit avec le volume est déjà dans le modèle.

Une nuance chiffrée depuis (`docs/VERIFICATION.md`) : l'API ne fournit
**aucun canal de contact** (vérifié en réel — ni e-mail ni téléphone, pour
aucun établissement), donc la **revendication** d'une fiche passe soit par
le domaine propre de l'entreprise (coût nul, minutes), soit par un
**courrier au siège** (~1-2 € l'envoi, ~1 semaine). C'est un coût
**d'acquisition ponctuel** par fiche revendiquée, pas un coût mensuel de
service : il n'entre pas dans `cost_free_per_user`, il s'amortit dans le CAC
du mouvement concerné — et seulement pour les entreprises sans domaine, qui
sont celles que la voie express ne couvre pas.

## 1. Deux mouvements commerciaux, deux unités économiques

Les confondre en un ARPU moyen — ce que faisait la version précédente de ce
modèle — aurait cousu ensemble deux entreprises différentes. Elles sont
présentées séparément.

### Mouvement 1 — Gratuit → Forfait (19 €/mois), self-serve

| | Valeur | Origine |
|---|---|---|
| Prix | **19 €/mois** | calibré sur Webflow Premium (25 $) et Base44 (~40 $), côté accessible |
| Conversion éventuelle des inscrits gratuits | **13,0 %** | `convert_rate / (convert_rate + churn_free)` = 1,5 % / (1,5 % + 10 %) |
| Marge brute / client Forfait / mois | **13 €** | 19 € − 3 € de mesure − 3 € d'exploitation, quasi automatisées |
| CAC effectif | **82 €** | coût d'inscription **et** hébergement de tous les gratuits qui ne convertissent jamais, amorti sur ceux qui paient |
| **LTV** | **217 €** | marge × durée de vie (churn 6 %/mois, ≈ 16,7 mois) |
| **LTV / CAC** | **2,6x** | — |
| Retour sur CAC | 6,3 mois | |

**Ce ratio est sciemment sous le seuil de santé classique de 3x, et ce n'est
pas un défaut à corriger en gonflant les hypothèses.** À 19 €/mois, ce palier
ne peut pas structurellement être un centre de profit isolé — comparer
Linktree ci-dessus. Son rôle est de couvrir le registre en volume (l'argument
"aider un maximum d'entreprises") et d'alimenter le second mouvement par
recommandation et par upsell, pas de porter la rentabilité. `tests/test_economics.py`
vérifie explicitement que ce ratio reste **entre 1x et 3x** — en dessous de
1x, le canal détruirait de la valeur ; au-dessus de 3x, l'hypothèse serait
trop optimiste pour un prix d'entrée volontairement bas.

### Mouvement 2 — Sortant → Exclusif, playbook `docs/VENTE.md` inchangé

| | Valeur | Origine |
|---|---|---|
| Prix | **990 €/mois** | position vérifiée exclusive, catégorie × zone |
| Marge brute / client / mois | **859 €** | 990 € − 11 € de mesure (2 moteurs) − 120 € d'exploitation |
| CAC | **2 400 €** | 100 audits de prospection × 9 € + 1 500 € de temps commercial |
| **LTV** | **35 050 €** | marge × durée de vie (churn 2,5 %/mois, 40 mois — coût de sortie réel : le créneau part à un concurrent) |
| **LTV / CAC** | **14,6x** | |
| Retour sur CAC | 2,8 mois | |

C'est ce mouvement qui porte l'économie du modèle. `docs/VENTE.md` ne change
pas : l'Audit d'Invisibilité, la séquence de six touches, les objections, le
seuil de 8 % audit → rendez-vous restent la méthode de vente de ce palier —
elle n'a jamais eu de sens pour un abonnement à 19 €, elle en a pour un
contrat à 990 €.

## 2. Trajectoire combinée

Signups gratuits : 20 au mois 1, montée jusqu'à 150/mois au mois 6.
Exclusif : 1 vente au mois 1, montée jusqu'à 4/mois au mois 6. Coûts fixes
14 000 €/mois (plus légers que le modèle 100 % sortant précédent : le canal
Forfait n'a pas d'équipe commerciale dédiée).

| Mois | Gratuits | Forfait | Exclusif | MRR | EBITDA | Cumul |
|---:|---:|---:|---:|---:|---:|---:|
| 1 | 20 | 0 | 1 | 990 € | −14 911 € | −14 911 € |
| 6 | 425 | 10 | 14 | 14 397 € | −9 110 € | −76 656 € |
| 9 | 695 | 31 | 25 | 25 334 € | 39 € | **−85 583 €** |
| 12 | 882 | 58 | 35 | 35 626 € | 8 687 € | −68 054 € |
| 18 | 1 101 | 117 | 53 | 54 205 € | 24 383 € | 40 047 € |
| 24 | 1 207 | 170 | 68 | 70 214 € | 37 983 € | 234 927 € |

- **EBITDA mensuel positif : mois 9.**
- **Cumul positif : mois 17.**
- **Besoin de financement maximal : 86 k€ au mois 8.**

Comparé à l'ancien modèle 100 % sortant (162 k€ de besoin maximal, cumul
positif au mois 19), celui-ci atteint le seuil plus tôt et demande moins de
capital — parce que le canal Forfait, même à faible marge unitaire, ne coûte
presque rien à faire tourner et commence à contribuer dès les premiers mois,
avant que le mouvement Exclusif n'ait fini sa montée en charge.

## 3. Sensibilité

**À la conversion gratuit → Forfait**, l'hypothèse la moins certaine du
modèle — personne ne la connaît tant qu'elle n'est pas mesurée sur de vrais
inscrits, exactement comme `slots_per_month` l'était pour l'ancien modèle :

| Taux mensuel | Conversion éventuelle | CAC effectif | LTV/CAC |
|---|---|---|---|
| 1,0 % | 9,1 % | 122 € | 1,8x |
| 1,5 % (référence) | 13,0 % | 82 € | 2,6x |
| 2,5 % | 20,0 % | 50 € | 4,3x |

Sous 1,0 %, le canal Forfait s'approche du régime Linktree (volume sans
monétisation) : il resterait utile pour le registre, mais cesserait de
contribuer à la trésorerie. Le suivre chaque mois dès les premiers
utilisateurs gratuits est donc la même discipline que le taux audit →
rendez-vous pour l'Exclusif.

**Au churn Forfait** :

| Churn mensuel | Durée de vie | LTV | LTV/CAC |
|---|---|---|---|
| 6 % (référence) | 16,7 mois | 217 € | 2,6x |
| 9 % | 11,1 mois | 144 € | 1,8x |
| 12 % | 8,3 mois | 108 € | 1,3x |

**Au churn Exclusif**, le modèle reste largement au-dessus de 3x même dégradé
à 5 %/mois (contre 2,5 % en référence) — voir `tests/test_economics.py::TestExclusifMotion`.

## 4. Ce que ces chiffres disent du modèle

**Ce sont deux entreprises sous un même toit.** Le Forfait construit la
couverture et la preuve d'universalité ; l'Exclusif construit la trésorerie.
Vouloir que le premier soit aussi rentable que le second reviendrait à
reproduire l'erreur de prix des paliers précédents — inaccessible, et donc
contraire à l'objectif.

**Le palier gratuit n'est pas gratuit à servir, seulement peu coûteux
(≈ 1 €/mois/utilisateur).** À l'échelle, ce coût doit rester amorti par la
conversion — c'est tout l'objet du calcul de CAC effectif ci-dessus plutôt
qu'un CAC naïf qui ignorerait les inscrits qui ne paient jamais.

**Le déclencheur de conversion doit rester structurel, pas cosmétique.**
Retenir la distribution (visibilité aux agents) plutôt qu'une fonctionnalité
secondaire est ce qui sépare ce modèle du régime Linktree — c'est aussi
pourquoi ce choix ne doit pas être affaibli plus tard pour "faciliter
l'inscription".

**Le seul chiffre à surveiller chaque semaine, sur le mouvement Forfait, est
le taux de conversion gratuit → payant.** Sur l'Exclusif, c'est toujours le
taux audit → rendez-vous (`docs/VENTE.md`). Les deux pilotent, chacun de son
côté, si l'entreprise atteint son seuil de rentabilité.
