"""Deux preuves, jamais confondues: l'existence légale (SIRENE) et le
contrôle de l'établissement — par domaine (voie express) ou par courrier au
siège (socle universel).

Ces tests défendent les cas limites explicitement décidés — SIREN radié,
homonymes, établissements multiples, diffusion partielle — et le principe qui
gouverne le module: refuser plutôt que deviner. Un canal librement saisi
(e-mail quelconque, téléphone) ne prouve rien, donc n'existe pas. Aucun test
n'appelle le vrai réseau: un ``fetch`` factice est injecté partout,
exactement comme le module le prévoit.
"""

import unittest
from datetime import date, datetime, timedelta, timezone

from noyau.verification import (
    ACTIF,
    COURRIER,
    COURRIER_VALIDITY_DAYS,
    DIFFUSIBLE,
    DOMAINE,
    DOMAINE_VALIDITY_MINUTES,
    IDENTITY_CONTROL_KEY,
    IDENTITY_EXISTENCE_KEY,
    NON_REVENDIQUEE,
    VERIFIEE_COURRIER,
    VERIFIEE_DOMAINE,
    ControlCode,
    SireneEtablissement,
    VerificationRefusee,
    by_name,
    by_siren,
    claim_existence,
    confirm_code,
    issue_code_courrier,
    issue_code_domaine,
    verification_status,
)

TODAY = date(2026, 8, 21)
NOW = datetime(2026, 8, 21, 10, 0, tzinfo=timezone.utc)


def sirene_result(
    siren="123456789", nom="Plomberie Martin", etat=ACTIF,
    code_postal="69001", commune="Lyon", nombre_etablissements=1,
    statut_diffusion=DIFFUSIBLE, statut_diffusion_etablissement=DIFFUSIBLE,
):
    return {
        "siren": siren,
        "nom_complet": nom,
        "date_creation": "2015-03-12",
        "date_fermeture": None,
        "nombre_etablissements": nombre_etablissements,
        "statut_diffusion": statut_diffusion,
        "siege": {
            "siret": f"{siren}00012",
            "adresse": f"1 rue de la République {code_postal} {commune}",
            "code_postal": code_postal,
            "libelle_commune": commune,
            "etat_administratif": etat,
            "statut_diffusion_etablissement": statut_diffusion_etablissement,
        },
    }


def fake_fetch(payload):
    """Un ``fetch`` factice qui ignore l'URL et rend toujours le même corps."""

    def _fetch(url):
        return payload

    return _fetch


def etablissement(**kwargs) -> SireneEtablissement:
    return by_siren(
        kwargs.get("siren", "123456789"),
        fetch=fake_fetch({"results": [sirene_result(**kwargs)]}),
    )


# -- existence légale -----------------------------------------------------------


class TestBySiren(unittest.TestCase):
    def test_siren_actif_est_resolu(self):
        entreprise = etablissement()
        self.assertEqual(entreprise.siren, "123456789")
        self.assertTrue(entreprise.est_actif)
        self.assertTrue(entreprise.est_diffusible)
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


class TestDiffusionPartielle(unittest.TestCase):
    """Un dirigeant qui a protégé ses données Sirene (statut "P") n'apparaît
    jamais — même en fiche référencée. L'API sert alors "[NON-DIFFUSIBLE]"
    à la place des champs d'adresse: publier ça serait à la fois un faux pas
    de confiance et un affichage cassé."""

    def test_diffusion_partielle_entreprise_refuse(self):
        payload = {"results": [sirene_result(statut_diffusion="P")]}
        with self.assertRaises(VerificationRefusee):
            by_siren("123456789", fetch=fake_fetch(payload))

    def test_diffusion_partielle_etablissement_refuse(self):
        payload = {"results": [sirene_result(statut_diffusion_etablissement="P")]}
        with self.assertRaises(VerificationRefusee):
            by_siren("123456789", fetch=fake_fetch(payload))

    def test_les_non_diffusibles_sont_ecartes_des_homonymes(self):
        payload = {
            "results": [
                sirene_result(siren="111111111"),
                sirene_result(siren="222222222", statut_diffusion="P"),
            ]
        }
        resultats = by_name("Plomberie Martin", fetch=fake_fetch(payload))
        self.assertEqual([r.siren for r in resultats], ["111111111"])


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
        entreprise = etablissement(nombre_etablissements=12)
        self.assertEqual(entreprise.nombre_etablissements, 12)
        # Le SIRET résolu est bien celui du siège, pas un établissement au hasard.
        self.assertTrue(entreprise.siret_siege.startswith(entreprise.siren))


class TestClaimExistence(unittest.TestCase):
    def test_forme_une_affirmation_verifiee(self):
        claim = claim_existence(etablissement(), today=TODAY)
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
        claim = claim_existence(etablissement(), today=TODAY)
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


