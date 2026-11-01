"""La Part de Citation est l'indicateur du contrat: elle doit être exacte,
bornée, et refuser de se présenter comme une mesure quand elle n'en est pas une."""

import json
import math
import unittest
from pathlib import Path

from citation_audit.market import Market
from citation_audit.providers import (
    EVIDENCE_MEASURED,
    EVIDENCE_REPLAYED,
    EVIDENCE_SYNTHETIC,
    EngineResponse,
    SyntheticProvider,
)
from citation_audit.score import MIN_PROMPTS, compute, rank_weight

FIXTURE = Path(__file__).resolve().parent.parent / "markets" / "plombier-bordeaux.json"


class TestRankWeight(unittest.TestCase):
    def test_known_values(self):
        self.assertAlmostEqual(rank_weight(1), 1.0)
        self.assertAlmostEqual(rank_weight(2), 1 / math.log2(3))
        self.assertAlmostEqual(rank_weight(3), 0.5)

    def test_is_strictly_decreasing(self):
        weights = [rank_weight(r) for r in range(1, 8)]
        self.assertEqual(weights, sorted(weights, reverse=True))

    def test_never_exceeds_one(self):
        self.assertLessEqual(max(rank_weight(r) for r in range(1, 20)), 1.0)


class TestCompute(unittest.TestCase):
    def setUp(self):
        self.market = Market.load(FIXTURE)
        self.prompts = self.market.basket()

    def _measured(self, responses):
        return compute(self.market, self.prompts, [("moteur-a", EVIDENCE_MEASURED, responses)])

    def test_shares_sum_to_one_when_anyone_is_cited(self):
        provider = SyntheticProvider(self.market, seed="7")
        responses = [provider.query(p) for p in self.prompts]
        result = self._measured(responses)
        self.assertAlmostEqual(sum(s.citation_share for s in result.scores), 1.0, places=6)

    def test_leaderboard_is_sorted_by_share(self):
        provider = SyntheticProvider(self.market, seed="7")
        result = self._measured([provider.query(p) for p in self.prompts])
        shares = [s.citation_share for s in result.scores]
        self.assertEqual(shares, sorted(shares, reverse=True))

    def test_absent_client_scores_zero_and_collects_blind_spots(self):
        rival = self.market.competitors[0]
        responses = [
            EngineResponse(p.id, f"1. {rival.name} — excellent.", []) for p in self.prompts
        ]
        result = self._measured(responses)
        self.assertEqual(result.client_score.presence_rate, 0.0)
        self.assertEqual(result.client_score.citation_share, 0.0)
        self.assertEqual(len(result.blind_spots), len(self.prompts))
        self.assertIn(rival.name, result.blind_spots[0].competitors)

    def test_blind_spots_exclude_prompts_where_nobody_is_cited(self):
        responses = [
            EngineResponse(p.id, "Je ne trouve aucune entreprise identifiable.", [])
            for p in self.prompts
        ]
        result = self._measured(responses)
        self.assertEqual(result.blind_spots, [])

    def test_blind_spots_are_ordered_by_commercial_weight(self):
        rival = self.market.competitors[0]
        responses = [EngineResponse(p.id, f"{rival.name} d'abord.", []) for p in self.prompts]
        weights = [b.weight for b in self._measured(responses).blind_spots]
        self.assertEqual(weights, sorted(weights, reverse=True))

    def test_rank_one_beats_rank_three(self):
        first, second = self.market.competitors[0], self.market.competitors[1]
        early = [
            EngineResponse(p.id, f"1. {first.name}. 2. autre. 3. {second.name}.", [])
            for p in self.prompts
        ]
        result = self._measured(early)
        by_id = {s.entity_id: s for s in result.scores}
        self.assertGreater(by_id[first.id].citation_share, by_id[second.id].citation_share)
        self.assertEqual(by_id[first.id].presence_rate, by_id[second.id].presence_rate)

    def test_failed_responses_are_excluded_not_counted_as_absence(self):
        responses = [EngineResponse(p.id, "", [], error="timeout") for p in self.prompts]
        result = self._measured(responses)
        self.assertEqual(result.usable_prompt_count, 0)
        self.assertEqual(result.failed_queries, len(self.prompts))
        self.assertTrue(any("sans réponse exploitable" in w for w in result.warnings))

    def test_value_estimate_uses_the_gap_to_fair_share(self):
        rival = self.market.competitors[0]
        responses = [EngineResponse(p.id, rival.name, []) for p in self.prompts]
        estimate = self._measured(responses).value_estimate
        self.assertIsNotNone(estimate)
        fair_share = 1 / len(self.market.entities)
        self.assertAlmostEqual(estimate.fair_share, fair_share)
        self.assertEqual(estimate.captured_share, 0.0)
        self.assertAlmostEqual(estimate.annual_missed, 1400 * fair_share * 0.22 * 420 * 12)

    def test_value_estimate_never_goes_negative(self):
        """Un client qui dépasse sa part équitable n'a aucune perte à réclamer."""
        client = self.market.client
        responses = [EngineResponse(p.id, f"1. {client.name}.", []) for p in self.prompts]
        estimate = self._measured(responses).value_estimate
        self.assertEqual(estimate.captured_share, 1.0)
        self.assertEqual(estimate.share_gap, 0.0)
        self.assertEqual(estimate.annual_missed, 0.0)

    def test_explicit_fair_share_overrides_the_default(self):
        raw = json.loads(FIXTURE.read_text(encoding="utf-8"))
        raw["economics"]["fair_share"] = 0.30
        market = Market.from_dict(raw)
        prompts = market.basket()
        rival = market.competitors[0]
        result = compute(
            market,
            prompts,
            [(
                "m",
                EVIDENCE_MEASURED,
                [EngineResponse(p.id, rival.name, []) for p in prompts],
            )],
        )
        self.assertAlmostEqual(result.value_estimate.fair_share, 0.30)

    def test_sourced_domains_are_counted(self):
        client = self.market.client
        responses = [
            EngineResponse(p.id, "Une entreprise locale convient.", [f"https://{client.domains[0]}/"])
            for p in self.prompts
        ]
        self.assertGreater(self._measured(responses).client_score.sourced_count, 0)


