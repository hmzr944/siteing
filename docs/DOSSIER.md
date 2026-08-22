# Le Dossier de Vérité

> C'est la partie **livrée** du produit. Le moteur de Part de Citation diagnostique
> une perte ; le Dossier de Vérité est ce que le client paie chaque mois. Sans lui,
> Source Primaire n'est qu'un outil de mesure, donc commoditisable dans l'année.

## 1. La frontière qui fait le produit

Un dossier est un ensemble d'affirmations sur une entreprise : existence légale,
capacités, engagements, couverture. Chacune porte son statut et les pièces qui
l'appuient. Une seule règle gouverne tout :

> **Seules les affirmations vérifiées sont publiées vers la couche machine.**

Une affirmation déclarée reste visible par un humain, marquée comme déclarée, et
n'est jamais exportée comme un fait. Cette frontière est vérifiée par un test
(`tests/test_publish.py::test_no_unverified_value_appears_anywhere`) qui échoue si
une seule valeur non contrôlée fuit dans le JSON-LD.

C'est le cœur du modèle pour trois raisons :

1. **Ce n'est pas copiable par un générateur de sites.** Vérifier suppose un tiers
   qui contrôle des pièces. Un produit en self-serve ne peut pas se contrôler
   lui-même sans que le contrôle perde toute valeur.
2. **Ça donne une raison de payer tous les mois.** Une vérification **expire**. Un
   dossier constitué une fois vaut une déclaration ; c'est la tenue dans le temps
   qui se facture.
3. **Ça rend l'entreprise citable.** Les moteurs de réponse reprennent ce qui est
   structuré et attribuable, et ignorent la prose marketing.

## 2. Les quatre statuts

| Statut | Condition | Publié en machine |
|---|---|---|
| `verifie` | pièce contrôlée, validité en cours | oui |
| `declare` | aucune pièce, ou pièce reçue mais pas contrôlée | non |
| `expire` | contrôle dont la validité est dépassée | non |
| `refute` | contredit par les pièces | non |

Deux subtilités qui comptent :

- **Une pièce reçue n'est pas une pièce contrôlée.** Une affirmation avec des
  pièces mais sans date de contrôle reste `declare`. C'est ce qui empêche de
  déclarer vérifié tout ce qui arrive par courriel.
- **Le dernier jour de validité reste valable.** L'expiration prend effet le
  lendemain, pas le jour même.

Sans échéance explicite, une vérification en reçoit une automatiquement
(`DEFAULT_VALIDITY_DAYS`, 365 jours). La péremption n'est jamais optionnelle.

## 3. Prose pour l'humain, valeur typée pour la machine

`foundingDate` attend une date, pas une phrase. Une affirmation peut donc porter
deux valeurs :

```json
{
  "value": "SARL immatriculée au RCS de Bordeaux depuis mars 2009",
  "schema_property": "foundingDate",
  "schema_value": "2009-03"
}
```

L'humain lit la phrase, la machine reçoit `2009-03`. Publier de la prose dans une
propriété typée produit du structuré malformé, c'est à dire exactement le défaut
que ce produit est censé corriger.

## 4. Les quatre sorties

```bash
python3 -m citation_audit dossier dossiers/vasseur.json \
    --url https://plomberie-vasseur.fr/verite \
    --out out/
```

| Fichier | Public | Contenu |
|---|---|---|
| `<id>.html` | humains et indexeurs | la Page de Vérité, document autonome hébergé par l'entreprise, JSON-LD embarqué |
| `<id>.jsonld` | indexeurs | schema.org, **vérifié uniquement** |
| `<id>.manifest.json` | agents | **toutes** les affirmations, avec leur statut, leur nombre de pièces et leurs dates |
| `<id>.jsonl` | agrégation sectorielle | une ligne par entreprise, pour les flux |

Le manifeste expose délibérément le déclaratif *avec son statut*. Un agent a
besoin de savoir ce qui n'est pas vérifié ; le lui cacher serait la seule vraie
faute de ce format. La distinction est portée par la donnée, pas par une note de
bas de page.

## 5. La Page de Vérité

La page est le point de publication, pas une brochure qui renvoie ailleurs : le
JSON-LD y est embarqué, lisible sans exécuter de script.

**Le parti de conception est contraint par le sujet.** Une page de vérification
qui ressemble à une page de vente ne vérifie rien. Donc : aucune carte arrondie
(rayon 0 partout), aucune animation, aucune pastille verte, et une section
entière consacrée à **ce qui n'est pas vérifié**. C'est cette section qui rend le
reste croyable, et c'est le choix de conception le plus important du document.

