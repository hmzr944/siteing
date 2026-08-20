"""Le Noyau est l'actif du projet: ses seuils de preuve sont sa valeur.

Un seuil qui cède, c'est une anecdote publiée comme un fait, et le produit ne
vaut plus rien. Ces tests défendent les trois seuils et la frontière de
publication.
"""

import json
import unittest
from datetime import date, timedelta
from pathlib import Path

from noyau import (
    MIN_CHANTIERS,
    MIN_CHANTIERS_TERRITOIRE,
    NATURES,
    Chantier,
    Noyau,
    Referentiel,
    Territoire,
    aggregate,
)
from noyau.budget import MAX_AGE_DAYS, eligible
from noyau.chantier import FROM_INVOICE, FROM_VOICE
from noyau.territoire import normalize

ROOT = Path(__file__).resolve().parent.parent
REFERENTIEL = ROOT / "referentiels" / "bordeaux.json"
NOYAU = ROOT / "noyaux" / "atelier-ferrand.json"
TODAY = date(2026, 8, 16)


def referentiel() -> Referentiel:
    return Referentiel.load(REFERENTIEL)


def core() -> Noyau:
    return Noyau.load(NOYAU, referentiel())


def chantier(**kwargs) -> Chantier:
    base = dict(
        id="c", nature="salle-de-bain", territoire="chartrons",
        completed_on=date(2026, 1, 1), budget_eur=10000.0,
        provenance=FROM_INVOICE, reference="F-1", size=6.0,
    )
    base.update(kwargs)
    return Chantier(**base)


# -- territoire ---------------------------------------------------------------


class TestTerritoire(unittest.TestCase):
    def setUp(self):
        self.ref = referentiel()

    def test_normalization_drops_articles_and_accents(self):
        self.assertEqual(normalize("les Chartrons"), "chartrons")
        self.assertEqual(normalize("quartier des Chartrons"), "chartrons")
        self.assertEqual(normalize("Caudéran"), "cauderan")

    def test_variant_spellings_resolve_to_one_code(self):
        """Sans cela, la preuve se fragmente en quatre tas dont aucun n'atteint
        le seuil de publication."""
        for raw in ("Chartrons", "les chartrons", "quartier des Chartrons",
                    "Bordeaux Chartrons"):
            self.assertEqual(self.ref.resolve(raw).code, "chartrons", raw)

    def test_alias_resolves(self):
        self.assertEqual(self.ref.resolve("Bassins à flot").code, "bacalan")

    def test_free_text_containing_one_known_place_resolves(self):
        found = self.ref.resolve("chantier rue Notre-Dame aux Chartrons")
        self.assertEqual(found.code, "chartrons")

    def test_unknown_place_returns_none_rather_than_guessing(self):
        """Inventer un territoire, ce serait fabriquer de la preuve."""
        self.assertIsNone(self.ref.resolve("Paris"))
        self.assertIsNone(self.ref.resolve(""))

    def test_ambiguous_text_is_refused(self):
        found = self.ref.resolve("entre les Chartrons et Caudéran")
        self.assertIsNone(found, "deux territoires possibles: il faut refuser")

    def test_ancestors_climb_to_the_metropolis(self):
        self.assertEqual(
            [t.code for t in self.ref.ancestors("chartrons")],
            ["bordeaux", "bdx-metropole"],
        )

    def test_covers_is_transitive_and_reflexive(self):
        self.assertTrue(self.ref.covers("chartrons", "chartrons"))
        self.assertTrue(self.ref.covers("bordeaux", "chartrons"))
        self.assertTrue(self.ref.covers("bdx-metropole", "chartrons"))
        self.assertFalse(self.ref.covers("chartrons", "bordeaux"))

    def test_locative_forms_are_grammatical(self):
        self.assertEqual(self.ref.get("chartrons").locative(), "aux Chartrons")
        self.assertEqual(self.ref.get("talence").locative(), "à Talence")
        self.assertEqual(self.ref.get("la-bastide").locative(), "à la Bastide")
        self.assertEqual(self.ref.get("le-bouscat").locative(), "au Bouscat")

    def test_duplicate_codes_are_rejected(self):
        with self.assertRaises(ValueError):
            Referentiel([
                Territoire("a", "Alpha", "quartier"),
                Territoire("a", "Autre", "quartier"),
            ])

    def test_a_form_naming_two_territories_is_rejected(self):
        with self.assertRaises(ValueError):
            Referentiel([
                Territoire("a", "Alpha", "quartier"),
                Territoire("b", "Beta", "quartier", aliases=("Alpha",)),
            ])

    def test_orphan_parent_is_rejected(self):
        with self.assertRaises(ValueError):
            Referentiel([Territoire("a", "Alpha", "quartier", parent="fantome")])

    def test_top_is_the_root_of_the_hierarchy(self):
        self.assertEqual(self.ref.top().code, "bdx-metropole")

    def test_top_refuses_a_referentiel_without_exactly_one_root(self):
        """C'est ``top()`` qui fournit la zone par défaut d'un Noyau — donc sa
        position dans le registre des créneaux. Une racine ambiguë ne doit
        jamais se traduire par une devinette silencieuse."""
        with self.assertRaises(ValueError):
            Referentiel([
                Territoire("a", "Alpha", "quartier"),
                Territoire("b", "Beta", "quartier"),
            ]).top()
        with self.assertRaises(ValueError):
            Referentiel([Territoire("a", "Alpha", "quartier", parent="a")]).top()


