"""Les surfaces sont la porte de sortie de l'infrastructure.

Deux invariants dominent tous les autres: aucune page sans fait, et aucun
vocabulaire d'offre dans le structuré. Le premier protège de la pénalité pour
contenu maigre, le second de la requalification d'un constat en proposition
commerciale.
"""

import json
import re
import unittest
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory

from noyau import MIN_CHANTIERS_TERRITOIRE, Noyau, Referentiel
from surfaces import (
    AI_CRAWLERS,
    COMPLET,
    CROISEMENT,
    FORBIDDEN_TERMS,
    MINIMAL,
    MIN_CHANTIERS_CROISEMENT,
    ROOT,
    TERRITOIRE,
    build,
    contains_offer_vocabulary,
    for_node,
    generate,
    llms_txt,
    markdown,
    page,
    robots,
    sitemap,
)
from surfaces.render import budget_scope

ROOT_DIR = Path(__file__).resolve().parent.parent
TODAY = date(2026, 8, 16)
BASE = "https://atelier-ferrand.fr"


def core() -> Noyau:
    return Noyau.load(
        ROOT_DIR / "noyaux" / "atelier-ferrand.json",
        Referentiel.load(ROOT_DIR / "referentiels" / "bordeaux.json"),
    )


def extract_jsonld(html: str) -> dict:
    raw = re.search(r'<script type="application/ld\+json">(.*?)</script>', html, re.S)
    payload = raw.group(1).replace("\\u003c", "<").replace("\\u003e", ">").replace("\\u0026", "&")
    return json.loads(payload)


class TestLattice(unittest.TestCase):
    def setUp(self):
        self.core = core()
        self.nodes = build(self.core, TODAY)

    def test_a_company_is_not_a_single_page(self):
        """Une page unique concourt sur tout et perd contre les annuaires."""
        self.assertGreater(len(self.nodes), 1)
        self.assertEqual(sum(1 for n in self.nodes if n.kind == ROOT), 1)

    def test_no_page_without_facts(self):
        for node in self.nodes:
            self.assertTrue(node.has_facts, node.slug)
            if node.kind != ROOT:
                self.assertTrue(node.chantiers, node.slug)

    def test_territoire_pages_respect_the_district_threshold(self):
        for node in self.nodes:
            if node.kind == TERRITOIRE:
                self.assertGreaterEqual(len(node.chantiers), MIN_CHANTIERS_TERRITOIRE)

    def test_crossing_pages_need_a_repeated_pattern(self):
        for node in self.nodes:
            if node.kind == CROISEMENT:
                self.assertGreaterEqual(len(node.chantiers), MIN_CHANTIERS_CROISEMENT)

    def test_a_crossing_never_exists_without_its_district_page(self):
        districts = {n.territoire.code for n in self.nodes if n.kind == TERRITOIRE}
        for node in self.nodes:
            if node.kind == CROISEMENT:
                self.assertIn(node.territoire.code, districts)

    def test_slugs_are_unique(self):
        slugs = [n.slug for n in self.nodes]
        self.assertEqual(len(slugs), len(set(slugs)))

    def test_every_page_answers_a_real_buying_question(self):
        for node in self.nodes:
            self.assertTrue(node.question.endswith("?"), node.slug)

    def test_a_single_chantier_district_gets_no_page(self):
        singles = {
            p.territoire.code
            for p in self.core.territoires(TODAY)
            if p.territoire.level == "quartier" and p.count == 1
        }
        self.assertTrue(singles)
        produced = {n.territoire.code for n in self.nodes if n.territoire}
        self.assertEqual(singles & produced, set())