Aucune coche de validation nulle part. Une coche verte est le signal de confiance
le moins coûteux à fabriquer, donc le moins crédible. Le statut est porté par un
libellé, une date de contrôle et la nature de la pièce.

Sans photo réelle de l'entreprise, **aucun substitut** : une image d'illustration
sur un registre de vérification détruirait ce que la page sert à établir.

Les règles de conception sont testées mécaniquement dans
`tests/test_verite.py::TestDesignPreFlight` : zéro tiret cadratin, plafond
d'eyebrows, système de forme unique, jetons de thème définis pour les trois états
d'affichage, contraste, focus clavier. Une règle de design non testée est une
règle qui sera violée à la prochaine modification.

## 6. Sécurité

Les valeurs d'affirmations viennent d'un fichier fourni par l'exploitant, mais
elles finissent dans un bloc `<script type="application/ld+json">`. Une valeur
contenant `</script>` en sortirait et deviendrait du balisage exécutable. Les
caractères `<`, `>` et `&` sont donc échappés en séquences `\uXXXX` dans le JSON
embarqué, ce qui reste du JSON valide. Couvert par
`test_jsonld_cannot_escape_its_script_block`.

Les pièces ne sont **jamais** stockées ni publiées : le dossier ne porte que des
références (« Police 4471-882-C », « DSN 2026-05 ») et le nom du contrôleur. Un
dossier est un document publiable ; publier une facture client serait une faute.

## 7. L'allocation des créneaux d'accompagnement

À ne pas confondre avec le Dossier de Vérité ou sa publication : ceci ne
touche jamais à ce qu'une IA lit sur une entreprise. Le dossier et ses
sorties machine (§3-§6) sont la même source pour toute entreprise vérifiée,
payante ou non — sans quoi le registre cesserait d'être une source fiable
pour devenir une régie publicitaire. `to_manifest()` et `to_html()` n'ont
d'ailleurs plus aucun paramètre lié à ceci : ils ne peuvent pas le faire
fuiter.

Ce que `citation_audit/creneau.py` gère est différent : sur quelle
entreprise, par catégorie et par zone, l'équipe concentre son travail
d'accompagnement — le modèle d'une agence de génération de leads qui ne
travaille jamais pour deux concurrents directs à la fois. Une exclusivité de
service promise oralement et tenue dans un tableur finit promise deux fois,
et ce jour-là nous perdons les deux clients plus l'argument qui fait notre
prix.

`citation_audit/creneau.py` en fait une **contrainte système**. Le registre
d'allocation ne prévient pas, il refuse :

```
créneau plombier / Bordeaux Métropole détenu en exclusivité par vasseur
jusqu'au 2027-02-01
```

Les règles appliquées :

- un créneau détenu en exclusivité bloque toute autre entreprise ;
- l'exclusivité est refusée si le créneau est déjà partagé ;
- un créneau partagé sature à `MAX_SHARED_HOLDERS` (3) titulaires, au-delà le
  travail d'accompagnement se dilue entre trop de clients pour rester ce
  qu'il prétend être ;
- une même entreprise ne peut pas détenir deux fois le même créneau ;
- la clé de créneau ignore la casse, les accents et les espaces, donc
  « Bordeaux Métropole » et « bordeaux metropole » sont le même créneau ;
- libérer un créneau raccourcit l'octroi sans effacer l'historique : savoir qui
  détenait quoi et jusqu'à quand fait partie du registre d'allocation.

## 8. Ce qui reste à construire

1. **La chaîne de collecte des pièces.** Aujourd'hui le dossier est un JSON tenu
   à la main. Il faut le circuit : demande de pièce, dépôt par le client,
   contrôle, journal d'attestation daté. C'est le prochain goulot d'étranglement,
   et c'est aussi la ligne de coût qui décide si l'entreprise reste un éditeur ou
   devient une agence déguisée (voir `docs/ECONOMIE.md`, 120 €/mois/client).
2. **La distribution.** Le dossier est publiable ; il n'est pas encore *poussé*
   vers les corpus sectoriels et les partenaires de données. Publier ne suffit
   pas à être cité.
3. **La boucle de mesure.** Relier la Part de Citation au dossier, pour établir
   quelles affirmations vérifiées font réellement bouger la citation. C'est ce qui
   transformerait le produit d'une intuition en une méthode.
