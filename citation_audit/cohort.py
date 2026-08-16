"""Ligne de base sur un panel d'entreprises.

Un audit mesure une entreprise contre ses concurrents. Une **cohorte** mesure un
marché entier, sans client désigné, et répond à trois questions dont dépend tout
le projet.

1. **Le rang Google prédit-il la citation par les moteurs de réponse ?**
   Si non, le marché est réellement neuf, et l'argument de vente le plus fort
   devient « vous êtes premier sur Google et invisible pour ChatGPT ». Si oui,
   la thèse est faible et il faut le savoir avant d'écrire l'ingestion.

2. **Un agrégateur possède-t-il déjà la réponse ?** Si les moteurs citent
   systématiquement un annuaire ou une place de marché plutôt que des
   entreprises, la niche est fermée et aucun flux structuré ne la rouvrira à
   court terme. C'est le test le moins cher du projet et il vaut mieux le passer
   avant de choisir une ville.

3. **Quelle est la valeur de départ de chacun ?** Sans mesure avant, aucune
   preuve après: on ne saura jamais distinguer un effet de produit du bruit
   saisonnier.

Le panel de mesure est **stratifié** et n'est pas la liste de prospection. On
mesure sur des strates de rang pour pouvoir corréler; on vend ensuite au segment
de son choix. Confondre les deux listes détruit la mesure.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from .market import Market, Prompt
from .providers import EVIDENCE_MEASURED, EVIDENCE_SYNTHETIC, EngineResponse
from .score import (
    EVIDENCE_ORDER,
    MIN_PROMPTS,
    EntityScore,
    observe,
    score_entities,
)
from .stats import Correlation, spearman

# En dessous de ce nombre d'entreprises mesurées, la corrélation ne se lit pas.
MIN_PANEL = 12


@dataclass
class StratumSummary:
    name: str
    count: int
    mean_presence: float
    mean_share: float
    cited_count: int          # entreprises citées au moins une fois

    @property
    def silent_count(self) -> int:
        return self.count - self.cited_count


@dataclass
class CohortResult:
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
    scores: list[EntityScore]
    rank_correlation: Correlation | None
    strata: list[StratumSummary]
    warnings: list[str] = field(default_factory=list)

    @property
    def cited(self) -> list[EntityScore]:
        return [s for s in self.scores if s.presence_rate > 0]

    @property
    def silent(self) -> list[EntityScore]:
        """Les entreprises que les moteurs ne nomment jamais."""
        return [s for s in self.scores if s.presence_rate == 0]

    @property
    def concentration(self) -> float:
        """Part de citation captée par les trois premiers.

        Proche de 1, la réponse du marché est déjà tenue par une poignée
        d'acteurs, ce qui rend l'entrée coûteuse.
        """
        total = sum(s.citation_share for s in self.scores) or 1.0
        return sum(s.citation_share for s in self.scores[:3]) / total

    @property
    def is_readable(self) -> bool:
        return (
            self.evidence != EVIDENCE_SYNTHETIC
            and self.usable_prompt_count >= MIN_PROMPTS
            and len(self.scores) >= MIN_PANEL
        )

    def to_dict(self) -> dict:
        return {
            "market": {
                "id": self.market_id,
                "label": self.label,
                "category": self.category,
                "zone": self.zone,
            },
            "baseline": {
                "basket_version": self.basket_version,
                "generated_at": self.generated_at,
                "providers": self.providers,
                "evidence": self.evidence,
                "readable": self.is_readable,
                "panel_size": len(self.scores),
                "prompt_count": self.prompt_count,
                "usable_prompt_count": self.usable_prompt_count,
                "failed_queries": self.failed_queries,
                "cited": len(self.cited),
                "silent": len(self.silent),
                "top3_concentration": round(self.concentration, 4),
                "warnings": self.warnings,
            },
            "rank_correlation": (
                {
                    "rho": round(self.rank_correlation.rho, 4),
                    "p_value": round(self.rank_correlation.p_value, 5),
                    "n": self.rank_correlation.n,
                    "significant": self.rank_correlation.is_significant,
                    "reading": self.rank_correlation.reading,
                }
                if self.rank_correlation
                else None
            ),
            "strata": [
                {
                    "name": s.name,
                    "count": s.count,
                    "cited": s.cited_count,
                    "silent": s.silent_count,
                    "mean_presence": round(s.mean_presence, 4),
                    "mean_share": round(s.mean_share, 4),
                }
                for s in self.strata
            ],
            "panel": [
                {
                    "entity_id": s.entity_id,
                    "name": s.name,
                    "presence_rate": round(s.presence_rate, 4),
                    "citation_share": round(s.citation_share, 4),
                    "avg_rank": round(s.avg_rank, 2) if s.avg_rank is not None else None,
                    "sourced_count": s.sourced_count,
                }
                for s in self.scores
            ],
        }


def _strata(market: Market, scores: list[EntityScore]) -> list[StratumSummary]:
    by_id = {s.entity_id: s for s in scores}
    buckets: dict[str, list[EntityScore]] = {}
    for entity in market.entities:
        name = entity.segment or "non stratifié"
        buckets.setdefault(name, []).append(by_id[entity.id])

    summaries = []
    for name, group in sorted(buckets.items()):
        summaries.append(
            StratumSummary(
                name=name,
                count=len(group),
                mean_presence=sum(s.presence_rate for s in group) / len(group),
                mean_share=sum(s.citation_share for s in group) / len(group),
                cited_count=sum(1 for s in group if s.presence_rate > 0),
            )
        )
    return summaries


def measure(
    market: Market,
    prompts: list[Prompt],
    runs: list[tuple[str, str, list[EngineResponse]]],
) -> CohortResult:
    """Établit la ligne de base d'un marché entier."""
    observed = observe(market, prompts, runs)
    scores = score_entities(market, observed)
    by_id = {s.entity_id: s for s in scores}

    # Corrélation entre rang Google et part de citation. Attention au signe:
    # un bon rang Google est *petit*, une bonne part de citation est *grande*.
    # Un rho négatif signifie donc « bien classé et bien cité ».
    ranked = [e for e in market.entities if e.google_rank is not None]
    correlation = None
    if len(ranked) >= 3:
        correlation = spearman(
            [float(e.google_rank) for e in ranked],
            [by_id[e.id].citation_share for e in ranked],
        )

    evidence = min(
        (run[1] for run in runs), key=lambda e: EVIDENCE_ORDER.index(e),
        default=EVIDENCE_SYNTHETIC,
    )

    warnings: list[str] = []
    if evidence == EVIDENCE_SYNTHETIC:
        warnings.append(
            "Ligne de base produite avec un moteur simulé: elle valide la chaîne "
            "de mesure, elle ne dit rien du marché réel."
        )
    if len(market.entities) < MIN_PANEL:
        warnings.append(
            f"Panel de {len(market.entities)} entreprises (minimum {MIN_PANEL}): "
            "la corrélation de rang n'est pas lisible à cette taille."
        )
    if correlation is not None and correlation.n < len(market.entities):
        missing = len(market.entities) - correlation.n
        warnings.append(
            f"{missing} entreprise(s) sans rang Google renseigné, exclue(s) de la "
            "corrélation mais bien mesurée(s)."
        )
    if len({e.segment for e in market.entities if e.segment}) < 2:
        warnings.append(
            "Panel non stratifié: sans strates de rang, on ne peut pas distinguer "
            "un effet de visibilité d'un effet de sélection."
        )
    if observed.failed:
        warnings.append(f"{observed.failed} requête(s) sans réponse exploitable.")
    if len(runs) < 2 and evidence == EVIDENCE_MEASURED:
        warnings.append(
            "Un seul moteur interrogé: la ligne de base reflète un éditeur, pas le "
            "marché des moteurs de réponse."
        )

    return CohortResult(
        market_id=market.id,
        label=market.label,
        category=market.category,
        zone=market.zone,
        basket_version=market.basket_version,
        generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        providers=[run[0] for run in runs],
        evidence=evidence,
        prompt_count=len(prompts),
        usable_prompt_count=observed.usable,
        failed_queries=observed.failed,
        scores=scores,
        rank_correlation=correlation,
        strata=_strata(market, scores),
        warnings=warnings,
    )


