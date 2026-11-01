"""La boucle de mesure temporelle décide si le projet peut prouver quoi que ce
soit. Ces tests défendent l'honnêteté de l'estimateur avant sa puissance."""

import json
import unittest
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory

from citation_audit.evolution import (
    ESTABLISHED,
    INCONCLUSIVE,
    MIN_CONTROLS,
    UNDER_NOISE,
    Comparison,
    Incomparable,
    Wave,
    capture,
    check_comparable,
    client_report,
    compare,
    modelled_value,
    paired_bootstrap,
    paired_bootstrap_presence,
    to_text,
    track,
    track_to_text,
)
from citation_audit.market import Market
from citation_audit.providers import EVIDENCE_MEASURED, EVIDENCE_SYNTHETIC, EngineResponse

PANEL = Path(__file__).resolve().parent.parent / "markets" / "renovation-bordeaux.json"
J0 = date(2026, 8, 16)
J60 = date(2026, 10, 15)


def market() -> Market:
    return Market.load(PANEL)


def wave_from(m: Market, cited: dict[str, int], on: date, evidence=EVIDENCE_MEASURED) -> Wave:
    """Vague fabriquée: chaque entité citée l'est sur `n` prompts, au rang 1."""
    prompts = m.basket()
    responses = []
    for index, prompt in enumerate(prompts):
        names = [
            m.entity(eid).name for eid, count in cited.items() if index < count
        ]
        responses.append(
            EngineResponse(prompt.id, ". ".join(names) if names else "Rien à signaler.", [])
        )
    return capture(m, prompts, [("moteur", evidence, responses)], observed_on=on)


