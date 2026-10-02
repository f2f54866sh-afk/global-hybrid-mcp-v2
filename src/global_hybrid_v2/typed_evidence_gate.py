"""Bounded full-span evidence admission; never a natural-language semantic oracle.

No default evidence, external calls, or public PASS. The bridge constructs evidence
only from the current immutable snapshot. Unparsed text is always withheld.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum


class EvidenceState(StrEnum):
    CONFIRMED_TRUE = "CONFIRMED_TRUE"
    CONFIRMED_FALSE = "CONFIRMED_FALSE"
    UNKNOWN = "UNKNOWN"
    ABSENT = "ABSENT"


class PublicationPolicy(StrEnum):
    ALLOW = "ALLOW"
    HOLD = "HOLD"
    FORBID = "FORBID"


class Cardinality(StrEnum):
    SINGLE_VALUED = "SINGLE_VALUED"
    MULTI_VALUED = "MULTI_VALUED"


@dataclass(frozen=True)
class Proposition:
    entity_id: str
    predicate: str
    value: str
    polarity: bool
    evidence_state: EvidenceState
    publication_policy: PublicationPolicy
    source_ref: str


@dataclass(frozen=True)
class Atom:
    entity_id: str
    predicate: str
    value: str
    polarity: bool = True


PREDICATE_CARDINALITY = {
    **dict.fromkeys(
        (
            "vehicle_model",
            "vehicle_year",
            "ecu_tune",
            "horsepower",
            "horsepower_gain",
            "handling_improvement",
            "bilstein_exact_model",
        ),
        Cardinality.SINGLE_VALUED,
    ),
    **dict.fromkeys(
        ("mst_intake", "mst_exhaust", "bilstein_suspension", "bilstein_spring"), Cardinality.MULTI_VALUED
    ),
}
SENTINEL = re.compile(
    "ECU|電腦|程式|二階|一階|馬力|匹|PS|hp|動力|油門|操控|B16|PSS10|B14|排氣|進氣|避震|年份|車型", re.I
)
EQUIP = (
    "(?:MST(?: Performance)?進氣(?:系統)?|BILSTEIN避震(?:系統)?"
    "|MST(?: Performance)?排氣(?:系統)?|BILSTEIN彈簧)"
)
VEHICLE = "(?P<year>20\\d{2})\\s*(?:Volkswagen\\s*)?(?P<model>Tiguan R|Golf GTI)"


def equipment(item):
    if item.startswith("MST"):
        return "mst_exhaust" if "排氣" in item else "mst_intake"
    return "bilstein_spring" if "彈簧" in item else "bilstein_suspension"


def parse(text, target_entity, entities):
    entity = target_entity
    atoms = []
    body = text
    subject = re.fullmatch(
        "(另外一台|另有一台|這台|這是一台|這是(?:一台)?|目標車輛是)?" + VEHICLE + "(?P<tail>.*)", body
    )
    if subject:
        model = "Volkswagen " + subject["model"]
        year = subject["year"]
        if subject[1] in ["另外一台", "另有一台"]:
            entity = entities.get("Volkswagen " + subject["model"], "UNBOUND_OTHER_ENTITY")
        elif not subject[1]:
            entity = entities.get("Volkswagen " + subject["model"], target_entity)
        atoms.extend([Atom(entity, "vehicle_year", year), Atom(entity, "vehicle_model", model)])
        body = subject["tail"]
        if not body:
            return (atoms, "VEHICLE_IDENTITY_GRAMMAR")
    else:
        m = re.fullmatch("這台(?P<model>Tiguan R|Golf GTI)(?P<tail>.+)", body)
        if m:
            atoms.append(Atom(entity, "vehicle_model", "Volkswagen " + m["model"]))
            body = m["tail"]
        else:
            body = re.sub("^(?:這台車|車上|這台)", "", body, count=1)
    body = re.sub("^(?:也|而且)", "", body, count=1)
    m = re.fullmatch(
        "(?:配有|有|裝有|使用)?(?P<items>" + EQUIP + "(?:與" + EQUIP + ")*)(?:都已在車上|已在車上)?", body
    )
    if m:
        items = m["items"].split("與")
        atoms.extend(Atom(entity, equipment(item), "PRESENT") for item in items)
        return (atoms, "EXACT_EQUIPMENT_LIST_GRAMMAR")
    m = re.fullmatch("(?:已完成|完成|已經完成|已確認完成)?(?:二階ECU調校|二階程式|二階調校)", body)
    if m:
        return (atoms + [Atom(entity, "ecu_tune", "STAGE2")], "TUNE_GRAMMAR")
    if re.fullmatch("(?:ECU)?(?:已經|已)?(?:寫|刷)程式", body):
        return (atoms + [Atom(entity, "ecu_tune", "ANY_TUNE")], "TUNE_GRAMMAR")
    if re.fullmatch("(?:沒有做二階程式|沒有改電腦|沒刷程式|ECU沒有寫程式)", body):
        return (
            atoms + [Atom(entity, "ecu_tune", "STAGE2" if "二階" in body else "ANY_TUNE", False)],
            "NEGATED_TUNE_GRAMMAR",
        )
    if body in ["ECU維持原廠程式", "原廠程式沒有動"]:
        return (atoms + [Atom(entity, "ecu_tune", "STOCK")], "STOCK_TUNE_GRAMMAR")
    if re.fullmatch("馬力(?:也)?(?:已經|已)?提升|馬力提升已確認", body):
        return (atoms + [Atom(entity, "horsepower_gain", "INCREASED")], "POWER_GRAMMAR")
    if body == "馬力維持原廠":
        return (atoms + [Atom(entity, "horsepower_gain", "INCREASED", False)], "NEGATED_POWER_GRAMMAR")
    m = re.fullmatch("(?:使用)?BILSTEIN\\s*(B16|PSS10|B14)(?:避震)?", body)
    if m:
        return (atoms + [Atom(entity, "bilstein_exact_model", m[1])], "EXACT_MODEL_GRAMMAR")
    m = re.fullmatch("(?:有|也是|約)?(\\d+)匹(?:馬力)?", body)
    if m:
        return (atoms + [Atom(entity, "horsepower", m[1] + "hp")], "HORSEPOWER_GRAMMAR")
    return (atoms, None)


def admit(atom: Atom, evidence: tuple[Proposition, ...]) -> str | None:
    """All applicable evidence must agree; absence never supplies a negation."""
    same = tuple(x for x in evidence if x.entity_id == atom.entity_id and x.predicate == atom.predicate)
    if any(x.evidence_state in (EvidenceState.UNKNOWN, EvidenceState.ABSENT) for x in same):
        return "TYPED_EVIDENCE_UNKNOWN_POLARITY"
    exact = tuple(x for x in same if x.value == atom.value)
    if not exact:
        if PREDICATE_CARDINALITY.get(atom.predicate) is Cardinality.SINGLE_VALUED and any(
            x.evidence_state is EvidenceState.CONFIRMED_TRUE and x.polarity for x in same
        ):
            return "TYPED_EVIDENCE_VALUE_CONTRADICTION"
        if any(

                x.predicate == atom.predicate and x.value == atom.value and (x.entity_id != atom.entity_id)
                for x in evidence

        ):
            return "TYPED_EVIDENCE_ENTITY_MISMATCH"
        return "TYPED_EVIDENCE_UNSUPPORTED_CLAIM"
    for item in exact:
        if item.publication_policy is not PublicationPolicy.ALLOW:
            return "TYPED_EVIDENCE_PUBLICATION_" + item.publication_policy.value
        supports = (
            item.polarity == atom.polarity
            if item.evidence_state is EvidenceState.CONFIRMED_TRUE
            else item.polarity != atom.polarity
        )
        if not supports:
            return "TYPED_EVIDENCE_VALUE_CONTRADICTION"
        if not item.source_ref:
            return "TYPED_EVIDENCE_UNSUPPORTED_CLAIM"
    return None


@dataclass(frozen=True)
class Span:
    start: int
    end: int
    text: str
    disposition: str
    atoms: tuple[Atom, ...]
    high_risk: bool


@dataclass(frozen=True)
class GateResult:
    spans: tuple[Span, ...]
    hard_blockers: tuple[str, ...]
    unresolved_remainders: tuple[Span, ...]

    @property
    def blocker_codes(self) -> tuple[str, ...]:
        return self.hard_blockers

    @property
    def allowed(self) -> bool:
        return not self.hard_blockers and not self.unresolved_remainders


def evaluate(text: str, *, evidence: tuple[Proposition, ...], target_entity: str,
             incumbent_literals: tuple[str, ...] = ()) -> GateResult:
    """Account for every original character; only full-span grammar admits atoms."""
    entities = {
        x.value: x.entity_id
        for x in evidence
        if x.predicate == "vehicle_model" and x.evidence_state is EvidenceState.CONFIRMED_TRUE
    }
    spans = []
    blockers = []
    unresolved = []
    for match in re.finditer("[^，。；\\n]+|[，。；\\n]+", text):
        raw = match[0]
        trim = raw.strip()
        atoms = []
        if not trim or re.fullmatch("[，。；\\n]+", raw):
            disposition = "BOUND_NONFACTUAL_SAFE_TEXT"
        else:
            atoms, grammar = parse(trim, target_entity, entities)
            disposition = "BOUND_FACTUAL_ATOM" if grammar else "UNPARSED_OR_AMBIGUOUS"
            if not grammar:
                if trim in incumbent_literals:
                    disposition = "BOUND_INCUMBENT_LITERAL"
                elif SENTINEL.search(trim):
                    blockers.append("TYPED_EVIDENCE_UNPARSED_REMAINDER")
            for atom in atoms:
                blocker = admit(atom, evidence)
                if blocker:
                    blockers.append(blocker)
        span = Span(*match.span(), raw, disposition, tuple(atoms), bool(SENTINEL.search(trim)))
        spans.append(span)
        if disposition == "UNPARSED_OR_AMBIGUOUS":
            unresolved.append(span)
    if not text.strip():
        blockers.append("TYPED_EVIDENCE_COVERAGE_INCOMPLETE")
    if "".join(span.text for span in spans) != text:
        blockers.append("TYPED_EVIDENCE_COVERAGE_INCOMPLETE")
    return GateResult(tuple(spans), tuple(dict.fromkeys(blockers)), tuple(unresolved))


def snapshot_evidence(snapshot):
    """Adapt only bounded complete verified facts; unknown strings never become facts.

    Target entity is task-owned, not selected by candidate text. Unsupported source
    syntax contributes no evidence. Source refs include the immutable digest/index.
    Cross-vehicle statements are withheld rather than guessed into target evidence.
    """
    target = snapshot.task_handle
    evidence = []
    for index, fact in enumerate(snapshot.snapshot.verified_public_facts):
        result = evaluate(fact, evidence=(), target_entity=target)
        if any(span.disposition == "UNPARSED_OR_AMBIGUOUS" for span in result.spans):
            continue
        for span in result.spans:
            for atom in span.atoms:
                if atom.entity_id == target:
                    evidence.append(
                        Proposition(
                            atom.entity_id,
                            atom.predicate,
                            atom.value,
                            atom.polarity,
                            EvidenceState.CONFIRMED_TRUE,
                            PublicationPolicy.ALLOW,
                            f"{snapshot.snapshot_digest}:verified_public_facts:{index}",
                        )
                    )
    unknown_predicates = {
        "ECU是否寫程式": "ecu_tune",
        "ECU tune status": "ecu_tune",
        "horsepower gain": "horsepower_gain",
        "馬力提升未知": "horsepower_gain",
        "BILSTEIN確切型號未知": "bilstein_exact_model",
        "BILSTEIN exact model": "bilstein_exact_model",
        "handling improvement": "handling_improvement",
        "操控改善未知": "handling_improvement",
    }
    for index, unknown in enumerate(snapshot.snapshot.internal_only_unknowns):
        predicate = unknown_predicates.get(unknown)
        if predicate:
            evidence.append(
                Proposition(
                    target,
                    predicate,
                    "UNSPECIFIED",
                    True,
                    EvidenceState.UNKNOWN,
                    PublicationPolicy.HOLD,
                    f"{snapshot.snapshot_digest}:internal_only_unknowns:{index}",
                )
            )
    return tuple(evidence)