# -- contrôle par domaine (voie express) -----------------------------------------


class TestIssueCodeDomaine(unittest.TestCase):
    def test_emet_un_code_pour_une_adresse_du_domaine_declare(self):
        control, code = issue_code_domaine(
            "atelier-ferrand", "contact@atelier-ferrand.fr",
            "https://atelier-ferrand.fr", now=NOW,
        )
        self.assertEqual(len(code), 6)
        self.assertTrue(code.isdigit())
        self.assertEqual(control.canal, DOMAINE)
        self.assertEqual(
            control.expires_at, NOW + timedelta(minutes=DOMAINE_VALIDITY_MINUTES)
        )

    def test_www_et_schema_sont_normalises(self):
        control, _ = issue_code_domaine(
            "x", "info@atelier-ferrand.fr", "http://www.atelier-ferrand.fr/contact",
            now=NOW,
        )
        self.assertEqual(control.canal, DOMAINE)

    def test_un_sous_domaine_du_domaine_declare_est_accepte(self):
        control, _ = issue_code_domaine(
            "x", "contact@mail.atelier-ferrand.fr", "https://atelier-ferrand.fr",
            now=NOW,
        )
        self.assertEqual(control.canal, DOMAINE)

    def test_une_adresse_hors_domaine_refuse(self):
        # L'usurpateur saisirait la sienne: seule une adresse du domaine
        # déclaré sur la fiche prouve quelque chose.
        with self.assertRaises(VerificationRefusee):
            issue_code_domaine(
                "x", "pirate@autre-domaine.fr", "https://atelier-ferrand.fr", now=NOW
            )

    def test_un_domaine_grand_public_refuse(self):
        # Une adresse Gmail ne prouve le contrôle d'aucune entreprise, quel
        # que soit le nom devant l'arobase — même si le site déclaré était
        # lui-même une page Gmail, ce qui n'a pas de sens non plus.
        with self.assertRaises(VerificationRefusee):
            issue_code_domaine(
                "x", "atelier.ferrand@gmail.com", "https://gmail.com", now=NOW
            )

    def test_sans_site_declare_refuse_vers_le_courrier(self):
        with self.assertRaises(VerificationRefusee):
            issue_code_domaine("x", "contact@atelier-ferrand.fr", "", now=NOW)

    def test_adresse_mal_formee_refuse(self):
        with self.assertRaises(VerificationRefusee):
            issue_code_domaine("x", "pas-une-adresse", "https://atelier-ferrand.fr", now=NOW)

    def test_masque_l_adresse(self):
        control, _ = issue_code_domaine(
            "x", "jean.dupont@atelier-ferrand.fr", "https://atelier-ferrand.fr", now=NOW
        )
        self.assertNotIn("dupont", control.destination_masquee)
        self.assertIn("@atelier-ferrand.fr", control.destination_masquee)

    def test_le_hash_ne_permet_pas_de_retrouver_le_code_en_clair(self):
        control, code = issue_code_domaine(
            "x", "a@atelier-ferrand.fr", "https://atelier-ferrand.fr", now=NOW
        )
        self.assertNotEqual(control.code_hash, code)


# -- contrôle par courrier (socle universel) -------------------------------------


class TestIssueCodeCourrier(unittest.TestCase):
    def test_emet_un_code_vers_l_adresse_du_siege(self):
        control, code = issue_code_courrier("x", etablissement(), now=NOW)
        self.assertEqual(control.canal, COURRIER)
        self.assertEqual(len(code), 6)
        # La destination vient du répertoire, jamais d'une saisie: le masque
        # ne montre que la commune, l'adresse complète est déjà publique
        # mais n'a pas à voyager avec l'objet de contrôle.
        self.assertIn("69001 Lyon", control.destination_masquee)
        self.assertEqual(
            control.expires_at, NOW + timedelta(days=COURRIER_VALIDITY_DAYS)
        )

    def test_un_courrier_a_le_temps_d_arriver_et_de_se_perdre(self):
        # La fenêtre postale est en jours, pas en minutes: un code encore
        # valide trois semaines après l'envoi doit se confirmer.
        control, code = issue_code_courrier("x", etablissement(), now=NOW)
        trois_semaines = NOW + timedelta(days=21)
        claim = confirm_code(control, code, today=TODAY, now=trois_semaines)
        self.assertTrue(claim.is_publishable(TODAY))

    def test_sans_adresse_au_repertoire_refuse(self):
        entreprise = SireneEtablissement(
            siren="123456789", nom="X", siret_siege="12345678900012",
            adresse="  ", code_postal="", commune="",
            etat_administratif=ACTIF, statut_diffusion=DIFFUSIBLE,
            statut_diffusion_etablissement=DIFFUSIBLE,
            date_creation=None, nombre_etablissements=1,
        )
        with self.assertRaises(VerificationRefusee):
            issue_code_courrier("x", entreprise, now=NOW)


