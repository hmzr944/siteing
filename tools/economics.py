#!/usr/bin/env python3
"""Modèle économique de Source Primaire.

Le modèle est ici plutôt que dans un tableur pour la même raison que la Part de
Citation est calculée et non estimée: un chiffre dont on ne peut pas montrer le
calcul n'est pas un argument.

    python3 tools/economics.py
    python3 tools/economics.py --months 36 --slots-per-month 14

Toutes les hypothèses sont en tête de fichier et modifiables en argument. La
seule qui compte vraiment est ``slots_per_month``: ce modèle est contraint par
la capacité commerciale, pas par la demande.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field

NBSP = " "


def eur(value: float) -> str:
    return f"{round(value):,}".replace(",", NBSP) + NBSP + "€"


@dataclass
class Tier:
    name: str
    price: float          # loyer de position mensuel
    share_of_mix: float   # part des créneaux vendus


@dataclass
class Assumptions:
    # -- offre ---------------------------------------------------------------
    tiers: list[Tier] = field(
        default_factory=lambda: [
            Tier("Socle", 349, 0.50),
            Tier("Position", 749, 0.35),
            Tier("Exclusif", 1490, 0.15),
        ]
    )
    setup_fee: float = 900          # dossier de vérité + vérification initiale
    attribution_rate: float = 0.05  # commission sur demande entrante attribuée
    # Valeur mensuelle de demande attribuée par client, une fois en régime.
    attributed_demand_per_client: float = 1800
    ramp_months: int = 4            # délai avant que l'attribution produise

    # -- capacité et rétention ----------------------------------------------
    # Le modèle est contraint par la capacité commerciale, pas par la demande.
    # La montée en charge est progressive: il n'y a pas de pipeline au mois 1.
    slots_per_month: int = 10
    sales_ramp_months: int = 6
    slots_first_month: int = 3
    # 4 %/mois ≈ 25 mois de durée de vie. Plus favorable qu'un SaaS TPE
    # générique (5-7 %) parce que le créneau est exclusif et que le partir
    # signifie le céder à un concurrent — mais pas au point de se raconter
    # une rétention d'éditeur de logiciel installé.
    monthly_churn: float = 0.04

    # -- coûts ---------------------------------------------------------------
    cost_measure_per_client: float = 11    # requêtes moteurs, 2 moteurs × panier figé
    cost_ops_per_client: float = 120       # distribution, mise à jour du dossier de vérité
    cost_setup_per_client: float = 210     # vérification initiale (KYB, pièces)
    # 100 audits par vente = 8 % de prise de rendez-vous × 12 % de closing.
    # L'audit de prospection tourne sur un panier réduit (12 prompts, 1 moteur):
    # produire le panier complet sur un inconnu coûterait plus que le prospect
    # ne vaut.
    audits_per_sale: int = 100
    cost_per_audit: float = 9
    cost_sales_per_sale: float = 1500      # temps commercial réel imputé à une vente
    fixed_monthly: float = 21000           # équipe, outils, structure

    @property
    def arpu(self) -> float:
        return sum(t.price * t.share_of_mix for t in self.tiers)

    @property
    def gross_margin_per_client(self) -> float:
        return self.arpu - self.cost_measure_per_client - self.cost_ops_per_client

    @property
    def cac(self) -> float:
        return self.audits_per_sale * self.cost_per_audit + self.cost_sales_per_sale

    @property
    def lifetime_months(self) -> float:
        return 1 / self.monthly_churn

    @property
    def ltv(self) -> float:
        """Marge brute cumulée sur la durée de vie, frais d'entrée inclus."""
        recurring = self.gross_margin_per_client * self.lifetime_months
        attribution = (
            self.attributed_demand_per_client
            * self.attribution_rate
            * max(0.0, self.lifetime_months - self.ramp_months)
        )
        return recurring + attribution + (self.setup_fee - self.cost_setup_per_client)

    @property
    def payback_months(self) -> float:
        return self.cac / self.gross_margin_per_client


@dataclass
class MonthRow:
    month: int
    clients: int
    mrr: float
    revenue: float
    variable_cost: float
    contribution: float
    ebitda: float
    cumulative: float


