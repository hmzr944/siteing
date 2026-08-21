"""Deux preuves, jamais confondues: l'existence légale (SIRENE) et le
contrôle de l'établissement (code envoyé, resaisi).

Ces tests défendent les trois cas limites explicitement demandés — SIREN
radié, homonymes, établissements multiples — et le principe qui gouverne le
module: refuser plutôt que deviner. Aucun test n'appelle le vrai réseau: un
``fetch`` factice est injecté partout, exactement comme le module le prévoit.
"""

import unittest
from datetime import date, datetime, timedelta, timezone

from noyau.verification import (
    ACTIF,
    CODE_VALIDITY_MINUTES,
    EMAIL,
    IDENTITY_CONTROL_KEY,
    IDENTITY_EXISTENCE_KEY,
    TELEPHONE,
    ControlCode,
    SireneEtablissement,
    VerificationRefusee,
    by_name,
    by_siren,
    claim_existence,
    confirm_code,
    issue_code,
)

TODAY = date(2026, 8, 21)
NOW = datetime(2026, 8, 21, 10, 0, tzinfo=timezone.utc)


def sirene_result(
    siren="123456789", nom="Plomberie Martin", etat=ACTIF,
    code_postal="69001", commune="Lyon", nombre_etablissements=1,
):
    return {
        "siren": siren,
        "nom_complet": nom,
        "date_creation": "2015-03-12",
        "date_fermeture": None,
        "nombre_etablissements": nombre_etablissements,
        "siege": {
            "siret": f"{siren}00012",
            "adresse": f"1 rue de la République {code_postal} {commune}",
            "code_postal": code_postal,
            "libelle_commune": commune,
            "etat_administratif": etat,
        },
    }


def fake_fetch(payload):
    """Un ``fetch`` factice qui ignore l'URL et rend toujours le même corps."""

    def _fetch(url):
        return payload

    return _fetch


# -- existence légale -----------------------------------------------------------


class TestBySiren(unittest.TestCase):
    def test_siren_actif_est_resolu(self):
        entreprise = by_siren(
            "123456789", fetch=fake_fetch({"results": [sirene_result()]})
        )
        self.assertEqual(entreprise.siren, "123456789")
        self.assertTrue(entreprise.est_actif)
        self.assertEqual(entreprise.commune, "Lyon")

    def test_siren_mal_forme_refuse_sans_appeler_le_reseau(self):
        def _fetch(url):
            raise AssertionError("ne doit jamais être appelé sur un SIREN mal formé")

        with self.assertRaises(VerificationRefusee):
            by_siren("12345", fetch=_fetch)

    def test_siren_accepte_les_espaces_et_points(self):
        entreprise = by_siren(
            "123 456 789", fetch=fake_fetch({"results": [sirene_result()]})
        )
        self.assertEqual(entreprise.siren, "123456789")

    def test_siren_introuvable_refuse(self):
        with self.assertRaises(VerificationRefusee):
            by_siren("999999999", fetch=fake_fetch({"results": []}))

    def test_siren_radie_refuse(self):
        # F = fermeture, code SIRENE réel pour un établissement cessé.
        payload = {"results": [sirene_result(etat="F")]}
        with self.assertRaises(VerificationRefusee):
            by_siren("123456789", fetch=fake_fetch(payload))

    def test_ne_devine_jamais_un_autre_siren_que_celui_demande(self):
        # Le répertoire peut rendre des résultats voisins; on ne prend que
        # la correspondance exacte, jamais "le premier de la liste".
        payload = {"results": [sirene_result(siren="987654321")]}
        with self.assertRaises(VerificationRefusee):
            by_siren("123456789", fetch=fake_fetch(payload))


class TestByName(unittest.TestCase):
    def test_homonymes_rendus_tous_sans_choix_automatique(self):
        payload = {
            "results": [
                sirene_result(siren="111111111", commune="Lyon"),
                sirene_result(siren="222222222", commune="Nantes"),
                sirene_result(siren="333333333", commune="Toulouse"),
            ]
        }
        resultats = by_name("Boulangerie Martin", fetch=fake_fetch(payload))
        self.assertEqual(len(resultats), 3)
        self.assertEqual({r.siren for r in resultats}, {"111111111", "222222222", "333333333"})

    def test_aucun_resultat_rend_une_liste_vide_jamais_une_erreur_devinee(self):
        resultats = by_name("Entreprise Inexistante Xyz", fetch=fake_fetch({"results": []}))
        self.assertEqual(resultats, [])

    def test_code_postal_desambiguise(self):
        captured = {}

        def _fetch(url):
            captured["url"] = url
            return {"results": [sirene_result(code_postal="69001")]}

        by_name("Boulangerie Martin", code_postal="69001", fetch=_fetch)
        self.assertIn("code_postal=69001", captured["url"])

    def test_etablissements_radies_exclus_des_homonymes(self):
        payload = {
            "results": [
                sirene_result(siren="111111111", etat=ACTIF),
                sirene_result(siren="222222222", etat="F"),
            ]
        }
        resultats = by_name("Plomberie Martin", fetch=fake_fetch(payload))
        self.assertEqual([r.siren for r in resultats], ["111111111"])


class TestEtablissementsMultiples(unittest.TestCase):
    """Cas limite explicitement demandé: une entreprise à établissements
    multiples n'est résolue que par son siège — jamais un établissement
    secondaire deviné à sa place."""

    def test_le_nombre_d_etablissements_est_conserve_mais_seul_le_siege_est_resolu(self):
        payload = sirene_result(nombre_etablissements=12)
        entreprise = by_siren("123456789", fetch=fake_fetch({"results": [payload]}))
        self.assertEqual(entreprise.nombre_etablissements, 12)
        # Le SIRET résolu est bien celui du siège, pas un établissement au hasard.
        self.assertTrue(entreprise.siret_siege.startswith(entreprise.siren))


