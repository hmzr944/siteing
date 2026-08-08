"""Calcul de la Part de Citation.

Trois indicateurs, et un seul contrat.

**Taux de Présence** — sur quelle proportion du panier l'entreprise apparaît-elle,
d'une manière ou d'une autre. C'est le chiffre brutal, celui qui ouvre une
conversation commerciale: « sur 40 questions d'achat de votre marché, vous
apparaissez 0 fois ».

**Part de Citation** — la part de la voix disponible que l'entreprise capte,
pondérée par l'intention commerciale du prompt et par son rang dans la réponse.
Être nommé en premier ne vaut pas être nommé en quatrième: la pondération de
rang suit ``1 / log2(1 + rang)``, la même décote logarithmique que le DCG en
recherche d'information. C'est l'indicateur du contrat.

**Angles morts** — les prompts où l'entreprise est absente alors qu'au moins un
concurrent est cité. Ce ne sont pas des statistiques, ce sont des pertes
nommées, et c'est la matière du rapport remis au dirigeant.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timezone

from .detect import find_mentions
from .market import FAMILY_WEIGHTS, Market, Prompt
from .providers import EVIDENCE_MEASURED, EVIDENCE_REPLAYED, EVIDENCE_SYNTHETIC, EngineResponse

# Du plus faible au plus fort: le niveau de preuve d'un audit est celui de son
# maillon le plus faible.
EVIDENCE_ORDER = [EVIDENCE_SYNTHETIC, EVIDENCE_REPLAYED, EVIDENCE_MEASURED]

# En dessous de ce nombre de prompts exploitables, la Part de Citation est
# trop instable pour être présentée comme une mesure.
MIN_PROMPTS = 20


def rank_weight(rank: int) -> float:
    """Décote logarithmique du rang: 1er = 1.00, 2e = 0.63, 3e = 0.50."""
    return 1.0 / math.log2(1 + max(1, rank))


@dataclass(frozen=True)
class Observation:
    prompt_id: str
    family: str
    provider: str
    entity_id: str
    rank: int
    via: str

    @property
    def value(self) -> float:
        return FAMILY_WEIGHTS.get(self.family, 1.0) * rank_weight(self.rank)


@dataclass
class EntityScore:
    entity_id: str
    name: str
    is_client: bool
    presence_rate: float = 0.0
    citation_share: float = 0.0
    first_place_rate: float = 0.0
    avg_rank: float | None = None
    sourced_count: int = 0          # cité comme *source* (domaine dans les citations)
    by_family: dict[str, float] = field(default_factory=dict)  # famille -> part de citation


@dataclass
class BlindSpot:
    prompt_id: str
    text: str
    family: str
    weight: float
    competitors: list[str]


@dataclass
class ValueEstimate:
    """Valorisation de l'écart à la part équitable.

    Le piège serait de valoriser *toute* l'intention du marché où le client est
    absent: aucune entreprise ne capterait 100 % de son marché, et un chiffre
    gonflé détruit précisément la crédibilité qui fait la valeur du rapport.

    On mesure donc l'écart entre la **part équitable** — ce qu'un acteur parmi
    n captait s'ils étaient à égalité, soit 1/n par défaut — et la part
    réellement captée. C'est un plancher défendable, pas un plafond flatteur:
    « vous devriez capter un septième de la voix de votre marché, vous en
    captez 1,8 % ».
    """

    monthly_intent_volume: int
    avg_deal_value: float
    close_rate: float
    fair_share: float
    captured_share: float

    @property
    def share_gap(self) -> float:
        return max(0.0, self.fair_share - self.captured_share)

    @property
    def monthly_missed(self) -> float:
        return (
            self.monthly_intent_volume
            * self.share_gap
            * self.close_rate
            * self.avg_deal_value
        )

    @property
    def annual_missed(self) -> float:
        return self.monthly_missed * 12


@dataclass
class AuditResult:
    market_id: str
    label: str
    category: str
    zone: str
    basket_version: str
    generated_at: str
    providers: list[str]
    evidence: str
    prompt_count: int
    usable_prompt_count: int
    failed_queries: int
    client_id: str
    scores: list[EntityScore]
    blind_spots: list[BlindSpot]
    value_estimate: ValueEstimate | None = None
    warnings: list[str] = field(default_factory=list)

    @property
    def client_score(self) -> EntityScore:
        return next(s for s in self.scores if s.entity_id == self.client_id)

    @property
    def leader(self) -> EntityScore:
        return self.scores[0]

    @property
    def is_presentable(self) -> bool:
        """Un rapport simulé ou sous-échantillonné ne se remet pas à un client."""
        return self.evidence != EVIDENCE_SYNTHETIC and self.usable_prompt_count >= MIN_PROMPTS

    def to_dict(self) -> dict:
        return {
            "market": {
                "id": self.market_id,
                "label": self.label,
                "category": self.category,
                "zone": self.zone,
            },
            "audit": {
                "basket_version": self.basket_version,
                "generated_at": self.generated_at,
                "providers": self.providers,
                "evidence": self.evidence,
                "presentable": self.is_presentable,
                "prompt_count": self.prompt_count,
                "usable_prompt_count": self.usable_prompt_count,
                "failed_queries": self.failed_queries,
                "warnings": self.warnings,
            },
            "leaderboard": [
                {
                    "entity_id": s.entity_id,
                    "name": s.name,
                    "is_client": s.is_client,
                    "presence_rate": round(s.presence_rate, 4),
                    "citation_share": round(s.citation_share, 4),
                    "first_place_rate": round(s.first_place_rate, 4),
                    "avg_rank": round(s.avg_rank, 2) if s.avg_rank is not None else None,
                    "sourced_count": s.sourced_count,
                    "by_family": {k: round(v, 4) for k, v in sorted(s.by_family.items())},
                }
                for s in self.scores
            ],
            "blind_spots": [
                {
                    "prompt_id": b.prompt_id,
                    "prompt": b.text,
                    "family": b.family,
                    "weight": b.weight,
                    "cited_instead": b.competitors,
                }
                for b in self.blind_spots
            ],
            "value_estimate": (
                {
                    "monthly_intent_volume": self.value_estimate.monthly_intent_volume,
                    "avg_deal_value": self.value_estimate.avg_deal_value,
                    "close_rate": self.value_estimate.close_rate,
                    "fair_share": round(self.value_estimate.fair_share, 4),
                    "captured_share": round(self.value_estimate.captured_share, 4),
                    "share_gap": round(self.value_estimate.share_gap, 4),
                    "monthly_missed_eur": round(self.value_estimate.monthly_missed),
                    "annual_missed_eur": round(self.value_estimate.annual_missed),
                }
                if self.value_estimate
                else None
            ),
        }


def compute(
    market: Market,
    prompts: list[Prompt],
    runs: list[tuple[str, str, list[EngineResponse]]],
) -> AuditResult:
    """Agrège des séries de réponses en un audit.

    ``runs`` est une liste de ``(nom_du_provider, niveau_de_preuve, réponses)``.
    """
    context_terms = [market.category, market.category_plural, market.zone, *market.services]
    prompt_by_id = {p.id: p for p in prompts}

    observations: list[Observation] = []
    failed = 0
    usable_prompt_ids: set[str] = set()
    # prompt -> entités présentes (tous providers confondus)
    presence: dict[str, set[str]] = {p.id: set() for p in prompts}
    sourced: dict[str, int] = {e.id: 0 for e in market.entities}

    for provider_name, _evidence, responses in runs:
        for response in responses:
            prompt = prompt_by_id.get(response.prompt_id)
            if prompt is None:
                continue
            if response.error or not response.text.strip():
                failed += 1
                continue
            usable_prompt_ids.add(prompt.id)
            mentions = find_mentions(
                response.text, market.entities, response.citations, context_terms
            )
            for mention in mentions:
                observations.append(
                    Observation(
                        prompt_id=prompt.id,
                        family=prompt.family,
                        provider=provider_name,
                        entity_id=mention.entity_id,
                        rank=mention.rank,
                        via=mention.via,
                    )
                )
                presence[prompt.id].add(mention.entity_id)
                if mention.via == "domaine":
                    sourced[mention.entity_id] += 1

    usable = len(usable_prompt_ids)
    total_value = sum(o.value for o in observations) or 1.0

    # Valeur totale par famille, pour les parts de citation sectorielles.
    family_totals: dict[str, float] = {}
    for observation in observations:
        family_totals[observation.family] = (
            family_totals.get(observation.family, 0.0) + observation.value
        )

    scores: list[EntityScore] = []
    for entity in market.entities:
        own = [o for o in observations if o.entity_id == entity.id]
        prompts_present = {pid for pid, ids in presence.items() if entity.id in ids}
        ranks = [o.rank for o in own]
        by_family: dict[str, float] = {}
        for family, family_total in family_totals.items():
            family_value = sum(o.value for o in own if o.family == family)
            by_family[family] = family_value / family_total if family_total else 0.0

        scores.append(
            EntityScore(
                entity_id=entity.id,
                name=entity.name,
                is_client=entity.is_client,
                presence_rate=len(prompts_present) / usable if usable else 0.0,
                citation_share=sum(o.value for o in own) / total_value,
                first_place_rate=(sum(1 for r in ranks if r == 1) / len(ranks)) if ranks else 0.0,
                avg_rank=(sum(ranks) / len(ranks)) if ranks else None,
                sourced_count=sourced[entity.id],
                by_family=by_family,
            )
        )

    scores.sort(key=lambda s: (-s.citation_share, -s.presence_rate, s.name))

    client = market.client
    blind_spots = [
        BlindSpot(
            prompt_id=prompt.id,
            text=prompt.text,
            family=prompt.family,
            weight=prompt.weight,
            competitors=[
                market.entity(eid).name
                for eid in sorted(presence[prompt.id])
                if eid != client.id
            ],
        )
        for prompt in prompts
        if prompt.id in usable_prompt_ids
        and client.id not in presence[prompt.id]
        and any(eid != client.id for eid in presence[prompt.id])
    ]
    blind_spots.sort(key=lambda b: (-b.weight, -len(b.competitors), b.text))

    client_score = next(s for s in scores if s.entity_id == client.id)
    value_estimate = None
    if market.economics:
        value_estimate = ValueEstimate(
            monthly_intent_volume=market.economics.monthly_intent_volume,
            avg_deal_value=market.economics.avg_deal_value,
            close_rate=market.economics.close_rate,
            fair_share=market.economics.fair_share or (1.0 / len(market.entities)),
            captured_share=client_score.citation_share,
        )

    evidence = min(
        (run[1] for run in runs), key=lambda e: EVIDENCE_ORDER.index(e), default=EVIDENCE_SYNTHETIC
    )

    warnings: list[str] = []
    if evidence == EVIDENCE_SYNTHETIC:
        warnings.append(
            "Audit produit avec un moteur simulé: chiffres illustratifs, non opposables. "
            "Ne pas remettre à un client."
        )
    if usable < MIN_PROMPTS:
        warnings.append(
            f"Seulement {usable} prompt(s) exploitable(s) (minimum {MIN_PROMPTS}): "
            "la Part de Citation n'est pas stable à ce niveau d'échantillonnage."
        )
    if failed:
        warnings.append(f"{failed} requête(s) sans réponse exploitable, exclue(s) du calcul.")
    if len(runs) < 2 and evidence == EVIDENCE_MEASURED:
        warnings.append(
            "Un seul moteur interrogé: la mesure reflète un éditeur, pas le marché des "
            "moteurs de réponse. Deux moteurs minimum pour un rapport contractuel."
        )

    return AuditResult(
        market_id=market.id,
        label=market.label,
        category=market.category,
        zone=market.zone,
        basket_version=market.basket_version,
        generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        providers=[run[0] for run in runs],
        evidence=evidence,
        prompt_count=len(prompts),
        usable_prompt_count=usable,
        failed_queries=failed,
        client_id=client.id,
        scores=scores,
        blind_spots=blind_spots,
        value_estimate=value_estimate,
        warnings=warnings,
    )
