"""Le verdict: cinq issues possibles, aucune laissée à l'interprétation.

`decide()` refuse d'agréger des entretiens menés sous des protocoles
différents — un seuil changé en cours de campagne casse le calcul plutôt que
de s'y glisser sans bruit. C'est la mécanique qui rend « fixé avant le premier
entretien » vérifiable a posteriori, et pas seulement une intention déclarée.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .entretien import Entretien
from .seuils import PROTOCOLE_V2, Protocole

EXPLORER_REPRESENTATION = "explorer_representation"
EXPLORER_ACTION = "explorer_action"
TESTER_ENSEMBLE = "tester_ensemble"
ABANDONNER = "abandonner"
ECHANTILLON_INSUFFISANT = "echantillon_insuffisant"

VERDICT_LABELS: dict[str, str] = {
    EXPLORER_REPRESENTATION: (
        "H1 seule confirmée — creuser la représentation (Noyau + Surfaces), "
        "la capacité d'action reste secondaire."
    ),
    EXPLORER_ACTION: (
        "H2 seule confirmée — creuser la capacité d'action (réponse rapide), "
        "revoir le cœur du produit avant de continuer sur la citation seule."
    ),
    TESTER_ENSEMBLE: (
        "H1 et H2 confirmées — le repositionnement « source de vérité + "
        "capacité d'action » est justifié. On construit dessus."
    ),
    ABANDONNER: (
        "Ni H1 ni H2 confirmée — le métier ou la ville ne valide pas la "
        "thèse. Changer de secteur, ou remettre en cause la thèse elle-même."
    ),
    ECHANTILLON_INSUFFISANT: (
        "Moins d'entretiens que prévu par le protocole — aucune décision "
        "n'est prise sur un échantillon incomplet."
    ),
}

# Marge de vigilance: un compte à une unité du seuil est signalé, pour qu'une
# décision qui bascule sur un seul entretien de plus ou de moins ne soit
# jamais lue comme un verdict tranché.
ZONE_GRISE = 1


@dataclass(frozen=True)
class Verdict:
    n: int
    h1_niveau1: int
    h1_niveau2: int
    h1_niveau3: int
    h2_niveau1: int
    h2_niveau2: int
    h2_niveau3: int
    h1_go: bool
    h2_go: bool
    matrice: str
    warnings: list[str] = field(default_factory=list)

    @property
    def label(self) -> str:
        return VERDICT_LABELS[self.matrice]

    def to_text(self) -> str:
        lines = [
            f"VERDICT — {self.n} entretien(s)",
            "",
            f"H1 (représentation)  niveau1 {self.h1_niveau1:>2}  "
            f"niveau2 {self.h1_niveau2:>2}  niveau3 {self.h1_niveau3:>2}  "
            f"{'GO' if self.h1_go else 'non'}",
            f"H2 (capacité d'action)  niveau1 {self.h2_niveau1:>2}  "
            f"niveau2 {self.h2_niveau2:>2}  niveau3 {self.h2_niveau3:>2}  "
            f"{'GO' if self.h2_go else 'non'}",
            "",
            self.label,
        ]
        if self.warnings:
            lines += [""] + [f"! {w}" for w in self.warnings]
        return "\n".join(lines)


def decide(entretiens: list[Entretien], protocole: Protocole = PROTOCOLE_V2) -> Verdict:
    """Applique le protocole verrouillé à une liste d'entretiens.

    Refuse (lève ValueError) si un entretien porte le hash d'un autre
    protocole: agréger silencieusement des entretiens menés sous des seuils
    différents produirait un verdict qui n'a jamais été pré-enregistré.
    """
    expected_hash = protocole.hash()
    for entretien in entretiens:
        if entretien.protocole_hash != expected_hash:
            raise ValueError(
                f"entretien {entretien.entreprise_id!r} mené sous le protocole "
                f"{entretien.protocole_hash!r}, attendu {expected_hash!r} "
                f"({protocole.version}): les seuils ont changé, ce lot ne "
                "s'agrège pas avec les autres"
            )

    n = len(entretiens)
    h1_niveau1 = sum(1 for e in entretiens if e.h1.niveau1)
    h1_niveau2 = sum(1 for e in entretiens if e.h1.niveau2)
    h1_niveau3 = sum(1 for e in entretiens if e.h1.niveau3)
    h2_niveau1 = sum(1 for e in entretiens if e.h2.niveau1)
    h2_niveau2 = sum(1 for e in entretiens if e.h2.niveau2)
    h2_niveau3 = sum(1 for e in entretiens if e.h2.niveau3)

    h1_go = (
        h1_niveau1 >= protocole.h1_niveau1_min
        and h1_niveau2 >= protocole.h1_niveau2_min
        and h1_niveau3 >= protocole.h1_niveau3_min
    )
    h2_go = (
        h2_niveau1 >= protocole.h2_niveau1_min
        and h2_niveau2 >= protocole.h2_niveau2_min
        and h2_niveau3 >= protocole.h2_niveau3_min
    )

    warnings: list[str] = []
    for label, count, seuil in (
        ("H1 niveau 3", h1_niveau3, protocole.h1_niveau3_min),
        ("H2 niveau 3", h2_niveau3, protocole.h2_niveau3_min),
    ):
        if abs(count - seuil) <= ZONE_GRISE and count != seuil:
            continue  # déjà tranché dans un sens ou l'autre, pas au seuil
        if count == seuil:
            warnings.append(
                f"{label} est exactement au seuil ({count}/{seuil}): zone grise, "
                "un entretien de plus ou de moins change le verdict."
            )

    if n < protocole.n_entreprises:
        warnings.append(
            f"{n} entretien(s) sur {protocole.n_entreprises} prévus: échantillon "
            "incomplet."
        )
        matrice = ECHANTILLON_INSUFFISANT
    elif h1_go and h2_go:
        matrice = TESTER_ENSEMBLE
    elif h1_go and not h2_go:
        matrice = EXPLORER_REPRESENTATION
    elif h2_go and not h1_go:
        matrice = EXPLORER_ACTION
    else:
        matrice = ABANDONNER

    return Verdict(
        n=n,
        h1_niveau1=h1_niveau1,
        h1_niveau2=h1_niveau2,
        h1_niveau3=h1_niveau3,
        h2_niveau1=h2_niveau1,
        h2_niveau2=h2_niveau2,
        h2_niveau3=h2_niveau3,
        h1_go=h1_go,
        h2_go=h2_go,
        matrice=matrice,
        warnings=warnings,
    )
