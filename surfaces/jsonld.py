"""Projection schema.org du Noyau.

Deux principes, dont le second a des conséquences juridiques.

**La discipline vaut mieux que la densité.** Un JSON-LD « hyper-dense » bourré de
propriétés inventées n'est pas mieux lu, il est moins bien lu: un consommateur de
données structurées valide les types, et du vocabulaire hors référentiel est
ignoré au mieux, pénalisé au pire. On publie donc peu de propriétés, toutes
valides, toutes adossées à un fait daté.

**Un budget constaté n'est jamais une offre.** C'est l'interdit central de ce
module. Le vocabulaire ``Offer``, ``AggregateOffer``, ``PriceSpecification`` et
``price`` décrit ce qu'une entreprise **propose de vendre**. Or nous publions ce
qui a été **facturé par le passé**, sur des chantiers passés, sans engagement sur
le prochain. Utiliser le vocabulaire de l'offre transformerait un constat en
proposition commerciale, ce qui est précisément le risque contre lequel tout le
schéma du Noyau a été conçu.

Les budgets sont donc publiés en ``additionalProperty``, avec une
``QuantitativeValue`` explicitement décrite comme observée sur N chantiers. Un
test interdit la présence du vocabulaire de l'offre dans toute la sortie.
"""

from __future__ import annotations

from datetime import date

from noyau import NATURES, Noyau

from .lattice import CROISEMENT, ROOT, TERRITOIRE, Node

CONTEXT = "https://schema.org"

# Vocabulaire interdit: il ferait d'un constat une proposition commerciale.
FORBIDDEN_TERMS = (
    "Offer",
    "AggregateOffer",
    "PriceSpecification",
    "price",
    "priceCurrency",
    "lowPrice",
    "highPrice",
)


def _organisation(core: Noyau, today: date, minimal: bool = False) -> dict:
    """L'entreprise, telle qu'un moteur doit la comprendre.

    Ce document ne varie jamais selon un palier commercial de manière
    cachée: la seule variation possible est ``minimal``, explicite,
    documentée, et elle ne retire jamais rien qui exigerait une vérification
    humaine d'un côté pour l'ajouter de l'autre en douce. C'est la fiche du
    palier Gratuit — identité vérifiable automatiquement (SIRENE), rien de
    plus — telle que fixée par ``docs/PLAN.md`` §2-3 : le gratuit publie le
    minimum vérifiable, le payant vend la profondeur, jamais l'existence.
    L'exclusivité (``citation_audit.creneau``) reste hors de ce module,
    quelle que soit la valeur de ``minimal``.
    """
    document: dict = {
        "@type": "HomeAndConstructionBusiness",
        "@id": f"{core.contact_url or ''}#entreprise",
        "name": core.name,
        "description": (
            f"{core.category.capitalize()} à {core.zone}, identité vérifiée."
            if minimal else
            f"{core.category.capitalize()} intervenant à {core.zone}, "
            "dont les chantiers, budgets constatés et qualifications sont "
            "publiés et vérifiés."
        ),
    }
    if core.contact_url:
        document["url"] = core.contact_url
    if core.legal_id:
        document["identifier"] = {
            "@type": "PropertyValue",
            "propertyID": "SIREN",
            "value": core.legal_id,
        }

    if minimal:
        # Aucun chantier, aucune certification: ces deux matières exigent une
        # vérification humaine sur pièce, donc appartiennent au palier payant
        # — voir la frontière posée dans docs/PLAN.md §2.
        return document

    served = [
        p.territoire for p in core.territoires_publiables(today)
    ]
    if served:
        document["areaServed"] = [
            {"@type": "Place", "name": t.name.strip()} for t in served
        ]

    credentials = []
    extras = []
    for claim in core.autorites(today):
        if claim.schema_property == "hasCredential":
            credentials.append(
                {
                    "@type": "EducationalOccupationalCredential",
                    "name": claim.machine_value,
                    "validUntil": claim.valid_until.isoformat()
                    if claim.valid_until
                    else None,
                    "recognizedBy": {
                        "@type": "Organization",
                        "name": claim.evidence[0].checked_by if claim.evidence else "",
                    },
                }
            )
        elif claim.schema_property:
            document.setdefault(claim.schema_property, claim.machine_value)
        else:
            extras.append(
                {
                    "@type": "PropertyValue",
                    "name": claim.label,
                    "value": claim.machine_value,
                }
            )
    if credentials:
        document["hasCredential"] = credentials
    if extras:
        document.setdefault("additionalProperty", []).extend(extras)

    return document


