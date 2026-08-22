# Méthode de mesure de la Part de Citation

> Document destiné à être **public**. Une mesure vendue dont la méthode est secrète
> n'est pas un audit, c'est une opinion facturée. La publier est ce qui la rend
> contestable — donc crédible.

## 1. Ce que l'on mesure, et ce que l'on ne mesure pas

**On mesure** ce que des moteurs de réponse équipés de recherche web restituent,
aujourd'hui, quand on leur pose les questions d'achat réelles d'un marché donné :
quelles entreprises sont nommées, dans quel ordre, et lesquelles sont utilisées
comme sources.

**On ne mesure pas**, et personne ne peut mesurer :

- un classement interne d'un éditeur (aucun n'expose de position) ;
- une garantie de figurer dans une réponse future ;
- le volume réel de trafic issu des moteurs de réponse, que les éditeurs
  n'attribuent pas de façon fiable.

Cette frontière est contractuelle : nous vendons une **Part de Citation mesurée**
et son évolution. Toute promesse de « position garantie chez un éditeur » est un
engagement intenable, et nous refusons de la formuler.

## 2. Le panier de questions

Chaque marché est défini par sa catégorie, sa zone, ses services, ses contraintes
d'achat et la liste des entreprises suivies. De cette définition, le moteur dérive
un panier de questions réparties en six familles :

| Famille | Ce que cherche l'acheteur | Poids |
|---|---|---|
| Découverte | « quel {métier} choisir à {ville} » | 1,0 |
| Comparaison | « le meilleur », « top 3 », « la meilleure réputation » | 1,2 |
| Contrainte | urgence, horaires, budget, certification | 1,1 |
| Problème | un besoin précis et nommé | 1,0 |
| Transactionnel | devis, commande, intervention datée | 1,3 |
| Vérification | réputation d'une marque explicitement nommée | 0,8 |

Les poids traduisent l'intention commerciale : être cité sur « je veux un devis
pour X cette semaine » ne vaut pas la même chose qu'être cité sur « c'est quoi un
X ».

**Le panier est figé.** Il porte une empreinte (`basket_version`) calculée sur
tout ce qui influence sa composition. Deux relevés de versions différentes ne
sont pas comparables, et le rapport le signale. C'est la propriété la plus
importante de la méthode : un audit dont le panel change à chaque exécution ne
mesure rien et ne peut pas être opposé au client.

