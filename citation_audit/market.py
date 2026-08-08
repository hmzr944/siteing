"""Définition d'un marché et génération du panier de prompts d'achat.

Principe central: le panier est **déterministe**. Pour une définition de marché
donnée, les mêmes prompts sont produits, dans le même ordre, avec les mêmes
identifiants stables. C'est la condition pour qu'une mesure soit comparable d'un
mois sur l'autre — un audit dont le panel bouge à chaque exécution ne mesure
rien et n'est pas opposable au client.

Toute modification de la définition du marché change `basket_version`: deux
rapports de versions différentes ne sont pas comparables, et le rapport le dit.
"""

from __future__ import annotations

import hashlib
import json
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

# Familles de prompts, avec leur poids commercial. Un prompt de comparaison
# ("le meilleur X") ou transactionnel ("je veux un devis") pèse plus lourd
# qu'une découverte générique: l'intention d'achat y est déjà formée.
FAMILY_WEIGHTS: dict[str, float] = {
    "decouverte": 1.0,
    "comparaison": 1.2,
    "contrainte": 1.1,
    "probleme": 1.0,
    "transactionnel": 1.3,
    "verification": 0.8,
}

# Nombre maximum de prompts retenus par famille. Le panier complet est le
# produit cartésien des gabarits et des modificateurs; on en tire un
# sous-ensemble stable pour garder un coût d'exécution borné.
FAMILY_CAPS: dict[str, int] = {
    "decouverte": 8,
    "comparaison": 6,
    "contrainte": 8,
    "probleme": 8,
    "transactionnel": 6,
    "verification": 4,
}

TEMPLATES: dict[str, list[str]] = {
    "decouverte": [
        "Quel {cat} choisir à {zone} ?",
        "Peux-tu me recommander un {cat} à {zone} ?",
        "Je cherche un {cat} sérieux à {zone}, lequel prendre ?",
        "Liste les {cat_pl} à {zone}.",
        "Quelles entreprises font {cat} à {zone} ?",
    ],
    "comparaison": [
        "Quel est le meilleur {cat} à {zone} ?",
        "Top 3 des {cat_pl} à {zone} ?",
        "Quel {cat} a la meilleure réputation à {zone} ?",
        "Compare les principaux {cat_pl} à {zone}.",
    ],
    "contrainte": [
        "{cat} à {zone} {constraint} : qui contacter ?",
        "Je cherche un {cat} à {zone} {constraint}. Lequel ?",
        "Y a-t-il un {cat} {constraint} à {zone} ?",
    ],
    "probleme": [
        "{service} à {zone} : qui appeler ?",
        "J'ai besoin de {service} à {zone}, quelle entreprise choisir ?",
        "Qui est compétent pour {service} à {zone} ?",
    ],
    "transactionnel": [
        "Je veux un devis pour {service} à {zone}. Quelles entreprises contacter ?",
        "Qui peut intervenir pour {service} à {zone} cette semaine ?",
        "Où commander {service} à {zone} ?",
    ],
    "verification": [
        "Que penses-tu de {entity} ?",
        "{entity} est-il fiable ?",
    ],
}


def slug(text: str) -> str:
    """Normalise une chaîne pour servir de clé stable."""
    stripped = unicodedata.normalize("NFKD", text)
    stripped = "".join(c for c in stripped if not unicodedata.combining(c))
    return " ".join(stripped.lower().split())


def stable_id(*parts: str) -> str:
    digest = hashlib.sha1("\x1f".join(parts).encode("utf-8")).hexdigest()
    return digest[:12]


@dataclass(frozen=True)
class Entity:
    """Une entreprise suivie dans le marché: le client ou un concurrent."""

    id: str
    name: str
    aliases: tuple[str, ...] = ()
    domains: tuple[str, ...] = ()
    is_client: bool = False
    # Force estimée de présence, utilisée uniquement par le provider de
    # démonstration. Sans effet sur une mesure réelle.
    strength: float = 0.5

    @property
    def match_terms(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys((self.name, *self.aliases)))


@dataclass(frozen=True)
class Economics:
    """Paramètres de valorisation de l'intention, fournis par le client.

    Trois nombres qu'un dirigeant connaît ou peut estimer en une minute. Ils ne
    servent qu'à traduire un taux d'absence en euros — et ils sont republiés
    dans le rapport pour que le calcul reste vérifiable.
    """

    monthly_intent_volume: int   # recherches d'achat mensuelles sur la catégorie et la zone
    avg_deal_value: float        # panier ou valeur moyenne d'une affaire, en euros
    close_rate: float            # taux de transformation d'une demande entrante qualifiée
    # Part de citation qu'un acteur devrait capter sur ce marché. Laissée vide,
    # elle vaut 1/n (part équitable entre les entités suivies) — l'hypothèse la
    # plus neutre, et la plus difficile à contester.
    fair_share: float | None = None

    @classmethod
    def from_dict(cls, data: dict | None) -> "Economics | None":
        if not data:
            return None
        raw_share = data.get("fair_share")
        return cls(
            monthly_intent_volume=int(data["monthly_intent_volume"]),
            avg_deal_value=float(data["avg_deal_value"]),
            close_rate=float(data["close_rate"]),
            fair_share=float(raw_share) if raw_share is not None else None,
        )


