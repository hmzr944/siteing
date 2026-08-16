"""Vocabulaire géographique contrôlé.

Premier impératif de la donnée rénovation: un chantier n'existe que s'il est
localisé, et l'IA ne recommandera pas un artisan « aux Chartrons » sans preuve
d'intervention aux Chartrons.

Le piège est la saisie libre. « Chartrons », « les Chartrons », « quartier des
Chartrons », « Bordeaux Chartrons » désignent le même endroit et, laissés tels
quels, fragmentent la preuve en quatre tas dont aucun n'atteint le seuil de
publication. Un territoire est donc une **entrée de vocabulaire**, jamais une
chaîne saisie par un humain ou extraite par un modèle sans résolution.
"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

# Niveaux de granularité, du plus fin au plus large. La preuve se construit au
# niveau du quartier: c'est le grain auquel un acheteur se pose la question, et
# celui auquel presque aucune entreprise n'est citée aujourd'hui.
QUARTIER = "quartier"
COMMUNE = "commune"
METROPOLE = "metropole"

LEVELS = (QUARTIER, COMMUNE, METROPOLE)

_ARTICLES = {"le", "la", "les", "l", "du", "de", "des", "au", "aux", "a", "quartier"}
_PUNCT = re.compile(r"[^\w\s]", re.UNICODE)


def normalize(text: str) -> str:
    """Forme comparable: sans accents, sans casse, sans articles, sans ponctuation."""
    decomposed = unicodedata.normalize("NFKD", text)
    plain = "".join(c for c in decomposed if not unicodedata.combining(c)).lower()
    tokens = [t for t in _PUNCT.sub(" ", plain).split() if t and t not in _ARTICLES]
    return " ".join(tokens)


@dataclass(frozen=True)
class Territoire:
    code: str
    name: str                       # forme d'affichage, avec article: « les Chartrons »
    level: str
    parent: str | None = None       # code du territoire englobant
    aliases: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.level not in LEVELS:
            raise ValueError(f"niveau inconnu: {self.level!r}")

    @property
    def keys(self) -> tuple[str, ...]:
        """Toutes les formes normalisées qui désignent ce territoire."""
        return tuple(
            dict.fromkeys(normalize(term) for term in (self.name, self.code, *self.aliases))
        )

    def locative(self) -> str:
        """Forme employée dans une phrase: « aux Chartrons », « à Talence »."""
        plain = normalize(self.name)
        raw = self.name.strip()
        if raw.lower().startswith("les "):
            return f"aux {raw[4:]}"
        if raw.lower().startswith("la "):
            return f"à la {raw[3:]}"
        if raw.lower().startswith("le "):
            return f"au {raw[3:]}"
        if plain and plain[0] in "aeiouy":
            return f"à {raw}"
        return f"à {raw}"


@dataclass
class Referentiel:
    """L'ensemble des territoires d'un marché, et la résolution des saisies."""

    territoires: list[Territoire]
    _index: dict[str, Territoire] = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        codes = [t.code for t in self.territoires]
        duplicates = {c for c in codes if codes.count(c) > 1}
        if duplicates:
            raise ValueError(f"codes de territoire en doublon: {sorted(duplicates)}")

        self._index = {}
        for territoire in self.territoires:
            for key in territoire.keys:
                previous = self._index.get(key)
                if previous is not None and previous.code != territoire.code:
                    raise ValueError(
                        f"la forme {key!r} désigne à la fois {previous.code} "
                        f"et {territoire.code}"
                    )
                self._index[key] = territoire

        for territoire in self.territoires:
            if territoire.parent and territoire.parent not in codes:
                raise ValueError(
                    f"{territoire.code}: parent {territoire.parent!r} introuvable"
                )

    def get(self, code: str) -> Territoire:
        found = next((t for t in self.territoires if t.code == code), None)
        if found is None:
            raise KeyError(f"territoire inconnu: {code!r}")
        return found

    def resolve(self, raw: str) -> Territoire | None:
        """Résout une saisie libre. Retourne ``None`` plutôt que de deviner.

        Une adresse non résolue doit remonter à l'humain: inventer un territoire
        à partir d'un texte approximatif reviendrait à fabriquer de la preuve.
        """
        key = normalize(raw)
        if not key:
            return None
        if key in self._index:
            return self._index[key]
        # Une saisie plus longue qui contient exactement une clé connue.
        # « chantier rue Notre-Dame aux Chartrons » -> les Chartrons.
        matches = {
            territoire.code: territoire
            for candidate, territoire in self._index.items()
            if candidate and re.search(rf"(?<!\w){re.escape(candidate)}(?!\w)", key)
        }
        return next(iter(matches.values())) if len(matches) == 1 else None

    def ancestors(self, code: str) -> list[Territoire]:
        """Chaîne des territoires englobants, du plus proche au plus large."""
        chain: list[Territoire] = []
        current = self.get(code).parent
        seen = {code}
        while current and current not in seen:
            seen.add(current)
            territoire = self.get(current)
            chain.append(territoire)
            current = territoire.parent
        return chain

    def covers(self, code: str, other: str) -> bool:
        """Vrai si ``code`` est ``other`` ou l'englobe."""
        if code == other:
            return True
        return any(a.code == code for a in self.ancestors(other))

    def at_level(self, level: str) -> list[Territoire]:
        return [t for t in self.territoires if t.level == level]

    @classmethod
    def from_dict(cls, data: dict) -> "Referentiel":
        return cls(
            territoires=[
                Territoire(
                    code=raw["code"],
                    name=raw["name"],
                    level=raw["level"],
                    parent=raw.get("parent"),
                    aliases=tuple(raw.get("aliases", ())),
                )
                for raw in data["territoires"]
            ]
        )

    @classmethod
    def load(cls, path: str | Path) -> "Referentiel":
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))
