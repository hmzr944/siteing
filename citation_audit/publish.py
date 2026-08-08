"""La couche machine du Dossier de Vérité.

C'est ici que se trouve le produit vendu: une entreprise devient citable parce
qu'elle expose des affirmations **structurées et vérifiées**, dans des formats que
consomment les moteurs de réponse et les agents.

Deux sorties, deux publics:

* ``to_jsonld`` — schema.org, pour les indexeurs classiques. N'y figurent que les
  affirmations vérifiées : y publier du déclaratif serait exactement le
  comportement que le marché a déjà appris à ignorer.
* ``to_manifest`` — un descripteur destiné aux agents, qui liste **toutes** les
  affirmations avec leur statut. Un agent a besoin de savoir ce qui n'est pas
  vérifié ; le lui cacher serait la seule vraie faute. La distinction est portée
  par la donnée, pas par une note de bas de page.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timezone

from .creneau import Registry
from .dossier import DECLARED, EXPIRED, REFUTED, VERIFIED, Dossier

PROTOCOL = "source-primaire/1"

NOTICE = (
    "Les affirmations de statut 'verifie' ont été contrôlées sur pièces par un "
    "tiers, à la date indiquée et jusqu'à la date de validité. Les autres sont "
    "déclarées par l'entreprise et n'ont pas été contrôlées."
)


def _today(today: date | None) -> date:
    return today or date.today()


def to_jsonld(dossier: Dossier, today: date | None = None) -> dict:
    """Projection schema.org des seules affirmations vérifiées."""
    moment = _today(today)
    verified = dossier.publishable(moment)

    document: dict = {
        "@context": "https://schema.org",
        "@type": "LocalBusiness",
        "name": dossier.name,
        "additionalType": dossier.category,
        "areaServed": {"@type": "Place", "name": dossier.zone},
    }
    if dossier.legal_id:
        document["identifier"] = {
            "@type": "PropertyValue",
            "propertyID": "SIREN",
            "value": dossier.legal_id,
        }
    if dossier.contact_url:
        document["url"] = dossier.contact_url
    if dossier.photo_url:
        document["image"] = dossier.photo_url

    # Les affirmations qui se projettent sur une propriété du vocabulaire la
    # renseignent directement; les autres deviennent des propriétés
    # additionnelles typées, ce que schema.org prévoit explicitement.
    extras = []
    for claim in verified:
        if claim.schema_property:
            document.setdefault(claim.schema_property, claim.machine_value)
        else:
            extras.append(
                {
                    "@type": "PropertyValue",
                    "name": claim.label,
                    "value": claim.value,
                    "valueReference": {
                        "@type": "PropertyValue",
                        "name": "verifie_le",
                        "value": claim.verified_on.isoformat() if claim.verified_on else None,
                    },
                }
            )
    if extras:
        document["additionalProperty"] = extras

    return document


def to_manifest(
    dossier: Dossier,
    registry: Registry | None = None,
    dossier_url: str | None = None,
    today: date | None = None,
) -> dict:
    """Descripteur destiné aux agents: toutes les affirmations, avec leur statut."""
    moment = _today(today)
    counts = dossier.counts(moment)
    last_verified = dossier.last_verified_on(moment)

    claims = [
        {
            "key": claim.key,
            "label": claim.label,
            "value": claim.value,
            "cluster": claim.cluster,
            "status": claim.status(moment),
            "evidence_count": len(claim.evidence),
            "evidence_kinds": sorted({e.kind for e in claim.evidence}),
            "verified_on": claim.verified_on.isoformat() if claim.verified_on else None,
            "valid_until": claim.valid_until.isoformat() if claim.valid_until else None,
            "schema_property": claim.schema_property,
        }
        for claim in dossier.claims
    ]
    claims.sort(key=lambda c: (c["cluster"], c["key"]))

    manifest: dict = {
        "protocol": PROTOCOL,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "notice": NOTICE,
        "entity": {
            "id": dossier.entity_id,
            "name": dossier.name,
            "category": dossier.category,
            "zone": dossier.zone,
            "legal_id": dossier.legal_id,
            "contact_url": dossier.contact_url,
        },
        "verification": {
            "verified": counts[VERIFIED],
            "declared": counts[DECLARED],
            "expired": counts[EXPIRED],
            "refuted": counts[REFUTED],
            "verified_ratio": round(dossier.verified_ratio(moment), 4),
            "last_verified_on": last_verified.isoformat() if last_verified else None,
            "updated_on": dossier.updated_on.isoformat() if dossier.updated_on else None,
        },
        "claims": claims,
    }
    if dossier_url:
        manifest["dossier_url"] = dossier_url

    if registry is not None:
        manifest["slots"] = [
            {
                "category": grant.category,
                "zone": grant.zone,
                "tier": grant.tier,
                "exclusive": grant.is_exclusive,
                "expires_on": grant.expires_on.isoformat(),
            }
            for grant in registry.slots_for(dossier.entity_id, moment)
        ]

    return manifest


def to_feed_line(dossier: Dossier, today: date | None = None) -> str:
    """Une ligne JSONL par entreprise, pour les flux d'agrégation sectoriels."""
    moment = _today(today)
    return json.dumps(
        {
            "id": dossier.entity_id,
            "name": dossier.name,
            "category": dossier.category,
            "zone": dossier.zone,
            "verified_claims": {c.key: c.value for c in dossier.publishable(moment)},
            "verified_ratio": round(dossier.verified_ratio(moment), 4),
            "last_verified_on": (
                dossier.last_verified_on(moment).isoformat()
                if dossier.last_verified_on(moment)
                else None
            ),
        },
        ensure_ascii=False,
        sort_keys=True,
    )


def write_bundle(
    directory,
    dossier: Dossier,
    registry: Registry | None = None,
    dossier_url: str | None = None,
    today: date | None = None,
) -> dict[str, str]:
    """Écrit les sorties machine d'un dossier. Retourne les chemins produits."""
    from pathlib import Path

    from .verite import to_document

    root = Path(directory)
    root.mkdir(parents=True, exist_ok=True)
    stem = dossier.entity_id

    written: dict[str, str] = {}

    targets = {
        f"{stem}.jsonld": json.dumps(
            to_jsonld(dossier, today), ensure_ascii=False, indent=2
        )
        + "\n",
        f"{stem}.manifest.json": json.dumps(
            to_manifest(dossier, registry, dossier_url, today), ensure_ascii=False, indent=2
        )
        + "\n",
        f"{stem}.jsonl": to_feed_line(dossier, today) + "\n",
        f"{stem}.html": to_document(dossier, registry, today),
    }
    for name, content in targets.items():
        path = root / name
        path.write_text(content, encoding="utf-8")
        written[name] = str(path)

    return written
