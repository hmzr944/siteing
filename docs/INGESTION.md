# L'ingestion — comment ne pas laisser un LLM inventer des faits

```bash
python3 -m ingestion --fichier messages-demo.txt --date 2026-08-16
python3 -m ingestion "j'ai fini la salle de bain rue Rode, 6 m2, facturé 11 400 euros" --llm
```

---

## 1. La réponse à la question difficile

Le problème posé : nos règles sont strictes (vocabulaire géographique contrôlé,
bandes de tailles, refus des ambiguïtés) et les modèles de langue sont de mauvais
élèves dès qu'on leur demande de respecter une énumération fermée.

**La réponse est de ne pas le leur demander.**

| Étape | Qui | Ce qu'il produit |
|---|---|---|
| 1 | le modèle | des **fragments verbatim** typés (`lieu`, `montant`, `nature`…) |
| 2 | le code | la traduction en **codes contrôlés**, avec refus de l'ambigu |
| 3 | le code | une **question** pour ce qui manque, classée par ce qu'elle débloque |

Le contrat imposé au modèle est volontairement pauvre : *« recopie des morceaux
exacts du texte et dis de quoi ils parlent »*. Il n'y a **aucun vocabulaire fermé
à respecter**, donc l'essentiel du risque d'hallucination disparaît par
construction. Ce n'est pas de la méfiance, c'est de la division du travail : un
modèle est excellent pour repérer « y'en a eu pour 12 plaques » dans un flot de
parole spontanée, et un `re.compile` est excellent pour garantir une sortie dans
une énumération. On donne à chacun ce qu'il sait faire.

## 2. Le garde-fou qui rend une hallucination inoffensive

`verbatim_only()` jette tout fragment qui n'apparaît pas **mot pour mot** dans le
message d'origine, avant toute résolution :

```python
verbatim_only("j'ai fini la rénovation rue Rode", [
    {"kind": "nature", "text": "salle de bain"},   # inventé  -> jeté
    {"kind": "lieu",   "text": "rue Rode"},        # présent  -> gardé
])
```

Un modèle qui inventerait une nature de chantier ne peut pas produire un fait :
son fragment n'existe plus quand les résolveurs entrent en jeu.

## 3. Le piège métier, et pourquoi il justifie l'architecture

Ton exemple : *« y'en a eu pour 12 plaques »* vaut **12 000 €**. Mais dans le
bâtiment, **une plaque est aussi une plaque de plâtre** :

```
"y'en a eu pour 12 plaques"        ->  12 000 €
"j'ai posé 12 plaques ce matin"    ->  REFUS: unité d'argot sans marqueur monétaire
```

Un modèle à qui on demanderait « donne le budget » aurait sorti 12 000 € dans les
deux cas, avec assurance. Le résolveur exige un **marqueur monétaire** dans la
phrase (`y'en a eu pour`, `facturé`, `devis`, `ça a coûté`, `€`…) et refuse
sinon. C'est le meilleur argument pour la séparation des rôles que je puisse
donner.

## 4. Ce que le système fait de ton message exact

```
> Ouais j'ai fini la rénovation rue Notre-Dame, y'en a eu pour 12 plaques,
  on a mis 4 jours, c'était galère

  fragments : montant='12 plaques', duree='4 jours', nature='renovation',
              lieu='rue Notre-Dame'
  compris   : aux Chartrons, 12 000 €, 4 jours
  refus     : nature — un chantier est évoqué sans dire lequel: terme trop général
  statut    : incomplet
  question  : Vous avez parlé d'un chantier sans préciser lequel. Salle de bain,
              cuisine, rénovation complète, isolation, ravalement, verrière ?
              débloque l'enregistrement du chantier (bloquant)
```

**« rénovation » ne dit pas ce qui a été rénové.** Déduire « salle de bain » d'un
budget de 12 000 € et de 4 jours serait une **inférence**, pas une extraction, et
elle finirait publiée comme un fait sur une page que les moteurs citent. Le
système le refuse et pose la question.

`rue Notre-Dame` devient `chartrons` parce que le **référentiel** porte les voies
en alias. C'est un quartier pour qui connaît Bordeaux, et rien du tout pour un
programme : c'est au référentiel de le savoir, jamais au modèle de le deviner.

## 5. Une seule question par échange

Le produit s'est vendu sur une friction nulle. Chaque question entame cette
promesse, donc la boucle de confirmation est un **budget rare** :
`next_question()` rend **une** question, celle qui débloque le plus.

L'ordre de priorité suit ce que le champ débloque, pas l'ordre du formulaire :

| Champ | Débloque | Bloquant |
|---|---|---|
| `nature` | l'enregistrement du chantier | oui |
| `territoire` | la preuve d'implantation | oui |
| `budget_eur` | le budget constaté de la catégorie | oui |
| `size` | la comparabilité avec les autres chantiers | non |
| `completed_on` | la fraîcheur de la preuve | non |

Un refus motivé remplace la question générique par une question **ciblée** :
« vous avez parlé d'un chantier sans préciser lequel » plutôt que « quel type de
chantier ? ».

## 6. Rien n'est jamais écrit dans le Noyau

L'ingestion produit un **candidat**, pas un chantier. Chaque champ porte son
fragment d'origine, sa confiance et, s'il a échoué, le motif du refus. Le message
brut est conservé. Une donnée fausse est donc toujours remontable à ce qui l'a
produite.

`to_chantier()` **lève** si un champ bloquant manque : on ne peut pas fabriquer
un chantier incomplet par accident.

