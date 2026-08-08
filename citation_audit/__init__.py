"""Source Primaire — moteur de mesure de la Part de Citation.

Le marché de la présence en ligne a perdu sa rareté: fabriquer un site ne vaut
plus rien. Ce qui reste rare, c'est d'être *cité* par les moteurs qui répondent
désormais à la place des moteurs de recherche. Ce paquet mesure cette citation,
de façon reproductible et opposable, et produit l'Audit d'Invisibilité qui sert
à la fois de diagnostic client et d'outil d'acquisition.

Voir ``docs/METHODE.md`` pour la méthodologie et ses limites.
"""

from .creneau import Grant, Registry, SlotConflict
from .dossier import Claim, Dossier, Evidence
from .market import Economics, Entity, Market, Prompt
from .providers import EngineResponse, build as build_provider
from .publish import to_jsonld, to_manifest, write_bundle
from .report import to_html, to_text
from .score import AuditResult, compute
from .verite import to_document, to_html as verite_html

__all__ = [
    "AuditResult",
    "Claim",
    "Dossier",
    "Economics",
    "EngineResponse",
    "Entity",
    "Evidence",
    "Grant",
    "Market",
    "Prompt",
    "Registry",
    "SlotConflict",
    "build_provider",
    "compute",
    "to_document",
    "to_html",
    "to_jsonld",
    "to_manifest",
    "to_text",
    "verite_html",
    "write_bundle",
]

__version__ = "0.1.0"
