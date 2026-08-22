# Le test terrain — l'hypothèse qui décide de tout (protocole v2)

> Séquence retenue : **hypothèse → terrain → preuve → positionnement → produit.**
> Pas l'inverse. Ce document ne construit rien : il prépare dix conversations
> réelles, sous un protocole dont les seuils sont fixés et hashés *avant* de
> les avoir eues.
>
> **Les seuils numériques qui suivent ne sont pas la source de vérité — le
> code l'est.** `terrain.seuils.PROTOCOLE_V2` est l'objet verrouillé;
> `python -m terrain protocole` l'affiche avec son hash. Ce document en donne
> la lecture humaine, mais en cas d'écart, c'est le code qui a raison.
>
> **Ce que ce protocole change par rapport à la v1** : les deux hypothèses
> sont désormais évaluées entièrement indépendamment (v1 les faisait
> interagir dans une seule formule), chacune sur trois niveaux de preuve
> explicites et symétriques, et le test d'engagement (« 3 factures ») est
> reformulé comme un dossier de vérité commerciale à construire ensemble,
> plutôt qu'un service rendu gratuitement en échange d'un geste vague.

---

## 1. Deux hypothèses, jamais mélangées, jamais notées ensemble

**H1 — Représentation.** L'entreprise est mal ou pas représentée dans ce que
disent Google et les moteurs de réponse IA à son sujet, et elle perd de la
demande à cause de ça. C'est ce que mesure `citation_audit`.

**H2 — Capacité d'action.** L'entreprise perd des demandes entrantes faute de
pouvoir répondre vite et précisément (prix, délai, disponibilité), et un
système qui répondrait à sa place aurait une valeur réelle.

Chaque entretien répond séparément aux deux, parce que le produit à construire
n'est pas le même selon celle qui est validée — et une entreprise peut très
bien confirmer l'une sans l'autre. Les compter ensemble, comme le faisait la
v1, aurait pu faire passer pour validé un mélange où aucune des deux thèses
prise seule ne l'est.

---

## 2. Trois niveaux de preuve, symétriques pour H1 et H2

Le principe qui traverse tout le protocole : **seul le niveau 3 compte comme
signal commercial.** Les niveaux 1 et 2 sont consignés parce qu'un niveau 3
sans eux serait suspect (un engagement sans aucun fait ni aucune
reconnaissance qui le motive) — pas parce qu'ils suffisent seuls à valider
quoi que ce soit.

| Niveau | H1 — représentation | H2 — capacité d'action |
|---|---|---|
| **1 — fait observé** | L'audit en direct montre l'entreprise absente ou mal citée sur son propre marché. | Un décompte chiffré (pas une estimation) montre un taux significatif de réponse tardive ou absente, ou un exemple concret et daté de chantier perdu pour ce motif. |
| **2 — reconnu comme important** | Le professionnel manifeste une réaction de surprise ou d'inquiétude authentique face à l'audit (pas polie). | Le retard concerne un type de demande répétitif et nommé — pas un incident isolé qu'on ne reverra pas. |
| **3 — engagement révélé** | L'échange proposé (construire ensemble le dossier de vérité contre 3 factures + 20 minutes) est réellement honoré sous 7 jours. | Le même échange, côté réponse aux demandes, est réellement honoré sous 7 jours. |

Le niveau 3 est délibérément dur : c'est ce qui protège contre l'envie de lire
dans dix conversations sympathiques ce qu'on avait envie d'y trouver. Un
« oui » à l'oral n'est jamais un niveau 3 — c'est, au mieux, un niveau 2.

Ce triptyque est encodé dans `terrain.entretien` :
`EntretienH1.niveau1/2/3` et `EntretienH2.niveau1/2/3` sont des propriétés
calculées à partir des faits consignés, jamais saisies directement — pour
qu'aucun entretien ne puisse déclarer un niveau sans les faits qui le
justifient.

---

## 3. Sélection des dix entreprises

Un seul secteur, une seule ville — rénovation, Bordeaux Métropole — pour ne
pas ajouter une variable de plus à un test qui en a déjà deux. C'est une
contrainte explicite de cette première campagne : conflater des causes entre
types de métiers différents rendrait le résultat ininterprétable, y compris
en cas de succès.

