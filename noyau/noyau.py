"""Le Noyau: assemblage et règles de publication.

Le Noyau réunit trois matières et une seule règle.

Les matières: les **chantiers** (preuve d'intervention, localisée et datée), les
**budgets constatés** (distributions adossées à des pièces) et les **attributs
d'autorité** (certifications, assurances, immatriculation), qui réutilisent le
modèle d'affirmation vérifiée du Dossier de Vérité.

La règle, la même depuis le début du projet: **seul ce qui franchit son seuil de
preuve est publié vers la surface machine.** Le reste est visible par un humain,
marqué comme non prouvé, et forme le plan de travail du mois. C'est ce plan de
travail qui justifie un abonnement: un Noyau constitué une fois se périme.

Trois seuils, trois raisons:

* un chantier ne suffit pas à prouver qu'on intervient dans un quartier, il faut
  un motif répété;
* cinq chantiers comparables au minimum pour qu'une médiane de budget ne soit
  pas du bruit;
* une certification n'est un attribut d'autorité que si elle est en cours de
  validité, la date faisant toute la différence.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

# Le modèle d'affirmation vérifiée vient du Dossier de Vérité. Il a vocation à
# rejoindre ce paquet lors de la réorganisation, mais le dupliquer maintenant
# ferait diverger deux définitions de la vérification, ce qui est le pire des
# deux mondes.
from citation_audit.dossier import Claim, Evidence, VERIFIED

from .budget import BudgetBloque, BudgetConstate, aggregate
from .chantier import NATURES, Chantier, TerritoirePreuve
from .territoire import QUARTIER, Referentiel, Territoire
from .verification import STATUTS_VERIFIES, verification_status

# Nombre de chantiers requis pour qu'une implantation territoriale soit publiée.
# Un chantier isolé aux Chartrons ne fait pas de vous un spécialiste des
# Chartrons, et le publier comme tel serait fabriquer de la preuve.
MIN_CHANTIERS_TERRITOIRE = 3


@dataclass(frozen=True)
class Assertion:
    """Une affirmation prête à être publiée vers la surface machine."""

    kind: str                 # "territoire", "budget", "autorite", "capacite"
    subject: str              # code territoire, clé de budget, clé d'attribut
    statement: str            # la phrase publiée
    evidence_count: int
    observed_from: date | None = None
    observed_to: date | None = None
    payload: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        data = {
            "kind": self.kind,
            "subject": self.subject,
            "statement": self.statement,
            "evidence_count": self.evidence_count,
        }
        if self.observed_from:
            data["observed_from"] = self.observed_from.isoformat()
        if self.observed_to:
            data["observed_to"] = self.observed_to.isoformat()
        if self.payload:
            data["payload"] = self.payload
        return data


@dataclass(frozen=True)
class Manque:
    """Ce qui empêche une publication, et ce qu'il faut aller chercher."""

    kind: str
    subject: str
    have: int
    need: int
    action: str

    @property
    def missing(self) -> int:
        return max(0, self.need - self.have)

    def to_dict(self) -> dict:
        return {
            "kind": self.kind,
            "subject": self.subject,
            "have": self.have,
            "need": self.need,
            "missing": self.missing,
            "action": self.action,
        }


