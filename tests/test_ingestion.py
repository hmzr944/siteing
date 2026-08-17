"""L'ingestion est la porte par laquelle une donnée fausse pourrait entrer.

Ces tests défendent une seule règle: **le modèle propose des fragments, le code
dispose du vocabulaire.** Et son corollaire: une résolution ambiguë est un refus,
jamais une supposition.
"""

import unittest
from datetime import date
from pathlib import Path

from ingestion import (
    BLOCKING,
    Candidate,
    HeuristicExtractor,
    Span,
    build_candidate,
    parse_date,
    parse_duree,
    parse_montant,
    parse_nature,
    parse_surface,
    resolve_territoire,
    summarise,
    verbatim_only,
)
from noyau import Referentiel

REFERENTIEL = Path(__file__).resolve().parent.parent / "referentiels" / "bordeaux.json"
TODAY = date(2026, 8, 16)

VOCAL = (
    "Ouais j'ai fini la rénovation rue Notre-Dame, y'en a eu pour 12 plaques, "
    "on a mis 4 jours, c'était galère"
)


def referentiel() -> Referentiel:
    return Referentiel.load(REFERENTIEL)


class TestMontant(unittest.TestCase):
    def test_slang_needs_a_money_marker(self):
        """Dans le bâtiment, une plaque est aussi une plaque de plâtre.

        C'est le piège métier: sans marqueur monétaire, « 12 plaques » ne doit
        pas devenir douze mille euros.
        """
        self.assertFalse(parse_montant("j'ai posé 12 plaques ce matin").ok)
        self.assertEqual(parse_montant("y'en a eu pour 12 plaques").value, 12000.0)
        self.assertEqual(parse_montant("ça a coûté 22 plaques").value, 22000.0)

    def test_explicit_euros_need_no_marker(self):
        self.assertEqual(parse_montant("11 400 euros").value, 11400.0)
        self.assertEqual(parse_montant("4500 €").value, 4500.0)

    def test_thousands_separated_by_spaces(self):
        for text, expected in (
            ("facturé 11 400 euros", 11400.0),
            ("devis à 28 500 euros", 28500.0),
            ("un total de 148 000 euros", 148000.0),
        ):
            self.assertEqual(parse_montant(text).value, expected, text)

    def test_a_number_never_leaks_from_the_previous_unit(self):
        """« 90 m2, 34 plaques » ne doit pas produire le nombre « 2, 34 »."""
        resolved = parse_montant("ravalement 90 m2, 34 plaques, facturé")
        self.assertEqual(resolved.value, 34000.0)

    def test_words_in_letters(self):
        self.assertEqual(parse_montant("ça a coûté douze mille").value, 12000.0)

    def test_bare_number_rejected_without_money_context(self):
        self.assertFalse(parse_montant("on était 12 sur le chantier").ok)

    def test_refusal_carries_its_motive(self):
        resolved = parse_montant("j'ai posé 12 plaques")
        self.assertFalse(resolved.ok)
        self.assertIn("ambigu", resolved.note)


class TestOtherResolvers(unittest.TestCase):
    def test_durations(self):
        for text, expected in (
            ("on a mis 4 jours", 4), ("trois semaines", 21), ("un mois", 30),
            ("quinze jours", 15), ("une semaine", 7), ("2 mois", 60),
        ):
            self.assertEqual(parse_duree(text).value, expected, text)

    def test_surfaces(self):
        self.assertEqual(parse_surface("6 m2").value, 6.0)
        self.assertEqual(parse_surface("130 mètres carrés").value, 130.0)
        self.assertFalse(parse_surface("une grande salle de bain").ok)

    def test_relative_dates(self):
        self.assertEqual(parse_date("terminé hier", TODAY).value, date(2026, 8, 15))
        self.assertEqual(parse_date("ce matin", TODAY).value, TODAY)
        self.assertEqual(parse_date("le 12/03/2026", TODAY).value, date(2026, 3, 12))

    def test_absent_date_falls_back_with_low_confidence(self):
        """Le défaut est explicite et peu confiant: on ne sait pas la date."""
        resolved = parse_date("j'ai fini le chantier", TODAY)
        self.assertEqual(resolved.value, TODAY)
        self.assertLess(resolved.confidence, 0.5)
        self.assertIn("aucune date énoncée", resolved.note)

    def test_invalid_date_is_refused(self):
        self.assertFalse(parse_date("le 45/99", TODAY).ok)


class TestNature(unittest.TestCase):
    def test_specific_natures_resolve(self):
        for text, code in (
            ("la salle de bain", "salle-de-bain"),
            ("la cuisine", "cuisine"),
            ("isolation par l'extérieur", "isolation-exterieure"),
            ("un ravalement", "ravalement-pierre"),
            ("une verrière", "verriere"),
            ("rénovation complète", "renovation-globale"),
        ):
            self.assertEqual(parse_nature(text).value, code, text)

    def test_a_vague_term_resolves_nothing(self):
        """« J'ai fini la rénovation » ne dit pas ce qui a été rénové.

        Déduire « salle de bain » d'un budget et d'une durée serait une
        inférence, pas une extraction, et elle finirait publiée comme un fait.
        """
        for text in ("j'ai fini la rénovation", "les travaux sont finis", "le chantier"):
            resolved = parse_nature(text)
            self.assertFalse(resolved.ok, text)
            self.assertIn("trop général", resolved.note)

    def test_two_natures_are_refused_not_arbitrated(self):
        resolved = parse_nature("la salle de bain et la cuisine")
        self.assertFalse(resolved.ok)
        self.assertIn("plusieurs natures", resolved.note)


