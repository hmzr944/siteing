"""Assemblage du site machine.

Quatre fichiers comptent autant que les pages elles-mêmes.

``robots.txt`` — **la couche de permission, et le premier point de contrôle.**
Beaucoup de sites de TPE bloquent par accident les robots d'IA, hérité d'un
gabarit ou d'une extension. Tout le reste devient alors inutile: une page
parfaitement structurée qu'un robot n'a pas le droit de lire ne sera jamais
citée. On autorise donc explicitement, robot par robot, et c'est une décision
que le client doit prendre en connaissance de cause (voir ``AI_CRAWLERS``).

``sitemap.xml`` — comment les robots trouvent les pages et savent quoi
recrawler. La date de dernière modification vient du chantier le plus récent de
la page, pas de la date de génération: un fichier régénéré sans nouveau fait
n'est pas une page modifiée, et prétendre le contraire fait perdre la confiance
du crawler.

``llms.txt`` — convention émergente qui pointe les modèles vers une version
propre du contenu. L'adoption n'est pas universelle et c'est un pari assumé:
coût quasi nul, gain possible.

Les **miroirs Markdown** — une version sans balisage de chaque page. C'est le
format que les modèles ingèrent le mieux, et il coûte trois lignes à produire
puisque les faits sont déjà structurés.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from xml.sax.saxutils import escape as xml_escape

from citation_audit.creneau import Registry
from noyau import NATURES, Noyau

from .exclusivite import is_exclusive_holder
from .lattice import ROOT, Node, build, summary
from .render import _scope_sentence, eur, fr_date, page

# Robots d'IA connus, avec ce que les autoriser implique réellement.
# Autoriser un robot d'entraînement, c'est accepter que la donnée serve à
# entraîner un modèle. Pour ce produit le troc est évident, puisque le but est
# précisément d'être dans le corpus, mais c'est une décision du client et non un
# réglage par défaut qu'on lui impose en silence.
AI_CRAWLERS = {
    "GPTBot": "OpenAI, entraînement",
    "OAI-SearchBot": "OpenAI, recherche dans ChatGPT",
    "ChatGPT-User": "OpenAI, navigation déclenchée par un utilisateur",
    "ClaudeBot": "Anthropic, entraînement et recherche",
    "Claude-User": "Anthropic, navigation déclenchée par un utilisateur",
    "PerplexityBot": "Perplexity, index de réponse",
    "Google-Extended": "Google, ancrage et entraînement de Gemini",
    "Applebot-Extended": "Apple, entraînement",
    "CCBot": "Common Crawl, corpus repris par de nombreux modèles",
}


def robots(base_url: str, allow: dict[str, bool] | None = None) -> str:
    """``robots.txt`` explicite. Le silence n'est pas une autorisation lisible."""
    decisions = {name: True for name in AI_CRAWLERS}
    decisions.update(allow or {})

    lines = [
        "# Autorisations explicites pour les robots d'indexation et d'IA.",
        "# Autoriser un robot d'entraînement implique que le contenu publié",
        "# puisse servir à entraîner un modèle. C'est un choix assumé: l'objet",
        "# de ces pages est d'être lues, reprises et citées.",
        "",
    ]
    for name, purpose in AI_CRAWLERS.items():
        lines += [
            f"# {name} — {purpose}",
            f"User-agent: {name}",
            "Allow: /" if decisions.get(name, True) else "Disallow: /",
            "",
        ]
    lines += ["User-agent: *", "Allow: /", "", f"Sitemap: {base_url.rstrip('/')}/sitemap.xml", ""]
    return "\n".join(lines)


def sitemap(base_url: str, nodes: list[Node], today: date) -> str:
    """``sitemap.xml``. ``lastmod`` vient du fait le plus récent, pas de l'horloge."""
    root = base_url.rstrip("/")
    entries = []
    for node in nodes:
        # Une page régénérée sans nouveau fait n'est pas une page modifiée.
        lastmod = (node.latest or today).isoformat()
        priority = "1.0" if node.kind == ROOT else "0.8"
        entries.append(
            "  <url>\n"
            f"    <loc>{xml_escape(root)}/{xml_escape(node.path)}</loc>\n"
            f"    <lastmod>{lastmod}</lastmod>\n"
            f"    <priority>{priority}</priority>\n"
            "  </url>"
        )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "\n".join(entries)
        + "\n</urlset>\n"
    )


