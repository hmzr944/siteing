"""De la parole au candidat de chantier.

Trois étapes, et la frontière entre elles est le cœur du dispositif.

1. Un extracteur produit des **fragments** verbatim typés. Il ne connaît aucun
   de nos codes: il dit « ici on parle d'un lieu », « ici d'un montant ».
2. Les résolveurs de ``lexique`` et le référentiel géographique traduisent ces
   fragments en vocabulaire contrôlé, et **refusent** l'ambigu.
3. Ce qui manque devient une **question**, classée par ce qu'elle débloque.

Rien n'est jamais écrit directement dans le Noyau. On produit un **candidat**,
avec la provenance de chaque champ et la phrase d'origine, pour qu'une donnée
fausse soit toujours remontable à ce qui l'a produite.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from noyau.chantier import FROM_VOICE, NATURES, TYPOLOGIES, Chantier
from noyau.territoire import Referentiel, Territoire

from .lexique import (
    Resolved,
    nature_label,
    parse_date,
    parse_duree,
    parse_montant,
    parse_nature,
    parse_surface,
    plain,
)

# Types de fragments qu'un extracteur peut produire. Volontairement pauvre:
# plus le contrat est étroit, moins un modèle a d'occasions d'inventer.
SPAN_TYPES = ("lieu", "nature", "montant", "duree", "surface", "date", "typologie")

# Champs requis pour qu'un candidat soit enregistrable, dans l'ordre de ce
# qu'ils débloquent. La nature et le territoire sont bloquants: le Noyau refuse
# un chantier sans eux. La taille débloque la comparabilité, donc les budgets.
FIELD_PRIORITY = ("nature", "territoire", "budget_eur", "size", "completed_on")

BLOCKING = ("nature", "territoire", "budget_eur")


@dataclass(frozen=True)
class Span:
    """Un fragment verbatim, tel qu'un extracteur le rend."""

    kind: str
    text: str

    def __post_init__(self) -> None:
        if self.kind not in SPAN_TYPES:
            raise ValueError(f"type de fragment inconnu: {self.kind!r}")


@dataclass(frozen=True)
class Question:
    """Ce qu'il faut demander, et ce que la réponse débloquera."""

    field: str
    text: str
    unlocks: str
    blocking: bool

    @property
    def rank(self) -> int:
        return FIELD_PRIORITY.index(self.field) if self.field in FIELD_PRIORITY else 99


@dataclass
class Candidate:
    """Un chantier proposé, jamais enregistré tel quel."""

    source_text: str
    entity_id: str
    provenance: str = FROM_VOICE
    fields: dict[str, object] = field(default_factory=dict)
    evidence: dict[str, str] = field(default_factory=dict)     # champ -> fragment retenu
    confidence: dict[str, float] = field(default_factory=dict)
    refusals: dict[str, str] = field(default_factory=dict)     # champ -> motif du refus

    @property
    def missing(self) -> list[str]:
        return [f for f in FIELD_PRIORITY if f not in self.fields]

    @property
    def is_complete(self) -> bool:
        return all(f in self.fields for f in BLOCKING)

    @property
    def min_confidence(self) -> float:
        return min(self.confidence.values(), default=0.0)

    def questions(self, referentiel: Referentiel) -> list[Question]:
        """Les questions à poser, de la plus débloquante à la moins utile."""
        catalogue = {
            "nature": Question(
                "nature",
                "C'était quel type de chantier ? Salle de bain, cuisine, "
                "rénovation complète, isolation, ravalement, verrière ?",
                "l'enregistrement du chantier",
                True,
            ),
            "territoire": Question(
                "territoire",
                "C'était dans quel quartier ou quelle commune ?",
                "la preuve d'implantation sur ce secteur",
                True,
            ),
            "budget_eur": Question(
                "budget_eur",
                "Le chantier a été facturé combien, au total ?",
                "le budget constaté de cette catégorie",
                True,
            ),
            "size": Question(
                "size",
                "Ça faisait quelle surface, à peu près ?",
                "la comparaison avec vos autres chantiers du même type",
                False,
            ),
            "completed_on": Question(
                "completed_on",
                "Il a été terminé quand ?",
                "la fraîcheur de la preuve",
                False,
            ),
        }
        pending = [catalogue[f] for f in self.missing if f in catalogue]
        # Un refus motivé remplace la question générique par une question ciblée.
        for question in pending:
            motive = self.refusals.get(question.field)
            if motive and question.field == "nature":
                pending[pending.index(question)] = Question(
                    "nature",
                    "Vous avez parlé d'un chantier sans préciser lequel. "
                    "Salle de bain, cuisine, rénovation complète, isolation, "
                    "ravalement, verrière ?",
                    question.unlocks,
                    True,
                )
        return sorted(pending, key=lambda q: q.rank)

    def next_question(self, referentiel: Referentiel) -> Question | None:
        """Une seule question par échange.

        Le produit s'est vendu sur une friction nulle. Chaque question demandée
        entame cette promesse, donc la boucle de confirmation est un budget rare:
        on pose celle qui débloque le plus, et on se taît sur le reste.
        """
        pending = self.questions(referentiel)
        return pending[0] if pending else None

    def to_chantier(self, chantier_id: str) -> Chantier:
        """Construit le chantier. Lève si un champ bloquant manque."""
        if not self.is_complete:
            raise ValueError(
                f"candidat incomplet, il manque: {', '.join(self.missing)}"
            )
        return Chantier(
            id=chantier_id,
            nature=str(self.fields["nature"]),
            territoire=str(self.fields["territoire"]),
            completed_on=self.fields.get("completed_on") or date.today(),
            budget_eur=float(self.fields["budget_eur"]),
            provenance=self.provenance,
            size=self.fields.get("size"),
            typologie=self.fields.get("typologie"),
            duration_days=self.fields.get("duration_days"),
            notes=self.source_text,
        )

    def to_dict(self) -> dict:
        return {
            "entity_id": self.entity_id,
            "source_text": self.source_text,
            "provenance": self.provenance,
            "complete": self.is_complete,
            "fields": {
                key: (value.isoformat() if isinstance(value, date) else value)
                for key, value in self.fields.items()
            },
            "evidence": self.evidence,
            "confidence": {k: round(v, 2) for k, v in self.confidence.items()},
            "refusals": self.refusals,
            "missing": self.missing,
        }


