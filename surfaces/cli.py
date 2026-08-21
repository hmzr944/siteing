"""Génération du site machine d'un Noyau.

    python3 -m surfaces noyaux/atelier-ferrand.json \
        --url https://atelier-ferrand.fr --out out/site

    # fiche gratuite: identité vérifiée automatiquement, rien de plus
    python3 -m surfaces noyaux/atelier-ferrand.json \
        --url https://atelier-ferrand.fr --out out/site --distribution minimal
"""

from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

from noyau import Noyau, Referentiel
from noyau.verification import VerificationRefusee

from .site import COMPLET, DISTRIBUTIONS, generate


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="surfaces", description=__doc__.splitlines()[0])
    parser.add_argument("noyau")
    parser.add_argument("-r", "--referentiel", default="referentiels/bordeaux.json")
    parser.add_argument("--url", required=True, help="URL publique de base")
    parser.add_argument("--out", type=Path, default=Path("out/site"))
    parser.add_argument("--date", help="date du relevé (AAAA-MM-JJ)")
    parser.add_argument(
        "--distribution", choices=DISTRIBUTIONS, default=COMPLET,
        help="minimal (palier Gratuit: identité seulement) ou complet (défaut)",
    )
    parser.add_argument(
        "--require-verified-identity", action="store_true",
        help=(
            "applique le modèle à deux états (docs/VERIFICATION.md §4): "
            "minimal exige l'existence SIRENE (fiche référencée si non "
            "revendiquée), complet exige aussi le contrôle de l'établissement"
        ),
    )
    args = parser.parse_args(argv)

    core = Noyau.load(args.noyau, Referentiel.load(args.referentiel))
    today = date.fromisoformat(args.date) if args.date else date.today()
    try:
        report = generate(
            core, args.url, args.out, today, distribution=args.distribution,
            require_verified_identity=args.require_verified_identity,
        )
    except VerificationRefusee as exc:
        print(f"REFUSÉ — {exc}")
        return 1

    statut = report["verification_status"]
    etiquette = f", fiche {statut}" if statut else ""
    print(f"SURFACES — {core.name} ({report['distribution']}{etiquette})")
    print(
        f"{report['pages']} pages ({report['territoires']} territoires, "
        f"{report['croisements']} croisements dont {report['avec_budget']} avec budget)"
    )
    print(f"{report['files']} fichiers écrits dans {args.out}\n")
    for detail in report["pages_detail"]:
        budget = " + budget" if detail["has_budget"] else ""
        print(f"  {detail['path']:<44} {detail['chantiers']:>2} chantiers{budget}")
        print(f"      {detail['question']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
