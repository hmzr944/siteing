"""La boucle de dialogue.

Traiter un message isolé est facile. Traiter un message qui répond à une question
posée trois heures plus tôt demande de savoir que cet artisan a un chantier en
attente d'une nature. C'est une machine à états, et elle est ici.

Trois problèmes réels, et la façon dont ils sont tranchés.

**Le routage.** Un message entrant est-il une réponse à la question en cours, ou
un nouveau chantier ? On tente de résoudre le champ attendu; si ça marche et que
le message ne porte pas les marques d'un nouvel événement (« j'ai fini », un
autre secteur, une autre nature), c'est une réponse. Sinon c'est une nouvelle
entrée, et **la précédente n'est jamais perdue**: elle est garée et remonte au
plan de travail.

**La désambiguïsation par le contexte.** C'est ce que le dialogue apporte de
plus que la collecte. « 12 plaques » seul est refusé, parce qu'une plaque est
aussi une plaque de plâtre. « 12 plaques » en réponse à « le chantier a été
facturé combien ? » est un montant, parce que la question a établi le contexte.

**La péremption.** Une question sans réponse depuis trois semaines ne peut plus
être répondue: « salle de bain » hors contexte ne désigne plus rien. Au-delà du
délai, le candidat est garé et la conversation repart à zéro.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

from noyau.chantier import FROM_INVOICE, FROM_VOICE
from noyau.territoire import Referentiel

from .extraction import Candidate, Question, build_candidate, summarise
from .extracteurs import Extractor, HeuristicExtractor
from .lexique import (
    parse_date,
    parse_duree,
    parse_montant,
    parse_nature,
    parse_surface,
    plain,
)

# Au-delà, une question en attente ne peut plus recevoir de réponse utile.
PENDING_TTL_DAYS = 7

# Marques d'un nouvel événement. Leur présence fait pencher le routage vers une
# nouvelle entrée plutôt qu'une réponse.
NEW_EVENT_CUES = (
    "j'ai fini", "jai fini", "j'ai termine", "jai termine", "on a livre",
    "j'ai livre", "jai livre", "j'ai pose", "jai pose", "on a pose",
    "on a fini", "on a termine", "je viens de finir", "chantier suivant",
    "autre chantier", "nouveau chantier",
)

# Références de pièces reconnues dans un message.
PIECE_CUES = ("facture", "devis", "piece", "justificatif")

ASK = "question"
REGISTERED = "enregistre"
PIECE_REQUEST = "piece_demandee"
PIECE_RECEIVED = "piece_recue"
PARKED = "gare"
UNCLEAR = "incompris"


@dataclass
class Reply:
    """Ce que le système répond, et ce qu'il a fait."""

    kind: str
    text: str
    candidate: Candidate | None = None
    chantier_id: str | None = None
    field_filled: str | None = None


