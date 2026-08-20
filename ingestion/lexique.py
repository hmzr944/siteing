"""Résolveurs déterministes.

Le principe qui gouverne tout le paquet: **un modèle de langue ne choisit jamais
dans notre vocabulaire contrôlé.** Il extrait des fragments verbatim; ce sont ces
fonctions, testables sans réseau et sans modèle, qui les traduisent en codes.

La raison n'est pas la méfiance, c'est la division du travail. Un modèle est
excellent pour repérer « y'en a eu pour 12 plaques » dans un flot de parole
spontanée, et mauvais pour garantir que la sortie appartient à une énumération
fermée. Un `re.compile` fait l'inverse. On donne à chacun ce qu'il sait faire.

Corollaire tenu partout ici: **une résolution ambiguë est un refus.** Rien n'est
deviné, parce qu'une donnée devinée entrerait dans un Noyau qui existe
précisément pour être opposable.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import date, timedelta

from noyau.chantier import NATURE_KEYWORDS, NATURES


@dataclass(frozen=True)
class Resolved:
    """Résultat d'une résolution: une valeur, ou un refus motivé."""

    value: object | None
    confidence: float = 0.0
    note: str = ""

    @property
    def ok(self) -> bool:
        return self.value is not None

    @classmethod
    def refuse(cls, note: str) -> "Resolved":
        return cls(value=None, confidence=0.0, note=note)


