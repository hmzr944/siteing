"""L'Audit d'Invisibilité: l'arme de prospection décrite dans docs/VENTE.md,
en code plutôt qu'en script à refaire à la main pour chaque prospect.

Un seul principe gouverne ce module: **ce n'est pas le relevé contractuel.**
``Market.prospecting_basket()`` produit délibérément moins de prompts que le
seuil de présentabilité (``score.MIN_PROMPTS``), donc ``AuditResult.is_presentable``
est structurellement faux ici — pas un oubli, la preuve que ce module ne peut
pas se faire passer pour l'audit vendu. Toute sortie de ce module porte la
mention « relevé indicatif », verbatim, parce que c'est le garde-fou non
négociable de docs/VENTE.md §1.
"""

from __future__ import annotations

from .score import AuditResult


def _top_competitor(result: AuditResult) -> tuple[str, int] | None:
    """Le concurrent qui apparaît le plus souvent là où le prospect est absent.

    C'est la donnée qui rend l'e-mail jour 0 vrai plutôt que générique: on ne
    nomme jamais un concurrent qu'on n'a pas vu cité.
    """
    tally: dict[str, int] = {}
    for spot in result.blind_spots:
        for name in spot.competitors:
            tally[name] = tally.get(name, 0) + 1
    if not tally:
        return None
    name = max(tally, key=lambda n: (tally[n], n))
    return name, tally[name]


def to_text(result: AuditResult) -> str:
    """Ce que le commercial regarde à l'écran en menant l'audit devant le prospect."""
    client = result.client_score
    lines = [
        f"AUDIT D'INVISIBILITÉ — {client.name}",
        f"{result.category} — {result.zone} · relevé indicatif, "
        f"{result.usable_prompt_count} question(s) testée(s) — "
        "PAS le relevé contractuel",
        "",
    ]

    if not result.blind_spots:
        lines.append(
            "Aucun angle mort sur ce panier réduit: pas de matière pour un "
            "Audit d'Invisibilité ici. Vérifier le panier complet avant de "
            "démarcher — ce prospect n'est peut-être pas une cible."
        )
        return "\n".join(lines)

    lines.append("QUESTIONS OÙ VOUS ÊTES ABSENT, VOS CONCURRENTS CITÉS")
    for spot in result.blind_spots:
        cited = ", ".join(spot.competitors)
        lines.append(f'  · « {spot.text} »\n    → cité(s) à votre place : {cited}')

    lines += [
        "",
        f"TAUX DE PRÉSENCE — {client.presence_rate:.0%} sur "
        f"{result.usable_prompt_count} questions testées",
    ]
    return "\n".join(lines)


def email_jour_0(result: AuditResult, prenom: str, lien: str, signature: str) -> str:
    """L'e-mail jour 0 de docs/VENTE.md §2, rempli avec le concurrent réellement
    le plus cité — jamais un nom générique, toujours ce que le relevé a montré."""
    top = _top_competitor(result)
    if top is None:
        raise ValueError(
            "aucun concurrent cité à la place du prospect: cet e-mail ne "
            "peut pas s'écrire tant qu'il n'y a pas d'angle mort à montrer"
        )
    concurrent, count = top
    client = result.client_score
    return (
        "Objet : Vous n'apparaissez pas\n\n"
        f"Bonjour {prenom},\n\n"
        f"J'ai posé {result.usable_prompt_count} questions d'achat de votre marché "
        f"aux moteurs de réponse IA — le genre de questions que vos clients posent "
        f"avant d'appeler. {concurrent} est cité {count} fois. {client.name} : zéro.\n\n"
        f"90 secondes, sans commentaire : {lien}\n\n"
        f"{signature}"
    )