class TestJsonLd(unittest.TestCase):
    def setUp(self):
        self.core = core()
        self.nodes = build(self.core, TODAY)

    def test_no_offer_vocabulary_anywhere(self):
        """L'interdit central: publier un constat, jamais une proposition."""
        for node in self.nodes:
            found = contains_offer_vocabulary(for_node(self.core, node, TODAY))
            self.assertEqual(found, [], f"{node.slug}: {found}")

    def test_the_detector_actually_detects(self):
        """Un garde-fou qui ne détecte rien ne garde rien."""
        for term in FORBIDDEN_TERMS:
            self.assertTrue(contains_offer_vocabulary({"a": {term: 1}}), term)
        self.assertTrue(contains_offer_vocabulary({"@type": "Offer"}))
        self.assertEqual(contains_offer_vocabulary({"@type": "Service"}), [])

    def test_budget_is_published_as_a_measurement(self):
        node = next(n for n in self.nodes if n.budget is not None)
        document = for_node(self.core, node, TODAY)
        prop = next(
            p for p in document["additionalProperty"]
            if p["name"].startswith("Budget")
        )
        self.assertEqual(prop["value"]["@type"], "QuantitativeValue")
        self.assertIn("measurementTechnique", prop)
        self.assertIn("sans engagement", prop["measurementTechnique"])

    def test_root_document_is_a_business_with_served_areas(self):
        root = next(n for n in self.nodes if n.kind == ROOT)
        document = for_node(self.core, root, TODAY)
        self.assertEqual(document["@type"], "HomeAndConstructionBusiness")
        self.assertTrue(document["areaServed"])
        self.assertEqual(document["identifier"]["propertyID"], "SIREN")

    def test_expired_credential_is_absent_from_structured_data(self):
        root = next(n for n in self.nodes if n.kind == ROOT)
        serialised = json.dumps(for_node(self.core, root, TODAY), ensure_ascii=False)
        self.assertIn("Qualibat 7131", serialised)
        self.assertNotIn("décennale", serialised.lower())

    def test_chantiers_are_dated_and_located(self):
        node = next(n for n in self.nodes if n.kind == CROISEMENT)
        works = for_node(self.core, node, TODAY)["workExample"]
        for work in works:
            self.assertEqual(work["@type"], "CreativeWork")
            self.assertTrue(work["dateCreated"])
            self.assertTrue(work["locationCreated"]["name"])


class TestBudgetScope(unittest.TestCase):
    """Une page de quartier qui liste 3 chantiers et annonce un budget « sur 6 »
    se contredit à l'œil nu. La portée doit être écrite, jamais déduite."""

    def setUp(self):
        self.core = core()
        self.nodes = build(self.core, TODAY)

    def test_scope_is_stated_when_it_differs_from_the_page(self):
        node = next(
            n for n in self.nodes if n.budget is not None and n.kind == CROISEMENT
        )
        total, local = budget_scope(node)
        self.assertGreater(total, local, "la fixture doit exercer ce cas")
        rendered = page(self.core, node, self.nodes, TODAY)
        self.assertIn("tous secteurs confondus", rendered)
        self.assertIn(f"dont {local}", rendered)

    def test_scope_note_reaches_markdown_and_structured_data(self):
        node = next(
            n for n in self.nodes if n.budget is not None and n.kind == CROISEMENT
        )
        self.assertIn("tous secteurs confondus", markdown(self.core, node, TODAY))
        document = for_node(self.core, node, TODAY)
        prop = next(
            p for p in document["additionalProperty"] if p["name"].startswith("Budget")
        )
        self.assertIn("tous secteurs confondus", prop["measurementTechnique"])


class TestRender(unittest.TestCase):
    def setUp(self):
        self.core = core()
        self.nodes = build(self.core, TODAY)
        self.pages = {n.slug: page(self.core, n, self.nodes, TODAY) for n in self.nodes}

    def test_facts_appear_in_visible_text_and_in_structured_data(self):
        """Un fait présent uniquement dans le JSON-LD est deux fois plus faible."""
        node = next(n for n in self.nodes if n.budget is not None)
        rendered = self.pages[node.slug]
        text = re.sub(r"<script.*?</script>", "", rendered, flags=re.S)
        text = re.sub(r"<[^>]+>", " ", text)
        self.assertIn("11 550", text.replace(" ", " ").replace("\xa0", " "))
        self.assertIn("11550", json.dumps(extract_jsonld(rendered)))

    def test_pages_carry_no_script_beyond_structured_data(self):
        for slug, rendered in self.pages.items():
            self.assertEqual(rendered.count("<script"), 1, slug)
            self.assertIn('type="application/ld+json"', rendered)

    def test_pages_load_no_remote_resource(self):
        for slug, rendered in self.pages.items():
            self.assertNotIn("http://", rendered.replace("http://www.sitemaps.org", ""))
            self.assertNotIn("<link", rendered)
            self.assertNotIn("<img", rendered)

    def test_structured_data_cannot_escape_its_block(self):
        rendered = self.pages[next(iter(self.pages))]
        block = re.search(r"<script.*?</script>", rendered, re.S).group(0)
        self.assertEqual(block.count("<script"), 1)
        self.assertNotIn("</script><", block[:-9])

    def test_every_page_states_the_budget_is_not_an_offer(self):
        for node in self.nodes:
            if node.budget is not None:
                self.assertIn("ni d'une offre", self.pages[node.slug])

    def test_pages_are_valid_standalone_documents(self):
        for slug, rendered in self.pages.items():
            self.assertTrue(rendered.startswith("<!doctype html>"), slug)
            self.assertEqual(rendered.count("<title>"), 1, slug)
            self.assertIn('lang="fr"', rendered)
            self.assertIn("</html>", rendered)

    def test_internal_links_point_to_produced_pages(self):
        produced = {n.path for n in self.nodes}
        for slug, rendered in self.pages.items():
            for href in re.findall(r'href="([^"]+)"', rendered):
                self.assertIn(href, produced, f"{slug} pointe vers {href}")