def resolve_territoire(text: str, referentiel: Referentiel) -> Resolved:
    """Territoire, en passant par le référentiel qui refuse déjà l'ambigu.

    Une adresse de rue est traitée en premier: « rue Notre-Dame » est un
    quartier pour qui connaît Bordeaux, et rien du tout pour un programme. Le
    référentiel porte donc des voies en alias, et deux quartiers revendiquant la
    même voie produisent un refus, pas un arbitrage.
    """
    found = referentiel.resolve(text)
    if found is not None:
        return Resolved(found.code, 0.9, f"« {text.strip()} »")
    return Resolved.refuse(
        f"« {text.strip()} » ne correspond à aucun secteur connu, ou en désigne "
        "plusieurs"
    )


def resolve_typologie(text: str) -> Resolved:
    lowered = plain(text)
    for code, label in TYPOLOGIES.items():
        if code.replace("-", " ") in lowered or plain(label) in lowered:
            return Resolved(code, 0.85, f"« {text.strip()} »")
    if "echoppe" in lowered:
        return Resolved("echoppe", 0.9, "« échoppe »")
    return Resolved.refuse("typologie non reconnue")


def build_candidate(
    text: str,
    spans: list[Span],
    entity_id: str,
    referentiel: Referentiel,
    today: date | None = None,
) -> Candidate:
    """Assemble un candidat à partir des fragments, sans jamais deviner."""
    moment = today or date.today()
    candidate = Candidate(source_text=text.strip(), entity_id=entity_id)

    def record(field_name: str, resolved: Resolved) -> None:
        if resolved.ok:
            candidate.fields[field_name] = resolved.value
            candidate.evidence[field_name] = resolved.note
            candidate.confidence[field_name] = resolved.confidence
        elif resolved.note:
            candidate.refusals.setdefault(field_name, resolved.note)

    by_kind: dict[str, list[str]] = {}
    for span in spans:
        by_kind.setdefault(span.kind, []).append(span.text)

    # Chaque fragment est résolu dans son domaine; en dernier recours on relit
    # la phrase entière, parce qu'un extracteur peut avoir manqué un fragment
    # que le résolveur, lui, saurait lire.
    def first(kind: str, resolver) -> Resolved:
        for fragment in by_kind.get(kind, ()):
            attempt = resolver(fragment)
            if attempt.ok:
                return attempt
        return resolver(text)

    record("nature", first("nature", parse_nature))
    record("budget_eur", first("montant", parse_montant))
    record("size", first("surface", parse_surface))
    record("duration_days", first("duree", parse_duree))
    record("typologie", first("typologie", resolve_typologie))
    record(
        "territoire",
        first("lieu", lambda fragment: resolve_territoire(fragment, referentiel)),
    )
    record("completed_on", first("date", lambda fragment: parse_date(fragment, moment)))

    return candidate


def summarise(candidate: Candidate, referentiel: Referentiel) -> str:
    """Ce que le système a compris, en une phrase relisible par le dirigeant."""
    parts = []
    if "nature" in candidate.fields:
        parts.append(nature_label(str(candidate.fields["nature"])))
    if "size" in candidate.fields:
        unit = NATURES[str(candidate.fields["nature"])].unit if "nature" in candidate.fields else "m2"
        parts.append(f"{candidate.fields['size']:g} {unit}")
    if "territoire" in candidate.fields:
        territoire: Territoire = referentiel.get(str(candidate.fields["territoire"]))
        parts.append(territoire.locative())
    if "budget_eur" in candidate.fields:
        amount = f"{round(float(candidate.fields['budget_eur'])):,}".replace(",", " ")
        parts.append(f"{amount} €")
    if "duration_days" in candidate.fields:
        parts.append(f"{candidate.fields['duration_days']} jours")
    if "completed_on" in candidate.fields:
        parts.append(f"terminé le {candidate.fields['completed_on']}")
    return ", ".join(parts) if parts else "rien de compris"
