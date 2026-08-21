"""Smoke-test réseau: interroge le vrai répertoire SIRENE.

Volontairement hors de `tests/` — `noyau/verification.py` est testé hors
ligne partout ailleurs, avec un `fetch` factice injecté, pour rester rapide
et stable. Ce script est l'inverse: il prouve que l'intégration réelle
fonctionne encore, contre le vrai `recherche-entreprises.api.gouv.fr`. Pas
automatisé, pas dans `unittest discover` — à lancer à la main quand on
change le client HTTP ou qu'on doute du contrat de l'API.

    python3 tools/verifie_siren.py                    # SIREN connu (La Poste)
    python3 tools/verifie_siren.py 356000000
    python3 tools/verifie_siren.py --nom "Boulangerie Martin"
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from noyau.verification import VerificationRefusee, by_name, by_siren

# La Poste — SIREN public, stable, actif depuis des décennies: un bon témoin
# pour vérifier que le client parle toujours correctement à l'API réelle.
SIREN_TEMOIN = "356000000"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("siren", nargs="?", default=SIREN_TEMOIN)
    parser.add_argument("--nom", help="chercher par nom au lieu d'un SIREN")
    parser.add_argument("--code-postal", help="filtre de désambiguïsation pour --nom")
    args = parser.parse_args(argv)

    print(f"SIRENE (réseau réel) — {'https://recherche-entreprises.api.gouv.fr'}\n")

    try:
        if args.nom:
            resultats = by_name(args.nom, code_postal=args.code_postal)
            if not resultats:
                print(f"Aucun résultat actif pour {args.nom!r}.")
                return 0
            print(f"{len(resultats)} établissement(s) actif(s) pour {args.nom!r}:\n")
            for entreprise in resultats:
                print(f"  SIREN {entreprise.siren} — {entreprise.nom}")
                print(f"    {entreprise.adresse}, {entreprise.code_postal} {entreprise.commune}")
                print(f"    {entreprise.nombre_etablissements} établissement(s) au total\n")
        else:
            entreprise = by_siren(args.siren)
            print(f"SIREN {entreprise.siren} résolu:")
            print(f"  nom      : {entreprise.nom}")
            print(f"  adresse  : {entreprise.adresse}, {entreprise.code_postal} {entreprise.commune}")
            print(f"  créée le : {entreprise.date_creation}")
            print(f"  actif    : {entreprise.est_actif}")
            print(f"  établissements : {entreprise.nombre_etablissements}")
    except VerificationRefusee as exc:
        print(f"REFUSÉ — {exc}")
        return 1

    print("\nOK — le client parle toujours à l'API réelle.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
