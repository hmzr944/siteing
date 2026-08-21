"""La Page de Vérité, contenu et conception.

La seconde classe de ce fichier encode mécaniquement le contrôle avant livraison
de la charte de design. Une règle de conception qui n'est pas testée est une
règle qui sera violée à la prochaine modification: elles sont donc ici, au même
titre que le calcul des statuts.
"""

import html
import math
import re
import unittest
from datetime import date
from pathlib import Path

from citation_audit.dossier import Claim, Dossier
from citation_audit.verite import fr_date, to_document, to_html

FIXTURE = Path(__file__).resolve().parent.parent / "dossiers" / "vasseur.json"
TODAY = date(2026, 8, 8)


def page():
    return to_html(Dossier.load(FIXTURE), TODAY)


class TestContent(unittest.TestCase):
    def setUp(self):
        self.dossier = Dossier.load(FIXTURE)
        self.html = page()

    def test_french_dates_are_spelled_out(self):
        self.assertEqual(fr_date(date(2026, 3, 12)), "12 mars 2026")
        self.assertEqual(fr_date(None), "sans date")

    def test_names_the_entity_and_its_legal_identifier(self):
        self.assertIn(self.dossier.name, self.html)
        self.assertIn(self.dossier.legal_id, self.html)

    def test_shows_every_claim_verified_or_not(self):
        for claim in self.dossier.claims:
            self.assertIn(claim.label, self.html, claim.key)

    def test_unverified_claims_are_listed_in_their_own_section(self):
        """La section qui rend le reste croyable."""
        self.assertIn("Ce qui n'est pas vérifié", self.html)
        gaps = self.html.split("Ce qui n'est pas vérifié", 1)[1]
        for claim in self.dossier.stale(TODAY):
            self.assertIn(claim.label, gaps, claim.key)

    def test_expired_control_states_the_date_it_lapsed(self):
        expired = [c for c in self.dossier.claims if c.status(TODAY) == "expire"]
        self.assertTrue(expired)
        self.assertIn(fr_date(expired[0].valid_until), self.html)

    def test_evidence_references_are_shown_for_verified_claims(self):
        for claim in self.dossier.publishable(TODAY):
            for item in claim.evidence:
                self.assertIn(html.escape(item.reference), self.html, claim.key)

    def test_embeds_jsonld_for_machine_reading(self):
        self.assertIn('<script type="application/ld+json">', self.html)
        self.assertIn("https://schema.org", self.html)

    def test_jsonld_cannot_escape_its_script_block(self):
        """Une valeur hostile ne doit pas pouvoir fermer le bloc script."""
        dossier = Dossier.load(FIXTURE)
        dossier.claims.append(
            Claim(
                key="hostile",
                label="Injection",
                value='</script><script>alert("x")</script>',
                cluster="capacite",
                evidence=dossier.claims[0].evidence,
                verified_on=date(2026, 6, 1),
                valid_until=date(2027, 6, 1),
            )
        )
        rendered = to_html(dossier, TODAY)
        self.assertEqual(rendered.count("<script"), 1, "un second script a été injecté")
        self.assertIn("\\u003c/script", rendered)

    def test_escapes_hostile_text_in_the_human_layer(self):
        dossier = Dossier.load(FIXTURE)
        dossier.name = '<img src=x onerror="alert(1)">'
        rendered = to_html(dossier, TODAY)
        self.assertNotIn("<img src=x", rendered)
        self.assertIn("&lt;img", rendered)

    def test_never_mentions_slots_or_exclusivity(self):
        """La page ne varie jamais selon un palier commercial: ce n'est plus
        une fonctionnalité de ce module, voir docs/PLAN.md §1."""
        for term in ("Créneaux détenus", "exclusif", "Exclusif", "palier"):
            self.assertNotIn(term, self.html)

    def test_no_photo_means_no_substitute_image(self):
        """Une image d'illustration sur un registre de vérification détruirait
        ce que la page sert à établir."""
        self.assertIsNone(Dossier.load(FIXTURE).photo_url)
        self.assertNotIn("<img", self.html)

    def test_document_wrapper_is_a_complete_page(self):
        document = to_document(Dossier.load(FIXTURE), TODAY)
        self.assertTrue(document.startswith("<!doctype html>"))
        self.assertEqual(document.count("<main"), 1)
        self.assertEqual(document.count("<style>"), 1)
        self.assertIn('name="description"', document)
        self.assertIn("</html>", document)


