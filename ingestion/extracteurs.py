"""Les extracteurs de fragments.

Deux implémentations du même contrat étroit: rendre des fragments verbatim
typés, jamais des codes internes.

``HeuristicExtractor`` — sans réseau ni modèle. Il sert de démonstration, de
repli quand l'appel échoue, et surtout d'oracle de test: les résolveurs peuvent
ainsi être vérifiés indépendamment du modèle.

``LLMExtractor`` — sortie structurée typée. Le contrat imposé au modèle est
volontairement pauvre: il découpe la phrase, il ne classe rien. C'est ce qui
supprime l'essentiel du risque d'hallucination, puisqu'il n'y a aucun
vocabulaire fermé à respecter.
"""

from __future__ import annotations

import json
import os
import re
import urllib.request
from typing import Protocol

from .extraction import SPAN_TYPES, Span
from .lexique import NATURE_KEYWORDS, VAGUE_TERMS, plain

LOCATION_CUES = (
    "rue", "avenue", "boulevard", "cours", "quai", "place", "impasse",
    "allee", "chemin", "quartier", "a ", "aux ", "sur ",
)


class Extractor(Protocol):
    name: str

    def spans(self, text: str) -> list[Span]: ...


class HeuristicExtractor:
    """Découpage par motifs. Suffisant pour la démonstration et les tests."""

    name = "heuristique"

    def spans(self, text: str) -> list[Span]:
        found: list[Span] = []
        lowered = plain(text)

        for pattern, kind in (
            (r"\d[\d\s]*(?:plaques?|briques?|k|keuros?|bars?|euros?|€)", "montant"),
            (r"\d[\d\s]*(?:jours?|semaines?|mois)", "duree"),
            (r"\d[\d\s.,]*(?:m2|m²|metres? carres?|ml|litres?|kw|kilowatts?)", "surface"),
            (r"\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?", "date"),
            (r"\b(?:hier|avant-hier|ce matin|aujourd'hui|semaine derniere|mois dernier)\b", "date"),
        ):
            for match in re.finditer(pattern, lowered):
                found.append(Span(kind, match.group(0)))

        for keyword in NATURE_KEYWORDS:
            if re.search(rf"\b{re.escape(keyword)}\b", lowered):
                found.append(Span("nature", keyword))
        if not any(s.kind == "nature" for s in found):
            for term in VAGUE_TERMS:
                if term in lowered:
                    found.append(Span("nature", term))
                    break

        # Une expression de lieu court du repère jusqu'à la ponctuation.
        for cue in ("rue", "avenue", "boulevard", "cours", "quai", "place", "quartier"):
            # On s'arrête aussi sur « sur », « de » et un chiffre: « quai des
            # Chartrons sur une échoppe, 90 m2 » ne doit pas devenir un lieu.
            for match in re.finditer(
                rf"\b{cue}\s+(?:[^,.;!?\d]|(?<!\s)\d)+", text, re.IGNORECASE
            ):
                fragment = re.split(r"\s+(?:sur|avec|pour)\s+", match.group(0))[0]
                found.append(Span("lieu", fragment.strip()))
        for match in re.finditer(r"\b(?:aux?|à)\s+([A-ZÉÈÊÀÂÎÔÛ][\w'’-]+(?:\s+[A-ZÉÈÊ][\w'’-]+)?)", text):
            found.append(Span("lieu", match.group(1).strip()))

        if "echoppe" in lowered:
            found.append(Span("typologie", "échoppe"))

        seen: set[tuple[str, str]] = set()
        unique = []
        for span in found:
            key = (span.kind, plain(span.text))
            if key not in seen:
                seen.add(key)
                unique.append(span)
        return unique


SYSTEM = """Tu découpes un message vocal d'artisan en fragments verbatim.

Tu ne classes rien, tu ne normalises rien, tu n'inventes rien. Tu recopies des
morceaux exacts du texte et tu indiques de quoi ils parlent.

Types autorisés: lieu, nature, montant, duree, surface, date, typologie.

Règles absolues:
- chaque fragment doit apparaître MOT POUR MOT dans le texte d'origine;
- si une information est absente, tu ne produis aucun fragment pour elle;
- tu ne devines jamais: « rénovation » sans précision reste « rénovation ».
"""

TOOL = {
    "name": "fragments",
    "description": "Fragments verbatim repérés dans le message.",
    "input_schema": {
        "type": "object",
        "properties": {
            "spans": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "kind": {"type": "string", "enum": list(SPAN_TYPES)},
                        "text": {"type": "string"},
                    },
                    "required": ["kind", "text"],
                },
            }
        },
        "required": ["spans"],
    },
}

API_URL = "https://api.anthropic.com/v1/messages"


class LLMExtractor:
    """Extraction par sortie structurée, avec vérification du verbatim."""

    name = "llm"

    def __init__(
        self,
        model: str = "claude-sonnet-5",
        api_key: str | None = None,
        fallback: Extractor | None = None,
    ) -> None:
        self.model = model
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        self.fallback = fallback or HeuristicExtractor()
        if not self.api_key:
            raise RuntimeError(
                "ANTHROPIC_API_KEY absente: utilisez HeuristicExtractor pour une "
                "extraction hors ligne."
            )

    def spans(self, text: str) -> list[Span]:
        body = json.dumps(
            {
                "model": self.model,
                "max_tokens": 1024,
                "system": SYSTEM,
                "tools": [TOOL],
                "tool_choice": {"type": "tool", "name": "fragments"},
                "messages": [{"role": "user", "content": text}],
            }
        ).encode("utf-8")
        request = urllib.request.Request(
            API_URL,
            data=body,
            headers={
                "content-type": "application/json",
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=45) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except Exception:  # pragma: no cover - réseau
            return self.fallback.spans(text)

        raw = next(
            (
                block.get("input", {}).get("spans", [])
                for block in payload.get("content", ())
                if isinstance(block, dict) and block.get("type") == "tool_use"
            ),
            [],
        )
        return verbatim_only(text, raw)


def verbatim_only(text: str, raw: list[dict]) -> list[Span]:
    """Ne garde que les fragments réellement présents dans le texte d'origine.

    C'est le garde-fou qui rend l'hallucination inoffensive. Un modèle qui
    inventerait « salle de bain » dans un message qui n'en parle pas voit son
    fragment jeté ici, avant toute résolution: il ne peut pas produire un fait.
    """
    haystack = plain(text)
    kept: list[Span] = []
    for item in raw:
        kind, fragment = item.get("kind"), (item.get("text") or "").strip()
        if kind not in SPAN_TYPES or not fragment:
            continue
        if plain(fragment) not in haystack:
            continue
        kept.append(Span(kind, fragment))
    return kept
