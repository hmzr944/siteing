# Source Primaire — le plan

> Décision prise. `STRATEGIE.md` contient les trois concepts explorés ; ce
> document n'en garde qu'un et engage tout le reste. Trois concepts en parallèle,
> c'est zéro concept.

## 1. La décision

Nous construisons **Source Primaire** : l'opérateur qui rend une entreprise
citable par les moteurs de réponse, mesure sa Part de Citation, et ne vend ce
créneau qu'à **une seule entreprise par catégorie et par zone**.

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

Pas un site. Pas du contenu. **Un loyer de position** sur un créneau rare.

Le livrable en régime, chaque mois :

1. **Le Dossier de Vérité** — référentiel machine-lisible de l'entreprise (offre,
   prix, délais, zones, capacités, garanties, preuves), maintenu à jour et exposé
   dans les formats que consomment les agents.
2. **La vérification par tiers** — chaque affirmation contrôlée sur pièces. C'est
   la partie qu'un logiciel en self-serve ne peut structurellement pas produire.
3. **La distribution** — travail d'opérateur sur les corpus qui alimentent les
   réponses : bases sectorielles, annuaires structurés, sources citées,
   partenariats de données.
4. **Le relevé de Part de Citation** — panier figé, deux moteurs, réponses
   archivées. C'est l'unique KPI du contrat.

## 3. Grille tarifaire

| Palier | Prix | Ce qui change | Cible |
|---|---|---|---|
| **Socle** | 349 €/mois | dossier vérifié, relevé mensuel, 1 catégorie | TPE, artisan, commerce |
| **Position** | 749 €/mois | + distribution active, 3 catégories, revue trimestrielle | PME, prestataire multi-services |
| **Exclusif** | 1 490 €/mois | + **exclusivité contractuelle** catégorie × zone, priorité de traitement | leader local, franchise, e-commerce régional |

- **Frais d'entrée : 900 €** — constitution du dossier et vérification initiale.
  Ils qualifient autant qu'ils financent : un dirigeant qui refuse 900 € ne
  signera pas 749 €/mois.
- **Commission d'attribution : 5 %** sur la demande entrante tracée.
- Mix cible : 50 % Socle, 35 % Position, 15 % Exclusif → **ARPU 660 €**.

L'exclusivité n'est vendue qu'au palier haut, et elle est **réelle** : nous ne
pouvons techniquement servir qu'un acteur par créneau sans détruire la valeur que
nous vendons. C'est ce qui rend l'urgence commerciale honnête, et c'est aussi ce
qui interdit à un concurrent en self-serve de nous copier — son modèle de volume
est incompatible avec la rareté qui fait notre prix.

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
5. ~~Registre des créneaux.~~ Fait — `citation_audit/creneau.py`, trois
   paliers (socle/position/exclusif), refus de conflit plutôt qu'avertissement,
   maintenant consulté par les surfaces publiques (`surfaces/exclusivite.py`).
6. **Le niveau engageant.** Toujours pas fait — voir `docs/NOYAU.md` §7.
7. **Le commerce et l'hôtellerie-restauration.** Toujours hors scope,
   délibérément — voir `docs/NOYAU.md` §7.

## 5. Économie

Détail et sensibilité dans `docs/ECONOMIE.md`. En résumé, aux hypothèses par
défaut :

| | |
|---|---|
| ARPU | 660 € |
| Marge brute mensuelle par client | 529 € |
| CAC | 2 400 € |
| Retour sur CAC | 4,5 mois |
| LTV / CAC | 6,6x |
| EBITDA mensuel positif | mois 10 |
| Besoin de financement maximal | ~162 k€ (mois 9) |

Le modèle reste au-dessus de 3x de LTV/CAC jusqu'à **8 % de churn mensuel**. Il
est contraint par la capacité commerciale, jamais par la demande.

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

Une verticale, une agglomération, et trois chiffres qui décident de la suite :

| | Cible |
|---|---|
| Clients signés | 12 |
| Part de Citation médiane des clients | ×3 vs relevé initial |
| Taux audit → rendez-vous | ≥ 8 % |

Si la Part de Citation ne triple pas, le produit ne fonctionne pas et aucun
discours ne le sauvera. Si le taux de rendez-vous est sous 5 %, le CAC double et
le modèle passe sous 4x : il faut alors changer de canal, pas d'argumentaire.
