"""Le rapport est l'objet remis au dirigeant: il doit être exact, échappé,
et incapable de se faire passer pour un audit quand il n'en est pas un."""

import re
import unittest
from pathlib import Path

from citation_audit.market import Entity, Market
from citation_audit.providers import EVIDENCE_MEASURED, EVIDENCE_SYNTHETIC, EngineResponse
from citation_audit.report import eur, pct, to_html, to_text
from citation_audit.score import compute

FIXTURE = Path(__file__).resolve().parent.parent / "markets" / "plombier-bordeaux.json"


def build(evidence=EVIDENCE_MEASURED, engines=2):
    market = Market.load(FIXTURE)
    prompts = market.basket()
    rival = market.competitors[0]
    responses = [
        EngineResponse(p.id, f"1. {rival.name} — très bien noté.", []) for p in prompts
    ]
    runs = [(f"moteur-{i}", evidence, responses) for i in range(engines)]
    return market, compute(market, prompts, runs)


class TestFormatting(unittest.TestCase):
    def test_percent_uses_french_decimal_comma(self):
        self.assertEqual(pct(0.1234, 1).replace(" ", " "), "12,3 %")

    def test_euro_groups_thousands(self):
        self.assertEqual(eur(1552320).replace(" ", " "), "1 552 320 €")


class TestText(unittest.TestCase):
    def test_summary_names_the_client_and_the_leader(self):
        market, result = build()
        text = to_text(result)
        self.assertIn(market.client.name, text)
        self.assertIn(market.competitors[0].name, text)
        self.assertIn("ANGLES MORTS", text)


class TestHtml(unittest.TestCase):
    def test_contains_single_title_and_no_document_scaffolding(self):
        _, result = build()
        html = to_html(result)
        self.assertEqual(html.count("<title>"), 1)
        # Le squelette de document est ajouté à la publication: en écrire un
        # second produirait un HTML imbriqué. `<header>` ne compte pas.
        scaffolding = re.search(r"<(!doctype|html|head|body)[\s>]", html, re.I)
        self.assertIsNone(scaffolding, scaffolding.group(0) if scaffolding else "")

    def test_reports_the_measured_figures(self):
        _, result = build()
        html = to_html(result)
        self.assertIn(pct(result.client_score.presence_rate, 0), html)
        self.assertIn(eur(result.value_estimate.annual_missed), html)

    def test_names_the_competitor_cited_instead(self):
        market, result = build()
        self.assertIn(market.competitors[0].name, to_html(result))

    def test_synthetic_report_carries_a_do_not_send_banner(self):
        _, result = build(evidence=EVIDENCE_SYNTHETIC)
        self.assertIn("ne pas remettre au client", to_html(result))

    def test_measured_report_has_no_banner(self):
        _, result = build()
        self.assertNotIn("ne pas remettre au client", to_html(result))

    def test_escapes_hostile_entity_names(self):
        market = Market.load(FIXTURE)
        market.entities.append(
            Entity(id="xss", name='<script>alert("x")</script>', strength=0.9)
        )
        prompts = market.basket()
        responses = [EngineResponse(p.id, "Aquitaine Dépannage.", []) for p in prompts]
        result = compute(market, prompts, [("m", EVIDENCE_MEASURED, responses)])
        html = to_html(result)
        self.assertNotIn("<script>", html)
        self.assertIn("&lt;script&gt;", html)

    def test_every_colour_token_is_defined_in_the_base_root(self):
        """Un jeton défini seulement sous @media ou [data-theme] rend la page
        illisible dans l'état « système » non estampillé."""
        _, result = build()
        html = to_html(result)
        base = html.split("@media", 1)[0]
        base_root = re.search(r":root\{(.*?)\}", base, re.S)
        self.assertIsNotNone(base_root)
        declared = set(re.findall(r"(--[a-z-]+):", base_root.group(1)))
        used = set(re.findall(r"var\((--[a-z-]+)\)", html))
        self.assertEqual(used - declared, set(), "jetons utilisés mais jamais définis en clair")

    def test_both_themes_redefine_the_same_token_set(self):
        _, result = build()
        html = to_html(result)
        media = re.search(r'@media \(prefers-color-scheme:dark\)\{\s*:root:not\(\[data-theme="light"\]\)\{(.*?)\}', html, re.S)
        stamped = re.search(r':root\[data-theme="dark"\]\{(.*?)\}', html, re.S)
        self.assertIsNotNone(media)
        self.assertIsNotNone(stamped)
        self.assertEqual(
            set(re.findall(r"(--[a-z-]+):", media.group(1))),
            set(re.findall(r"(--[a-z-]+):", stamped.group(1))),
            "la préférence système et le choix explicite doivent donner le même thème",
        )

    def test_body_paints_its_own_background(self):
        _, result = build()
        body_rule = re.search(r"\bbody\{(.*?)\}", to_html(result), re.S)
        self.assertIsNotNone(body_rule)
        self.assertIn("background:var(--ground)", body_rule.group(1))


if __name__ == "__main__":
    unittest.main()
