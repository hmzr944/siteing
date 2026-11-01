"""L'instrument de validation terrain: seuils verrouillés, niveaux de preuve,
décision. Le risque que ces tests couvrent n'est pas un bug de calcul, c'est un
protocole qui se déplace en cours de route sans que personne ne le voie.
"""

import unittest
from dataclasses import replace
from datetime import date

from terrain.decision import (
    ABANDONNER,
    ECHANTILLON_INSUFFISANT,
    EXPLORER_ACTION,
    EXPLORER_REPRESENTATION,
    TESTER_ENSEMBLE,
    decide,
)
from terrain.entretien import (
    ConstatH1,
    Entretien,
    EntretienH1,
    EntretienH2,
    EvenementsH2,
)
from terrain.seuils import PROTOCOLE_V2, Protocole

J0 = date(2026, 8, 18)


class TestProtocole(unittest.TestCase):
    def test_hash_is_deterministic(self):
        self.assertEqual(PROTOCOLE_V2.hash(), PROTOCOLE_V2.hash())

    def test_hash_is_stable_across_instances(self):
        """Deux instances aux mêmes valeurs doivent porter le même hash: c'est
        ce qui permet à un entretien sérialisé de rester comparable après un
        redémarrage du process."""
        rebuilt = Protocole(version="v2", vertical="renovation", zone="bordeaux-metropole")
        self.assertEqual(rebuilt.hash(), PROTOCOLE_V2.hash())

    def test_changing_a_threshold_changes_the_hash(self):
        """Sans ça, un seuil modifié en cours de campagne s'agrégerait
        silencieusement avec les entretiens menés sous l'ancien seuil."""
        moved = replace(PROTOCOLE_V2, h1_niveau3_min=2)
        self.assertNotEqual(moved.hash(), PROTOCOLE_V2.hash())

    def test_changing_the_version_changes_the_hash(self):
        renamed = replace(PROTOCOLE_V2, version="v3")
        self.assertNotEqual(renamed.hash(), PROTOCOLE_V2.hash())


class TestEvenementsH2Coherence(unittest.TestCase):
    def test_responded_plus_unanswered_cannot_exceed_received(self):
        with self.assertRaises(ValueError):
            EvenementsH2(
                periode_jours=7, recues=5, repondues_moins_5min=3,
                repondues_5_60min=2, repondues_plus_1h=1, sans_reponse=1,
                necessitant_devis=3, qualifiees=2,
            )

    def test_exact_totals_are_accepted(self):
        events = EvenementsH2(
            periode_jours=7, recues=10, repondues_moins_5min=3,
            repondues_5_60min=3, repondues_plus_1h=2, sans_reponse=2,
            necessitant_devis=6, qualifiees=5,
        )
        self.assertAlmostEqual(events.taux_sans_reponse, 0.2)
        self.assertAlmostEqual(events.taux_reponse_lente_ou_absente, 0.4)

    def test_zero_received_does_not_divide_by_zero(self):
        events = EvenementsH2(
            periode_jours=7, recues=0, repondues_moins_5min=0,
            repondues_5_60min=0, repondues_plus_1h=0, sans_reponse=0,
            necessitant_devis=0, qualifiees=0,
        )
        self.assertEqual(events.taux_sans_reponse, 0.0)
        self.assertEqual(events.taux_reponse_lente_ou_absente, 0.0)


class TestConstatH1(unittest.TestCase):
    def test_unknown_source_is_refused(self):
        with self.assertRaises(ValueError):
            ConstatH1("un fait", source="intuition", juge_important=True)


