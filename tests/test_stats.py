"""La corrélation décide de la thèse du projet: elle doit être juste, et elle
doit refuser de conclure quand l'échantillon ne le permet pas."""

import unittest

from citation_audit.stats import (
    Correlation,
    incomplete_beta,
    rank_with_ties,
    spearman,
    student_t_two_sided,
)


class TestRanking(unittest.TestCase):
    def test_simple_ranks(self):
        self.assertEqual(rank_with_ties([10.0, 30.0, 20.0]), [1.0, 3.0, 2.0])

    def test_ties_share_the_average_rank(self):
        self.assertEqual(rank_with_ties([5.0, 5.0, 9.0]), [1.5, 1.5, 3.0])

    def test_all_equal_values_share_one_rank(self):
        self.assertEqual(rank_with_ties([7.0, 7.0, 7.0]), [2.0, 2.0, 2.0])


class TestBetaAndT(unittest.TestCase):
    def test_incomplete_beta_bounds(self):
        self.assertEqual(incomplete_beta(2.0, 3.0, 0.0), 0.0)
        self.assertEqual(incomplete_beta(2.0, 3.0, 1.0), 1.0)

    def test_incomplete_beta_symmetry(self):
        """I(a,b,x) = 1 - I(b,a,1-x), identité qui valide la fraction continue."""
        self.assertAlmostEqual(
            incomplete_beta(2.5, 4.5, 0.3), 1 - incomplete_beta(4.5, 2.5, 0.7), places=10
        )

    def test_t_zero_gives_probability_one(self):
        self.assertAlmostEqual(student_t_two_sided(0.0, 10), 1.0, places=10)

    def test_t_known_critical_value(self):
        """t = 2.228 à 10 degrés de liberté correspond à p ≈ 0,05."""
        self.assertAlmostEqual(student_t_two_sided(2.228, 10), 0.05, places=3)

    def test_larger_t_gives_smaller_probability(self):
        self.assertLess(student_t_two_sided(4.0, 10), student_t_two_sided(1.0, 10))


class TestSpearman(unittest.TestCase):
    def test_perfect_positive(self):
        result = spearman([1, 2, 3, 4, 5], [1, 2, 3, 4, 5])
        self.assertAlmostEqual(result.rho, 1.0)
        self.assertEqual(result.p_value, 0.0)

    def test_perfect_negative(self):
        self.assertAlmostEqual(spearman([1, 2, 3, 4, 5], [5, 4, 3, 2, 1]).rho, -1.0)

    def test_matches_the_closed_form_without_ties(self):
        """Sans ex aequo, rho = 1 - 6.Sigma(d²)/(n(n²-1)).

        Ici: rangs x = 1..8, rangs y = [1,4,6,5,8,7,2,3], donc Sigma(d²) = 74
        et rho = 1 - 6*74/(8*63) = 0,119048.
        """
        xs = [86, 97, 99, 100, 101, 103, 106, 110]
        ys = [0, 20, 28, 27, 50, 29, 7, 17]
        self.assertAlmostEqual(spearman(xs, ys).rho, 1 - 6 * 74 / (8 * 63), places=10)

    def test_monotone_transform_of_x_does_not_change_rho(self):
        """Une corrélation de rangs ne dépend que de l'ordre."""
        xs = [1, 2, 3, 4, 5, 6]
        ys = [2, 1, 4, 3, 6, 5]
        squared = [x * x for x in xs]
        self.assertAlmostEqual(spearman(xs, ys).rho, spearman(squared, ys).rho)

    def test_constant_series_yields_no_correlation(self):
        result = spearman([1, 1, 1, 1], [4, 3, 2, 1])
        self.assertEqual(result.rho, 0.0)
        self.assertEqual(result.p_value, 1.0)

    def test_mismatched_lengths_are_rejected(self):
        with self.assertRaises(ValueError):
            spearman([1, 2, 3], [1, 2])

    def test_tiny_sample_never_claims_significance(self):
        result = spearman([1, 2], [2, 1])
        self.assertEqual(result.p_value, 1.0)
        self.assertFalse(result.is_significant)

    def test_noise_is_not_significant_at_n_twenty(self):
        xs = list(range(20))
        ys = [3, 17, 8, 1, 14, 6, 19, 2, 11, 15, 4, 9, 18, 0, 13, 7, 16, 5, 12, 10]
        self.assertFalse(spearman(xs, ys).is_significant)


class TestReading(unittest.TestCase):
    def test_small_panel_refuses_to_conclude(self):
        reading = Correlation(rho=-0.9, p_value=0.001, n=6).reading
        self.assertIn("aucune conclusion possible", reading)

    def test_non_significant_reading_states_the_absence_of_link(self):
        reading = Correlation(rho=-0.10, p_value=0.67, n=20).reading
        self.assertIn("ne prédit pas", reading)

    def test_significant_negative_reads_as_rank_matching_citation(self):
        """Rang Google petit = bon, part de citation grande = bonne: un rho
        négatif signifie donc « bien classé et bien cité »."""
        reading = Correlation(rho=-0.62, p_value=0.003, n=20).reading
        self.assertIn("va de pair avec", reading)


if __name__ == "__main__":
    unittest.main()
