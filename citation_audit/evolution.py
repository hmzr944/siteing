"""Mesure de l'évolution entre deux vagues.

C'est le module qui décide si le projet peut prouver quoi que ce soit.

**Le piège central: un avant/après ne prouve rien.** Si la part de citation d'une
entreprise passe de 1,8 % à 12 %, cela peut venir de notre publication, mais
aussi d'un changement de modèle chez l'éditeur, de la disparition d'un
concurrent, de la saison, ou du simple bruit d'échantillonnage entre deux
exécutions. Vendre « depuis la publication, vous êtes cité dans 42 % des
requêtes » sur cette base serait une affirmation causale tirée de la forme de
preuve la plus faible qui existe.

**La sortie est déjà dans l'architecture: le groupe témoin.** Nous mesurons une
cohorte entière alors que nous n'en traitons qu'une partie. Les entreprises non
traitées absorbent tout ce qui affecte le marché entier. D'où l'estimateur de
**double différence**:

    effet = (traités après - traités avant) - (témoins après - témoins avant)

Tout ce qui a bougé pour tout le monde s'annule. Ce qui reste est attribuable au
traitement, et c'est aussi un bien meilleur argument commercial: « vous avez
gagné 9 points de plus que des entreprises comparables qui n'ont rien changé »
est infiniment plus solide que « vous avez gagné 11 points ».

**Deux mesures du bruit, cumulatives.** Une variation n'est rapportable que si
elle franchit les deux:

* l'**intervalle de confiance apparié** par rééchantillonnage des prompts. Le
  panier étant figé, les deux vagues portent sur les mêmes questions: on
  rééchantillonne une fois et on calcule la différence sur le même tirage, ce
  qui est plus puissant qu'un tirage indépendant par vague;
* le **plancher de bruit** empirique, c'est à dire l'amplitude des variations
  observées chez les témoins. Si les entreprises qui n'ont rien fait bougent de
  huit points d'une vague à l'autre, une hausse de six points chez un traité ne
  veut rien dire, quel que soit son intervalle de confiance.

**Piège découvert en construisant ce module, et corrigé ici.** La part de
citation est **compositionnelle**: les parts somment à 100 %. Quand une
entreprise traitée gagne de la part, les témoins en perdent *mécaniquement*,
sans que rien ne leur soit arrivé. Or la double différence suppose exactement
l'inverse, à savoir que le traitement n'affecte pas les témoins. Appliquée à une
part, elle sous-estime donc l'effet, et pire, elle déclare « établies » des
baisses chez des témoins qui n'ont rien fait.

L'effet attribuable est donc estimé sur le **taux de présence**, qui n'est pas
compositionnel: un moteur peut citer trois entreprises ou cinq, et la présence
d'une entreprise ne retire rien à celle d'une autre. La part de citation reste
publiée, mais comme **description**, jamais comme estimation causale.
"""

from __future__ import annotations

import json
import statistics
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path

from .market import FAMILY_WEIGHTS, Market, Prompt
from .providers import EVIDENCE_SYNTHETIC, EngineResponse
from .score import EVIDENCE_ORDER, observe, rank_weight

# Tirages de rééchantillonnage. Mille suffit pour un intervalle à 95 % stable
# au dixième de point, et reste instantané sur un panier de cette taille.
BOOTSTRAP_DRAWS = 1000

# Quantile des variations témoins qui sert de plancher de bruit. Le neuvième
# décile, donc: une variation traitée doit dépasser ce que dépassent seulement
# 10 % des variations spontanées du marché.
NOISE_QUANTILE = 0.90

# En dessous, le plancher de bruit n'est pas estimable et aucune variation n'est
# déclarée établie.
MIN_CONTROLS = 5

ESTABLISHED = "etabli"
UNDER_NOISE = "sous le bruit"
INCONCLUSIVE = "non concluant"


# -- vagues --------------------------------------------------------------------