class TestNiveauxH1(unittest.TestCase):
    def test_no_constat_is_niveau1_false(self):
        h1 = EntretienH1()
        self.assertFalse(h1.niveau1)
        self.assertFalse(h1.niveau2)
        self.assertFalse(h1.niveau3)

    def test_one_constat_is_niveau1_only(self):
        h1 = EntretienH1(constats=[ConstatH1("absent du panier", "citation_audit", False)])
        self.assertTrue(h1.niveau1)
        self.assertFalse(h1.niveau2)

    def test_an_important_constat_reaches_niveau2(self):
        h1 = EntretienH1(constats=[ConstatH1("absent du panier", "citation_audit", True)])
        self.assertTrue(h1.niveau1)
        self.assertTrue(h1.niveau2)
        self.assertFalse(h1.niveau3)

    def test_only_a_realised_action_reaches_niveau3(self):
        """Un « oui » à l'oral ne suffit pas: seul un engagement daté compte,
        parce que c'est l'engagement révélé qui protège contre la lecture
        complaisante de dix conversations sympathiques."""
        h1 = EntretienH1(
            constats=[ConstatH1("absent du panier", "citation_audit", True)],
            action_engagee="dossier proposé",
        )
        self.assertFalse(h1.niveau3)
        h1.action_realisee_le = J0
        self.assertTrue(h1.niveau3)


class TestNiveauxH2(unittest.TestCase):
    def test_a_low_delay_rate_is_not_niveau1(self):
        events = EvenementsH2(
            periode_jours=7, recues=10, repondues_moins_5min=8,
            repondues_5_60min=1, repondues_plus_1h=1, sans_reponse=0,
            necessitant_devis=5, qualifiees=4,
        )
        h2 = EntretienH2(evenements=events)
        self.assertFalse(h2.niveau1)

    def test_a_significant_delay_rate_is_niveau1(self):
        events = EvenementsH2(
            periode_jours=7, recues=10, repondues_moins_5min=2,
            repondues_5_60min=2, repondues_plus_1h=3, sans_reponse=3,
            necessitant_devis=6, qualifiees=5,
        )
        h2 = EntretienH2(evenements=events)
        self.assertTrue(h2.niveau1)
        self.assertFalse(h2.niveau2)

    def test_a_named_repeating_pattern_reaches_niveau2(self):
        h2 = EntretienH2(type_repetitif_identifie="demandes du dimanche soir jamais rappelées")
        self.assertTrue(h2.niveau1)
        self.assertTrue(h2.niveau2)

    def test_only_a_realised_action_reaches_niveau3(self):
        h2 = EntretienH2(type_repetitif_identifie="demandes du dimanche soir")
        self.assertFalse(h2.niveau3)
        h2.action_realisee_le = J0
        self.assertTrue(h2.niveau3)


class TestEntretienPersistence(unittest.TestCase):
    def test_nouveau_stamps_the_current_protocol_hash(self):
        e = Entretien.nouveau("ferrand", "Atelier Ferrand", J0)
        self.assertEqual(e.protocole_hash, PROTOCOLE_V2.hash())

    def test_round_trip_preserves_everything(self):
        e = Entretien.nouveau("ferrand", "Atelier Ferrand", J0, notes="test")
        e.h1 = EntretienH1(
            constats=[ConstatH1("absent", "citation_audit", True)],
            presence_rate=0.1,
            action_realisee_le=J0,
        )
        e.h2 = EntretienH2(
            type_repetitif_identifie="devis du week-end",
            action_realisee_le=J0,
        )
        restored = Entretien.from_dict(e.to_dict())
        self.assertEqual(restored, e)
        self.assertTrue(restored.h1.niveau3)
        self.assertTrue(restored.h2.niveau3)


def _entretien(entreprise_id: str, h1_niveau: int, h2_niveau: int) -> Entretien:
    """Fabrique un entretien où H1 et H2 culminent chacun au niveau demandé
    (0 = rien, 1, 2, ou 3), pour construire des lots de test lisibles."""
    e = Entretien.nouveau(entreprise_id, entreprise_id, J0)
    if h1_niveau >= 1:
        e.h1.constats.append(ConstatH1("absent du panier", "citation_audit", h1_niveau >= 2))
    if h1_niveau >= 3:
        e.h1.action_realisee_le = J0
    if h2_niveau >= 1:
        e.h2.evenements = EvenementsH2(
            periode_jours=7, recues=10, repondues_moins_5min=2,
            repondues_5_60min=2, repondues_plus_1h=3, sans_reponse=3,
            necessitant_devis=6, qualifiees=5,
        )
    if h2_niveau >= 2:
        e.h2.type_repetitif_identifie = "devis du week-end jamais rappelés"
    if h2_niveau >= 3:
        e.h2.action_realisee_le = J0
    return e


