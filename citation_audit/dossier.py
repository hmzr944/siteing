"""Le Dossier de Vérité.

C'est la partie *livrée* du produit, celle qui justifie un loyer mensuel là où le
moteur de mesure ne fait que diagnostiquer.

Un dossier est un ensemble d'**affirmations** sur une entreprise (délais, zones,
certifications, garanties, capacités), chacune portant son propre statut de
vérification et les pièces qui l'appuient. La règle qui fait tout le modèle :

    seules les affirmations vérifiées sont publiées vers la couche machine.

Une affirmation déclarée reste visible par un humain, marquée comme déclarée, et
n'est jamais exportée comme un fait. C'est ce qui donne au client une raison de
continuer à fournir des pièces chaque mois, et c'est ce qu'un générateur de sites
en self-serve ne peut structurellement pas produire : il n'a pas de tiers pour
contrôler quoi que ce soit.

Une vérification **expire**. Un dossier qui ne serait vérifié qu'une fois vaudrait
autant qu'une déclaration : la péremption est donc calculée, pas déclarative.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

# Statuts d'une affirmation, du plus faible au plus fort.
DECLARED = "declare"
EXPIRED = "expire"
REFUTED = "refute"
VERIFIED = "verifie"

STATUS_LABELS = {
    DECLARED: "Déclaré",
    EXPIRED: "Vérification expirée",
    REFUTED: "Réfuté",
    VERIFIED: "Vérifié",
}

# Regroupements d'affirmations. Un dossier n'est pas une liste plate de vingt
# lignes: il se lit par grappes.
CLUSTERS = {
    "identite": "Identité et existence légale",
    "capacite": "Ce que l'entreprise peut faire",
    "engagement": "Ce qu'elle s'engage à tenir",
    "couverture": "Où elle intervient",
}

# Durée de validité par défaut d'une vérification, en jours.
DEFAULT_VALIDITY_DAYS = 365

# Natures de pièces acceptées en preuve.
EVIDENCE_KINDS = {
    "immatriculation": "Extrait d'immatriculation",
    "assurance": "Attestation d'assurance",
    "certification": "Certificat délivré par un organisme",
    "facture": "Facture acquittée",
    "contrat": "Contrat signé",
    "releve": "Relevé d'exploitation",
    "attestation": "Attestation d'un tiers",
}


@dataclass(frozen=True)
class Evidence:
    """Une pièce qui appuie une affirmation.

    On stocke une **référence**, jamais la pièce elle-même: le dossier est un
    document publiable, et publier une facture client serait une faute.
    """

    kind: str
    reference: str
    issued_on: date
    checked_by: str

    @property
    def kind_label(self) -> str:
        return EVIDENCE_KINDS.get(self.kind, self.kind)

    @classmethod
    def from_dict(cls, data: dict) -> "Evidence":
        if data["kind"] not in EVIDENCE_KINDS:
            raise ValueError(f"nature de pièce inconnue: {data['kind']!r}")
        return cls(
            kind=data["kind"],
            reference=data["reference"],
            issued_on=date.fromisoformat(data["issued_on"]),
            checked_by=data["checked_by"],
        )


@dataclass
class Claim:
    """Une affirmation sur l'entreprise, et son niveau de preuve."""

    key: str
    label: str
    value: str
    cluster: str
    evidence: list[Evidence] = field(default_factory=list)
    verified_on: date | None = None
    valid_until: date | None = None
    refuted: bool = False
    # Vocabulaire schema.org, quand l'affirmation s'y projette. Sans
    # correspondance, l'affirmation reste lisible par un humain mais n'est pas
    # publiée comme propriété structurée.
    schema_property: str | None = None
    # Valeur destinée à la machine, quand elle diffère de la phrase lue par un
    # humain. « SARL immatriculée au RCS de Bordeaux depuis mars 2009 » se lit
    # bien et n'est pas une date; `foundingDate` attend « 2009-03 ». Publier de
    # la prose dans une propriété typée produit du structuré malformé, c'est à
    # dire exactement le défaut que ce produit est censé corriger.
    schema_value: str | None = None

    @property
    def machine_value(self) -> str:
        return self.schema_value if self.schema_value is not None else self.value

    def status(self, today: date | None = None) -> str:
        today = today or date.today()
        if self.refuted:
            return REFUTED
        if not self.evidence or self.verified_on is None:
            return DECLARED
        if self.valid_until is not None and self.valid_until < today:
            return EXPIRED
        return VERIFIED

    def status_label(self, today: date | None = None) -> str:
        return STATUS_LABELS[self.status(today)]

    def is_publishable(self, today: date | None = None) -> bool:
        """Seul le vérifié franchit la frontière vers la couche machine."""
        return self.status(today) == VERIFIED

    def days_until_expiry(self, today: date | None = None) -> int | None:
        if self.valid_until is None:
            return None
        return (self.valid_until - (today or date.today())).days

    @classmethod
    def from_dict(cls, data: dict) -> "Claim":
        if data["cluster"] not in CLUSTERS:
            raise ValueError(f"grappe inconnue: {data['cluster']!r}")
        evidence = [Evidence.from_dict(raw) for raw in data.get("evidence", ())]
        verified_on = (
            date.fromisoformat(data["verified_on"]) if data.get("verified_on") else None
        )
        valid_until = (
            date.fromisoformat(data["valid_until"]) if data.get("valid_until") else None
        )
        # Une vérification sans échéance explicite en reçoit une: c'est la
        # péremption qui distingue un dossier tenu d'un dossier constitué une fois.
        if verified_on is not None and valid_until is None:
            valid_until = verified_on + timedelta(days=DEFAULT_VALIDITY_DAYS)
        return cls(
            key=data["key"],
            label=data["label"],
            value=str(data["value"]),
            cluster=data["cluster"],
            evidence=evidence,
            verified_on=verified_on,
            valid_until=valid_until,
            refuted=bool(data.get("refuted", False)),
            schema_property=data.get("schema_property"),
            schema_value=data.get("schema_value"),
        )


