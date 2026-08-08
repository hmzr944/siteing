"""Rendu de l'audit: synthèse terminal et rapport HTML remis au dirigeant.

Le rapport HTML est l'objet commercial du modèle. Sa contrainte de conception
est inhabituelle: il doit avoir l'air d'un **instrument de mesure**, pas d'une
plaquette. Un dirigeant à qui l'on annonce qu'il est invisible croit un relevé
et se méfie d'une publicité — donc étiquette d'échantillon, filets fins, chiffres
tabulaires, hypothèses affichées, et une seule couleur chaude employée trois
fois: le taux de présence, le montant perdu, sa propre barre.
"""

from __future__ import annotations

import html
from datetime import datetime

from .score import AuditResult

NBSP = " "

FAMILY_LABELS = {
    "decouverte": "Découverte",
    "comparaison": "Comparaison",
    "contrainte": "Contrainte",
    "probleme": "Problème",
    "transactionnel": "Transactionnel",
    "verification": "Vérification",
}

FAMILY_HINTS = {
    "decouverte": "« quel {cat} choisir »",
    "comparaison": "« le meilleur {cat} »",
    "contrainte": "urgence, horaires, budget",
    "probleme": "un besoin précis à résoudre",
    "transactionnel": "devis, commande, intervention",
    "verification": "réputation d'une marque nommée",
}


def pct(value: float, decimals: int = 0) -> str:
    formatted = f"{value * 100:.{decimals}f}".replace(".", ",")
    return f"{formatted}{NBSP}%"


def eur(value: float) -> str:
    return f"{value:,.0f}".replace(",", NBSP) + f"{NBSP}€"


# -- synthèse terminal ---------------------------------------------------------


def to_text(result: AuditResult) -> str:
    client = result.client_score
    lines = [
        f"AUDIT D'INVISIBILITÉ — {result.label}",
        f"{result.category} · {result.zone} · panier {result.basket_version} · "
        f"{result.usable_prompt_count}/{result.prompt_count} prompts exploitables",
        f"moteurs: {', '.join(result.providers)} · niveau de preuve: {result.evidence}",
        "",
        f"Taux de Présence     {pct(client.presence_rate, 1):>10}",
        f"Part de Citation     {pct(client.citation_share, 1):>10}",
        f"Rang moyen           {(f'{client.avg_rank:.1f}' if client.avg_rank else '—'):>10}",
    ]
    if result.value_estimate:
        estimate = result.value_estimate
        lines.append(f"Part équitable       {pct(estimate.fair_share, 1):>10}")
        lines.append(f"Écart valorisé/an    {eur(estimate.annual_missed):>10}")

    lines += ["", "CLASSEMENT"]
    for position, score in enumerate(result.scores, start=1):
        marker = "▸" if score.is_client else " "
        lines.append(
            f"{marker} {position:>2}. {score.name[:34]:<34} "
            f"part {pct(score.citation_share, 1):>7}   présence {pct(score.presence_rate, 0):>6}"
        )

    if result.blind_spots:
        lines += ["", f"ANGLES MORTS ({len(result.blind_spots)})"]
        for spot in result.blind_spots[:8]:
            lines.append(f"  · {spot.text}")
            lines.append(f"      cité à votre place : {', '.join(spot.competitors)}")
        if len(result.blind_spots) > 8:
            lines.append(f"  … et {len(result.blind_spots) - 8} autre(s)")

    if result.warnings:
        lines += ["", "RÉSERVES"]
        lines += [f"  ! {w}" for w in result.warnings]

    return "\n".join(lines)


# -- rapport HTML --------------------------------------------------------------

