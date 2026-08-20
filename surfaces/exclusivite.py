"""Le marqueur d'exclusivité: la seule différence visible entre deux Noyaux.

Le Noyau se publie sans condition — n'importe quelle entreprise peut être
représentée, vérifiée, citée, quel que soit son métier (voir
``noyau.catalogue``) ou si elle détient le moindre créneau. C'est la couche
universelle, celle qui répond à « aider un maximum de personnes ».

L'exclusivité est une couche commerciale séparée, au-dessus, jamais une
condition de publication. Un Noyau sans créneau exclusif reste publié
normalement, simplement sans la mention — il ne peut jamais prétendre à une
exclusivité qu'il ne détient pas, exactement comme un budget non documenté ne
peut jamais être publié comme constaté. Le registre (``citation_audit.creneau``)
reste la seule source de vérité: ce module ne fait qu'aller lui demander, pour
un métier et une zone donnés, si le Noyau interrogé est le titulaire exclusif
actif — jamais deviné, jamais mis en cache.
"""

from __future__ import annotations

from datetime import date

from citation_audit.creneau import Grant, Registry


def exclusive_grant(
    category: str, zone: str, registry: Registry | None, today: date | None = None
) -> Grant | None:
    """Le créneau exclusif actif sur ce métier et cette zone, s'il existe.

    ``registry`` est optionnel: générer des surfaces sans registre reste un
    usage valide (démonstration, marché sans enjeu commercial), il ne publie
    simplement jamais de mention d'exclusivité.
    """
    if registry is None:
        return None
    return registry.exclusive_holder(category, zone, today)


def is_exclusive_holder(
    entity_id: str,
    category: str,
    zone: str,
    registry: Registry | None,
    today: date | None = None,
) -> bool:
    grant = exclusive_grant(category, zone, registry, today)
    return grant is not None and grant.entity_id == entity_id