@dataclass
class Dossier:
    """Le référentiel d'une entreprise, humainement lisible et publiable."""

    entity_id: str
    name: str
    category: str
    zone: str
    claims: list[Claim]
    legal_id: str | None = None          # SIREN, SIRET, numéro d'immatriculation
    contact_url: str | None = None
    photo_url: str | None = None
    updated_on: date | None = None

    def __post_init__(self) -> None:
        keys = [c.key for c in self.claims]
        duplicates = {k for k in keys if keys.count(k) > 1}
        if duplicates:
            raise ValueError(f"affirmations en doublon: {sorted(duplicates)}")

    # -- lecture -------------------------------------------------------------

    def by_cluster(self, today: date | None = None) -> list[tuple[str, str, list[Claim]]]:
        """Affirmations groupées, vérifiées d'abord à l'intérieur d'une grappe."""
        order = {VERIFIED: 0, EXPIRED: 1, DECLARED: 2, REFUTED: 3}
        grouped = []
        for key, label in CLUSTERS.items():
            claims = [c for c in self.claims if c.cluster == key]
            if not claims:
                continue
            claims.sort(key=lambda c: (order[c.status(today)], c.label))
            grouped.append((key, label, claims))
        return grouped

    def publishable(self, today: date | None = None) -> list[Claim]:
        return [c for c in self.claims if c.is_publishable(today)]

    def counts(self, today: date | None = None) -> dict[str, int]:
        tally = {status: 0 for status in STATUS_LABELS}
        for claim in self.claims:
            tally[claim.status(today)] += 1
        return tally

    def verified_ratio(self, today: date | None = None) -> float:
        if not self.claims:
            return 0.0
        return len(self.publishable(today)) / len(self.claims)

    def last_verified_on(self, today: date | None = None) -> date | None:
        dates = [c.verified_on for c in self.publishable(today) if c.verified_on]
        return max(dates) if dates else None

    def expiring_soon(self, within_days: int = 60, today: date | None = None) -> list[Claim]:
        """Vérifications à renouveler. C'est le plan de travail du mois."""
        today = today or date.today()
        soon = [
            c
            for c in self.publishable(today)
            if (days := c.days_until_expiry(today)) is not None and days <= within_days
        ]
        soon.sort(key=lambda c: c.valid_until or today)
        return soon

    def stale(self, today: date | None = None) -> list[Claim]:
        """Affirmations qui ne tiennent plus: expirées, réfutées, jamais prouvées."""
        return [c for c in self.claims if not c.is_publishable(today)]

    # -- chargement ----------------------------------------------------------

    @classmethod
    def from_dict(cls, data: dict) -> "Dossier":
        return cls(
            entity_id=data["entity_id"],
            name=data["name"],
            category=data["category"],
            zone=data["zone"],
            claims=[Claim.from_dict(raw) for raw in data["claims"]],
            legal_id=data.get("legal_id"),
            contact_url=data.get("contact_url"),
            photo_url=data.get("photo_url"),
            updated_on=(
                date.fromisoformat(data["updated_on"]) if data.get("updated_on") else None
            ),
        )

    @classmethod
    def load(cls, path: str | Path) -> "Dossier":
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))