L'échantillonnage à l'intérieur de chaque famille est pseudo-aléatoire mais
déterministe (tri par identifiant stable ancré sur l'identifiant du marché) :
reproductible, borné en coût, et non choisi à la main — donc non orientable en
faveur d'un client.

## 3. La détection des entreprises

Une entreprise est comptée comme citée si l'un de ces trois cas est vérifié :

1. **nom** — correspondance de sa raison sociale ;
2. **alias** — correspondance d'une variante déclarée ;
3. **domaine** — son domaine figure dans les sources citées par le moteur.

Avant comparaison, les textes sont normalisés : accents retirés, casse aplatie,
ponctuation supprimée, formes juridiques ignorées (`SARL`, `SAS`, `Ets`,
`Société`, `Groupe`…).

La détection est **volontairement avare**, parce qu'un faux positif dans un audit
facturé détruit la crédibilité de la mesure entière :

- correspondance sur **frontières de mots** uniquement — « Hydrolys » n'est pas
  trouvé dans « hydrolyse » ;
- **rejet des noms génériques** — dans un marché « plombier / Bordeaux », une
  entreprise nommée « Plomberie Bordeaux » n'est pas comptée sur la seule
  occurrence de ces mots, qui apparaissent dans toutes les réponses ;
- **rejet des alias trop courts** (moins de 4 caractères significatifs) ;
- exception explicite : une expression multi-mots longue et improbable (« Les
  Compagnons de la Garonne ») est acceptée même sans jeton rare.

Le **rang** est l'ordre d'apparition des entreprises distinctes dans la réponse.
Une entreprise dont le domaine figure dans les sources citées passe devant les
mentions en prose : le moteur ne se contente pas de la nommer, il s'appuie sur
elle.

## 4. Les trois indicateurs

**Taux de Présence** — proportion des questions du panier où l'entreprise
apparaît, quel que soit son rang. Indicateur non pondéré, immédiatement
compréhensible.

**Part de Citation** — indicateur du contrat. Pour chaque mention :

```
valeur = poids_de_la_famille × 1 / log2(1 + rang)
```

soit 1,00 pour le premier cité, 0,63 pour le deuxième, 0,50 pour le troisième :
la même décote logarithmique que le DCG en recherche d'information. La Part de
Citation d'une entreprise est la somme de ses valeurs divisée par la somme des
valeurs de toutes les entreprises suivies. Les parts somment donc à 100 %.

**Angles morts** — questions où l'entreprise est absente alors qu'au moins un
concurrent suivi est cité, ordonnées par poids commercial décroissant. Une
question où *personne* n'est cité n'est pas un angle mort : c'est une opportunité
ouverte, comptée séparément.

## 5. L'écart à la part équitable

Le rapport traduit l'écart de citation en euros. Le piège serait de valoriser
toute l'intention du marché où le client est absent : aucune entreprise ne
capterait 100 % de son marché, et un chiffre gonflé détruit exactement la
crédibilité qui fait la valeur du rapport.

On mesure donc l'écart à la **part équitable** — ce qu'un acteur parmi *n*
capterait si tous étaient à égalité, soit `1/n` par défaut :

```
écart mensuel = volume d'intention × (part équitable − part captée)
                × taux de transformation × valeur moyenne d'une affaire
```

Les quatre entrées sont affichées dans le rapport, et le résultat est plancher à
zéro : une entreprise qui dépasse sa part équitable n'a aucune perte à réclamer.
C'est un plancher défendable, pas un plafond flatteur.

## 6. Niveaux de preuve

Tout relevé porte un niveau, et le niveau d'un audit est celui de son **maillon
le plus faible** :

| Niveau | Source | Utilisable avec un client ? |
|---|---|---|
| `mesure` | interrogation réelle des moteurs | oui |
| `rejeu` | réponses archivées rejouées | oui, en contestation |
| `simulation` | moteur simulé hors ligne | **jamais** |

Un rapport simulé, ou reposant sur moins de 20 questions exploitables, porte un
bandeau « ne pas remettre au client » et se déclare non présentable. Ce garde-fou
est dans le code, pas dans une consigne : `AuditResult.is_presentable`.

Un relevé contractuel exige **au moins deux moteurs**. Un seul moteur mesure un
éditeur, pas le marché des moteurs de réponse ; le rapport le signale.

## 7. Archivage et contestation

Toutes les réponses brutes sont archivées avec leur horodatage
(`--archive`). Tout chiffre d'un rapport est reconductible au corpus exact qui l'a
produit. Un client qui contesterait une mesure est confronté aux réponses
elles-mêmes, pas à notre parole.

## 8. Limites connues

Nous les publions parce que les cacher serait le seul vrai risque.

1. **Variance des moteurs.** Une même question peut recevoir des réponses
   différentes à quelques minutes d'intervalle. La mesure n'a de sens qu'agrégée
   sur un panier large ; un prompt isolé ne prouve rien. C'est pourquoi le
   minimum est fixé à 20 questions exploitables et la cible à 35+.
2. **Non-personnalisation.** Nous mesurons des réponses hors session, sans
   historique utilisateur ni géolocalisation fine. Un utilisateur réel peut
   obtenir autre chose.
3. **Approximation d'éditeur.** Interroger un modèle avec recherche web activée
   approche le comportement d'un moteur de réponse sans être identique au produit
   grand public d'un éditeur. La méthode mesure une famille de comportements, pas
   une interface précise.
4. **Dépendance de plateforme.** Les éditeurs peuvent changer leurs mécanismes de
   sourçage sans préavis. C'est le risque structurel du modèle, et il est assumé
   explicitement dans `docs/PLAN.md`.
5. **Périmètre concurrentiel déclaré.** Les parts sont calculées sur les
   entreprises suivies. Ajouter un concurrent modifie les parts de tous : c'est
   pourquoi la liste fait partie de l'empreinte du panier.

## 9. Reproduire une mesure

```bash
# le panier figé d'un marché
python3 -m citation_audit basket markets/plombier-bordeaux.json

# relevé réel, deux moteurs, avec archivage
export ANTHROPIC_API_KEY=...
python3 -m citation_audit audit markets/plombier-bordeaux.json \
    --provider anthropic:claude-sonnet-5 \
    --provider anthropic:claude-opus-5 \
    --archive archives/ --out out/

# rejeu d'un corpus archivé: doit redonner exactement les mêmes chiffres
python3 -m citation_audit audit markets/plombier-bordeaux.json \
    --provider fixture:archives/plombier-bordeaux-anthropic-claude-sonnet-5.json
```
