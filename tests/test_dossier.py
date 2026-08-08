"""Le Dossier de Vérité vend une frontière: vérifié d'un côté, déclaré de
l'autre. Si cette frontière fuit une seule fois, le produit ne vaut plus rien."""

import json
import unittest
from datetime import date, timedelta
from pathlib import Path

from citation_audit.dossier import (
    DECLARED,
    DEFAULT_VALIDITY_DAYS,
    EXPIRED,
    REFUTED,
    VERIFIED,
    Claim,
    Dossier,
    Evidence,
)

FIXTURE = Path(__file__).resolve().parent.parent / "dossiers" / "vasseur.json"
TODAY = date(2026, 8, 8)


def evidence(kind="facture", reference="F-1"):
    return Evidence(
        kind=kind, reference=reference, issued_on=date(2026, 1, 1), checked_by="Tiers"
    )


def claim(**kwargs):
    base = dict(key="k", label="Label", value="Valeur", cluster="capacite")
    base.update(kwargs)
    return Claim(**base)


class TestClaimStatus(unittest.TestCase):
    def test_no_evidence_is_declared(self):
        self.assertEqual(claim().status(TODAY), DECLARED)

    def test_evidence_without_verification_date_stays_declared(self):
        """Une pièce reçue n'est pas une pièce contrôlée."""
        self.assertEqual(claim(evidence=[evidence()]).status(TODAY), DECLARED)

    def test_verified_within_validity(self):
        subject = claim(
            evidence=[evidence()],
            verified_on=date(2026, 6, 1),
            valid_until=date(2027, 6, 1),
        )
        self.assertEqual(subject.status(TODAY), VERIFIED)
        self.assertTrue(subject.is_publishable(TODAY))

    def test_expires_the_day_after_validity_ends(self):
        subject = claim(
            evidence=[evidence()], verified_on=date(2025, 8, 8), valid_until=TODAY
        )
        self.assertEqual(subject.status(TODAY), VERIFIED, "le dernier jour reste valable")
        self.assertEqual(subject.status(TODAY + timedelta(days=1)), EXPIRED)

    def test_expired_claim_is_not_publishable(self):
        subject = claim(
            evidence=[evidence()],
            verified_on=date(2024, 1, 1),
            valid_until=date(2025, 1, 1),
        )
        self.assertEqual(subject.status(TODAY), EXPIRED)
        self.assertFalse(subject.is_publishable(TODAY))

    def test_refuted_overrides_a_valid_verification(self):
        subject = claim(
            evidence=[evidence()],
            verified_on=date(2026, 6, 1),
            valid_until=date(2027, 6, 1),
            refuted=True,
        )
        self.assertEqual(subject.status(TODAY), REFUTED)
        self.assertFalse(subject.is_publishable(TODAY))

    def test_machine_value_falls_back_to_the_human_value(self):
        self.assertEqual(claim(value="4 salariés").machine_value, "4 salariés")
        self.assertEqual(claim(value="4 salariés", schema_value="4").machine_value, "4")

    def test_default_validity_applied_when_absent(self):
        subject = Claim.from_dict(
            {
                "key": "k",
                "label": "L",
                "value": "V",
                "cluster": "capacite",
                "verified_on": "2026-01-01",
                "evidence": [
                    {
                        "kind": "facture",
                        "reference": "F",
                        "issued_on": "2026-01-01",
                        "checked_by": "T",
                    }
                ],
            }
        )
        self.assertEqual(
            subject.valid_until, date(2026, 1, 1) + timedelta(days=DEFAULT_VALIDITY_DAYS)
        )

    def test_unknown_cluster_and_evidence_kind_are_rejected(self):
        with self.assertRaises(ValueError):
            Claim.from_dict({"key": "k", "label": "L", "value": "V", "cluster": "inconnu"})
        with self.assertRaises(ValueError):
            Evidence.from_dict(
                {
                    "kind": "rumeur",
                    "reference": "R",
                    "issued_on": "2026-01-01",
                    "checked_by": "T",
                }
            )


class TestDossier(unittest.TestCase):
    def setUp(self):
        self.dossier = Dossier.load(FIXTURE)

    def test_fixture_mixes_statuses_on_purpose(self):
        """Un dossier vérifié à 100 % en démonstration serait un mensonge utile."""
        counts = self.dossier.counts(TODAY)
        self.assertGreater(counts[VERIFIED], 0)
        self.assertGreater(counts[DECLARED], 0)
        self.assertGreater(counts[EXPIRED], 0)
        self.assertLess(self.dossier.verified_ratio(TODAY), 1.0)

    def test_duplicate_claim_keys_are_rejected(self):
        raw = json.loads(FIXTURE.read_text(encoding="utf-8"))
        raw["claims"].append(dict(raw["claims"][0]))
        with self.assertRaises(ValueError):
            Dossier.from_dict(raw)

    def test_clusters_put_verified_claims_first(self):
        for _key, _label, claims in self.dossier.by_cluster(TODAY):
            statuses = [c.status(TODAY) for c in claims]
            verified_positions = [i for i, s in enumerate(statuses) if s == VERIFIED]
            other_positions = [i for i, s in enumerate(statuses) if s != VERIFIED]
            if verified_positions and other_positions:
                self.assertLess(max(verified_positions), min(other_positions))

    def test_stale_and_publishable_partition_the_dossier(self):
        publishable = self.dossier.publishable(TODAY)
        stale = self.dossier.stale(TODAY)
        self.assertEqual(len(publishable) + len(stale), len(self.dossier.claims))
        self.assertEqual(set(c.key for c in publishable) & set(c.key for c in stale), set())

    def test_expiring_soon_is_a_subset_of_publishable_and_sorted(self):
        soon = self.dossier.expiring_soon(60, TODAY)
        publishable_keys = {c.key for c in self.dossier.publishable(TODAY)}
        self.assertTrue(all(c.key in publishable_keys for c in soon))
        self.assertEqual(
            [c.valid_until for c in soon], sorted(c.valid_until for c in soon)
        )

    def test_expiring_soon_excludes_already_expired(self):
        soon = self.dossier.expiring_soon(60, TODAY)
        self.assertTrue(all(c.days_until_expiry(TODAY) >= 0 for c in soon))

    def test_last_verified_only_counts_still_valid_controls(self):
        last = self.dossier.last_verified_on(TODAY)
        self.assertIsNotNone(last)
        expired = [c for c in self.dossier.claims if c.status(TODAY) == EXPIRED]
        self.assertTrue(expired, "la fixture doit contenir un contrôle expiré")
        self.assertNotIn(last, [c.verified_on for c in expired])

    def test_ratio_is_zero_for_an_empty_dossier(self):
        empty = Dossier(
            entity_id="x", name="X", category="c", zone="z", claims=[]
        )
        self.assertEqual(empty.verified_ratio(TODAY), 0.0)
        self.assertEqual(empty.publishable(TODAY), [])


if __name__ == "__main__":
    unittest.main()
