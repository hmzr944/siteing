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
from datetime import date
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
    # L'hyperlocal pèse lourd parce qu'il est à la fois le plus proche de
    # l'achat et le moins disputé: peu de sources sont assez précises pour
    # qu'un moteur cite quelqu'un sur un quartier nommé.
    "hyperlocal": 1.15,
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
    "hyperlocal": 10,
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
    "hyperlocal": [
        "Quel {cat} intervient à {district} ?",
        "Je cherche un {cat} qui connaît bien {district}, lequel ?",
        "Qui a déjà fait ce genre de chantier à {district} ?",
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
    # Rang Google constaté au moment du relevé. Sert à répondre à la seule
    # question qui décide de la thèse: le rang Google prédit-il la citation
    # par les moteurs de réponse ? Absent, l'entité est exclue du calcul de
    # corrélation mais reste mesurée.
    google_rank: int | None = None
    # Strate d'échantillonnage. On mesure sur un panel stratifié pour pouvoir
    # calculer la corrélation; on vend ensuite au segment de son choix. Les
    # deux listes ne doivent jamais être confondues.
    segment: str = ""
    # Date à laquelle des surfaces ont été publiées pour cette entreprise.
    # C'est ce qui partage le panel entre traités et témoins, et donc ce qui
    # rend un avant/après interprétable: sans témoins, une hausse de citation
    # ne se distingue pas d'un changement de modèle chez l'éditeur.
    treated_since: date | None = None

    def is_treated(self, on: date) -> bool:
        return self.treated_since is not None and self.treated_since <= on

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
    # Nombre d'affaires supplémentaires que l'entreprise peut réellement
    # absorber par mois. Sans ce plafond, toute valorisation d'un gain de
    # visibilité finit par supposer une entreprise à capacité infinie, ce qui
    # produit des chiffres flatteurs et faux.
    max_monthly_deals: float | None = None

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
            max_monthly_deals=(
                float(data["max_monthly_deals"])
                if data.get("max_monthly_deals") is not None
                else None
            ),
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
    districts: list[str] = field(default_factory=list)
    economics: Economics | None = None

    def __post_init__(self) -> None:
        if not self.category_plural:
            self.category_plural = f"{self.category}s"
        clients = [e for e in self.entities if e.is_client]
        if len(clients) > 1:
            raise ValueError(
                f"marché {self.id!r}: au plus une entité peut porter is_client=true "
                f"({len(clients)} trouvées)"
            )

    @property
    def has_client(self) -> bool:
        """Sans client, le marché est un panel de mesure et non un audit."""
        return any(e.is_client for e in self.entities)

    @property
    def client(self) -> Entity:
        client = next((e for e in self.entities if e.is_client), None)
        if client is None:
            raise ValueError(
                f"marché {self.id!r}: panel sans client désigné. La ligne de base "
                "se mesure en mode cohorte."
            )
        return client

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
                google_rank=(
                    int(raw["google_rank"]) if raw.get("google_rank") is not None else None
                ),
                segment=raw.get("segment", ""),
                treated_since=(
                    date.fromisoformat(raw["treated_since"])
                    if raw.get("treated_since")
                    else None
                ),
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
            districts=list(data.get("districts", ())),
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
                "districts": sorted(self.districts),
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
            elif "{district}" in template:
                out += [template.format(**base, district=d) for d in self.districts]
            elif "{service}" in template:
                out += [template.format(**base, service=s) for s in self.services]
            elif "{entity}" in template:
                # On vérifie la marque du client et celle des concurrents les
                # plus visibles: c'est là que se joue la réputation racontée
                # par les moteurs.
                # En audit, on teste la réputation du client et des deux
                # concurrents les plus visibles. En panel, il n'y a pas de
                # client: on prend les trois premières entités déclarées, ce
                # qui reste déterministe.
                if self.has_client:
                    names = [self.client.name] + [e.name for e in self.competitors[:2]]
                else:
                    names = [e.name for e in self.entities[:3]]
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

    def prospecting_basket(self, limit: int = 12) -> list[Prompt]:
        """Panier réduit pour l'Audit d'Invisibilité (docs/VENTE.md).

        Sous-ensemble du panier complet, jamais un panier distinct: mêmes
        gabarits, mêmes identifiants stables, donc directement comparable au
        relevé contractuel qui suivra. On retient les prompts au poids
        commercial le plus fort — les plus proches d'une décision d'achat,
        donc les plus convaincants montrés à un dirigeant en 90 secondes —
        puis on tranche à ``limit``, déterministe grâce au tri stable du
        panier complet.

        En dessous de ``score.MIN_PROMPTS`` (20), un relevé n'est structurellement
        pas présentable comme mesure contractuelle (``AuditResult.is_presentable``) —
        c'est volontaire: un panier de 12 questions reste un repère de
        prospection, jamais le relevé vendu.
        """
        ordered = sorted(self.basket(), key=lambda p: (-p.weight, p.family, p.id))
        return ordered[:limit]


def scaffold(
    client_name: str,
    category: str,
    zone: str,
    competitors: list[str],
    client_domain: str = "",
    market_id: str = "",
) -> Market:
    """Fichier de marché minimal pour une entreprise réelle du terrain.

    Sert le protocole de validation: en entretien, on lance l'audit sur le nom
    réel de l'entreprise interrogée, pas sur un fictif du panel de mesure. Le
    résultat passe par `Market.from_dict()` avant d'être renvoyé, pour
    qu'un marché mal formé échoue ici plutôt qu'au moment de l'audit.
    """
    if not competitors:
        raise ValueError(
            "au moins un concurrent nommé est requis: sans concurrent, il n'y "
            "a pas de marché à mesurer, seulement une marque isolée"
        )
    market_id = market_id or slug(client_name).replace(" ", "-")
    data = {
        "id": market_id,
        "label": f"{client_name} — {category} — {zone}",
        "category": category,
        "zone": zone,
        "entities": [
            {
                "name": client_name,
                "is_client": True,
                "domains": [client_domain] if client_domain else [],
            },
            *[{"name": name} for name in competitors],
        ],
    }
    return Market.from_dict(data)