class TestSiteFiles(unittest.TestCase):
    def setUp(self):
        self.core = core()
        self.nodes = build(self.core, TODAY)

    def test_robots_allows_every_ai_crawler_by_default(self):
        text = robots(BASE)
        for name in AI_CRAWLERS:
            self.assertIn(f"User-agent: {name}", text)
        self.assertNotIn("Disallow: /", text)
        self.assertIn(f"Sitemap: {BASE}/sitemap.xml", text)

    def test_a_crawler_can_be_refused_explicitly(self):
        text = robots(BASE, allow={"CCBot": False})
        block = text.split("User-agent: CCBot")[1].splitlines()[1]
        self.assertEqual(block.strip(), "Disallow: /")

    def test_robots_states_what_allowing_a_crawler_implies(self):
        """Autoriser un robot d'entraînement est une décision du client."""
        self.assertIn("entraîner un modèle", robots(BASE))

    def test_sitemap_lastmod_comes_from_the_facts_not_the_clock(self):
        """Un fichier régénéré sans nouveau fait n'est pas une page modifiée."""
        xml = sitemap(BASE, self.nodes, TODAY)
        self.assertNotIn(f"<lastmod>{TODAY.isoformat()}</lastmod>", xml)
        for node in self.nodes:
            self.assertIn(f"<lastmod>{node.latest.isoformat()}</lastmod>", xml)

    def test_sitemap_lists_every_page_once(self):
        xml = sitemap(BASE, self.nodes, TODAY)
        self.assertEqual(xml.count("<url>"), len(self.nodes))

    def test_llms_txt_points_to_markdown_mirrors(self):
        text = llms_txt(self.core, BASE, self.nodes)
        for node in self.nodes:
            self.assertIn(node.path.replace(".html", ".md"), text)
        self.assertIn("ni un tarif, ni une offre", text)

    def test_markdown_mirror_carries_the_same_facts(self):
        node = next(n for n in self.nodes if n.budget is not None)
        text = markdown(self.core, node, TODAY)
        self.assertIn("Budget médian constaté", text)
        self.assertIn("Chantiers", text)
        self.assertNotIn("<", text)


class TestGenerate(unittest.TestCase):
    def test_full_site_is_written_and_self_consistent(self):
        with TemporaryDirectory() as tmp:
            report = generate(core(), BASE, tmp, TODAY)
            directory = Path(tmp)

            for name in ("robots.txt", "sitemap.xml", "llms.txt", "surfaces.json"):
                self.assertTrue((directory / name).exists(), name)

            for detail in report["pages_detail"]:
                html_file = directory / detail["path"]
                markdown_file = directory / detail["path"].replace(".html", ".md")
                self.assertTrue(html_file.exists(), detail["path"])
                self.assertTrue(markdown_file.exists())
                self.assertGreater(html_file.stat().st_size, 500)

            listed = {
                re.sub(rf"^{re.escape(BASE)}/", "", loc)
                for loc in re.findall(r"<loc>([^<]+)</loc>", (directory / "sitemap.xml").read_text())
            }
            self.assertEqual(listed, {d["path"] for d in report["pages_detail"]})

    def test_report_counts_match_the_lattice(self):
        with TemporaryDirectory() as tmp:
            report = generate(core(), BASE, tmp, TODAY)
        self.assertEqual(report["pages"], len(build(core(), TODAY)))
        self.assertEqual(len(report["pages_detail"]), report["pages"])


