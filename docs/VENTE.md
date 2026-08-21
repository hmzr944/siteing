# Acquisition — le playbook

> Règle unique, dont tout le reste découle : **on ne vend rien, on montre une
> perte.** Le dirigeant qui découvre le nom de son concurrent dans une réponse où
> il n'existe pas a déjà fait le travail de conviction à notre place. Chaque fois
> que le discours dérive vers ce que nous faisons plutôt que vers ce qu'il perd,
> le taux s'effondre.

Ce playbook vend le palier **Exclusif** (`docs/PLAN.md` §3) : c'est le seul
qui justifie un cycle sortant à 2 400 € de CAC. Le palier Gratuit et le
Forfait à 19 €/mois se vendent en self-serve, sans appel commercial —
détail et raison dans `docs/ECONOMIE.md` §0.

## 1. L'Audit d'Invisibilité, arme principale

Panier réduit à 12 questions, un seul moteur, rendu vidéo de 90 secondes. Coût
cible **9 €**. Construit et testé (`citation_audit/prospection.py`, `Market.prospecting_basket()`,
12 tests) :

```bash
# fichier de marché minimal pour l'entreprise réellement démarchée
python3 -m citation_audit amorce "Nom réel" "catégorie" "Ville" \
    --concurrent "Concurrent 1" --concurrent "Concurrent 2" \
    --out markets/prospect.json

# l'audit d'invisibilité + l'e-mail jour 0, rempli avec le vrai concurrent cité
python3 -m citation_audit prospection markets/prospect.json \
    --provider anthropic:claude-sonnet-5 --email \
    --prenom "Marc" --lien "https://..." --signature "Julien"
```

Le panier réduit est un **sous-ensemble** du panier complet (mêmes gabarits,
mêmes identifiants stables), jamais une liste distincte — ce qui rend le
relevé de prospection directement comparable au relevé contractuel qui
suivra. Il est aussi, par construction, **structurellement en dessous du
seuil de présentabilité** (`score.MIN_PROMPTS = 20`) : `AuditResult.is_presentable`
y est toujours faux. Ce n'est pas un oubli, c'est le garde-fou qui rend
impossible de confondre ce relevé avec celui qu'on facture — voir §
« deux garde-fous non négociables » ci-dessous, maintenant vérifiés par le
code et non plus seulement par la discipline commerciale.

L'e-mail jour 0 (§2) se génère automatiquement, rempli avec le concurrent
**réellement** le plus cité sur ce prospect précis — jamais un nom
générique. `email_jour_0()` refuse d'écrire l'e-mail si aucun concurrent
n'a été cité à la place du prospect : pas de mensonge par construction.

Ce qui apparaît à l'écran :

1. on tape une question d'achat de **son** marché ;
2. la réponse nomme deux ou trois de ses concurrents ;
3. son entreprise n'y est pas ;
4. on répète sur une deuxième question, puis une troisième ;
5. plein écran : `Taux de Présence — 0 %` sur les 12 questions testées.

Aucune voix off commerciale. On énonce ce qu'on fait et on se taît. La séquence
n'a pas besoin d'être commentée.

**Deux garde-fous non négociables.** L'audit envoyé nomme les concurrents dans un
document adressé au seul dirigeant concerné — jamais publiquement, jamais avec un
jugement de valeur sur eux : nous rapportons ce que le moteur dit, nous n'évaluons
personne. Et un audit de prospection tourne sur un panier réduit : il porte donc
la mention « relevé indicatif, 12 questions » et ne se présente jamais comme le
relevé contractuel. Un prospect qui compare les deux chiffres et trouve un écart
inexpliqué est perdu définitivement.

## 2. La séquence sortante

| Jour | Canal | Contenu | Objectif |
|---|---|---|---|
| 0 | e-mail | Objet : `Vous n'apparaissez pas` — 4 lignes + lien vidéo | ouvrir la vidéo |
| 2 | LinkedIn | demande de contact sans message | présence |
| 4 | e-mail | la question exacte + le nom du concurrent cité | forcer la réaction |
| 7 | téléphone | référence à la vidéo, une seule question | rendez-vous |
| 11 | e-mail | rareté datée du créneau | décision |
| 18 | e-mail | clôture propre, porte laissée ouverte | libérer le pipeline |

**E-mail jour 0**

> Objet : Vous n'apparaissez pas
>
> Bonjour {prénom},
>
> J'ai posé 12 questions d'achat de votre marché à ChatGPT et Gemini — le genre de
> questions que vos clients posent avant d'appeler. {Concurrent} est cité 7 fois.
> {Entreprise} : zéro.
>
> 90 secondes, sans commentaire : {lien}
>
> {signature}

Pas de « j'espère que vous allez bien », pas de présentation de notre société, pas
de proposition de rendez-vous dans le premier message. Le seul appel à l'action
est le lien.