CSS = """
:root{
  --ground:#f5f7f8; --panel:#ffffff; --rule:#dde3e7; --rule-soft:#eaeff2;
  --ink:#111721; --ink-soft:#4a545f; --ink-mute:#7b868f;
  --measure:#1c6e6b; --measure-soft:#d7e5e4; --flag:#a8481b; --flag-soft:#f3e0d6;
  --shadow:0 1px 2px rgba(17,23,33,.05), 0 8px 24px -18px rgba(17,23,33,.35);
  --serif:ui-serif,Georgia,"Iowan Old Style","Times New Roman",serif;
  --sans:ui-sans-serif,-apple-system,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
  --mono:ui-monospace,SFMono-Regular,"SF Mono",Menlo,Consolas,monospace;
}
@media (prefers-color-scheme:dark){
  :root:not([data-theme="light"]){
    --ground:#0f131a; --panel:#161c25; --rule:#2a333f; --rule-soft:#212a34;
    --ink:#e8edf1; --ink-soft:#a8b3bd; --ink-mute:#76818c;
    --measure:#5fb8b3; --measure-soft:#1e3a3a; --flag:#e08a55; --flag-soft:#3a2419;
    --shadow:0 1px 2px rgba(0,0,0,.4), 0 8px 24px -18px rgba(0,0,0,.8);
  }
}
:root[data-theme="dark"]{
  --ground:#0f131a; --panel:#161c25; --rule:#2a333f; --rule-soft:#212a34;
  --ink:#e8edf1; --ink-soft:#a8b3bd; --ink-mute:#76818c;
  --measure:#5fb8b3; --measure-soft:#1e3a3a; --flag:#e08a55; --flag-soft:#3a2419;
  --shadow:0 1px 2px rgba(0,0,0,.4), 0 8px 24px -18px rgba(0,0,0,.8);
}

*{box-sizing:border-box}
body{
  margin:0; background:var(--ground); color:var(--ink);
  font-family:var(--sans); font-size:16px; line-height:1.6;
  -webkit-font-smoothing:antialiased;
}
.sheet{max-width:60rem; margin:0 auto; padding:clamp(1.25rem,4vw,3.5rem) clamp(1rem,4vw,2.5rem) 5rem}
.stack{display:flex; flex-direction:column}

.label{
  font-family:var(--mono); font-size:.6875rem; letter-spacing:.14em;
  text-transform:uppercase; color:var(--ink-mute); margin:0;
}
h1{font-family:var(--serif); font-weight:500; font-size:clamp(1.75rem,4.5vw,2.5rem);
   line-height:1.15; letter-spacing:-.015em; margin:0; text-wrap:balance}
h2{font-family:var(--serif); font-weight:500; font-size:1.3rem; letter-spacing:-.01em;
   margin:0; text-wrap:balance}
p{margin:0; max-width:64ch}
a{color:var(--measure)}

/* étiquette d'échantillon ------------------------------------------------- */
.masthead{border-top:2px solid var(--ink); padding-top:1rem; gap:1.5rem}
.specimen{
  display:grid; grid-template-columns:repeat(auto-fit,minmax(9.5rem,1fr));
  gap:1px; background:var(--rule); border:1px solid var(--rule);
}
.specimen div{background:var(--panel); padding:.625rem .75rem; display:flex;
  flex-direction:column; gap:.15rem}
.specimen dt{font-family:var(--mono); font-size:.625rem; letter-spacing:.12em;
  text-transform:uppercase; color:var(--ink-mute)}
.specimen dd{margin:0; font-family:var(--mono); font-size:.8125rem; color:var(--ink);
  font-variant-numeric:tabular-nums; overflow-wrap:anywhere}

/* bandeau de réserve ------------------------------------------------------ */
.flagbar{
  border-left:3px solid var(--flag); background:var(--flag-soft);
  padding:.875rem 1.125rem; display:flex; flex-direction:column; gap:.35rem;
}
.flagbar strong{font-family:var(--mono); font-size:.6875rem; letter-spacing:.14em;
  text-transform:uppercase; color:var(--flag)}
.flagbar p{font-size:.875rem; color:var(--ink-soft)}

/* verdict ---------------------------------------------------------------- */
.verdict{display:grid; grid-template-columns:repeat(auto-fit,minmax(13rem,1fr)); gap:1px;
  background:var(--rule); border:1px solid var(--rule); box-shadow:var(--shadow)}
.metric{background:var(--panel); padding:1.5rem 1.375rem; display:flex;
  flex-direction:column; gap:.5rem}
.metric .figure{font-family:var(--serif); font-size:clamp(2.5rem,7vw,3.75rem);
  line-height:.95; letter-spacing:-.03em; font-variant-numeric:tabular-nums}
.metric.hot .figure{color:var(--flag)}
.metric .note{font-size:.8125rem; color:var(--ink-mute); line-height:1.45}

/* classement ------------------------------------------------------------- */
.board{display:flex; flex-direction:column; gap:1px; background:var(--rule-soft);
  border-top:1px solid var(--rule); border-bottom:1px solid var(--rule)}
.row{background:var(--panel); display:grid;
  grid-template-columns:2.25rem minmax(7rem,1.6fr) minmax(6rem,3fr) 5rem;
  align-items:center; gap:.75rem; padding:.6875rem .75rem}
.row .rank{font-family:var(--mono); font-size:.75rem; color:var(--ink-mute);
  font-variant-numeric:tabular-nums}
.row .who{font-size:.9375rem; overflow-wrap:anywhere}
.row.self .who{font-weight:650; color:var(--flag)}
.row.self .rank{color:var(--flag)}
.track{height:.5rem; background:var(--measure-soft); border-radius:1px; overflow:hidden}
.fill{height:100%; background:var(--measure); border-radius:1px;
  transform-origin:left center; animation:grow .7s cubic-bezier(.2,.7,.3,1) both}
.row.self .track{background:var(--flag-soft)}
.row.self .fill{background:var(--flag)}
.row .share{font-family:var(--mono); font-size:.8125rem; text-align:right;
  font-variant-numeric:tabular-nums; color:var(--ink-soft)}
@keyframes grow{from{transform:scaleX(0)}to{transform:scaleX(1)}}
@media (prefers-reduced-motion:reduce){.fill{animation:none}}

/* angles morts ----------------------------------------------------------- */
.spots{display:flex; flex-direction:column; gap:1px; background:var(--rule-soft);
  border-top:1px solid var(--rule); border-bottom:1px solid var(--rule)}
.spot{background:var(--panel); padding:.875rem .875rem .875rem 1rem;
  border-left:2px solid var(--flag); display:flex; flex-direction:column; gap:.4rem}
.spot .q{font-family:var(--mono); font-size:.8125rem; line-height:1.5; color:var(--ink)}
.spot .instead{font-size:.8125rem; color:var(--ink-soft)}
.spot .instead b{font-weight:600; color:var(--measure)}
.spot .fam{font-family:var(--mono); font-size:.625rem; letter-spacing:.12em;
  text-transform:uppercase; color:var(--ink-mute)}

/* familles --------------------------------------------------------------- */
.grid-table{width:100%; border-collapse:collapse; font-size:.875rem}
.grid-table th,.grid-table td{text-align:left; padding:.5rem .625rem;
  border-bottom:1px solid var(--rule-soft)}
.grid-table thead th{font-family:var(--mono); font-size:.625rem; letter-spacing:.12em;
  text-transform:uppercase; color:var(--ink-mute); border-bottom:1px solid var(--rule)}
.grid-table td.num{font-family:var(--mono); text-align:right;
  font-variant-numeric:tabular-nums}
.grid-table td.hint{color:var(--ink-mute); font-size:.8125rem}
.scroll{overflow-x:auto}

/* méthode --------------------------------------------------------------- */
.method{background:var(--panel); border:1px solid var(--rule); padding:1.25rem 1.375rem;
  display:flex; flex-direction:column; gap:.75rem}
.method p,.method li{font-size:.875rem; color:var(--ink-soft)}
.method ul{margin:0; padding-left:1.1rem; display:flex; flex-direction:column; gap:.4rem}
.method code{font-family:var(--mono); font-size:.8125rem; color:var(--ink)}
footer{border-top:1px solid var(--rule); padding-top:1rem; font-size:.75rem;
  color:var(--ink-mute); font-family:var(--mono)}
"""


