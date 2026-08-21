"""La Page de Vérité: rendu public du Dossier de Vérité.

Deux lecteurs, un seul document. Un humain qui vérifie avant d'appeler, et un
agent qui parse. Le JSON-LD des affirmations vérifiées est embarqué dans la page:
elle est le point de publication, pas une brochure qui renvoie ailleurs.

Le parti de conception est contraint par le sujet. Une page de vérification qui
ressemble à une page de vente ne vérifie rien: pas de carte arrondie, pas de
pastille verte, pas d'animation. Des filets, des libellés, des dates, et une
section entière consacrée à ce qui **n'est pas** vérifié. C'est cette section qui
rend le reste croyable.

Aucune coche, aucune icône de validation: une coche verte est le signal de
confiance le moins coûteux à fabriquer, donc le moins crédible. Le statut est
porté par un libellé, une date de contrôle et la nature de la pièce.
"""

from __future__ import annotations

import html
import json
from datetime import date

from .dossier import DECLARED, EXPIRED, REFUTED, VERIFIED, Dossier
from .publish import PROTOCOL, to_jsonld

MONTHS = (
    "janvier", "février", "mars", "avril", "mai", "juin",
    "juillet", "août", "septembre", "octobre", "novembre", "décembre",
)

STATUS_CLASS = {
    VERIFIED: "verified",
    DECLARED: "declared",
    EXPIRED: "lapsed",
    REFUTED: "refuted",
}

STATUS_TEXT = {
    VERIFIED: "Vérifié",
    DECLARED: "Déclaré, non contrôlé",
    EXPIRED: "Contrôle expiré",
    REFUTED: "Réfuté",
}


def fr_date(value: date | None) -> str:
    if value is None:
        return "sans date"
    return f"{value.day} {MONTHS[value.month - 1]} {value.year}"


