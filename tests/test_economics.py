"""Le modèle économique sert à décider d'un investissement: ses invariants
doivent être testés comme du code de production."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

from economics import Assumptions, project, slots_in_month  # noqa: E402


class TestUnitEconomics(unittest.TestCase):
    def setUp(self):
        self.a = Assumptions()

    def test_arpu_is_the_weighted_mix(self):
        expected = sum(t.price * t.share_of_mix for t in self.a.tiers)
        self.assertAlmostEqual(self.a.arpu, expected)

    def test_tier_mix_sums_to_one(self):
        self.assertAlmostEqual(sum(t.share_of_mix for t in self.a.tiers), 1.0)

    def test_ratios_stay_in_plausible_territory(self):
        """Un modèle qui affiche 60x de LTV/CAC se raconte une histoire."""
        self.assertGreater(self.a.ltv / self.a.cac, 3.0, "modèle non viable")
        self.assertLess(self.a.ltv / self.a.cac, 12.0, "hypothèses trop flatteuses")
        self.assertGreater(self.a.payback_months, 1.0, "retour sur CAC irréaliste")

    def test_higher_churn_shortens_life_and_lowers_ltv(self):
        patient = Assumptions(monthly_churn=0.03)
        volatile = Assumptions(monthly_churn=0.09)
        self.assertGreater(patient.lifetime_months, volatile.lifetime_months)
        self.assertGreater(patient.ltv, volatile.ltv)

    def test_model_survives_pessimistic_churn(self):
        """Test de rupture: à 8 %/mois, le modèle doit rester au-dessus de 3x."""
        self.assertGreater(Assumptions(monthly_churn=0.08).ltv / Assumptions().cac, 3.0)


class TestSalesRamp(unittest.TestCase):
    def test_ramp_starts_low_and_reaches_target(self):
        a = Assumptions()
        self.assertEqual(slots_in_month(a, 1), a.slots_first_month)
        self.assertEqual(slots_in_month(a, a.sales_ramp_months), a.slots_per_month)
        self.assertEqual(slots_in_month(a, 99), a.slots_per_month)

    def test_ramp_is_monotonic(self):
        a = Assumptions()
        values = [slots_in_month(a, m) for m in range(1, a.sales_ramp_months + 3)]
        self.assertEqual(values, sorted(values))


class TestProjection(unittest.TestCase):
    def setUp(self):
        self.a = Assumptions()
        self.rows = project(self.a, 36)

    def test_client_base_grows_then_approaches_steady_state(self):
        counts = [r.clients for r in self.rows]
        self.assertEqual(counts, sorted(counts), "la base ne doit pas décroître en montée")
        ceiling = self.a.slots_per_month / self.a.monthly_churn
        self.assertLess(counts[-1], ceiling * 1.02, "la base dépasse son plafond théorique")

    def test_steady_state_ceiling_is_respected_over_long_horizon(self):
        long_run = project(self.a, 400)
        ceiling = self.a.slots_per_month / self.a.monthly_churn
        self.assertAlmostEqual(long_run[-1].clients, round(ceiling), delta=1)

    def test_reaches_monthly_and_cumulative_breakeven(self):
        self.assertTrue(any(r.ebitda > 0 for r in self.rows))
        self.assertTrue(any(r.cumulative > 0 for r in self.rows))

    def test_monthly_breakeven_precedes_cumulative_breakeven(self):
        monthly = next(r.month for r in self.rows if r.ebitda > 0)
        cumulative = next(r.month for r in self.rows if r.cumulative > 0)
        self.assertLess(monthly, cumulative)

    def test_cumulative_is_the_running_sum_of_ebitda(self):
        running = 0.0
        for row in self.rows:
            running += row.ebitda
            self.assertAlmostEqual(row.cumulative, running, places=6)

    def test_cash_trough_is_financeable_and_precedes_breakeven(self):
        trough = min(self.rows, key=lambda r: r.cumulative)
        breakeven = next(r.month for r in self.rows if r.ebitda > 0)
        self.assertLess(-trough.cumulative, 400_000, "besoin de financement hors cible")
        self.assertLessEqual(trough.month, breakeven)

    def test_attribution_revenue_only_starts_after_the_ramp(self):
        early = self.rows[0]
        self.assertAlmostEqual(
            early.mrr, early.clients * self.a.arpu, delta=self.a.arpu,
            msg="aucune attribution ne doit être comptée au mois 1",
        )


if __name__ == "__main__":
    unittest.main()