def to_text(result: CohortResult) -> str:
    """Restitution terminal, écrite pour une décision et non pour un rapport."""
    pct = lambda v: f"{v * 100:.1f} %".replace(".", ",")  # noqa: E731
    lines = [
        f"LIGNE DE BASE — {result.label}",
        f"{result.category} · {result.zone} · panier {result.basket_version}",
        f"{len(result.scores)} entreprises · {result.usable_prompt_count}/"
        f"{result.prompt_count} prompts · preuve: {result.evidence}",
        "",
        "LA QUESTION QUI DÉCIDE DE LA THÈSE",
    ]
    if result.rank_correlation is None:
        lines.append("  Aucun rang Google renseigné: corrélation incalculable.")
    else:
        lines.append(f"  {result.rank_correlation.reading}")

    lines += [
        "",
        "ÉTAT DU MARCHÉ",
        f"  Entreprises jamais citées   {len(result.silent)}/{len(result.scores)}",
        f"  Concentration des 3 premiers {pct(result.concentration):>10}",
        "",
        "PAR STRATE",
    ]
    for stratum in result.strata:
        lines.append(
            f"  {stratum.name[:22]:<22} {stratum.cited_count}/{stratum.count} citées"
            f"   présence moy. {pct(stratum.mean_presence):>8}"
            f"   part moy. {pct(stratum.mean_share):>8}"
        )

    lines += ["", "PANEL"]
    for position, score in enumerate(result.scores, start=1):
        lines.append(
            f"  {position:>2}. {score.name[:32]:<32} part {pct(score.citation_share):>7}"
            f"   présence {pct(score.presence_rate):>7}"
        )

    if result.warnings:
        lines += ["", "RÉSERVES"]
        lines += [f"  ! {w}" for w in result.warnings]

    return "\n".join(lines)
