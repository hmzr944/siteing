#!/usr/bin/env python3
"""Démonstration de la boucle de dialogue complète.

    python3 tools/demo_dialogue.py

Rejoue un fil d'artisan de bout en bout: message insuffisant, question,
hydratation, enregistrement, demande de pièce, réception de pièce, nouveau
chantier, et bruit conversationnel.
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ingestion import Dialogue
from noyau import Referentiel

FIL = [
    "Ouais j'ai fini la rénovation rue Notre-Dame, y'en a eu pour 12 plaques, "
    "on a mis 4 jours, c'était galère",
    "c'était une salle de bain",
    "6 m2",
    "voilà la facture F2026-118",
    "j'ai livré la cuisine place Nansouty, 14 m2, ça a coûté 22 plaques",
    "hier",
    "ok merci",
]


def main() -> int:
    talk = Dialogue(Referentiel.load("referentiels/bordeaux.json"), entity_id="ferrand")
    today = date(2026, 8, 16)

    for message in FIL:
        reply = talk.receive(message, today)
        print(f"\nartisan  > {message}")
        for line in reply.text.splitlines():
            print(f"système  < {line}")
        print(f"           [{reply.kind}]")

    print("\n" + "=" * 72)
    print("\nCHANTIERS PRÊTS POUR LE NOYAU")
    for record in talk.chantiers():
        size = f"{record['size']:g} m2" if record.get("size") else "taille inconnue"
        piece = record.get("reference") or "sans pièce"
        print(
            f"  {record['id']}  {record['nature']:<18} {record['territoire']:<12} "
            f"{record['budget_eur']:>8.0f} €  {size:<14} {record['provenance']:<8} {piece}"
        )

    print("\nPLAN DE TRAVAIL")
    for line in talk.work_plan():
        print(f"  · {line}")

    talk.conversation.save(Path("conversations") / "ferrand.json")
    print("\nétat du fil : conversations/ferrand.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
