# Les surfaces — comment le Noyau devient citable

```bash
python3 -m surfaces noyaux/atelier-ferrand.json \
    --url https://atelier-ferrand.fr --out out/site
```

---

## 1. Correction technique préalable

**`.well-known/ai-plugin.json` est mort.** C'était le manifeste des ChatGPT
Plugins, abandonné lors du passage aux GPTs puis aux Actions. Bâtir la
distribution dessus serait bâtir sur un cadavre.

Le point stratégique qui en découle est plus important que le point technique :

> **Les agents ne découvrent pas des API. Les crawlers lisent des pages.**

Une API ou un serveur MCP suppose qu'un agent ait été **configuré** pour s'y
connecter. C'est un canal de *transaction*, pas de *découverte*. Or nous cherchons
d'abord à être **cités**, ce qui passe par le crawl. La couche agent à agent
viendra pour le transactionnel, quand les protocoles auront des volumes réels ;
la construire aujourd'hui, ce serait parier sur un calendrier qu'on ne maîtrise
pas, risque déjà identifié dans `PAROLE.md`.

Ce qui est réellement consommé aujourd'hui, par ordre d'importance :

1. le **texte rendu** d'une page HTML rapide ;
2. le **JSON-LD** schema.org, qui confirme et désambiguïse ce texte ;
3. les **miroirs Markdown**, format que les modèles ingèrent le mieux ;
4. la couche de **permission** (`robots.txt`), sans laquelle rien du reste ne sert.

---

## 2. La décision structurante : une entreprise n'est pas une page

Une page unique qui dit tout est une URL en concurrence sur tout, et elle perd
contre les annuaires sur les requêtes génériques.

Ce que le Noyau permet, et que personne d'autre ne peut produire, c'est un
**treillis** : le croisement du territoire et de la nature de chantier, où chaque
nœud correspond exactement à une question d'achat réelle.

| Page | Question à laquelle elle répond | Matière |
|---|---|---|
| `index.html` | Quelle entreprise de rénovation choisir à Bordeaux ? | 18 chantiers |
| `chantiers-chartrons.html` | Quelle entreprise intervient aux Chartrons ? | 6 chantiers |
| `salle-de-bain-chartrons.html` | Qui fait une salle de bain aux Chartrons ? | 3 chantiers + budget |
| `chantiers-cauderan.html` | Quelle entreprise intervient à Caudéran ? | 5 chantiers |
| `isolation-exterieure-cauderan.html` | Qui fait une isolation extérieure à Caudéran ? | 2 chantiers |

**Un concurrent ne peut pas fabriquer la troisième page.** Il faudrait avoir fait
les chantiers. C'est le composé décrit dans `PAROLE.md`, rendu opérationnel : le
treillis transforme une accumulation en surface de citation.

### Deux règles, une seule idée : une page sans fait est du spam

- un croisement n'a sa page qu'à partir de **2 chantiers**, parce qu'un chantier
  isolé produit une page maigre, exactement ce que les moteurs apprennent à
  ignorer ;
- un territoire n'a sa page qu'à partir de **3 chantiers**, seuil hérité du Noyau ;
- un fait qui ne mérite pas sa page **n'est pas perdu** : il reste porté par la
  page du territoire.

Un test interdit la production d'une page sans fait daté.

---

## 3. Le principe de rendu : redondance volontaire

> **Les mêmes faits figurent dans le texte visible et dans le JSON-LD.**

Un moteur de réponse extrait avant tout du **texte rendu** ; les données
structurées confirment et désambiguïsent. Un fait qui n'existerait que dans le
JSON-LD serait deux fois plus faible qu'un fait présent dans les deux. La
redondance est ici une fonctionnalité, pas un gaspillage. Un test le vérifie sur
le budget.

La page ne charge **aucune ressource distante**, aucun script hors JSON-LD,
aucune image décorative. Ce qui est cité, c'est un fait daté et localisé, jamais
une mise en page.

---

## 4. L'interdit central : jamais le vocabulaire de l'offre

`Offer`, `AggregateOffer`, `PriceSpecification`, `price`, `lowPrice`, `highPrice`
décrivent ce qu'une entreprise **propose de vendre**. Nous publions ce qui a été
**facturé par le passé**, sans engagement sur le prochain chantier.

Employer ce vocabulaire transformerait un constat en proposition commerciale, ce
qui est exactement le risque contre lequel tout le schéma du Noyau a été conçu.
C'eût été l'erreur la plus facile à commettre : `AggregateOffer` avec
`lowPrice`/`highPrice` est la projection « naturelle » d'une fourchette de prix,
et elle est juridiquement fausse ici.

Le budget est donc publié en mesure :

```json
{
  "@type": "PropertyValue",
  "name": "Budget constaté sur chantiers réalisés",
  "value": {
    "@type": "QuantitativeValue",
    "unitText": "EUR", "value": 11550, "minValue": 10600, "maxValue": 12575
  },
  "measurementTechnique": "Médiane et quartiles de 6 chantiers facturés entre
    2025-03-14 et 2026-06-30, sur des ouvrages de taille comparable. […]
    Constat de facturation passée, sans engagement sur un chantier futur."
}
```

