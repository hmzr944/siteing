"""Détection des entreprises citées dans une réponse de moteur de réponse.

Le point délicat n'est pas de trouver les mentions, c'est de ne pas en inventer.
Un faux positif dans un audit vendu au client détruit la crédibilité de la
mesure entière, donc la détection est volontairement conservatrice:

* on normalise (accents, casse, formes juridiques, ponctuation);
* on n'accepte qu'une correspondance sur frontières de mots;
* on rejette les alias trop courts ou purement génériques (« Plomberie
  Bordeaux » ne prouve rien dans un marché de plombiers bordelais), sauf
  lorsqu'ils portent un jeton distinctif.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from .market import Entity

# Formes juridiques et abréviations à retirer avant comparaison.
LEGAL_FORMS = {
    "sarl", "sas", "sasu", "eurl", "sa", "sci", "scop", "snc", "ei", "eirl",
    "ets", "etablissements", "ste", "societe", "groupe", "cie", "company",
    "entreprise", "agence", "cabinet", "atelier", "maison",
}

# Jetons trop faibles pour identifier une entreprise à eux seuls.
WEAK_TOKENS = {
    "le", "la", "les", "de", "du", "des", "et", "au", "aux", "en", "pro",
    "plus", "services", "service", "france", "expert", "experts", "conseil",
}

_PUNCT = re.compile(r"[^\w\s]", re.UNICODE)
_TOKEN = re.compile(r"\w+", re.UNICODE)


def normalize(text: str) -> str:
    """Minuscule, sans accents, sans ponctuation, espaces normalisés."""
    decomposed = unicodedata.normalize("NFKD", text)
    without_accents = "".join(c for c in decomposed if not unicodedata.combining(c))
    return " ".join(_PUNCT.sub(" ", without_accents.lower()).split())


def signature_tokens(term: str) -> list[str]:
    """Jetons distinctifs d'un nom d'entreprise, formes juridiques retirées."""
    tokens = _TOKEN.findall(normalize(term))
    return [t for t in tokens if t not in LEGAL_FORMS]


@dataclass(frozen=True)
class Mention:
    entity_id: str
    offset: int          # position du premier caractère de la mention
    rank: int            # rang parmi les entités distinctes citées (1 = première)
    via: str             # "nom", "alias" ou "domaine"
    matched: str


def _generic_tokens(context_terms: list[str]) -> set[str]:
    """Jetons qui décrivent le marché lui-même, donc non discriminants.

    Dans un marché « plombier / Bordeaux », les mots « plombier », « plomberie »
    et « bordeaux » apparaissent dans toutes les réponses: ils ne peuvent pas
    servir à identifier une entreprise en particulier.
    """
    generic = set(WEAK_TOKENS)
    for term in context_terms:
        for token in _TOKEN.findall(normalize(term)):
            generic.add(token)
            # Variantes morphologiques courantes du français métier
            # (plombier → plomberie, couvreur → couverture).
            if len(token) > 5:
                generic.add(token[:5])
    return generic


def _is_discriminant(term: str, generic: set[str]) -> bool:
    tokens = signature_tokens(term)
    if not tokens:
        return False
    distinctive = [
        t for t in tokens
        if len(t) >= 4 and t not in generic and not any(t.startswith(g) for g in generic if len(g) >= 5)
    ]
    if distinctive:
        return True
    # Aucun jeton distinctif isolé: on accepte tout de même une expression
    # multi-mots suffisamment longue (ex. « Aux Deux Clés »), qui ne peut pas
    # apparaître par hasard.
    return len(tokens) >= 3 and len(" ".join(tokens)) >= 12


def find_mentions(
    text: str,
    entities: list[Entity],
    citations: list[str] | None = None,
    context_terms: list[str] | None = None,
) -> list[Mention]:
    """Repère les entités citées, dans l'ordre d'apparition.

    `citations` sont les URL sourcées par le moteur: une correspondance de
    domaine y est la preuve la plus forte qu'une entreprise est utilisée comme
    source, et non simplement évoquée.
    """
    citations = citations or []
    generic = _generic_tokens(context_terms or [])
    haystack = normalize(text)
    joined_citations = " ".join(citations).lower()

    found: dict[str, Mention] = {}

    for entity in entities:
        best: tuple[int, str, str] | None = None  # (offset, via, matched)

        for term in entity.match_terms:
            if not _is_discriminant(term, generic):
                continue
            needle = normalize(term)
            if not needle:
                continue
            match = re.search(rf"(?<!\w){re.escape(needle)}(?!\w)", haystack)
            if match and (best is None or match.start() < best[0]):
                via = "nom" if term == entity.name else "alias"
                best = (match.start(), via, term)

        # Une source citée est la preuve la plus forte: le moteur ne se contente
        # pas de nommer l'entreprise, il s'appuie sur elle. On lui attribue donc
        # un décalage négatif, qui la place devant toute mention en prose, en
        # conservant l'ordre des sources tel que le moteur l'a produit.
        for domain in entity.domains:
            needle = domain.lower().lstrip(".")
            if not needle:
                continue
            position = next(
                (i for i, url in enumerate(citations) if needle in url.lower()), None
            )
            if position is not None:
                best = (position - len(citations), "domaine", domain)
                break
            if best is None and needle in haystack.replace(" ", ""):
                best = (haystack.replace(" ", "").find(needle), "domaine", domain)

        if best is not None:
            found[entity.id] = Mention(
                entity_id=entity.id, offset=best[0], rank=0, via=best[1], matched=best[2]
            )

    ordered = sorted(found.values(), key=lambda m: (m.offset, m.entity_id))
    return [
        Mention(m.entity_id, m.offset, rank, m.via, m.matched)
        for rank, m in enumerate(ordered, start=1)
    ]
