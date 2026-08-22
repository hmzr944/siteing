"""Le Noyau: la représentation canonique et vérifiée d'une entreprise.

C'est l'actif du projet. Le rendu (site, flux, fiche) est une commodité de
distribution; ce qui ne se copie pas, c'est la mémoire accumulée et vérifiée de
ce que l'entreprise a réellement fait.

Conçu sur la rénovation d'habitat, mais pas spécifique à elle: seul le
vocabulaire des natures de prestation dépendait du métier, et il est
externalisé dans ``metiers/`` (un fichier JSON par métier, voir
``catalogue``) — le même Noyau sert n'importe quel métier qui documente des
interventions datées, localisées et facturées. Trois impératifs de donnée
gouvernent la conception, et chacun a son module:

* la preuve par l'hyper-local  -> ``territoire`` et ``chantier``
* le vocabulaire du métier      -> ``catalogue``
* le budget constaté           -> ``budget``
* les attributs d'autorité     -> ``noyau``, qui réutilise le modèle
  d'affirmation vérifiée du Dossier de Vérité
"""

from .budget import BudgetBloque, BudgetConstate, MIN_CHANTIERS, aggregate
from .catalogue import Catalogue
from .chantier import NATURE_KEYWORDS, NATURES, TYPOLOGIES, Chantier, Nature, TerritoirePreuve
from .noyau import (
    MIN_CHANTIERS_TERRITOIRE,
    Assertion,
    Manque,
    Noyau,
)
from .territoire import COMMUNE, METROPOLE, QUARTIER, Referentiel, Territoire
from .verification import (
    IDENTITY_CONTROL_KEY,
    IDENTITY_EXISTENCE_KEY,
    NON_REVENDIQUEE,
    STATUTS_VERIFIES,
    VERIFIEE_COURRIER,
    VERIFIEE_DOMAINE,
    ControlCode,
    SireneEtablissement,
    VerificationRefusee,
    by_name,
    by_siren,
    claim_existence,
    confirm_code,
    issue_code_courrier,
    issue_code_domaine,
)

__all__ = [
    "Assertion",
    "BudgetBloque",
    "BudgetConstate",
    "COMMUNE",
    "Catalogue",
    "Chantier",
    "ControlCode",
    "IDENTITY_CONTROL_KEY",
    "IDENTITY_EXISTENCE_KEY",
    "MIN_CHANTIERS",
    "MIN_CHANTIERS_TERRITOIRE",
    "METROPOLE",
    "Manque",
    "NATURE_KEYWORDS",
    "NATURES",
    "NON_REVENDIQUEE",
    "Nature",
    "Noyau",
    "QUARTIER",
    "Referentiel",
    "STATUTS_VERIFIES",
    "SireneEtablissement",
    "Territoire",
    "TerritoirePreuve",
    "TYPOLOGIES",
    "VERIFIEE_COURRIER",
    "VERIFIEE_DOMAINE",
    "VerificationRefusee",
    "aggregate",
    "by_name",
    "by_siren",
    "claim_existence",
    "confirm_code",
    "issue_code_courrier",
    "issue_code_domaine",
]

__version__ = "0.1.0"