class TestEvidenceGuards(unittest.TestCase):
    def setUp(self):
        self.market = Market.load(FIXTURE)
        self.prompts = self.market.basket()
        provider = SyntheticProvider(self.market, seed="3")
        self.responses = [provider.query(p) for p in self.prompts]

    def test_synthetic_audit_is_never_presentable(self):
        result = compute(
            self.market, self.prompts, [("synthetic", EVIDENCE_SYNTHETIC, self.responses)]
        )
        self.assertFalse(result.is_presentable)
        self.assertTrue(any("non opposables" in w for w in result.warnings))

    def test_evidence_level_is_the_weakest_link(self):
        result = compute(
            self.market,
            self.prompts,
            [
                ("moteur-a", EVIDENCE_MEASURED, self.responses),
                ("archive", EVIDENCE_REPLAYED, self.responses),
            ],
        )
        self.assertEqual(result.evidence, EVIDENCE_REPLAYED)

    def test_single_measured_engine_is_flagged_for_contract_use(self):
        result = compute(
            self.market, self.prompts, [("moteur-a", EVIDENCE_MEASURED, self.responses)]
        )
        self.assertTrue(any("Un seul moteur" in w for w in result.warnings))

    def test_small_sample_is_flagged_and_not_presentable(self):
        short = self.prompts[: MIN_PROMPTS - 1]
        result = compute(
            self.market,
            short,
            [("moteur-a", EVIDENCE_MEASURED, [r for r in self.responses[: len(short)]])],
        )
        self.assertFalse(result.is_presentable)
        self.assertTrue(any("pas stable" in w for w in result.warnings))

    def test_measured_two_engines_full_basket_is_presentable(self):
        result = compute(
            self.market,
            self.prompts,
            [
                ("moteur-a", EVIDENCE_MEASURED, self.responses),
                ("moteur-b", EVIDENCE_MEASURED, self.responses),
            ],
        )
        self.assertTrue(result.is_presentable)
        self.assertEqual(result.warnings, [])


class TestSyntheticProvider(unittest.TestCase):
    def setUp(self):
        self.market = Market.load(FIXTURE)
        self.prompts = self.market.basket()

    def test_same_seed_gives_identical_responses(self):
        a = SyntheticProvider(self.market, seed="42")
        b = SyntheticProvider(self.market, seed="42")
        self.assertEqual(
            [a.query(p).text for p in self.prompts], [b.query(p).text for p in self.prompts]
        )

    def test_different_seeds_diverge(self):
        a = SyntheticProvider(self.market, seed="1")
        b = SyntheticProvider(self.market, seed="2")
        self.assertNotEqual(
            [a.query(p).text for p in self.prompts], [b.query(p).text for p in self.prompts]
        )

    def test_strength_ordering_is_respected_overall(self):
        provider = SyntheticProvider(self.market, seed="11")
        result = compute(
            self.market,
            self.prompts,
            [("synthetic", EVIDENCE_SYNTHETIC, [provider.query(p) for p in self.prompts])],
        )
        leader = result.scores[0]
        strongest = max(self.market.entities, key=lambda e: e.strength)
        self.assertEqual(leader.entity_id, strongest.id)
        self.assertLess(result.client_score.citation_share, leader.citation_share)


if __name__ == "__main__":
    unittest.main()