**Ne pas prendre au hasard.** Deux biais à éviter :
- des entreprises qui ne reçoivent presque aucune demande en ligne
  aujourd'hui : elles ne pourront rien dire sur de la demande perdue ;
- uniquement des entreprises déjà convaincues du sujet (réseau affinitaire) :
  ça gonflerait artificiellement le taux de validation.

Cible : des entreprises qui reçoivent déjà un flux réel de demandes (devis,
appels, messages), sans présager de leur maturité numérique.

**Ce panel n'est pas celui de `markets/renovation-bordeaux.json`** — celui-là
sert à mesurer la citation sur des entités fictives. Les dix entretiens
demandent de vrais contacts (réseau personnel, chambre de métiers, CAPEB,
recommandations), et un fichier de marché réel par entreprise interrogée —
voir §4.

---

## 4. Le déroulé d'un entretien (20 minutes maximum)

### Étape 1 — La mesure, pas la promesse (H1)

Ouvrir par une donnée, jamais par une idée. Un fichier de marché minimal se
génère en une commande, sans écrire le JSON à la main :

```bash
python3 -m citation_audit amorce "Nom réel de l'entreprise" "catégorie" "Bordeaux" \
    --concurrent "Concurrent local 1" --concurrent "Concurrent local 2" \
    --out markets/<entreprise-reelle>.json

export ANTHROPIC_API_KEY=...
python3 -m citation_audit audit markets/<entreprise-reelle>.json \
    --provider anthropic:claude-sonnet-5 --provider anthropic:claude-opus-5 \
    --out out/
```

Ce que l'entretien observe ici n'est pas ce que dit l'artisan : c'est sa
**réaction** face à un fait qu'il n'a pas produit lui-même. Niveau 1 dès que
l'audit montre une absence ou une mauvaise citation ; niveau 2 si la réaction
est une surprise ou une inquiétude authentique.

### Étape 2 — H2, en comptant, pas en évaluant

Questions dans cet ordre, quantitatives avant qualitatives :

1. « Sur une semaine normale, tous canaux confondus, combien de personnes vous
   contactent pour un devis ou une question ? » — ouvrir le téléphone
   ensemble et compter les 7 derniers jours plutôt que d'estimer.
2. « Combien vous rappelez en moins de 5 minutes ? Entre 5 minutes et une
   heure ? Après une heure ? Combien ne sont jamais rappelées ? »
3. « Qu'est-ce qui fait qu'une demande traîne ou tombe à l'eau ? »
4. « Les questions qu'on vous pose reviennent souvent les mêmes ? Lesquelles ? »
5. « Un dimanche soir, quelqu'un demande un prix ou une dispo : il se passe
   quoi ? »
6. « Un exemple récent où vous pensez avoir perdu un chantier parce que la
   réponse est arrivée trop tard ou pas du tout ? »

Les réponses aux questions 1-2 se consignent dans `terrain.entretien.EvenementsH2`
— le décompte, pas une note libre. La question 6 nourrit
`type_repetitif_identifie` dès qu'un motif nommé se dégage, pas un incident
isolé.

### Étape 3 — L'engagement révélé, pas déclaré (niveau 3, H1 et H2)

Ne jamais demander « seriez-vous prêt à payer ». Proposer un échange concret,
formulé comme la construction d'un dossier de vérité commerciale, pas un
service offert en échange d'un geste vague :

> « On construit avec vous le dossier de vérité de votre entreprise —
> [montrer `noyaux/atelier-ferrand.json` rendu] — à partir de vos vrais
> chantiers. Pour ça, il nous faut trois factures de vos derniers chantiers,
> et vingt minutes cette semaine pour les documenter avec vous. »

Noter séparément la réponse à l'oral (niveau 2 possible) et **ce qui se passe
réellement sous 7 jours** (niveau 3). Seul le second compte dans la décision.
Un entretien où l'action est engagée (`action_engagee`) mais jamais réalisée
(`action_realisee_le` reste vide) est un niveau 2, pas un niveau 3 — la
distinction est structurelle dans `EntretienH1`/`EntretienH2`, pas laissée à
l'interprétation de qui remplit la fiche.

---

## 5. Consigner un entretien

