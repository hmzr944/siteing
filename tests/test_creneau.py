"""Une exclusivité promise et tenue dans un tableur finit vendue deux fois.
Le registre doit refuser, jamais avertir."""

import unittest
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory

from citation_audit.creneau import (
    EXCLUSIF,
    MAX_SHARED_HOLDERS,
    POSITION,
    SOCLE,
    Grant,
    Registry,
    SlotConflict,
)

TODAY = date(2026, 8, 8)
START = date(2026, 1, 1)
END = date(2027, 1, 1)


class TestGrant(unittest.TestCase):
    def test_slot_key_ignores_case_accents_and_spacing(self):
        a = Grant("Plombier", "Bordeaux Métropole", "a", SOCLE, START, END)
        b = Grant("plombier", "bordeaux metropole", "b", SOCLE, START, END)
        self.assertEqual(a.slot_key, b.slot_key)

    def test_only_the_top_tier_is_exclusive(self):
        self.assertTrue(Grant("c", "z", "e", EXCLUSIF, START, END).is_exclusive)
        self.assertFalse(Grant("c", "z", "e", POSITION, START, END).is_exclusive)
        self.assertFalse(Grant("c", "z", "e", SOCLE, START, END).is_exclusive)

    def test_expiry_must_follow_the_grant(self):
        with self.assertRaises(ValueError):
            Grant.from_dict(
                {
                    "category": "c",
                    "zone": "z",
                    "entity_id": "e",
                    "tier": SOCLE,
                    "granted_on": "2026-01-01",
                    "expires_on": "2026-01-01",
                }
            )

    def test_unknown_tier_is_rejected(self):
        with self.assertRaises(ValueError):
            Registry(grants=[]).grant("c", "z", "e", "premium", START, END, TODAY)


class TestExclusivity(unittest.TestCase):
    def setUp(self):
        self.registry = Registry(grants=[])

    def test_exclusive_grant_blocks_every_other_entity(self):
        self.registry.grant("plombier", "Bordeaux", "vasseur", EXCLUSIF, START, END, TODAY)
        with self.assertRaises(SlotConflict) as caught:
            self.registry.grant("plombier", "Bordeaux", "rival", SOCLE, START, END, TODAY)
        self.assertIn("vasseur", str(caught.exception))

    def test_exclusivity_refused_when_the_slot_is_already_shared(self):
        self.registry.grant("plombier", "Bordeaux", "a", SOCLE, START, END, TODAY)
        with self.assertRaises(SlotConflict):
            self.registry.grant("plombier", "Bordeaux", "b", EXCLUSIF, START, END, TODAY)

    def test_shared_slot_saturates_at_the_cap(self):
        for index in range(MAX_SHARED_HOLDERS):
            self.registry.grant("plombier", "Bordeaux", f"e{index}", SOCLE, START, END, TODAY)
        with self.assertRaises(SlotConflict) as caught:
            self.registry.grant("plombier", "Bordeaux", "trop", SOCLE, START, END, TODAY)
        self.assertIn("saturé", str(caught.exception))

    def test_same_entity_cannot_hold_the_slot_twice(self):
        self.registry.grant("plombier", "Bordeaux", "vasseur", SOCLE, START, END, TODAY)
        with self.assertRaises(SlotConflict):
            self.registry.grant("plombier", "Bordeaux", "vasseur", POSITION, START, END, TODAY)

    def test_different_zones_do_not_collide(self):
        self.registry.grant("plombier", "Bordeaux", "vasseur", EXCLUSIF, START, END, TODAY)
        self.registry.grant("plombier", "Toulouse", "autre", EXCLUSIF, START, END, TODAY)
        self.assertEqual(len(self.registry.active(TODAY)), 2)

    def test_different_categories_do_not_collide(self):
        self.registry.grant("plombier", "Bordeaux", "vasseur", EXCLUSIF, START, END, TODAY)
        self.registry.grant("couvreur", "Bordeaux", "autre", EXCLUSIF, START, END, TODAY)
        self.assertEqual(len(self.registry.active(TODAY)), 2)

    def test_expired_grant_frees_the_slot(self):
        self.registry.grant(
            "plombier", "Bordeaux", "ancien", EXCLUSIF, date(2024, 1, 1), date(2025, 1, 1),
            today=date(2024, 6, 1),
        )
        self.assertTrue(self.registry.is_available("plombier", "Bordeaux", EXCLUSIF, TODAY))
        self.registry.grant("plombier", "Bordeaux", "nouveau", EXCLUSIF, START, END, TODAY)
        holder = self.registry.exclusive_holder("plombier", "Bordeaux", TODAY)
        self.assertEqual(holder.entity_id, "nouveau")

    def test_availability_matches_what_grant_would_do(self):
        self.assertTrue(self.registry.is_available("plombier", "Bordeaux", EXCLUSIF, TODAY))
        self.registry.grant("plombier", "Bordeaux", "vasseur", EXCLUSIF, START, END, TODAY)
        self.assertFalse(self.registry.is_available("plombier", "Bordeaux", SOCLE, TODAY))


class TestRelease(unittest.TestCase):
    def test_release_shortens_the_grant_and_keeps_the_trace(self):
        registry = Registry(grants=[])
        registry.grant("plombier", "Bordeaux", "vasseur", EXCLUSIF, START, END, TODAY)
        released = registry.release("plombier", "Bordeaux", "vasseur", TODAY)
        self.assertEqual(released, 1)
        self.assertEqual(len(registry.grants), 1, "l'historique n'est pas supprimé")
        self.assertEqual(registry.grants[0].expires_on, TODAY)

    def test_released_slot_becomes_grantable_the_next_day(self):
        registry = Registry(grants=[])
        registry.grant("plombier", "Bordeaux", "vasseur", EXCLUSIF, START, END, TODAY)
        registry.release("plombier", "Bordeaux", "vasseur", TODAY)
        later = date(2026, 8, 9)
        registry.grant("plombier", "Bordeaux", "suivant", EXCLUSIF, later, END, later)
        self.assertEqual(
            registry.exclusive_holder("plombier", "Bordeaux", later).entity_id, "suivant"
        )


class TestPersistence(unittest.TestCase):
    def test_round_trip_preserves_grants(self):
        registry = Registry(grants=[])
        registry.grant("plombier", "Bordeaux", "vasseur", EXCLUSIF, START, END, TODAY)
        registry.grant("couvreur", "Bordeaux", "autre", SOCLE, START, END, TODAY)
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "nested" / "registre.json"
            registry.save(path)
            reloaded = Registry.load(path)
        self.assertEqual(
            [g.to_dict() for g in registry.grants], [g.to_dict() for g in reloaded.grants]
        )

    def test_loading_a_missing_file_yields_an_empty_registry(self):
        with TemporaryDirectory() as tmp:
            self.assertEqual(Registry.load(Path(tmp) / "absent.json").grants, [])

    def test_conflicts_survive_a_round_trip(self):
        registry = Registry(grants=[])
        registry.grant("plombier", "Bordeaux", "vasseur", EXCLUSIF, START, END, TODAY)
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "registre.json"
            registry.save(path)
            reloaded = Registry.load(path)
        with self.assertRaises(SlotConflict):
            reloaded.grant("plombier", "Bordeaux", "rival", SOCLE, START, END, TODAY)


if __name__ == "__main__":
    unittest.main()
