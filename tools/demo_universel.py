#!/usr/bin/env python3
"""Démonstration: le même code sert n'importe quel métier, n'importe quelle ville.

    python3 tools/demo_universel.py

``noyau/chantier.py`` chargeait autrefois un dict Python codé en dur pour la
rénovation (``NATURES``), et plusieurs modules de ``surfaces/`` écrivaient
« Bordeaux Métropole » en dur. Ni l'un ni l'autre n'était une contrainte
mécanique — comparabilité par bande, seuil de publication, preuve par pièce
s'appliquent à n'importe quel métier et n'importe quelle zone qui documente
des interventions datées, localisées et facturées.

Ce script publie trois Noyaux avec exactement les mêmes appels, en variant
métier et ville indépendamment:

* Atelier Ferrand — rénovation, Bordeaux (référentiel d'origine)
* Aqua Bordeaux — plomberie, Bordeaux (second métier, même ville)
* Atelier Croix-Rousse Rénovation — rénovation, Lyon (même métier, seconde ville)

Aucune branche « si Bordeaux alors... » ni « si rénovation alors... » n'existe
dans le code appelé ici — la preuve, c'est que ce script n'a besoin d'aucune.

Ceci teste le mécanisme en simulation, avec des données fictives. Ça ne
remplace aucune validation terrain: ça montre que l'architecture n'est
prisonnière ni d'un métier ni d'une ville, pas que ce marché en a besoin.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from noyau import Noyau, Referentiel
from surfaces.lattice import build, summary
from surfaces.site import generate

ENTREPRISES = [
    ("Atelier Ferrand", "noyaux/atelier-ferrand.json", "referentiels/bordeaux.json"),
    ("Aqua Bordeaux", "noyaux/aqua-bordeaux.json", "referentiels/bordeaux.json"),
    ("Atelier Croix-Rousse Rénovation", "noyaux/renov-lyon.json", "referentiels/lyon.json"),
]


def main() -> int:
    for label, noyau_path, referentiel_path in ENTREPRISES:
        core = Noyau.load(noyau_path, Referentiel.load(referentiel_path))
        coverage = core.coverage()
        nodes = build(core)
        pages = summary(nodes)
        out_dir = Path("out") / core.entity_id
        report = generate(core, f"https://{core.entity_id}.exemple.fr", out_dir)

        print(f"{label}  ({core.category}, {core.zone})")
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
        "Métier: metiers/*.json, fusionnés par noyau.catalogue.merge(). "
        "Ville: un fichier referentiels/*.json par zone, sa racine devient "
        "Noyau.zone (noyau.territoire.Referentiel.top()). Ajouter l'un ou "
        "l'autre ne demande jamais de toucher au code de ce script."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