def _specimen(result: AuditResult) -> str:
    generated = result.generated_at.replace("T", " ").replace("+00:00", " UTC")
    fields = [
        ("Marché", result.label),
        ("Catégorie", result.category),
        ("Zone", result.zone),
        ("Panier", result.basket_version),
        ("Prompts", f"{result.usable_prompt_count}/{result.prompt_count}"),
        ("Moteurs", ", ".join(result.providers) or "—"),
        ("Preuve", result.evidence),
        ("Relevé", generated),
    ]
    cells = "".join(
        f"<div><dt>{html.escape(name)}</dt><dd>{html.escape(str(value))}</dd></div>"
        for name, value in fields
    )
    return f'<dl class="specimen">{cells}</dl>'


def _verdict(result: AuditResult) -> str:
    client = result.client_score
    metrics = [
        (
            "hot",
            pct(client.presence_rate, 0),
            "Taux de Présence",
            f"Vous apparaissez sur {round(client.presence_rate * result.usable_prompt_count)} "
            f"des {result.usable_prompt_count} questions d'achat testées.",
        ),
        (
            "",
            pct(client.citation_share, 1),
            "Part de Citation",
            f"Part de la voix captée sur votre marché. Le leader, "
            f"{html.escape(result.leader.name)}, en capte {pct(result.leader.citation_share, 1)}.",
        ),
    ]
    if result.value_estimate:
        estimate = result.value_estimate
        metrics.append(
            (
                "hot",
                eur(estimate.annual_missed),
                "Écart à votre part équitable, par an",
                f"Part équitable {pct(estimate.fair_share, 1)} − part captée "
                f"{pct(estimate.captured_share, 1)} = {pct(estimate.share_gap, 1)} "
                f"de la voix du marché, appliqués à {estimate.monthly_intent_volume} "
                f"recherches/mois × {pct(estimate.close_rate, 0)} de transformation "
                f"× {eur(estimate.avg_deal_value)} par affaire.",
            )
        )
    cells = "".join(
        f'<div class="metric {tone}"><span class="figure">{figure}</span>'
        f'<p class="label">{html.escape(label)}</p>'
        f'<p class="note">{note}</p></div>'
        for tone, figure, label, note in metrics
    )
    return f'<div class="verdict">{cells}</div>'


