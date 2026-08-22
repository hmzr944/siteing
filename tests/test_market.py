"""Le panier doit être figé: c'est ce qui rend deux relevés comparables."""

import copy
import json
import unittest
from pathlib import Path

from citation_audit.market import FAMILY_CAPS, Market, scaffold

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


class TestProspectingBasket(unittest.TestCase):
    """Le panier de l'Audit d'Invisibilité (docs/VENTE.md): un sous-ensemble
    du panier complet, jamais une liste distincte de prompts."""

    def setUp(self):
        self.market = Market.load(FIXTURE)

    def test_is_a_strict_subset_of_the_full_basket(self):
        full = {p.id for p in self.market.basket()}
        reduced = {p.id for p in self.market.prospecting_basket(12)}
        self.assertTrue(reduced <= full)

    def test_respects_the_limit(self):
        self.assertLessEqual(len(self.market.prospecting_basket(12)), 12)
        self.assertLessEqual(len(self.market.prospecting_basket(3)), 3)

    def test_keeps_the_highest_commercial_weight_prompts(self):
        """C'est ce qui rend le panier convaincant en 90 secondes: les
        questions les plus proches d'une décision d'achat, pas un tirage."""
        reduced = self.market.prospecting_basket(5)
        full_sorted = sorted(self.market.basket(), key=lambda p: -p.weight)
        self.assertEqual({p.id for p in reduced}, {p.id for p in full_sorted[:5]})

    def test_is_deterministic(self):
        self.assertEqual(
            [p.id for p in self.market.prospecting_basket(12)],
            [p.id for p in Market.load(FIXTURE).prospecting_basket(12)],
        )

    def test_is_too_small_to_be_presentable_as_the_contractual_measurement(self):
        """Le seuil de présentabilité (score.MIN_PROMPTS) doit rester au-dessus
        de la taille du panier de prospection — sinon l'Audit d'Invisibilité
        pourrait se faire passer pour le relevé vendu, ce que docs/VENTE.md
        interdit explicitement."""
        from citation_audit.score import MIN_PROMPTS

        self.assertLess(len(self.market.prospecting_basket(12)), MIN_PROMPTS)


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


class TestScaffold(unittest.TestCase):
    """Le fichier de marché rapide pour un entretien terrain: doit produire un
    marché valide, pas juste un JSON qui a l'air correct."""

    def test_produces_a_valid_market_with_a_designated_client(self):
        market = scaffold(
            "Atelier Ferrand", "rénovation", "Bordeaux",
            competitors=["Bâti Concept", "Rénov Sud-Ouest"],
        )
        self.assertTrue(market.has_client)
        self.assertEqual(market.client.name, "Atelier Ferrand")
        self.assertEqual(len(market.competitors), 2)
        self.assertGreater(len(market.basket()), 0)

    def test_id_is_derived_from_the_client_name_when_not_given(self):
        market = scaffold("Atelier Ferrand", "rénovation", "Bordeaux", ["X"])
        self.assertEqual(market.id, "atelier-ferrand")

    def test_refuses_without_a_named_competitor(self):
        """Sans concurrent, il n'y a pas de marché, seulement une marque
        isolée: rien à comparer, donc rien à mesurer."""
        with self.assertRaises(ValueError):
            scaffold("Atelier Ferrand", "rénovation", "Bordeaux", competitors=[])

    def test_round_trips_through_from_dict(self):
        """Ce que produit `amorce` en CLI doit être un JSON que `Market.load`
        accepte tel quel, pas seulement l'objet en mémoire."""
        market = scaffold("Atelier Ferrand", "rénovation", "Bordeaux", ["X", "Y"])
        payload = {
            "id": market.id,
            "label": market.label,
            "category": market.category,
            "zone": market.zone,
            "entities": [
                {"name": e.name, "is_client": e.is_client, "domains": list(e.domains)}
                for e in market.entities
            ],
        }
        reloaded = Market.from_dict(payload)
        self.assertEqual(reloaded.client.name, market.client.name)
        self.assertEqual([p.id for p in reloaded.basket()], [p.id for p in market.basket()])


if __name__ == "__main__":
    unittest.main()