@dataclass(frozen=True)
class Prompt:
    id: str
    text: str
    family: str

    @property
    def weight(self) -> float:
        return FAMILY_WEIGHTS.get(self.family, 1.0)


@dataclass
class Market:
    id: str
    label: str
    category: str
    zone: str
    entities: list[Entity]
    category_plural: str = ""
    services: list[str] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)
    economics: Economics | None = None

    def __post_init__(self) -> None:
        if not self.category_plural:
            self.category_plural = f"{self.category}s"
        clients = [e for e in self.entities if e.is_client]
        if len(clients) != 1:
            raise ValueError(
                f"marché {self.id!r}: exactement une entité doit porter is_client=true "
                f"({len(clients)} trouvée(s))"
            )

    @property
    def client(self) -> Entity:
        return next(e for e in self.entities if e.is_client)

    @property
    def competitors(self) -> list[Entity]:
        return [e for e in self.entities if not e.is_client]

    def entity(self, entity_id: str) -> Entity:
        return next(e for e in self.entities if e.id == entity_id)

    # -- chargement ----------------------------------------------------------

    @classmethod
    def from_dict(cls, data: dict) -> "Market":
        entities = [
            Entity(
                id=raw.get("id") or slug(raw["name"]).replace(" ", "-"),
                name=raw["name"],
                aliases=tuple(raw.get("aliases", ())),
                domains=tuple(raw.get("domains", ())),
                is_client=bool(raw.get("is_client", False)),
                strength=float(raw.get("strength", 0.5)),
            )
            for raw in data["entities"]
        ]
        return cls(
            id=data["id"],
            label=data.get("label", data["id"]),
            category=data["category"],
            zone=data["zone"],
            entities=entities,
            category_plural=data.get("category_plural", ""),
            services=list(data.get("services", ())),
            constraints=list(data.get("constraints", ())),
            economics=Economics.from_dict(data.get("economics")),
        )

    @classmethod
    def load(cls, path: str | Path) -> "Market":
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))

    # -- panier de prompts ---------------------------------------------------

    @property
    def basket_version(self) -> str:
        """Empreinte de tout ce qui influence la composition du panier.

        Les entités ne comptent que par leur nom (une entité de vérification
        change le panier) mais pas par leur `strength`, qui est un paramètre de
        démonstration.
        """
        signature = json.dumps(
            {
                "category": self.category,
                "category_plural": self.category_plural,
                "zone": self.zone,
                "services": sorted(self.services),
                "constraints": sorted(self.constraints),
                "entities": sorted(e.name for e in self.entities),
                "templates": TEMPLATES,
                "caps": FAMILY_CAPS,
            },
            sort_keys=True,
            ensure_ascii=False,
        )
        return stable_id(self.id, signature)

    def _expand(self, family: str) -> list[str]:
        base = {"cat": self.category, "cat_pl": self.category_plural, "zone": self.zone}
        out: list[str] = []
        for template in TEMPLATES[family]:
            if "{constraint}" in template:
                out += [template.format(**base, constraint=c) for c in self.constraints]
            elif "{service}" in template:
                out += [template.format(**base, service=s) for s in self.services]
            elif "{entity}" in template:
                # On vérifie la marque du client et celle des concurrents les
                # plus visibles: c'est là que se joue la réputation racontée
                # par les moteurs.
                names = [self.client.name] + [e.name for e in self.competitors[:2]]
                out += [template.format(**base, entity=n) for n in names]
            else:
                out.append(template.format(**base))
        return out

    def basket(self) -> list[Prompt]:
        """Panier de prompts d'achat, stable et borné."""
        prompts: list[Prompt] = []
        for family in TEMPLATES:
            candidates = list(dict.fromkeys(self._expand(family)))
            # Tri par identifiant stable = échantillonnage pseudo-aléatoire
            # reproductible, ancré sur l'identifiant du marché.
            candidates.sort(key=lambda text: stable_id(self.id, family, slug(text)))
            for text in candidates[: FAMILY_CAPS.get(family, 6)]:
                prompts.append(
                    Prompt(id=stable_id(self.id, slug(text)), text=text, family=family)
                )
        prompts.sort(key=lambda p: (p.family, p.id))
        return prompts
