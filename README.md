# Source Primaire

**L'IA n'a pas tué les agences web. Elle a tué la valeur de l'objet « site web ».**

Fabriquer un site ne vaut plus rien : Base44, Lovable, Bolt, v0, Framer AI le font
en trente secondes. Le taux d'échec commercial, lui, n'a pas bougé d'un point —
parce qu'il ne venait pas de là. Ce qui reste rare quand la fabrication devient
gratuite, c'est **être trouvé**, **être cru**, **être garanti**.

Source Primaire attaque la première : le premier point de contact entre une
entreprise et son client n'est plus un moteur de recherche mais une **réponse
générée**, qui ne classe pas des sites — elle cite trois sources. Nous rendons une
entreprise citable, nous mesurons sa **Part de Citation**, et nous ne vendons ce
créneau qu'à une seule entreprise par catégorie et par zone.

Un générateur de sites en self-serve ne peut pas nous copier : la citabilité est
un bien rival, et un produit qui l'ouvre à tous annule sa propre promesse.

## Le dépôt

| | |
|---|---|
| [`docs/PLAN.md`](docs/PLAN.md) | la décision : offre, prix, feuille de route, risques, preuve à 90 jours |
| [`docs/DOSSIER.md`](docs/DOSSIER.md) | le Dossier de Vérité : la partie livrée, ses statuts, ses sorties machine, le registre des créneaux |
| [`docs/METHODE.md`](docs/METHODE.md) | la méthode de mesure, limites incluses — destinée à être publique |
| [`docs/ECONOMIE.md`](docs/ECONOMIE.md) | unité économique, trajectoire, sensibilité |
| [`docs/VENTE.md`](docs/VENTE.md) | le playbook d'acquisition : séquences, objections, seuils |
| [`STRATEGIE.md`](STRATEGIE.md) | les trois concepts explorés au départ, et pourquoi celui-ci |
| `citation_audit/` | le moteur de mesure et le Dossier de Vérité |
| `tools/economics.py` | le modèle économique, exécutable |

## Démarrer

Aucune dépendance : Python 3.11+ et la bibliothèque standard.

```bash
# le panier de questions figé d'un marché
python3 -m citation_audit basket markets/plombier-bordeaux.json

# un relevé de démonstration (moteur simulé, hors ligne)
python3 -m citation_audit audit markets/plombier-bordeaux.json \
    --provider synthetic:7 --provider synthetic:19 --out out/

# publier un Dossier de Vérité: page publique + sorties machine
python3 -m citation_audit dossier dossiers/vasseur.json \
    --registry registre/creneaux.json --out out/

# le modèle économique
python3 tools/economics.py

# les tests
python3 -m unittest discover -s tests -t . -q
```

Le relevé écrit `out/<marché>-audit.html` (le rapport remis au dirigeant) et
`out/<marché>-audit.json` (l'annexe complète).

### Un relevé réel

```bash
export ANTHROPIC_API_KEY=...
python3 -m citation_audit audit markets/plombier-bordeaux.json \
    --provider anthropic:claude-sonnet-5 \
    --provider anthropic:claude-opus-5 \
    --archive archives/ --out out/
```

Les réponses brutes sont archivées : tout chiffre d'un rapport est reconductible
au corpus exact qui l'a produit, et rejouable avec `--provider fixture:<archive>`.

## Les trois indicateurs

- **Taux de Présence** — sur quelle proportion du panier l'entreprise apparaît.
  Le chiffre brutal, celui qui ouvre une conversation : « sur 35 questions
  d'achat de votre marché, vous apparaissez 2 fois ».
- **Part de Citation** — la part de la voix captée, pondérée par l'intention
  commerciale de la question et par le rang d'apparition (décote logarithmique
  `1/log2(1+rang)`). C'est l'indicateur du contrat.
- **Angles morts** — les questions où l'entreprise est absente alors qu'un
  concurrent est cité, nommé. Ce ne sont pas des statistiques, ce sont des pertes
  identifiées.

