"""Allocation des créneaux d'accompagnement — pas le registre de visibilité.

À ne pas confondre avec ce que ``noyau``/``surfaces`` publient : ce module ne
touche jamais à ce qu'une IA lit sur une entreprise. Le registre (le Noyau, ses
pages, son JSON-LD) est **la même source pour tout le monde**, vérifiée ou
non, payante ou non — un registre qui distinguerait ses clients payants
cesserait d'être une source fiable pour devenir une régie publicitaire.

Ce que ce module gère est différent : sur quelle entreprise, par catégorie et
par zone, l'équipe concentre son travail d'accompagnement (fiche enrichie,
suivi rapproché, monitoring approfondi) — le modèle classique d'une agence de
génération de leads qui ne travaille jamais pour deux concurrents directs à la
fois. Une exclusivité de service promise oralement et tenue dans un tableur
finit toujours promise deux fois ; elle doit donc être une **contrainte du
système**, comme le reste.

Le registre d'allocation refuse tout octroi qui entrerait en conflit. Il
n'avertit pas: il refuse.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from .market import slug

# Paliers d'accompagnement. Seul le palier haut réserve l'exclusivité du
# service sur ce créneau — jamais l'accès au registre, qui reste ouvert à
# toute entreprise vérifiée indépendamment de ce module.
SOCLE = "socle"
POSITION = "position"
EXCLUSIF = "exclusif"

EXCLUSIVE_TIERS = frozenset({EXCLUSIF})
TIER_LABELS = {SOCLE: "Socle", POSITION: "Position", EXCLUSIF: "Exclusif"}

# Nombre maximum d'entreprises accompagnées à la fois sur un même créneau en
# dessous du palier exclusif. Au-delà, le travail d'accompagnement se dilue
# entre trop de clients pour rester ce qu'il prétend être.
MAX_SHARED_HOLDERS = 3


class SlotConflict(Exception):
    """Octroi refusé: le créneau est déjà pris, ou saturé."""


@dataclass(frozen=True)
class Grant:
    category: str
    zone: str
    entity_id: str
    tier: str
    granted_on: date
    expires_on: date

    @property
    def slot_key(self) -> str:
        return f"{slug(self.category).replace(' ', '-')}/{slug(self.zone).replace(' ', '-')}"

    @property
    def is_exclusive(self) -> bool:
        return self.tier in EXCLUSIVE_TIERS

    def is_active(self, today: date | None = None) -> bool:
        today = today or date.today()
        return self.granted_on <= today <= self.expires_on

    def to_dict(self) -> dict:
        return {
            "category": self.category,
            "zone": self.zone,
            "entity_id": self.entity_id,
            "tier": self.tier,
            "granted_on": self.granted_on.isoformat(),
            "expires_on": self.expires_on.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Grant":
        if data["tier"] not in TIER_LABELS:
            raise ValueError(f"palier inconnu: {data['tier']!r}")
        granted_on = date.fromisoformat(data["granted_on"])
        expires_on = date.fromisoformat(data["expires_on"])
        if expires_on <= granted_on:
            raise ValueError("un créneau doit expirer après avoir été octroyé")
        return cls(
            category=data["category"],
            zone=data["zone"],
            entity_id=data["entity_id"],
            tier=data["tier"],
            granted_on=granted_on,
            expires_on=expires_on,
        )


@dataclass
class Registry:
    grants: list[Grant]

    # -- lecture -------------------------------------------------------------

    def active(self, today: date | None = None) -> list[Grant]:
        return [g for g in self.grants if g.is_active(today)]

    def holders(self, category: str, zone: str, today: date | None = None) -> list[Grant]:
        key = Grant(category, zone, "", SOCLE, date.min, date.max).slot_key
        return [g for g in self.active(today) if g.slot_key == key]

    def exclusive_holder(
        self, category: str, zone: str, today: date | None = None
    ) -> Grant | None:
        return next(
            (g for g in self.holders(category, zone, today) if g.is_exclusive), None
        )

    def is_available(
        self, category: str, zone: str, tier: str, today: date | None = None
    ) -> bool:
        try:
            self._check(category, zone, "candidat", tier, today)
        except SlotConflict:
            return False
        return True

    def slots_for(self, entity_id: str, today: date | None = None) -> list[Grant]:
        return [g for g in self.active(today) if g.entity_id == entity_id]

    # -- écriture ------------------------------------------------------------

    def _check(
        self, category: str, zone: str, entity_id: str, tier: str, today: date | None
    ) -> None:
        holders = self.holders(category, zone, today)

        existing_exclusive = next((g for g in holders if g.is_exclusive), None)
        if existing_exclusive and existing_exclusive.entity_id != entity_id:
            raise SlotConflict(
                f"créneau {category} / {zone} détenu en exclusivité par "
                f"{existing_exclusive.entity_id} jusqu'au {existing_exclusive.expires_on}"
            )

        if any(g.entity_id == entity_id for g in holders):
            raise SlotConflict(
                f"{entity_id} détient déjà un créneau actif sur {category} / {zone}"
            )

        if tier in EXCLUSIVE_TIERS and holders:
            others = ", ".join(sorted(g.entity_id for g in holders))
            raise SlotConflict(
                f"exclusivité impossible sur {category} / {zone}: déjà partagé par {others}"
            )

        if tier not in EXCLUSIVE_TIERS and len(holders) >= MAX_SHARED_HOLDERS:
            raise SlotConflict(
                f"créneau {category} / {zone} saturé "
                f"({len(holders)}/{MAX_SHARED_HOLDERS} titulaires)"
            )

    def grant(
        self,
        category: str,
        zone: str,
        entity_id: str,
        tier: str,
        granted_on: date,
        expires_on: date,
        today: date | None = None,
    ) -> Grant:
        """Octroie un créneau, ou lève ``SlotConflict``. Jamais d'avertissement."""
        if tier not in TIER_LABELS:
            raise ValueError(f"palier inconnu: {tier!r}")
        self._check(category, zone, entity_id, tier, today or granted_on)
        grant = Grant.from_dict(
            {
                "category": category,
                "zone": zone,
                "entity_id": entity_id,
                "tier": tier,
                "granted_on": granted_on.isoformat(),
                "expires_on": expires_on.isoformat(),
            }
        )
        self.grants.append(grant)
        return grant

    def release(self, category: str, zone: str, entity_id: str, on: date) -> int:
        """Met fin aux créneaux d'une entité à une date donnée.

        On ne supprime rien: un créneau libéré garde sa trace, parce que savoir
        qui détenait quoi et jusqu'à quand fait partie du registre.
        """
        key = Grant(category, zone, "", SOCLE, date.min, date.max).slot_key
        released = 0
        for index, grant in enumerate(self.grants):
            if (
                grant.slot_key == key
                and grant.entity_id == entity_id
                and grant.expires_on > on
            ):
                self.grants[index] = Grant(
                    category=grant.category,
                    zone=grant.zone,
                    entity_id=grant.entity_id,
                    tier=grant.tier,
                    granted_on=grant.granted_on,
                    expires_on=on,
                )
                released += 1
        return released

    # -- persistance ---------------------------------------------------------

    @classmethod
    def load(cls, path: str | Path) -> "Registry":
        target = Path(path)
        if not target.exists():
            return cls(grants=[])
        payload = json.loads(target.read_text(encoding="utf-8"))
        return cls(grants=[Grant.from_dict(raw) for raw in payload.get("grants", ())])

    def save(self, path: str | Path) -> None:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        payload = {"grants": [g.to_dict() for g in self.grants]}
        target.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