def _board(result: AuditResult) -> str:
    top = max((s.citation_share for s in result.scores), default=0.0) or 1.0
    rows = []
    for position, score in enumerate(result.scores, start=1):
        # Une part réellement nulle se dessine vide. Un plancher de barre
        # laisserait croire à une présence résiduelle qui n'existe pas.
        width = 0.0 if score.citation_share <= 0 else max(1.5, score.citation_share / top * 100)
        classes = "row self" if score.is_client else "row"
        rows.append(
            f'<div class="{classes}">'
            f'<span class="rank">{position:02d}</span>'
            f'<span class="who">{html.escape(score.name)}</span>'
            f'<span class="track"><span class="fill" style="width:{width:.1f}%"></span></span>'
            f'<span class="share">{pct(score.citation_share, 1)}</span>'
            f"</div>"
        )
    return f'<div class="board">{"".join(rows)}</div>'


def _spots(result: AuditResult, limit: int = 12) -> str:
    if not result.blind_spots:
        return (
            '<p class="note">Aucun angle mort: vous apparaissez partout où au moins '
            "un concurrent apparaît.</p>"
        )
    items = []
    for spot in result.blind_spots[:limit]:
        instead = ", ".join(f"<b>{html.escape(name)}</b>" for name in spot.competitors)
        items.append(
            f'<div class="spot">'
            f'<span class="fam">{html.escape(FAMILY_LABELS.get(spot.family, spot.family))}</span>'
            f'<span class="q">{html.escape(spot.text)}</span>'
            f'<span class="instead">Cité à votre place&nbsp;: {instead}</span>'
            f"</div>"
        )
    more = ""
    if len(result.blind_spots) > limit:
        more = (
            f'<p class="note">… et {len(result.blind_spots) - limit} autre(s) question(s) '
            "détaillée(s) dans l'annexe JSON.</p>"
        )
    return f'<div class="spots">{"".join(items)}</div>{more}'


def _families(result: AuditResult) -> str:
    client = result.client_score
    leader = result.leader
    rows = []
    for family, label in FAMILY_LABELS.items():
        if family not in client.by_family:
            continue
        hint = FAMILY_HINTS.get(family, "").replace("{cat}", result.category)
        rows.append(
            f"<tr><td>{html.escape(label)}</td>"
            f'<td class="hint">{html.escape(hint)}</td>'
            f'<td class="num">{pct(client.by_family.get(family, 0.0), 1)}</td>'
            f'<td class="num">{pct(leader.by_family.get(family, 0.0), 1)}</td></tr>'
        )
    if not rows:
        return ""
    return (
        '<div class="scroll"><table class="grid-table">'
        "<thead><tr><th>Famille de question</th><th>Ce que cherche l'acheteur</th>"
        f"<th>Vous</th><th>{html.escape(leader.name[:22])}</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table></div>"
    )