## Ce qui est livré au client

Le moteur diagnostique ; le **Dossier de Vérité** est ce qui se facture chaque
mois. C'est un ensemble d'affirmations sur l'entreprise, chacune avec son statut
et les pièces qui l'appuient, gouverné par une seule règle :

> Seules les affirmations **vérifiées** sont publiées vers la couche machine.

Une affirmation déclarée reste visible par un humain, marquée comme telle, et
n'est jamais exportée comme un fait. Une vérification **expire** : un dossier
constitué une fois vaut une déclaration, c'est sa tenue dans le temps qui se
facture. Détails dans [`docs/DOSSIER.md`](docs/DOSSIER.md).

La **Page de Vérité** publie tout cela pour deux lecteurs à la fois : un humain
qui vérifie avant d'appeler, et un agent qui parse le JSON-LD embarqué. Sa
section la plus importante est celle qui liste **ce qui n'est pas vérifié**, sans
laquelle le reste ne serait pas croyable.

Le **registre des créneaux** fait de l'exclusivité vendue une contrainte du
système plutôt qu'une promesse orale. Il ne prévient pas, il refuse.

## Les garde-fous, et pourquoi ils sont dans le code

La crédibilité de la mesure est le seul actif de l'entreprise. Elle est donc
défendue par le programme, pas par une consigne :

- **un panier figé** par marché, avec empreinte de version — deux relevés de
  versions différentes se déclarent non comparables. Un audit dont le panel bouge
  ne mesure rien ;
- **une détection avare** — frontières de mots, rejet des noms génériques et des
  alias trop courts. Un faux positif dans un audit facturé coûte plus cher que dix
  mentions manquées ;
- **un niveau de preuve** porté par chaque relevé, égal à celui de son maillon le
  plus faible. Un relevé simulé refuse de se présenter comme un audit et porte un
  bandeau « ne pas remettre au client » (`AuditResult.is_presentable`) ;
- **une valorisation plancher** — l'écart est mesuré à la *part équitable* (1/n),
  jamais à 100 % du marché, et le rapport affiche le calcul ;
- **aucune promesse de position.** Nous mesurons ce que les moteurs restituent.
  Garantir une place chez un éditeur tiers est intenable, et le refuser est un
  argument de vente.

- **la frontière du vérifié**, testée: une seule valeur non contrôlée qui fuirait
  dans le JSON-LD fait échouer la suite. Et les valeurs d'affirmations ne peuvent
  pas s'échapper de leur bloc `<script>`.

146 tests couvrent ces invariants, la normalisation, le calcul des parts, les
statuts de vérification, les conflits de créneaux, le modèle économique, et les
règles de conception de la Page de Vérité. Une règle de design non testée est une
règle qui sera violée à la prochaine modification.

## Ligne de base sur un marché

Un audit mesure une entreprise contre ses concurrents. Une **cohorte** mesure un
marché entier, sans client désigné, et répond à la question dont dépend la thèse
du projet : **le rang Google prédit-il la citation par les moteurs de réponse ?**

```bash
python3 -m citation_audit cohorte markets/renovation-bordeaux.json \
    --provider synthetic:11 --provider synthetic:23 --out out/
```

Le panel de mesure est **stratifié par rang Google** et n'est pas la liste de
prospection. On mesure sur des strates pour pouvoir corréler ; on vend ensuite au
segment de son choix. Confondre les deux listes détruit la mesure, parce qu'un
échantillon choisi sur le rang Google ne peut plus rien dire du lien entre rang
Google et citation.

La corrélation est une corrélation de rangs (Spearman) avec sa valeur p : un
coefficient sans seuil de signification sur vingt observations est une illusion
d'optique. Le signe se lit avec attention, un bon rang Google étant *petit* et
une bonne part de citation *grande* : rho négatif signifie « bien classé et bien
cité ».
