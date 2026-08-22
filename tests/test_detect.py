"""La détection doit être avare: un faux positif dans un audit facturé détruit
la crédibilité de la mesure entière, et donc du contrat."""

import unittest

from citation_audit.detect import find_mentions, normalize, signature_tokens
from citation_audit.market import Entity

CONTEXT = ["plombier", "plombiers", "Bordeaux", "une recherche de fuite"]


def entity(eid, name, **kwargs):
    return Entity(id=eid, name=name, **kwargs)


class TestNormalize(unittest.TestCase):
    def test_strips_accents_case_and_punctuation(self):
        self.assertEqual(normalize("Fiducé — Expertise, S.A.S."), "fiduce expertise s a s")

    def test_collapses_whitespace(self):
        self.assertEqual(normalize("  Sud-Ouest\n\tSanitaire "), "sud ouest sanitaire")

    def test_signature_drops_legal_forms(self):
        self.assertEqual(signature_tokens("SARL Vasseur Plomberie"), ["vasseur", "plomberie"])


class TestFindMentions(unittest.TestCase):
    def test_finds_name_with_accent_and_legal_form(self):
        entities = [entity("f", "Fiducé")]
        mentions = find_mentions("Je recommande FIDUCE, sérieux.", entities, [], CONTEXT)
        self.assertEqual([m.entity_id for m in mentions], ["f"])
        self.assertEqual(mentions[0].via, "nom")

    def test_ranks_by_order_of_appearance(self):
        entities = [
            entity("a", "Aquitaine Dépannage"),
            entity("b", "Hydrolys"),
            entity("c", "Ateliers Peyrat"),
        ]
        text = "1. Hydrolys ... 2. Ateliers Peyrat ... 3. Aquitaine Dépannage"
        ranks = {m.entity_id: m.rank for m in find_mentions(text, entities, [], CONTEXT)}
        self.assertEqual(ranks, {"b": 1, "c": 2, "a": 3})

    def test_alias_is_detected_and_labelled(self):
        entities = [entity("p", "Ateliers Peyrat", aliases=("Peyrat",))]
        mentions = find_mentions("Contactez Peyrat pour ce chantier.", entities, [], CONTEXT)
        self.assertEqual(mentions[0].via, "alias")

    def test_rejects_substring_without_word_boundary(self):
        """« Hydrolys » ne doit pas être trouvé dans « hydrolyse »."""
        entities = [entity("h", "Hydrolys")]
        self.assertEqual(find_mentions("un phénomène d'hydrolyse", entities, [], CONTEXT), [])

    def test_rejects_purely_generic_name(self):
        """Un nom composé uniquement des mots du marché ne prouve rien."""
        entities = [entity("g", "Plomberie Bordeaux")]
        text = "Pour la plomberie à Bordeaux, comparez plusieurs devis."
        self.assertEqual(find_mentions(text, entities, [], CONTEXT), [])

    def test_accepts_generic_words_with_a_distinctive_token(self):
        entities = [entity("v", "Plomberie Vasseur")]
        mentions = find_mentions("Plomberie Vasseur intervient vite.", entities, [], CONTEXT)
        self.assertEqual([m.entity_id for m in mentions], ["v"])

    def test_accepts_long_multiword_name_without_rare_token(self):
        entities = [entity("c", "Les Compagnons de la Garonne")]
        text = "Les Compagnons de la Garonne sont bien notés."
        self.assertEqual([m.entity_id for m in find_mentions(text, entities, [], CONTEXT)], ["c"])

    def test_sourced_domain_counts_and_outranks_prose(self):
        entities = [
            entity("a", "Aquitaine Dépannage"),
            entity("v", "Plomberie Vasseur", domains=("plomberie-vasseur.fr",)),
        ]
        mentions = find_mentions(
            "Aquitaine Dépannage est souvent recommandé.",
            entities,
            ["https://plomberie-vasseur.fr/tarifs"],
            CONTEXT,
        )
        by_id = {m.entity_id: m for m in mentions}
        self.assertEqual(by_id["v"].via, "domaine")
        self.assertEqual(by_id["v"].rank, 1, "une source citée place l'entité en tête")

    def test_absent_entity_yields_nothing(self):
        entities = [entity("v", "Plomberie Vasseur"), entity("a", "Aquitaine Dépannage")]
        mentions = find_mentions("Aquitaine Dépannage uniquement.", entities, [], CONTEXT)
        self.assertEqual([m.entity_id for m in mentions], ["a"])

    def test_ignores_short_alias(self):
        entities = [entity("s", "Sud-Ouest Sanitaire", aliases=("SO",))]
        self.assertEqual(find_mentions("SO bien noté.", entities, [], CONTEXT), [])


if __name__ == "__main__":
    unittest.main()