**E-mail jour 4** — la question in extenso, la réponse copiée, le nom du
concurrent en gras, une ligne : *« C'est la question qui précède un devis dans
votre métier. Aujourd'hui elle ne mène pas chez vous. »*

**Téléphone jour 7** — une seule question, puis on écoute :

> « Vous avez vu la vidéo. Ma question est simple : quand un client demande à une
> IA qui appeler dans votre métier à {ville}, vous trouvez normal que ce soit
> {concurrent} qui sorte ? »

## 3. Les objections, et la réponse

**« Ça ne m'amène aucun client, l'IA. »**
« Aujourd'hui, non. C'est exactement le moment où le créneau est encore libre.
Dans dix-huit mois il sera occupé par celui qui s'y est mis maintenant — c'est le
même film que le référencement en 2005, et vous connaissez la fin. Je ne vous
demande pas de me croire : je vous propose de mesurer tous les mois, et vous
regardez la courbe. »

**« J'ai déjà refait mon site avec une IA. »**
« Très bien, et ça ne change rien à ce relevé — vous l'avez vu. Un site s'adresse
à un humain qui vous a déjà trouvé. Nous travaillons sur ce qui décide qu'on vous
trouve. Ce sont deux problèmes différents, et vous n'avez résolu que le premier. »

**« C'est cher pour ce que c'est. »**
Ne jamais défendre le prix. Ramener à la comparaison de nature : « Votre
concurrent occupe une place que vous n'occupez pas. Ce n'est pas un abonnement
logiciel, c'est un emplacement — et il n'y en a qu'un par métier et par ville. Si
l'écart mesuré sur votre marché est de {montant}/an, la question n'est pas le
prix, c'est de savoir qui l'occupe l'an prochain. »

**« Vous garantissez que je serai cité ? »**
La réponse est **non**, et c'est un argument de vente :
« Non, et personne ne peut le garantir — méfiez-vous de qui vous le promettra. Ce
que je garantis, c'est une mesure reproductible, archivée et contestable, et un
travail dont vous voyez l'effet sur la courbe chaque mois. Notre méthode est
publiée, limites comprises. »

**« Je vais réfléchir. »**
« Bien sûr. Une seule précision utile : le créneau {catégorie} — {zone} est
ouvert. Le jour où quelqu'un le prend, je ne peux plus vous le proposer, parce que
je ne peux pas vendre la même place deux fois. Je vous rappelle {date}. »

## 4. Les canaux, par rendement décroissant

1. **Classements sectoriels publiés.** « Les 50 entreprises les plus citées par
   l'IA dans le BTP à Lyon. » Un classement agrégé et méthodologiquement défendable
   crée le marché : les absents appellent. Ne jamais publier de note nominative
   dépréciative — le classement dit qui est cité, pas qui est mauvais.
2. **Prescripteurs.** Experts-comptables, fédérations professionnelles,
   franchiseurs, réseaux d'affaires. Un accord porte le message d'urgence à des
   centaines d'entreprises d'un coup, avec la crédibilité de l'émetteur. C'est le
   canal qui divise le CAC par trois — à travailler dès le premier trimestre, pas
   quand le sortant s'essouffle.
3. **Sortant direct** par grappe géographique et sectorielle. Densité avant
   échelle : une ville, un métier, jusqu'à saturation. Un audit est infiniment
   plus convaincant quand le prospect reconnaît les noms cités.
4. **Recommandation par créneau adjacent.** Un client Exclusif n'a aucun intérêt à
   nous recommander à son concurrent — mais tout intérêt à nous recommander à un
   métier complémentaire de sa zone. C'est le seul mécanisme de recommandation
   compatible avec l'exclusivité, et il faut le solliciter explicitement.

## 5. Ce qu'on ne fait pas

- Pas de rendez-vous de « découverte » avant que la vidéo soit vue. Le relevé fait
  la qualification ; un rendez-vous à froid consomme le temps commercial qui porte
  le CAC.
- Pas de démonstration produit. Le prospect n'achète pas une interface, il achète
  une place. Montrer le tableau de bord déplace la conversation vers la
  fonctionnalité, terrain où les générateurs IA gagnent.
- Pas de remise. Une remise sur un loyer de position détruit la crédibilité de la
  rareté. Si le prix bloque, on descend de palier — jamais de prix.
- Pas de comparaison avec les générateurs de sites. Se comparer à eux, c'est
  accepter d'être rangé dans leur catégorie.

## 6. Les chiffres à tenir

| Indicateur | Cible | Sous ce seuil, on change quoi |
|---|---|---|
| Audit → vidéo vue | 35 % | l'objet et les 4 lignes, pas la vidéo |
| Vidéo vue → rendez-vous | 22 % | la question de l'appel du jour 7 |
| Audit → rendez-vous | ≥ 8 % | le ciblage, avant tout le reste |
| Rendez-vous → signature | 12 % | le palier proposé, pas l'argumentaire |
| Audits par vente | ≤ 100 | au-delà, le CAC passe 3 000 € et le modèle sous 5x |