@dataclass
class Noyau:
    entity_id: str
    name: str
    category: str
    referentiel: Referentiel
    chantiers: list[Chantier] = field(default_factory=list)
    claims: list[Claim] = field(default_factory=list)
    legal_id: str | None = None
    contact_url: str | None = None
    # Clé de créneau, avec category: identifie l'entreprise dans le registre
    # des exclusivités (citation_audit.creneau). Laissé vide, elle se déduit
    # du référentiel géographique fourni (sa racine, métropole ou commune) —
    # jamais d'une ville codée en dur, pour rester valable dans n'importe
    # quelle zone du pays sans toucher ce fichier.
    zone: str | None = None

    def __post_init__(self) -> None:
        ids = [c.id for c in self.chantiers]
        duplicates = {i for i in ids if ids.count(i) > 1}
        if duplicates:
            raise ValueError(f"chantiers en doublon: {sorted(duplicates)}")
        for chantier in self.chantiers:
            if chantier.territoire is None:
                continue
            # Un chantier rattaché à un territoire hors référentiel est une
            # preuve invérifiable: on refuse à la construction plutôt que de
            # publier une localisation inventée.
            self.referentiel.get(chantier.territoire)
        if self.zone is None:
            self.zone = self.referentiel.top().name

    # -- implantation territoriale -------------------------------------------

    def territoires(self, today: date | None = None) -> list[TerritoirePreuve]:
        """Preuves d'implantation, du territoire le mieux couvert au moins couvert.

        Un chantier prouve son quartier **et** tous les territoires englobants:
        intervenir aux Chartrons prouve qu'on intervient à Bordeaux. Un
        chantier sans territoire (mission à distance) ne prouve aucune
        implantation: il est simplement absent de ce calcul, pas une erreur.
        """
        buckets: dict[str, list[Chantier]] = {}
        for chantier in self.chantiers:
            if chantier.territoire is None:
                continue
            codes = [chantier.territoire] + [
                a.code for a in self.referentiel.ancestors(chantier.territoire)
            ]
            for code in codes:
                buckets.setdefault(code, []).append(chantier)

        preuves = [
            TerritoirePreuve(territoire=self.referentiel.get(code), chantiers=group)
            for code, group in buckets.items()
        ]
        preuves.sort(key=lambda p: (-p.count, p.territoire.code))
        return preuves

    def territoires_publiables(
        self, today: date | None = None, level: str = QUARTIER
    ) -> list[TerritoirePreuve]:
        return [
            p
            for p in self.territoires(today)
            if p.territoire.level == level and p.count >= MIN_CHANTIERS_TERRITOIRE
        ]

    # -- budgets --------------------------------------------------------------

    def budgets(
        self, today: date | None = None
    ) -> tuple[list[BudgetConstate], list[BudgetBloque]]:
        return aggregate(self.chantiers, today)

    # -- attributs d'autorité -------------------------------------------------

    def autorites(self, today: date | None = None) -> list[Claim]:
        """Certifications et assurances en cours de validité, à la date donnée."""
        return [c for c in self.claims if c.status(today) == VERIFIED]

    def has_credential(self, key: str, on: date | None = None) -> bool:
        """Interrogation booléenne, telle que la surface machine en a besoin."""
        return any(c.key == key and c.status(on) == VERIFIED for c in self.claims)

    def verification_status(self, today: date | None = None) -> str | None:
        """Le statut de vérification publiable de la fiche.

        ``None`` (rien n'est publiable), ``NON_REVENDIQUEE`` (fiche
        référencée: données publiques SIRENE uniquement, étiquetée),
        ``VERIFIEE_DOMAINE`` ou ``VERIFIEE_COURRIER`` (revendication
        prouvée, le canal reste lisible). Voir ``noyau/verification.py`` et
        ``docs/VERIFICATION.md`` pour ce que chaque niveau autorise.
        """
        return verification_status(self.claims, today)

    def is_publication_ready(self, today: date | None = None) -> bool:
        """Les deux preuves d'identité — existence légale ET contrôle de
        l'établissement — sont vérifiées et à jour.

        C'est la condition du badge « vérifié » et de **toute donnée
        déclarative** (chantiers, budgets, certifications: tout ce que
        l'entreprise affirme d'elle-même). La fiche référencée — données
        publiques du répertoire, étiquetée « non revendiquée » — n'exige que
        l'existence: paywall ou pas, personne n'est cru sur parole sans
        avoir prouvé contrôler l'établissement qu'il revendique. Sans ce
        garde-fou, un concurrent pourrait inscrire une fiche usurpée avec de
        fausses coordonnées, et la première affaire de ce genre démolirait
        la promesse « source vérifiée » du registre entier.
        """
        return self.verification_status(today) in STATUTS_VERIFIES

    # -- publication ----------------------------------------------------------

    def publication(self, today: date | None = None) -> list[Assertion]:
        """Tout ce qui franchit son seuil de preuve, prêt pour les agents."""
        moment = today or date.today()
        assertions: list[Assertion] = []

        for preuve in self.territoires_publiables(moment):
            natures = ", ".join(
                sorted({c.nature_spec.label.lower() for c in preuve.chantiers})
            )
            assertions.append(
                Assertion(
                    kind="territoire",
                    subject=preuve.territoire.code,
                    statement=(
                        f"{preuve.count} chantiers réalisés "
                        f"{preuve.territoire.locative()}, dernier en "
                        f"{preuve.latest.strftime('%m/%Y')} ({natures})."
                    ),
                    evidence_count=preuve.documented_count,
                    observed_from=min(c.completed_on for c in preuve.chantiers),
                    observed_to=preuve.latest,
                    payload={
                        "territoire": preuve.territoire.name,
                        "level": preuve.territoire.level,
                        "chantiers": preuve.count,
                        "natures": preuve.natures,
                    },
                )
            )

        published, _ = self.budgets(moment)
        for budget in published:
            assertions.append(
                Assertion(
                    kind="budget",
                    subject=f"{budget.nature}/{budget.band}",
                    statement=budget.sentence(),
                    evidence_count=budget.n,
                    observed_from=budget.oldest,
                    observed_to=budget.newest,
                    payload=budget.to_dict(),
                )
            )

        for claim in self.autorites(moment):
            assertions.append(
                Assertion(
                    kind="autorite",
                    subject=claim.key,
                    statement=(
                        f"{claim.label} : {claim.value}. Contrôlé le "
                        f"{claim.verified_on.isoformat()}, valable jusqu'au "
                        f"{claim.valid_until.isoformat()}."
                    ),
                    evidence_count=len(claim.evidence),
                    observed_from=claim.verified_on,
                    observed_to=claim.valid_until,
                    payload={
                        "key": claim.key,
                        "value": claim.machine_value,
                        "schema_property": claim.schema_property,
                        "valid_until": claim.valid_until.isoformat()
                        if claim.valid_until
                        else None,
                    },
                )
            )

        return assertions

    def manques(self, today: date | None = None) -> list[Manque]:
        """Le plan de travail: ce qui manque pour publier davantage.

        C'est la contrepartie visible de l'abonnement. Un Noyau qui n'aurait
        aucun manque serait un Noyau qui a cessé de croître.
        """
        moment = today or date.today()
        manques: list[Manque] = []

        for preuve in self.territoires(moment):
            if preuve.territoire.level != QUARTIER:
                continue
            if 0 < preuve.count < MIN_CHANTIERS_TERRITOIRE:
                manques.append(
                    Manque(
                        kind="territoire",
                        subject=preuve.territoire.code,
                        have=preuve.count,
                        need=MIN_CHANTIERS_TERRITOIRE,
                        action=(
                            f"Documenter {MIN_CHANTIERS_TERRITOIRE - preuve.count} "
                            f"chantier(s) de plus {preuve.territoire.locative()} pour "
                            "publier cette implantation."
                        ),
                    )
                )

        _, blocked = self.budgets(moment)
        for budget in blocked:
            # Le libellé doit porter la nature et la bande: une ligne de plan de
            # travail qui dit « 2 chantiers sur 5 requis » sans dire de quoi est
            # inutilisable par la personne qui va chercher les pièces.
            label = f"{NATURES[budget.nature].label}, {budget.band}"
            manques.append(
                Manque(
                    kind="budget",
                    subject=f"{budget.nature}/{budget.band}",
                    have=budget.n,
                    need=budget.n + budget.missing,
                    action=(
                        f"{label} : {budget.reason}. Récupérer les pièces "
                        "manquantes pour publier ce budget."
                    ),
                )
            )

        for claim in self.claims:
            status = claim.status(moment)
            if status == VERIFIED:
                continue
            manques.append(
                Manque(
                    kind="autorite",
                    subject=claim.key,
                    have=1 if claim.evidence else 0,
                    need=1,
                    action=(
                        f"{claim.label} : {claim.status_label().lower()}. "
                        "Obtenir la pièce à jour pour la publier."
                    ),
                )
            )

        manques.sort(key=lambda m: (-m.missing, m.kind, m.subject))
        return manques

    def coverage(self, today: date | None = None) -> dict:
        """Chiffres de tête, pour décider où porter l'effort du mois."""
        moment = today or date.today()
        published, blocked = self.budgets(moment)
        quartiers = [p for p in self.territoires(moment) if p.territoire.level == QUARTIER]
        return {
            "chantiers": len(self.chantiers),
            "chantiers_documentes": sum(1 for c in self.chantiers if c.is_documented),
            "quartiers_touches": len(quartiers),
            "quartiers_publiables": len(self.territoires_publiables(moment)),
            "budgets_publies": len(published),
            "budgets_bloques": len(blocked),
            "autorites_valides": len(self.autorites(moment)),
            "assertions_publiees": len(self.publication(moment)),
            "manques": len(self.manques(moment)),
        }

    # -- chargement -----------------------------------------------------------

    @classmethod
    def from_dict(cls, data: dict, referentiel: Referentiel) -> "Noyau":
        return cls(
            entity_id=data["entity_id"],
            name=data["name"],
            category=data["category"],
            referentiel=referentiel,
            chantiers=[Chantier.from_dict(raw) for raw in data.get("chantiers", ())],
            claims=[Claim.from_dict(raw) for raw in data.get("claims", ())],
            legal_id=data.get("legal_id"),
            contact_url=data.get("contact_url"),
            zone=data.get("zone"),
        )

    @classmethod
    def load(cls, path: str | Path, referentiel: Referentiel) -> "Noyau":
        return cls.from_dict(
            json.loads(Path(path).read_text(encoding="utf-8")), referentiel
        )


__all__ = [
    "Assertion",
    "Chantier",
    "Claim",
    "Evidence",
    "Manque",
    "MIN_CHANTIERS_TERRITOIRE",
    "Noyau",
    "Referentiel",
    "Territoire",
]
