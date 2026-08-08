"""Accès aux moteurs de réponse.

Trois implémentations, trois usages:

* ``AnthropicProvider`` — mesure réelle, recherche web activée côté serveur.
* ``FixtureProvider``  — rejoue des réponses enregistrées. C'est ce qui rend un
  audit *rejouable*: on archive les réponses brutes, donc un client qui
  contesterait un chiffre peut être confronté au corpus exact qui l'a produit.
* ``SyntheticProvider`` — génère des réponses plausibles hors ligne, pour les
  tests et les démonstrations. Tout rapport qui en dépend est marqué comme
  non probant; ce garde-fou n'est pas contournable.
"""

from __future__ import annotations

import hashlib
import json
import os
import struct
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from .market import Market, Prompt

# Niveaux de preuve. Un provider "synthetic" ne peut jamais produire un
# rapport opposable au client.
EVIDENCE_MEASURED = "mesure"
EVIDENCE_REPLAYED = "rejeu"
EVIDENCE_SYNTHETIC = "simulation"


@dataclass
class EngineResponse:
    prompt_id: str
    text: str
    citations: list[str] = field(default_factory=list)
    error: str | None = None


class Provider(Protocol):
    name: str
    evidence: str

    def query(self, prompt: Prompt) -> EngineResponse: ...


# -- déterminisme --------------------------------------------------------------


def _unit_hash(*parts: str) -> float:
    """Réel dans [0, 1), déterministe pour un jeu de clés donné."""
    digest = hashlib.sha256("\x1f".join(parts).encode("utf-8")).digest()
    (raw,) = struct.unpack(">Q", digest[:8])
    return raw / float(1 << 64)


# -- synthétique ---------------------------------------------------------------

_OPENINGS = [
    "Voici les entreprises les plus souvent recommandées :",
    "Plusieurs acteurs ressortent sur ce besoin :",
    "D'après les avis et les sources disponibles :",
    "Quelques options sérieuses :",
]

_QUALIFIERS = [
    "réputé pour ses délais d'intervention",
    "souvent cité pour la qualité du suivi",
    "bien noté sur les avis clients vérifiés",
    "recommandé pour les interventions urgentes",
    "apprécié pour la clarté de ses devis",
]


class SyntheticProvider:
    """Moteur de réponse simulé, déterministe pour un couple (marché, graine).

    La probabilité qu'une entreprise soit citée dépend de sa `strength` dans la
    définition du marché. Cela permet de démontrer la mécanique de mesure sans
    dépendre d'un réseau ni d'une clé d'API — jamais de produire un chiffre
    présentable à un client.
    """

    evidence = EVIDENCE_SYNTHETIC

    def __init__(self, market: Market, seed: str = "0", name: str | None = None) -> None:
        self.market = market
        self.seed = seed
        # La graine fait partie de l'identité du moteur: deux séries simulées
        # doivent rester distinguables dans le rapport et dans les archives.
        self.name = name or f"synthetic:{seed}"

    def query(self, prompt: Prompt) -> EngineResponse:
        scored = []
        for entity in self.market.entities:
            noise = _unit_hash(self.seed, prompt.id, entity.id)
            scored.append((entity.strength * (0.55 + 0.9 * noise), entity))
        scored.sort(key=lambda pair: (-pair[0], pair[1].id))

        slots = 2 + int(_unit_hash(self.seed, prompt.id, "slots") * 3)  # 2 à 4
        cited = [entity for _, entity in scored[:slots]]

        # Un prompt de vérification porte sur une marque nommée: le moteur
        # répond nécessairement à son sujet.
        if prompt.family == "verification":
            named = [
                e for e in self.market.entities
                if e.name.lower() in prompt.text.lower()
            ]
            for entity in named:
                if entity not in cited:
                    cited.insert(0, entity)

        opening = _OPENINGS[int(_unit_hash(self.seed, prompt.id, "open") * len(_OPENINGS))]
        lines = [opening]
        citations: list[str] = []
        for position, entity in enumerate(cited):
            qualifier = _QUALIFIERS[
                int(_unit_hash(self.seed, prompt.id, entity.id, "q") * len(_QUALIFIERS))
            ]
            lines.append(f"{position + 1}. {entity.name} — {qualifier}.")
            if entity.domains and _unit_hash(self.seed, prompt.id, entity.id, "src") < 0.7:
                citations.append(f"https://{entity.domains[0]}/")

        lines.append(
            "Pensez à demander plusieurs devis et à vérifier l'assurance "
            "décennale avant de vous engager."
        )
        return EngineResponse(prompt.id, "\n".join(lines), citations)


# -- rejeu ---------------------------------------------------------------------


