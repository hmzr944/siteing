"""Interface en ligne de commande.

    python -m terrain protocole
    python -m terrain decision entretiens/
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .decision import decide
from .entretien import Entretien
from .seuils import PROTOCOLE_V2


def _protocole(args) -> int:
    p = PROTOCOLE_V2
    print(
        f"PROTOCOLE {p.version} — {p.vertical} · {p.zone}\n"
        f"hash {p.hash()}\n"
        f"{p.n_entreprises} entreprises\n\n"
        f"H1 (représentation)  niveau1 ≥ {p.h1_niveau1_min}  "
        f"niveau2 ≥ {p.h1_niveau2_min}  niveau3 ≥ {p.h1_niveau3_min}\n"
        f"H2 (capacité d'action)  niveau1 ≥ {p.h2_niveau1_min}  "
        f"niveau2 ≥ {p.h2_niveau2_min}  niveau3 ≥ {p.h2_niveau3_min}\n\n"
        "Seul le niveau 3 (engagement révélé, pas déclaré) compte comme "
        "signal commercial."
    )
    return 0


def _decision(args) -> int:
    directory = Path(args.dossier)
    paths = sorted(directory.glob("*.json"))
    if not paths:
        print(f"aucun entretien trouvé dans {directory}", file=sys.stderr)
        return 2

    entretiens = [Entretien.load(p) for p in paths]
    try:
        verdict = decide(entretiens)
    except ValueError as exc:
        print(f"décision impossible : {exc}", file=sys.stderr)
        return 2

    print(verdict.to_text())
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="terrain",
        description="Le protocole de validation terrain: seuils et décision, en code.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    proto = sub.add_parser("protocole", help="affiche les seuils verrouillés et leur hash")
    proto.set_defaults(func=_protocole)

    decision = sub.add_parser(
        "decision", help="agrège les entretiens d'un dossier et rend le verdict"
    )
    decision.add_argument("dossier", help="dossier contenant un fichier JSON par entretien")
    decision.set_defaults(func=_decision)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