@dataclass
class Conversation:
    """L'état d'un fil, pour une entreprise."""

    entity_id: str
    active: Candidate | None = None
    awaiting: str | None = None            # champ attendu
    asked_on: date | None = None
    parked: list[Candidate] = field(default_factory=list)
    registered: list[dict] = field(default_factory=list)
    awaiting_piece_for: str | None = None  # identifiant de chantier

    @property
    def has_pending_question(self) -> bool:
        return self.active is not None and self.awaiting is not None

    def is_stale(self, today: date) -> bool:
        if self.asked_on is None:
            return False
        return (today - self.asked_on).days > PENDING_TTL_DAYS

    def park(self, reason: str = "") -> None:
        """Range le candidat en cours sans rien perdre."""
        if self.active is not None:
            if reason:
                self.active.refusals.setdefault("_parked", reason)
            self.parked.append(self.active)
        self.active = None
        self.awaiting = None
        self.asked_on = None

    def to_dict(self) -> dict:
        return {
            "entity_id": self.entity_id,
            "awaiting": self.awaiting,
            "asked_on": self.asked_on.isoformat() if self.asked_on else None,
            "awaiting_piece_for": self.awaiting_piece_for,
            "active": self.active.to_dict() if self.active else None,
            "parked": [c.to_dict() for c in self.parked],
            "registered": self.registered,
        }

    def save(self, path: str | Path) -> None:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(self.to_dict(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )


# -- résolution d'un champ attendu ---------------------------------------------


def resolve_field(
    field_name: str, text: str, referentiel: Referentiel, today: date
):
    """Résout un seul champ à partir d'une réponse libre.

    Le contexte monétaire est passé au résolveur quand c'est un budget qui est
    attendu: c'est la question qui l'établit.
    """
    from .extraction import resolve_territoire

    if field_name == "nature":
        return parse_nature(text)
    if field_name == "budget_eur":
        return parse_montant(text, money_context=True)
    if field_name == "size":
        return parse_surface(text)
    if field_name == "territoire":
        return resolve_territoire(text, referentiel)
    if field_name == "completed_on":
        return parse_date(text, today)
    if field_name == "duration_days":
        return parse_duree(text)
    raise ValueError(f"champ non résoluble en dialogue: {field_name!r}")


# Champs de détail: ils précisent un chantier sans jamais en ouvrir un autre.
DETAIL_FIELDS = ("size", "duration_days", "completed_on")

# Confiance minimale pour qu'une date amende un chantier déjà enregistré. Le
# résolveur de date rend toujours une valeur, le jour de l'énoncé par défaut:
# sans ce seuil, n'importe quel message passerait pour une correction de date.
EXPLICIT_DATE_CONFIDENCE = 0.5


def resolved_field_count(text: str, referentiel: Referentiel, today: date) -> int:
    """Nombre de faits indépendants qu'un message porte à lui seul.

    C'est le meilleur signal de routage disponible: une réponse à « quel type de
    chantier ? » est courte et porte une seule information, alors qu'une nouvelle
    entrée en porte plusieurs. La date par défaut ne compte pas, puisqu'elle est
    déduite et non énoncée.
    """
    from .extraction import resolve_territoire

    attempts = (
        parse_nature(text),
        parse_montant(text),
        parse_surface(text),
        parse_duree(text),
        resolve_territoire(text, referentiel),
    )
    return sum(1 for attempt in attempts if attempt.ok)


def looks_like_new_event(
    text: str,
    candidate: Candidate | None,
    referentiel: Referentiel | None = None,
    today: date | None = None,
) -> bool:
    """Le message ouvre-t-il un nouveau chantier plutôt que de répondre ?"""
    lowered = plain(text)
    if any(cue in lowered for cue in NEW_EVENT_CUES):
        return True
    # Un message qui porte plusieurs faits indépendants n'est pas une réponse à
    # une question fermée: c'est une nouvelle entrée. Sans ce test, « j'ai livré
    # la cuisine place Nansouty, 14 m2, 22 plaques » se ferait absorber comme
    # simple réponse au chantier précédent, et les deux fusionneraient.
    if referentiel is not None:
        if resolved_field_count(text, referentiel, today or date.today()) >= 2:
            return True
    if candidate is not None and "nature" in candidate.fields:
        proposed = parse_nature(text)
        if proposed.ok and proposed.value != candidate.fields["nature"]:
            return True
    return False


def find_piece_reference(text: str) -> str | None:
    """Référence de pièce citée dans un message, si elle est identifiable."""
    import re

    lowered = plain(text)
    if not any(cue in lowered for cue in PIECE_CUES):
        return None
    match = re.search(r"\b([A-Za-z]{1,3}\s?\d{4}-\d{2,4})\b", text)
    if match:
        return match.group(1).replace(" ", "")
    match = re.search(r"\b(?:facture|devis)\s+(?:n[°o]\s*)?([\w-]{3,})", text, re.I)
    return match.group(1) if match else None


# -- la boucle -----------------------------------------------------------------


class Dialogue:
    """Reçoit des messages, tient l'état, et répond une chose à la fois."""

    def __init__(
        self,
        referentiel: Referentiel,
        extractor: Extractor | None = None,
        conversation: Conversation | None = None,
        entity_id: str = "ferrand",
    ) -> None:
        self.referentiel = referentiel
        self.extractor = extractor or HeuristicExtractor()
        self.conversation = conversation or Conversation(entity_id=entity_id)
        self._counter = len(self.conversation.registered)

    # -- entrées ---------------------------------------------------------------

    def receive(self, text: str, today: date | None = None) -> Reply:
        moment = today or date.today()
        conversation = self.conversation

        if conversation.is_stale(moment):
            conversation.park(
                f"question restée sans réponse plus de {PENDING_TTL_DAYS} jours"
            )

        if conversation.awaiting_piece_for is not None:
            handled = self._try_piece(text, moment)
            if handled is not None:
                return handled
            amended = self._try_amendment(text, moment)
            if amended is not None:
                return amended

        if conversation.has_pending_question and not looks_like_new_event(
            text, conversation.active, self.referentiel, moment
        ):
            answered = self._try_answer(text, moment)
            if answered is not None:
                return answered

        return self._new_entry(text, moment)

    # -- branches --------------------------------------------------------------

    def _try_answer(self, text: str, today: date) -> Reply | None:
        conversation = self.conversation
        candidate = conversation.active
        field_name = conversation.awaiting
        resolved = resolve_field(field_name, text, self.referentiel, today)
        if not resolved.ok:
            return None

        candidate.fields[field_name] = resolved.value
        candidate.evidence[field_name] = resolved.note
        candidate.confidence[field_name] = resolved.confidence
        candidate.refusals.pop(field_name, None)
        candidate.source_text = f"{candidate.source_text} | {text.strip()}"

        if candidate.is_complete:
            return self._register(candidate, field_filled=field_name)
        return self._ask(candidate, today, field_filled=field_name)

    def _new_entry(self, text: str, today: date) -> Reply:
        conversation = self.conversation
        spans = self.extractor.spans(text)
        candidate = build_candidate(
            text, spans, conversation.entity_id, self.referentiel, today
        )

        # Un candidat dont le seul champ est la date par défaut ne porte aucune
        # information: le résolveur de date rend toujours une valeur, donc
        # « ok merci » produirait sinon un chantier fantôme.
        substantive = {
            name: value
            for name, value in candidate.fields.items()
            if name != "completed_on"
            or candidate.confidence.get(name, 0.0) >= EXPLICIT_DATE_CONFIDENCE
        }
        if not substantive:
            return Reply(
                UNCLEAR,
                "Je n'ai rien réussi à en tirer. Dites-moi le type de chantier, "
                "le secteur et le montant facturé.",
            )

        if conversation.has_pending_question:
            conversation.park("nouveau chantier annoncé avant réponse")

        conversation.active = candidate
        if candidate.is_complete:
            return self._register(candidate)
        return self._ask(candidate, today)

    def _ask(
        self, candidate: Candidate, today: date, field_filled: str | None = None
    ) -> Reply:
        question: Question = candidate.next_question(self.referentiel)
        self.conversation.awaiting = question.field
        self.conversation.asked_on = today
        prefix = (
            f"Noté : {summarise(candidate, self.referentiel)}.\n"
            if candidate.fields
            else ""
        )
        return Reply(
            ASK, f"{prefix}{question.text}", candidate=candidate, field_filled=field_filled
        )

    def _register(self, candidate: Candidate, field_filled: str | None = None) -> Reply:
        conversation = self.conversation
        self._counter += 1
        chantier_id = f"{conversation.entity_id}-{self._counter:03d}"
        chantier = candidate.to_chantier(chantier_id)

        conversation.registered.append(
            {
                "id": chantier_id,
                "nature": chantier.nature,
                "territoire": chantier.territoire,
                "completed_on": chantier.completed_on.isoformat(),
                "budget_eur": chantier.budget_eur,
                "size": chantier.size,
                "duration_days": chantier.duration_days,
                "provenance": chantier.provenance,
                "reference": chantier.reference,
                "date_confidence": candidate.confidence.get("completed_on", 0.0),
                "notes": chantier.notes,
            }
        )
        conversation.active = None
        conversation.awaiting = None
        conversation.asked_on = None
        conversation.awaiting_piece_for = chantier_id

        return Reply(
            REGISTERED,
            f"C'est enregistré : {summarise(candidate, self.referentiel)}.\n"
            "Pour que son budget soit publié et compte dans votre visibilité, il "
            "me faut la facture. Envoyez-la ici, une photo suffit.",
            candidate=candidate,
            chantier_id=chantier_id,
            field_filled=field_filled,
        )

    def _try_amendment(self, text: str, today: date) -> Reply | None:
        """Un détail arrivé juste après l'enregistrement complète le chantier.

        « 6 m2 » envoyé dans la seconde qui suit ne signale pas un nouveau
        chantier: c'est une précision sur celui qu'on vient d'enregistrer. Sans
        cette branche, le message ouvrait un candidat parasite qui polluait
        ensuite l'entrée suivante.
        """
        conversation = self.conversation
        if looks_like_new_event(text, None, self.referentiel, today):
            return None

        record = next(
            (
                r
                for r in conversation.registered
                if r["id"] == conversation.awaiting_piece_for
            ),
            None,
        )
        if record is None:
            return None

        labels = {
            "size": "surface", "duration_days": "durée", "completed_on": "date"
        }
        for field_name in DETAIL_FIELDS:
            resolved = resolve_field(field_name, text, self.referentiel, today)
            if not resolved.ok:
                continue
            if field_name == "completed_on":
                # Une date énoncée corrige une date déduite; une date déduite ne
                # corrige rien.
                if resolved.confidence < EXPLICIT_DATE_CONFIDENCE:
                    continue
                if resolved.confidence <= record.get("date_confidence", 0.0):
                    continue
                record["completed_on"] = resolved.value.isoformat()
                record["date_confidence"] = resolved.confidence
            elif record.get(field_name) is None:
                record[field_name] = resolved.value
            else:
                continue
            return Reply(
                PIECE_REQUEST,
                f"{labels[field_name].capitalize()} notée pour le chantier "
                f"{record['id']}. J'attends toujours la facture pour publier "
                "son budget.",
                chantier_id=record["id"],
                field_filled=field_name,
            )
        return None

    def _try_piece(self, text: str, today: date) -> Reply | None:
        conversation = self.conversation
        reference = find_piece_reference(text)
        if reference is None:
            return None

        chantier_id = conversation.awaiting_piece_for
        record = next(
            (r for r in conversation.registered if r["id"] == chantier_id), None
        )
        if record is None:
            conversation.awaiting_piece_for = None
            return None

        record["provenance"] = FROM_INVOICE
        record["reference"] = reference
        conversation.awaiting_piece_for = None
        return Reply(
            PIECE_RECEIVED,
            f"Facture {reference} rattachée au chantier. Son budget entre "
            "maintenant dans vos budgets constatés.",
            chantier_id=chantier_id,
        )

    # -- sortie ----------------------------------------------------------------

    def chantiers(self) -> list[dict]:
        """Chantiers enregistrés, prêts à rejoindre un Noyau."""
        return [
            {k: v for k, v in record.items() if v is not None}
            for record in self.conversation.registered
        ]

    def work_plan(self) -> list[str]:
        """Ce qui reste en suspens, y compris ce qui a été garé.

        Rien ne se perd: un chantier annoncé puis abandonné en cours de dialogue
        remonte ici plutôt que de disparaître.
        """
        lines: list[str] = []
        if self.conversation.awaiting_piece_for:
            lines.append(
                f"Facture attendue pour le chantier "
                f"{self.conversation.awaiting_piece_for}, sans quoi son budget "
                "ne sera pas publié."
            )
        if self.conversation.has_pending_question:
            lines.append(
                f"Réponse attendue sur « {self.conversation.awaiting} » pour le "
                "chantier en cours."
            )
        for candidate in self.conversation.parked:
            lines.append(
                f"Chantier incomplet laissé de côté ({', '.join(candidate.missing)}) : "
                f"« {candidate.source_text[:60]}… »"
            )
        for record in self.conversation.registered:
            if record["provenance"] == FROM_VOICE:
                lines.append(
                    f"Chantier {record['id']} enregistré sans pièce : il prouve une "
                    "intervention mais n'entre dans aucun budget publié."
                )
        return lines