# -- chantier -----------------------------------------------------------------


class TestChantier(unittest.TestCase):
    def test_surface_bands_make_sizes_comparable(self):
        nature = NATURES["salle-de-bain"]
        self.assertEqual(nature.band_of(4.0), "0 à 5 m2")
        self.assertEqual(nature.band_of(6.0), "5 à 8 m2")
        self.assertEqual(nature.band_of(20.0), "12 m2 et plus")
        self.assertIsNone(nature.band_of(None))

    def test_band_boundaries_do_not_overlap(self):
        """Une taille tombe dans exactement une bande."""
        nature = NATURES["salle-de-bain"]
        for size in (0.1, 4.9, 5.0, 7.9, 8.0, 11.9, 12.0, 30.0):
            bands = [
                f"{low}-{high}" for low, high in nature.bands
                if size >= low and (high is None or size < high)
            ]
            self.assertEqual(len(bands), 1, f"{size} m2 tombe dans {bands}")

    def test_size_unknown_means_no_comparability(self):
        """Sans taille, un chantier prouve une intervention mais n'entre dans
        aucun budget: on ne sait pas à quoi le comparer."""
        self.assertIsNone(chantier(size=None).comparability_key)

    def test_documented_provenance_requires_a_reference(self):
        with self.assertRaises(ValueError):
            chantier(provenance=FROM_INVOICE, reference=None)

    def test_voice_provenance_needs_no_reference_but_is_not_documented(self):
        told = chantier(provenance=FROM_VOICE, reference=None)
        self.assertFalse(told.is_documented)

    def test_invalid_budget_or_size_is_rejected(self):
        with self.assertRaises(ValueError):
            chantier(budget_eur=0)
        with self.assertRaises(ValueError):
            chantier(size=-3)

    def test_unknown_nature_typology_or_provenance_is_rejected(self):
        for bad in ({"nature": "piscine"}, {"typologie": "chalet"},
                    {"provenance": "rumeur"}):
            with self.assertRaises(ValueError):
                chantier(**bad)

    def test_unit_price_is_suppressed_where_it_would_mislead(self):
        """Une verrière se compte à la pièce: un prix au mètre y serait faux."""
        verriere = chantier(
            nature="verriere", size=3.0, budget_eur=4500, id="v1",
        )
        self.assertIsNone(verriere.unit_price)
        self.assertAlmostEqual(chantier(size=6.0, budget_eur=12000).unit_price, 2000.0)


# -- budget -------------------------------------------------------------------