class TestMultiMetier(unittest.TestCase):
    """Ce module ne doit rien connaître de la rénovation en particulier.

    Régression directe: la première version de ``for_node`` écrivait
    ``"Rénovation d'habitat"`` en dur comme repli pour les pages de
    territoire, ce qui aurait publié un type de service faux pour n'importe
    quel autre métier. Découvert en construisant ce Noyau de plomberie, et
    corrigé ici.
    """

    def plombier(self) -> Noyau:
        return Noyau.load(
            ROOT_DIR / "noyaux" / "aqua-bordeaux.json",
            Referentiel.load(ROOT_DIR / "referentiels" / "bordeaux.json"),
        )

    def test_no_offer_vocabulary_for_a_different_metier(self):
        core = self.plombier()
        for node in build(core, TODAY):
            found = contains_offer_vocabulary(for_node(core, node, TODAY))
            self.assertEqual(found, [], node.slug)

    def test_territoire_service_type_reflects_the_noyau_category_not_renovation(self):
        core = self.plombier()
        territoire_nodes = [n for n in build(core, TODAY) if n.kind == TERRITOIRE]
        self.assertTrue(territoire_nodes)
        for node in territoire_nodes:
            document = for_node(core, node, TODAY)
            self.assertEqual(document["serviceType"], core.category.capitalize())
            self.assertNotIn("Rénovation", document["serviceType"])

    def test_a_full_site_generates_for_a_non_renovation_metier(self):
        with TemporaryDirectory() as tmp:
            report = generate(self.plombier(), "https://aqua-bordeaux.fr", tmp, TODAY)
        self.assertGreater(report["pages"], 0)


class TestMultiZone(unittest.TestCase):
    """Ce module ne doit rien connaître de Bordeaux en particulier.

    Régression directe: cinq endroits de ``surfaces/`` écrivaient « Bordeaux
    Métropole » ou « Bordeaux » en dur comme repli — invisible tant qu'un
    seul référentiel existait, faux dès qu'une seconde ville arrive (la même
    classe de bug que ``TestMultiMetier`` ci-dessus, côté géographie).
    """

    def lyonnais(self) -> Noyau:
        return Noyau.load(
            ROOT_DIR / "noyaux" / "renov-lyon.json",
            Referentiel.load(ROOT_DIR / "referentiels" / "lyon.json"),
        )

    def test_zone_is_lyon_not_bordeaux(self):
        self.assertEqual(self.lyonnais().zone, "Métropole de Lyon")

    def test_no_bordeaux_leaks_into_any_rendered_surface(self):
        lyon_core = self.lyonnais()
        nodes = build(lyon_core, TODAY)
        self.assertTrue(nodes)
        for node in nodes:
            self.assertNotIn("Bordeaux", str(for_node(lyon_core, node, TODAY)))
            self.assertNotIn("Bordeaux", page(lyon_core, node, nodes, TODAY))
            self.assertNotIn("Bordeaux", markdown(lyon_core, node, TODAY))
        self.assertNotIn("Bordeaux", llms_txt(lyon_core, "https://exemple.fr", nodes))

    def test_a_full_site_generates_for_a_different_city(self):
        with TemporaryDirectory() as tmp:
            report = generate(self.lyonnais(), "https://croix-rousse-renovation.fr", tmp, TODAY)
        self.assertGreater(report["pages"], 0)


class TestSansAncrageLocal(unittest.TestCase):
    """Un cabinet de conseil à distance: aucun chantier n'a de territoire.

    Ce n'est pas un cas dégradé du modèle rénovation/plomberie, c'est un
    usage prévu — voir Chantier.territoire et le référentiel minimal
    referentiels/national.json.
    """

    def conseil(self) -> Noyau:
        return Noyau.load(
            ROOT_DIR / "noyaux" / "conseil-remote.json",
            Referentiel.load(ROOT_DIR / "referentiels" / "national.json"),
        )

    def test_zone_comes_from_the_minimal_referentiel(self):
        self.assertEqual(self.conseil().zone, "France")

    def test_only_the_root_page_exists_with_no_territoire_anywhere(self):
        """Pas de page de quartier ni de croisement à produire: il n'y a
        rien à y localiser. Le Noyau reste publiable, juste avec une seule
        page plutôt qu'un treillis."""
        nodes = build(self.conseil(), TODAY)
        self.assertEqual([n.kind for n in nodes], [ROOT])

    def test_the_budget_still_publishes_without_any_territoire(self):
        core = self.conseil()
        published, _ = core.budgets(TODAY)
        self.assertTrue(published)

    def test_no_offer_vocabulary_and_a_full_site_generates(self):
        core = self.conseil()
        for node in build(core, TODAY):
            self.assertEqual(contains_offer_vocabulary(for_node(core, node, TODAY)), [])
        with TemporaryDirectory() as tmp:
            report = generate(core, "https://delta-conseil.fr", tmp, TODAY)
        self.assertGreater(report["pages"], 0)


