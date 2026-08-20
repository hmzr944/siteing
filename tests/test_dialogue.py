"""La boucle de dialogue: routage, état, désambiguïsation, et rien de perdu.

Le routage est la partie fragile: un message mal classé fusionne deux chantiers
ou en fabrique un fantôme. Ces tests couvrent les quatre confusions possibles.
"""

import unittest
from datetime import date, timedelta
from pathlib import Path

from ingestion import (
    ASK,
    PENDING_TTL_DAYS,
    PIECE_RECEIVED,
    REGISTERED,
    UNCLEAR,
    Conversation,
    Dialogue,
    find_piece_reference,
    looks_like_new_event,
    parse_montant,
    resolve_field,
)
from ingestion.dialogue import PIECE_REQUEST, resolved_field_count
from noyau import Referentiel

REFERENTIEL = Path(__file__).resolve().parent.parent / "referentiels" / "bordeaux.json"
TODAY = date(2026, 8, 16)

VOCAL = (
    "Ouais j'ai fini la rénovation rue Notre-Dame, y'en a eu pour 12 plaques, "
    "on a mis 4 jours, c'était galère"
)


def referentiel() -> Referentiel:
    return Referentiel.load(REFERENTIEL)


def dialogue() -> Dialogue:
    return Dialogue(referentiel(), entity_id="ferrand")


class TestContextualDisambiguation(unittest.TestCase):
    """Ce que le dialogue apporte de plus que la collecte."""

    def test_the_question_supplies_the_missing_money_context(self):
        """« 12 plaques » seul est refusé. En réponse à « facturé combien ? »,
        c'est un montant: la question a établi le contexte."""
        self.assertFalse(parse_montant("12 plaques").ok)
        resolved = resolve_field("budget_eur", "12 plaques", referentiel(), TODAY)
        self.assertEqual(resolved.value, 12000.0)

    def test_context_applies_through_the_loop(self):
        talk = dialogue()
        talk.receive("j'ai fini la salle de bain rue Rode, 6 m2", TODAY)
        self.assertEqual(talk.conversation.awaiting, "budget_eur")
        reply = talk.receive("12 plaques", TODAY)
        self.assertEqual(reply.kind, REGISTERED)
        self.assertEqual(talk.chantiers()[0]["budget_eur"], 12000.0)


class TestRouting(unittest.TestCase):
    def setUp(self):
        self.ref = referentiel()

    def test_a_dense_message_is_a_new_entry_not_an_answer(self):
        """Sans ce test, « j'ai livré la cuisine place Nansouty, 14 m2, 22
        plaques » se ferait absorber comme réponse et les deux chantiers
        fusionneraient."""
        text = "j'ai livré la cuisine place Nansouty, 14 m2, ça a coûté 22 plaques"
        self.assertGreaterEqual(resolved_field_count(text, self.ref, TODAY), 2)
        self.assertTrue(looks_like_new_event(text, None, self.ref, TODAY))

    def test_a_short_answer_is_not_a_new_entry(self):
        for answer in ("c'était une salle de bain", "6 m2", "aux Chartrons"):
            self.assertFalse(
                looks_like_new_event(answer, None, self.ref, TODAY), answer
            )

    def test_two_chantiers_never_merge(self):
        talk = dialogue()
        talk.receive(VOCAL, TODAY)                       # attend la nature
        reply = talk.receive(
            "j'ai livré la cuisine place Nansouty, 14 m2, ça a coûté 22 plaques", TODAY
        )
        self.assertEqual(reply.kind, REGISTERED)
        registered = talk.chantiers()[0]
        self.assertEqual(registered["nature"], "cuisine")
        self.assertEqual(registered["territoire"], "nansouty")
        # Le premier chantier n'est pas perdu: il est garé, avec ce qui avait
        # déjà été résolu pour lui.
        self.assertEqual(len(talk.conversation.parked), 1)
        parked = talk.conversation.parked[0]
        self.assertEqual(parked.fields["territoire"], "chartrons")
        self.assertEqual(parked.fields["budget_eur"], 12000.0)
        self.assertIn("rue Notre-Dame", parked.source_text)

    def test_an_explicit_new_event_cue_wins(self):
        self.assertTrue(looks_like_new_event("j'ai fini un truc", None, self.ref, TODAY))

    def test_a_different_nature_signals_another_chantier(self):
        talk = dialogue()
        talk.receive("la salle de bain rue Rode, 6 m2", TODAY)
        self.assertTrue(
            looks_like_new_event("la cuisine", talk.conversation.active, self.ref, TODAY)
        )