class TestBudget(unittest.TestCase):
    def _group(self, n, **kwargs):
        return [
            chantier(id=f"c{i}", budget_eur=10000 + i * 500, **kwargs)
            for i in range(n)
        ]

    def test_below_the_threshold_nothing_is_published(self):
        published, blocked = aggregate(self._group(MIN_CHANTIERS - 1), TODAY)
        self.assertEqual(published, [])
        self.assertEqual(len(blocked), 1)
        self.assertEqual(blocked[0].missing, 1)

    def test_at_the_threshold_a_budget_is_published(self):
        published, blocked = aggregate(self._group(MIN_CHANTIERS), TODAY)
        self.assertEqual(len(published), 1)
        self.assertEqual(blocked, [])
        self.assertEqual(published[0].n, MIN_CHANTIERS)

    def test_undocumented_chantiers_never_enter_a_published_budget(self):
        """Un budget est une donnée que l'entreprise engage: elle ne peut pas
        reposer sur un souvenir."""
        told = [
            chantier(id=f"v{i}", provenance=FROM_VOICE, reference=None)
            for i in range(MIN_CHANTIERS + 2)
        ]
        published, blocked = aggregate(told, TODAY)
        self.assertEqual(published, [])
        self.assertIn("sans pièce justificative", blocked[0].reason)

    def test_stale_chantiers_are_excluded(self):
        old = TODAY - timedelta(days=MAX_AGE_DAYS + 1)
        group = self._group(MIN_CHANTIERS, completed_on=old)
        self.assertEqual(eligible(group, TODAY), [])
        published, blocked = aggregate(group, TODAY)
        self.assertEqual(published, [])
        self.assertIn("trop ancien", blocked[0].reason)

    def test_sizes_from_different_bands_are_not_averaged(self):
        small = [chantier(id=f"s{i}", size=6.0, budget_eur=11000) for i in range(3)]
        large = [chantier(id=f"l{i}", size=15.0, budget_eur=26000) for i in range(3)]
        _, blocked = aggregate(small + large, TODAY)
        self.assertEqual(len(blocked), 2, "deux bandes distinctes, jamais fusionnées")

    def test_statistics_are_correct(self):
        budgets = [9000, 10000, 11000, 12000, 13000]
        group = [
            chantier(id=f"c{i}", budget_eur=float(b)) for i, b in enumerate(budgets)
        ]
        published, _ = aggregate(group, TODAY)
        budget = published[0]
        self.assertEqual(budget.median, 11000)
        self.assertEqual(budget.low, 9000)
        self.assertEqual(budget.high, 13000)
        self.assertLessEqual(budget.p25, budget.median)
        self.assertGreaterEqual(budget.p75, budget.median)

    def test_statement_is_a_finding_never_an_offer(self):
        """« à partir de X € » serait un engagement commercial. « constaté sur
        N chantiers » est un fait."""
        published, _ = aggregate(self._group(MIN_CHANTIERS), TODAY)
        sentence = published[0].sentence()
        self.assertIn("constaté", sentence)
        self.assertIn(f"sur {MIN_CHANTIERS} chantiers", sentence)
        self.assertNotIn("à partir de", sentence)
        self.assertNotIn("tarif", sentence.lower())

    def test_wide_spread_is_flagged(self):
        spread = [5000, 6000, 11000, 24000, 30000]
        group = [
            chantier(id=f"c{i}", budget_eur=float(b)) for i, b in enumerate(spread)
        ]
        published, _ = aggregate(group, TODAY)
        self.assertTrue(published[0].is_wide, "une fourchette trop large doit se dire")

    def test_unit_price_is_reported_when_meaningful(self):
        published, _ = aggregate(self._group(MIN_CHANTIERS, size=6.0), TODAY)
        self.assertIsNotNone(published[0].median_unit_price)


# -- assemblage et publication ------------------------------------------------


