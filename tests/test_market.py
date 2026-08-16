"""Le panier doit être figé: c'est ce qui rend deux relevés comparables."""

import copy
import json
import unittest
from pathlib import Path

from citation_audit.market import FAMILY_CAPS, Market

FIXTURE = Path(__file__).resolve().parent.parent / "markets" / "plombier-bordeaux.json"


def load_raw():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


class TestBasket(unittest.TestCase):
    def setUp(self):
        self.market = Market.load(FIXTURE)

    def test_basket_is_deterministic(self):
        first = self.market.basket()
        second = Market.load(FIXTURE).basket()
        self.assertEqual([p.id for p in first], [p.id for p in second])
        self.assertEqual([p.text for p in first], [p.text for p in second])

    def test_prompt_ids_are_unique(self):
        ids = [p.id for p in self.market.basket()]
        self.assertEqual(len(ids), len(set(ids)))

    def test_every_family_respects_its_cap(self):
        counts: dict[str, int] = {}
        for prompt in self.market.basket():
            counts[prompt.family] = counts.get(prompt.family, 0) + 1
        for family, count in counts.items():
            self.assertLessEqual(count, FAMILY_CAPS[family], family)

    def test_every_family_with_available_modifiers_is_represented(self):
        """Une famille sans matière ne produit rien: le marché plombier n'a pas
        de quartiers déclarés, donc pas de prompts hyperlocaux."""
        families = {p.family for p in self.market.basket()}
        self.assertEqual(families, set(FAMILY_CAPS) - {"hyperlocal"})
        self.assertEqual(self.market.districts, [])

    def test_declaring_districts_activates_the_hyperlocal_family(self):
        raw = load_raw()
        raw["districts"] = ["Chartrons", "Caudéran"]
        families = {p.family for p in Market.from_dict(raw).basket()}
        self.assertIn("hyperlocal", families)

    def test_verification_prompts_name_the_client(self):
        verifications = [p for p in self.market.basket() if p.family == "verification"]
        self.assertTrue(
            any(self.market.client.name in p.text for p in verifications),
            "la réputation de la marque du client doit être testée",
        )

    def test_transactional_prompts_weigh_more_than_discovery(self):
        by_family = {p.family: p.weight for p in self.market.basket()}
        self.assertGreater(by_family["transactionnel"], by_family["decouverte"])


class TestBasketVersion(unittest.TestCase):
    def test_version_is_stable_across_loads(self):
        self.assertEqual(Market.load(FIXTURE).basket_version, Market.load(FIXTURE).basket_version)

    def test_version_changes_when_the_panel_changes(self):
        raw = load_raw()
        before = Market.from_dict(copy.deepcopy(raw)).basket_version
        raw["services"].append("l'installation d'un adoucisseur")
        self.assertNotEqual(before, Market.from_dict(raw).basket_version)

    def test_version_ignores_demo_only_strength(self):
        """`strength` ne pilote que le moteur simulé: il ne doit pas invalider
        la comparabilité d'un relevé à l'autre."""
        raw = load_raw()
        before = Market.from_dict(copy.deepcopy(raw)).basket_version
        raw["entities"][0]["strength"] = 0.99
        self.assertEqual(before, Market.from_dict(raw).basket_version)


class TestValidation(unittest.TestCase):
    def test_market_without_client_is_a_measurement_panel(self):
        """Zéro client n'est pas une erreur: c'est une cohorte de ligne de base.
        Demander le client d'un panel, en revanche, en est une."""
        raw = load_raw()
        raw["entities"][0]["is_client"] = False
        panel = Market.from_dict(raw)
        self.assertFalse(panel.has_client)
        self.assertEqual(len(panel.basket()), len(Market.load(FIXTURE).basket()))
        with self.assertRaises(ValueError):
            _ = panel.client

    def test_rejects_market_with_two_clients(self):
        raw = load_raw()
        raw["entities"][1]["is_client"] = True
        with self.assertRaises(ValueError):
            Market.from_dict(raw)

    def test_economics_are_optional(self):
        raw = load_raw()
        raw.pop("economics")
        self.assertIsNone(Market.from_dict(raw).economics)


if __name__ == "__main__":
    unittest.main()
