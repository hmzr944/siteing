"""Le chantier: unité atomique de preuve du Noyau.

Un chantier documenté est ce que les moteurs de réponse citent, parce qu'il est
spécifique, daté et localisé. C'est aussi ce qui s'accumule et qu'un concurrent
qui démarre ne peut pas fabriquer: il ne peut que l'attendre.

Le point de conception qui engage tout le reste est la **comparabilité**. Une
salle de bain de 4 m² et une de 20 m² ne se moyennent pas. Sans bandes de
surface, le « budget constaté » devient une moyenne de choux et de carottes,
c'est à dire un chiffre faux publié avec assurance, exactement ce que ce produit
existe pour éviter.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from .catalogue import Nature, load_all, merge, merge_keywords
from .territoire import Territoire

# Provenance de l'information. Elle ne dit pas si c'est vrai, elle dit d'où ça
# vient: c'est la condition pour déboguer une donnée fausse et pour décider ce
# qui peut devenir opposable.
FROM_VOICE = "vocal"          # le dirigeant l'a raconté
FROM_INVOICE = "facture"      # extrait d'une facture acquittée
FROM_QUOTE = "devis"          # extrait d'un devis signé
FROM_IMPORT = "import"        # repris d'un outil de gestion

PROVENANCES = {
    FROM_VOICE: "Raconté par l'entreprise",
    FROM_INVOICE: "Extrait d'une facture acquittée",
    FROM_QUOTE: "Extrait d'un devis signé",
    FROM_IMPORT: "Importé d'un outil de gestion",
}

# Seules ces provenances portent une pièce opposable. Un chantier raconté reste
# affiché comme raconté et ne compte pas dans un budget publié: un budget est
# une donnée que l'entreprise engage, elle ne peut pas reposer sur un souvenir.
DOCUMENTED = frozenset({FROM_INVOICE, FROM_QUOTE})

# Le vocabulaire des natures de chantier n'a jamais été spécifique à la
# rénovation dans sa mécanique (comparabilité par bande, seuil de publication,
# preuve par pièce) — seul le contenu l'était, codé en dur. Il est désormais
# chargé depuis ``metiers/``, un fichier JSON par métier, et fusionné: le même
# Noyau sert n'importe quel métier qui documente des interventions datées,
# localisées et facturées, sans changer une ligne de ce module.
_METIERS_DIR = Path(__file__).resolve().parent.parent / "metiers"
_CATALOGUES = load_all(_METIERS_DIR)
NATURES, TYPOLOGIES = merge(_CATALOGUES)
# Index mot-clé -> code, pour ingestion.lexique.parse_nature. Vit ici, à côté
# de NATURES, pour la même raison: un métier de plus ne doit demander qu'un
# fichier JSON, jamais une modification du code de résolution.
NATURE_KEYWORDS = merge_keywords(_CATALOGUES)


@dataclass(frozen=True)
class Chantier:
    """Une intervention réalisée, datée et localisée."""

    id: str
    nature: str
    territoire: str                    # code du référentiel, jamais une saisie libre
    completed_on: date
    budget_eur: float
    provenance: str
    size: float | None = None          # surface ou linéaire, dans l'unité de la nature
    typologie: str | None = None
    duration_days: int | None = None
    reference: str | None = None       # numéro de facture ou de devis
    photos: tuple[str, ...] = ()
    notes: str = ""

    def __post_init__(self) -> None:
        if self.nature not in NATURES:
            raise ValueError(f"nature de chantier inconnue: {self.nature!r}")
        if self.provenance not in PROVENANCES:
            raise ValueError(f"provenance inconnue: {self.provenance!r}")
        if self.typologie is not None and self.typologie not in TYPOLOGIES:
            raise ValueError(f"typologie inconnue: {self.typologie!r}")
        if self.budget_eur <= 0:
            raise ValueError(f"{self.id}: budget non renseigné ou négatif")
        if self.size is not None and self.size <= 0:
            raise ValueError(f"{self.id}: taille non renseignée ou négative")
        if self.provenance in DOCUMENTED and not self.reference:
            raise ValueError(
                f"{self.id}: une provenance {self.provenance!r} exige une référence "
                "de pièce, sinon elle n'est pas opposable"
            )

    @property
    def nature_spec(self) -> Nature:
        return NATURES[self.nature]

    @property
    def is_documented(self) -> bool:
        """Adossé à une pièce, donc utilisable dans une donnée publiée."""
        return self.provenance in DOCUMENTED

    @property
    def band(self) -> str | None:
        return self.nature_spec.band_of(self.size)

    @property
    def comparability_key(self) -> tuple[str, str] | None:
        """Clé sous laquelle deux chantiers peuvent être agrégés.

        Sans taille connue, un chantier reste une preuve d'intervention mais ne
        participe à aucun budget: on ne sait pas à quoi le comparer.
        """
        band = self.band
        return (self.nature, band) if band else None

    @property
    def unit_price(self) -> float | None:
        if not self.nature_spec.unit_price_meaningful or not self.size:
            return None
        return self.budget_eur / self.size

    def age_days(self, today: date) -> int:
        return (today - self.completed_on).days

    @classmethod
    def from_dict(cls, data: dict) -> "Chantier":
        return cls(
            id=data["id"],
            nature=data["nature"],
            territoire=data["territoire"],
            completed_on=date.fromisoformat(data["completed_on"]),
            budget_eur=float(data["budget_eur"]),
            provenance=data["provenance"],
            size=float(data["size"]) if data.get("size") is not None else None,
            typologie=data.get("typologie"),
            duration_days=(
                int(data["duration_days"]) if data.get("duration_days") is not None else None
            ),
            reference=data.get("reference"),
            photos=tuple(data.get("photos", ())),
            notes=data.get("notes", ""),
        )


@dataclass
class TerritoirePreuve:
    """Preuve d'implantation sur un territoire, avec ce qui l'appuie."""

    territoire: Territoire
    chantiers: list[Chantier] = field(default_factory=list)

    @property
    def count(self) -> int:
        return len(self.chantiers)

    @property
    def documented_count(self) -> int:
        return sum(1 for c in self.chantiers if c.is_documented)

    @property
    def latest(self) -> date | None:
        return max((c.completed_on for c in self.chantiers), default=None)

    @property
    def natures(self) -> list[str]:
        return sorted({c.nature for c in self.chantiers})
