# La vérification d'identité — comment on empêche une fiche usurpée

```bash
python3 tools/verifie_siren.py                          # smoke-test réseau réel
python3 tools/verifie_siren.py --nom "Boulangerie Martin" --code-postal 69001
python3 -m surfaces noyaux/atelier-ferrand.json \
    --url https://atelier-ferrand.fr --out out/site --require-verified-identity
```

---

## 1. Le problème, et le dilemme qu'il fallait trancher

La vérification SIRENE (`docs/ECONOMIE.md` §0) prouve qu'une entreprise
**existe**. Elle ne prouve rien sur **qui** est en train de l'inscrire :
n'importe qui peut chercher n'importe quel SIREN et recopier une adresse
publique. Pour un registre dont l'argument central est « vérifié et digne de
confiance des IA », c'est le maillon à traiter avant l'échelle.

Mais une règle stricte « rien sans les deux preuves » aurait un coût
stratégique caché : le registre ne grandirait qu'au rythme des entreprises
qui font la démarche active de s'inscrire, alors que son argument face aux
IA est la **complétude** (« 300 plombiers à Lyon, pas 12 »). La sortie
retenue est un modèle à **deux états, clairement étiquetés** — le modèle
« établissement à revendiquer » de Google Business Profile :

| État | Contenu | Preuve exigée | Étiquette publiée |
|---|---|---|---|
| **Fiche référencée** | données publiques SIRENE uniquement — nom, catégorie, zone, SIREN. Aucune donnée déclarative : pas d'offre, pas de prix, pas de chantier, pas d'avis. | existence (automatique, gratuite) | « non revendiquée », sur la page, dans le JSON-LD et dans `llms.txt` |
| **Fiche vérifiée** | s'ouvre la saisie : tout ce que l'entreprise déclare d'elle-même, selon le palier | existence **+** contrôle de l'établissement | « vérifiée par domaine » ou « vérifiée par courrier » — le canal reste lisible |

La phrase-clé du plan survit intacte : **exister est un droit (référencé),
être cru sur parole se mérite (vérifié).** Et la distinction est honnête
parce qu'elle est publiée : un champ `verification_status` dans le JSON-LD
dit la vérité au lieu de la masquer.

## 2. Les deux canaux de contrôle — deux niveaux de preuve

Un e-mail ou un téléphone librement saisis ne prouvent **rien** : un
usurpateur saisirait les siens. Ils n'existent donc pas comme canaux.
**Vérifié en direct sur l'API réelle** pendant la construction de ce module :
`recherche-entreprises.api.gouv.fr` n'expose aucun canal de contact — ni
e-mail ni téléphone, dans aucun cas, pour aucun établissement. Le répertoire
public fournit une seule destination de confiance : l'**adresse du siège**.
D'où l'architecture :

| Canal | Mécanisme | Preuve | Délai | Coût | Couverture |
|---|---|---|---|---|---|
| **Domaine** (voie express) | code envoyé sur une adresse du domaine propre de l'entreprise — le site déjà déclaré sur la fiche, jamais une saisie libre | contrôle du domaine, comme un certificat TLS ou Search Console | minutes (validité 15 min) | nul | entreprises à domaine propre seulement — un artisan sur Gmail ne peut rien prouver ici, et les domaines de messagerie grand public sont refusés d'office |
| **Courrier** (socle universel) | code posté à l'adresse du siège telle qu'elle figure au répertoire SIRENE | seul qui relève le courrier au siège reçoit le code | ~1 semaine (validité 30 jours ; courrier perdu = renvoi, nouveau code) | ~1-2 € l'envoi — un coût d'acquisition, le prix d'un badge qui vaut quelque chose | toute entreprise diffusible |

Le canal utilisé fait partie de la **nature de la pièce**
(`controle_domaine` / `controle_courrier` dans `EVIDENCE_KINDS`) : le niveau
de preuve reste lisible par la machine dans le dossier, pas seulement dans
une phrase. C'est aussi un argument produit : « vérifié comme un certificat,
pas comme un annuaire ».

## 3. Le flux d'inscription

```
1. Saisie du nom (et idéalement du code postal) par l'entreprise
2. by_name(nom, code_postal) -> liste de SIRENE actifs et diffusibles
   - un seul résultat plausible -> proposé, jamais imposé
   - plusieurs -> l'entreprise choisit le sien (§4, homonymes)
   - zéro -> refus, rien à vérifier automatiquement
3. Confirmation -> by_siren(siren) résout le SIREN choisi ; refuse s'il est
   radié ou en diffusion partielle (§4)
4. claim_existence(entreprise) -> Claim "existence_siren", vérifiée 30 jours
   => la fiche RÉFÉRENCÉE est publiable dès ici, étiquetée « non revendiquée »
5. Revendication, par l'un des deux canaux:
   a. issue_code_domaine(entity, email, site_déclaré) — l'adresse doit être
      sur le domaine du site déjà porté par la fiche
   b. issue_code_courrier(entity, entreprise) — destination = adresse du
      siège au répertoire, jamais une saisie
6. L'entreprise resaisit le code reçu
7. confirm_code(control, submitted) -> Claim "controle_etablissement",
   vérifiée 365 jours, pièce portant le canal
8. verification_status passe à « vérifiée par domaine/courrier »
   => badge vérifié, et la saisie déclarative s'ouvre (palier selon l'offre)
```

