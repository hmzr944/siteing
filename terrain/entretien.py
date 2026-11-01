"""Un entretien: ce qui a été constaté, jamais ce qu'on en pense.

Chaque entretien se range dans les deux hypothèses, séparément, et chacune
sur ses trois niveaux de preuve (voir `terrain.seuils.Protocole`). La forme de
ces classes est délibérément pauvre en champs libres: le protocole demande une
grille de consignation comparable en un coup d'œil, pas dix comptes rendus
narratifs à relire.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from .seuils import PROTOCOLE_V2

SOURCES_H1 = ("citation_audit", "observation_directe")


@dataclass(frozen=True)
class ConstatH1:
    """Un fait relevé pendant l'audit en direct, pas une opinion sur lui."""

    description: str
    source: str  # "citation_audit" | "observation_directe"
    juge_important: bool

    def __post_init__(self) -> None:
        if self.source not in SOURCES_H1:
            raise ValueError(
                f"source de constat inconnue: {self.source!r} "
                f"(attendu: {', '.join(SOURCES_H1)})"
            )

    def to_dict(self) -> dict:
        return {
            "description": self.description,
            "source": self.source,
            "juge_important": self.juge_important,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ConstatH1":
        return cls(
            description=data["description"],
            source=data["source"],
            juge_important=bool(data["juge_important"]),
        )


@dataclass
class EntretienH1:
    """H1 — représentation. Trois niveaux de preuve, jugés indépendamment.

    Niveau 1: au moins un constat factuel (absence ou mauvaise citation).
    Niveau 2: au moins un constat jugé important par l'entreprise elle-même.
    Niveau 3: l'échange proposé (dossier construit contre 3 factures + 20
    minutes) a été réellement honoré, pas seulement accepté à l'oral.
    """

    constats: list[ConstatH1] = field(default_factory=list)
    audit_json: str | None = None
    presence_rate: float | None = None
    action_engagee: str | None = None
    action_realisee_le: date | None = None

    @property
    def niveau1(self) -> bool:
        return len(self.constats) > 0

    @property
    def niveau2(self) -> bool:
        return any(c.juge_important for c in self.constats)

    @property
    def niveau3(self) -> bool:
        return self.action_realisee_le is not None

    def to_dict(self) -> dict:
        return {
            "constats": [c.to_dict() for c in self.constats],
            "audit_json": self.audit_json,
            "presence_rate": self.presence_rate,
            "action_engagee": self.action_engagee,
            "action_realisee_le": (
                self.action_realisee_le.isoformat() if self.action_realisee_le else None
            ),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "EntretienH1":
        return cls(
            constats=[ConstatH1.from_dict(c) for c in data.get("constats", ())],
            audit_json=data.get("audit_json"),
            presence_rate=data.get("presence_rate"),
            action_engagee=data.get("action_engagee"),
            action_realisee_le=(
                date.fromisoformat(data["action_realisee_le"])
                if data.get("action_realisee_le")
                else None
            ),
        )


@dataclass(frozen=True)
class EvenementsH2:
    """Décompte des demandes entrantes sur une période, pas une estimation.

    Le protocole demande de compter (ouvrir le téléphone, dérouler les 7
    derniers jours) plutôt que d'évaluer. Les compartiments de délai de
    réponse doivent rester cohérents avec le total reçu: c'est vérifié à la
    construction, pour qu'une saisie incohérente casse plutôt que de fausser
    silencieusement le taux calculé.
    """

    periode_jours: int
    recues: int
    repondues_moins_5min: int
    repondues_5_60min: int
    repondues_plus_1h: int
    sans_reponse: int
    necessitant_devis: int
    qualifiees: int

    def __post_init__(self) -> None:
        repondues = (
            self.repondues_moins_5min + self.repondues_5_60min + self.repondues_plus_1h
        )
        if repondues + self.sans_reponse > self.recues:
            raise ValueError(
                "incohérence: répondues "
                f"({repondues}) + sans réponse ({self.sans_reponse}) dépasse "
                f"les demandes reçues ({self.recues})"
            )

    @property
    def taux_sans_reponse(self) -> float:
        return self.sans_reponse / self.recues if self.recues else 0.0

    @property
    def taux_reponse_lente_ou_absente(self) -> float:
        """Répondues après plus d'une heure, ou jamais: la fenêtre où une
        demande de rénovation part probablement voir ailleurs."""
        lente_ou_absente = self.repondues_plus_1h + self.sans_reponse
        return lente_ou_absente / self.recues if self.recues else 0.0

    def to_dict(self) -> dict:
        return {
            "periode_jours": self.periode_jours,
            "recues": self.recues,
            "repondues_moins_5min": self.repondues_moins_5min,
            "repondues_5_60min": self.repondues_5_60min,
            "repondues_plus_1h": self.repondues_plus_1h,
            "sans_reponse": self.sans_reponse,
            "necessitant_devis": self.necessitant_devis,
            "qualifiees": self.qualifiees,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "EvenementsH2":
        return cls(
            periode_jours=int(data["periode_jours"]),
            recues=int(data["recues"]),
            repondues_moins_5min=int(data["repondues_moins_5min"]),
            repondues_5_60min=int(data["repondues_5_60min"]),
            repondues_plus_1h=int(data["repondues_plus_1h"]),
            sans_reponse=int(data["sans_reponse"]),
            necessitant_devis=int(data["necessitant_devis"]),
            qualifiees=int(data["qualifiees"]),
        )


@dataclass
class EntretienH2:
    """H2 — capacité d'action. Mêmes trois niveaux, sur la réponse aux demandes.

    Niveau 1: un décompte chiffré montre un retard ou une absence de réponse
    significative, ou un exemple concret et daté de chantier perdu pour ce
    motif (`type_repetitif_identifie` sert cet exemple textuel).
    Niveau 2: le retard concerne un type de demande répétitif et identifié
    (pas un incident isolé qu'on ne reverra pas).
    Niveau 3: l'échange a été réellement honoré.
    """

    evenements: EvenementsH2 | None = None
    type_repetitif_identifie: str | None = None
    action_engagee: str | None = None
    action_realisee_le: date | None = None

    # Au-delà de ce taux, un retard ou silence n'est plus un incident mais un
    # motif de perte de demande significatif — seuil de lecture du niveau 1,
    # distinct des seuils d'agrégation du protocole (qui portent sur le
    # nombre d'entreprises, pas sur un taux individuel).
    SEUIL_RETARD_SIGNIFICATIF = 0.20

    @property
    def niveau1(self) -> bool:
        if self.evenements is not None:
            if self.evenements.taux_reponse_lente_ou_absente >= self.SEUIL_RETARD_SIGNIFICATIF:
                return True
        return self.type_repetitif_identifie is not None

    @property
    def niveau2(self) -> bool:
        return self.type_repetitif_identifie is not None

    @property
    def niveau3(self) -> bool:
        return self.action_realisee_le is not None

    def to_dict(self) -> dict:
        return {
            "evenements": self.evenements.to_dict() if self.evenements else None,
            "type_repetitif_identifie": self.type_repetitif_identifie,
            "action_engagee": self.action_engagee,
            "action_realisee_le": (
                self.action_realisee_le.isoformat() if self.action_realisee_le else None
            ),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "EntretienH2":
        raw_evenements = data.get("evenements")
        return cls(
            evenements=EvenementsH2.from_dict(raw_evenements) if raw_evenements else None,
            type_repetitif_identifie=data.get("type_repetitif_identifie"),
            action_engagee=data.get("action_engagee"),
            action_realisee_le=(
                date.fromisoformat(data["action_realisee_le"])
                if data.get("action_realisee_le")
                else None
            ),
        )


@dataclass
class Entretien:
    """Un entretien complet, daté et rattaché au protocole sous lequel il a
    été mené. `.nouveau()` est le seul chemin qui tamponne le hash courant:
    un entretien reconstruit à la main doit déclarer explicitement le sien."""

    entreprise_id: str
    entreprise_nom: str
    date_entretien: date
    protocole_hash: str
    h1: EntretienH1 = field(default_factory=EntretienH1)
    h2: EntretienH2 = field(default_factory=EntretienH2)
    notes: str = ""

    @classmethod
    def nouveau(
        cls,
        entreprise_id: str,
        entreprise_nom: str,
        date_entretien: date,
        notes: str = "",
    ) -> "Entretien":
        return cls(
            entreprise_id=entreprise_id,
            entreprise_nom=entreprise_nom,
            date_entretien=date_entretien,
            protocole_hash=PROTOCOLE_V2.hash(),
            notes=notes,
        )

    def to_dict(self) -> dict:
        return {
            "entreprise_id": self.entreprise_id,
            "entreprise_nom": self.entreprise_nom,
            "date_entretien": self.date_entretien.isoformat(),
            "protocole_hash": self.protocole_hash,
            "h1": self.h1.to_dict(),
            "h2": self.h2.to_dict(),
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Entretien":
        return cls(
            entreprise_id=data["entreprise_id"],
            entreprise_nom=data["entreprise_nom"],
            date_entretien=date.fromisoformat(data["date_entretien"]),
            protocole_hash=data["protocole_hash"],
            h1=EntretienH1.from_dict(data.get("h1", {})),
            h2=EntretienH2.from_dict(data.get("h2", {})),
            notes=data.get("notes", ""),
        )

    def save(self, path: str | Path) -> None:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(self.to_dict(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    @classmethod
    def load(cls, path: str | Path) -> "Entretien":
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))