CSS = """
:root{
  --paper:#f6f7f4; --panel:#ffffff; --rule:#dbdfd8; --rule-soft:#e8ebe5;
  --ink:#141a17; --ink-soft:#4b544e; --ink-mute:#79837b;
  --pine:#1f5138; --pine-soft:#dfe9e2;
  --declared:#79837b; --lapsed:#8a5a12; --refuted:#8a2e22;
  --sans:system-ui,-apple-system,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
  --mono:ui-monospace,SFMono-Regular,"SF Mono",Menlo,Consolas,monospace;
}
@media (prefers-color-scheme:dark){
  :root:not([data-theme="light"]){
    --paper:#101512; --panel:#171d19; --rule:#2b332d; --rule-soft:#222a25;
    --ink:#e9eee9; --ink-soft:#a9b3ab; --ink-mute:#76817a;
    --pine:#7fb79a; --pine-soft:#1c2f26;
    --declared:#8a948c; --lapsed:#d1a05a; --refuted:#d98476;
  }
}
:root[data-theme="dark"]{
  --paper:#101512; --panel:#171d19; --rule:#2b332d; --rule-soft:#222a25;
  --ink:#e9eee9; --ink-soft:#a9b3ab; --ink-mute:#76817a;
  --pine:#7fb79a; --pine-soft:#1c2f26;
  --declared:#8a948c; --lapsed:#d1a05a; --refuted:#d98476;
}

*{box-sizing:border-box}
body{
  margin:0; background:var(--paper); color:var(--ink);
  font-family:var(--sans); font-size:16px; line-height:1.6;
  -webkit-font-smoothing:antialiased;
}
.sheet{max-width:56rem; margin:0 auto; padding:clamp(1.5rem,5vw,4rem) clamp(1rem,4vw,2rem) 4rem;
  display:flex; flex-direction:column; gap:3rem}
.block{display:flex; flex-direction:column}
a{color:var(--pine); text-decoration-thickness:1px; text-underline-offset:2px}
a:focus-visible,summary:focus-visible{outline:2px solid var(--pine); outline-offset:3px}

.eyebrow{font-family:var(--mono); font-size:.6875rem; letter-spacing:.16em;
  text-transform:uppercase; color:var(--ink-mute); margin:0}
h1{font-size:clamp(1.875rem,5vw,2.75rem); font-weight:600; line-height:1.1;
  letter-spacing:-.02em; margin:0; text-wrap:balance}
h2{font-size:1.125rem; font-weight:600; letter-spacing:-.005em; margin:0;
  padding-bottom:.625rem; border-bottom:1px solid var(--ink)}
h3{font-size:.9375rem; font-weight:600; margin:0; color:var(--ink-soft)}
p{margin:0; max-width:62ch; color:var(--ink-soft)}

/* identité --------------------------------------------------------------- */
.identity{gap:1rem; border-top:2px solid var(--ink); padding-top:1.25rem}
.identity .meta{display:flex; flex-wrap:wrap; gap:.375rem 1.25rem;
  font-family:var(--mono); font-size:.8125rem; color:var(--ink-soft);
  font-variant-numeric:tabular-nums}
.identity .meta span{display:inline-flex; gap:.4rem}
.identity .meta b{font-weight:500; color:var(--ink-mute)}
.portrait{width:100%; max-width:100%; height:auto; display:block;
  border:1px solid var(--rule)}

/* compteur de vérification ----------------------------------------------- */
.tally{display:flex; flex-wrap:wrap; gap:0; border:1px solid var(--rule);
  background:var(--panel)}
.tally div{flex:1 1 8rem; padding:.875rem 1rem; border-right:1px solid var(--rule-soft);
  display:flex; flex-direction:column; gap:.2rem}
.tally div:last-child{border-right:0}
.tally .n{font-size:1.5rem; font-weight:600; line-height:1;
  font-variant-numeric:tabular-nums}
.tally .k{font-family:var(--mono); font-size:.625rem; letter-spacing:.12em;
  text-transform:uppercase; color:var(--ink-mute)}
.tally .verified .n{color:var(--pine)}
.tally .lapsed .n{color:var(--lapsed)}
.tally .refuted .n{color:var(--refuted)}

/* affirmations ----------------------------------------------------------- */
.cluster{display:flex; flex-direction:column; gap:.75rem}
.claims{display:grid; grid-template-columns:repeat(auto-fit,minmax(17rem,1fr)); gap:1px;
  background:var(--rule-soft)}
.claim{background:var(--panel); padding:.875rem 1rem; border-left:3px solid var(--declared);
  display:flex; flex-direction:column; gap:.3rem}
.claim.verified{border-left-color:var(--pine)}
.claim.lapsed{border-left-color:var(--lapsed)}
.claim.refuted{border-left-color:var(--refuted)}
.claim .label{font-family:var(--mono); font-size:.625rem; letter-spacing:.12em;
  text-transform:uppercase; color:var(--ink-mute)}
.claim .value{font-size:.9375rem; color:var(--ink-soft)}
.claim.verified .value{color:var(--ink); font-weight:500}
.claim .state{font-size:.75rem; color:var(--declared)}
.claim.verified .state{color:var(--pine)}
.claim.lapsed .state{color:var(--lapsed)}
.claim.refuted .state{color:var(--refuted)}
.claim .proof{font-family:var(--mono); font-size:.6875rem; color:var(--ink-mute);
  line-height:1.5; overflow-wrap:anywhere}

/* ce qui n'est pas vérifié ----------------------------------------------- */
.gaps{border:1px solid var(--rule); background:var(--panel);
  display:flex; flex-direction:column}
.gaps li{list-style:none; padding:.75rem 1rem; border-bottom:1px solid var(--rule-soft);
  display:flex; flex-wrap:wrap; gap:.25rem 1rem; align-items:baseline}
.gaps li:last-child{border-bottom:0}
.gaps ul{margin:0; padding:0; display:flex; flex-direction:column}
.gaps .what{font-size:.9375rem; flex:1 1 12rem}
.gaps .why{font-family:var(--mono); font-size:.6875rem; letter-spacing:.06em;
  text-transform:uppercase; color:var(--lapsed)}
.gaps .why.declared{color:var(--declared)}
.gaps .why.refuted{color:var(--refuted)}

/* couche machine --------------------------------------------------------- */
.machine{border:1px solid var(--rule); background:var(--panel);
  padding:1.125rem 1.25rem; display:flex; flex-direction:column; gap:.75rem}
.machine dl{margin:0; display:grid; grid-template-columns:auto 1fr; gap:.4rem 1rem;
  font-family:var(--mono); font-size:.8125rem}
.machine dt{color:var(--ink-mute)}
.machine dd{margin:0; overflow-wrap:anywhere}
.machine code{font-family:var(--mono); font-size:.8125rem}

footer{border-top:1px solid var(--rule); padding-top:1rem; display:flex;
  flex-direction:column; gap:.4rem; font-size:.8125rem; color:var(--ink-mute)}
footer .protocol{font-family:var(--mono); font-size:.6875rem;
  font-variant-numeric:tabular-nums}
"""