Ces cinq chiffres se lisent ensemble : c'est le produit des trois premiers qui
pilote le CAC, et le CAC qui décide si l'entreprise existe.

## 7. L'appel du jour 7, par métier

La question du jour 7 (§2) ne change pas de forme, mais l'objection qui suit
n'est jamais la même selon le métier — parce que le rapport à la demande et
à la réputation n'est pas le même. Trois scripts, calés sur les métiers déjà
pris en charge de bout en bout (`metiers/*.json`) et sur les huit dossiers
réels générés dans `markets/prospection/`.

### Plombier

Métier de flux tendu : beaucoup sont déjà pleins, l'urgence fait le chiffre.
L'objection la plus probable n'est pas « ça ne marche pas », c'est **« j'ai
déjà trop de travail »**.

> « Vous avez vu la vidéo. Une question simple : un dimanche soir, une fuite,
> quelqu'un demande à ChatGPT quel plombier appeler à {ville} — c'est {concurrent}
> qui sort, pas vous. Ça vous est égal, ou vous préféreriez que ce soit vous
> qui décrochiez cet appel-là ? »

**« J'ai déjà trop de travail, je n'ai pas besoin de plus de clients. »**
« Ce n'est pas un problème de volume, c'est un problème de tri. Vous avez déjà
trop de demandes — la question, c'est qui reçoit les meilleures : les urgences
bien payées ou les dépannages au rabais. Aujourd'hui, c'est {concurrent} qui
choisit en premier, pas vous. »

**« Je n'ai pas le temps de m'occuper de ça. »**
« C'est justement pour ça que ça ne vous demande rien : pas de site à gérer,
pas de contenu à écrire. Vous racontez vos chantiers à l'oral, cinq minutes,
le reste se construit tout seul. »

### Rénovateur

Métier de gros montants et de cycle de décision long : le client compare, se
renseigne, regarde des photos avant-après avant d'appeler. C'est le métier où
la thèse de la dépossession porte le plus fort, parce que la recherche en
amont y est déjà un réflexe.

> « Vous avez vu la vidéo. Quelqu'un qui a un budget de 15 000 € pour sa
> rénovation ne choisit pas au hasard — il compare. Aujourd'hui, quand il
> demande à une IA, c'est {concurrent} qu'elle lui met en avant, avec des
> exemples de chantiers. Vous, rien. Ça vous semble normal pour un budget
> pareil ? »

**« J'ai déjà un site avec mon book de réalisations. »**
« Très bien, et ce book ne sert à rien tant qu'un humain ne l'a pas déjà
trouvé. Ce qu'on construit n'est pas un book de plus, c'est ce qui fait qu'une
IA cite vos chantiers réels — datés, chiffrés, localisés — au lieu de deviner.
Ce sont deux problèmes différents, vous n'avez résolu que celui de la
présentation, pas celui d'être trouvé en premier. »

**« Mes clients viennent du bouche-à-oreille, pas d'internet. »**
« Le bouche-à-oreille d'aujourd'hui, c'est aussi quelqu'un qui tape "qui
recommandes-tu pour une rénovation à {ville}" dans un moteur de réponse
avant même d'appeler les gens de son réseau. Le vôtre y est invisible ou
absent — c'est exactement ce que le relevé montre. »

### Expert-comptable / conseil

Métier de confiance et de déontologie, marché souvent saturé localement (une
dizaine de cabinets comparables dans une même ville n'est pas rare — voir
`markets/prospection/*-toulouse.json`). Public très à l'aise avec les
chiffres : l'argument qui porte le mieux est la mesure elle-même, pas
l'émotion.

> « Vous avez vu la vidéo. Un chiffre : sur {n} questions qu'un dirigeant se
> pose avant de choisir un cabinet, vous apparaissez sur {x}. {Concurrent}
> apparaît sur {y}. Ce n'est pas une opinion, c'est un relevé reproductible.
> Vous voulez qu'on le refasse ensemble sur le panier complet ? »

**« Je suis déjà référencé sur l'annuaire de l'Ordre. »**
« L'annuaire de l'Ordre répond à "cette personne a-t-elle le droit
d'exercer", pas à "lequel choisir". Une IA à qui on demande un cabinet ne va
pas consulter l'annuaire ordinal, elle répond avec ce qu'elle a déjà lu sur
vous — et le relevé montre ce qu'elle a lu, ou pas lu du tout. »

**« Mes clients viennent par recommandation, je n'ai pas besoin de ça. »**
« La recommandation reste la meilleure source — ça ne change pas. Ce qui
change, c'est qu'avant de rappeler la personne qui vous recommande, de plus
en plus de dirigeants vérifient d'abord ce qu'en dit une IA. Si elle cite un
confrère à votre place à ce moment-là, la recommandation ne suffit plus à
elle seule. »