class TestDesignPreFlight(unittest.TestCase):
    """Contrôle avant livraison, exécuté sur le HTML réellement produit."""

    def setUp(self):
        self.html = page()

    def test_zero_em_dashes_or_en_dashes(self):
        found = [c for c in "—–" if c in self.html]
        self.assertEqual(found, [], f"tiret(s) cadratin interdits: {found}")

    def test_eyebrow_count_within_the_cap(self):
        """Un eyebrow par tranche de trois sections, pas un par section."""
        sections = self.html.count("<h2") + 1  # + l'en-tête
        eyebrows = len(re.findall(r'class="eyebrow"', self.html))
        self.assertLessEqual(eyebrows, math.ceil(sections / 3), f"{eyebrows} eyebrows")

    def test_single_shape_system(self):
        """Radius 0 assumé: un registre n'a pas de cartes arrondies."""
        radii = set(re.findall(r"border-radius:\s*([^;}]+)", self.html))
        self.assertEqual(radii, set(), f"systèmes de forme mélangés: {radii}")

    def test_middle_dot_is_rationed_to_one_per_visible_line(self):
        text = re.sub(r"<[^>]+>", " ", self.html)
        for line in text.splitlines():
            self.assertLessEqual(line.count("·"), 1, f"points médians: {line.strip()[:70]}")

    def test_no_scroll_cue_or_build_stamp(self):
        lowered = self.html.lower()
        for banned in ("scroll to", "défiler", "↓", "build ", " v1.", "beta"):
            self.assertNotIn(banned, lowered, f"motif interdit: {banned!r}")

    def test_no_static_motion_claim(self):
        """La page se dit sans animation: elle ne doit en contenir aucune."""
        self.assertNotIn("@keyframes", self.html)
        self.assertNotIn("animation:", self.html)

    def test_every_token_is_defined_in_the_unstamped_root(self):
        base = self.html.split("@media", 1)[0]
        declared = set(re.findall(r"(--[a-z-]+):", re.search(r":root\{(.*?)\}", base, re.S).group(1)))
        used = set(re.findall(r"var\((--[a-z-]+)\)", self.html))
        self.assertEqual(used - declared, set(), "jeton utilisé sans définition en clair")

    def test_both_dark_paths_define_the_same_tokens(self):
        media = re.search(
            r'@media \(prefers-color-scheme:dark\)\{\s*:root:not\(\[data-theme="light"\]\)\{(.*?)\}',
            self.html, re.S,
        )
        stamped = re.search(r':root\[data-theme="dark"\]\{(.*?)\}', self.html, re.S)
        self.assertIsNotNone(media, "préférence système non gérée")
        self.assertIsNotNone(stamped, "choix explicite non géré")
        self.assertEqual(
            set(re.findall(r"(--[a-z-]+):", media.group(1))),
            set(re.findall(r"(--[a-z-]+):", stamped.group(1))),
        )

    def test_body_paints_its_own_ground(self):
        body = re.search(r"\bbody\{(.*?)\}", self.html, re.S)
        self.assertIn("background:var(--paper)", body.group(1))

    def test_accent_is_used_through_one_token_only(self):
        """Verrou de couleur: un seul accent, jamais un littéral parachuté."""
        literals = set(re.findall(r"#[0-9a-fA-F]{3,6}", self.html))
        base = self.html.split("*{box-sizing", 1)[0]
        token_literals = set(re.findall(r"#[0-9a-fA-F]{3,6}", base))
        self.assertEqual(
            literals - token_literals, set(), "couleur codée en dur hors des jetons"
        )

    def test_focus_is_visible_for_keyboard_users(self):
        self.assertIn(":focus-visible", self.html)

    def test_wide_content_scrolls_inside_its_own_container(self):
        self.assertNotIn("white-space:nowrap", self.html)
        self.assertIn("overflow-wrap:anywhere", self.html)


if __name__ == "__main__":
    unittest.main()