Et la provenance est `vocal`, donc **non documentée** : un chantier raconté prouve
une intervention mais n'entre dans **aucun budget publié**. Un budget est une
donnée que l'entreprise engage, elle ne peut pas reposer sur un souvenir. La
facture viendra plus tard, et c'est une ligne du Plan de Travail.

## 7. Deux extracteurs, un contrat

`HeuristicExtractor` — sans réseau ni modèle. Il sert de démonstration, de repli
quand l'appel échoue, et surtout d'**oracle de test** : les résolveurs sont
vérifiés indépendamment de tout modèle. Les 485 tests du dépôt tournent hors
ligne (à l'exception de `tools/verifie_siren.py`, un smoke-test volontairement
tenu hors de la suite — `docs/VERIFICATION.md`).

`LLMExtractor` — sortie structurée typée, avec `tool_choice` forcé et
vérification du verbatim en sortie. Repli automatique sur l'heuristique en cas
d'échec réseau.

## 8. Ce qui reste

1. **La transcription.** On part d'un texte déjà transcrit. Le passage audio vers
   texte sur un chantier bruyant, avec accent et jargon, est un problème distinct
   et non traité ici.
2. **Les pièces.** Passer un chantier de `vocal` à `facture` suppose de recevoir
   et contrôler la pièce. C'est le maillon qui débloque les budgets, et c'est le
   prochain goulot.

~~Le dialogue~~ — fait (section 9). ~~Un seul métier~~ — fait aussi : le
vocabulaire de nature (`parse_nature`) ne connaît plus la rénovation en
particulier, il vient de la fusion de `metiers/*.json`
(`noyau.catalogue.merge_keywords`). Ajouter un métier à l'ingestion demande un
fichier JSON, jamais une ligne de ce paquet. Un mot-clé disputé par deux
métiers (« salle d'eau » en rénovation et en plomberie) est retiré de l'index
plutôt qu'arbitré au hasard — la même règle que pour les codes de nature dans
`noyau.catalogue.merge()`, en plus tolérant : une ambiguïté de langage entre
métiers est plausible, elle ne doit pas empêcher les catalogues de charger.

---

## 9. La boucle de dialogue

```bash
python3 tools/demo_dialogue.py
```

### Ce que le dialogue apporte de plus que la collecte : il désambiguïse

C'est la meilleure trouvaille de cette étape. « 12 plaques » seul est **refusé**,
parce qu'une plaque est aussi une plaque de plâtre. Mais en réponse à la question
*« le chantier a été facturé combien ? »*, c'est un montant : **la question a
établi le contexte monétaire.**

```python
parse_montant("12 plaques")                        # refus
resolve_field("budget_eur", "12 plaques", …)       # 12 000 €
```

Le dialogue ne sert donc pas seulement à remplir des trous. Il fournit au
résolveur le contexte que le message isolé n'avait pas.

### Le routage, par densité d'information

Un message entrant est-il une réponse, ou un nouveau chantier ? La règle qui
marche n'est pas une liste de tournures, c'est de **compter les faits
indépendants** que le message porte à lui seul :

- **un seul fait** → c'est une réponse à la question en cours ;
- **deux ou plus** → c'est une nouvelle entrée.

Sans ce test, *« j'ai livré la cuisine place Nansouty, 14 m2, ça a coûté 22
plaques »* se faisait absorber comme simple réponse au chantier précédent, et
**les deux chantiers fusionnaient**. C'était le bug le plus grave de la première
version.

### Rien ne se perd

Quand une nouvelle entrée interrompt une question sans réponse, le candidat
précédent est **garé** avec tout ce qui avait déjà été résolu pour lui, et il
remonte au plan de travail. Un chantier annoncé puis abandonné en cours de
conversation ne disparaît jamais.

### Trois pièges de la machine à états, et leurs garde-fous

**Le candidat fantôme.** Le résolveur de date rend *toujours* une valeur, le jour
de l'énoncé par défaut. Sans précaution, « ok merci » créait donc un chantier
avec une date et rien d'autre. Un candidat dont le seul champ est une date déduite
ne porte aucune information : il est écarté.

**L'amendement.** « 6 m2 » envoyé juste après un enregistrement ne signale pas un
nouveau chantier, c'est une précision sur celui qu'on vient d'enregistrer. Idem
pour une date : mais une date **énoncée** corrige une date **déduite**, et une
date déduite ne corrige rien, sinon n'importe quel message passerait pour une
correction.

**La péremption.** Une question sans réponse depuis plus de sept jours ne peut
plus être répondue : « salle de bain » hors contexte ne désigne plus rien. Le
candidat est garé et la conversation repart.

### Le pont vers la pièce justificative

C'est le canal de collecte. À l'enregistrement :

> C'est enregistré : Rénovation de salle de bain, aux Chartrons, 12 000 €, 4 jours.
> Pour que son budget soit publié et compte dans votre visibilité, il me faut la
> facture. Envoyez-la ici, une photo suffit.

Puis, à la réception d'une référence :

> Facture F2026-118 rattachée au chantier. Son budget entre maintenant dans vos
> budgets constatés.

La référence n'est reconnue que si le message porte un indice de pièce
(« facture », « devis ») : un numéro nu ne suffit pas. Et tant que la pièce
manque, le chantier apparaît au plan de travail avec sa conséquence exacte : *il
prouve une intervention mais n'entre dans aucun budget publié.*

**Limite assumée** : recevoir une facture référencée rend le chantier
« documenté » au sens du Noyau. Le contrôle du montant *contre* la pièce reste un
travail distinct, non construit.