`surfaces.jsonld.contains_offer_vocabulary()` fait partie du contrat du module,
pas des tests : deux tests l'exercent, dont un qui vérifie que **le détecteur
détecte** (un garde-fou qui ne détecte rien ne garde rien).

---

## 5. Le piège de la portée du budget

Défaut trouvé et corrigé en cours de construction, qui aurait ruiné la
crédibilité en silence.

Un budget est agrégé sur **toute l'activité** de l'entreprise pour une nature et
une taille données, jamais sur le seul quartier : trois chantiers locaux ne font
pas une médiane. Mais une page de quartier qui **liste 3 chantiers** et annonce un
budget « sur **6** chantiers » se contredit à l'œil nu, pour un lecteur comme pour
un modèle.

La portée est donc **écrite**, jamais déduite :

> Ce budget porte sur les 6 chantiers de cette nature et de cette taille réalisés
> par l'entreprise, tous secteurs confondus, dont 3 aux Chartrons.

La mention est propagée aux trois rendus : HTML, Markdown et `measurementTechnique`.

---

## 6. L'exclusivité n'entre jamais dans ce module

Une première version de ce module ajoutait une mention « Position vérifiée
exclusive » dans les quatre rendus quand une entreprise détenait un créneau
exclusif (`citation_audit.creneau.Registry`). **Corrigé : ce module n'a plus
aucune notion de palier commercial.**

La raison n'est pas esthétique. Le registre a de la valeur pour un agent
parce qu'il peut lui faire confiance comme source complète et honnête. Le
jour où un agent découvrirait qu'une mention favorable dépend de ce qu'une
entreprise paie, le registre cesserait d'être une source fiable pour devenir
une régie publicitaire — et ça contredit frontalement la position de tiers
neutre du produit (« le passeport, pas la frontière »). Voir `docs/PLAN.md` §1
pour la décision complète.

Ce que publie ce module — `for_node`, `page`, `markdown`, `llms_txt`,
`generate` — est donc **strictement identique** pour toute entreprise
vérifiée, quel que soit ce qu'elle paie. Ces fonctions n'acceptent d'ailleurs
plus de paramètre de registre du tout : il ne peut pas fuiter par erreur dans
une future modification, il n'a simplement plus de point d'entrée.

L'exclusivité continue d'exister, mais uniquement comme allocation interne
du travail d'accompagnement (`citation_audit.creneau`) — sur quelle
entreprise l'équipe concentre son effort, jamais sur ce que ce module publie.
Elle n'est câblée nulle part dans ce paquet, volontairement.

---

## 7. Les quatre fichiers qui comptent autant que les pages

**`robots.txt` — la couche de permission, et le premier point de contrôle.**
Beaucoup de sites de TPE bloquent par accident les robots d'IA, hérité d'un
gabarit ou d'une extension. Tout le reste devient alors inutile : une page
parfaitement structurée qu'un robot n'a pas le droit de lire ne sera jamais citée.

Les robots sont donc autorisés **explicitement, un par un**, avec leur finalité en
commentaire : GPTBot, OAI-SearchBot, ChatGPT-User, ClaudeBot, Claude-User,
PerplexityBot, Google-Extended, Applebot-Extended, CCBot.

⚠️ **Autoriser un robot d'entraînement implique que la donnée publiée puisse
servir à entraîner un modèle.** Pour ce produit le troc est évident, puisque le
but est précisément d'être dans le corpus. Mais c'est une décision du client, pas
un réglage qu'on lui impose en silence : `robots(base_url, allow={"CCBot": False})`
permet de refuser au cas par cas.

**`sitemap.xml`** — le `lastmod` vient du **chantier le plus récent de la page**,
pas de la date de génération. Un fichier régénéré sans nouveau fait n'est pas une
page modifiée, et prétendre le contraire fait perdre la confiance du crawler. Un
test vérifie qu'aucun `lastmod` n'est la date du jour.

**`llms.txt`** — convention émergente pointant vers les miroirs Markdown.
L'adoption n'est pas universelle : c'est un **pari assumé**, coût quasi nul, gain
possible.

**Les miroirs Markdown** — une version sans balisage de chaque page, format que
les modèles ingèrent le mieux. Trois lignes à produire, puisque les faits sont
déjà structurés.

---

## 8. Ce que ça ne fait pas encore

1. **Le rendu adaptatif selon le contexte d'entrée.** Le treillis produit des
   pages statiques. La composition selon la requête référente reste à faire, et
   elle est moins urgente que la citation : il faut d'abord du trafic à convertir.
2. **La fiche locale.** Pas de synchronisation avec les fiches d'établissement.
3. **Le point d'accès agent.** Délibérément reporté, voir section 1.
4. **La mesure de l'effet.** Publier ne prouve rien. Le lien avec la Part de
   Citation, c'est à dire mesurer si ces pages font effectivement bouger la
   citation, est le chaînon manquant entre les deux moitiés du dépôt, et
   probablement la prochaine chose à construire.
