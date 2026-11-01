"""Vérification d'identité: existence légale, puis contrôle de propriété.

Deux preuves distinctes, jamais confondues, parce qu'elles ne prouvent pas la
même chose.

**L'existence** (`by_siren`/`by_name`) confirme qu'une entreprise nommée
existe réellement à cette adresse, via le répertoire public SIRENE
(``recherche-entreprises.api.gouv.fr``, données INSEE, gratuit, sans
authentification). Elle ne prouve rien sur qui fait la demande : n'importe
qui peut chercher n'importe quel SIREN. Elle suffit à une fiche
**référencée** — données publiques uniquement, étiquetée « non revendiquée ».

**Le contrôle de propriété** (`issue_code_domaine`/`issue_code_courrier`,
puis `confirm_code`) confirme que la personne qui revendique la fiche
contrôle réellement l'établissement. Deux niveaux, parce que les canaux ne
prouvent pas la même chose :

* **par domaine** — un code envoyé sur une adresse e-mail du domaine propre
  de l'entreprise (le site déclaré sur la fiche). Contrôler
  ``contact@atelier-ferrand.fr`` prouve le contrôle du domaine
  ``atelier-ferrand.fr`` — le mécanisme des certificats TLS et de Search
  Console. Rapide, automatique, mais ne couvre que les entreprises à domaine
  propre : un artisan sur Gmail ne peut rien prouver par ce chemin.
* **par courrier** — un code posté à l'adresse du siège telle qu'elle figure
  au répertoire SIRENE. Universel (toute entreprise diffusible a une adresse
  publique), lent (~1 semaine), coûte le prix d'un timbre — le prix d'un
  badge qui vaut quelque chose.

Un e-mail ou un téléphone librement saisis ne prouvent **rien** : un
usurpateur saisirait les siens. Ils n'existent donc pas comme canaux ici.
Vérification faite en direct sur l'API réelle : SIRENE n'expose aucun canal
de contact (ni e-mail ni téléphone), dans aucun cas — le courrier au siège
est le seul canal que le répertoire public fournisse, d'où son rôle de socle.

**Le statut de diffusion est respecté strictement.** Un dirigeant qui a opté
pour la diffusion partielle de ses données Sirene (``statut_diffusion`` à
``"P"``, champs servis comme ``[NON-DIFFUSIBLE]``) n'apparaît jamais, même
en fiche référencée : le refus est explicite, pas un affichage dégradé.

Voir ``noyau.noyau.Noyau.verification_status`` et ``docs/VERIFICATION.md``
pour ce que chaque niveau de preuve autorise à publier.
"""

from __future__ import annotations

import json
import re
import secrets
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from citation_audit.dossier import VERIFIED, Claim, Evidence

SIRENE_ENDPOINT = "https://recherche-entreprises.api.gouv.fr/search"

# Code SIRENE de l'INSEE pour un établissement en activité. Toute autre
# valeur (fermeture, cessation) signifie radié: jamais vérifiable comme actif.
ACTIF = "A"

# Statut de diffusion Sirene: "O" = diffusible, "P" = diffusion partielle
# (le dirigeant a demandé la protection de ses données; l'API sert alors
# "[NON-DIFFUSIBLE]" à la place des champs d'adresse). Tout ce qui n'est pas
# "O" est refusé, y compris pour une fiche référencée.
DIFFUSIBLE = "O"

# Les deux canaux de contrôle, du plus rapide au plus universel. Un canal
# librement saisi (e-mail quelconque, téléphone) n'existe pas: il ne
# prouverait rien.
DOMAINE = "domaine"
COURRIER = "courrier"
CANAUX = (DOMAINE, COURRIER)

# Durées de vie des codes, par canal. Le code de domaine arrive en secondes:
# une fenêtre courte limite les essais répétés. Le code postal met des jours
# à arriver, et un courrier se perd: 30 jours, puis renvoi.
DOMAINE_VALIDITY_MINUTES = 15
COURRIER_VALIDITY_DAYS = 30

