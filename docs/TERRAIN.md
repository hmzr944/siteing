# Le test terrain — l'hypothèse qui décide de tout

> Séquence retenue : **hypothèse → terrain → preuve → positionnement → produit.**
> Pas l'inverse. Ce document ne construit rien : il prépare dix conversations
> réelles, avec un seuil de décision fixé *avant* de les avoir eues.

---

## 1. Deux hypothèses, jamais mélangées

Le protocole initial les traitait ensemble. C'est le premier piège : elles
appellent deux produits différents, et une entreprise peut valider l'une sans
l'autre.

**H1 — Représentation.** L'entreprise est mal ou pas représentée dans ce que
disent Google et les moteurs de réponse IA à son sujet, et elle perd de la
demande à cause de ça. C'est ce que mesure déjà `citation_audit` (Part de
Citation, angles morts).

**H2 — Capacité d'action.** L'entreprise perd des demandes entrantes faute de
pouvoir répondre vite et précisément (prix, délai, disponibilité), et un
système qui répondrait à sa place aurait une valeur réelle. C'est la couche
« engageante » qu'on avait mise de côté, et que la lecture de Google qui
appelle directement les entreprises remet en question.

Chaque entretien doit pouvoir répondre séparément aux deux, parce que le
produit à construire n'est pas le même selon celle qui est validée.

---

## 2. Sélection des dix entreprises

Un seul secteur, une seule ville — cohérent avec le choix déjà fait
(rénovation, Bordeaux) — pour ne pas ajouter une variable de plus à un test
qui en a déjà deux.

**Ne pas prendre au hasard.** Deux biais à éviter :
- des entreprises qui ne reçoivent presque aucune demande en ligne
  aujourd'hui : elles ne pourront rien dire sur de la demande perdue, le test
  serait aveugle ;
- uniquement des entreprises déjà convaincues du sujet (via un réseau
  affinitaire) : ça gonflerait artificiellement le taux de validation.

Cible : des entreprises qui reçoivent déjà un flux réel de demandes (devis,
appels, messages), sans présager de leur maturité numérique.

**Ce panel n'est pas celui de `markets/renovation-bordeaux.json`** — celui-là
sert à mesurer la citation, ses entités sont fictives. Les dix entretiens
demandent de vrais contacts (réseau personnel, chambre de métiers, CAPEB,
recommandations).

---

## 3. Le déroulé d'un entretien (20 minutes maximum)

### Étape 1 — La mesure, pas la promesse

Ouvrir par une donnée, jamais par une idée. Lancer l'audit en direct sur le
nom réel de l'entreprise et sa zone, montrer l'écran :

```bash
export ANTHROPIC_API_KEY=...
python3 -m citation_audit audit markets/<entreprise-reelle>.json \
    --provider anthropic:claude-sonnet-5 --provider anthropic:claude-opus-5 \
    --out out/
```

Il faut un fichier de marché minimal pour l'entreprise interrogée et 2-3
concurrents locaux nommés (voir `markets/plombier-bordeaux.json` comme
gabarit). C'est reproductible pour chacune des dix, en amont ou sur place.

Ce que l'entretien observe ici n'est pas ce que dit l'artisan : c'est sa
**réaction** face à un fait qu'il n'a pas produit lui-même. C'est la mesure de
H1, en direct, pas déclarative.

### Étape 2 — H2, en comptant, pas en évaluant

Questions dans cet ordre, quantitatives avant qualitatives :

1. « Sur une semaine normale, tous canaux confondus, combien de personnes vous
   contactent pour un devis ou une question ? » — si possible, ouvrir le
   téléphone ensemble et compter les 7 derniers jours plutôt que de demander
   une estimation.
2. « Combien vous rappelez dans les 24h ? Dans les 3 jours ? Combien ne sont
   jamais rappelées ? »
3. « Qu'est-ce qui fait qu'une demande traîne ou tombe à l'eau ? » (laisser
   venir : pas eu le temps, en chantier, prix pas clair, dispo incertaine…)
4. « Les questions qu'on vous pose reviennent souvent les mêmes ? Lesquelles ? »
5. « Un dimanche soir, quelqu'un demande un prix ou une dispo : il se passe
   quoi ? »
6. « Un exemple récent où vous pensez avoir perdu un chantier parce que la
   réponse est arrivée trop tard ou pas du tout ? »

La question 6 est la plus importante : un exemple concret et daté vaut plus
que dix évaluations abstraites.

### Étape 3 — L'engagement révélé, pas déclaré

Ne jamais demander « seriez-vous prêt à payer ». Proposer un échange concret :

> « On vous construit gratuitement ce dossier [montrer `noyaux/atelier-ferrand.json`
> rendu, ou la Page de Vérité] en échange de trois factures de vos derniers
> chantiers et de vingt minutes cette semaine pour les documenter avec vous. »

Noter deux choses séparément : la réponse à l'oral, et **ce qui se passe
réellement sous 7 jours** (rendez-vous tenu, factures envoyées). Seule la
seconde compte dans la décision.

---

## 4. Grille de consignation (une ligne par entreprise)

| # | Entreprise | Cité sur son marché ? (H1) | Réaction à l'audit | Demandes/semaine | Non rappelées sous 3j | Exemple de perte concrète (o/n) | A accepté l'échange à l'oral | A vraiment envoyé les factures sous 7j |
|---|---|---|---|---|---|---|---|---|
| 1 | | | | | | | | |
| … | | | | | | | | |

Remplir en une phrase courte par colonne, jamais une note narrative libre : le
but est de pouvoir comparer les dix lignes d'un coup d'œil, pas de relire dix
comptes rendus.

---

## 5. Seuils de décision — fixés avant le premier entretien

**H1 confirmée** si au moins 7/10 entreprises sont absentes ou mal citées sur
leur propre marché lors de l'audit en direct, **et** au moins 5/10 montrent une
réaction de surprise ou d'inquiétude authentique (pas polie) en le voyant.

**H2 confirmée** si au moins 6/10 rapportent un délai de rappel supérieur à 24h
sur une part significative des demandes, **ou** décrivent un exemple concret et
daté de chantier perdu pour ce motif, **et** au moins 5/10 acceptent
réellement l'échange (factures envoyées sous 7 jours, pas seulement un oui à
l'oral).

| Résultat | Conséquence |
|---|---|
| **H1 et H2 confirmées** | Le repositionnement « source de vérité + capacité d'action » est justifié. On construit dessus. |
| **H1 seule confirmée** | Le produit reste centré sur la citation et la preuve (ce qui est déjà construit : Noyau + Surfaces). La couche engageante temps réel reste basse priorité. |
| **H2 seule confirmée** | À reconsidérer en profondeur : le vrai besoin est peut-être un standard de réponse rapide (secrétariat augmenté), pas une couche de citation IA. Revoir le cœur du produit avant de continuer. |
| **Ni l'une ni l'autre** | Le métier ou la ville ne valide pas l'hypothèse. Changer de secteur, ou remettre en cause la thèse elle-même. |

Le seuil d'engagement révélé (factures envoyées sous 7 jours) est
volontairement le plus dur des quatre : c'est celui qui protège contre l'envie
de lire dans dix conversations sympathiques ce qu'on avait envie d'y trouver.

---

## 6. Ce que ce test ne remplace pas

Dix entretiens ne valident pas un marché, ils valident — ou invalident — une
hypothèse assez fort pour justifier ou non d'investir dans le repositionnement
et dans la couche engageante. Le repositionnement (sortir du mot « AEO »,
formuler « source de vérité + capacité d'action ») n'est écrit qu'après ce
résultat, pas avant.
