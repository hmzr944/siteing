# La vérification d'identité — comment on empêche une fiche usurpée

```bash
python3 tools/verifie_siren.py                          # smoke-test réseau réel
python3 tools/verifie_siren.py --nom "Boulangerie Martin" --code-postal 69001
python3 -m surfaces noyaux/atelier-ferrand.json \
    --url https://atelier-ferrand.fr --out out/site --require-verified-identity
```

---

## 1. Le problème que ce module résout

La vérification SIRENE (`docs/ECONOMIE.md` §0) prouve qu'une entreprise
**existe**. Elle ne prouve rien sur **qui** est en train de l'inscrire :
n'importe qui peut chercher n'importe quel SIREN et recopier une adresse
publique. Pour un registre dont l'argument central est « vérifié et digne de
confiance des IA », c'est le maillon à traiter avant l'échelle — la première
fiche d'un concurrent inscrite avec de fausses coordonnées démolirait la
promesse d'un coup.

**Deux preuves distinctes, jamais confondues, parce qu'elles ne prouvent pas
la même chose :**

| Preuve | Confirme | Comment | Automatisable |
|---|---|---|---|
| **Existence légale** | l'entreprise nommée existe à cette adresse | recherche SIRENE (`by_siren` / `by_name`) | oui, gratuit (§0 de `docs/ECONOMIE.md`) |
| **Contrôle de l'établissement** | la personne qui inscrit la fiche a accès à un canal de contact déclaré de l'établissement | code envoyé puis resaisi (`issue_code` / `confirm_code`) | non — c'est justement ce qui la rend probante |

Les deux sont modélisées comme deux `Claim` ordinaires
(`citation_audit/dossier.py`) — pas de nouvelle machinerie d'état, le même
vocabulaire vérifié/déclaré/expiré/réfuté que tout le reste du Dossier de
Vérité. `Noyau.is_publication_ready` verrouille la règle : **les deux
doivent être vérifiées, ensemble, avant toute publication** — voir §4.

## 2. Le flux d'inscription

```
1. Saisie du nom (et idéalement du code postal) par l'entreprise
2. by_name(nom, code_postal) -> liste de SIRENE actifs
   - un seul résultat plausible -> proposé, jamais imposé
   - plusieurs -> l'entreprise choisit le sien (voir §3, homonymes)
   - zéro -> refus, rien à vérifier automatiquement (voir §3, introuvable)
3. Confirmation -> by_siren(siren) résout le SIREN choisi, refuse s'il est
   radié (voir §3)
4. claim_existence(entreprise) -> Claim "existence_siren", vérifiée 30 jours
5. issue_code(entity_id, canal, destination) -> code à 6 chiffres envoyé sur
   un canal *déjà déclaré publiquement* (le canal du siège trouvé en (3),
   jamais une destination saisie librement à cette étape — sinon n'importe
   qui pourrait indiquer sa propre adresse)
6. L'entreprise resaisit le code reçu
7. confirm_code(control, submitted) -> Claim "controle_etablissement",
   vérifiée 365 jours
8. Noyau.is_publication_ready devient vrai -> la fiche peut être publiée
```

Chaque étape peut refuser plutôt que deviner (`VerificationRefusee`) : un
SIREN mal formé, introuvable, radié, un canal inconnu, une destination vide,
un code faux ou expiré arrêtent le flux net. Aucune de ces situations ne
produit un résultat partiel silencieusement accepté.

## 3. Les trois cas limites

**SIREN radié.** `by_siren` lit `etat_administratif` du siège renvoyé par
l'API ; toute valeur différente de `"A"` (actif) refuse avec
`VerificationRefusee`. Une entreprise qui a cessé son activité ne peut pas
s'inscrire comme si elle existait encore — le répertoire public est la seule
autorité sur ce point, jamais une déclaration de l'utilisateur.

