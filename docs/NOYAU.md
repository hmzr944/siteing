# Le Noyau — schéma de la donnée, quel que soit le métier

> C'est l'actif. Le rendu (site, flux, fiche) est une commodité de distribution ;
> ce qui ne se copie pas, c'est la mémoire accumulée et vérifiée de ce que
> l'entreprise a réellement fait.

```bash
python3 -m noyau noyaux/atelier-ferrand.json -r referentiels/bordeaux.json --json out/
```

---

## 1. La règle unique

**Seul ce qui franchit son seuil de preuve est publié vers la surface machine.**

Le reste reste visible par un humain, marqué comme non prouvé, et forme le **plan
de travail** du mois. Ce plan est la contrepartie visible de l'abonnement : un
Noyau constitué une fois se périme, et un Noyau sans manques est un Noyau qui a
cessé de croître.

Trois seuils, trois raisons, tous les trois configurables et tous les trois
testés :

| Seuil | Valeur | Pourquoi |
|---|---|---|
| Chantiers pour prouver un quartier | **3** | Un chantier isolé aux Chartrons ne fait pas de vous un spécialiste des Chartrons. Le publier comme tel serait fabriquer de la preuve. |
| Chantiers comparables pour un budget | **5** | En dessous, une médiane est du bruit, et un chiffre fragile publié avec assurance détruit la crédibilité qui fait toute la valeur. |
| Validité d'un attribut d'autorité | **date** | Une certification expirée n'est pas un attribut d'autorité. La date fait toute la différence. |

---

## 2. Impératif 1 : la preuve par l'hyper-local

Un chantier n'existe que s'il est localisé, et un moteur ne recommandera pas un
artisan « aux Chartrons » sans preuve d'intervention aux Chartrons.

### Le piège est la saisie libre

« Chartrons », « les Chartrons », « quartier des Chartrons », « Bordeaux
Chartrons » désignent le même endroit. Laissés tels quels, ils **fragmentent la
preuve en quatre tas dont aucun n'atteint le seuil de publication**. C'est le
défaut le plus coûteux possible : l'entreprise a la preuve, et le système ne la
voit pas.

Un territoire est donc une **entrée de vocabulaire contrôlé**, jamais une chaîne
saisie par un humain ni extraite par un modèle sans résolution :

```
Chartrons                                → chartrons
les chartrons                            → chartrons
quartier des Chartrons                   → chartrons
chantier rue Notre-Dame aux Chartrons    → chartrons
Bassins à flot                           → bacalan   (alias)
Paris                                    → non résolu
entre les Chartrons et Caudéran          → non résolu (ambigu)
```

Deux refus délibérés : une saisie **inconnue** et une saisie **ambiguë** rendent
`None` et remontent à l'humain. Deviner un territoire, ce serait fabriquer de la
preuve, ce qui est exactement le contraire du produit.

### Trois niveaux, et l'héritage

`quartier` → `commune` → `metropole`. Un chantier prouve son quartier **et tous
les territoires englobants** : intervenir aux Chartrons prouve qu'on intervient à
Bordeaux, jamais l'inverse.

La preuve se construit au niveau du **quartier**, parce que c'est le grain auquel
un acheteur se pose la question et celui auquel presque aucune entreprise n'est
citée aujourd'hui. C'est là que la première citation se gagnera.

### Formes locatives

Le rendu doit écrire « aux Chartrons », « à Talence », « à la Bastide », « au
Bouscat ». Une phrase publiée avec un article faux se lit comme une phrase
générée, et perd exactement la crédibilité qu'on cherche.

---

## 3. Impératif 2 : le budget constaté

C'est la donnée que les moteurs citent le plus volontiers, et la plus dangereuse
à publier. Trois règles.

### Un budget constaté est une distribution, pas un prix

« Rénovation complète SDB 6 m² = 11 500 € » à partir d'un chantier est une
anecdote déguisée en tarif. Ce qui est citable et défendable :

> Rénovation de salle de bain, 5 à 8 m² : budget médian constaté **11 550 €**,
> moitié des chantiers entre **10 600 €** et **12 575 €**, sur **6 chantiers
> facturés** depuis 2025.

Sont publiés : effectif, médiane, quartiles, min, max, période, et le prix
unitaire médian quand il a un sens.

### La comparabilité est la décision qui engage tout le reste

Une salle de bain de 4 m² et une de 20 m² ne se moyennent pas. Chaque nature de
chantier porte donc ses **bandes de taille**, et deux chantiers ne s'agrègent que
dans la même bande :

| Nature | Unité | Bandes |
|---|---|---|
| Salle de bain | m² | 0-5, 5-8, 8-12, 12+ |
| Cuisine | m² | 0-8, 8-14, 14+ |
| Rénovation globale | m² | 0-60, 60-100, 100-150, 150+ |
| Isolation par l'extérieur | m² | 0-80, 80-140, 140+ |
| Ravalement pierre de taille | m² | 0-60, 60-120, 120+ |
| Verrière d'atelier | ml | 0-2, 2-4, 4+ |

Sans bandes, le budget constaté serait une moyenne de choux et de carottes, c'est
à dire un chiffre faux publié avec assurance. Un test vérifie que les bornes ne se
recouvrent pas : une taille tombe dans exactement une bande.

Le **prix unitaire est supprimé là où il tromperait** : une verrière se compte à
la pièce, publier un prix au mètre linéaire y serait faux.