Chaque étape peut refuser plutôt que deviner (`VerificationRefusee`) : un
SIREN mal formé, introuvable, radié ou protégé, une adresse hors domaine, un
domaine grand public, un code faux ou expiré arrêtent le flux net. Aucune de
ces situations ne produit un résultat partiel silencieusement accepté.

## 4. Les quatre cas limites

**SIREN radié.** `by_siren` lit `etat_administratif` du siège ; toute valeur
différente de `"A"` refuse. Une entreprise qui a cessé son activité ne peut
pas s'inscrire comme si elle existait encore — le répertoire public est la
seule autorité sur ce point.

**Diffusion partielle.** Certains dirigeants (surtout des
auto-entrepreneurs) ont opté pour la protection de leurs données Sirene :
`statut_diffusion` ou `statut_diffusion_etablissement` vaut alors `"P"`, et
l'API sert littéralement la chaîne `"[NON-DIFFUSIBLE]"` à la place des
champs d'adresse — constaté en réel sur l'API pendant la construction.
Refus explicite aux deux niveaux, **y compris pour la fiche référencée** :
publier une adresse que le dirigeant a fait protéger serait exactement le
faux pas qui fragilise un projet dont l'argument est la confiance. Ces
entreprises n'apparaissent que si le dirigeant s'inscrit lui-même.

**Homonymes.** `by_name` ne choisit jamais à la place de l'humain : elle
rend **tous** les établissements actifs et diffusibles qui correspondent —
des centaines pour un nom courant, vérifié en direct contre l'API réelle.
Le code postal filtre côté serveur et réduit la liste à une poignée. Le
choix final reste à l'entreprise qui s'inscrit.

**Établissements multiples.** Un Noyau correspond à une entreprise (un
SIREN), qui peut avoir plusieurs établissements (plusieurs SIRET) —
`nombre_etablissements` le rapporte tel quel. Seul le **siège** est résolu
et retenu (`SireneEtablissement.siret_siege`) : c'est lui qui reçoit le
courrier de contrôle. Faire porter le contrôle sur une agence secondaire
n'est pas couvert — cas de vérification manuelle, hors de ce module.

## 5. Ce qui est affiché selon le niveau de preuve atteint

| Preuve atteinte | Fiche publique | `verification_status` |
|---|---|---|
| Aucune (ou existence expirée — validité 30 jours) | rien — pas de page, pas de JSON-LD | `None` |
| Existence seule | fiche **référencée** (`surfaces.MINIMAL`) : données publiques SIRENE, étiquetée sur toutes les surfaces | « non revendiquée » |
| Contrôle seul (sans existence à jour) | rien — un contrôle orphelin ne vaut pas mieux qu'une absence de contrôle | `None` |
| Les deux, à jour | fiche vérifiée ; la distribution **complète** (chantiers, budgets, certifications — `surfaces.COMPLET`) ne s'ouvre qu'ici, parce qu'elle est entièrement déclarative | « vérifiée par domaine » / « vérifiée par courrier » |

`surfaces.generate()` porte cette règle via `require_verified_identity`
(défaut faux, pour ne pas casser les appels et fixtures existants) : à vrai,
MINIMAL exige au moins l'existence, COMPLET exige les deux preuves, et le
statut est publié sur la page, dans le JSON-LD (`additionalProperty` /
`verification_status`), dans le miroir Markdown et dans `llms.txt`. Voir
`tests/test_surfaces.py::TestRequireVerifiedIdentity` et
`TestReferencedFicheLabeling`.

La fiche référencée est aussi le canal d'acquisition : « revendiquez votre
fiche » s'adresse à une entreprise qui se voit déjà dans le registre — un
tout autre point de départ que « payez pour exister ».

## 6. Ce que ce module ne fait pas (encore)

Il génère le code et sait le vérifier ; il **n'envoie rien lui-même** — ni
e-mail, ni courrier. C'est délibéré : la logique de vérification n'est
couplée à aucun fournisseur de messagerie ni d'affranchissement.
`issue_code_domaine`/`issue_code_courrier` rendent le code en clair une
seule fois, à charge pour l'appelant de le transmettre.

Le re-contrôle périodique de l'existence (mensuel, pour rester sous la
limite de ~7 requêtes/seconde de l'API — `docs/ECONOMIE.md` §0) n'est pas
encore ordonnancé : `claim_existence` pose une validité de 30 jours, mais
rien ne relance `by_siren` automatiquement à l'expiration. C'est un morceau
d'ingestion périodique, pas de ce module. Il devra aussi surveiller les
passages en diffusion partielle : une fiche référencée dont le dirigeant
protège ses données après coup doit être dépubliée au re-contrôle suivant.

Le contrôle d'une agence secondaire (courrier à un établissement qui n'est
pas le siège) n'est pas implémenté — voir §4.