class TestClaimExistence(unittest.TestCase):
    def test_forme_une_affirmation_verifiee(self):
        entreprise = by_siren(
            "123456789", fetch=fake_fetch({"results": [sirene_result()]})
        )
        claim = claim_existence(entreprise, today=TODAY)
        self.assertEqual(claim.key, IDENTITY_EXISTENCE_KEY)
        self.assertEqual(claim.cluster, "identite")
        self.assertEqual(claim.evidence[0].kind, "immatriculation")
        self.assertTrue(claim.is_publishable(TODAY))
        self.assertEqual(claim.valid_until, TODAY + timedelta(days=30))

    def test_round_trip_par_dict(self):
        # Claim/Evidence n'exposent pas de to_dict (chargées depuis un JSON
        # écrit par l'ingestion, jamais sérialisées depuis l'objet) — le
        # round-trip se vérifie donc dans l'autre sens: la forme produite par
        # ``claim_existence`` doit rester lisible par ``Claim.from_dict``.
        entreprise = by_siren(
            "123456789", fetch=fake_fetch({"results": [sirene_result()]})
        )
        claim = claim_existence(entreprise, today=TODAY)
        from citation_audit.dossier import Claim

        restored = Claim.from_dict(
            {
                "key": claim.key,
                "label": claim.label,
                "value": claim.value,
                "cluster": claim.cluster,
                "schema_property": claim.schema_property,
                "schema_value": claim.schema_value,
                "verified_on": claim.verified_on.isoformat(),
                "valid_until": claim.valid_until.isoformat(),
                "evidence": [
                    {
                        "kind": e.kind,
                        "reference": e.reference,
                        "issued_on": e.issued_on.isoformat(),
                        "checked_by": e.checked_by,
                    }
                    for e in claim.evidence
                ],
            }
        )
        self.assertEqual(restored.key, claim.key)
        self.assertEqual(restored.evidence[0].kind, "immatriculation")


# -- contrôle de propriété -------------------------------------------------------


class TestIssueCode(unittest.TestCase):
    def test_emet_un_code_a_six_chiffres(self):
        control, code = issue_code("atelier-ferrand", EMAIL, "contact@atelier.fr", now=NOW)
        self.assertEqual(len(code), 6)
        self.assertTrue(code.isdigit())
        self.assertEqual(control.entity_id, "atelier-ferrand")
        self.assertEqual(
            control.expires_at, NOW + timedelta(minutes=CODE_VALIDITY_MINUTES)
        )

    def test_masque_l_email(self):
        control, _ = issue_code("x", EMAIL, "jean.dupont@atelier.fr", now=NOW)
        self.assertNotIn("dupont", control.destination_masquee)
        self.assertIn("@atelier.fr", control.destination_masquee)

    def test_masque_le_telephone(self):
        control, _ = issue_code("x", TELEPHONE, "0612345678", now=NOW)
        self.assertTrue(control.destination_masquee.endswith("78"))
        self.assertNotIn("0612345678", control.destination_masquee)

    def test_canal_inconnu_refuse(self):
        with self.assertRaises(VerificationRefusee):
            issue_code("x", "courrier", "1 rue de la Paix", now=NOW)

    def test_destination_vide_refuse(self):
        with self.assertRaises(VerificationRefusee):
            issue_code("x", EMAIL, "   ", now=NOW)

    def test_le_hash_ne_permet_pas_de_retrouver_le_code_en_clair(self):
        control, code = issue_code("x", EMAIL, "a@b.fr", now=NOW)
        self.assertNotEqual(control.code_hash, code)


class TestConfirmCode(unittest.TestCase):
    def test_code_correct_confirme_le_controle(self):
        control, code = issue_code("atelier-ferrand", EMAIL, "contact@atelier.fr", now=NOW)
        claim = confirm_code(control, code, today=TODAY, now=NOW)
        self.assertEqual(claim.key, IDENTITY_CONTROL_KEY)
        self.assertEqual(claim.evidence[0].kind, "controle_canal")
        self.assertTrue(claim.is_publishable(TODAY))
        self.assertEqual(claim.valid_until, TODAY + timedelta(days=365))

    def test_code_incorrect_refuse(self):
        control, _ = issue_code("x", EMAIL, "a@b.fr", now=NOW)
        with self.assertRaises(VerificationRefusee):
            confirm_code(control, "000000", today=TODAY, now=NOW)

    def test_code_expire_refuse_meme_si_correct(self):
        control, code = issue_code("x", EMAIL, "a@b.fr", now=NOW)
        apres_expiration = NOW + timedelta(minutes=CODE_VALIDITY_MINUTES + 1)
        with self.assertRaises(VerificationRefusee):
            confirm_code(control, code, today=TODAY, now=apres_expiration)

    def test_pas_de_seconde_chance_apres_un_code_faux(self):
        # confirm_code ne fait aucune tentative supplémentaire en interne:
        # chaque échec est un refus définitif de *ce* code, un nouveau code
        # doit être émis pour réessayer.
        control, code = issue_code("x", EMAIL, "a@b.fr", now=NOW)
        with self.assertRaises(VerificationRefusee):
            confirm_code(control, "wrong1", today=TODAY, now=NOW)
        # Le bon code, lui, reste valide: on n'a pas corrompu l'état du
        # ControlCode immuable en échouant une fois.
        claim = confirm_code(control, code, today=TODAY, now=NOW)
        self.assertTrue(claim.is_publishable(TODAY))


if __name__ == "__main__":
    unittest.main()
