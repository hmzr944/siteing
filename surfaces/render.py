"""Rendu HTML d'un nœud du treillis.

Principe qui gouverne tout le fichier: **les mêmes faits figurent dans le texte
visible et dans le JSON-LD.** Un moteur de réponse extrait avant tout du texte
rendu; les données structurées confirment et désambiguïsent. Un fait qui
n'existerait que dans le JSON-LD serait deux fois plus faible qu'un fait présent
dans les deux. La redondance est ici une fonctionnalité, pas un gaspillage.

Deuxième principe: la page est un document, pas une vitrine. Pas de script, pas
de police distante, pas d'image décorative. Ce qui est mesuré et cité, c'est un
fait daté et localisé, jamais une mise en page.
"""

from __future__ import annotations

import html
import json
from datetime import date

from noyau import NATURES, Noyau

from .jsonld import for_node
from .lattice import CROISEMENT, ROOT, TERRITOIRE, Node

MONTHS = (
    "janvier", "février", "mars", "avril", "mai", "juin",
    "juillet", "août", "septembre", "octobre", "novembre", "décembre",
)

CSS = """
:root{--paper:#fbfbfa;--ink:#16181c;--soft:#575c63;--mute:#82888f;--rule:#e2e5e8;
--accent:#1b4d3e;--panel:#fff}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){
--paper:#111315;--ink:#e9ebed;--soft:#a8aeb4;--mute:#7b8188;--rule:#292d31;
--accent:#7cb79f;--panel:#17191c}}
:root[data-theme="dark"]{--paper:#111315;--ink:#e9ebed;--soft:#a8aeb4;
--mute:#7b8188;--rule:#292d31;--accent:#7cb79f;--panel:#17191c}
*{box-sizing:border-box}
body{margin:0;background:var(--paper);color:var(--ink);line-height:1.6;
font:16px/1.6 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
main{max-width:44rem;margin:0 auto;padding:2rem 1.25rem 4rem}
h1{font-size:1.75rem;line-height:1.2;margin:0 0 .5rem;text-wrap:balance}
h2{font-size:1.0625rem;margin:2rem 0 .5rem;padding-bottom:.35rem;
border-bottom:1px solid var(--ink)}
p{margin:0 0 .875rem;color:var(--soft)}
a{color:var(--accent)}
.lede{color:var(--ink);font-size:1.0625rem}
.fact{background:var(--panel);border:1px solid var(--rule);padding:.875rem 1rem;
margin:0 0 .875rem}
.fact strong{color:var(--ink)}
table{width:100%;border-collapse:collapse;font-size:.9375rem}
th,td{text-align:left;padding:.5rem .5rem .5rem 0;border-bottom:1px solid var(--rule)}
th{font-size:.75rem;text-transform:uppercase;letter-spacing:.08em;color:var(--mute)}
td.num{text-align:right;font-variant-numeric:tabular-nums}
ul.links{list-style:none;margin:0;padding:0}
ul.links li{padding:.45rem 0;border-bottom:1px solid var(--rule)}
footer{margin-top:2.5rem;padding-top:1rem;border-top:1px solid var(--rule);
font-size:.8125rem;color:var(--mute)}
.scroll{overflow-x:auto}
"""


def fr_date(value: date) -> str:
    return f"{value.day} {MONTHS[value.month - 1]} {value.year}"


def eur(value: float) -> str:
    return f"{round(value):,}".replace(",", " ") + " €"


def budget_scope(node: Node) -> tuple[int, int]:
    """Portée d'un budget: (chantiers agrégés, chantiers présents sur la page).

    Un budget est agrégé sur toute l'activité de l'entreprise pour une nature et
    une taille données, jamais sur le seul quartier: trois chantiers locaux ne
    font pas une médiane. Mais une page de quartier qui liste trois chantiers et
    annonce un budget « sur six chantiers » se contredit à l'œil nu. La portée
    doit donc être écrite, pas déduite.
    """
    if node.budget is None:
        return (0, 0)
    local = sum(
        1
        for c in node.chantiers
        if c.comparability_key == (node.budget.nature, node.budget.band)
    )
    return (node.budget.n, local)


def _scope_sentence(node: Node) -> str:
    total, local = budget_scope(node)
    if not total or node.territoire is None or total == local:
        return ""
    return (
        f" Ce budget porte sur les {total} chantiers de cette nature et de cette "
        f"taille réalisés par l'entreprise, tous secteurs confondus, dont {local} "
        f"{node.territoire.locative()}."
    )


