"""Le vocabulaire des prestations est chargé par métier, pas codé en dur.

Ce que ces tests défendent: un métier ne doit jamais pouvoir en écraser un
autre silencieusement, et ajouter un métier ne doit demander de toucher aucun
code déjà écrit — seulement un fichier JSON de plus dans ``metiers/``.
"""

import unittest
from pathlib import Path

from noyau.catalogue import Catalogue, Nature, load_all, merge, merge_keywords

ROOT = Path(__file__).resolve().parent.parent
METIERS = ROOT / "metiers"


def make(metier: str, **natures: dict) -> Catalogue:
    return Catalogue.from_dict(
        {
            "metier": metier,
            "label": metier,
            "natures": natures,
        }
    )


class TestNature(unittest.TestCase):
    def test_band_of_picks_the_matching_range(self):
        nature = Nature("x", "X", "m2", ((0, 5), (5, None)))
        self.assertEqual(nature.band_of(3), "0 à 5 m2")
        self.assertEqual(nature.band_of(8), "5 m2 et plus")

    def test_band_of_unknown_size_is_none(self):
        nature = Nature("x", "X", "m2", ((0, None),))
        self.assertIsNone(nature.band_of(None))


class TestMerge(unittest.TestCase):
    def test_two_disjoint_catalogues_merge_cleanly(self):
        a = make("a", ax={"label": "A x", "unit": "m2", "bands": [[0, None]]})
        b = make("b", bx={"label": "B x", "unit": "ml", "bands": [[0, None]]})
        natures, _ = merge([a, b])
        self.assertEqual(set(natures), {"ax", "bx"})

    def test_a_code_reused_by_two_metiers_is_refused(self):
        """Un code de nature ambigu casserait la résolution de vocabulaire
        exactement comme un alias de territoire qui désignerait deux
        quartiers à la fois: on refuse plutôt que d'écraser silencieusement."""
        a = make("a", x={"label": "A x", "unit": "m2", "bands": [[0, None]]})
        b = make("b", x={"label": "B x", "unit": "m2", "bands": [[0, None]]})
        with self.assertRaises(ValueError):
            merge([a, b])

    def test_the_same_metier_can_appear_in_two_files_without_conflict(self):
        """Un métier qui se répète (même code, même propriétaire) n'est pas
        un conflit — seul un code disputé entre deux métiers différents l'est."""
        a = make("a", x={"label": "A x", "unit": "m2", "bands": [[0, None]]})
        also_a = make("a", y={"label": "A y", "unit": "m2", "bands": [[0, None]]})
        natures, _ = merge([a, also_a])
        self.assertEqual(set(natures), {"x", "y"})


class TestMergeKeywords(unittest.TestCase):
    def test_disjoint_keywords_all_resolve(self):
        a = make("a", ax={"label": "A x", "unit": "m2", "bands": [[0, None]], "keywords": ["mot-a"]})
        b = make("b", bx={"label": "B x", "unit": "ml", "bands": [[0, None]], "keywords": ["mot-b"]})
        index = merge_keywords([a, b])
        self.assertEqual(index, {"mot-a": "ax", "mot-b": "bx"})

    def test_a_keyword_shared_by_two_natures_resolves_to_neither(self):
        """Mieux vaut qu'une phrase ne résolve rien et pose une question,
        qu'une résolution silencieuse et fausse entre deux métiers."""
        a = make("a", ax={"label": "A x", "unit": "m2", "bands": [[0, None]], "keywords": ["ambigu"]})
        b = make("b", bx={"label": "B x", "unit": "ml", "bands": [[0, None]], "keywords": ["ambigu"]})
        index = merge_keywords([a, b])
        self.assertNotIn("ambigu", index)

    def test_a_disputed_keyword_does_not_break_the_others(self):
        a = make(
            "a",
            ax={"label": "A x", "unit": "m2", "bands": [[0, None]], "keywords": ["ambigu", "sur"]},
        )
        b = make(
            "b",
            bx={"label": "B x", "unit": "ml", "bands": [[0, None]], "keywords": ["ambigu"]},
        )
        index = merge_keywords([a, b])
        self.assertNotIn("ambigu", index)
        self.assertEqual(index["sur"], "ax")

    def test_loading_ambiguous_catalogues_never_raises(self):
        """Contrairement à merge() sur les codes, une ambiguïté de langage
        naturel entre métiers est plausible: elle ne doit jamais empêcher les
        catalogues de charger."""
        a = make("a", ax={"label": "A x", "unit": "m2", "bands": [[0, None]], "keywords": ["x"]})
        b = make("b", bx={"label": "B x", "unit": "ml", "bands": [[0, None]], "keywords": ["x"]})
        merge_keywords([a, b])  # ne lève pas


class TestBundledCatalogues(unittest.TestCase):
    """Les catalogues réellement livrés avec le dépôt, chargés comme au démarrage."""

    def test_at_least_two_metiers_are_bundled(self):
        catalogues = load_all(METIERS)
        self.assertGreaterEqual(len(catalogues), 2)
        self.assertIn("renovation", {c.metier for c in catalogues})
        self.assertIn("plomberie", {c.metier for c in catalogues})

    def test_bundled_catalogues_merge_without_collision(self):
        # Si deux métiers livrés se disputaient un code, ce test échouerait
        # à l'import de noyau.chantier lui-même, avant même d'arriver ici —
        # mais l'écrire explicitement documente l'invariant.
        natures, typologies = merge(load_all(METIERS))
        self.assertGreater(len(natures), 0)
        self.assertGreater(len(typologies), 0)

    def test_bundled_keywords_include_a_deliberate_cross_metier_ambiguity(self):
        """« salle d'eau » est un cas volontaire: rénovation et plomberie
        l'emploient toutes les deux pour des choses différentes. Le prouver
        ici documente que c'est un choix, pas un oubli."""
        index = merge_keywords(load_all(METIERS))
        self.assertNotIn("salle d'eau", index)
        self.assertEqual(index.get("salle de bain"), "salle-de-bain")
        self.assertEqual(index.get("chauffe-eau"), "chauffe-eau")


if __name__ == "__main__":
    unittest.main()