# Domaines de messagerie grand public: une adresse chez eux ne prouve le
# contrôle d'aucune entreprise, quel que soit le nom devant l'arobase.
FREE_MAIL_DOMAINS = frozenset({
    "gmail.com", "googlemail.com", "outlook.com", "outlook.fr", "hotmail.com",
    "hotmail.fr", "live.com", "live.fr", "yahoo.com", "yahoo.fr", "icloud.com",
    "me.com", "orange.fr", "wanadoo.fr", "free.fr", "sfr.fr", "neuf.fr",
    "laposte.net", "bbox.fr", "gmx.fr", "gmx.com", "protonmail.com",
    "proton.me", "aol.com",
})

# Clés des deux affirmations, partagées avec `noyau.noyau.Noyau` pour qu'il
# n'existe qu'un seul endroit où ces chaînes sont écrites.
IDENTITY_EXISTENCE_KEY = "existence_siren"
IDENTITY_CONTROL_KEY = "controle_etablissement"

# Les statuts de vérification d'une fiche, tels qu'ils sont publiés — sur la
# page, dans le JSON-LD, dans llms.txt. Un agent doit pouvoir lire la
# différence entre « le répertoire public dit que ça existe » et « la bonne
# personne a prouvé qu'elle contrôle l'établissement », et par quel canal.
NON_REVENDIQUEE = "non revendiquée"
VERIFIEE_DOMAINE = "vérifiée par domaine"
VERIFIEE_COURRIER = "vérifiée par courrier"
STATUTS_VERIFIES = (VERIFIEE_DOMAINE, VERIFIEE_COURRIER)


class VerificationRefusee(Exception):
    """Refus explicite: mieux vaut une inscription bloquée qu'une identité
    mal résolue. Jamais un résultat partiel deviné à la place de l'humain."""


# -- existence légale (SIRENE) --------------------------------------------------


@dataclass(frozen=True)
class SireneEtablissement:
    siren: str
    nom: str
    siret_siege: str
    adresse: str
    code_postal: str
    commune: str
    etat_administratif: str
    statut_diffusion: str
    statut_diffusion_etablissement: str
    date_creation: str | None
    nombre_etablissements: int

    @property
    def est_actif(self) -> bool:
        return self.etat_administratif == ACTIF

    @property
    def est_diffusible(self) -> bool:
        """Diffusible aux deux niveaux, entreprise et établissement. Le
        moindre "P" suffit à tout refuser: publier une adresse que le
        dirigeant a fait protéger serait exactement le faux pas qui
        fragilise un projet dont l'argument est la confiance."""
        return (
            self.statut_diffusion == DIFFUSIBLE
            and self.statut_diffusion_etablissement == DIFFUSIBLE
        )


def _parse(raw: dict) -> SireneEtablissement:
    siege = raw.get("siege", {})
    return SireneEtablissement(
        siren=raw["siren"],
        nom=raw.get("nom_complet") or raw.get("nom_raison_sociale") or "",
        siret_siege=siege.get("siret", ""),
        adresse=siege.get("adresse", ""),
        code_postal=siege.get("code_postal", ""),
        commune=siege.get("libelle_commune", ""),
        etat_administratif=siege.get("etat_administratif", ""),
        statut_diffusion=raw.get("statut_diffusion", ""),
        statut_diffusion_etablissement=siege.get("statut_diffusion_etablissement", ""),
        date_creation=raw.get("date_creation"),
        nombre_etablissements=raw.get("nombre_etablissements", 0),
    )


