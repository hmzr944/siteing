"""L'Audit d'Invisibilité (docs/VENTE.md §1): l'arme de prospection.

Ce que ces tests défendent avant tout: cette sortie ne doit jamais pouvoir se
lire comme le relevé contractuel, et l'e-mail généré ne doit jamais nommer un
concurrent qui n'a pas été réellement cité.
"""

import unittest
from pathlib import Path

from citation_audit.market import Market
from citation_audit.prospection import email_jour_0, to_text
from citation_audit.providers import EVIDENCE_MEASURED, EngineResponse
from citation_audit.score import compute

FIXTURE = Path(__file__).resolve().parent.parent / "markets" / "plombier-bordeaux.json"


def market() -> Market:
    return Market.load(FIXTURE)


def result_with_blind_spots():
    m = market()
    prompts = m.prospecting_basket(12)
    rival = m.competitors[0]
    # Le concurrent est cité sur tout le panier réduit, jamais le client:
    # panier d'angles morts maximal, déterministe.
    responses = [EngineResponse(p.id, f"1. {rival.name} recommandé.", []) for p in prompts]
    result = compute(m, prompts, [("moteur", EVIDENCE_MEASURED, responses)])
    return result, rival


class TestProspectingText(unittest.TestCase):
    def test_carries_the_indicative_mention_verbatim(self):
        result, _ = result_with_blind_spots()
        text = to_text(result)
        self.assertIn("relevé indicatif", text)
        self.assertIn("PAS le relevé contractuel", text)

    def test_names_the_client_and_the_real_competitor(self):
        result, rival = result_with_blind_spots()
        text = to_text(result)
        self.assertIn(result.client_score.name, text)
        self.assertIn(rival.name, text)

    def test_states_the_presence_rate(self):
        result, _ = result_with_blind_spots()
        text = to_text(result)
        self.assertIn(f"{result.usable_prompt_count} questions testées", text)

    def test_no_blind_spots_says_so_rather_than_fabricating_one(self):
        m = market()
        prompts = m.prospecting_basket(12)
        responses = [EngineResponse(p.id, f"1. {m.client.name} recommandé.", []) for p in prompts]
        result = compute(m, prompts, [("moteur", EVIDENCE_MEASURED, responses)])
        text = to_text(result)
        self.assertIn("Aucun angle mort", text)


class TestEmailJour0(unittest.TestCase):
    def test_names_the_competitor_actually_cited_most(self):
        result, rival = result_with_blind_spots()
        email = email_jour_0(result, "Marc", "https://exemple.fr/v", "Julien")
        self.assertIn(rival.name, email)
        self.assertIn(result.client_score.name, email)
        self.assertIn("Marc", email)
        self.assertIn("https://exemple.fr/v", email)
        self.assertIn("Julien", email)

    def test_refuses_to_write_an_email_with_no_competitor_to_name(self):
        """Un e-mail « vous n'apparaissez pas » sans concurrent réellement cité
        serait un mensonge par construction: on refuse plutôt que d'inventer."""
        m = market()
        prompts = m.prospecting_basket(12)
        responses = [EngineResponse(p.id, f"1. {m.client.name} recommandé.", []) for p in prompts]
        result = compute(m, prompts, [("moteur", EVIDENCE_MEASURED, responses)])
        with self.assertRaises(ValueError):
            email_jour_0(result, "Marc", "https://exemple.fr/v", "Julien")

    def test_object_line_matches_the_playbook(self):
        result, _ = result_with_blind_spots()
        email = email_jour_0(result, "Marc", "https://exemple.fr/v", "Julien")
        self.assertTrue(email.startswith("Objet : Vous n'apparaissez pas"))


if __name__ == "__main__":
    unittest.main()
