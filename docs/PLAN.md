# Source Primaire — le plan

> Décision prise. `STRATEGIE.md` contient les trois concepts explorés ; ce
> document n'en garde qu'un et engage tout le reste. Trois concepts en parallèle,
> c'est zéro concept.

## 1. La décision

Nous construisons **Source Primaire** : l'opérateur qui rend une entreprise
citable par les moteurs de réponse, mesure sa Part de Citation, et réserve la
**position vérifiée exclusive** d'une catégorie et d'une zone à une seule
entreprise à la fois.

Le Noyau lui-même — le dossier vérifié, sa publication — n'est réservé à
personne : le registre publie une fiche minimale gratuite pour toute
entreprise vérifiée, sans exception (§2-3). Seule l'exclusivité, palier
au-dessus, reste rare et payante — et elle ne porte que sur l'accompagnement,
jamais sur ce que le registre publie (`docs/SURFACES.md` §6).

Pourquoi celui-là plutôt que Cote (notation) ou Confluence (réseau mutualisé) :

| Critère | Source Primaire | Cote | Confluence |
|---|---|---|---|
| Douleur démontrable sans client | **oui, à coût ~9 €** | non, exige un audit | non, exige un réseau |
| Fenêtre de marché | **se ferme en 24-36 mois** | permanente | permanente |
| Démarrage à froid | aucun | partenaires institutionnels | fatal |
| Risque juridique | faible | élevé (notes nominatives) | moyen |

Cote et Confluence ne sont pas abandonnés : ils deviennent la **phase 2** et la
**phase 3**, et Source Primaire produit précisément les actifs qui les rendent
possibles (données vérifiées pour la notation, base de membres exclusifs pour le
réseau). L'ordre n'est pas un compromis, c'est la seule séquence où chaque étape
finance et débloque la suivante.

## 2. Ce que nous vendons

Pas un site. Pas du contenu. **La donnée vérifiée d'abord, la position rare
ensuite.**

Le livrable, du gratuit à l'exclusif :

1. **Le Dossier de Vérité** — référentiel machine-lisible de l'entreprise (offre,
   prix, délais, zones, capacités, garanties, preuves), constitué dès
   l'inscription, quel que soit le palier. Ce qui change avec le palier n'est
   pas si le dossier existe, c'est sa **profondeur publiée**.
2. **La vérification** — deux natures bien distinctes, qui tracent la
   frontière gratuit/payant : l'identité (SIREN/SIRET) se vérifie
   **automatiquement**, gratuitement, via le répertoire public SIRENE ; les
   chantiers sur pièce et les certifications exigent un **contrôle humain**,
   qui ne s'automatise pas. Voir `docs/ECONOMIE.md` §0 pour le chiffrage. Mais
   exister sur SIRENE ne prouve pas *qui* inscrit la fiche : un contrôle de
   l'établissement (code envoyé sur un canal déclaré, puis resaisi) est exigé
   en plus, avant toute publication même gratuite — voir `docs/VERIFICATION.md`.
3. **La distribution** — deux niveaux (`surfaces.MINIMAL` / `surfaces.COMPLET`),
   jamais un interrupteur payant/gratuit sur l'existence même. **Le registre
   publie sans exception** : toute entreprise vérifiée a une page et un
   JSON-LD, dès l'inscription. Ce que le palier change, c'est la profondeur
   de ce qui est publié (§3).
4. **La position exclusive** — catégorie × zone, réservée à une seule
   entreprise, contrainte par le registre d'allocation
   (`citation_audit/creneau.py`), pas une promesse orale — et jamais visible
   dans ce que le registre publie (voir `docs/SURFACES.md` §6).

## 3. Grille tarifaire

| Palier | Prix | Ce qui change | Cible |
|---|---|---|---|
| **Gratuit** | 0 € | fiche **minimale**, publiée : identité vérifiée automatiquement (nom, catégorie, zone, SIREN), page publique + JSON-LD. Aucun chantier, aucune certification. | toute entreprise, sans exception — c'est la couche universelle |
| **Forfait** | **19 €/mois** | fiche **complète** : chantiers sur pièce, budgets constatés, certifications, treillis de pages, relevé de citation périodique | TPE, artisan, indépendant — vendu en self-serve, jamais par appel commercial |
| **Exclusif** | 990 €/mois | + **position vérifiée exclusive** catégorie × zone, distribution prioritaire, revue trimestrielle | leader local, franchise, e-commerce régional — vendu par le playbook sortant (`docs/VENTE.md`) |

