"""Vérification d'identité: existence légale, puis contrôle de propriété.

Deux preuves distinctes, jamais confondues, parce qu'elles ne prouvent pas la
même chose.

**L'existence** (`by_siren`/`by_name`) confirme qu'une entreprise nommée
existe réellement à cette adresse, via le répertoire public SIRENE
(``recherche-entreprises.api.gouv.fr``, données INSEE, gratuit, sans
authentification). Elle ne prouve rien sur qui fait la demande : n'importe
qui peut chercher n'importe quel SIREN.

**Le contrôle de propriété** (`issue_code`/`confirm_code`) confirme que la
personne qui inscrit la fiche a effectivement accès à un canal de contact
déclaré de l'établissement — un code envoyé, puis resaisi. C'est ce qui
transforme « une entreprise qui existe » en « la bonne personne inscrit sa
propre entreprise ».

Publier une fiche sans les deux, c'est ouvrir la porte à l'usurpation : la
première fiche d'un concurrent inscrite avec de fausses coordonnées démolit
la promesse « source vérifiée » d'un coup. Voir ``noyau.noyau.Noyau.is_publication_ready``,
qui verrouille cette règle plutôt que de la laisser à la discipline d'un
appelant.
"""

from __future__ import annotations

import json
import re
import secrets
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from citation_audit.dossier import Claim, Evidence

SIRENE_ENDPOINT = "https://recherche-entreprises.api.gouv.fr/search"

# Code SIRENE de l'INSEE pour un établissement en activité. Toute autre
# valeur (fermeture, cessation) signifie radié: jamais vérifiable comme actif.
ACTIF = "A"

# Le canal de contrôle: l'un ou l'autre, jamais devinable à partir de l'autre.
EMAIL = "email"
TELEPHONE = "telephone"
CANAUX = (EMAIL, TELEPHONE)

# Durée de vie d'un code envoyé. Assez court pour limiter une attaque par
# essais répétés, assez long pour qu'un dirigeant ait le temps de le lire.
CODE_VALIDITY_MINUTES = 15

# Clés des deux affirmations, partagées avec `noyau.noyau.Noyau.is_publication_ready`
# pour qu'il n'existe qu'un seul endroit où ces chaînes sont écrites.
IDENTITY_EXISTENCE_KEY = "existence_siren"
IDENTITY_CONTROL_KEY = "controle_etablissement"


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
    date_creation: str | None
    nombre_etablissements: int

    @property
    def est_actif(self) -> bool:
        return self.etat_administratif == ACTIF


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
    """Résout un SIREN connu. Refuse s'il est introuvable ou radié.

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
    return entreprise


def by_name(nom: str, code_postal: str | None = None, fetch=_fetch) -> list[SireneEtablissement]:
    """Cherche par nom, éventuellement affiné par code postal.

    Rend zéro, un, ou plusieurs homonymes — ne choisit jamais à la place de
    l'humain. Un nom d'entreprise commun (« Boulangerie Martin ») en produit
    des centaines au niveau national: c'est le cas ordinaire, pas l'exception,
    d'où l'intérêt du filtre par code postal dès qu'il est connu.
    """
    query = urllib.parse.quote(nom)
    url = f"{SIRENE_ENDPOINT}?q={query}&per_page=10"
    if code_postal:
        url += f"&code_postal={urllib.parse.quote(code_postal)}"
    payload = fetch(url)
    return [_parse(r) for r in payload.get("results", ()) if _parse(r).est_actif]


def claim_existence(entreprise: SireneEtablissement, today: date | None = None) -> Claim:
    """L'affirmation d'existence légale, prête à rejoindre ``Noyau.claims``.

    Réutilise le vocabulaire de pièce déjà existant (``immatriculation``):
    une résolution SIRENE est l'équivalent automatisé d'un extrait
    d'immatriculation, pas une nouvelle nature de preuve.
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
        # cessations), jamais vérifiée une fois pour toutes: voir la limite
        # de débit de l'API (§ module docstring) qui impose un cache daté
        # plutôt qu'une revérification à chaque lecture.
        valid_until=moment + timedelta(days=30),
    )


# -- contrôle de propriété (code envoyé, puis resaisi) --------------------------


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


def _mask(destination: str, canal: str) -> str:
    if canal == EMAIL:
        local, _, domain = destination.partition("@")
        if not domain:
            return "***"
        visible = local[:1]
        return f"{visible}***@{domain}"
    digits = re.sub(r"\D", "", destination)
    return f"{'*' * max(0, len(digits) - 2)}{digits[-2:]}" if digits else "**"


def issue_code(
    entity_id: str, canal: str, destination: str, now: datetime | None = None
) -> tuple[ControlCode, str]:
    """Émet un code à six chiffres. Rend le code en clair une seule fois:
    à l'appelant de le transmettre (e-mail, SMS) — ce module ne l'envoie pas,
    il ne fait que le générer et savoir le vérifier."""
    if canal not in CANAUX:
        raise VerificationRefusee(f"canal inconnu: {canal!r} (attendu: {CANAUX})")
    if not destination.strip():
        raise VerificationRefusee("destination vide: aucun code à émettre")
    moment = now or datetime.now(timezone.utc)
    code = f"{secrets.randbelow(1_000_000):06d}"
    control = ControlCode(
        entity_id=entity_id,
        canal=canal,
        destination_masquee=_mask(destination, canal),
        code_hash=_hash_code(code),
        issued_at=moment,
        expires_at=moment + timedelta(minutes=CODE_VALIDITY_MINUTES),
    )
    return control, code


def confirm_code(
    control: ControlCode, submitted: str, today: date | None = None, now: datetime | None = None
) -> Claim:
    """Vérifie le code resaisi. Refuse sur code faux ou expiré — jamais de
    seconde chance silencieuse: un appelant qui veut réessayer doit émettre
    un nouveau code, avec une nouvelle fenêtre d'expiration."""
    if control.is_expired(now):
        raise VerificationRefusee("code expiré: demandez-en un nouveau")
    if not secrets.compare_digest(_hash_code(submitted.strip()), control.code_hash):
        raise VerificationRefusee("code incorrect")
    moment = today or date.today()
    return Claim(
        key=IDENTITY_CONTROL_KEY,
        label="Contrôle de l'établissement",
        value=f"Contrôle du canal {control.canal} confirmé ({control.destination_masquee})",
        cluster="identite",
        evidence=[
            Evidence(
                kind="controle_canal",
                reference=control.destination_masquee,
                issued_on=moment,
                checked_by="Source Primaire (code de vérification)",
            )
        ],
        verified_on=moment,
        valid_until=moment + timedelta(days=365),
    )
