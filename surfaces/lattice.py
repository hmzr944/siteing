"""Le treillis de pages.

Décision structurante de la distribution: **une entreprise n'est pas une page.**

Une page unique qui dit tout est une URL en concurrence sur tout, et elle perd
contre les annuaires sur les requêtes génériques. Ce que le Noyau permet, et que
personne d'autre ne peut produire, c'est un **treillis**: le croisement du
territoire et de la nature de chantier, où chaque nœud correspond exactement à
une question d'achat réelle.

    « Quel artisan pour une salle de bain aux Chartrons ? »

Cette question a une page, avec six chantiers datés, un budget constaté et des
certifications en cours de validité. Aucun concurrent ne peut fabriquer cette
page: il faudrait avoir fait les chantiers.

Deux règles gouvernent le treillis, et les deux découlent de la même idée: **une
page sans fait est du spam.**

* un nœud n'existe que si le croisement porte au moins deux chantiers, parce
  qu'un chantier isolé produit une page maigre, c'est à dire exactement ce que
  les moteurs apprennent à ignorer;
* un fait qui ne mérite pas sa page n'est pas perdu: il reste porté par la page
  du territoire.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from noyau import MIN_CHANTIERS_TERRITOIRE, NATURES, Chantier, Noyau
from noyau.budget import BudgetConstate
from noyau.territoire import QUARTIER, Territoire

# Chantiers requis pour qu'un croisement territoire x nature ait sa page.
# Deux, c'est le minimum pour qu'un motif se répète; un seul produirait une page
# maigre, qui coûte plus en crédibilité qu'elle ne rapporte en citation.
MIN_CHANTIERS_CROISEMENT = 2

ROOT = "racine"
TERRITOIRE = "territoire"
CROISEMENT = "croisement"


@dataclass
class Node:
    """Un nœud du treillis, c'est à dire une page à produire."""

    kind: str
    slug: str
    title: str
    question: str                      # la question d'achat à laquelle la page répond
    chantiers: list[Chantier] = field(default_factory=list)
    territoire: Territoire | None = None
    nature: str | None = None
    budget: BudgetConstate | None = None

    @property
    def path(self) -> str:
        return "index.html" if self.kind == ROOT else f"{self.slug}.html"

    @property
    def documented(self) -> int:
        return sum(1 for c in self.chantiers if c.is_documented)

    @property
    def latest(self) -> date | None:
        return max((c.completed_on for c in self.chantiers), default=None)

    @property
    def natures(self) -> list[str]:
        return sorted({c.nature for c in self.chantiers})

    @property
    def has_facts(self) -> bool:
        """Une page sans fait daté ne doit pas exister."""
        return bool(self.chantiers) or self.kind == ROOT


def _slug(*parts: str) -> str:
    return "-".join(p for p in parts if p)


def build(core: Noyau, today: date | None = None) -> list[Node]:
    """Calcule les pages qui méritent d'exister, et elles seules."""
    moment = today or date.today()
    published, _ = core.budgets(moment)
    budgets = {(b.nature, b.band): b for b in published}

    nodes: list[Node] = [
        Node(
            kind=ROOT,
            slug="index",
            title=core.name,
            question=f"Quelle {core.category} choisir à {core.zone} ?",
            chantiers=list(core.chantiers),
        )
    ]

    for preuve in core.territoires_publiables(moment, level=QUARTIER):
        territoire = preuve.territoire
        nodes.append(
            Node(
                kind=TERRITOIRE,
                slug=_slug("chantiers", territoire.code),
                title=f"Nos chantiers {territoire.locative()}",
                question=(
                    f"Quelle {core.category} intervient {territoire.locative()} ?"
                ),
                chantiers=list(preuve.chantiers),
                territoire=territoire,
            )
        )

        by_nature: dict[str, list[Chantier]] = {}
        for chantier in preuve.chantiers:
            by_nature.setdefault(chantier.nature, []).append(chantier)

        for nature, group in sorted(by_nature.items()):
            if len(group) < MIN_CHANTIERS_CROISEMENT:
                continue
            label = NATURES[nature].label
            # Le budget rattaché est celui de la bande la mieux représentée
            # dans ce croisement, et seulement s'il est publiable.
            bands = sorted(
                {c.band for c in group if c.band},
                key=lambda b: -sum(1 for c in group if c.band == b),
            )
            budget = next(
                (budgets[(nature, band)] for band in bands if (nature, band) in budgets),
                None,
            )
            nodes.append(
                Node(
                    kind=CROISEMENT,
                    slug=_slug(nature, territoire.code),
                    title=f"{label} {territoire.locative()}",
                    question=(
                        f"Qui fait {label.lower()} {territoire.locative()} ?"
                    ),
                    chantiers=group,
                    territoire=territoire,
                    nature=nature,
                    budget=budget,
                )
            )

    # Garde-fou final: aucune page sans fait ne sort de cette fonction.
    return [n for n in nodes if n.has_facts]


def summary(nodes: list[Node]) -> dict:
    return {
        "pages": len(nodes),
        "territoires": sum(1 for n in nodes if n.kind == TERRITOIRE),
        "croisements": sum(1 for n in nodes if n.kind == CROISEMENT),
        "avec_budget": sum(1 for n in nodes if n.budget is not None),
        "seuil_territoire": MIN_CHANTIERS_TERRITOIRE,
        "seuil_croisement": MIN_CHANTIERS_CROISEMENT,
    }