### Trois conditions cumulatives d'éligibilité

1. **Adossé à une pièce** (facture acquittée ou devis signé). Un chantier
   raconté à l'oral reste une preuve d'intervention mais n'entre dans aucun
   budget : un budget est une donnée que l'entreprise engage, elle ne peut pas
   reposer sur un souvenir.
2. **Comparable**, donc de taille connue.
3. **Pas trop ancien** : trois ans, au-delà le chantier ne reflète plus les prix
   pratiqués.

### Un budget constaté n'est jamais une offre

La phrase publiée dit « constaté sur N chantiers », jamais « à partir de X € ».
Entre les deux il y a la différence entre un fait et un engagement commercial, et
c'est une différence juridique. Un test l'interdit explicitement.

Une **fourchette trop large** (écart interquartile supérieur à 1,2 fois la
médiane) est signalée : elle indique que la bande mélange des ouvrages trop
différents, et une fourchette qui n'informe pas doit le dire.

---

## 4. Impératif 3 : les attributs d'autorité

Les certifications réutilisent le modèle d'affirmation vérifiée du Dossier de
Vérité : valeur, pièce référencée, organisme contrôleur, date de contrôle, date
de validité. Rien n'est dupliqué, parce que deux définitions de la vérification
seraient le pire des deux mondes.

La surface machine a besoin d'une interrogation booléenne, et elle est **datée** :

```python
core.has_credential("rge", on=date(2026, 8, 16))   # True
core.has_credential("rge", on=date(2027, 1, 1))    # False, expirée entretemps
core.has_credential("decennale", on=date(2026, 8, 16))  # False, expirée
```

C'est la date qui fait l'autorité. Une décennale expirée sort automatiquement de
la publication et entre dans le plan de travail, sans intervention humaine.

---

## 5. La provenance, sur chaque chantier

Elle ne dit pas si c'est vrai, elle dit **d'où ça vient**. C'est la condition pour
déboguer une donnée fausse et pour décider ce qui peut devenir opposable.

| Provenance | Pièce | Entre dans un budget publié |
|---|---|---|
| `facture` | référence obligatoire | oui |
| `devis` | référence obligatoire | oui |
| `vocal` | aucune | non |
| `import` | aucune | non |

Une provenance documentée **sans référence de pièce est refusée à la
construction** : elle prétendrait à une opposabilité qu'elle n'a pas.

---

## 6. Ce que ça produit

Sur le Noyau de démonstration (18 chantiers, 2 quartiers au-dessus du seuil) :

**Publié vers la surface machine**

```
[territoire] 6 chantiers réalisés aux Chartrons, dernier en 06/2026
             (ravalement de façade en pierre de taille, rénovation de cuisine,
             rénovation de salle de bain, rénovation globale).
[budget]     Rénovation de salle de bain, 5 à 8 m2 : budget médian constaté
             11 550 €, moitié des chantiers entre 10 600 € et 12 575 €,
             sur 6 chantiers facturés depuis 2025.
[autorite]   Qualification RGE : RGE Qualibat 7131, isolation thermique par
             l'extérieur. Contrôlé le 2025-11-04, valable jusqu'au 2026-11-04.
```

**Plan de travail**

```
· Rénovation de cuisine, 8 à 14 m2 : 2 chantiers exploitables sur 5 requis
  (1 sans pièce justificative). Récupérer les pièces manquantes.
· Documenter 2 chantiers de plus à Nansouty pour publier cette implantation.
· Assurance décennale : vérification expirée. Obtenir la pièce à jour.
```

Le plan de travail est l'objet le plus important du produit du point de vue
commercial : c'est lui qui rend le travail visible, et le travail visible est ce
qui empêche la résiliation. Chaque ligne nomme son sujet et l'action précise,
parce qu'une ligne qui dirait « 2 chantiers sur 5 requis » sans dire de quoi
serait inutilisable par la personne qui va chercher les pièces.

Un invariant testé : **publié et manques ne se recouvrent jamais.**

---

## 7. Ce qui reste à construire

1. **L'ingestion.** Le Noyau est aujourd'hui un fichier tenu à la main. Il manque
   la chaîne vocal et photo vers assertions candidates, avec provenance et
   confiance, jamais d'écriture directe.
2. **Le niveau engageant.** Le modèle distingue déclaré et vérifié ; il manque le
   troisième niveau, celui que l'entreprise **engage** avec conséquence, seul
   utilisable par un agent qui transacte.
3. **Les surfaces.** Les assertions sont structurées mais pas encore rendues en
   schema.org, fiche locale, ni point d'accès interrogeable.
4. **Les autres verticales.** ~~Fait.~~ Les natures et les bandes ne sont plus
   codées en dur pour la rénovation : elles vivent dans `metiers/*.json`, un
   fichier par métier, chargés et fusionnés par `noyau.catalogue`. Le noyau
   générique (territoire, provenance, seuils, distribution) et le vocabulaire
   métier sont désormais découplés au même titre — voir
   `tools/demo_multi_metier.py`, qui publie une rénovation
   (`atelier-ferrand.json`) et une plomberie (`aqua-bordeaux.json`) avec
   exactement le même code, aucune branche par métier. Ajouter un métier ne
   demande qu'un fichier JSON de plus dans `metiers/`, avec des codes de
   nature qui ne collisionnent pas avec ceux déjà pris (`merge()` refuse la
   collision plutôt que de l'écraser silencieusement).