class FixtureProvider:
    """Rejoue des réponses archivées (``{prompt_id: {text, citations}}``)."""

    evidence = EVIDENCE_REPLAYED

    def __init__(self, path: str | Path, name: str | None = None) -> None:
        self.path = Path(path)
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        self.name = name or payload.get("engine", self.path.stem)
        self.captured_at = payload.get("captured_at")
        self._responses: dict[str, dict] = payload.get("responses", {})

    def query(self, prompt: Prompt) -> EngineResponse:
        record = self._responses.get(prompt.id)
        if record is None:
            return EngineResponse(prompt.id, "", [], error="réponse absente de l'archive")
        return EngineResponse(
            prompt.id,
            record.get("text", ""),
            list(record.get("citations", ())),
        )


def write_archive(
    path: str | Path, engine: str, responses: list[EngineResponse], prompts: list[Prompt]
) -> None:
    """Archive un jeu de réponses pour rejeu et contestation ultérieure."""
    from datetime import datetime, timezone

    texts = {p.id: p.text for p in prompts}
    payload = {
        "engine": engine,
        "captured_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "responses": {
            r.prompt_id: {
                "prompt": texts.get(r.prompt_id, ""),
                "text": r.text,
                "citations": r.citations,
            }
            for r in responses
            if r.error is None
        },
    }
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


# -- mesure réelle -------------------------------------------------------------

API_URL = "https://api.anthropic.com/v1/messages"

ENGINE_SYSTEM = (
    "Tu es un assistant de recherche grand public. Réponds à la question de "
    "l'utilisateur en t'appuyant sur la recherche web. Nomme explicitement les "
    "entreprises pertinentes, classées de la plus à la moins recommandable, et "
    "cite tes sources. Si tu ne trouves aucune entreprise identifiable, dis-le."
)


class AnthropicProvider:
    """Interroge un modèle avec recherche web activée, via l'API Messages.

    C'est une approximation contrôlée d'un moteur de réponse: on mesure ce
    qu'un assistant équipé de recherche web restitue sur un marché. La méthode
    est documentée dans ``docs/METHODE.md``, limites incluses — vendre une
    « position garantie chez un éditeur » serait un engagement intenable.
    """

    evidence = EVIDENCE_MEASURED

    def __init__(
        self,
        model: str = "claude-sonnet-5",
        api_key: str | None = None,
        max_uses: int = 5,
        timeout: float = 90.0,
        name: str | None = None,
    ) -> None:
        self.model = model
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        self.max_uses = max_uses
        self.timeout = timeout
        self.name = name or f"anthropic:{model}"
        if not self.api_key:
            raise RuntimeError(
                "ANTHROPIC_API_KEY absente: impossible de lancer une mesure réelle. "
                "Utilisez un provider 'fixture:' ou 'synthetic:' pour un rejeu ou une démonstration."
            )

    def query(self, prompt: Prompt) -> EngineResponse:
        body = json.dumps(
            {
                "model": self.model,
                "max_tokens": 1500,
                "system": ENGINE_SYSTEM,
                "tools": [
                    {
                        "type": "web_search_20250305",
                        "name": "web_search",
                        "max_uses": self.max_uses,
                    }
                ],
                "messages": [{"role": "user", "content": prompt.text}],
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
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:  # pragma: no cover - réseau
            detail = exc.read().decode("utf-8", "replace")[:300]
            return EngineResponse(prompt.id, "", [], error=f"HTTP {exc.code}: {detail}")
        except Exception as exc:  # pragma: no cover - réseau
            return EngineResponse(prompt.id, "", [], error=f"{type(exc).__name__}: {exc}")

        return EngineResponse(prompt.id, *_extract(payload))


def _extract(payload: dict) -> tuple[str, list[str]]:
    """Extrait le texte et les URL sourcées d'une réponse de l'API Messages."""
    chunks: list[str] = []
    citations: list[str] = []

    def harvest(block: dict) -> None:
        kind = block.get("type")
        if kind == "text":
            chunks.append(block.get("text", ""))
            for citation in block.get("citations", ()) or ():
                url = citation.get("url")
                if url:
                    citations.append(url)
        elif kind == "web_search_tool_result":
            content = block.get("content")
            if isinstance(content, list):
                for item in content:
                    url = item.get("url") if isinstance(item, dict) else None
                    if url:
                        citations.append(url)

    for block in payload.get("content", ()) or ():
        if isinstance(block, dict):
            harvest(block)

    return "\n".join(c for c in chunks if c), list(dict.fromkeys(citations))


# -- fabrique ------------------------------------------------------------------


def build(spec: str, market: Market) -> Provider:
    """Instancie un provider depuis une spécification textuelle.

    ``synthetic``, ``synthetic:7``, ``fixture:archives/gpt.json``,
    ``anthropic``, ``anthropic:claude-sonnet-5``
    """
    kind, _, argument = spec.partition(":")
    kind = kind.strip().lower()
    argument = argument.strip()

    if kind == "synthetic":
        return SyntheticProvider(market, seed=argument or "0")
    if kind == "fixture":
        if not argument:
            raise ValueError("provider 'fixture:' requiert un chemin d'archive")
        return FixtureProvider(argument)
    if kind == "anthropic":
        return AnthropicProvider(model=argument or "claude-sonnet-5")
    raise ValueError(f"provider inconnu: {spec!r}")