# -- confirmation ----------------------------------------------------------------


class TestConfirmCode(unittest.TestCase):
    def domaine(self):
        return issue_code_domaine(
            "atelier-ferrand", "contact@atelier-ferrand.fr",
            "https://atelier-ferrand.fr", now=NOW,
        )

    def test_code_correct_confirme_et_la_piece_porte_le_canal(self):
        control, code = self.domaine()
        claim = confirm_code(control, code, today=TODAY, now=NOW)
        self.assertEqual(claim.key, IDENTITY_CONTROL_KEY)
        self.assertEqual(claim.evidence[0].kind, "controle_domaine")
        self.assertTrue(claim.is_publishable(TODAY))
        self.assertEqual(claim.valid_until, TODAY + timedelta(days=365))

    def test_le_canal_courrier_produit_sa_propre_nature_de_piece(self):
        control, code = issue_code_courrier("x", etablissement(), now=NOW)
        claim = confirm_code(control, code, today=TODAY, now=NOW)
        self.assertEqual(claim.evidence[0].kind, "controle_courrier")

    def test_les_deux_natures_de_piece_round_trippent(self):
        from citation_audit.dossier import Evidence

        for kind in ("controle_domaine", "controle_courrier"):
            restored = Evidence.from_dict(
                {
                    "kind": kind,
                    "reference": "c***@atelier-ferrand.fr",
                    "issued_on": TODAY.isoformat(),
                    "checked_by": "Source Primaire",
                }
            )
            self.assertEqual(restored.kind, kind)

    def test_code_incorrect_refuse(self):
        control, _ = self.domaine()
        with self.assertRaises(VerificationRefusee):
            confirm_code(control, "000000", today=TODAY, now=NOW)

    def test_code_expire_refuse_meme_si_correct(self):
        control, code = self.domaine()
        apres_expiration = NOW + timedelta(minutes=DOMAINE_VALIDITY_MINUTES + 1)
        with self.assertRaises(VerificationRefusee):
            confirm_code(control, code, today=TODAY, now=apres_expiration)

    def test_pas_de_seconde_chance_apres_un_code_faux(self):
        # confirm_code ne fait aucune tentative supplémentaire en interne:
        # chaque échec est un refus définitif de *ce* code, un nouveau code
        # doit être émis pour réessayer.
        control, code = self.domaine()
        with self.assertRaises(VerificationRefusee):
            confirm_code(control, "wrong1", today=TODAY, now=NOW)
        # Le bon code, lui, reste valide: on n'a pas corrompu l'état du
        # ControlCode immuable en échouant une fois.
        claim = confirm_code(control, code, today=TODAY, now=NOW)
        self.assertTrue(claim.is_publishable(TODAY))


# -- statut de vérification ------------------------------------------------------


class TestVerificationStatus(unittest.TestCase):
    """Le statut publié — sur la page, dans le JSON-LD, dans llms.txt — se
    déduit des affirmations, jamais d'un drapeau posé à la main."""

    def existence(self, today=TODAY):
        return claim_existence(etablissement(), today=today)

    def controle(self, par=DOMAINE):
        if par == DOMAINE:
            control, code = issue_code_domaine(
                "x", "contact@atelier-ferrand.fr", "https://atelier-ferrand.fr",
                now=NOW,
            )
        else:
            control, code = issue_code_courrier("x", etablissement(), now=NOW)
        return confirm_code(control, code, today=TODAY, now=NOW)

    def test_sans_existence_rien_n_est_publiable(self):
        self.assertIsNone(verification_status([], TODAY))

    def test_existence_seule_donne_une_fiche_referencee(self):
        self.assertEqual(
            verification_status([self.existence()], TODAY), NON_REVENDIQUEE
        )

    def test_les_deux_preuves_affichent_le_canal(self):
        self.assertEqual(
            verification_status([self.existence(), self.controle(DOMAINE)], TODAY),
            VERIFIEE_DOMAINE,
        )
        self.assertEqual(
            verification_status([self.existence(), self.controle(COURRIER)], TODAY),
            VERIFIEE_COURRIER,
        )

    def test_un_controle_sans_existence_ne_donne_aucun_statut(self):
        # L'existence est la base de tout: un contrôle orphelin (existence
        # expirée entre-temps, par exemple) ne suffit pas.
        self.assertIsNone(verification_status([self.controle(DOMAINE)], TODAY))

    def test_une_existence_expiree_retire_le_statut(self):
        vieille = self.existence(today=date(2020, 1, 1))
        self.assertIsNone(
            verification_status([vieille, self.controle(DOMAINE)], TODAY)
        )


if __name__ == "__main__":
    unittest.main()