def _budget_property(node: Node) -> dict:
    """Un budget constaté, en vocabulaire de mesure et non d'offre."""
    from .render import _scope_sentence

    budget = node.budget
    scope = _scope_sentence(node)
    return {
        "@type": "PropertyValue",
        "name": "Budget constaté sur chantiers réalisés",
        "description": budget.sentence(),
        "value": {
            "@type": "QuantitativeValue",
            "unitText": "EUR",
            "value": round(budget.median),
            "minValue": round(budget.p25),
            "maxValue": round(budget.p75),
        },
        "measurementTechnique": (
            f"Médiane et quartiles de {budget.n} chantiers facturés entre "
            f"{budget.oldest.isoformat()} et {budget.newest.isoformat()}, "
            "sur des ouvrages de taille comparable." + scope + " Constat de "
            "facturation passée, sans engagement sur un chantier futur."
        ),
    }


def _realisations(node: Node, limit: int = 12) -> list[dict]:
    """Les chantiers, en ``CreativeWork`` daté et localisé.

    C'est la matière la plus citée: spécifique, datée, localisée. Un moteur
    reprend « salle de bain de 6 m² aux Chartrons en mars 2025 » là où il ignore
    « nous réalisons vos salles de bain avec passion ».
    """
    ordered = sorted(node.chantiers, key=lambda c: c.completed_on, reverse=True)
    works = []
    for chantier in ordered[:limit]:
        spec = NATURES[chantier.nature]
        size = (
            f", {chantier.size:g} {spec.unit}" if chantier.size else ""
        )
        works.append(
            {
                "@type": "CreativeWork",
                "name": f"{spec.label}{size}",
                "dateCreated": chantier.completed_on.isoformat(),
                "locationCreated": {
                    "@type": "Place",
                    "name": (node.territoire.name.strip() if node.territoire else ""),
                },
                "about": spec.label,
            }
        )
    return works


def for_node(core: Noyau, node: Node, today: date, minimal: bool = False) -> dict:
    """Le document structuré d'une page du treillis."""
    organisation = _organisation(core, today, minimal)

    if node.kind == ROOT or minimal:
        return {"@context": CONTEXT, **organisation}

    spec = NATURES[node.nature] if node.nature else None
    service: dict = {
        "@context": CONTEXT,
        "@type": "Service",
        "name": node.title,
        "provider": organisation,
        "areaServed": {
            "@type": "Place",
            "name": node.territoire.name.strip() if node.territoire else "",
        },
    }
    if spec:
        service["serviceType"] = spec.label

    properties = []
    if node.budget is not None:
        properties.append(_budget_property(node))
    properties.append(
        {
            "@type": "PropertyValue",
            "name": "Chantiers réalisés sur ce périmètre",
            "value": len(node.chantiers),
            "description": (
                f"{len(node.chantiers)} chantiers, dont {node.documented} adossés "
                f"à une pièce justificative. Dernier en "
                f"{node.latest.isoformat() if node.latest else 'n/a'}."
            ),
        }
    )
    service["additionalProperty"] = properties

    works = _realisations(node)
    if works:
        service["workExample"] = works

    if node.kind == TERRITOIRE and spec is None:
        # Une page de territoire n'a pas de nature (elle couvre tout le
        # métier sur ce quartier): le type de service vient de la catégorie
        # du Noyau, jamais d'un métier codé en dur — ce module sert
        # n'importe quel métier, pas seulement la rénovation.
        service["serviceType"] = core.category.capitalize()

    return service


def contains_offer_vocabulary(document: dict) -> list[str]:
    """Repère toute trace du vocabulaire de l'offre. Doit toujours rendre [].

    Ce contrôle est appelé par les tests, mais il est ici et non dans les tests
    parce qu'il fait partie du contrat du module: ce qu'on publie ne doit jamais
    pouvoir se lire comme une proposition commerciale.
    """
    found: list[str] = []

    def walk(value, path: str) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                if key in FORBIDDEN_TERMS:
                    found.append(f"{path}.{key}")
                walk(item, f"{path}.{key}")
        elif isinstance(value, list):
            for index, item in enumerate(value):
                walk(item, f"{path}[{index}]")
        elif isinstance(value, str) and value in FORBIDDEN_TERMS:
            found.append(f"{path} = {value}")

    walk(document, "$")
    return found
