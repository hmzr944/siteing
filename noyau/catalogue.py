"""Vocabulaire des prestations, par métier.

Généralisation du principe déjà appliqué au territoire (``territoire.py``): une
nature de prestation est une entrée de vocabulaire résolue par le métier,
jamais une chaîne saisie librement ni un dict Python codé en dur pour une
seule verticale.

Le Noyau n'a jamais été spécifique à la rénovation dans sa mécanique — la
comparabilité par bande, le seuil de publication, la preuve par pièce
s'appliquent à n'importe quel métier qui documente des interventions datées,
localisées et facturées. Ce qui était codé en dur, c'était uniquement le
**vocabulaire** (quelles natures existent, avec quelles unités et quelles
bandes). Ce module l'externalise en fichiers JSON sous ``metiers/``, un par
métier, chargés et fusionnés au démarrage — exactement comme un
``Referentiel`` se charge par zone plutôt que d'être une liste Python figée.

Chaque métier possède ses propres codes de nature. Ils doivent être uniques
**globalement** (pas seulement au sein d'un métier) : la fusion refuse deux
métiers qui revendiquent le même code, parce qu'un code de nature ambigu
casserait la résolution de vocabulaire exactement comme un alias de
territoire ambigu.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class Nature:
    """Un type de prestation, avec l'unité et les bandes qui le rendent comparable."""

    code: str
    label: str
    unit: str                          # "m2", "ml", "logement", "intervention"
    bands: tuple[tuple[float, float | None], ...]
    # Un prix unitaire n'a de sens que si la prestation se mesure. Un
    # débouchage de canalisation se compte à l'intervention: publier un prix
    # au mètre y serait trompeur.
    unit_price_meaningful: bool = True
    # Formulations parlées qui désignent cette nature (déjà passées par
    # ``ingestion.lexique.plain``: sans accent, en minuscule). C'est ce qui
    # permet à ``ingestion.parse_nature`` de reconnaître n'importe quel
    # métier sans jamais toucher au code de l'ingestion: le vocabulaire vit
    # avec le catalogue, pas dans le résolveur.
    keywords: tuple[str, ...] = ()

    def band_of(self, size: float | None) -> str | None:
        """Étiquette de la bande de taille, ou ``None`` si la taille est inconnue."""
        if size is None:
            return None
        for low, high in self.bands:
            if size >= low and (high is None or size < high):
                return f"{low:g} à {high:g} {self.unit}" if high else f"{low:g} {self.unit} et plus"
        return None


@dataclass(frozen=True)
class Catalogue:
    """Le vocabulaire d'un métier: ses natures de prestation, ses typologies."""

    metier: str
    label: str
    natures: dict[str, Nature] = field(default_factory=dict)
    typologies: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict) -> "Catalogue":
        natures = {
            code: Nature(
                code=code,
                label=raw["label"],
                unit=raw["unit"],
                bands=tuple(tuple(b) for b in raw["bands"]),
                unit_price_meaningful=raw.get("unit_price_meaningful", True),
                keywords=tuple(raw.get("keywords", ())),
            )
            for code, raw in data.get("natures", {}).items()
        }
        return cls(
            metier=data["metier"],
            label=data["label"],
            natures=natures,
            typologies=dict(data.get("typologies", {})),
        )

    @classmethod
    def load(cls, path: str | Path) -> "Catalogue":
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))


def merge(catalogues: list[Catalogue]) -> tuple[dict[str, Nature], dict[str, str]]:
    """Fusionne plusieurs catalogues de métier en un vocabulaire global.

    Refuse plutôt que d'écraser silencieusement: un code de nature qui
    apparaîtrait dans deux métiers deviendrait ambigu dès qu'un chantier le
    référence, exactement comme un alias de territoire qui désignerait deux
    quartiers à la fois.
    """
    natures: dict[str, Nature] = {}
    typologies: dict[str, str] = {}
    owners: dict[str, str] = {}
    for catalogue in catalogues:
        for code, nature in catalogue.natures.items():
            if code in owners and owners[code] != catalogue.metier:
                raise ValueError(
                    f"code de nature {code!r} défini à la fois par "
                    f"{owners[code]!r} et {catalogue.metier!r}: les codes de "
                    "nature doivent être uniques tous métiers confondus"
                )
            owners[code] = catalogue.metier
            natures[code] = nature
        typologies.update(catalogue.typologies)
    return natures, typologies


def load_all(directory: str | Path) -> list[Catalogue]:
    """Charge tous les catalogues d'un dossier, triés par nom de fichier."""
    return [Catalogue.load(p) for p in sorted(Path(directory).glob("*.json"))]


def merge_keywords(catalogues: list[Catalogue]) -> dict[str, str]:
    """Index mot-clé -> code de nature, tous métiers confondus.

    Un mot-clé disputé par deux natures différentes (deux métiers qui
    emploient la même formulation pour des choses distinctes — « salle
    d'eau » pour une rénovation ou pour une intervention de plomberie) est
    **retiré** plutôt qu'attribué au hasard: mieux vaut que la phrase ne
    résolve rien et déclenche une question, qu'une résolution silencieuse et
    fausse. Contrairement aux codes de nature (``merge``), on ne lève pas
    d'exception ici: une ambiguïté de langage naturel entre métiers est
    plausible et ne doit pas empêcher les catalogues de charger.
    """
    owners: dict[str, str] = {}
    ambiguous: set[str] = set()
    for catalogue in catalogues:
        for code, nature in catalogue.natures.items():
            for keyword in nature.keywords:
                if keyword in owners and owners[keyword] != code:
                    ambiguous.add(keyword)
                else:
                    owners[keyword] = code
    return {k: v for k, v in owners.items() if k not in ambiguous}
