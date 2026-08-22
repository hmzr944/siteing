"""La ligne de base sert à décider si le projet a une thèse. Elle doit donc
mesurer juste, et surtout refuser de conclure quand le panel ne le permet pas."""

import json
import unittest
from pathlib import Path

from citation_audit.cohort import MIN_PANEL, measure, to_text
from citation_audit.market import Market
from citation_audit.providers import (
    EVIDENCE_MEASURED,
    EVIDENCE_SYNTHETIC,
    EngineResponse,
    SyntheticProvider,
)

PANEL = Path(__file__).resolve().parent.parent / "markets" / "renovation-bordeaux.json"


def load_panel() -> Market:
    return Market.load(PANEL)


def measured(market, responses):
    prompts = market.basket()
    return measure(market, prompts, [("moteur", EVIDENCE_MEASURED, responses(prompts))])


class TestPanelDefinition(unittest.TestCase):
    def setUp(self):
        self.market = load_panel()

    def test_panel_has_no_client(self):
        """Une ligne de base mesure un marché, pas un client: un client
        désigné introduirait un biais de cadrage."""
        self.assertFalse(self.market.has_client)

    def test_panel_is_large_enough_to_read(self):
        self.assertGreaterEqual(len(self.market.entities), MIN_PANEL)

    def test_panel_is_stratified_across_rank_bands(self):
        segments = {e.segment for e in self.market.entities}
        self.assertGreaterEqual(len(segments), 3, "il faut des strates pour corréler")
        self.assertTrue(all(e.google_rank is not None for e in self.market.entities))

    def test_every_entity_is_detectable(self):
        """Un nom composé uniquement du vocabulaire du marché est indétectable:
        il n'a rien à faire dans un panel de mesure."""
        from citation_audit.detect import find_mentions

        context = [
            self.market.category, self.market.category_plural,
            self.market.zone, *self.market.services,
        ]
        for entity in self.market.entities:
            mentions = find_mentions(
                f"Je recommande {entity.name} pour ce chantier.",
                [entity], [], context,
            )
            self.assertEqual(
                [m.entity_id for m in mentions], [entity.id],
                f"{entity.name} n'est pas détectable dans une réponse",
            )

    def test_hyperlocal_prompts_are_generated(self):
        families = {p.family for p in self.market.basket()}
        self.assertIn("hyperlocal", families)


class TestMeasurement(unittest.TestCase):
    def setUp(self):
        self.market = load_panel()

    def test_silent_companies_are_identified(self):
        winner = self.market.entities[0]
        result = measured(
            self.market,
            lambda prompts: [EngineResponse(p.id, winner.name, []) for p in prompts],
        )
        self.assertEqual(len(result.cited), 1)
        self.assertEqual(len(result.silent), len(self.market.entities) - 1)

    def test_concentration_is_total_when_one_company_owns_the_answer(self):
        winner = self.market.entities[0]
        result = measured(
            self.market,
            lambda prompts: [EngineResponse(p.id, winner.name, []) for p in prompts],
        )
        self.assertAlmostEqual(result.concentration, 1.0)

    def test_strata_partition_the_panel(self):
        provider = SyntheticProvider(self.market, seed="5")
        result = measured(
            self.market, lambda prompts: [provider.query(p) for p in prompts]
        )
        self.assertEqual(
            sum(s.count for s in result.strata), len(self.market.entities)
        )
        for stratum in result.strata:
            self.assertLessEqual(stratum.cited_count, stratum.count)
            self.assertEqual(stratum.silent_count, stratum.count - stratum.cited_count)

    def test_correlation_covers_only_entities_with_a_rank(self):
        raw = json.loads(PANEL.read_text(encoding="utf-8"))
        raw["entities"][0].pop("google_rank")
        raw["entities"][1].pop("google_rank")
        market = Market.from_dict(raw)
        provider = SyntheticProvider(market, seed="5")
        prompts = market.basket()
        result = measure(
            market,
            prompts,
            [("m", EVIDENCE_MEASURED, [provider.query(p) for p in prompts])],
        )
        self.assertEqual(result.rank_correlation.n, len(market.entities) - 2)
        self.assertTrue(any("sans rang Google" in w for w in result.warnings))

    def test_correlation_is_absent_without_any_rank(self):
        raw = json.loads(PANEL.read_text(encoding="utf-8"))
        for entity in raw["entities"]:
            entity.pop("google_rank", None)
        market = Market.from_dict(raw)
        provider = SyntheticProvider(market, seed="5")
        prompts = market.basket()
        result = measure(
            market, prompts,
            [("m", EVIDENCE_MEASURED, [provider.query(p) for p in prompts])],
        )
        self.assertIsNone(result.rank_correlation)
        self.assertIn("corrélation incalculable", to_text(result))

    def test_shares_sum_to_one_across_the_panel(self):
        provider = SyntheticProvider(self.market, seed="9")
        result = measured(
            self.market, lambda prompts: [provider.query(p) for p in prompts]
        )
        self.assertAlmostEqual(sum(s.citation_share for s in result.scores), 1.0, places=6)


class TestGuards(unittest.TestCase):
    def setUp(self):
        self.market = load_panel()
        self.prompts = self.market.basket()
        provider = SyntheticProvider(self.market, seed="4")
        self.responses = [provider.query(p) for p in self.prompts]

    def test_simulated_baseline_is_never_readable(self):
        result = measure(
            self.market, self.prompts,
            [("synthetic", EVIDENCE_SYNTHETIC, self.responses)],
        )
        self.assertFalse(result.is_readable)
        self.assertTrue(any("ne dit rien du marché réel" in w for w in result.warnings))

    def test_small_panel_is_flagged_and_unreadable(self):
        raw = json.loads(PANEL.read_text(encoding="utf-8"))
        raw["entities"] = raw["entities"][:5]
        market = Market.from_dict(raw)
        prompts = market.basket()
        provider = SyntheticProvider(market, seed="4")
        result = measure(
            market, prompts,
            [("m", EVIDENCE_MEASURED, [provider.query(p) for p in prompts])],
        )
        self.assertFalse(result.is_readable)
        self.assertTrue(any("n'est pas lisible à cette taille" in w for w in result.warnings))

    def test_unstratified_panel_is_flagged(self):
        raw = json.loads(PANEL.read_text(encoding="utf-8"))
        for entity in raw["entities"]:
            entity["segment"] = ""
        market = Market.from_dict(raw)
        prompts = market.basket()
        provider = SyntheticProvider(market, seed="4")
        result = measure(
            market, prompts,
            [("m", EVIDENCE_MEASURED, [provider.query(p) for p in prompts])],
        )
        self.assertTrue(any("Panel non stratifié" in w for w in result.warnings))

    def test_text_output_leads_with_the_deciding_question(self):
        result = measure(
            self.market, self.prompts,
            [("synthetic", EVIDENCE_SYNTHETIC, self.responses)],
        )
        text = to_text(result)
        self.assertIn("LA QUESTION QUI DÉCIDE DE LA THÈSE", text)
        self.assertIn("RÉSERVES", text)


if __name__ == "__main__":
    unittest.main()
