#!/usr/bin/env python3
"""Modèle économique de Source Primaire — offre à deux mouvements.

Le modèle est ici plutôt que dans un tableur pour la même raison que la Part
de Citation est calculée et non estimée: un chiffre dont on ne peut pas
montrer le calcul n'est pas un argument.

    python3 tools/economics.py
    python3 tools/economics.py --months 36 --free-signups 200

**L'offre a changé de forme, deux fois.** Trois paliers, dont un gratuit —
et publié :

* **Gratuit** — Noyau constitué et vérifié, publié en fiche **minimale**
  (identité vérifiée automatiquement via le répertoire SIRENE : nom,
  catégorie, zone, SIREN — voir ``surfaces.MINIMAL``). Le registre vaut par
  sa complétude, pas par son revenu : un annuaire qui n'exposerait que ses
  clients payants perdrait la densité qui le rend utile à un agent, et
  ressemblerait aux annuaires professionnels payants des années 2000. Rien
  qui exige une vérification humaine (chantiers sur pièce, certifications)
  n'y figure — la frontière suit le coût de vérification, jamais
  l'existence.
* **Forfait — 19 €/mois** — distribution **complète** (``surfaces.COMPLET`` :
  chantiers, budgets constatés, certifications, treillis de pages) et relevé
  de citation périodique. Vendu en self-serve, jamais par appel commercial :
  à ce prix, un cycle de vente sortant coûterait plus que le client ne
  rapporte.
* **Forfait Exclusif** — + position vérifiée exclusive (catégorie × zone),
  vendue par le playbook sortant existant (docs/VENTE.md), inchangé : à ce
  ticket, l'Audit d'Invisibilité et l'appel restent rentables.

Deux mouvements commerciaux distincts cohabitent donc dans ce modèle, avec
chacun son propre CAC, sa propre rétention, son propre coût de service — les
confondre en un seul ARPU moyen, comme le faisait la version précédente de ce
fichier, aurait caché que ce sont deux entreprises différentes sous le même
toit.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass

NBSP = " "


def eur(value: float) -> str:
    return f"{round(value):,}".replace(",", NBSP) + NBSP + "€"


@dataclass
class Assumptions:
    # -- prix -----------------------------------------------------------------
    forfait_price: float = 19
    exclusif_price: float = 990
    setup_fee_exclusif: float = 900   # filtre qualifiant, réservé au ticket haut

    # -- mouvement 1: gratuit -> Forfait, en self-serve -----------------------
    # Le chiffre le moins certain du modèle, comme `slots_per_month` l'était
    # dans la version précédente: personne ne connaît le taux de conversion
    # tant qu'il n'a pas été mesuré sur de vrais inscrits.
    free_signups_steady: int = 150
    free_signups_first_month: int = 20
    free_signups_ramp_months: int = 6
    # Sur la population gratuite restante chaque mois: converti, ou parti.
    # Fraction qui finit par convertir = convert_rate / (convert_rate + churn_free)
    # ≈ 13 % ici. Le Gratuit publie désormais la fiche minimale (identité
    # vérifiée automatiquement, docs/PLAN.md §2-3) — le déclencheur n'est plus
    # "payez pour exister" mais "payez pour la profondeur, la fraîcheur et le
    # suivi". Cette hypothèse de conversion reste donc à confirmer sur de
    # vrais inscrits, comme avant : ce n'est pas parce que le registre est
    # plus honnête qu'il convertit forcément mieux.
    convert_rate: float = 0.015
    churn_free: float = 0.10
    cost_per_signup: float = 2       # contenu/SEO amorti (docs/VENTE.md §4.1)
    # Vérification de l'identité (SIREN/SIRET) : gratuite, l'API publique
    # recherche-entreprises.api.gouv.fr (source ouverte INSEE Sirene) ne
    # facture rien et autorise ~7 requêtes/seconde sans authentification —
    # largement suffisant à l'échelle de ce modèle. Ce chiffre couvre donc
    # seulement l'ingestion et le stockage, jamais la vérification elle-même.
    cost_free_per_user: float = 1

    # -- mouvement 2: sortant -> Exclusif (docs/VENTE.md, inchangé) -----------
    exclusif_slots_per_month: int = 4
    exclusif_slots_first_month: int = 1
    exclusif_sales_ramp_months: int = 6
    audits_per_exclusif_sale: int = 100
    cost_per_audit: float = 9
    cost_sales_per_sale: float = 1500
    cost_setup_per_exclusif_sale: float = 210

    # -- rétention --------------------------------------------------------------
    # Le Forfait se résilie en un clic, sans quoi que ce soit à céder: churn
    # proche d'un SaaS TPE générique. L'Exclusif a un coût de sortie réel
    # (le créneau part à un concurrent), churn nettement plus bas.
    monthly_churn_forfait: float = 0.06
    monthly_churn_exclusif: float = 0.025

    # -- coûts de service ------------------------------------------------------
    cost_measure_per_forfait_client: float = 3    # 1 moteur, cadence allégée
    cost_ops_per_forfait_client: float = 3         # self-serve, quasi automatisé
    cost_measure_per_exclusif_client: float = 11   # 2 moteurs, panier complet
    cost_ops_per_exclusif_client: float = 120      # distribution active, revue trimestrielle

    fixed_monthly: float = 14000   # équipe et structure, plus légères qu'un modèle 100 % sortant

    # -- dérivés, mouvement Forfait --------------------------------------------
    @property
    def gross_margin_forfait(self) -> float:
        return (
            self.forfait_price
            - self.cost_measure_per_forfait_client
            - self.cost_ops_per_forfait_client
        )

    @property
    def eventual_conversion_share(self) -> float:
        """Fraction des inscrits gratuits qui finissent par payer."""
        return self.convert_rate / (self.convert_rate + self.churn_free)

    @property
    def effective_cac_forfait(self) -> float:
        """Le vrai coût d'un client Forfait: hébergement de tous les gratuits
        qui ne convertissent jamais inclus, pas seulement du converti."""
        avg_free_tenure = 1 / (self.convert_rate + self.churn_free)
        cost_per_signup_lifetime = self.cost_per_signup + avg_free_tenure * self.cost_free_per_user
        return cost_per_signup_lifetime / self.eventual_conversion_share

    @property
    def lifetime_months_forfait(self) -> float:
        return 1 / self.monthly_churn_forfait

    @property
    def ltv_forfait(self) -> float:
        return self.gross_margin_forfait * self.lifetime_months_forfait

    @property
    def payback_months_forfait(self) -> float:
        return self.effective_cac_forfait / self.gross_margin_forfait

    # -- dérivés, mouvement Exclusif --------------------------------------------
    @property
    def gross_margin_exclusif(self) -> float:
        return (
            self.exclusif_price
            - self.cost_measure_per_exclusif_client
            - self.cost_ops_per_exclusif_client
        )

    @property
    def cac_exclusif(self) -> float:
        return self.audits_per_exclusif_sale * self.cost_per_audit + self.cost_sales_per_sale

    @property
    def lifetime_months_exclusif(self) -> float:
        return 1 / self.monthly_churn_exclusif

    @property
    def ltv_exclusif(self) -> float:
        recurring = self.gross_margin_exclusif * self.lifetime_months_exclusif
        return recurring + (self.setup_fee_exclusif - self.cost_setup_per_exclusif_sale)

    @property
    def payback_months_exclusif(self) -> float:
        return self.cac_exclusif / self.gross_margin_exclusif


@dataclass
class MonthRow:
    month: int
    free_users: int
    forfait_clients: int
    exclusif_clients: int
    mrr: float
    revenue: float
    variable_cost: float
    ebitda: float
    cumulative: float


def _ramp(first: float, steady: float, ramp_months: int, month: int) -> float:
    if month >= ramp_months:
        return steady
    span = max(1, ramp_months - 1)
    progress = (month - 1) / span
    return first + (steady - first) * progress


def project(a: Assumptions, months: int) -> list[MonthRow]:
    rows: list[MonthRow] = []
    free_users = 0.0
    forfait_clients = 0.0
    exclusif_clients = 0.0
    cumulative = 0.0

    for month in range(1, months + 1):
        new_signups = _ramp(
            a.free_signups_first_month, a.free_signups_steady, a.free_signups_ramp_months, month
        )
        exclusif_sold = _ramp(
            a.exclusif_slots_first_month, a.exclusif_slots_per_month,
            a.exclusif_sales_ramp_months, month,
        )

        newly_converted = free_users * a.convert_rate
        free_users = free_users * (1 - a.convert_rate - a.churn_free) + new_signups
        forfait_clients = forfait_clients * (1 - a.monthly_churn_forfait) + newly_converted
        exclusif_clients = exclusif_clients * (1 - a.monthly_churn_exclusif) + exclusif_sold

        mrr = forfait_clients * a.forfait_price + exclusif_clients * a.exclusif_price
        setup_revenue = exclusif_sold * a.setup_fee_exclusif
        revenue = mrr + setup_revenue

        variable = (
            free_users * a.cost_free_per_user
            + new_signups * a.cost_per_signup
            + forfait_clients * (a.cost_measure_per_forfait_client + a.cost_ops_per_forfait_client)
            + exclusif_clients * (a.cost_measure_per_exclusif_client + a.cost_ops_per_exclusif_client)
            + exclusif_sold * (a.cost_setup_per_exclusif_sale + a.cac_exclusif)
        )
        ebitda = revenue - variable - a.fixed_monthly
        cumulative += ebitda

        rows.append(
            MonthRow(
                month=month,
                free_users=round(free_users),
                forfait_clients=round(forfait_clients),
                exclusif_clients=round(exclusif_clients),
                mrr=mrr,
                revenue=revenue,
                variable_cost=variable,
                ebitda=ebitda,
                cumulative=cumulative,
            )
        )
    return rows


def render(a: Assumptions, rows: list[MonthRow]) -> str:
    out: list[str] = []
    out.append("MOUVEMENT 1 — GRATUIT -> FORFAIT (19 €/mois, self-serve)")
    out.append(
        f"  Conversion éventuelle des inscrits gratuits   {a.eventual_conversion_share:>8.1%}"
    )
    out.append(f"  Marge brute mensuelle / client Forfait        {eur(a.gross_margin_forfait):>10}")
    out.append(f"  CAC effectif (gratuits jamais convertis inclus) {eur(a.effective_cac_forfait):>8}")
    out.append(f"  Retour sur CAC                                {a.payback_months_forfait:>7.1f} mois")
    out.append(f"  LTV                                           {eur(a.ltv_forfait):>10}")
    out.append(f"  LTV / CAC                                     {a.ltv_forfait / a.effective_cac_forfait:>9.1f}x")
    out.append("")
    out.append("MOUVEMENT 2 — SORTANT -> EXCLUSIF (docs/VENTE.md, inchangé)")
    out.append(f"  Marge brute mensuelle / client Exclusif       {eur(a.gross_margin_exclusif):>10}")
    out.append(f"  CAC ({a.audits_per_exclusif_sale} audits + closing)                  {eur(a.cac_exclusif):>10}")
    out.append(f"  Retour sur CAC                                {a.payback_months_exclusif:>7.1f} mois")
    out.append(f"  LTV                                           {eur(a.ltv_exclusif):>10}")
    out.append(f"  LTV / CAC                                     {a.ltv_exclusif / a.cac_exclusif:>9.1f}x")
    out.append("")

    breakeven = next((r.month for r in rows if r.ebitda > 0), None)
    cash_positive = next((r.month for r in rows if r.cumulative > 0), None)
    trough = min(rows, key=lambda r: r.cumulative)
    out.append("SEUILS (mouvements combinés)")
    out.append(f"  EBITDA mensuel positif           {f'mois {breakeven}' if breakeven else 'jamais':>12}")
    out.append(f"  Cumul positif                    {f'mois {cash_positive}' if cash_positive else 'jamais':>12}")
    out.append(f"  Besoin de trésorerie maximal     {eur(-trough.cumulative):>12}  (mois {trough.month})")
    out.append("")

    out.append("TRAJECTOIRE")
    out.append(
        f"  {'mois':>4} {'gratuits':>9} {'forfait':>8} {'exclusif':>9} "
        f"{'MRR':>11} {'EBITDA':>12} {'cumul':>13}"
    )
    for row in rows:
        if row.month % 3 == 0 or row.month == 1:
            out.append(
                f"  {row.month:>4} {row.free_users:>9} {row.forfait_clients:>8} "
                f"{row.exclusif_clients:>9} {eur(row.mrr):>12} {eur(row.ebitda):>13} "
                f"{eur(row.cumulative):>14}"
            )
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--months", type=int, default=24)
    parser.add_argument("--free-signups", type=int, default=None, help="inscriptions gratuites/mois en régime")
    parser.add_argument("--convert-rate", type=float, default=None, help="taux mensuel gratuit -> Forfait")
    parser.add_argument("--exclusif-slots-per-month", type=int, default=None)
    parser.add_argument("--fixed", type=float, default=None, help="coûts fixes mensuels")
    args = parser.parse_args(argv)

    assumptions = Assumptions()
    if args.free_signups is not None:
        assumptions.free_signups_steady = args.free_signups
    if args.convert_rate is not None:
        assumptions.convert_rate = args.convert_rate
    if args.exclusif_slots_per_month is not None:
        assumptions.exclusif_slots_per_month = args.exclusif_slots_per_month
    if args.fixed is not None:
        assumptions.fixed_monthly = args.fixed

    print(render(assumptions, project(assumptions, args.months)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