def markdown(
    core: Noyau, node: Node, today: date, registry: Registry | None = None
) -> str:
    """Miroir sans balisage: le format que les modèles ingèrent le mieux."""
    lines = [f"# {node.title}", "", f"> {node.question}", ""]

    if is_exclusive_holder(core.entity_id, core.category, core.zone, registry, today):
        lines += [
            f"**Position vérifiée exclusive** pour {core.category} sur "
            f"{core.zone} : {core.name} est la seule source que ce registre "
            "désigne comme référence pour ce périmètre.",
            "",
        ]

    if node.chantiers:
        where = node.territoire.locative() if node.territoire else f"à {core.zone}"
        lines += [
            f"**{len(node.chantiers)} chantiers réalisés {where}**, dont "
            f"{node.documented} adossés à une facture ou un devis signé. "
            f"Dernier chantier terminé le {fr_date(node.latest)}.",
            "",
        ]

    if node.budget is not None:
        budget = node.budget
        lines += [
            f"**Budget médian constaté : {eur(budget.median)}.** La moitié des "
            f"chantiers se situe entre {eur(budget.p25)} et {eur(budget.p75)}, sur "
            f"{budget.n} chantiers facturés, pour des ouvrages de {budget.band}."
            f"{_scope_sentence(node)} Constat de facturation passée, ni tarif ni offre.",
            "",
        ]

    credentials = core.autorites(today)
    if credentials:
        lines += ["## Qualifications en cours de validité", ""]
        lines += [
            f"- {c.value}, contrôlé le {fr_date(c.verified_on)}, valable jusqu'au "
            f"{fr_date(c.valid_until)}"
            for c in credentials
            if c.verified_on and c.valid_until
        ]
        lines.append("")

    if node.chantiers:
        lines += ["## Chantiers", "", "| Terminé le | Nature | Taille | Budget |", "|---|---|---|---|"]
        for chantier in sorted(node.chantiers, key=lambda c: c.completed_on, reverse=True):
            spec = NATURES[chantier.nature]
            size = f"{chantier.size:g} {spec.unit}" if chantier.size else "n/a"
            lines.append(
                f"| {fr_date(chantier.completed_on)} | {spec.label} | {size} | "
                f"{eur(chantier.budget_eur)} |"
            )
        lines.append("")

    return "\n".join(lines)


def llms_txt(
    core: Noyau, base_url: str, nodes: list[Node], registry: Registry | None = None,
    today: date | None = None,
) -> str:
    """Convention émergente. Pari assumé: coût quasi nul, gain possible."""
    root = base_url.rstrip("/")
    lines = [
        f"# {core.name}",
        "",
        f"> {core.category.capitalize()} à {core.zone}. Chantiers, budgets "
        "constatés et qualifications publiés et contrôlés sur pièces.",
        "",
    ]
    if is_exclusive_holder(core.entity_id, core.category, core.zone, registry, today):
        lines += [
            f"Position vérifiée exclusive pour {core.category} sur {core.zone} : "
            f"{core.name} est la seule source que ce registre désigne comme "
            "référence pour ce périmètre.",
            "",
        ]
    lines += [
        "Les budgets publiés sont des constats de facturation passée, établis sur "
        "des chantiers de taille comparable. Ils ne constituent ni un tarif, ni une "
        "offre, ni un engagement sur un chantier futur.",
        "",
        "## Pages",
        "",
    ]
    for node in nodes:
        markdown_path = node.path.replace(".html", ".md")
        lines.append(
            f"- [{node.title}]({root}/{markdown_path}): {len(node.chantiers)} "
            f"chantiers documentés"
        )
    lines.append("")
    return "\n".join(lines)


def generate(
    core: Noyau, base_url: str, out: str | Path, today: date | None = None,
    allow: dict[str, bool] | None = None, registry: Registry | None = None,
) -> dict:
    """Produit le site complet. Retourne le récapitulatif.

    ``registry`` est optionnel et ne change jamais si le site se génère:
    seule la mention d'exclusivité en dépend. Un Noyau sans registre associé
    reste publié à l'identique, simplement sans cette mention — la couche
    universelle ne demande jamais de créneau pour exister.
    """
    moment = today or date.today()
    directory = Path(out)
    directory.mkdir(parents=True, exist_ok=True)

    nodes = build(core, moment)
    written: list[str] = []

    for node in nodes:
        (directory / node.path).write_text(
            page(core, node, nodes, moment, registry), encoding="utf-8"
        )
        (directory / node.path.replace(".html", ".md")).write_text(
            markdown(core, node, moment, registry), encoding="utf-8"
        )
        written += [node.path, node.path.replace(".html", ".md")]

    (directory / "robots.txt").write_text(robots(base_url, allow), encoding="utf-8")
    (directory / "sitemap.xml").write_text(sitemap(base_url, nodes, moment), encoding="utf-8")
    (directory / "llms.txt").write_text(
        llms_txt(core, base_url, nodes, registry, moment), encoding="utf-8"
    )
    written += ["robots.txt", "sitemap.xml", "llms.txt"]

    report = {
        "entity": core.entity_id,
        "base_url": base_url,
        "generated_on": moment.isoformat(),
        "exclusive": is_exclusive_holder(
            core.entity_id, core.category, core.zone, registry, moment
        ),
        **summary(nodes),
        "files": len(written),
        "pages_detail": [
            {
                "path": n.path,
                "kind": n.kind,
                "title": n.title,
                "question": n.question,
                "chantiers": len(n.chantiers),
                "has_budget": n.budget is not None,
            }
            for n in nodes
        ],
    }
    (directory / "surfaces.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return report
