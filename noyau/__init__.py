"""Le Noyau: la représentation canonique et vérifiée d'une entreprise.

C'est l'actif du projet. Le rendu (site, flux, fiche) est une commodité de
distribution; ce qui ne se copie pas, c'est la mémoire accumulée et vérifiée de
ce que l'entreprise a réellement fait.

Verticale de départ: la rénovation d'habitat. Trois impératifs de donnée y
gouvernent la conception, et chacun a son module:

* la preuve par l'hyper-local  -> ``territoire`` et ``chantier``
* le budget constaté           -> ``budget``
* les attributs d'autorité     -> ``noyau``, qui réutilise le modèle
  d'affirmation vérifiée du Dossier de Vérité
"""

from .budget import BudgetBloque, BudgetConstate, MIN_CHANTIERS, aggregate
from .chantier import NATURES, TYPOLOGIES, Chantier, Nature, TerritoirePreuve
from .noyau import (
    MIN_CHANTIERS_TERRITOIRE,
    Assertion,
    Manque,
    Noyau,
)
from .territoire import COMMUNE, METROPOLE, QUARTIER, Referentiel, Territoire

__all__ = [
    "Assertion",
    "BudgetBloque",
    "BudgetConstate",
    "COMMUNE",
    "Chantier",
    "MIN_CHANTIERS",
    "MIN_CHANTIERS_TERRITOIRE",
    "METROPOLE",
    "Manque",
    "NATURES",
    "Nature",
    "Noyau",
    "QUARTIER",
    "Referentiel",
    "Territoire",
    "TerritoirePreuve",
    "TYPOLOGIES",
    "aggregate",
]

__version__ = "0.1.0"