def _method(result: AuditResult) -> str:
    warnings = "".join(f"<li>{html.escape(w)}</li>" for w in result.warnings)
    warnings_block = f"<ul>{warnings}</ul>" if warnings else ""
    return f"""<div class="method">
<p class="label">Méthode</p>
<ul>
<li>Le panier de {result.prompt_count} questions est <strong>figé</strong> pour ce marché
(empreinte <code>{html.escape(result.basket_version)}</code>). Il est rejoué à l'identique
chaque mois: c'est ce qui rend deux relevés comparables.</li>
<li>La <strong>Part de Citation</strong> pondère chaque mention par l'intention commerciale de
la question et par le rang d'apparition, avec une décote logarithmique
(<code>1/log2(1+rang)</code>): premier cité 1,00 — deuxième 0,63 — troisième 0,50.</li>
<li>La détection n'accepte que des correspondances sur nom, alias ou domaine sourcé, avec
frontières de mots. Les termes génériques du marché sont exclus, pour ne jamais compter une
mention qui n'existe pas.</li>
<li>Les réponses brutes sont archivées. Tout chiffre de ce rapport est reconductible au
corpus exact qui l'a produit.</li>
<li>Ce relevé mesure ce que les moteurs de réponse restituent aujourd'hui. Il ne constitue
pas un engagement de position auprès d'un éditeur tiers&nbsp;: personne ne peut vendre cela.</li>
</ul>
{warnings_block}
</div>"""


def to_html(result: AuditResult, title: str | None = None) -> str:
    client = result.client_score
    heading = title or f"Vous êtes invisible sur {result.usable_prompt_count - round(client.presence_rate * result.usable_prompt_count)} des {result.usable_prompt_count} questions qui font acheter"
    year = datetime.now().year

    banner = ""
    if not result.is_presentable:
        reason = (
            "Moteur simulé — chiffres illustratifs"
            if result.evidence == "simulation"
            else "Échantillon insuffisant"
        )
        banner = f"""<div class="flagbar">
<strong>Document interne — ne pas remettre au client</strong>
<p>{html.escape(reason)}. Ce relevé démontre la mécanique de mesure&nbsp;; il n'a pas
valeur d'audit.</p></div>"""

    return f"""<title>Audit d'Invisibilité — {html.escape(result.label)}</title>
<style>{CSS}</style>
<main class="sheet stack" style="gap:2.75rem">

  <header class="masthead stack">
    <div class="stack" style="gap:.75rem">
      <p class="label">Audit d'Invisibilité · Source Primaire</p>
      <h1>{html.escape(heading)}</h1>
      <p style="color:var(--ink-soft)">Relevé de la présence de
      <strong>{html.escape(client.name)}</strong> dans les réponses générées par les moteurs
      d'IA sur le marché {html.escape(result.label)} — et de ce que vos concurrents y captent
      à votre place.</p>
    </div>
    {_specimen(result)}
  </header>

  {banner}

  <section class="stack" style="gap:1rem">
    <h2>Le relevé</h2>
    {_verdict(result)}
  </section>

  <section class="stack" style="gap:1rem">
    <h2>Qui capte la voix de votre marché</h2>
    <p style="color:var(--ink-soft)">Part de la citation disponible, pondérée par l'intention
    d'achat et le rang d'apparition.</p>
    {_board(result)}
  </section>

  <section class="stack" style="gap:1rem">
    <h2>Vos angles morts</h2>
    <p style="color:var(--ink-soft)">Les questions où vous n'existez pas, et le nom de
    l'entreprise citée à votre place.</p>
    {_spots(result)}
  </section>

  <section class="stack" style="gap:1rem">
    <h2>Où la perte se concentre</h2>
    {_families(result)}
  </section>

  {_method(result)}

  <footer>Source Primaire · panier {html.escape(result.basket_version)} ·
  relevé {html.escape(result.generated_at)} · © {year}</footer>
</main>"""