- **Frais d'entrée, palier Exclusif seulement : 900 €** — constitution
  approfondie et vérification initiale. Ils qualifient autant qu'ils
  financent : un dirigeant qui refuse 900 € ne signera pas 990 €/mois. Le
  Forfait n'a pas de frais d'entrée : à ce prix, le moindre frein casse la
  conversion self-serve.
- Détail du calibrage et de l'unité économique de chaque palier :
  `docs/ECONOMIE.md`.

**Le gratuit n'est pas un plafond de fonctionnalités arbitraire, c'est la
frontière du vérifiable sans humain.** Le registre vaut par sa complétude,
pas par son revenu : un annuaire qui n'exposerait que ses clients payants
perdrait la densité qui est son seul argument face à une IA qui, sinon,
consulte le web scrappé. « Payez pour exister » est aussi le modèle des
annuaires professionnels payants des années 2000 — reconnaissable au premier
coup d'œil par n'importe quel prospect sceptique. La phrase qui tient lieu de
règle : **exister dans le registre est un droit, en tirer la profondeur, la
fraîcheur et le suivi est un service.**

**L'exclusivité reste réelle**, comme avant : un seul acteur par créneau,
contrainte système et non promesse orale — c'est ce qui rend l'urgence
commerciale honnête sur ce palier, et interdit à un concurrent en self-serve
de le copier sans en détruire la valeur.

## 4. Ce qui est construit, et ce qui reste à construire

**Construit et testé** (`citation_audit/`, 73 tests) :

- définition de marché et génération du panier figé, avec empreinte de version ;
- détection conservatrice des entreprises (nom, alias, domaine sourcé) ;
- calcul de la Part de Citation, du Taux de Présence, des angles morts et de
  l'écart à la part équitable ;
- providers : mesure réelle (API avec recherche web), rejeu d'archive,
  simulation hors ligne ;
- garde-fous de preuve dans le code — un relevé simulé refuse de se présenter
  comme un audit ;
- rapport client HTML + annexe JSON + archivage des réponses brutes ;
- modèle économique exécutable (`tools/economics.py`).

**État réel, mis à jour au fil de la construction** (cette liste datait d'avant
la plupart de ce qui suit — laissée visible pour la trace, corrigée plutôt que
réécrite en silence) :

1. ~~Deuxième famille de moteurs.~~ Fait — `--provider` est répétable, un seul
   éditeur n'est jamais accepté comme mesure de marché.
2. ~~Le Dossier de Vérité comme produit.~~ Fait, et étendu au-delà de la
   rénovation : voir `noyau/` et `surfaces/` (`docs/NOYAU.md`, `docs/SURFACES.md`)
   — universel par métier (`metiers/*.json`) et par ville (`referentiels/*.json`),
   avec ou sans ancrage géographique.
3. ~~Chaîne de vérification.~~ Fait — provenance par pièce (facture, devis),
   seuils de publication testés (`noyau/budget.py`, `noyau/noyau.py`).
4. **Industrialisation de l'audit de prospection.** Fait pour la partie
   texte : panier réduit à 12 questions (`Market.prospecting_basket()`),
   1 moteur, e-mail jour 0 généré automatiquement
   (`citation_audit/prospection.py`, voir `docs/VENTE.md` §1). **Pas fait** :
   le rendu vidéo de 90 secondes reste manuel.
5. ~~Registre des créneaux.~~ Fait, puis corrigé — `citation_audit/creneau.py`,
   trois paliers (socle/position/exclusif), refus de conflit plutôt
   qu'avertissement. Une première version le faisait consulter par les
   surfaces publiques pour y ajouter une mention d'exclusivité
   (`surfaces/exclusivite.py`, supprimé) : erroné, ça faisait du registre une
   régie publicitaire. L'exclusivité porte désormais uniquement sur
   l'allocation de l'accompagnement, jamais sur ce que le registre publie —
   voir §1.