class TestWave(unittest.TestCase):
    def setUp(self):
        self.market = market()
        self.wave = wave_from(self.market, {"ferrand": 20, "cazenave": 10}, J0)

    def test_round_trip_preserves_everything(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "w.json"
            self.wave.save(path)
            again = Wave.load(path)
        self.assertEqual(again.to_dict()["observations"], self.wave.to_dict()["observations"])
        self.assertEqual(again.basket_version, self.wave.basket_version)

    def test_observations_are_stored_prompt_by_prompt(self):
        """Sans le détail, ni rééchantillonnage ni contestation ne sont possibles."""
        self.assertTrue(self.wave.observations)
        self.assertEqual(len(self.wave.observations[0]), 4)

    def test_presence_counts_prompts_not_mentions(self):
        self.assertAlmostEqual(
            self.wave.presence("ferrand"), 20 / self.wave.prompt_count, places=6
        )
        self.assertEqual(self.wave.presence("lespiault"), 0.0)

    def test_shares_sum_to_one(self):
        total = sum(self.wave.share(e.id) for e in self.market.entities)
        self.assertAlmostEqual(total, 1.0, places=6)


class TestComparability(unittest.TestCase):
    """On refuse une comparaison invalide, on ne la rattrape pas."""

    def setUp(self):
        self.market = market()
        self.before = wave_from(self.market, {"ferrand": 10}, J0)

    def test_same_wave_pair_is_comparable(self):
        after = wave_from(self.market, {"ferrand": 20}, J60)
        check_comparable(self.before, after)

    def test_different_basket_is_refused(self):
        raw = json.loads(PANEL.read_text(encoding="utf-8"))
        raw["services"].append("la pose d'un poêle à bois")
        other = Market.from_dict(raw)
        after = wave_from(other, {"ferrand": 20}, J60)
        with self.assertRaises(Incomparable) as caught:
            check_comparable(self.before, after)
        self.assertIn("questions ont changé", str(caught.exception))

    def test_changed_panel_is_refused(self):
        """Une part de citation est relative aux entités suivies."""
        raw = json.loads(PANEL.read_text(encoding="utf-8"))
        raw["entities"] = raw["entities"][:-1]
        after = wave_from(Market.from_dict(raw), {"ferrand": 20}, J60)
        with self.assertRaises(Incomparable):
            check_comparable(self.before, after)

    def test_different_providers_are_refused(self):
        after = wave_from(self.market, {"ferrand": 20}, J60)
        after.providers = ["autre-moteur"]
        with self.assertRaises(Incomparable):
            check_comparable(self.before, after)

    def test_reversed_order_is_refused(self):
        after = wave_from(self.market, {"ferrand": 20}, date(2026, 1, 1))
        with self.assertRaises(Incomparable):
            check_comparable(self.before, after)


class TestBootstrap(unittest.TestCase):
    def setUp(self):
        self.market = market()
        self.before = wave_from(self.market, {"ferrand": 5, "cazenave": 20}, J0)
        self.after = wave_from(self.market, {"ferrand": 30, "cazenave": 20}, J60)

    def test_interval_is_deterministic(self):
        first = paired_bootstrap_presence(self.before, self.after, "ferrand")
        second = paired_bootstrap_presence(self.before, self.after, "ferrand")
        self.assertEqual(first, second)

    def test_interval_brackets_the_observed_delta(self):
        low, high = paired_bootstrap_presence(self.before, self.after, "ferrand")
        observed = self.after.presence("ferrand") - self.before.presence("ferrand")
        self.assertLessEqual(low, observed)
        self.assertGreaterEqual(high, observed)

    def test_no_change_yields_an_interval_containing_zero(self):
        low, high = paired_bootstrap_presence(self.before, self.after, "cazenave")
        self.assertLessEqual(low, 0.0)
        self.assertGreaterEqual(high, 0.0)

    def test_share_and_presence_intervals_are_distinct_measures(self):
        share = paired_bootstrap(self.before, self.after, "ferrand")
        presence = paired_bootstrap_presence(self.before, self.after, "ferrand")
        self.assertNotEqual(share, presence)


class TestCompare(unittest.TestCase):
    def setUp(self):
        self.market = market()
        self.treated = [e.id for e in self.market.entities if e.is_treated(J60)]
        self.assertGreaterEqual(len(self.treated), 1)

    def _comparison(self) -> Comparison:
        stable = {"cazenave": 20, "girondin-batisseur": 25, "duviella": 15,
                  "peyrouny": 10, "loustau": 8, "vignau": 6}
        before = wave_from(self.market, {**stable, "ferrand": 5}, J0)
        after = wave_from(self.market, {**stable, "ferrand": 35}, J60)
        return compare(self.market, before, after, draws=200)

    def test_treated_and_controls_are_split_by_date(self):
        comparison = self._comparison()
        self.assertEqual(comparison.treated_count, len(self.treated))
        self.assertEqual(
            comparison.control_count, len(self.market.entities) - len(self.treated)
        )

    def test_attributable_effect_is_estimated_on_presence(self):
        """La part est compositionnelle: un gain chez un traité fait baisser les
        témoins mécaniquement, ce qui biaiserait l'estimateur."""
        comparison = self._comparison()
        self.assertIsNotNone(comparison.did)
        self.assertIsNotNone(comparison.share_did)
        payload = comparison.to_dict()
        self.assertIn("attributable_presence_gain", payload)
        self.assertIn("compositionnel", payload["estimator_note"])

    def test_untouched_control_is_never_declared_established(self):
        comparison = self._comparison()
        for delta in comparison.controls:
            if delta.presence_delta == 0:
                self.assertEqual(delta.verdict, INCONCLUSIVE, delta.name)

    def test_a_real_gain_is_established(self):
        comparison = self._comparison()
        ferrand = comparison.delta_for("ferrand")
        self.assertGreater(ferrand.presence_delta, 0)
        self.assertEqual(ferrand.verdict, ESTABLISHED)

    def test_small_movement_falls_under_the_noise_floor(self):
        noisy = {f"e{i}": 0 for i in range(0)}
        controls = ["cazenave", "girondin-batisseur", "duviella", "peyrouny",
                    "loustau", "vignau", "duprat", "lespiault"]
        before = wave_from(self.market, {c: 20 for c in controls} | {"ferrand": 20}, J0)
        after = wave_from(
            self.market,
            {c: 20 + (i % 5) * 3 for i, c in enumerate(controls)} | {"ferrand": 21},
            J60,
        )
        comparison = compare(self.market, before, after, draws=200)
        ferrand = comparison.delta_for("ferrand")
        self.assertGreater(comparison.noise_floor, 0)
        self.assertIn(ferrand.verdict, {UNDER_NOISE, INCONCLUSIVE})

    def test_without_controls_nothing_is_established(self):
        raw = json.loads(PANEL.read_text(encoding="utf-8"))
        for entity in raw["entities"]:
            entity["treated_since"] = "2026-01-01"
        small = Market.from_dict(raw)
        before = wave_from(small, {"ferrand": 5}, J0)
        after = wave_from(small, {"ferrand": 40}, J60)
        comparison = compare(small, before, after, draws=200)
        self.assertEqual(comparison.control_count, 0)
        self.assertIsNone(comparison.did)
        self.assertTrue(all(d.verdict == INCONCLUSIVE for d in comparison.deltas))
        self.assertTrue(any("groupe témoin" in w for w in comparison.warnings))

    def test_simulated_waves_are_never_reportable(self):
        before = wave_from(self.market, {"ferrand": 5}, J0, EVIDENCE_SYNTHETIC)
        after = wave_from(self.market, {"ferrand": 30}, J60, EVIDENCE_SYNTHETIC)
        comparison = compare(self.market, before, after, draws=100)
        self.assertFalse(comparison.is_reportable)
        self.assertTrue(any("simulée" in w for w in comparison.warnings))


class TestReports(unittest.TestCase):
    def setUp(self):
        self.market = market()
        stable = {"cazenave": 20, "girondin-batisseur": 25, "duviella": 15,
                  "peyrouny": 10, "loustau": 8, "vignau": 6}
        self.before = wave_from(self.market, {**stable, "ferrand": 5}, J0)
        self.after = wave_from(self.market, {**stable, "ferrand": 35}, J60)
        self.comparison = compare(self.market, self.before, self.after, draws=200)

    def test_modelled_value_refuses_a_negative_or_absent_gain(self):
        self.assertIsNone(modelled_value(self.market, -0.05))
        self.assertIsNone(modelled_value(self.market, 0.0))
        raw = json.loads(PANEL.read_text(encoding="utf-8"))
        raw.pop("economics", None)
        self.assertIsNone(modelled_value(Market.from_dict(raw), 0.1))

    def test_modelled_value_shows_its_inputs_and_its_caveat(self):
        value = modelled_value(self.market, 0.1)
        for key in ("monthly_intent_volume", "close_rate", "avg_deal_value", "caveat"):
            self.assertIn(key, value)
        self.assertIn("pas un chiffre d'affaires attribué", value["caveat"])

    def test_client_report_never_claims_credit(self):
        report = client_report(self.comparison, self.market, "ferrand")
        for banned in ("grâce à nous", "grâce à notre", "nous vous avons"):
            self.assertNotIn(banned, report.lower())

    def test_client_report_states_what_it_does_not_say(self):
        report = client_report(self.comparison, self.market, "ferrand")
        self.assertIn("CE QUE CE RAPPORT NE DIT PAS", report)
        self.assertIn("ne garantissons aucune", report)

    def test_client_report_counts_questions_not_percentages_first(self):
        report = client_report(self.comparison, self.market, "ferrand")
        self.assertIn("question(s) sur", report)

    def test_unreportable_comparison_is_marked_internal(self):
        before = wave_from(self.market, {"ferrand": 5}, J0, EVIDENCE_SYNTHETIC)
        after = wave_from(self.market, {"ferrand": 30}, J60, EVIDENCE_SYNTHETIC)
        comparison = compare(self.market, before, after, draws=100)
        self.assertIn(
            "NE PAS REMETTRE AU CLIENT", client_report(comparison, self.market, "ferrand")
        )

    def test_internal_text_leads_with_the_attributable_effect(self):
        text = to_text(self.comparison, self.market)
        self.assertIn("EFFET ATTRIBUABLE", text)
        self.assertIn("Plancher de bruit", text)
        self.assertIn("compositionnel", text)


class TestTrack(unittest.TestCase):
    """Le suivi descriptif J0 -> J7 -> J30: pas de témoin, pas de causalité.
    Ce que ces tests protègent, c'est que `track()` ne se mette jamais à
    ressembler à `compare()` — aucun verdict, aucun intervalle."""

    def setUp(self):
        self.market = market()
        self.j0 = wave_from(self.market, {"ferrand": 2}, J0)
        self.j0.label = "J0"
        self.j30 = wave_from(self.market, {"ferrand": 20}, J60)
        self.j30.label = "J30"

    def test_points_are_ordered_by_date_regardless_of_input_order(self):
        points = track([self.j30, self.j0], "ferrand")
        self.assertEqual([p.observed_on for p in points], [J0, J60])

    def test_presence_rate_reflects_each_wave_independently(self):
        points = track([self.j0, self.j30], "ferrand")
        self.assertLess(points[0].presence_rate, points[1].presence_rate)

    def test_blind_spot_count_is_prompts_minus_hits(self):
        points = track([self.j0], "ferrand")
        prompt_count = len(self.j0.usable_prompt_ids)
        hits = round(points[0].presence_rate * prompt_count)
        self.assertEqual(points[0].blind_spot_count, prompt_count - hits)

    def test_an_entity_absent_from_every_wave_tracks_at_zero(self):
        points = track([self.j0, self.j30], "cazenave")
        self.assertTrue(all(p.presence_rate == 0.0 for p in points))

    def test_rendered_text_carries_the_no_causality_caveat(self):
        text = track_to_text(track([self.j0, self.j30], "ferrand"), "Atelier Ferrand")
        self.assertIn("ne prouve aucune causalité", text)
        self.assertNotIn("établi", text.lower())


if __name__ == "__main__":
    unittest.main()