class TestTerritoire(unittest.TestCase):
    def setUp(self):
        self.ref = referentiel()

    def test_a_street_resolves_to_its_district(self):
        """« rue Notre-Dame » est un quartier pour qui connaît Bordeaux, et rien
        du tout pour un programme: c'est au référentiel de le savoir."""
        self.assertEqual(resolve_territoire("rue Notre-Dame", self.ref).value, "chartrons")
        self.assertEqual(resolve_territoire("quai de Queyries", self.ref).value, "la-bastide")

    def test_unknown_place_is_refused(self):
        resolved = resolve_territoire("rue de la Paix", self.ref)
        self.assertFalse(resolved.ok)
        self.assertIn("aucun secteur connu", resolved.note)


class TestVerbatimGuard(unittest.TestCase):
    def test_a_fragment_absent_from_the_source_is_discarded(self):
        """Le garde-fou qui rend une hallucination inoffensive."""
        kept = verbatim_only(
            "j'ai fini la rénovation rue Rode",
            [
                {"kind": "nature", "text": "salle de bain"},   # inventé
                {"kind": "lieu", "text": "rue Rode"},          # présent
            ],
        )
        self.assertEqual([(s.kind, s.text) for s in kept], [("lieu", "rue Rode")])

    def test_unknown_span_type_is_discarded(self):
        self.assertEqual(verbatim_only("rue Rode", [{"kind": "prix", "text": "rue"}]), [])

    def test_accents_and_case_do_not_matter(self):
        kept = verbatim_only("Rénovation Rue RODE", [{"kind": "lieu", "text": "rue rode"}])
        self.assertEqual(len(kept), 1)


class TestPipeline(unittest.TestCase):
    def setUp(self):
        self.ref = referentiel()
        self.extractor = HeuristicExtractor()

    def _candidate(self, text: str) -> Candidate:
        return build_candidate(
            text, self.extractor.spans(text), "ferrand", self.ref, TODAY
        )

    def test_the_posed_example_resolves_what_it_can_and_asks_for_the_rest(self):
        candidate = self._candidate(VOCAL)
        self.assertEqual(candidate.fields["territoire"], "chartrons")
        self.assertEqual(candidate.fields["budget_eur"], 12000.0)
        self.assertEqual(candidate.fields["duration_days"], 4)
        self.assertNotIn("nature", candidate.fields)
        self.assertFalse(candidate.is_complete)

        question = candidate.next_question(self.ref)
        self.assertEqual(question.field, "nature")
        self.assertTrue(question.blocking)

    def test_a_complete_message_needs_no_question(self):
        candidate = self._candidate(
            "J'ai terminé hier la salle de bain rue Rode, 6 m2, facturé 11 400 euros"
        )
        self.assertTrue(candidate.is_complete)
        self.assertIsNone(candidate.next_question(self.ref))
        chantier = candidate.to_chantier("c-1")
        self.assertEqual(chantier.nature, "salle-de-bain")
        self.assertEqual(chantier.territoire, "chartrons")
        self.assertEqual(chantier.budget_eur, 11400.0)

    def test_only_one_question_is_asked_at_a_time(self):
        """Le produit s'est vendu sur une friction nulle: la boucle de
        confirmation est un budget rare."""
        candidate = self._candidate("J'ai fini un truc hier")
        self.assertGreater(len(candidate.questions(self.ref)), 1)
        self.assertIsNotNone(candidate.next_question(self.ref))

    def test_questions_are_ranked_by_what_they_unlock(self):
        candidate = self._candidate(VOCAL)
        ranks = [q.rank for q in candidate.questions(self.ref)]
        self.assertEqual(ranks, sorted(ranks))
        self.assertTrue(candidate.questions(self.ref)[0].blocking)

    def test_a_voice_candidate_is_never_documented(self):
        """Un chantier raconté n'entre dans aucun budget publié: un budget est
        une donnée engagée, elle ne repose pas sur un souvenir."""
        candidate = self._candidate(
            "J'ai terminé hier la salle de bain rue Rode, 6 m2, facturé 11 400 euros"
        )
        self.assertFalse(candidate.to_chantier("c-1").is_documented)

    def test_incomplete_candidate_refuses_to_become_a_chantier(self):
        candidate = self._candidate(VOCAL)
        with self.assertRaises(ValueError) as caught:
            candidate.to_chantier("c-1")
        self.assertIn("nature", str(caught.exception))

    def test_every_field_keeps_its_evidence_and_confidence(self):
        candidate = self._candidate(VOCAL)
        for field in candidate.fields:
            self.assertIn(field, candidate.evidence, field)
            self.assertIn(field, candidate.confidence, field)
        self.assertIn("source_text", candidate.to_dict())

    def test_refusals_are_recorded_with_their_motive(self):
        candidate = self._candidate("J'ai posé 12 plaques sur le chantier de Caudéran")
        self.assertIn("budget_eur", candidate.refusals)
        self.assertIn("ambigu", candidate.refusals["budget_eur"])
        self.assertNotIn("budget_eur", candidate.fields)

    def test_summary_is_readable_by_the_owner(self):
        candidate = self._candidate(
            "J'ai terminé la cuisine place Nansouty, 14 m2, ça a coûté 22 plaques"
        )
        summary = summarise(candidate, self.ref)
        self.assertIn("cuisine", summary.lower())
        self.assertIn("Nansouty", summary)
        self.assertIn("22 000", summary)

    def test_blocking_fields_are_exactly_what_the_noyau_requires(self):
        self.assertEqual(set(BLOCKING), {"nature", "territoire", "budget_eur"})


if __name__ == "__main__":
    unittest.main()