class TestNoTierLeaksIntoTheRegistry(unittest.TestCase):
    """Le registre est la même source pour toute entreprise vérifiée, quel que
    soit ce qu'elle paie — voir docs/PLAN.md §1. Ce module n'a plus aucune
    notion de palier commercial ou d'exclusivité: ces tests verrouillent
    l'absence, pas la présence conditionnelle d'une mention.

    (L'exclusivité existe toujours, mais uniquement comme allocation interne
    de service dans citation_audit.creneau — jamais câblée jusqu'ici.)
    """

    def test_no_exclusivity_vocabulary_anywhere_in_the_output(self):
        nodes = build(core(), TODAY)
        document = for_node(core(), nodes[0], TODAY)
        self.assertNotIn("exclusi", str(document).lower())

        rendered = page(core(), nodes[0], nodes, TODAY)
        self.assertNotIn("exclusi", rendered.lower())
        self.assertNotIn("créneau", rendered.lower())

        md = markdown(core(), nodes[0], TODAY)
        self.assertNotIn("exclusi", md.lower())

        txt = llms_txt(core(), BASE, nodes)
        self.assertNotIn("exclusi", txt.lower())

    def test_generate_report_has_no_tier_field(self):
        with TemporaryDirectory() as tmp:
            report = generate(core(), BASE, tmp, TODAY)
        self.assertNotIn("exclusive", report)
        self.assertNotIn("tier", report)


class TestMinimalDistribution(unittest.TestCase):
    """La fiche du palier Gratuit (docs/PLAN.md §2-3): identité vérifiable
    automatiquement, publiée pour toute entreprise vérifiée, sans exception.
    Rien qui exige une vérification humaine ne doit y apparaître.
    """

    def test_rejects_an_unknown_distribution_level(self):
        with TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                generate(core(), BASE, tmp, TODAY, distribution="premium")

    def test_produces_a_single_page(self):
        with TemporaryDirectory() as tmp:
            report = generate(core(), BASE, tmp, TODAY, distribution=MINIMAL)
        self.assertEqual(report["pages"], 1)
        self.assertEqual(report["distribution"], MINIMAL)

    def test_identity_is_present(self):
        nodes = build(core(), TODAY)
        document = for_node(core(), nodes[0], TODAY, minimal=True)
        self.assertEqual(document["name"], core().name)
        self.assertIn("identifier", document)

    def test_no_chantier_budget_or_credential_data_appears_anywhere(self):
        """La phrase honnête « aucun chantier n'est publié à ce palier » est
        attendue — ce test défend l'absence de *données* de chantier (une
        table, un montant, un nom de certification), pas l'absence du mot."""
        with TemporaryDirectory() as tmp:
            report = generate(core(), BASE, tmp, TODAY, distribution=MINIMAL)
            html = (Path(tmp) / "index.html").read_text(encoding="utf-8")
            md = (Path(tmp) / "index.md").read_text(encoding="utf-8")
            txt = (Path(tmp) / "llms.txt").read_text(encoding="utf-8")

        for corpus in (html, md, txt):
            self.assertNotIn("<table", corpus.lower())
            self.assertNotIn("budget médian", corpus.lower())
            self.assertNotIn("qualibat", corpus.lower())
            self.assertNotIn("décennale", corpus.lower())
        self.assertEqual(report["pages_detail"][0]["chantiers"], 0)
        self.assertFalse(report["pages_detail"][0]["has_budget"])

    def test_still_carries_no_offer_vocabulary(self):
        document = for_node(core(), build(core(), TODAY)[0], TODAY, minimal=True)
        self.assertEqual(contains_offer_vocabulary(document), [])

    def test_complet_is_the_default_and_unaffected(self):
        """Le comportement historique reste le défaut: aucun appelant existant
        ne doit changer de comportement en oubliant ce paramètre."""
        with TemporaryDirectory() as tmp:
            explicit = generate(core(), BASE, tmp, TODAY, distribution=COMPLET)
        with TemporaryDirectory() as tmp:
            implicit = generate(core(), BASE, tmp, TODAY)
        self.assertEqual(explicit["pages"], implicit["pages"])
        self.assertGreater(explicit["pages"], 1)


if __name__ == "__main__":
    unittest.main()
