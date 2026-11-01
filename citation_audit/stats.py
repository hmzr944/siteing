"""Le minimum statistique nécessaire pour ne pas se raconter d'histoires.

Une seule question justifie ce module, et c'est la plus rentable du projet :
**le rang Google prédit-il la citation par les moteurs de réponse ?**

Si la réponse est non, le marché est réellement neuf et l'argument de vente le
plus fort devient « vous êtes premier sur Google et invisible pour ChatGPT ».
Si la réponse est oui, la thèse du projet est beaucoup plus faible qu'on ne le
croit, et mieux vaut l'apprendre avant d'écrire la moindre ligne d'ingestion.

On mesure donc une corrélation de rangs (Spearman), avec sa valeur p, parce
qu'un coefficient sans seuil de signification sur vingt observations est une
illusion d'optique.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


def rank_with_ties(values: list[float]) -> list[float]:
    """Rangs moyens, les ex aequo partageant la moyenne de leurs rangs."""
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    position = 0
    while position < len(order):
        end = position
        while end + 1 < len(order) and values[order[end + 1]] == values[order[position]]:
            end += 1
        average = (position + end) / 2 + 1
        for index in range(position, end + 1):
            ranks[order[index]] = average
        position = end + 1
    return ranks


def _betacf(a: float, b: float, x: float, iterations: int = 200) -> float:
    """Fraction continue de la fonction bêta incomplète (Lentz)."""
    tiny = 1e-30
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c = 1.0
    d = 1.0 - qab * x / qap
    if abs(d) < tiny:
        d = tiny
    d = 1.0 / d
    h = d
    for m in range(1, iterations + 1):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        if abs(d) < tiny:
            d = tiny
        c = 1.0 + aa / c
        if abs(c) < tiny:
            c = tiny
        d = 1.0 / d
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        if abs(d) < tiny:
            d = tiny
        c = 1.0 + aa / c
        if abs(c) < tiny:
            c = tiny
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < 3e-16:
            break
    return h


def incomplete_beta(a: float, b: float, x: float) -> float:
    """Fonction bêta incomplète régularisée."""
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    front = math.exp(
        math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b)
        + a * math.log(x) + b * math.log1p(-x)
    )
    if x < (a + 1.0) / (a + b + 2.0):
        return front * _betacf(a, b, x) / a
    return 1.0 - front * _betacf(b, a, 1.0 - x) / b


def student_t_two_sided(t: float, df: int) -> float:
    """Probabilité bilatérale associée à une statistique t."""
    if df <= 0:
        return 1.0
    return incomplete_beta(df / 2.0, 0.5, df / (df + t * t))


@dataclass(frozen=True)
class Correlation:
    rho: float
    p_value: float
    n: int

    @property
    def is_significant(self) -> bool:
        return self.p_value < 0.05

    @property
    def reading(self) -> str:
        """Lecture en clair, prudente par construction."""
        if self.n < 10:
            return (
                f"{self.n} observations: aucune conclusion possible, "
                "il en faut au moins vingt pour lire ce coefficient."
            )
        if not self.is_significant:
            return (
                f"Aucun lien détectable (rho {self.rho:+.2f}, p {self.p_value:.3f}, "
                f"n {self.n}). Sur ce marché, le rang Google ne prédit pas la citation "
                "par les moteurs de réponse."
            )
        direction = "va de pair avec" if self.rho < 0 else "s'oppose à"
        return (
            f"Lien statistiquement établi (rho {self.rho:+.2f}, p {self.p_value:.3f}, "
            f"n {self.n}): un bon rang Google {direction} une bonne citation."
        )


def spearman(xs: list[float], ys: list[float]) -> Correlation:
    """Corrélation de rangs entre deux séries de même longueur.

    Le signe se lit avec attention dans notre usage: le rang Google est meilleur
    quand il est *petit*, la part de citation est meilleure quand elle est
    *grande*. Un rho négatif signifie donc « bien classé et bien cité ».
    """
    if len(xs) != len(ys):
        raise ValueError("les deux séries doivent avoir la même longueur")
    n = len(xs)
    if n < 3:
        return Correlation(rho=0.0, p_value=1.0, n=n)

    rx, ry = rank_with_ties(xs), rank_with_ties(ys)
    mean_x, mean_y = sum(rx) / n, sum(ry) / n
    covariance = sum((a - mean_x) * (b - mean_y) for a, b in zip(rx, ry))
    var_x = sum((a - mean_x) ** 2 for a in rx)
    var_y = sum((b - mean_y) ** 2 for b in ry)
    if var_x == 0 or var_y == 0:
        return Correlation(rho=0.0, p_value=1.0, n=n)

    rho = covariance / math.sqrt(var_x * var_y)
    rho = max(-1.0, min(1.0, rho))
    if abs(rho) >= 1.0:
        return Correlation(rho=rho, p_value=0.0, n=n)

    t = rho * math.sqrt((n - 2) / (1 - rho * rho))
    return Correlation(rho=rho, p_value=student_t_two_sided(t, n - 2), n=n)