Un entretien se sérialise en JSON via `terrain.entretien.Entretien` — voir
`terrain/gabarit-entretien.json` pour un exemple complet et généré (pas
écrit à la main), qui montre la forme attendue de chaque champ. En pratique :

```python
from datetime import date
from terrain.entretien import Entretien, EntretienH1, EntretienH2, ConstatH1, EvenementsH2

e = Entretien.nouveau("atelier-ferrand", "Atelier Ferrand", date.today())
e.h1 = EntretienH1(
    constats=[ConstatH1("absent des 3 premières réponses sur la requête type", "citation_audit", True)],
    audit_json="out/atelier-ferrand-audit.json",
)
e.h2 = EntretienH2(
    evenements=EvenementsH2(periode_jours=7, recues=12, repondues_moins_5min=2,
                             repondues_5_60min=4, repondues_plus_1h=3, sans_reponse=3,
                             necessitant_devis=8, qualifiees=6),
    type_repetitif_identifie="demandes de prix un week-end, jamais rappelées avant le lundi",
)
e.save(f"entretiens/{e.entreprise_id}.json")
```

`Entretien.nouveau()` tamponne automatiquement le hash du protocole en
vigueur (`PROTOCOLE_V2.hash()`). Un entretien reconstruit à la main sous un
hash différent sera rejeté à l'agrégation — voir §6.

Une fois les dix fichiers réunis dans un même dossier :

```bash
python3 -m terrain decision entretiens/
```

---

## 6. Le verdict : cinq issues, aucune laissée à l'interprétation

`terrain.decision.decide()` refuse d'agréger des entretiens qui ne portent pas
le hash du protocole attendu — un seuil modifié en cours de campagne casse le
calcul au lieu de s'y glisser silencieusement dans le résultat.

**H1 est confirmée** si, sur les dix entreprises, au moins 6 atteignent le
niveau 1, au moins 5 le niveau 2, **et** au moins 3 le niveau 3 — les trois
conditions ensemble, pas l'une ou l'autre.

**H2 est confirmée** selon la même règle, avec les mêmes seuils, appliquée à
ses propres niveaux 1/2/3.

| H1 | H2 | Issue | Conséquence |
|---|---|---|---|
| ✅ | ✅ | `tester_ensemble` | Le repositionnement « source de vérité + capacité d'action » est justifié. On construit dessus. |
| ✅ | ❌ | `explorer_representation` | Le produit reste centré sur la citation et la preuve (Noyau + Surfaces, déjà construits). La couche engageante temps réel reste basse priorité. |
| ❌ | ✅ | `explorer_action` | À reconsidérer en profondeur : le vrai besoin est peut-être un standard de réponse rapide, pas une couche de citation IA. Revoir le cœur du produit. |
| ❌ | ❌ | `abandonner` | Le métier ou la ville ne valide pas la thèse. Changer de secteur, ou remettre en cause la thèse elle-même. |
| — | — | `echantillon_insuffisant` | Moins de dix entretiens réunis : aucune décision n'est prise sur un échantillon incomplet. |

Ces cinq constantes vivent dans `terrain.decision` (`TESTER_ENSEMBLE`,
`EXPLORER_REPRESENTATION`, `EXPLORER_ACTION`, `ABANDONNER`,
`ECHANTILLON_INSUFFISANT`) — ce tableau en est la lecture humaine, pas une
règle parallèle qui pourrait diverger du code.

Un compte exactement au seuil déclenche un avertissement de « zone grise »
dans le verdict : un entretien de plus ou de moins ferait basculer la
décision, et ça doit rester visible plutôt que lu comme un résultat tranché.

---

## 7. Ce que ce protocole interdit explicitement entre les phases

**Ne pas construire le produit entre les phases 2 et 4** (terrain → preuve →
positionnement). L'instrument (ce document, le paquet `terrain`, les ajouts à
`citation_audit`) est le seul objet de travail avant que le verdict ne soit
rendu. Le repositionnement n'est écrit qu'après ce résultat, pas avant — et le
SaaS engageant (couche H2) n'est engagé que si `explorer_action` ou
`tester_ensemble` sort du verdict.

## 8. Ce que ce test ne remplace pas

Dix entretiens ne valident pas un marché, ils valident — ou invalident — une
hypothèse assez fort pour justifier ou non d'investir dans le repositionnement
et dans la couche engageante. Rien de plus.