def _facts_block(core: Noyau, node: Node, today: date, minimal: bool = False) -> str:
    """Les faits en clair. C'est ce que les moteurs extraient réellement."""
    blocks: list[str] = []

    if minimal:
        if core.legal_id:
            blocks.append(
                '<p class="fact"><strong>Identité vérifiée automatiquement</strong> '
                f"via le répertoire SIRENE, SIREN {html.escape(core.legal_id)}.</p>"
            )
        return "".join(blocks)

    if node.chantiers:
        where = (
            f" {node.territoire.locative()}" if node.territoire else f" à {core.zone}"
        )
        blocks.append(
            f'<p class="fact"><strong>{len(node.chantiers)} chantiers réalisés'
            f"{html.escape(where)}</strong>, dont {node.documented} adossés à une "
            f"facture ou un devis signé. Dernier chantier terminé le "
            f"{fr_date(node.latest)}.</p>"
        )

    if node.budget is not None:
        budget = node.budget
        unit = ""
        if budget.median_unit_price:
            spec = NATURES[budget.nature]
            unit = (
                f" Soit environ {eur(budget.median_unit_price)} par {spec.unit} "
                "sur ces chantiers."
            )
        blocks.append(
            f'<p class="fact"><strong>Budget médian constaté : '
            f"{eur(budget.median)}.</strong> La moitié des chantiers se situe "
            f"entre {eur(budget.p25)} et {eur(budget.p75)}, sur {budget.n} "
            f"chantiers facturés entre {fr_date(budget.oldest)} et "
            f"{fr_date(budget.newest)}, pour des ouvrages de {html.escape(budget.band)}."
            f"{html.escape(unit)}{html.escape(_scope_sentence(node))} Il s'agit "
            "d'un constat de facturation passée, et non d'un tarif ni d'une offre : "
            "chaque chantier fait l'objet d'un devis propre.</p>"
        )

    credentials = core.autorites(today)
    if credentials:
        items = " ".join(
            f"<strong>{html.escape(c.value)}</strong>, contrôlé le "
            f"{fr_date(c.verified_on)} et valable jusqu'au {fr_date(c.valid_until)}."
            for c in credentials
            if c.verified_on and c.valid_until
        )
        blocks.append(f'<p class="fact">{items}</p>')

    return "".join(blocks)


def _chantiers_table(node: Node) -> str:
    if not node.chantiers:
        return ""
    rows = []
    for chantier in sorted(node.chantiers, key=lambda c: c.completed_on, reverse=True):
        spec = NATURES[chantier.nature]
        size = f"{chantier.size:g} {spec.unit}" if chantier.size else "n/a"
        duration = f"{chantier.duration_days} j" if chantier.duration_days else "n/a"
        rows.append(
            f"<tr><td>{fr_date(chantier.completed_on)}</td>"
            f"<td>{html.escape(spec.label)}</td>"
            f'<td class="num">{html.escape(size)}</td>'
            f'<td class="num">{eur(chantier.budget_eur)}</td>'
            f'<td class="num">{duration}</td></tr>'
        )
    return (
        '<div class="scroll"><table><thead><tr><th>Terminé le</th><th>Nature</th>'
        "<th>Taille</th><th>Budget</th><th>Durée</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table></div>"
    )


def _links(node: Node, nodes: list[Node]) -> str:
    """Maillage interne: chaque page pointe vers ses voisines du treillis."""
    related = [
        other
        for other in nodes
        if other.slug != node.slug
        and (
            node.kind == ROOT
            or (node.territoire and other.territoire
                and other.territoire.code == node.territoire.code)
            or (node.nature and other.nature == node.nature)
        )
    ][:12]
    if not related:
        return ""
    items = "".join(
        f'<li><a href="{html.escape(other.path)}">{html.escape(other.title)}</a> '
        f"<span style=\"color:var(--mute)\">({len(other.chantiers)} chantiers)</span></li>"
        for other in related
    )
    return f'<h2>Voir aussi</h2><ul class="links">{items}</ul>'


def _embed(document: dict) -> str:
    """Sérialisation sûre pour un bloc script: aucune échappatoire possible."""
    payload = json.dumps(document, ensure_ascii=False, indent=2)
    return payload.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")


def page(
    core: Noyau, node: Node, nodes: list[Node], today: date, minimal: bool = False
) -> str:
    """Document HTML complet, autonome, sans script ni ressource distante.

    ``minimal`` produit la fiche du palier Gratuit: identité vérifiée
    automatiquement, aucun chantier ni certification. Voir docs/PLAN.md §2-3.
    """
    structured = _embed(for_node(core, node, today, minimal))
    heading = node.title if node.kind != ROOT else core.name

    if minimal:
        description = f"Fiche vérifiée de {core.name}, {core.category} à {core.zone}."
        body = f"""<h2>Identité</h2>
{_facts_block(core, node, today, minimal)}

<p>Fiche minimale, publiée gratuitement pour toute entreprise vérifiée.
Aucun chantier ni certification n'est publié à ce palier : ces deux matières
exigent une vérification humaine sur pièce.</p>"""
    else:
        description = (
            f"{len(node.chantiers)} chantiers documentés"
            + (f" {node.territoire.locative()}" if node.territoire else f" à {core.zone}")
            + f". {node.question}"
        )
        body = f"""<h2>Ce qui est établi</h2>
{_facts_block(core, node, today, minimal)}

<h2>Chantiers réalisés</h2>
{_chantiers_table(node)}

{_links(node, nodes)}"""

    return f"""<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(node.title)} — {html.escape(core.name)}</title>
<meta name="description" content="{html.escape(description[:300])}">
<meta name="robots" content="index, follow, max-snippet:-1, max-image-preview:large">
<script type="application/ld+json">
{structured}
</script>
<style>{CSS}</style>
</head>
<body>
<main>
<h1>{html.escape(heading)}</h1>
<p class="lede">{html.escape(node.question)}</p>

{body}

<footer>
<p>{
    f"Identité vérifiée automatiquement via le répertoire SIRENE pour {html.escape(core.name)}."
    if minimal else
    f"Chantiers, budgets et qualifications publiés par {html.escape(core.name)} "
    "et contrôlés sur pièces. Les budgets indiqués sont des constats de facturation "
    "passée : ils ne constituent ni un tarif, ni une offre, ni un engagement sur un "
    "chantier futur."
} Page mise à jour le {today.isoformat()}.</p>
</footer>
</main>
</body>
</html>
"""