6. **Le niveau engageant.** Toujours pas fait — voir `docs/NOYAU.md` §7.
7. **Le commerce et l'hôtellerie-restauration.** Toujours hors scope,
   délibérément — voir `docs/NOYAU.md` §7.

## 5. Économie

Détail et sensibilité dans `docs/ECONOMIE.md`. Deux mouvements commerciaux
distincts, deux unités économiques — les fondre en un ARPU moyen cacherait
que le Forfait et l'Exclusif ne jouent pas le même rôle :

| | Forfait (19 €/mois, self-serve) | Exclusif (990 €/mois, sortant) |
|---|---|---|
| Marge brute / client / mois | 13 € | 859 € |
| CAC | 82 € (effectif, gratuits inclus) | 2 400 € |
| Retour sur CAC | 6,3 mois | 2,8 mois |
| LTV / CAC | 2,6x | 14,6x |
| Rôle | volume, couverture du registre | rentabilité |

Combiné : **EBITDA mensuel positif au mois 9**, **cumul positif au mois 17**,
**besoin de financement maximal ~86 k€ (mois 8)**.

Le Forfait reste sciemment sous le seuil de santé de 3x — ce n'est pas un
centre de profit autonome à ce prix, et ce n'est pas censé l'être. Le
mouvement Exclusif, lui, est contraint par la capacité commerciale, jamais
par la demande ; le mouvement Forfait est contraint par le taux de
conversion gratuit → payant, la variable la moins connue du modèle.

## 6. Les trois risques, et ce qu'on fait contre

**Dépendance de plateforme.** Les éditeurs peuvent changer leurs mécanismes de
sourçage sans préavis. C'est le risque principal et il est irréductible. Mitigation :
le Dossier de Vérité est un actif indépendant du canal — donnée structurée,
vérifiée, exposée — qui garde sa valeur si les moteurs changent, et qui sert
directement de socle à la phase Cote. Nous vendons un dossier et une mesure, pas
un tuyau.

**Promesse intenable.** La tentation commerciale sera de garantir une position.
Interdit, et le garde-fou est dans le produit : le contrat porte sur la Part de
Citation mesurée, le rapport affiche cette limite, et la méthode publiée le
répète. Une seule promesse tenue de trop détruirait la crédibilité qui est notre
seul actif.

**Commoditisation de la mesure.** Un éditeur ou un concurrent peut proposer un
« score de visibilité IA » gratuit. Mitigation : la mesure n'est pas le produit,
c'est le prix d'entrée. Ce qui ne se copie pas, c'est la vérification par tiers,
le registre d'exclusivité et le travail de distribution. Nous devons donc sortir
du statut d'outil de mesure vite — d'où l'ordre de construction ci-dessus.

## 7. Preuve à 90 jours

Une verticale, une agglomération, et les chiffres qui décident de la suite —
un par mouvement commercial, parce qu'ils ne se valident pas de la même façon :

| | Cible | Mouvement |
|---|---|---|
| Taux de conversion gratuit → Forfait | ≥ 10 % cumulé sur 90 jours | Forfait |
| Clients Exclusif signés | 4 | Exclusif |
| Part de Citation médiane des clients payants | ×3 vs relevé initial | les deux |
| Taux audit → rendez-vous (Exclusif) | ≥ 8 % | Exclusif |

Si la conversion Forfait reste sous 5 %, le palier gratuit se rapproche du
régime Linktree (`docs/ECONOMIE.md` §0) : il continue de couvrir le
registre, mais il faut arrêter d'en attendre une contribution à la
trésorerie et le dire clairement plutôt que de se raconter un modèle qui ne
tient pas.

Si la Part de Citation ne triple pas, le produit ne fonctionne pas et aucun
discours ne le sauvera. Si le taux de rendez-vous est sous 5 %, le CAC double et
le modèle passe sous 4x : il faut alors changer de canal, pas d'argumentaire.
