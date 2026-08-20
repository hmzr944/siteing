"""Génération du site machine d'un Noyau.

    python3 -m surfaces noyaux/atelier-ferrand.json \
        --url https://atelier-ferrand.fr --out out/site
"""

from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

from citation_audit.creneau import Registry
from noyau import Noyau, Referentiel

from .site import generate


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="surfaces", description=__doc__.splitlines()[0])
    parser.add_argument("noyau")
    parser.add_argument("-r", "--referentiel", default="referentiels/bordeaux.json")
    parser.add_argument("--url", required=True, help="URL publique de base")
    parser.add_argument("--out", type=Path, default=Path("out/site"))
    parser.add_argument("--date", help="date du relevé (AAAA-MM-JJ)")
    parser.add_argument(
        "--registre", type=Path, default=Path("registre/creneaux.json"),
        help="registre des créneaux, pour la mention d'exclusivité (optionnel)",
    )
    args = parser.parse_args(argv)

    core = Noyau.load(args.noyau, Referentiel.load(args.referentiel))
    today = date.fromisoformat(args.date) if args.date else date.today()
    # Registry.load() rend un registre vide si le fichier n'existe pas: pas
    # de créneau connu, donc jamais de mention d'exclusivité, jamais d'erreur.
    registry = Registry.load(args.registre)
    report = generate(core, args.url, args.out, today, registry=registry)

    print(f"SURFACES — {core.name}")
    if report["exclusive"]:
        print(f"  position vérifiée exclusive pour {core.category} sur {core.zone}")
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
