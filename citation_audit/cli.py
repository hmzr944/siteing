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


def _capture_wave(args) -> int:
    from datetime import date

    from .evolution import capture

    market = Market.load(args.market)
    prompts, runs = _run(market, args.provider or ["synthetic"], args.archive)
    moment = date.fromisoformat(args.date) if args.date else date.today()
    wave = capture(market, prompts, runs, observed_on=moment, label=args.label)

    path = args.out / f"{market.id}-{moment.isoformat()}.json"
    wave.save(path)
    print(
        f"VAGUE {args.label or moment.isoformat()} — {market.label}\n"
        f"{wave.prompt_count} prompts exploitables · {len(wave.entity_ids)} entités\n"
        f"panier {wave.basket_version} · moteurs {', '.join(wave.providers)} · "
        f"preuve {wave.evidence}\n\narchivée : {path}"
    )
    return 0


def _compare_waves(args) -> int:
    from .evolution import Incomparable, Wave, client_report, compare, to_text

    market = Market.load(args.market)
    before, after = Wave.load(args.avant), Wave.load(args.apres)
    try:
        comparison = compare(market, before, after)
    except Incomparable as exc:
        print(f"comparaison impossible : {exc}", file=sys.stderr)
        return 2

    print(to_text(comparison, market))
    if args.client:
        print("\n" + "=" * 72 + "\n")
        print(client_report(comparison, market, args.client))

    if args.out:
        args.out.mkdir(parents=True, exist_ok=True)
        path = (
            args.out
            / f"{market.id}-{before.observed_on}-{after.observed_on}.json"
        )
        path.write_text(
            json.dumps(comparison.to_dict(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"\nannexe : {path}")
    return 0


def _track_entity(args) -> int:
    from .evolution import Wave, track, track_to_text

    market = Market.load(args.market)
    entity = market.entity(args.client)
    waves = [Wave.load(p) for p in args.vagues]
    points = track(waves, entity.id)
    print(track_to_text(points, entity.name))

    if args.out:
        args.out.mkdir(parents=True, exist_ok=True)
        path = args.out / f"{market.id}-{entity.id}-suivi.json"
        path.write_text(
            json.dumps(
                [
                    {
                        "label": p.label,
                        "observed_on": p.observed_on.isoformat(),
                        "presence_rate": round(p.presence_rate, 4),
                        "citation_share": round(p.citation_share, 4),
                        "blind_spot_count": p.blind_spot_count,
                        "evidence": p.evidence,
                    }
                    for p in points
                ],
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        print(f"\nannexe : {path}")
    return 0


def _scaffold_market(args) -> int:
    from .market import scaffold

    market = scaffold(
        client_name=args.client,
        category=args.categorie,
        zone=args.zone,
        competitors=args.concurrent or [],
        client_domain=args.client_domain or "",
        market_id=args.id or "",
    )
    payload = {
        "id": market.id,
        "label": market.label,
        "category": market.category,
        "zone": market.zone,
        "entities": [
            {
                "name": e.name,
                "is_client": e.is_client,
                "domains": list(e.domains),
            }
            for e in market.entities
        ],
    }
    text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    out_path = args.out or Path("markets") / f"{market.id}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(text, encoding="utf-8")
    print(f"marché : {out_path}\n{len(market.basket())} prompts dans le panier")
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

    wave = sub.add_parser("vague", help="capture une vague datée et l'archive")
    wave.add_argument("market")
    wave.add_argument("--provider", action="append", default=None, metavar="SPEC")
    wave.add_argument("--date", help="date du relevé (AAAA-MM-JJ)")
    wave.add_argument("--label", default="", help="libellé de la vague, ex. J30")
    wave.add_argument("--out", type=Path, default=Path("vagues"))
    wave.add_argument("--archive", type=Path, help="archivage des réponses brutes")

    evo = sub.add_parser(
        "evolution", help="compare deux vagues archivées, avec groupe témoin"
    )
    evo.add_argument("market")
    evo.add_argument("--avant", required=True, type=Path)
    evo.add_argument("--apres", required=True, type=Path)
    evo.add_argument("--client", help="produit en plus le rapport mensuel de cette entité")
    evo.add_argument("--out", type=Path, help="dossier de sortie (JSON)")

    track = sub.add_parser(
        "suivi", help="progression descriptive d'une entité à travers plusieurs vagues"
    )
    track.add_argument("market")
    track.add_argument("--client", required=True, help="identifiant de l'entité suivie")
    track.add_argument("--vagues", required=True, nargs="+", type=Path)
    track.add_argument("--out", type=Path, help="dossier de sortie (JSON)")

    amorce = sub.add_parser(
        "amorce", help="génère un fichier de marché minimal pour une entreprise réelle"
    )
    amorce.add_argument("client", help="nom de l'entreprise réelle")
    amorce.add_argument("categorie", help="catégorie, ex. plombier")
    amorce.add_argument("zone", help="zone, ex. Bordeaux")
    amorce.add_argument(
        "--concurrent", action="append", default=[], metavar="NOM",
        help="nom d'un concurrent local (répétable, au moins un requis)",
    )
    amorce.add_argument("--client-domain", help="domaine du site du client, si connu")
    amorce.add_argument("--id", help="identifiant du marché (déduit du nom sinon)")
    amorce.add_argument("--out", type=Path, help="chemin du fichier produit")

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

    if args.command == "vague":
        return _capture_wave(args)

    if args.command == "evolution":
        return _compare_waves(args)

    if args.command == "suivi":
        return _track_entity(args)

    if args.command == "amorce":
        return _scaffold_market(args)

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
