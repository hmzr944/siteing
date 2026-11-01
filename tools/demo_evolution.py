#!/usr/bin/env python3
"""Démonstration de la boucle de mesure temporelle.

Produit trois vagues simulées (J0, J30, J60) sur le panel de Bordeaux, en
simulant un effet de traitement pour les entreprises marquées `treated_since`.

    python3 tools/demo_evolution.py

Le traitement est ici **fabriqué** en augmentant la force des entreprises
traitées dans le moteur simulé. Cela exerce toute la chaîne de comparaison sans
rien dire du marché réel, et le code le signale de lui-même.
"""

from __future__ import annotations

import sys
from dataclasses import replace
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from citation_audit.evolution import capture, client_report, compare, to_text
from citation_audit.market import Market
from citation_audit.providers import EVIDENCE_SYNTHETIC, SyntheticProvider

WAVES = [
    (date(2026, 8, 16), "J0, avant publication", 0.0),
    (date(2026, 9, 15), "J30", 0.10),
    (date(2026, 10, 15), "J60", 0.22),
]


def wave_market(market: Market, moment: date, lift: float) -> Market:
    """Marché dont les traités ont une force accrue: l'effet simulé."""
    entities = [
        replace(e, strength=min(1.0, e.strength + lift)) if e.is_treated(moment) else e
        for e in market.entities
    ]
    return replace(market, entities=entities)


def main() -> int:
    market = Market.load("markets/renovation-bordeaux.json")
    prompts = market.basket()
    waves = []

    for moment, label, lift in WAVES:
        simulated = wave_market(market, moment, lift)
        runs = []
        for seed in ("11", "23"):
            provider = SyntheticProvider(simulated, seed=seed)
            runs.append(
                (provider.name, EVIDENCE_SYNTHETIC, [provider.query(p) for p in prompts])
            )
        wave = capture(market, prompts, runs, observed_on=moment, label=label)
        wave.save(Path("vagues") / f"{market.id}-{moment.isoformat()}.json")
        waves.append(wave)
        print(f"vague {label:<24} {moment}  {wave.prompt_count} prompts")

    print()
    comparison = compare(market, waves[0], waves[-1])
    print(to_text(comparison, market))
    print()
    print("=" * 72)
    print()
    print(client_report(comparison, market, "ferrand"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