class TestHydration(unittest.TestCase):
    def test_the_posed_example_completes_in_one_answer(self):
        """L'effet attendu en démonstration: une question, une réponse, enregistré."""
        talk = dialogue()
        first = talk.receive(VOCAL, TODAY)
        self.assertEqual(first.kind, ASK)
        self.assertEqual(talk.conversation.awaiting, "nature")

        second = talk.receive("c'était une salle de bain", TODAY)
        self.assertEqual(second.kind, REGISTERED)
        self.assertEqual(second.field_filled, "nature")

        chantier = talk.chantiers()[0]
        self.assertEqual(chantier["nature"], "salle-de-bain")
        self.assertEqual(chantier["territoire"], "chartrons")
        self.assertEqual(chantier["budget_eur"], 12000.0)
        self.assertEqual(chantier["duration_days"], 4)

    def test_the_source_of_both_messages_is_kept(self):
        talk = dialogue()
        talk.receive(VOCAL, TODAY)
        talk.receive("c'était une salle de bain", TODAY)
        notes = talk.chantiers()[0]["notes"]
        self.assertIn("rue Notre-Dame", notes)
        self.assertIn("salle de bain", notes)

    def test_several_missing_fields_are_asked_one_at_a_time(self):
        talk = dialogue()
        reply = talk.receive("j'ai fini un chantier aux Chartrons", TODAY)
        self.assertEqual(reply.kind, ASK)
        asked = [talk.conversation.awaiting]
        reply = talk.receive("une cuisine", TODAY)
        self.assertEqual(reply.kind, ASK)
        asked.append(talk.conversation.awaiting)
        self.assertEqual(asked, ["nature", "budget_eur"])

    def test_an_unresolvable_answer_does_not_advance(self):
        talk = dialogue()
        talk.receive(VOCAL, TODAY)
        talk.receive("j'sais plus trop", TODAY)
        self.assertEqual(talk.conversation.awaiting, "nature")
        self.assertEqual(talk.chantiers(), [])


class TestAmendments(unittest.TestCase):
    def _registered(self) -> Dialogue:
        talk = dialogue()
        talk.receive("la salle de bain rue Rode, facturé 11 400 euros", TODAY)
        return talk

    def test_a_detail_sent_after_registration_amends_it(self):
        """« 6 m2 » juste après l'enregistrement précise le chantier, il n'en
        ouvre pas un autre."""
        talk = self._registered()
        reply = talk.receive("6 m2", TODAY)
        self.assertEqual(reply.kind, PIECE_REQUEST)
        self.assertEqual(talk.chantiers()[0]["size"], 6.0)
        self.assertEqual(len(talk.chantiers()), 1)

    def test_an_explicit_date_corrects_a_defaulted_one(self):
        talk = self._registered()
        self.assertEqual(talk.chantiers()[0]["completed_on"], TODAY.isoformat())
        talk.receive("hier", TODAY)
        self.assertEqual(
            talk.chantiers()[0]["completed_on"], (TODAY - timedelta(days=1)).isoformat()
        )

    def test_a_defaulted_date_corrects_nothing(self):
        """Le résolveur de date rend toujours une valeur: sans seuil de
        confiance, n'importe quel message passerait pour une correction."""
        talk = self._registered()
        talk.receive("hier", TODAY)
        talk.receive("ça a été long", TODAY)
        self.assertEqual(
            talk.chantiers()[0]["completed_on"], (TODAY - timedelta(days=1)).isoformat()
        )


class TestOtherMetiers(unittest.TestCase):
    """La boucle de dialogue n'a jamais été écrite pour la rénovation en
    particulier: elle appelle des résolveurs, et ceux-ci savent parler
    plomberie depuis que metiers/plomberie.json existe."""

    def test_a_plumbing_job_is_captured_in_one_message(self):
        talk = dialogue()
        reply = talk.receive(
            "j'ai changé un chauffe-eau à Caudéran, 150 litres, "
            "ça a coûté 12 plaques",
            TODAY,
        )
        self.assertEqual(reply.kind, REGISTERED)
        chantier = talk.chantiers()[0]
        self.assertEqual(chantier["nature"], "chauffe-eau")
        self.assertEqual(chantier["territoire"], "cauderan")
        self.assertEqual(chantier["size"], 150.0)
        self.assertEqual(chantier["budget_eur"], 12000.0)