class TestNoyau(unittest.TestCase):
    def setUp(self):
        self.core = core()

    def test_zone_is_deduced_from_the_referentiel_root_by_default(self):
        """Aucune ville codée en dur: la zone vient du référentiel donné, pas
        d'une chaîne figée dans noyau.py — sinon un Noyau ailleurs qu'à
        Bordeaux se retrouverait publié sous le mauvais nom de zone."""
        self.assertEqual(self.core.zone, "Bordeaux Métropole")

    def test_an_explicit_zone_is_respected(self):
        raw = json.loads(NOYAU.read_text(encoding="utf-8"))
        raw["zone"] = "Zone personnalisée"
        core_custom = Noyau.from_dict(raw, referentiel())
        self.assertEqual(core_custom.zone, "Zone personnalisée")

    def test_a_chantier_outside_the_referential_is_refused(self):
        raw = json.loads(NOYAU.read_text(encoding="utf-8"))
        raw["chantiers"][0]["territoire"] = "montmartre"
        with self.assertRaises(KeyError):
            Noyau.from_dict(raw, referentiel())

    def test_duplicate_chantier_ids_are_refused(self):
        raw = json.loads(NOYAU.read_text(encoding="utf-8"))
        raw["chantiers"].append(dict(raw["chantiers"][0]))
        with self.assertRaises(ValueError):
            Noyau.from_dict(raw, referentiel())

    def test_a_chantier_proves_its_district_and_every_parent(self):
        by_code = {p.territoire.code: p for p in self.core.territoires(TODAY)}
        self.assertGreater(by_code["bordeaux"].count, by_code["chartrons"].count)
        self.assertEqual(by_code["bdx-metropole"].count, len(self.core.chantiers))

    def test_district_below_the_threshold_is_not_published(self):
        publiables = {p.territoire.code for p in self.core.territoires_publiables(TODAY)}
        for preuve in self.core.territoires(TODAY):
            if preuve.territoire.level == "quartier":
                expected = preuve.count >= MIN_CHANTIERS_TERRITOIRE
                self.assertEqual(preuve.territoire.code in publiables, expected)

    def test_one_chantier_never_proves_a_district(self):
        singles = [
            p for p in self.core.territoires(TODAY)
            if p.territoire.level == "quartier" and p.count == 1
        ]
        self.assertTrue(singles, "la fixture doit contenir des quartiers isolés")
        published = {a.subject for a in self.core.publication(TODAY)}
        for preuve in singles:
            self.assertNotIn(preuve.territoire.code, published)

    def test_expired_credential_is_not_published(self):
        self.assertFalse(self.core.has_credential("decennale", TODAY))
        self.assertNotIn(
            "decennale", {a.subject for a in self.core.publication(TODAY)}
        )

    def test_valid_credential_is_published_and_queryable(self):
        self.assertTrue(self.core.has_credential("rge", TODAY))
        self.assertIn("rge", {a.subject for a in self.core.publication(TODAY)})

    def test_declared_claim_without_evidence_is_not_published(self):
        self.assertFalse(self.core.has_credential("delai-demarrage", TODAY))

    def test_every_gap_names_its_subject(self):
        """Une ligne de plan de travail qui ne dit pas de quoi elle parle est
        inutilisable par la personne qui va chercher les pièces."""
        for manque in self.core.manques(TODAY):
            self.assertGreater(len(manque.action), 30, manque.subject)
            if manque.kind == "budget":
                nature = manque.subject.split("/")[0]
                self.assertIn(NATURES[nature].label, manque.action)

    def test_published_and_gaps_do_not_overlap(self):
        published = {(a.kind, a.subject) for a in self.core.publication(TODAY)}
        gaps = {(m.kind, m.subject) for m in self.core.manques(TODAY)}
        self.assertEqual(published & gaps, set())

    def test_coverage_counts_agree_with_the_details(self):
        counts = self.core.coverage(TODAY)
        self.assertEqual(counts["assertions_publiees"], len(self.core.publication(TODAY)))
        self.assertEqual(counts["manques"], len(self.core.manques(TODAY)))
        self.assertEqual(
            counts["quartiers_publiables"], len(self.core.territoires_publiables(TODAY))
        )
        self.assertEqual(
            counts["chantiers_documentes"],
            sum(1 for c in self.core.chantiers if c.is_documented),
        )

    def test_credential_expiry_removes_it_from_publication_over_time(self):
        later = date(2027, 1, 1)
        self.assertTrue(self.core.has_credential("rge", TODAY))
        self.assertFalse(self.core.has_credential("rge", later))

    def test_assertions_serialise_with_their_evidence_count(self):
        for assertion in self.core.publication(TODAY):
            payload = assertion.to_dict()
            self.assertIn("statement", payload)
            self.assertIn("evidence_count", payload)
            self.assertGreaterEqual(payload["evidence_count"], 1)


if __name__ == "__main__":
    unittest.main()
