"""Ingestion d'un message vocal transcrit.

    python3 -m ingestion "Ouais j'ai fini la salle de bain rue Notre-Dame, \
y'en a eu pour 12 plaques, on a mis 4 jours"
    python3 -m ingestion --fichier messages.txt --llm
"""

from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

from noyau import Referentiel

from .extracteurs import HeuristicExtractor, LLMExtractor
from .extraction import build_candidate, summarise


def process(text: str, extractor, referentiel: Referentiel, entity_id: str, today: date):
    spans = extractor.spans(text)
    candidate = build_candidate(text, spans, entity_id, referentiel, today)
    question = candidate.next_question(referentiel)

    print(f"\n> {text.strip()}")
    print(f"  fragments   : " + ", ".join(f"{s.kind}={s.text!r}" for s in spans))
    print(f"  compris     : {summarise(candidate, referentiel)}")
    if candidate.refusals:
        for field, motive in candidate.refusals.items():
            print(f"  refus       : {field} — {motive}")
    print(
        f"  statut      : "
        + ("enregistrable" if candidate.is_complete else "incomplet")
        + f" (confiance min. {candidate.min_confidence:.2f})"
    )
    if question:
        print(f"  question    : {question.text}")
        print(
            f"                débloque {question.unlocks}"
            + (" (bloquant)" if question.blocking else "")
        )
    return candidate


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ingestion", description=__doc__.splitlines()[0])
    parser.add_argument("message", nargs="*", help="message transcrit")
    parser.add_argument("--fichier", type=Path, help="un message par ligne")
    parser.add_argument("-r", "--referentiel", default="referentiels/bordeaux.json")
    parser.add_argument("--entite", default="ferrand")
    parser.add_argument("--date", help="jour de l'énoncé (AAAA-MM-JJ)")
    parser.add_argument("--llm", action="store_true", help="extraction par modèle")
    parser.add_argument("--out", type=Path, help="dossier de sortie (candidats JSON)")
    args = parser.parse_args(argv)

    referentiel = Referentiel.load(args.referentiel)
    today = date.fromisoformat(args.date) if args.date else date.today()

    if args.llm:
        try:
            extractor = LLMExtractor()
        except RuntimeError as exc:
            print(f"{exc}\nrepli sur l'extracteur heuristique.\n")
            extractor = HeuristicExtractor()
    else:
        extractor = HeuristicExtractor()

    messages = list(args.message)
    if args.fichier:
        messages += [
            line.strip()
            for line in args.fichier.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.startswith("#")
        ]
    if not messages:
        parser.error("aucun message fourni")

    print(f"EXTRACTEUR : {extractor.name}")
    candidates = [
        process(text, extractor, referentiel, args.entite, today) for text in messages
    ]

    complete = sum(1 for c in candidates if c.is_complete)
    print(
        f"\n{complete}/{len(candidates)} enregistrable(s) sans question, "
        f"{len(candidates) - complete} en attente d'une réponse."
    )

    if args.out:
        args.out.mkdir(parents=True, exist_ok=True)
        path = args.out / "candidats.json"
        path.write_text(
            json.dumps([c.to_dict() for c in candidates], ensure_ascii=False, indent=2)
            + "\n",
            encoding="utf-8",
        )
        print(f"candidats : {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
