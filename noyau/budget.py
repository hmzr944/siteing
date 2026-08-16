"""Le budget constaté.

C'est la donnée que les moteurs de réponse citent le plus volontiers, et c'est
aussi la plus dangereuse à publier. Trois règles la gouvernent.

**Un budget constaté est une distribution, pas un prix.** « Rénovation complète
d'une salle de bain de 6 m² : 11 500 € » à partir d'un seul chantier est une
anecdote déguisée en tarif. Ce qui est citable et défendable est « sur 8
chantiers de 5 à 8 m² réalisés depuis 2024, médiane 11 200 €, moitié centrale
entre 9 400 et 13 800 € ».

**Un budget ne se publie qu'au-dessus d'un seuil.** En dessous de cinq chantiers
comparables, une médiane est du bruit. Le système refuse alors de publier et
dit ce qui manque, plutôt que de sortir un chiffre fragile.

**Un budget constaté n'est jamais une offre.** Il décrit ce qui a été facturé
par le passé, jamais ce qui sera facturé demain. La formulation publiée porte
cette distinction, parce qu'entre « à partir de 9 400 € » et « constaté entre
9 400 et 13 800 € sur 8 chantiers » il y a la différence entre un engagement
commercial et un fait.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass
from datetime import date, timedelta

from .chantier import NATURES, Chantier

# En dessous de ce nombre de chantiers comparables, aucune publication.
MIN_CHANTIERS = 5

# Au-delà de cet âge, un chantier ne reflète plus les prix pratiqués.
MAX_AGE_DAYS = 365 * 3

# Un écart interquartile qui dépasse cette part de la médiane signale que la
# bande de comparabilité mélange des ouvrages trop différents. On publie quand
# même, mais le rendu doit le dire: une fourchette trop large n'informe pas.
WIDE_SPREAD_RATIO = 1.2


@dataclass(frozen=True)
class BudgetConstate:
    """Distribution de budgets réellement facturés, sur des chantiers comparables."""

    nature: str
    band: str
    n: int
    median: float
    p25: float
    p75: float
    low: float
    high: float
    oldest: date
    newest: date
    median_unit_price: float | None = None

    @property
    def label(self) -> str:
        return f"{NATURES[self.nature].label}, {self.band}"

    @property
    def spread_ratio(self) -> float:
        return (self.p75 - self.p25) / self.median if self.median else 0.0

    @property
    def is_wide(self) -> bool:
        return self.spread_ratio > WIDE_SPREAD_RATIO

    def sentence(self) -> str:
        """Formulation publiée. Elle décrit un constat, jamais une offre.

        C'est la seule chaîne que voient les moteurs et les humains: elle doit
        contenir l'effectif et la période, sans quoi un lecteur pourrait la lire
        comme un tarif.
        """
        period = (
            f"depuis {self.oldest.year}"
            if self.oldest.year != self.newest.year
            else f"en {self.oldest.year}"
        )
        return (
            f"{self.label} : budget médian constaté {_eur(self.median)}, "
            f"moitié des chantiers entre {_eur(self.p25)} et {_eur(self.p75)}, "
            f"sur {self.n} chantiers facturés {period}."
        )

    def to_dict(self) -> dict:
        return {
            "nature": self.nature,
            "band": self.band,
            "n": self.n,
            "median_eur": round(self.median),
            "p25_eur": round(self.p25),
            "p75_eur": round(self.p75),
            "min_eur": round(self.low),
            "max_eur": round(self.high),
            "median_unit_price_eur": (
                round(self.median_unit_price, 1) if self.median_unit_price else None
            ),
            "period": {"from": self.oldest.isoformat(), "to": self.newest.isoformat()},
            "wide_spread": self.is_wide,
            "statement": self.sentence(),
        }


@dataclass(frozen=True)
class BudgetBloque:
    """Un budget qui ne peut pas être publié, et la raison exacte."""

    nature: str
    band: str
    n: int
    reason: str

    @property
    def missing(self) -> int:
        return max(0, MIN_CHANTIERS - self.n)

    def to_dict(self) -> dict:
        return {
            "nature": self.nature,
            "band": self.band,
            "n": self.n,
            "missing": self.missing,
            "reason": self.reason,
        }


def _eur(value: float) -> str:
    return f"{round(value):,}".replace(",", " ") + " €"


def _quartiles(values: list[float]) -> tuple[float, float]:
    """Quartiles par interpolation linéaire, robustes aux petits effectifs."""
    ordered = sorted(values)
    if len(ordered) < 4:
        return ordered[0], ordered[-1]
    q1, _, q3 = statistics.quantiles(ordered, n=4, method="inclusive")
    return q1, q3


def eligible(chantiers: list[Chantier], today: date) -> list[Chantier]:
    """Chantiers utilisables dans un budget publié.

    Trois conditions cumulatives: adossé à une pièce, comparable (donc de taille
    connue), et pas trop ancien.
    """
    horizon = today - timedelta(days=MAX_AGE_DAYS)
    return [
        c
        for c in chantiers
        if c.is_documented and c.comparability_key and c.completed_on >= horizon
    ]


def aggregate(
    chantiers: list[Chantier], today: date | None = None
) -> tuple[list[BudgetConstate], list[BudgetBloque]]:
    """Regroupe les chantiers en budgets publiables et en budgets bloqués.

    Les bloqués ne sont pas un déchet: ils forment le plan de travail du mois,
    c'est à dire ce que l'abonnement finance.
    """
    today = today or date.today()
    usable = eligible(chantiers, today)

    groups: dict[tuple[str, str], list[Chantier]] = {}
    for chantier in usable:
        groups.setdefault(chantier.comparability_key, []).append(chantier)

    # Les groupes trop petits ou inéligibles doivent quand même apparaître,
    # sinon on ne saurait pas quoi aller chercher.
    for chantier in chantiers:
        key = chantier.comparability_key
        if key and key not in groups:
            groups.setdefault(key, [])

    published: list[BudgetConstate] = []
    blocked: list[BudgetBloque] = []

    for (nature, band), group in sorted(groups.items()):
        if len(group) < MIN_CHANTIERS:
            same_key = [
                c for c in chantiers if c.comparability_key == (nature, band)
            ]
            undocumented = sum(1 for c in same_key if not c.is_documented)
            stale = sum(
                1
                for c in same_key
                if c.is_documented and c.completed_on < today - timedelta(days=MAX_AGE_DAYS)
            )
            reason = f"{len(group)} chantier(s) exploitable(s) sur {MIN_CHANTIERS} requis"
            details = []
            if undocumented:
                details.append(f"{undocumented} sans pièce justificative")
            if stale:
                details.append(f"{stale} trop ancien(s)")
            if details:
                reason += " (" + ", ".join(details) + ")"
            blocked.append(BudgetBloque(nature, band, len(group), reason))
            continue

        budgets = [c.budget_eur for c in group]
        p25, p75 = _quartiles(budgets)
        unit_prices = [c.unit_price for c in group if c.unit_price is not None]
        published.append(
            BudgetConstate(
                nature=nature,
                band=band,
                n=len(group),
                median=statistics.median(budgets),
                p25=p25,
                p75=p75,
                low=min(budgets),
                high=max(budgets),
                oldest=min(c.completed_on for c in group),
                newest=max(c.completed_on for c in group),
                median_unit_price=statistics.median(unit_prices) if unit_prices else None,
            )
        )

    published.sort(key=lambda b: (-b.n, b.nature, b.band))
    blocked.sort(key=lambda b: (-b.n, b.nature, b.band))
    return published, blocked
