"""Le protocole: des seuils écrits avant le premier entretien, et scellés.

Le risque n'est pas de choisir un mauvais seuil, c'est de le déplacer en cours
de route pour qu'il colle à ce qu'on a envie de trouver dans dix conversations
sympathiques. La parade n'est pas la bonne foi, c'est la mécanique: le
protocole est haché, et `terrain.decision.decide` refuse d'agréger un
entretien mené sous un hash différent de celui qu'il attend. Un seuil modifié
casse la comparaison au lieu de s'y glisser sans bruit.

Ce fichier ne contient qu'une seule instance verrouillée, `PROTOCOLE_V2`. Un
changement de seuil pour la campagne en cours se fait en écrivant une nouvelle
version ici, jamais en éditant les valeurs de celle qui a déjà servi.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class Protocole:
    """Seuils de décision pour une campagne de dix entretiens.

    H1 (représentation) et H2 (capacité d'action) sont jugées séparément,
    chacune sur trois niveaux de preuve croissants:

    * **niveau 1** — un fait observé (l'audit ne cite pas l'entreprise;
      un dimanche soir, une demande arrive et personne n'y répond) ;
    * **niveau 2** — le professionnel reconnaît que c'est important, à
      l'oral (surprise ou inquiétude authentique face à l'audit; un « oui »
      à l'échange proposé) ;
    * **niveau 3** — un engagement comportemental, révélé et non déclaré
      (les factures sont réellement envoyées sous 7 jours).

    Seul le niveau 3 compte comme signal commercial. Les niveaux 1 et 2 sont
    conservés parce qu'un niveau 3 sans les deux précédents serait suspect
    (un engagement sans qu'aucun fait ni aucune reconnaissance ne le motive),
    pas parce qu'ils suffisent à eux seuls.
    """

    version: str
    vertical: str
    zone: str
    n_entreprises: int = 10
    h1_niveau1_min: int = 6
    h1_niveau2_min: int = 5
    h1_niveau3_min: int = 3
    h2_niveau1_min: int = 6
    h2_niveau2_min: int = 5
    h2_niveau3_min: int = 3

    def hash(self) -> str:
        """Empreinte stable de tout ce qui définit ce protocole.

        Deux protocoles aux mêmes seuils mais versionnés différemment ont des
        hash différents: `version` fait partie de la signature exprès, pour
        qu'une campagne relancée sous un nom explicite ne se confonde jamais
        silencieusement avec la précédente.
        """
        signature = json.dumps(asdict(self), sort_keys=True, ensure_ascii=False)
        return hashlib.sha1(signature.encode("utf-8")).hexdigest()[:12]


# Le protocole verrouillé pour la première campagne: rénovation d'habitat,
# Bordeaux Métropole, un seul secteur pour ne pas ajouter une variable à un
# test qui en a déjà deux (H1 et H2).
PROTOCOLE_V2 = Protocole(
    version="v2",
    vertical="renovation",
    zone="bordeaux-metropole",
)
