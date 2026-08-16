"""Inspection d'un Noyau.

    python3 -m noyau noyaux/atelier-ferrand.json --referentiel referentiels/bordeaux.json
    python3 -m noyau noyaux/atelier-ferrand.json -r referentiels/bordeaux.json --json out/
"""

from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

from .noyau import MIN_CHANTIERS_TERRITOIRE, Noyau
from .territoire import QUARTIER, Referentiel


def render(core: Noyau, today: date) -> str:
    counts = core.coverage(today)
    published, blocked = core.budgets(today)

    lines = [
        f"NOYAU — {core.name}",
        f"{core.category} · relevé au {today.isoformat()}",
        "",
        f"  {counts['chantiers']} chantiers dont {counts['chantiers_documentes']} adossés à une pièce",
        f"  {counts['quartiers_publiables']}/{counts['quartiers_touches']} quartiers au-dessus du seuil de preuve",
        f"  {counts['budgets_publies']} budget(s) publiable(s), {counts['budgets_bloques']} bloqué(s)",
        f"  {counts['autorites_valides']} attribut(s) d'autorité en cours de validité",
        "",
        "PUBLIÉ VERS LA SURFACE MACHINE",
    ]
    for assertion in core.publication(today):
        lines.append(f"  [{assertion.kind}] {assertion.statement}")

    lines += ["", "IMPLANTATION"]
    for preuve in core.territoires(today):
        if preuve.territoire.level != QUARTIER:
            continue
        mark = "publié" if preuve.count >= MIN_CHANTIERS_TERRITOIRE else "sous le seuil"
        plural = "s" if preuve.count > 1 else ""
        lines.append(
            f"  {preuve.territoire.name[:24]:<24} {preuve.count:>2} chantier{plural:<1} "
            f"({preuve.documented_count} documenté{plural})  {mark}"
        )

    if blocked:
        lines += ["", "BUDGETS BLOQUÉS"]
        for budget in blocked:
            lines.append(f"  {budget.nature}, {budget.band}")
            lines.append(f"      {budget.reason}")

    lines += ["", f"PLAN DE TRAVAIL ({counts['manques']} manques)"]
    for manque in core.manques(today):
        lines.append(f"  · {manque.action}")

    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="noyau", description=__doc__.splitlines()[0])
    parser.add_argument("noyau")
    parser.add_argument(
        "-r", "--referentiel", default="referentiels/bordeaux.json",
        help="référentiel géographique du marché",
    )
    parser.add_argument("--date", help="date du relevé (AAAA-MM-JJ), aujourd'hui par défaut")
    parser.add_argument("--json", type=Path, help="dossier de sortie pour la publication")
    args = parser.parse_args(argv)

    referentiel = Referentiel.load(args.referentiel)
    core = Noyau.load(args.noyau, referentiel)
    today = date.fromisoformat(args.date) if args.date else date.today()

    print(render(core, today))

    if args.json:
        args.json.mkdir(parents=True, exist_ok=True)
        payload = {
            "entity": {
                "id": core.entity_id,
                "name": core.name,
                "category": core.category,
                "legal_id": core.legal_id,
            },
            "observed_on": today.isoformat(),
            "coverage": core.coverage(today),
            "assertions": [a.to_dict() for a in core.publication(today)],
            "gaps": [m.to_dict() for m in core.manques(today)],
        }
        path = args.json / f"{core.entity_id}-noyau.json"
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(f"\npublication : {path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