def _identity(dossier: Dossier, today: date) -> str:
    last = dossier.last_verified_on(today)
    fields = [("Catégorie", dossier.category), ("Zone", dossier.zone)]
    if dossier.legal_id:
        fields.append(("SIREN", dossier.legal_id))
    fields.append(("Dernier contrôle", fr_date(last)))
    if dossier.updated_on:
        fields.append(("Dossier mis à jour", fr_date(dossier.updated_on)))

    meta = "".join(
        f"<span><b>{html.escape(name)}</b>{html.escape(str(value))}</span>"
        for name, value in fields
    )
    portrait = ""
    if dossier.photo_url:
        portrait = (
            f'<img class="portrait" src="{html.escape(dossier.photo_url)}" alt="" '
            f'loading="lazy" width="1200" height="675">'
        )
    # Sans photo réelle, aucun substitut: une image d'illustration sur un
    # registre de vérification détruirait ce que la page sert à établir.

    return f"""<header class="block identity">
  <p class="eyebrow">Registre de vérification</p>
  <h1>{html.escape(dossier.name)}</h1>
  <p>Ce document recense ce qui a été contrôlé sur pièces au sujet de cette
  entreprise, ce qui ne l'a pas été, et jusqu'à quand chaque contrôle reste
  valable.</p>
  <div class="meta">{meta}</div>
  {portrait}
</header>"""


def _tally(dossier: Dossier, today: date) -> str:
    counts = dossier.counts(today)
    cells = [
        ("verified", counts[VERIFIED], "Affirmations vérifiées"),
        ("declared", counts[DECLARED], "Déclarées, non contrôlées"),
        ("lapsed", counts[EXPIRED], "Contrôles expirés"),
    ]
    if counts[REFUTED]:
        cells.append(("refuted", counts[REFUTED], "Réfutées"))
    body = "".join(
        f'<div class="{css}"><span class="n">{value}</span>'
        f'<span class="k">{html.escape(label)}</span></div>'
        for css, value, label in cells
    )
    return f'<div class="tally">{body}</div>'


def _claims(dossier: Dossier, today: date) -> str:
    sections = []
    for _key, label, claims in dossier.by_cluster(today):
        cards = []
        for claim in claims:
            status = claim.status(today)
            state_bits = [STATUS_TEXT[status]]
            if status == VERIFIED and claim.verified_on:
                state_bits.append(f"le {fr_date(claim.verified_on)}")
                if claim.valid_until:
                    state_bits.append(f"valable jusqu'au {fr_date(claim.valid_until)}")
            elif status == EXPIRED and claim.valid_until:
                state_bits.append(f"depuis le {fr_date(claim.valid_until)}")
            proof = ""
            if claim.evidence:
                references = ", ".join(
                    f"{e.kind_label} {e.reference} ({e.checked_by})" for e in claim.evidence
                )
                proof = f'<span class="proof">{html.escape(references)}</span>'
            cards.append(
                f'<div class="claim {STATUS_CLASS[status]}">'
                f'<span class="label">{html.escape(claim.label)}</span>'
                f'<span class="value">{html.escape(claim.value)}</span>'
                f'<span class="state">{html.escape(", ".join(state_bits))}</span>'
                f"{proof}</div>"
            )
        sections.append(
            f'<div class="cluster"><h3>{html.escape(label)}</h3>'
            f'<div class="claims">{"".join(cards)}</div></div>'
        )
    return "".join(sections)


def _gaps(dossier: Dossier, today: date) -> str:
    stale = dossier.stale(today)
    if not stale:
        return (
            "<p>Toutes les affirmations de ce dossier sont contrôlées sur pièces et "
            "leur contrôle est en cours de validité.</p>"
        )
    rows = []
    for claim in stale:
        status = claim.status(today)
        reason = {
            DECLARED: "aucune pièce fournie",
            EXPIRED: f"contrôle expiré le {fr_date(claim.valid_until)}",
            REFUTED: "contredit par les pièces",
        }[status]
        rows.append(
            f'<li><span class="what">{html.escape(claim.label)} : '
            f'{html.escape(claim.value)}</span>'
            f'<span class="why {STATUS_CLASS[status]}">{html.escape(reason)}</span></li>'
        )
    return f'<div class="gaps"><ul>{"".join(rows)}</ul></div>'


