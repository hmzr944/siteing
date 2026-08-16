"""Interface en ligne de commande.

    python -m citation_audit basket markets/plombier-bordeaux.json
    python -m citation_audit audit  markets/plombier-bordeaux.json --provider synthetic:7
    python -m citation_audit audit  markets/plombier-bordeaux.json \
        --provider anthropic:claude-sonnet-5 --provider anthropic:claude-opus-5 \
        --archive archives/ --out out/
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import providers as providers_module
from .market import Market
from .report import to_html, to_text
from .score import compute


def _run(market: Market, specs: list[str], archive_dir: Path | None):
    prompts = market.basket()
    runs = []
    for spec in specs:
        try:
            provider = providers_module.build(spec, market)
        except (RuntimeError, ValueError) as exc:
            print(f"provider {spec!r} indisponible: {exc}", file=sys.stderr)
            continue
        responses = [provider.query(prompt) for prompt in prompts]
        runs.append((provider.name, provider.evidence, responses))
        if archive_dir is not None:
            providers_module.write_archive(
                archive_dir / f"{market.id}-{provider.name.replace(':', '-')}.json",
                provider.name,
                responses,
                prompts,
            )
    if not runs:
        raise SystemExit("aucun moteur interrogeable: audit impossible")
    return prompts, runs


def _measure_cohort(args) -> int:
    from .cohort import measure, to_text as cohort_text

    market = Market.load(args.market)
    if market.has_client:
        print(
            "attention: ce marché désigne un client. Une ligne de base se mesure "
            "sur un panel sans client, sinon la mesure porte un biais de cadrage.",
            file=sys.stderr,
        )
    prompts, runs = _run(market, args.provider or ["synthetic"], args.archive)
    result = measure(market, prompts, runs)
    print(cohort_text(result))

    if args.out:
        args.out.mkdir(parents=True, exist_ok=True)
        path = args.out / f"{market.id}-ligne-de-base.json"
        path.write_text(
            json.dumps(result.to_dict(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"\nannexe : {path}")
    return 0


def _publish_dossier(args) -> int:
    from .creneau import Registry
    from .dossier import DECLARED, EXPIRED, REFUTED, VERIFIED, Dossier
    from .publish import write_bundle

    dossier = Dossier.load(args.dossier)
    registry = Registry.load(args.registry) if args.registry else None
    counts = dossier.counts()

    print(f"DOSSIER DE VÉRITÉ — {dossier.name}")
    print(f"{dossier.category} · {dossier.zone}")
    print(
        f"vérifiées {counts[VERIFIED]} · déclarées {counts[DECLARED]} · "
        f"expirées {counts[EXPIRED]} · réfutées {counts[REFUTED]} "
        f"({dossier.verified_ratio():.0%} du dossier vérifié)"
    )

    expiring = dossier.expiring_soon()
    if expiring:
        print("\nÀ RENOUVELER SOUS 60 JOURS")
        for claim in expiring:
            print(f"  · {claim.label} — expire le {claim.valid_until} "
                  f"({claim.days_until_expiry()} jours)")

    stale = dossier.stale()
    if stale:
        print("\nNON PUBLIÉ VERS LA COUCHE MACHINE")
        for claim in stale:
            print(f"  · {claim.label} ({claim.status_label().lower()})")

    written = write_bundle(args.out, dossier, registry, args.url)
    print("\nPUBLIÉ")
    for name, path in written.items():
        print(f"  {path}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="citation_audit",
        description="Mesure la Part de Citation d'une entreprise dans les moteurs de réponse.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    basket = sub.add_parser("basket", help="affiche le panier de prompts figé du marché")
    basket.add_argument("market")

    audit = sub.add_parser("audit", help="interroge les moteurs et produit le relevé")
    audit.add_argument("market")
    audit.add_argument(
        "--provider",
        action="append",
        default=None,
        metavar="SPEC",
        help="synthetic[:graine] | fixture:chemin.json | anthropic[:modèle] (répétable)",
    )
    audit.add_argument("--out", type=Path, help="dossier de sortie (rapport HTML + JSON)")
    audit.add_argument("--archive", type=Path, help="dossier d'archivage des réponses brutes")

    baseline = sub.add_parser(
        "cohorte", help="mesure la ligne de base d'un panel d'entreprises"
    )
    baseline.add_argument("market")
    baseline.add_argument("--provider", action="append", default=None, metavar="SPEC")
    baseline.add_argument("--out", type=Path, help="dossier de sortie (JSON)")
    baseline.add_argument("--archive", type=Path, help="dossier d'archivage des réponses")

    publish = sub.add_parser(
        "dossier", help="publie un Dossier de Vérité (page publique + sorties machine)"
    )
    publish.add_argument("dossier")
    publish.add_argument("--out", type=Path, default=Path("out"))
    publish.add_argument("--registry", type=Path, help="registre des créneaux (JSON)")
    publish.add_argument("--url", help="URL publique de la page, incluse au manifeste")

    args = parser.parse_args(argv)

    if args.command == "dossier":
        return _publish_dossier(args)

    if args.command == "cohorte":
        return _measure_cohort(args)

    market = Market.load(args.market)

    if args.command == "basket":
        prompts = market.basket()
        print(f"{market.label} — panier {market.basket_version} — {len(prompts)} prompts\n")
        current = None
        for prompt in prompts:
            if prompt.family != current:
                current = prompt.family
                print(f"[{current}]  poids {prompt.weight}")
            print(f"  {prompt.id}  {prompt.text}")
        return 0

    prompts, runs = _run(market, args.provider or ["synthetic"], args.archive)
    result = compute(market, prompts, runs)
    print(to_text(result))

    if args.out:
        args.out.mkdir(parents=True, exist_ok=True)
        html_path = args.out / f"{market.id}-audit.html"
        json_path = args.out / f"{market.id}-audit.json"
        html_path.write_text(to_html(result), encoding="utf-8")
        json_path.write_text(
            json.dumps(result.to_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(f"\nrapport : {html_path}\nannexe  : {json_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