class TestGhostCandidates(unittest.TestCase):
    def test_pleasantries_create_nothing(self):
        talk = dialogue()
        for noise in ("ok merci", "super", "à plus"):
            self.assertEqual(talk.receive(noise, TODAY).kind, UNCLEAR, noise)
        self.assertEqual(talk.chantiers(), [])
        self.assertIsNone(talk.conversation.active)


class TestPieces(unittest.TestCase):
    def test_registration_asks_for_the_invoice(self):
        talk = dialogue()
        reply = talk.receive("la salle de bain rue Rode, facturé 11 400 euros", TODAY)
        self.assertEqual(reply.kind, REGISTERED)
        self.assertIn("facture", reply.text)
        self.assertIsNotNone(talk.conversation.awaiting_piece_for)

    def test_a_referenced_invoice_makes_the_chantier_documented(self):
        talk = dialogue()
        talk.receive("la salle de bain rue Rode, facturé 11 400 euros", TODAY)
        self.assertEqual(talk.chantiers()[0]["provenance"], "vocal")
        reply = talk.receive("voilà la facture F2026-118", TODAY)
        self.assertEqual(reply.kind, PIECE_RECEIVED)
        chantier = talk.chantiers()[0]
        self.assertEqual(chantier["provenance"], "facture")
        self.assertEqual(chantier["reference"], "F2026-118")

    def test_reference_detection_needs_a_piece_cue(self):
        self.assertIsNone(find_piece_reference("F2026-118"))
        self.assertEqual(find_piece_reference("facture F2026-118"), "F2026-118")
        self.assertEqual(find_piece_reference("le devis D2026-004"), "D2026-004")

    def test_an_undocumented_chantier_surfaces_in_the_work_plan(self):
        talk = dialogue()
        talk.receive("la salle de bain rue Rode, facturé 11 400 euros", TODAY)
        plan = " ".join(talk.work_plan())
        self.assertIn("Facture attendue", plan)
        self.assertIn("n'entre dans aucun budget publié", plan)


class TestStaleness(unittest.TestCase):
    def test_an_old_question_can_no_longer_be_answered(self):
        """« salle de bain » trois semaines plus tard ne désigne plus rien."""
        talk = dialogue()
        talk.receive(VOCAL, TODAY)
        later = TODAY + timedelta(days=PENDING_TTL_DAYS + 1)
        reply = talk.receive("c'était une salle de bain", later)
        self.assertNotEqual(reply.kind, REGISTERED)
        self.assertEqual(len(talk.conversation.parked), 1)
        self.assertIn("sans réponse", str(talk.conversation.parked[0].refusals))

    def test_a_fresh_question_is_still_answerable(self):
        talk = dialogue()
        talk.receive(VOCAL, TODAY)
        later = TODAY + timedelta(days=PENDING_TTL_DAYS - 1)
        self.assertEqual(talk.receive("une salle de bain", later).kind, REGISTERED)


class TestPersistence(unittest.TestCase):
    def test_state_survives_serialisation(self):
        talk = dialogue()
        talk.receive(VOCAL, TODAY)
        payload = talk.conversation.to_dict()
        self.assertEqual(payload["awaiting"], "nature")
        self.assertEqual(payload["asked_on"], TODAY.isoformat())
        self.assertIsNotNone(payload["active"])

    def test_chantiers_are_shaped_for_a_noyau(self):
        from noyau.chantier import Chantier

        talk = dialogue()
        talk.receive("la salle de bain rue Rode, 6 m2, facturé 11 400 euros", TODAY)
        talk.receive("facture F2026-118", TODAY)
        record = dict(talk.chantiers()[0])
        record.pop("date_confidence", None)
        chantier = Chantier.from_dict(record)
        self.assertTrue(chantier.is_documented)
        self.assertEqual(chantier.comparability_key, ("salle-de-bain", "5 à 8 m2"))

    def test_nothing_is_lost_when_a_conversation_is_abandoned(self):
        talk = dialogue()
        talk.receive(VOCAL, TODAY)
        talk.receive("j'ai fini la cuisine place Nansouty, 14 m2, 22 plaques facturé", TODAY)
        self.assertTrue(any("laissé de côté" in line for line in talk.work_plan()))


if __name__ == "__main__":
    unittest.main()
