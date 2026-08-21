"""Les surfaces: comment le Noyau devient lisible et citable par les moteurs.

Correction technique qui gouverne ce paquet: ``.well-known/ai-plugin.json`` est
mort, c'était le manifeste des ChatGPT Plugins, abandonné avec le passage aux
GPTs puis aux Actions. Bâtir dessus serait bâtir sur un cadavre.

Ce qui est réellement consommé aujourd'hui, par ordre d'importance:

1. le **texte rendu** d'une page HTML rapide;
2. le **JSON-LD** schema.org qui confirme et désambiguïse ce texte;
3. les **miroirs Markdown**, format que les modèles ingèrent le mieux;
4. la couche de permission (``robots.txt``) sans laquelle rien du reste ne sert.

Les agents ne découvrent pas des API: les crawlers lisent des pages. La couche
API et agent à agent viendra pour le transactionnel, quand les protocoles auront
des volumes réels.

Ce module ne connaît aucun palier commercial. Le registre publie la même
chose pour toute entreprise vérifiée, quel que soit ce qu'elle paie — c'est
ce qui le rend crédible comme source pour un agent. L'exclusivité éventuelle
(``citation_audit.creneau``) porte sur l'accompagnement, jamais sur ce que ce
module expose.
"""

from .jsonld import FORBIDDEN_TERMS, contains_offer_vocabulary, for_node
from .lattice import (
    CROISEMENT,
    MIN_CHANTIERS_CROISEMENT,
    ROOT,
    TERRITOIRE,
    Node,
    build,
    summary,
)
from .render import page
from .site import AI_CRAWLERS, generate, llms_txt, markdown, robots, sitemap

__all__ = [
    "AI_CRAWLERS",
    "CROISEMENT",
    "FORBIDDEN_TERMS",
    "MIN_CHANTIERS_CROISEMENT",
    "Node",
    "ROOT",
    "TERRITOIRE",
    "build",
    "contains_offer_vocabulary",
    "for_node",
    "generate",
    "llms_txt",
    "markdown",
    "page",
    "robots",
    "sitemap",
    "summary",
]