def slots_in_month(a: Assumptions, month: int) -> float:
    """Créneaux vendus ce mois-là, montée en charge comprise."""
    if month >= a.sales_ramp_months:
        return float(a.slots_per_month)
    span = max(1, a.sales_ramp_months - 1)
    progress = (month - 1) / span
    return a.slots_first_month + (a.slots_per_month - a.slots_first_month) * progress


def project(a: Assumptions, months: int) -> list[MonthRow]:
    rows: list[MonthRow] = []
    clients = 0.0
    cumulative = 0.0
    # Cohortes, pour n'appliquer l'attribution qu'aux clients en régime.
    cohorts: list[tuple[int, float]] = []

    for month in range(1, months + 1):
        sold = slots_in_month(a, month)
        churned = clients * a.monthly_churn
        clients = clients - churned + sold
        cohorts = [(m, size * (1 - a.monthly_churn)) for m, size in cohorts]
        cohorts.append((month, sold))

        mature = sum(size for m, size in cohorts if month - m >= a.ramp_months)

        recurring = clients * a.arpu
        setup = sold * a.setup_fee
        attribution = mature * a.attributed_demand_per_client * a.attribution_rate
        revenue = recurring + setup + attribution

        variable = (
            clients * (a.cost_measure_per_client + a.cost_ops_per_client)
            + sold * (a.cost_setup_per_client + a.cac)
        )
        contribution = revenue - variable
        ebitda = contribution - a.fixed_monthly
        cumulative += ebitda

        rows.append(
            MonthRow(
                month=month,
                clients=round(clients),
                mrr=recurring + attribution,
                revenue=revenue,
                variable_cost=variable,
                contribution=contribution,
                ebitda=ebitda,
                cumulative=cumulative,
            )
        )
    return rows


def render(a: Assumptions, rows: list[MonthRow]) -> str:
    out: list[str] = []
    out.append("HYPOTHÈSES UNITAIRES")
    out.append(f"  ARPU (mix de l'offre)            {eur(a.arpu):>12}")
    out.append(f"  Marge brute mensuelle / client   {eur(a.gross_margin_per_client):>12}")
    out.append(f"  CAC ({a.audits_per_sale} audits + closing)        {eur(a.cac):>12}")
    out.append(f"  Durée de vie (churn {a.monthly_churn:.1%})       {a.lifetime_months:>9.0f} mois")
    out.append(f"  LTV                              {eur(a.ltv):>12}")
    out.append(f"  LTV / CAC                        {a.ltv / a.cac:>11.1f}x")
    out.append(f"  Retour sur CAC                   {a.payback_months:>9.1f} mois")
    out.append("")

    breakeven = next((r.month for r in rows if r.ebitda > 0), None)
    cash_positive = next((r.month for r in rows if r.cumulative > 0), None)
    trough = min(rows, key=lambda r: r.cumulative)
    out.append("SEUILS")
    out.append(f"  EBITDA mensuel positif           {f'mois {breakeven}' if breakeven else 'jamais':>12}")
    out.append(f"  Cumul positif                    {f'mois {cash_positive}' if cash_positive else 'jamais':>12}")
    out.append(f"  Besoin de trésorerie maximal     {eur(-trough.cumulative):>12}  (mois {trough.month})")
    out.append("")

    out.append("TRAJECTOIRE")
    out.append(f"  {'mois':>4} {'clients':>8} {'MRR':>12} {'CA':>12} {'EBITDA':>12} {'cumul':>13}")
    for row in rows:
        if row.month % 3 == 0 or row.month == 1:
            out.append(
                f"  {row.month:>4} {row.clients:>8} {eur(row.mrr):>13}"
                f" {eur(row.revenue):>13} {eur(row.ebitda):>13} {eur(row.cumulative):>14}"
            )
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--months", type=int, default=24)
    parser.add_argument("--slots-per-month", type=int, default=None)
    parser.add_argument("--churn", type=float, default=None, help="churn mensuel, ex. 0.03")
    parser.add_argument("--fixed", type=float, default=None, help="coûts fixes mensuels")
    args = parser.parse_args(argv)

    assumptions = Assumptions()
    if args.slots_per_month is not None:
        assumptions.slots_per_month = args.slots_per_month
    if args.churn is not None:
        assumptions.monthly_churn = args.churn
    if args.fixed is not None:
        assumptions.fixed_monthly = args.fixed

    print(render(assumptions, project(assumptions, args.months)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
