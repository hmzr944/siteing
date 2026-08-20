"""Le modèle économique sert à décider d'un investissement: ses invariants
doivent être testés comme du code de production.

Deux mouvements commerciaux cohabitent (Forfait en self-serve, Exclusif en
sortant) et n'ont pas à réussir le même examen: le Forfait est un canal de
volume et de couverture du registre, pas un centre de profit autonome — ces
tests le vérifient explicitement plutôt que de le cacher derrière un ARPU
moyen.
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

from economics import Assumptions, _ramp, project  # noqa: E402


class TestForfaitMotion(unittest.TestCase):
    """Gratuit -> Forfait (19 €/mois), self-serve. Le canal de volume."""

    def setUp(self):
        self.a = Assumptions()

    def test_price_matches_the_accessible_positioning(self):
        self.assertEqual(self.a.forfait_price, 19)

    def test_eventual_conversion_share_is_the_relative_rate(self):
        expected = self.a.convert_rate / (self.a.convert_rate + self.a.churn_free)
        self.assertAlmostEqual(self.a.eventual_conversion_share, expected)

    def test_effective_cac_accounts_for_free_users_who_never_convert(self):
        """Le CAC « brut » (coût d'inscription seul) sous-estimerait la vraie
        facture: la plupart des inscrits gratuits ne convertissent jamais, et
        leur hébergement a un coût qui doit être amorti sur ceux qui paient."""
        naive_cac = self.a.cost_per_signup / self.a.eventual_conversion_share
        self.assertGreater(self.a.effective_cac_forfait, naive_cac)

    def test_forfait_alone_is_below_the_classic_health_bar(self):
        """C'est un constat assumé, pas un bug à corriger en gonflant les
        hypothèses: à ce prix, ce palier ne peut structurellement pas être un
        centre de profit isolé (comparer Linktree, <1$/utilisateur/an, cité
        dans docs/PLAN.md). Il finance sa place par le volume et la
        couverture du registre, pas par sa propre marge."""
        ratio = self.a.ltv_forfait / self.a.effective_cac_forfait
        self.assertGreater(ratio, 1.0, "en dessous de 1x, ce canal détruit de la valeur")
        self.assertLess(ratio, 3.0, "au-dessus de 3x, ce n'est plus un canal de volume à 19 €")

    def test_higher_free_churn_lowers_eventual_conversion(self):
        patient = Assumptions(churn_free=0.05)
        volatile = Assumptions(churn_free=0.20)
        self.assertGreater(patient.eventual_conversion_share, volatile.eventual_conversion_share)


class TestExclusifMotion(unittest.TestCase):
    """Sortant -> Exclusif, playbook docs/VENTE.md inchangé. Le moteur de profit."""

    def setUp(self):
        self.a = Assumptions()

    def test_ratios_stay_in_plausible_territory(self):
        ratio = self.a.ltv_exclusif / self.a.cac_exclusif
        self.assertGreater(ratio, 3.0, "modèle non viable")
        self.assertLess(ratio, 25.0, "hypothèses trop flatteuses")
        self.assertGreater(self.a.payback_months_exclusif, 1.0, "retour sur CAC irréaliste")

    def test_higher_churn_shortens_life_and_lowers_ltv(self):
        patient = Assumptions(monthly_churn_exclusif=0.015)
        volatile = Assumptions(monthly_churn_exclusif=0.06)
        self.assertGreater(patient.lifetime_months_exclusif, volatile.lifetime_months_exclusif)
        self.assertGreater(patient.ltv_exclusif, volatile.ltv_exclusif)

    def test_model_survives_pessimistic_churn(self):
        degraded = Assumptions(monthly_churn_exclusif=0.05)
        self.assertGreater(degraded.ltv_exclusif / degraded.cac_exclusif, 3.0)


class TestRamp(unittest.TestCase):
    def test_ramp_starts_low_and_reaches_target(self):
        a = Assumptions()
        self.assertEqual(
            _ramp(a.free_signups_first_month, a.free_signups_steady, a.free_signups_ramp_months, 1),
            a.free_signups_first_month,
        )
        self.assertEqual(
            _ramp(
                a.free_signups_first_month, a.free_signups_steady,
                a.free_signups_ramp_months, a.free_signups_ramp_months,
            ),
            a.free_signups_steady,
        )
        self.assertEqual(
            _ramp(a.free_signups_first_month, a.free_signups_steady, a.free_signups_ramp_months, 99),
            a.free_signups_steady,
        )

    def test_ramp_is_monotonic(self):
        a = Assumptions()
        values = [
            _ramp(a.free_signups_first_month, a.free_signups_steady, a.free_signups_ramp_months, m)
            for m in range(1, a.free_signups_ramp_months + 3)
        ]
        self.assertEqual(values, sorted(values))


class TestProjection(unittest.TestCase):
    def setUp(self):
        self.a = Assumptions()
        self.rows = project(self.a, 36)

    def test_populations_never_go_negative(self):
        for row in self.rows:
            self.assertGreaterEqual(row.free_users, 0)
            self.assertGreaterEqual(row.forfait_clients, 0)
            self.assertGreaterEqual(row.exclusif_clients, 0)

    def test_client_bases_grow_over_the_ramp(self):
        self.assertLess(self.rows[0].forfait_clients, self.rows[11].forfait_clients)
        self.assertLess(self.rows[0].exclusif_clients, self.rows[11].exclusif_clients)

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

    def test_exclusif_revenue_dominates_forfait_revenue(self):
        """Le Forfait couvre le registre en volume, mais c'est l'Exclusif qui
        doit porter l'essentiel du chiffre d'affaires — sinon le modèle s'est
        raconté un palier à 19 € plus rentable qu'il ne peut l'être."""
        last = self.rows[-1]
        forfait_revenue = last.forfait_clients * self.a.forfait_price
        exclusif_revenue = last.exclusif_clients * self.a.exclusif_price
        self.assertGreater(exclusif_revenue, forfait_revenue)


if __name__ == "__main__":
    unittest.main()
