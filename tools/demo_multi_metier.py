#!/usr/bin/env python3
"""Démonstration: le même code sert deux métiers, sans une ligne changée.

    python3 tools/demo_multi_metier.py

``noyau/chantier.py`` chargeait autrefois un dict Python codé en dur pour la
rénovation (``NATURES``). Il charge désormais tous les fichiers de
``metiers/`` et les fusionne — le Noyau, le budget constaté, le treillis de
pages et le JSON-LD n'ont jamais été spécifiques à un métier dans leur
mécanique, seul le vocabulaire l'était.

Ce script construit et publie deux Noyaux avec exactement les mêmes appels:
un de rénovation (``atelier-ferrand``, la démo existante) et un de plomberie
(``aqua-bordeaux``, nouveau). Aucune branche « si rénovation alors... »
n'existe dans le code appelé ici — la preuve de l'universalité, c'est que ce
script n'a pas besoin d'en avoir.

Ceci teste le mécanisme en simulation, avec des données fictives. Ça ne
remplace aucune validation terrain: ça montre que l'architecture n'est pas
prisonnière de la rénovation, pas que le marché de la plomberie en a besoin.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from noyau import Noyau, Referentiel
from surfaces.lattice import build, summary
from surfaces.site import generate

REFERENTIEL = Path("referentiels/bordeaux.json")

ENTREPRISES = [
    ("Atelier Ferrand", "noyaux/atelier-ferrand.json"),
    ("Aqua Bordeaux", "noyaux/aqua-bordeaux.json"),
]


def main() -> int:
    referentiel = Referentiel.load(REFERENTIEL)

    for label, path in ENTREPRISES:
        core = Noyau.load(path, referentiel)
        coverage = core.coverage()
        nodes = build(core)
        pages = summary(nodes)
        out_dir = Path("out") / core.entity_id
        report = generate(core, f"https://{core.entity_id}.exemple.fr", out_dir)

        print(f"{label}  ({core.category})")
        print(f"  métier: le même code Noyau/Surfaces, aucune branche par métier")
        print(
            f"  {coverage['chantiers']} chantiers ({coverage['chantiers_documentes']} "
            f"documentés) · {coverage['quartiers_publiables']} quartier(s) publiable(s) "
            f"· {coverage['budgets_publies']} budget(s) publié(s), "
            f"{coverage['budgets_bloques']} bloqué(s) · {coverage['assertions_publiees']} "
            "affirmations publiées"
        )
        print(f"  {pages['pages']} pages générées dans {out_dir}/")
        for assertion in core.publication()[:2]:
            print(f"    · {assertion.statement}")
        print()

    print(
        "Les natures de prestation viennent de metiers/renovation.json et "
        "metiers/plomberie.json, fusionnées par noyau.catalogue.merge() — "
        "ajouter un troisième métier ne demande qu'un troisième fichier JSON."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
