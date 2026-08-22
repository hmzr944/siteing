"""Le test terrain: l'instrument de validation, pas le produit.

Le protocole documenté dans ``docs/TERRAIN.md`` existe ici en code plutôt
qu'en prose, pour une seule raison: un seuil écrit dans un document peut se
déplacer discrètement d'une relecture à l'autre, un seuil hashé ne peut pas.

``seuils.PROTOCOLE_V2`` fixe les seuils de décision pour H1 (représentation)
et H2 (capacité d'action), chacune sur trois niveaux de preuve. ``entretien``
donne la forme d'un entretien consigné. ``decision.decide`` agrège une liste
d'entretiens et refuse ceux qui ne portent pas le hash du protocole attendu.
"""

from .decision import (
    ABANDONNER,
    ECHANTILLON_INSUFFISANT,
    EXPLORER_ACTION,
    EXPLORER_REPRESENTATION,
    TESTER_ENSEMBLE,
    VERDICT_LABELS,
    Verdict,
    decide,
)
from .entretien import (
    ConstatH1,
    Entretien,
    EntretienH1,
    EntretienH2,
    EvenementsH2,
)
from .seuils import PROTOCOLE_V2, Protocole

__all__ = [
    "ABANDONNER",
    "ECHANTILLON_INSUFFISANT",
    "EXPLORER_ACTION",
    "EXPLORER_REPRESENTATION",
    "TESTER_ENSEMBLE",
    "VERDICT_LABELS",
    "ConstatH1",
    "Entretien",
    "EntretienH1",
    "EntretienH2",
    "EvenementsH2",
    "PROTOCOLE_V2",
    "Protocole",
    "Verdict",
    "decide",
]

__version__ = "0.1.0"