def plain(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(c for c in decomposed if not unicodedata.combining(c)).lower()


# -- montants ------------------------------------------------------------------

# Multiplicateurs d'argot. « Plaque » et « brique » valent mille euros.
SLANG = {"plaque": 1000, "plaques": 1000, "brique": 1000, "briques": 1000,
         "k": 1000, "keur": 1000, "keuros": 1000, "bar": 1000, "bars": 1000}

# Marqueurs qui font d'un nombre un montant. Sans l'un d'eux, « 12 plaques »
# reste ambigu: dans le bâtiment, une plaque est aussi une plaque de plâtre.
MONEY_MARKERS = (
    "y'en a eu pour", "yen a eu pour", "ca a coute", "ça a coûté", "coute",
    "facture", "facturé", "devis", "budget", "prix", "euro", "eur", "€",
    "pour un total", "au total", "ttc", "ht", "encaisse", "paye", "payé",
)

WORDS = {
    "mille": 1000, "deux": 2, "trois": 3, "quatre": 4, "cinq": 5, "six": 6,
    "sept": 7, "huit": 8, "neuf": 9, "dix": 10, "onze": 11, "douze": 12,
    "quinze": 15, "vingt": 20, "trente": 30,
}

# Un nombre doit commencer sur une frontière. Sans le garde à gauche,
# « 90 m2, 34 plaques » produit le nombre « 2, 34 » en avalant la fin de
# l'unité précédente, et le montant devient faux. Le motif accepte les
# groupes de milliers séparés par une espace ordinaire, insécable ou fine.
_NUM = r"(?<![\w])(\d{1,3}(?:[\s\u00a0\u202f]\d{3})+|\d+(?:[.,]\d+)?)"


def _to_float(raw: str) -> float | None:
    cleaned = raw.replace(" ", "").replace(" ", "").replace(".", "")
    cleaned = cleaned.replace(",", ".").rstrip(".")
    try:
        return float(cleaned)
    except ValueError:
        return None


def parse_montant(text: str, money_context: bool = False) -> Resolved:
    """Montant en euros, à partir d'une formulation parlée.

    Le cas piégeux est propre au métier: « 12 plaques » vaut douze mille euros
    dans la bouche d'un patron qui parle de son chiffre, et douze plaques de
    plâtre dans celle du même patron qui parle de son chantier. Sans marqueur
    monétaire dans la phrase, on refuse et on pose la question.

    ``money_context`` est ce que le dialogue apporte. Quand le système vient de
    demander « le chantier a été facturé combien ? », la réponse « 12 plaques »
    n'est plus ambiguë: le contexte monétaire est fourni par la question. Le
    dialogue ne sert donc pas seulement à collecter, il désambiguïse.
    """
    lowered = plain(text)
    has_marker = money_context or any(m in lowered for m in MONEY_MARKERS)

    # Nombre suivi d'une unité d'argot ou de « euros ».
    match = re.search(rf"{_NUM}\s*(plaques?|briques?|k|keuros?|bars?|euros?|€)\b", lowered)
    if match:
        amount = _to_float(match.group(1))
        unit = match.group(2)
        if amount is None:
            return Resolved.refuse("nombre illisible")
        if unit in ("euros", "euro", "€"):
            return Resolved(amount, 0.95, f"« {match.group(0).strip()} »")
        if not has_marker:
            return Resolved.refuse(
                f"« {match.group(0).strip()} » est ambigu: unité d'argot sans "
                "marqueur monétaire dans la phrase"
            )
        return Resolved(
            amount * SLANG.get(unit, 1000), 0.8, f"« {match.group(0).strip()} »"
        )

    # Nombre écrit en lettres, du type « douze mille ».
    for word, value in WORDS.items():
        if re.search(rf"\b{word}\s+mille\b", lowered) and has_marker:
            return Resolved(value * 1000.0, 0.75, f"« {word} mille »")

    # Nombre nu, accepté seulement si la phrase parle bien d'argent.
    if has_marker:
        bare = re.search(rf"{_NUM}", lowered)
        if bare:
            amount = _to_float(bare.group(1))
            if amount and amount >= 100:
                return Resolved(amount, 0.6, f"« {bare.group(1).strip()} »")
    return Resolved.refuse("aucun montant identifiable")


# -- durées --------------------------------------------------------------------

def parse_duree(text: str) -> Resolved:
    """Durée en jours ouvrés déclarés."""
    lowered = plain(text)
    if re.search(r"\bquinze jours\b|\bquinzaine\b", lowered):
        return Resolved(15, 0.9, "« quinze jours »")
    match = re.search(rf"{_NUM}\s*(jours?|semaines?|mois)\b", lowered)
    if match:
        amount = _to_float(match.group(1))
        if amount is None:
            return Resolved.refuse("durée illisible")
        unit = match.group(2)
        factor = 1 if unit.startswith("jour") else 7 if unit.startswith("semaine") else 30
        return Resolved(int(amount * factor), 0.9, f"« {match.group(0).strip()} »")
    if re.search(r"\bune semaine\b", lowered):
        return Resolved(7, 0.85, "« une semaine »")
    for word, value in WORDS.items():
        for unit, factor in (("jours?", 1), ("semaines?", 7), ("mois", 30)):
            if re.search(rf"\b{word}\s+{unit}\b", lowered):
                return Resolved(value * factor, 0.8, f"« {word} {unit[:-2]} »")
    if re.search(r"\bun mois\b", lowered):
        return Resolved(30, 0.8, "« un mois »")
    return Resolved.refuse("aucune durée identifiable")


# -- surfaces ------------------------------------------------------------------

# Unités reconnues. Ce n'est pas encore dérivé des catalogues de métier
# (contrairement à NATURE_KEYWORDS ci-dessous): un métier qui introduirait une
# unité vraiment nouvelle (autre que surface, linéaire, volume, puissance ou
# durée-en-heures) demanderait d'étendre cette liste. Limitation connue, pas
# cachée.
#
# « jour(s) » est volontairement absent de cette liste, alors que le conseil
# (metiers/conseil.json) mesure sa taille en jours: le mot est déjà pris par
# parse_duree, et une mission de conseil confond taille et durée (un audit de
# "3 jours" est aussi bien sa taille que sa durée). Ajouter "jours?" ici ferait
# resurgir la même phrase dans deux champs à la fois. Le système pose la
# question plutôt que de deviner lequel des deux compte — refuser plutôt que
# résoudre en double, la même règle que partout ailleurs dans ce fichier.
def parse_surface(text: str) -> Resolved:
    """Taille d'une prestation, dans l'unité parlée.

    Couvre la surface et le linéaire (rénovation), le volume et la puissance
    (plomberie, chauffage), la durée en heures (conseil) : c'est le même champ
    de mesure pour n'importe quel métier, seule l'unité parlée change.
    """
    lowered = plain(text)
    match = re.search(
        rf"{_NUM}\s*"
        r"(m2|m²|metres? carres?|metres? lineaires?|ml|litres?|kw|kilowatts?|heures?)\b",
        lowered,
    )
    if match:
        amount = _to_float(match.group(1))
        if amount is None or amount <= 0:
            return Resolved.refuse("surface illisible")
        return Resolved(amount, 0.9, f"« {match.group(0).strip()} »")
    return Resolved.refuse("aucune surface identifiable")


# -- natures -------------------------------------------------------------------

# NATURE_KEYWORDS vient de noyau.chantier: fusion des mots-clés déclarés par
# chaque métier dans metiers/*.json. Ce résolveur ne connaît donc aucun métier
# en particulier — ajouter un métier ne demande jamais de toucher ce fichier,
# seulement son catalogue JSON. Un mot-clé disputé par deux métiers (« salle
# d'eau » en rénovation et en plomberie, par exemple) a déjà été retiré de
# l'index par noyau.catalogue.merge_keywords: il ne résout jamais rien plutôt
# que de deviner lequel des deux métiers est en cause.

# Termes qui annoncent un chantier sans dire lequel. Ils ne résolvent rien.
VAGUE_TERMS = ("renovation", "renover", "travaux", "chantier", "refait", "refaire")


def _keyword_in(keyword: str, lowered: str) -> bool:
    """Un mot-clé compte s'il apparaît en mot entier, jamais en sous-chaîne.

    Un simple ``in`` ferait matcher l'abréviation « ite » (isolation
    thermique par l'extérieur) à l'intérieur de « fu-ite »: un métier de plus
    dans le catalogue suffirait alors à faire dérailler un autre métier, sans
    qu'aucun des deux ne l'ait jamais demandé.
    """
    return re.search(rf"\b{re.escape(keyword)}\b", lowered) is not None


def parse_nature(text: str) -> Resolved:
    """Nature de chantier. Un terme vague ne résout rien, il pose une question.

    « J'ai fini la rénovation rue Notre-Dame » ne dit pas ce qui a été rénové.
    Déduire « salle de bain » d'un budget de douze mille euros et de quatre
    jours serait une inférence, pas une extraction, et elle finirait publiée
    comme un fait.
    """
    lowered = plain(text)
    hits = {code for keyword, code in NATURE_KEYWORDS.items() if _keyword_in(keyword, lowered)}
    if len(hits) == 1:
        keyword = next(
            k for k, c in NATURE_KEYWORDS.items() if c in hits and _keyword_in(k, lowered)
        )
        return Resolved(hits.pop(), 0.9, f"« {keyword} »")
    if len(hits) > 1:
        return Resolved.refuse(
            "plusieurs natures évoquées (" + ", ".join(sorted(hits)) + ")"
        )
    if any(term in lowered for term in VAGUE_TERMS):
        return Resolved.refuse(
            "un chantier est évoqué sans dire lequel: terme trop général"
        )
    return Resolved.refuse("aucune nature identifiable")


def nature_label(code: str) -> str:
    return NATURES[code].label if code in NATURES else code


# -- dates ---------------------------------------------------------------------

WEEKDAYS = ("lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche")


def parse_date(text: str, today: date) -> Resolved:
    """Date d'achèvement, résolue relativement au jour de l'énoncé."""
    lowered = plain(text)
    if "avant-hier" in lowered:
        return Resolved(today - timedelta(days=2), 0.9, "« avant-hier »")
    if "hier" in lowered:
        return Resolved(today - timedelta(days=1), 0.9, "« hier »")
    if any(w in lowered for w in ("ce matin", "aujourd'hui", "aujourd hui", "a l'instant")):
        return Resolved(today, 0.9, "« aujourd'hui »")
    if "semaine derniere" in lowered:
        return Resolved(today - timedelta(days=7), 0.7, "« la semaine dernière »")
    if "mois dernier" in lowered:
        return Resolved(today - timedelta(days=30), 0.6, "« le mois dernier »")
    match = re.search(r"\b(\d{1,2})[/-](\d{1,2})(?:[/-](\d{2,4}))?\b", lowered)
    if match:
        day, month = int(match.group(1)), int(match.group(2))
        year = int(match.group(3) or today.year)
        year += 2000 if year < 100 else 0
        try:
            return Resolved(date(year, month, day), 0.95, f"« {match.group(0)} »")
        except ValueError:
            return Resolved.refuse("date invalide")
    for index, name in enumerate(WEEKDAYS):
        if re.search(rf"\b{name}\b", lowered):
            delta = (today.weekday() - index) % 7 or 7
            return Resolved(today - timedelta(days=delta), 0.6, f"« {name} »")
    # Le défaut est explicite et de faible confiance: un chantier raconté
    # aujourd'hui a le plus souvent été fini récemment, mais on ne le sait pas.
    return Resolved(today, 0.3, "aucune date énoncée, jour de l'énoncé retenu")