class TestDecide(unittest.TestCase):
    def test_refuses_to_aggregate_across_protocol_versions(self):
        good = _entretien("a", 3, 3)
        stale = _entretien("b", 3, 3)
        stale.protocole_hash = "0" * 12
        with self.assertRaises(ValueError):
            decide([good, stale])

    def test_incomplete_sample_is_flagged_before_any_verdict(self):
        entretiens = [_entretien(str(i), 3, 3) for i in range(PROTOCOLE_V2.n_entreprises - 1)]
        verdict = decide(entretiens)
        self.assertEqual(verdict.matrice, ECHANTILLON_INSUFFISANT)
        self.assertTrue(any("incomplet" in w for w in verdict.warnings))

    def test_both_hypotheses_confirmed(self):
        """6 en niveau1, 5 en niveau2 (sous-ensemble), 3 en niveau3
        (sous-ensemble des 5), pour chaque hypothèse: exactement au seuil."""
        entretiens = (
            [_entretien(f"h1h2-{i}", 3, 3) for i in range(3)]
            + [_entretien(f"h1h2b-{i}", 2, 2) for i in range(2)]
            + [_entretien(f"h1h2c-{i}", 1, 1) for i in range(1)]
            + [_entretien(f"rien-{i}", 0, 0) for i in range(4)]
        )
        self.assertEqual(len(entretiens), 10)
        verdict = decide(entretiens)
        self.assertTrue(verdict.h1_go)
        self.assertTrue(verdict.h2_go)
        self.assertEqual(verdict.matrice, TESTER_ENSEMBLE)

    def test_h1_only_confirmed(self):
        entretiens = (
            [_entretien(f"h1-{i}", 3, 0) for i in range(3)]
            + [_entretien(f"h1b-{i}", 2, 0) for i in range(2)]
            + [_entretien(f"h1c-{i}", 1, 0) for i in range(1)]
            + [_entretien(f"rien-{i}", 0, 0) for i in range(4)]
        )
        verdict = decide(entretiens)
        self.assertTrue(verdict.h1_go)
        self.assertFalse(verdict.h2_go)
        self.assertEqual(verdict.matrice, EXPLORER_REPRESENTATION)

    def test_h2_only_confirmed(self):
        entretiens = (
            [_entretien(f"h2-{i}", 0, 3) for i in range(3)]
            + [_entretien(f"h2b-{i}", 0, 2) for i in range(2)]
            + [_entretien(f"h2c-{i}", 0, 1) for i in range(1)]
            + [_entretien(f"rien-{i}", 0, 0) for i in range(4)]
        )
        verdict = decide(entretiens)
        self.assertFalse(verdict.h1_go)
        self.assertTrue(verdict.h2_go)
        self.assertEqual(verdict.matrice, EXPLORER_ACTION)

    def test_neither_confirmed(self):
        entretiens = [_entretien(f"rien-{i}", 0, 0) for i in range(10)]
        verdict = decide(entretiens)
        self.assertFalse(verdict.h1_go)
        self.assertFalse(verdict.h2_go)
        self.assertEqual(verdict.matrice, ABANDONNER)

    def test_a_count_exactly_at_the_threshold_is_flagged_as_grey_zone(self):
        entretiens = (
            [_entretien(f"h1h2-{i}", 3, 3) for i in range(3)]
            + [_entretien(f"h1h2b-{i}", 2, 2) for i in range(2)]
            + [_entretien(f"h1h2c-{i}", 1, 1) for i in range(1)]
            + [_entretien(f"rien-{i}", 0, 0) for i in range(4)]
        )
        verdict = decide(entretiens)
        self.assertTrue(any("H1 niveau 3" in w and "zone grise" in w for w in verdict.warnings))
        self.assertTrue(any("H2 niveau 3" in w and "zone grise" in w for w in verdict.warnings))

    def test_a_count_comfortably_past_threshold_is_not_flagged(self):
        entretiens = [_entretien(f"tous-{i}", 3, 3) for i in range(10)]
        verdict = decide(entretiens)
        self.assertEqual(verdict.matrice, TESTER_ENSEMBLE)
        self.assertFalse(any("zone grise" in w for w in verdict.warnings))


if __name__ == "__main__":
    unittest.main()