**Homonymes.** `by_name` ne choisit jamais à la place de l'humain : elle rend
**tous** les établissements actifs qui correspondent, du zéro au plusieurs
centaines pour un nom courant (« Boulangerie Martin » en rend plusieurs
dizaines au niveau national, vérifié en direct contre l'API réelle pendant
la construction de ce module). Le code postal, dès qu'il est connu, filtre
la requête côté serveur et réduit la liste à une poignée de résultats
plausibles. Le choix final reste à l'entreprise qui s'inscrit ; le produit
ne devine jamais « c'est sûrement celui-là ».

**Établissements multiples.** Un Noyau correspond à une entreprise (un
SIREN), qui peut avoir plusieurs établissements (plusieurs SIRET) —
`nombre_etablissements` le rapporte tel quel. Seul le **siège** est résolu
et retenu (`SireneEtablissement.siret_siege`) : c'est l'établissement dont
l'adresse et les coordonnées apparaissent au répertoire public, donc la
cible par défaut du contrôle de canal. Une entreprise à établissements
multiples qui voudrait faire porter le contrôle sur une agence secondaire
plutôt que le siège n'est pas couverte par ce module aujourd'hui — traité
comme un cas de vérification manuelle (courrier au siège), pas automatisé.

## 4. Ce qui est affiché selon le niveau de preuve atteint

| Preuve atteinte | Fiche publique | `Noyau.is_publication_ready` |
|---|---|---|
| Aucune | rien — pas de page, pas de JSON-LD | faux |
| Existence seule | rien — une adresse vérifiée n'est pas une autorisation de publier au nom de l'entreprise | faux |
| Contrôle seul (sans existence) | rien — situation qui ne devrait pas arriver dans un flux normal (§2 vérifie l'existence avant d'émettre un code), gardée en refus par cohérence | faux |
| Les deux, à jour | fiche **minimale** publiable (`surfaces.MINIMAL`, `docs/PLAN.md` §2-3) : identité vérifiée automatiquement, page + JSON-LD | vrai |
| Les deux, à jour, + chantiers/certifications vérifiés sur pièce | fiche **complète** publiable (`surfaces.COMPLET`) | vrai |

**Il n'existe pas de palier intermédiaire où une fiche serait publiée avec
une identité non contrôlée.** C'est délibéré : le registre gratuit publie
sans exception (`docs/PLAN.md` §3), mais « sans exception » porte sur le
*prix*, pas sur la *preuve* — la gratuité n'a jamais voulu dire « sans
vérifier qui inscrit quoi ».

`surfaces.generate()` porte cette règle en code via
`require_verified_identity` (défaut faux, pour ne pas casser les appels
existants qui ne portent pas encore ces preuves) : à vrai, il lève
`VerificationRefusee` tant que `core.is_publication_ready` est faux, avant
d'écrire le moindre fichier. Tout appelant qui publie réellement vers le
web doit le passer à vrai — voir `tests/test_surfaces.py::TestRequireVerifiedIdentity`.

## 5. Ce que ce module ne fait pas (encore)

Il génère le code et sait le vérifier ; il **n'envoie rien lui-même**
(e-mail, SMS) — c'est délibérément laissé à l'appelant, pour ne pas coupler
la logique de vérification à un fournisseur de messagerie particulier.
`issue_code` rend le code en clair une seule fois, à charge pour
l'appelant de le transmettre immédiatement.

Le re-contrôle périodique de l'existence (mensuel, pour rester sous la
limite de ~7 requêtes/seconde de l'API et éviter de la solliciter à chaque
lecture — `docs/ECONOMIE.md` §0) n'est pas encore ordonnancé : `claim_existence`
pose une validité de 30 jours, mais rien ne relance `by_siren` automatiquement
à l'expiration. C'est un morceau d'ingestion périodique, pas de ce module.

Le cas « courrier postal au siège » pour lever l'ambiguïté d'un établissement
secondaire (§3) n'est pas implémenté : `noyau/verification.py` couvre
existence et contrôle de canal, pas encore un troisième mode de preuve.