@dataclass
class Wave:
    """Une mesure datée, conservée sous une forme qui permet de la recalculer.

    On archive les observations prompt par prompt, et non les parts déjà
    agrégées: sans le détail, ni le rééchantillonnage ni une contestation ne
    seraient possibles plus tard.
    """

    market_id: str
    basket_version: str
    observed_on: date
    providers: list[str]
    evidence: str
    usable_prompt_ids: list[str]
    entity_ids: list[str]
    # (prompt_id, famille, entity_id, rang)
    observations: list[tuple[str, str, str, int]] = field(default_factory=list)
    label: str = ""

    @property
    def prompt_count(self) -> int:
        return len(self.usable_prompt_ids)

    def value_by_prompt(self) -> dict[str, dict[str, float]]:
        """prompt -> entité -> valeur pondérée. Base de tous les calculs."""
        table: dict[str, dict[str, float]] = {pid: {} for pid in self.usable_prompt_ids}
        for prompt_id, family, entity_id, rank in self.observations:
            if prompt_id not in table:
                continue
            value = FAMILY_WEIGHTS.get(family, 1.0) * rank_weight(rank)
            table[prompt_id][entity_id] = table[prompt_id].get(entity_id, 0.0) + value
        return table

    def share(self, entity_id: str, prompt_ids: list[str] | None = None) -> float:
        table = self.value_by_prompt()
        ids = prompt_ids if prompt_ids is not None else self.usable_prompt_ids
        own = sum(table.get(pid, {}).get(entity_id, 0.0) for pid in ids)
        total = sum(sum(table.get(pid, {}).values()) for pid in ids)
        return own / total if total else 0.0

    def presence(self, entity_id: str) -> float:
        table = self.value_by_prompt()
        if not self.usable_prompt_ids:
            return 0.0
        hits = sum(1 for pid in self.usable_prompt_ids if entity_id in table.get(pid, {}))
        return hits / len(self.usable_prompt_ids)

    def to_dict(self) -> dict:
        return {
            "market_id": self.market_id,
            "basket_version": self.basket_version,
            "observed_on": self.observed_on.isoformat(),
            "label": self.label,
            "providers": self.providers,
            "evidence": self.evidence,
            "usable_prompt_ids": self.usable_prompt_ids,
            "entity_ids": self.entity_ids,
            "observations": [list(o) for o in self.observations],
            "captured_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Wave":
        return cls(
            market_id=data["market_id"],
            basket_version=data["basket_version"],
            observed_on=date.fromisoformat(data["observed_on"]),
            providers=list(data["providers"]),
            evidence=data["evidence"],
            usable_prompt_ids=list(data["usable_prompt_ids"]),
            entity_ids=list(data["entity_ids"]),
            observations=[tuple(o) for o in data.get("observations", ())],
            label=data.get("label", ""),
        )

    def save(self, path: str | Path) -> None:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(self.to_dict(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    @classmethod
    def load(cls, path: str | Path) -> "Wave":
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))


def capture(
    market: Market,
    prompts: list[Prompt],
    runs: list[tuple[str, str, list[EngineResponse]]],
    observed_on: date | None = None,
    label: str = "",
) -> Wave:
    """Transforme un relevé en vague archivable."""
    observed = observe(market, prompts, runs)
    return Wave(
        market_id=market.id,
        basket_version=market.basket_version,
        observed_on=observed_on or date.today(),
        providers=[run[0] for run in runs],
        evidence=min(
            (run[1] for run in runs), key=lambda e: EVIDENCE_ORDER.index(e),
            default=EVIDENCE_SYNTHETIC,
        ),
        usable_prompt_ids=sorted(observed.usable_prompt_ids),
        entity_ids=[e.id for e in market.entities],
        observations=[
            (o.prompt_id, o.family, o.entity_id, o.rank) for o in observed.observations
        ],
        label=label,
    )


class Incomparable(Exception):
    """Deux vagues qu'on ne peut pas comparer. On refuse, on ne rattrape pas."""


def check_comparable(before: Wave, after: Wave) -> None:
    """Refuse toute comparaison invalide, plutôt que de produire un delta faux."""
    if before.market_id != after.market_id:
        raise Incomparable(
            f"marchés différents: {before.market_id} et {after.market_id}"
        )
    if before.basket_version != after.basket_version:
        raise Incomparable(
            f"paniers différents ({before.basket_version} puis "
            f"{after.basket_version}): les questions ont changé, les parts ne se "
            "comparent pas"
        )
    if set(before.entity_ids) != set(after.entity_ids):
        added = set(after.entity_ids) - set(before.entity_ids)
        removed = set(before.entity_ids) - set(after.entity_ids)
        raise Incomparable(
            "le panel a changé (ajouts: "
            f"{sorted(added) or 'aucun'}, retraits: {sorted(removed) or 'aucun'}): "
            "une part de citation est relative aux entités suivies"
        )
    if set(before.providers) != set(after.providers):
        raise Incomparable(
            f"moteurs différents ({before.providers} puis {after.providers}): "
            "chaque éditeur a son propre comportement"
        )
    if after.observed_on <= before.observed_on:
        raise Incomparable("la vague postérieure doit être plus récente")


# -- rééchantillonnage ---------------------------------------------------------


def _draws(seed: str, count: int, size: int) -> list[list[int]]:
    """Tirages avec remise, déterministes pour une graine donnée."""
    import random

    generator = random.Random(seed)
    return [
        [generator.randrange(size) for _ in range(size)] for _ in range(count)
    ]


def paired_bootstrap_presence(
    before: Wave, after: Wave, entity_id: str, draws: int = BOOTSTRAP_DRAWS
) -> tuple[float, float]:
    """Intervalle à 95 % de la variation de **présence**, par tirage apparié.

    C'est l'intervalle qui compte pour un jugement causal: la présence n'est pas
    compositionnelle, donc sa variation ne peut pas être l'ombre du mouvement
    d'un concurrent.
    """
    prompts = sorted(set(before.usable_prompt_ids) & set(after.usable_prompt_ids))
    if len(prompts) < 5:
        return (float("-inf"), float("inf"))

    table_before = before.value_by_prompt()
    table_after = after.value_by_prompt()
    hit_before = [1.0 if entity_id in table_before.get(p, {}) else 0.0 for p in prompts]
    hit_after = [1.0 if entity_id in table_after.get(p, {}) else 0.0 for p in prompts]

    deltas = []
    for indices in _draws(f"{before.market_id}:presence:{entity_id}", draws, len(prompts)):
        n = len(indices)
        deltas.append(
            sum(hit_after[i] for i in indices) / n - sum(hit_before[i] for i in indices) / n
        )
    deltas.sort()
    return (
        deltas[int(0.025 * len(deltas))],
        deltas[min(len(deltas) - 1, int(0.975 * len(deltas)))],
    )


def paired_bootstrap(
    before: Wave, after: Wave, entity_id: str, draws: int = BOOTSTRAP_DRAWS
) -> tuple[float, float]:
    """Intervalle à 95 % de la variation de part, par tirage apparié.

    Le panier étant figé, les deux vagues portent sur les mêmes questions. On
    tire donc **un seul** échantillon de prompts et on calcule la différence
    dessus: apparier élimine la variance commune aux deux vagues et resserre
    l'intervalle, là où deux tirages indépendants la doubleraient.
    """
    prompts = sorted(set(before.usable_prompt_ids) & set(after.usable_prompt_ids))
    if len(prompts) < 5:
        return (float("-inf"), float("inf"))

    table_before = before.value_by_prompt()
    table_after = after.value_by_prompt()

    def share(table: dict[str, dict[str, float]], ids: list[str]) -> float:
        own = sum(table.get(pid, {}).get(entity_id, 0.0) for pid in ids)
        total = sum(sum(table.get(pid, {}).values()) for pid in ids)
        return own / total if total else 0.0

    deltas = []
    for indices in _draws(f"{before.market_id}:{entity_id}", draws, len(prompts)):
        sample = [prompts[i] for i in indices]
        deltas.append(share(table_after, sample) - share(table_before, sample))

    deltas.sort()
    low = deltas[int(0.025 * len(deltas))]
    high = deltas[min(len(deltas) - 1, int(0.975 * len(deltas)))]
    return (low, high)


# -- comparaison ---------------------------------------------------------------


@dataclass
class EntityDelta:
    entity_id: str
    name: str
    treated: bool
    share_before: float
    share_after: float
    presence_before: float
    presence_after: float
    ci_low: float
    ci_high: float
    presence_ci_low: float = 0.0
    presence_ci_high: float = 0.0
    verdict: str = INCONCLUSIVE

    @property
    def share_delta(self) -> float:
        return self.share_after - self.share_before

    @property
    def presence_delta(self) -> float:
        return self.presence_after - self.presence_before

    @property
    def excludes_zero(self) -> bool:
        """L'intervalle de présence ne contient pas zéro.

        On juge sur la présence et non sur la part: une part qui bouge peut
        n'être que le reflet mécanique du mouvement d'un concurrent.
        """
        return self.presence_ci_low > 0 or self.presence_ci_high < 0


@dataclass
class Comparison:
    market_id: str
    label: str
    before: Wave
    after: Wave
    deltas: list[EntityDelta]
    noise_floor: float          # sur la présence, non compositionnelle
    did: float | None           # effet attribuable, estimé sur la présence
    share_did: float | None = None  # descriptif, biaisé par la compositionnalité
    treated_count: int = 0
    control_count: int = 0
    warnings: list[str] = field(default_factory=list)

    @property
    def days(self) -> int:
        return (self.after.observed_on - self.before.observed_on).days

    @property
    def treated(self) -> list[EntityDelta]:
        return [d for d in self.deltas if d.treated]

    @property
    def controls(self) -> list[EntityDelta]:
        return [d for d in self.deltas if not d.treated]

    @property
    def is_reportable(self) -> bool:
        """Un rapport remis au client exige une mesure réelle et des témoins."""
        return (
            self.before.evidence != EVIDENCE_SYNTHETIC
            and self.after.evidence != EVIDENCE_SYNTHETIC
            and self.control_count >= MIN_CONTROLS
        )

    def delta_for(self, entity_id: str) -> EntityDelta:
        return next(d for d in self.deltas if d.entity_id == entity_id)

    def to_dict(self) -> dict:
        return {
            "market_id": self.market_id,
            "period": {
                "from": self.before.observed_on.isoformat(),
                "to": self.after.observed_on.isoformat(),
                "days": self.days,
            },
            "basket_version": self.before.basket_version,
            "reportable": self.is_reportable,
            "presence_noise_floor": round(self.noise_floor, 4),
            "attributable_presence_gain": (
                round(self.did, 4) if self.did is not None else None
            ),
            "share_difference_in_differences": (
                round(self.share_did, 4) if self.share_did is not None else None
            ),
            "estimator_note": (
                "L'effet attribuable est estimé sur le taux de présence, qui n'est "
                "pas compositionnel. La double différence sur la part de citation "
                "est publiée à titre descriptif: les parts sommant à 100 %, un gain "
                "chez les traités fait mécaniquement baisser les témoins, ce qui "
                "biaise l'estimateur vers le bas."
            ),
            "treated_count": self.treated_count,
            "control_count": self.control_count,
            "warnings": self.warnings,
            "entities": [
                {
                    "entity_id": d.entity_id,
                    "name": d.name,
                    "treated": d.treated,
                    "share_before": round(d.share_before, 4),
                    "share_after": round(d.share_after, 4),
                    "share_delta": round(d.share_delta, 4),
                    "presence_before": round(d.presence_before, 4),
                    "presence_after": round(d.presence_after, 4),
                    "ci_low": round(d.ci_low, 4),
                    "ci_high": round(d.ci_high, 4),
                    "verdict": d.verdict,
                }
                for d in self.deltas
            ],
        }


def compare(
    market: Market, before: Wave, after: Wave, draws: int = BOOTSTRAP_DRAWS
) -> Comparison:
    """Compare deux vagues, avec témoins, intervalles et plancher de bruit."""
    check_comparable(before, after)

    by_id = {e.id: e for e in market.entities}
    deltas: list[EntityDelta] = []
    for entity_id in before.entity_ids:
        entity = by_id.get(entity_id)
        low, high = paired_bootstrap(before, after, entity_id, draws)
        p_low, p_high = paired_bootstrap_presence(before, after, entity_id, draws)
        deltas.append(
            EntityDelta(
                entity_id=entity_id,
                name=entity.name if entity else entity_id,
                treated=bool(entity and entity.is_treated(after.observed_on)),
                share_before=before.share(entity_id),
                share_after=after.share(entity_id),
                presence_before=before.presence(entity_id),
                presence_after=after.presence(entity_id),
                ci_low=low,
                ci_high=high,
                presence_ci_low=p_low,
                presence_ci_high=p_high,
            )
        )

    controls = [d for d in deltas if not d.treated]
    treated = [d for d in deltas if d.treated]

    # Plancher de bruit: amplitude des variations spontanées du marché.
    noise_floor = 0.0
    if len(controls) >= MIN_CONTROLS:
        swings = sorted(abs(d.presence_delta) for d in controls)
        index = min(len(swings) - 1, int(NOISE_QUANTILE * len(swings)))
        noise_floor = swings[index]

    for delta in deltas:
        if len(controls) < MIN_CONTROLS or not delta.excludes_zero:
            delta.verdict = INCONCLUSIVE
        elif abs(delta.presence_delta) <= noise_floor:
            delta.verdict = UNDER_NOISE
        else:
            delta.verdict = ESTABLISHED

    did = share_did = None
    if treated and len(controls) >= MIN_CONTROLS:
        did = statistics.fmean(d.presence_delta for d in treated) - statistics.fmean(
            d.presence_delta for d in controls
        )
        share_did = statistics.fmean(d.share_delta for d in treated) - statistics.fmean(
            d.share_delta for d in controls
        )

    warnings: list[str] = []
    if EVIDENCE_SYNTHETIC in (before.evidence, after.evidence):
        warnings.append(
            "Au moins une vague est simulée: la comparaison valide la mécanique, "
            "elle ne dit rien du marché réel."
        )
    if not treated:
        warnings.append(
            "Aucune entreprise traitée sur cette période: rien à attribuer."
        )
    if len(controls) < MIN_CONTROLS:
        warnings.append(
            f"{len(controls)} témoin(s) seulement (minimum {MIN_CONTROLS}): sans "
            "groupe témoin, une hausse ne se distingue pas d'un changement de "
            "modèle chez l'éditeur. Aucune variation n'est déclarée établie."
        )
    shared = len(set(before.usable_prompt_ids) & set(after.usable_prompt_ids))
    if shared < len(before.usable_prompt_ids):
        warnings.append(
            f"{len(before.usable_prompt_ids) - shared} prompt(s) exploitable(s) "
            "dans une vague seulement, exclu(s) de la comparaison."
        )

    return Comparison(
        market_id=market.id,
        label=market.label,
        before=before,
        after=after,
        deltas=sorted(deltas, key=lambda d: -d.share_delta),
        noise_floor=noise_floor,
        did=did,
        share_did=share_did,
        treated_count=len(treated),
        control_count=len(controls),
        warnings=warnings,
    )


# -- restitution ---------------------------------------------------------------

NBSP = " "


def _pct(value: float, signed: bool = False) -> str:
    formatted = f"{value * 100:+.1f}" if signed else f"{value * 100:.1f}"
    return formatted.replace(".", ",") + NBSP + "%"


def _eur(value: float) -> str:
    return f"{round(value):,}".replace(",", NBSP) + NBSP + "€"


def modelled_value(market: Market, share_gain: float) -> dict | None:
    """Valeur modélisée d'un gain de part de citation.

    Ce n'est **pas** un chiffre d'affaires attribué. Attribuer une vente à une
    citation est impossible chez une TPE, et le prétendre nous coûterait la
    crédibilité qui est notre seul actif. C'est une traduction en euros d'un
    gain de part, avec ses quatre entrées affichées, exactement comme l'écart à
    la part équitable de l'audit.
    """
    if market.economics is None or share_gain <= 0:
        return None
    economics = market.economics
    # On valorise un gain de **part**, pas de présence: la part est bornée et
    # se lit comme une fraction de la voix du marché, là où un gain de présence
    # de treize points ne signifie pas capter treize pour cent de la demande.
    deals = economics.monthly_intent_volume * share_gain * economics.close_rate
    capped = (
        min(deals, economics.max_monthly_deals)
        if economics.max_monthly_deals is not None
        else deals
    )
    monthly = capped * economics.avg_deal_value
    return {
        "share_gain": round(share_gain, 4),
        "monthly_deals": round(deals, 2),
        "capacity_cap": economics.max_monthly_deals,
        "capped": capped < deals,
        "monthly_intent_volume": economics.monthly_intent_volume,
        "close_rate": economics.close_rate,
        "avg_deal_value": economics.avg_deal_value,
        "monthly_eur": round(monthly),
        "annual_eur": round(monthly * 12),
        "caveat": (
            "Valeur modélisée d'un gain de part de citation, pas un chiffre "
            "d'affaires attribué. Aucune vente n'est rattachée à une citation. "
            "Le résultat est plafonné par la capacité déclarée de l'entreprise: "
            "sans ce plafond, toute valorisation suppose une capacité infinie."
        ),
    }


def to_text(comparison: Comparison, market: Market) -> str:
    """Restitution interne, pour décider."""
    lines = [
        f"ÉVOLUTION — {comparison.label}",
        f"{comparison.before.observed_on} vers {comparison.after.observed_on} "
        f"({comparison.days} jours) · panier {comparison.before.basket_version}",
        f"{comparison.treated_count} traitée(s), {comparison.control_count} témoin(s) "
        f"· preuve: {comparison.after.evidence}",
        "",
        "EFFET ATTRIBUABLE (double différence)",
    ]
    if comparison.did is None:
        lines.append("  Incalculable: il faut des traités et assez de témoins.")
    else:
        lines.append(
            f"  {_pct(comparison.did, signed=True)} de présence, au-delà de ce "
            "qu'ont fait les témoins."
        )
        if comparison.share_did is not None:
            lines.append(
                f"  Pour information, sur la part de citation : "
                f"{_pct(comparison.share_did, signed=True)}. Descriptif seulement, "
                "les parts étant compositionnelles."
            )
        value = modelled_value(market, comparison.share_did or 0.0)
        if value:
            lines.append(
                f"  Valeur modélisée : {_eur(value['annual_eur'])} par an "
                f"({_eur(value['monthly_eur'])} par mois)."
            )
    lines.append(
        f"  Plancher de bruit du marché (présence) : {_pct(comparison.noise_floor)}"
    )

    lines += ["", "PAR ENTREPRISE"]
    for delta in comparison.deltas:
        if delta.share_before == 0 and delta.share_after == 0:
            continue
        mark = "T" if delta.treated else " "
        lines.append(
            f" {mark} {delta.name[:26]:<26} présence "
            f"{_pct(delta.presence_before):>6} vers {_pct(delta.presence_after):>6} "
            f"{_pct(delta.presence_delta, signed=True):>8}"
            f"  [{_pct(delta.presence_ci_low, True)} ; "
            f"{_pct(delta.presence_ci_high, True)}]  {delta.verdict}"
        )

    if comparison.warnings:
        lines += ["", "RÉSERVES"]
        lines += [f"  ! {w}" for w in comparison.warnings]
    return "\n".join(lines)


# -- suivi descriptif (sans témoin) --------------------------------------------


@dataclass(frozen=True)
class TrackPoint:
    """Un point de mesure pour une entreprise, sans jugement causal.

    Utile pour un « Audit J0 → J7 → J30 » sur une seule entreprise, avant
    qu'un groupe témoin existe ou soit pertinent (par exemple lors des dix
    entretiens du protocole de validation terrain: on montre une progression,
    pas une preuve).
    """

    label: str
    observed_on: date
    presence_rate: float
    citation_share: float
    blind_spot_count: int
    evidence: str


def track(waves: list[Wave], entity_id: str) -> list[TrackPoint]:
    """Progression d'une entité à travers une suite de vagues, triée par date.

    **Ceci n'est pas `compare()`.** Il n'y a ni groupe témoin, ni intervalle de
    confiance, ni verdict établi/sous le bruit. Une hausse ici peut venir de la
    publication comme de n'importe quoi d'autre. C'est un relevé descriptif,
    pas une estimation causale — utile pour montrer une trajectoire en
    entretien, jamais pour l'affirmer comme un effet.
    """
    ordered = sorted(waves, key=lambda w: w.observed_on)
    points: list[TrackPoint] = []
    for wave in ordered:
        table = wave.value_by_prompt()
        blind_spots = sum(
            1 for pid in wave.usable_prompt_ids if entity_id not in table.get(pid, {})
        )
        points.append(
            TrackPoint(
                label=wave.label or wave.observed_on.isoformat(),
                observed_on=wave.observed_on,
                presence_rate=wave.presence(entity_id),
                citation_share=wave.share(entity_id),
                blind_spot_count=blind_spots,
                evidence=wave.evidence,
            )
        )
    return points


def track_to_text(points: list[TrackPoint], entity_name: str) -> str:
    lines = [
        f"SUIVI — {entity_name}",
        "(progression descriptive, sans groupe témoin : ne prouve aucune "
        "causalité)",
        "",
    ]
    for point in points:
        lines.append(
            f"  {point.observed_on}  {point.label:<10} présence "
            f"{_pct(point.presence_rate):>6}  part {_pct(point.citation_share):>6}  "
            f"{point.blind_spot_count} angle(s) mort(s)  preuve {point.evidence}"
        )
    return "\n".join(lines)


def client_report(comparison: Comparison, market: Market, entity_id: str) -> str:
    """Le rapport mensuel remis au dirigeant.

    Il ne dit jamais « grâce à nous ». Il dit ce qui a été mesuré, contre quoi
    cela se compare, et ce qui reste incertain. Une promesse tenue une fois de
    trop détruirait tout le reste.
    """
    delta = comparison.delta_for(entity_id)
    lines = [
        f"RAPPORT DE CITATION — {delta.name}",
        f"Période du {comparison.before.observed_on} au {comparison.after.observed_on}",
        f"{comparison.before.prompt_count} questions d'achat de votre marché, "
        f"identiques d'une période à l'autre.",
        "",
    ]

    if not comparison.is_reportable:
        lines += [
            "DOCUMENT INTERNE — NE PAS REMETTRE AU CLIENT",
            "Mesure simulée ou groupe témoin insuffisant.",
            "",
        ]

    before_hits = round(delta.presence_before * comparison.before.prompt_count)
    after_hits = round(delta.presence_after * comparison.after.prompt_count)
    lines += [
        "CE QUI A CHANGÉ",
        f"  Vous étiez cité sur {before_hits} question(s) sur "
        f"{comparison.before.prompt_count}. Vous l'êtes maintenant sur {after_hits}.",
        f"  Part de la voix de votre marché : {_pct(delta.share_before)} vers "
        f"{_pct(delta.share_after)}.",
        "",
    ]

    if delta.verdict == ESTABLISHED:
        lines.append(
            "Cette variation dépasse à la fois l'incertitude de mesure et les "
            "variations spontanées observées sur le marché. Elle est établie."
        )
    elif delta.verdict == UNDER_NOISE:
        lines.append(
            f"Cette variation ({_pct(delta.share_delta, True)}) reste dans "
            f"l'amplitude des mouvements spontanés du marché "
            f"({_pct(comparison.noise_floor)} ce mois-ci). Nous ne la comptons pas."
        )
    else:
        lines.append(
            "Cette variation n'est pas distinguable du hasard d'échantillonnage "
            "sur ce nombre de questions. Nous ne la comptons pas."
        )

    if comparison.did is not None and delta.treated:
        lines += [
            "",
            "COMPARAISON AVEC LES ENTREPRISES QUI N'ONT RIEN CHANGÉ",
            f"  Nous suivons {comparison.control_count} entreprises comparables de "
            "votre marché qui n'ont pas publié de nouvelles données.",
            f"  Écart attribuable : {_pct(comparison.did, signed=True)} de "
            "présence au-delà de leur propre évolution.",
        ]
        value = modelled_value(market, comparison.share_did or 0.0)
        if value:
            lines += [
                f"  Traduit en euros : {_eur(value['annual_eur'])} par an, sur la "
                f"base de {value['monthly_intent_volume']} recherches par mois, "
                f"{_pct(value['close_rate'])} de transformation et "
                f"{_eur(value['avg_deal_value'])} par affaire.",
                "  Il s'agit d'une valeur modélisée à partir d'un gain de part de "
                "citation, et non d'un chiffre d'affaires attribué : aucune vente "
                "n'est rattachée à une citation.",
            ]

    lines += [
        "",
        "CE QUE CE RAPPORT NE DIT PAS",
        "  Nous mesurons ce que les moteurs de réponse restituent sur un panier de "
        "questions figé. Nous ne contrôlons aucun éditeur et ne garantissons aucune "
        "position. Les réponses brutes sont archivées et consultables.",
    ]
    return "\n".join(lines)