def _machine(dossier: Dossier, today: date) -> str:
    verified = len(dossier.publishable(today))
    return f"""<section class="block" style="gap:1rem">
  <h2>Lecture par les agents</h2>
  <p>Cette page est le point de publication, pas un renvoi. Les {verified}
  affirmations vérifiées y sont embarquées en JSON-LD, lisibles sans exécuter de
  script. Les affirmations déclarées ne sont pas publiées comme des faits.</p>
  <div class="machine">
    <dl>
      <dt>protocole</dt><dd><code>{html.escape(PROTOCOL)}</code></dd>
      <dt>structuré</dt><dd><code>{html.escape(dossier.entity_id)}.jsonld</code>
        (schema.org, vérifié uniquement)</dd>
      <dt>manifeste</dt><dd><code>{html.escape(dossier.entity_id)}.manifest.json</code>
        (toutes les affirmations, avec leur statut)</dd>
      <dt>flux</dt><dd><code>{html.escape(dossier.entity_id)}.jsonl</code></dd>
    </dl>
  </div>
</section>"""


def _embed_jsonld(document: dict) -> str:
    """Sérialise le JSON-LD pour un bloc ``<script>`` sans échappatoire possible.

    Une valeur d'affirmation contenant ``</script>`` sortirait du bloc et
    deviendrait du balisage exécutable. On neutralise donc les caractères qui
    peuvent fermer un élément script; les séquences produites restent du JSON
    valide et se relisent à l'identique.
    """
    payload = json.dumps(document, ensure_ascii=False, indent=2)
    return (
        payload.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    )


def to_html(dossier: Dossier, today: date | None = None) -> str:
    """Fragment de page: titre, styles et contenu, sans squelette de document.

    Ne varie jamais selon un palier commercial ou une exclusivité: c'est ce
    qui rend cette page crédible comme source pour un humain et pour un
    agent, quel que soit ce que l'entreprise paie.
    """
    moment = today or date.today()
    jsonld = _embed_jsonld(to_jsonld(dossier, moment))

    return f"""<title>Page de Vérité : {html.escape(dossier.name)}</title>
<script type="application/ld+json">
{jsonld}
</script>
<style>{CSS}</style>
<main class="sheet">

  {_identity(dossier, moment)}

  <section class="block" style="gap:1rem">
    <h2>État du dossier</h2>
    {_tally(dossier, moment)}
  </section>

  <section class="block" style="gap:1.5rem">
    <h2>Ce qui a été contrôlé</h2>
    {_claims(dossier, moment)}
  </section>

  <section class="block" style="gap:1rem">
    <h2>Ce qui n'est pas vérifié</h2>
    <p>Cette section existe pour que le reste soit croyable. Une entreprise qui
    ne publierait que ses points forts ne publierait rien.</p>
    {_gaps(dossier, moment)}
  </section>

  {_machine(dossier, moment)}

  <footer>
    <span>Contrôles effectués sur pièces par Source Primaire. Un contrôle porte
    sur la pièce présentée à sa date, et ne constitue pas une garantie de la
    prestation. La méthode est publique et contestable.</span>
    <span class="protocol">Protocole {html.escape(PROTOCOL)}</span>
    <span class="protocol">Dossier {html.escape(dossier.entity_id)}, rendu le
    {moment.isoformat()}</span>
  </footer>
</main>"""


def to_document(dossier: Dossier, today: date | None = None) -> str:
    """Document autonome, destiné à être hébergé par l'entreprise elle-même."""
    fragment = to_html(dossier, today)
    description = (
        f"Affirmations vérifiées sur pièces concernant {dossier.name}, "
        f"{dossier.category} à {dossier.zone}."
    )
    return f"""<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="description" content="{html.escape(description)}">
<meta name="robots" content="index, follow, max-snippet:-1">
{fragment.split("<main", 1)[0].rstrip()}
</head>
<body>
<main{fragment.split("<main", 1)[1]}
</body>
</html>
"""
