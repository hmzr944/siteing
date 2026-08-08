"""La couche machine ne doit jamais publier comme un fait ce qui n'a pas été
contrôlé. C'est l'invariant unique de ce module."""

import json
import unittest
from datetime import date, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

from citation_audit.creneau import EXCLUSIF, Registry
from citation_audit.dossier import VERIFIED, Dossier
from citation_audit.publish import (
    PROTOCOL,
    to_feed_line,
    to_jsonld,
    to_manifest,
    write_bundle,
)

FIXTURE = Path(__file__).resolve().parent.parent / "dossiers" / "vasseur.json"
TODAY = date(2026, 8, 8)


class TestJsonLd(unittest.TestCase):
    def setUp(self):
        self.dossier = Dossier.load(FIXTURE)
        self.document = to_jsonld(self.dossier, TODAY)
        self.serialised = json.dumps(self.document, ensure_ascii=False)

    def test_is_valid_schema_org_envelope(self):
        self.assertEqual(self.document["@context"], "https://schema.org")
        self.assertEqual(self.document["@type"], "LocalBusiness")
        self.assertEqual(self.document["name"], self.dossier.name)

    def test_no_unverified_value_appears_anywhere(self):
        """L'invariant du produit. Un seul déclaratif publié le casse."""
        for claim in self.dossier.stale(TODAY):
            self.assertNotIn(
                claim.value,
                self.serialised,
                f"'{claim.label}' n'est pas vérifié et fuit dans le JSON-LD",
            )

    def test_every_verified_claim_is_represented(self):
        for claim in self.dossier.publishable(TODAY):
            self.assertIn(claim.machine_value, self.serialised, claim.label)

    def test_typed_properties_use_the_machine_value_not_the_prose(self):
        """`foundingDate` attend une date, pas une phrase lisible."""
        self.assertEqual(self.document["foundingDate"], "2009-03")
        self.assertEqual(self.document["numberOfEmployees"], "4")

    def test_unmapped_claims_become_typed_additional_properties(self):
        extras = self.document["additionalProperty"]
        self.assertTrue(extras)
        for extra in extras:
            self.assertEqual(extra["@type"], "PropertyValue")
            self.assertTrue(extra["name"])
            self.assertTrue(extra["valueReference"]["value"], "date de contrôle manquante")

    def test_expiry_removes_a_claim_from_the_published_document(self):
        later = max(c.valid_until for c in self.dossier.publishable(TODAY)) + timedelta(days=1)
        document = json.dumps(to_jsonld(self.dossier, later), ensure_ascii=False)
        self.assertNotIn("additionalProperty", document)
        self.assertNotIn("foundingDate", document)


class TestManifest(unittest.TestCase):
    def setUp(self):
        self.dossier = Dossier.load(FIXTURE)
        self.manifest = to_manifest(self.dossier, today=TODAY)

    def test_declares_its_protocol_and_a_notice(self):
        self.assertEqual(self.manifest["protocol"], PROTOCOL)
        self.assertIn("verifie", self.manifest["notice"])

    def test_lists_every_claim_with_its_status(self):
        """Un agent doit savoir ce qui n'est pas vérifié: le lui cacher serait
        la seule vraie faute de ce format."""
        self.assertEqual(len(self.manifest["claims"]), len(self.dossier.claims))
        statuses = {c["status"] for c in self.manifest["claims"]}
        self.assertGreater(len(statuses), 1, "le manifeste doit exposer la nuance")

    def test_counts_agree_with_the_dossier(self):
        counts = self.dossier.counts(TODAY)
        self.assertEqual(self.manifest["verification"]["verified"], counts[VERIFIED])
        self.assertEqual(
            self.manifest["verification"]["verified_ratio"],
            round(self.dossier.verified_ratio(TODAY), 4),
        )

    def test_claims_are_deterministically_ordered(self):
        again = to_manifest(self.dossier, today=TODAY)
        self.assertEqual(
            [c["key"] for c in self.manifest["claims"]],
            [c["key"] for c in again["claims"]],
        )

    def test_slots_included_only_when_a_registry_is_supplied(self):
        self.assertNotIn("slots", self.manifest)
        registry = Registry(grants=[])
        registry.grant(
            "plombier", "Bordeaux", "vasseur", EXCLUSIF,
            date(2026, 1, 1), date(2027, 1, 1), today=TODAY,
        )
        with_slots = to_manifest(self.dossier, registry, today=TODAY)
        self.assertEqual(len(with_slots["slots"]), 1)
        self.assertTrue(with_slots["slots"][0]["exclusive"])

    def test_dossier_url_is_optional(self):
        self.assertNotIn("dossier_url", self.manifest)
        located = to_manifest(self.dossier, dossier_url="https://x.fr/verite", today=TODAY)
        self.assertEqual(located["dossier_url"], "https://x.fr/verite")


class TestFeedAndBundle(unittest.TestCase):
    def setUp(self):
        self.dossier = Dossier.load(FIXTURE)

    def test_feed_line_is_single_line_json_with_verified_only(self):
        line = to_feed_line(self.dossier, TODAY)
        self.assertNotIn("\n", line)
        payload = json.loads(line)
        self.assertEqual(
            set(payload["verified_claims"]),
            {c.key for c in self.dossier.publishable(TODAY)},
        )

    def test_bundle_writes_every_output(self):
        with TemporaryDirectory() as tmp:
            written = write_bundle(tmp, self.dossier, today=TODAY)
            self.assertEqual(
                set(written),
                {
                    "vasseur.jsonld",
                    "vasseur.manifest.json",
                    "vasseur.jsonl",
                    "vasseur.html",
                },
            )
            for path in written.values():
                self.assertGreater(Path(path).stat().st_size, 0)

    def test_bundle_html_is_a_standalone_document(self):
        with TemporaryDirectory() as tmp:
            written = write_bundle(tmp, self.dossier, today=TODAY)
            page = Path(written["vasseur.html"]).read_text(encoding="utf-8")
            self.assertTrue(page.startswith("<!doctype html>"))
            self.assertIn('<html lang="fr">', page)
            self.assertIn('<meta charset="utf-8">', page)
            self.assertEqual(page.count("<title>"), 1)
            self.assertEqual(page.count("<body>"), 1)


if __name__ == "__main__":
    unittest.main()