def _fetch(url: str) -> dict:
    """Le seul point qui parle au réseau. Toujours injectable dans les tests:
    un test qui appellerait le vrai répertoire serait lent et instable, pour
    un résultat qu'un enregistrement suffit à vérifier."""
    request = urllib.request.Request(url, headers={"User-Agent": "source-primaire/1"})
    with urllib.request.urlopen(request, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


def by_siren(siren: str, fetch=_fetch) -> SireneEtablissement:
    """Résout un SIREN connu. Refuse s'il est introuvable, radié, ou en
    diffusion partielle.

    Ne devine jamais: un SIREN mal formé ou absent du répertoire est un refus,
    pas une meilleure estimation.
    """
    digits = re.sub(r"\D", "", siren)
    if len(digits) != 9:
        raise VerificationRefusee(f"SIREN mal formé: {siren!r} (9 chiffres attendus)")
    payload = fetch(f"{SIRENE_ENDPOINT}?q={digits}&per_page=1")
    match = next((r for r in payload.get("results", ()) if r["siren"] == digits), None)
    if match is None:
        raise VerificationRefusee(f"SIREN {digits} introuvable au répertoire SIRENE")
    entreprise = _parse(match)
    if not entreprise.est_actif:
        raise VerificationRefusee(f"SIREN {digits} radié (état {entreprise.etat_administratif!r})")
    if not entreprise.est_diffusible:
        raise VerificationRefusee(
            f"SIREN {digits} en diffusion partielle: le dirigeant a demandé la "
            "protection de ses données Sirene, aucune fiche n'est publiée — "
            "même référencée — tant qu'il ne s'inscrit pas lui-même."
        )
    return entreprise


def by_name(nom: str, code_postal: str | None = None, fetch=_fetch) -> list[SireneEtablissement]:
    """Cherche par nom, éventuellement affiné par code postal.

    Rend zéro, un, ou plusieurs homonymes — ne choisit jamais à la place de
    l'humain. Un nom d'entreprise commun (« Boulangerie Martin ») en produit
    des centaines au niveau national: c'est le cas ordinaire, pas l'exception,
    d'où l'intérêt du filtre par code postal dès qu'il est connu. Les radiés
    et les diffusions partielles sont écartés d'office: ni les uns ni les
    autres ne peuvent donner une fiche, même référencée.
    """
    query = urllib.parse.quote(nom)
    url = f"{SIRENE_ENDPOINT}?q={query}&per_page=10"
    if code_postal:
        url += f"&code_postal={urllib.parse.quote(code_postal)}"
    payload = fetch(url)
    entreprises = [_parse(r) for r in payload.get("results", ())]
    return [e for e in entreprises if e.est_actif and e.est_diffusible]


def claim_existence(entreprise: SireneEtablissement, today: date | None = None) -> Claim:
    """L'affirmation d'existence légale, prête à rejoindre ``Noyau.claims``.

    Réutilise le vocabulaire de pièce déjà existant (``immatriculation``):
    une résolution SIRENE est l'équivalent automatisé d'un extrait
    d'immatriculation, pas une nouvelle nature de preuve. C'est le niveau de
    preuve de la fiche **référencée** — il autorise la publication des
    données publiques du répertoire, étiquetées « non revendiquée », jamais
    la moindre donnée déclarative.
    """
    moment = today or date.today()
    return Claim(
        key=IDENTITY_EXISTENCE_KEY,
        label="Existence légale",
        value=(
            f"{entreprise.nom}, SIREN {entreprise.siren}, "
            f"{entreprise.adresse or entreprise.commune}"
        ),
        cluster="identite",
        schema_property="foundingDate",
        schema_value=entreprise.date_creation[:7] if entreprise.date_creation else None,
        evidence=[
            Evidence(
                kind="immatriculation",
                reference=f"SIREN {entreprise.siren}",
                issued_on=moment,
                checked_by="INSEE Sirene (répertoire public, vérification automatique)",
            )
        ],
        verified_on=moment,
        # Une existence légale se re-contrôle périodiquement (radiations,
        # cessations, passages en diffusion partielle), jamais vérifiée une
        # fois pour toutes: la limite de débit de l'API (~7 req/s) impose un
        # cache daté plutôt qu'une revérification à chaque lecture.
        valid_until=moment + timedelta(days=30),
    )


# -- contrôle de propriété (code émis, puis resaisi) -----------------------------


@dataclass(frozen=True)
class ControlCode:
    """Un code émis, à confirmer avant expiration.

    Ne porte jamais le code en clair au-delà de sa création: seul un hash
    comparable est conservé, pour qu'une fuite de l'objet stocké entre
    l'émission et la confirmation ne livre pas le code lui-même.
    """

    entity_id: str
    canal: str
    destination_masquee: str
    code_hash: str
    issued_at: datetime
    expires_at: datetime

    def is_expired(self, now: datetime | None = None) -> bool:
        return (now or datetime.now(timezone.utc)) > self.expires_at


def _hash_code(code: str) -> str:
    import hashlib

    return hashlib.sha256(code.encode("utf-8")).hexdigest()


def _mask_email(destination: str) -> str:
    local, _, domain = destination.partition("@")
    if not domain:
        return "***"
    return f"{local[:1]}***@{domain}"


def _domain_of(url: str) -> str:
    """Le domaine d'un site déclaré, normalisé pour comparaison."""
    parsed = urllib.parse.urlparse(url if "//" in url else f"https://{url}")
    host = (parsed.netloc or "").lower().split(":")[0]
    return host.removeprefix("www.")


def _issue(
    entity_id: str, canal: str, destination_masquee: str,
    validity: timedelta, now: datetime | None = None,
) -> tuple[ControlCode, str]:
    moment = now or datetime.now(timezone.utc)
    code = f"{secrets.randbelow(1_000_000):06d}"
    control = ControlCode(
        entity_id=entity_id,
        canal=canal,
        destination_masquee=destination_masquee,
        code_hash=_hash_code(code),
        issued_at=moment,
        expires_at=moment + validity,
    )
    return control, code


def issue_code_domaine(
    entity_id: str, email: str, site_url: str, now: datetime | None = None
) -> tuple[ControlCode, str]:
    """Émet un code pour la voie express: une adresse du domaine propre.

    ``site_url`` est le site déjà déclaré sur la fiche — jamais une saisie
    libre à cette étape, sinon l'usurpateur déclarerait le sien. L'adresse
    doit être sur ce domaine (ou un de ses sous-domaines): recevoir le code
    là prouve le contrôle du domaine, comme un certificat TLS. Un domaine de
    messagerie grand public est refusé d'office — une adresse Gmail ne
    prouve le contrôle d'aucune entreprise, quel que soit le nom devant
    l'arobase.

    Rend le code en clair une seule fois: à l'appelant de l'envoyer, ce
    module ne parle pas aux serveurs de messagerie.
    """
    address = email.strip().lower()
    _, _, email_domain = address.partition("@")
    if not email_domain:
        raise VerificationRefusee(f"adresse e-mail mal formée: {email!r}")
    site_domain = _domain_of(site_url.strip()) if site_url and site_url.strip() else ""
    if not site_domain:
        raise VerificationRefusee(
            "aucun site déclaré sur la fiche: la voie du domaine exige un "
            "domaine propre — passer par le courrier au siège."
        )
    if site_domain in FREE_MAIL_DOMAINS or email_domain in FREE_MAIL_DOMAINS:
        raise VerificationRefusee(
            f"domaine de messagerie grand public ({email_domain}): il ne "
            "prouve le contrôle d'aucune entreprise — passer par le courrier "
            "au siège."
        )
    if email_domain != site_domain and not email_domain.endswith(f".{site_domain}"):
        raise VerificationRefusee(
            f"l'adresse {address!r} n'est pas sur le domaine déclaré "
            f"({site_domain}): elle ne prouverait rien."
        )
    return _issue(
        entity_id, DOMAINE, _mask_email(address),
        timedelta(minutes=DOMAINE_VALIDITY_MINUTES), now,
    )


def issue_code_courrier(
    entity_id: str, entreprise: SireneEtablissement, now: datetime | None = None
) -> tuple[ControlCode, str]:
    """Émet un code pour la voie universelle: courrier à l'adresse du siège.

    La destination vient du répertoire SIRENE, jamais d'une saisie — c'est ce
    qui fait la preuve: seul quelqu'un qui relève le courrier au siège
    recevra le code. Lent (~1 semaine), coûte un affranchissement, couvre
    toute entreprise diffusible — y compris celles sans domaine ni site, qui
    sont précisément le cœur de cible.

    Rend le code en clair une seule fois: à l'appelant d'imprimer et poster,
    ce module ne parle pas à La Poste.
    """
    if not entreprise.est_diffusible:
        raise VerificationRefusee(
            f"SIREN {entreprise.siren} en diffusion partielle: pas d'adresse "
            "publique à laquelle poster un code."
        )
    if not entreprise.adresse.strip():
        raise VerificationRefusee(
            f"SIREN {entreprise.siren}: aucune adresse de siège au répertoire, "
            "rien à poster."
        )
    masque = f"courrier au siège, {entreprise.code_postal} {entreprise.commune}".strip()
    return _issue(
        entity_id, COURRIER, masque, timedelta(days=COURRIER_VALIDITY_DAYS), now
    )


def confirm_code(
    control: ControlCode, submitted: str, today: date | None = None, now: datetime | None = None
) -> Claim:
    """Vérifie le code resaisi. Refuse sur code faux ou expiré — jamais de
    seconde chance silencieuse: un appelant qui veut réessayer doit émettre
    un nouveau code, avec une nouvelle fenêtre d'expiration (pour un courrier
    perdu, un renvoi).

    La nature de la pièce produite porte le canal (``controle_domaine`` /
    ``controle_courrier``): le niveau de preuve reste lisible par la machine
    dans le dossier, pas seulement dans une phrase.
    """
    if control.is_expired(now):
        raise VerificationRefusee("code expiré: demandez-en un nouveau")
    if not secrets.compare_digest(_hash_code(submitted.strip()), control.code_hash):
        raise VerificationRefusee("code incorrect")
    if control.canal not in CANAUX:
        raise VerificationRefusee(f"canal inconnu: {control.canal!r} (attendu: {CANAUX})")
    moment = today or date.today()
    return Claim(
        key=IDENTITY_CONTROL_KEY,
        label="Contrôle de l'établissement",
        value=(
            f"Contrôle vérifié par {control.canal} ({control.destination_masquee})"
        ),
        cluster="identite",
        evidence=[
            Evidence(
                kind=f"controle_{control.canal}",
                reference=control.destination_masquee,
                issued_on=moment,
                checked_by="Source Primaire (code de vérification)",
            )
        ],
        verified_on=moment,
        valid_until=moment + timedelta(days=365),
    )


# -- statut de vérification ------------------------------------------------------


def verification_status(claims: list[Claim], today: date | None = None) -> str | None:
    """Le statut publiable d'une fiche, déduit de ses affirmations d'identité.

    * ``None`` — l'existence n'est pas vérifiée (ou plus: la vérification
      SIRENE a 30 jours de validité). Rien n'est publiable, pas même une
      fiche référencée.
    * ``NON_REVENDIQUEE`` — existence vérifiée, contrôle absent. La fiche
      référencée: données publiques du répertoire uniquement, étiquetée.
    * ``VERIFIEE_DOMAINE`` / ``VERIFIEE_COURRIER`` — les deux preuves. Le
      canal reste visible: un agent peut lire par quel mécanisme la
      revendication a été prouvée.

    Le canal est lu dans la **nature de la pièce** du contrôle, jamais dans
    une phrase: c'est la donnée, pas sa mise en mots, qui fait foi.
    """
    moment = today or date.today()
    existence = any(
        c.key == IDENTITY_EXISTENCE_KEY and c.status(moment) == VERIFIED for c in claims
    )
    if not existence:
        return None
    control = next(
        (
            c for c in claims
            if c.key == IDENTITY_CONTROL_KEY and c.status(moment) == VERIFIED
        ),
        None,
    )
    if control is None:
        return NON_REVENDIQUEE
    kinds = {e.kind for e in control.evidence}
    if "controle_domaine" in kinds:
        return VERIFIEE_DOMAINE
    if "controle_courrier" in kinds:
        return VERIFIEE_COURRIER
    # Un contrôle dont la pièce ne nomme aucun canal connu ne devrait pas
    # exister; s'il existe, il ne vaut pas mieux qu'une absence de contrôle.
    return NON_REVENDIQUEE
