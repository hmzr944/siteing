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

Ce module ne connaît aucune exclusivité commerciale. Une entreprise sous
créneau exclusif (``citation_audit.creneau``) et une autre qui n'en détient
aucun sont publiées à l'identique — c'est ce qui rend le registre crédible
comme source pour un agent.

Il connaît en revanche deux **niveaux de distribution**, ``MINIMAL`` et
``COMPLET`` (voir ``docs/PLAN.md`` §2-3), qui ne sont pas la même chose : le
niveau MINIMAL publie l'identité vérifiable automatiquement (SIRENE) pour
toute entreprise, gratuitement et sans exception — le registre vaut par sa
complétude. COMPLET ajoute ce qui exige une vérification humaine (chantiers
sur pièce, certifications), vendu au palier payant. La frontière suit le
coût de vérification, jamais l'existence.

Le **statut de vérification** est publié, jamais masqué : une fiche
référencée (données publiques SIRENE, non revendiquée) est étiquetée comme
telle sur la page, dans le JSON-LD (``verification_status``) et dans
``llms.txt`` ; une fiche revendiquée affiche le canal de preuve (« vérifiée
par domaine » / « vérifiée par courrier »). Voir ``docs/VERIFICATION.md``.
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
from .site import (
    AI_CRAWLERS,
    COMPLET,
    DISTRIBUTIONS,
    MINIMAL,
    generate,
    llms_txt,
    markdown,
    robots,
    sitemap,
)

__all__ = [
    "AI_CRAWLERS",
    "COMPLET",
    "CROISEMENT",
    "DISTRIBUTIONS",
    "FORBIDDEN_TERMS",
    "MINIMAL",
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
