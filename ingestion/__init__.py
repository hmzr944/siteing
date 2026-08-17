"""L'ingestion: de la parole spontanée au candidat de chantier.

Réponse à la seule question difficile de ce paquet, à savoir comment respecter un
vocabulaire contrôlé avec un modèle de langue: **on ne le lui demande pas.**

Le modèle produit des fragments verbatim typés. Des résolveurs déterministes,
testables sans réseau, les traduisent en codes et refusent l'ambigu. Ce qui
manque devient une question, classée par ce qu'elle débloque. Un fragment qui
n'apparaît pas mot pour mot dans le message d'origine est jeté avant toute
résolution, ce qui rend une hallucination inoffensive.

Rien n'est jamais écrit directement dans le Noyau: on produit un candidat, avec
la provenance de chaque champ et la phrase d'origine.
"""

from .extracteurs import (
    HeuristicExtractor,
    LLMExtractor,
    verbatim_only,
)
from .extraction import (
    BLOCKING,
    FIELD_PRIORITY,
    SPAN_TYPES,
    Candidate,
    Question,
    Span,
    build_candidate,
    resolve_territoire,
    summarise,
)
from .lexique import (
    Resolved,
    parse_date,
    parse_duree,
    parse_montant,
    parse_nature,
    parse_surface,
)

__all__ = [
    "BLOCKING",
    "Candidate",
    "FIELD_PRIORITY",
    "HeuristicExtractor",
    "LLMExtractor",
    "Question",
    "Resolved",
    "SPAN_TYPES",
    "Span",
    "build_candidate",
    "parse_date",
    "parse_duree",
    "parse_montant",
    "parse_nature",
    "parse_surface",
    "resolve_territoire",
    "summarise",
    "verbatim_only",
]
