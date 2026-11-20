"""Derive and validate suggestions without changing case or partner state."""
import json
from pathlib import Path
import re

import httpx

from app.integrations.intake import extract_with_model
from app.schemas import IntakeRequest, IntakeResponse, IntakeResult, MissingIntakeField, normalize_intake_text


SAFETY = json.loads((Path(__file__).resolve().parents[3] / "shared/intake-safety.json").read_text(encoding="utf-8"))
GAS_SIGNAL = re.compile(SAFETY["possible_gas_leak"], re.IGNORECASE)
GAS_NEGATION = re.compile(SAFETY["negation_prefix"], re.IGNORECASE)

HEATING = re.compile(
    r"\b(?:no heat at all|no heat(?:ing)?|lack of heat(?:ing)?|"
    r"(?:(?:some|all|the|my)\s+)?(?:radiators?|heating|heater|boiler|thermostat)\b[^.!?;\n]{0,45}?"
    r"\b(?:lukewarm|cold|not working|stopped working|broken|won['’]t (?:heat|turn on|start)|"
    r"isn['’]t (?:heating|working)|doesn['’]t (?:heat|work)|stopped|leaking|making noise|off))\b",
    re.IGNORECASE,
)
HOT_WATER_PREFIX = r"hot water (?:also )?(?:(?:is|has) (?:also )?)?"
HOT_WATER = re.compile(
    rf"\b(?:(?P<affected>no hot water|lost (?:the )?hot water|{HOT_WATER_PREFIX}"
    rf"(?:not working|does not work|doesn['’]t work|affected|unavailable|stopped working|gone|cold))|"
    rf"(?P<working>still (?:have|got) hot water|there is still hot water|"
    rf"{HOT_WATER_PREFIX}(?:still works|works|fine|working|unaffected)))\b", re.IGNORECASE,
)
AVAILABILITY = re.compile(
    r"\b(?:availability\s*:\s*|(?:i (?:can (?:be home|be available|meet|do)|will be (?:home|available)|"
    r"am (?:home|available|free)|work from home)|i['’](?:m|ll be) (?:home|available|free)|"
    r"best time (?:for me )?is)\s+)([^.!?;\n]{1,160})(?=[.!?;\n]|$)",
    re.IGNORECASE,
)
RECURRING_AVAILABILITY = re.compile(
    r"(?:^|[.!?;\n,]\s*)(weekday|weekend)\s+(mornings?|afternoons?|evenings?)(?=\s*(?:[.!?;\n,]|$))",
    re.IGNORECASE,
)
PRIORITY = re.compile(
    r"\b(?:(?P<low>no rush|not urgent|low priority)|(?P<normal>normal priority)|"
    r"(?P<high>high priority|urgent|asap|as soon as possible))\b",
    re.IGNORECASE,
)
HOT_WATER_LABELS = {True: "hot_water_affected", False: "hot_water_working"}


def possible_gas_leak(report: str) -> bool:
    return any(not GAS_NEGATION.search(report[:match.start()]) for match in GAS_SIGNAL.finditer(report))


def unique_excerpts(excerpts, limit: int) -> list[str]:
    by_normalized = {}
    for excerpt in excerpts:
        clean = excerpt.strip()
        if clean:
            by_normalized.setdefault(normalize_intake_text(clean), clean)
    return list(by_normalized.values())[:limit]


def availability_excerpts(report: str, *, include_context: bool = False) -> list[str]:
    matches = [(match.start(1), match[0 if include_context else 1]) for match in AVAILABILITY.finditer(report)]
    matches += [(match.start(1), report[match.start(1):match.end(2)]) for match in RECURRING_AVAILABILITY.finditer(report)]
    return unique_excerpts((text for _, text in sorted(matches)), 8)


def explicit_urgency(report: str):
    priorities = {match.lastgroup for match in PRIORITY.finditer(report)}
    return priorities.pop() if len(priorities) == 1 else None


def reconcile(draft: IntakeRequest, result: IntakeResult) -> IntakeResult:
    symptoms = result.symptoms or unique_excerpts((match[0] for match in HEATING.finditer(draft.report)), 12)
    has_heating = any(HEATING.search(item) or not HOT_WATER.search(item) for item in symptoms)
    availability = result.availability_preferences or availability_excerpts(draft.report)
    if draft.hot_water_affected is not None:
        # Drop conflicting excerpts before appending the resident's explicit answer.
        answer = "affected" if draft.hot_water_affected else "working"
        symptoms = [item for item in symptoms if normalize_intake_text(item) not in HOT_WATER_LABELS.values()
                    and all(match.lastgroup == answer for match in HOT_WATER.finditer(item))]
        symptoms = unique_excerpts(symptoms, 11) + [HOT_WATER_LABELS[draft.hot_water_affected]]

    missing: list[MissingIntakeField] = []
    if not has_heating:
        missing.append("heating_symptom")
    elif draft.hot_water_affected is None and not HOT_WATER.search(draft.report):
        missing.append("hot_water_affected")
    if not availability:
        missing.append("availability_preferences")
    return IntakeResult(symptoms=symptoms, urgency=result.urgency or explicit_urgency(draft.report),
                        availability_preferences=availability,
                        missing_information=missing, safety_signal=result.safety_signal)


def fallback(draft: IntakeRequest, gas_leak: bool = False) -> IntakeResponse:
    result = IntakeResult(symptoms=[], urgency=None, availability_preferences=[], missing_information=[],
                          safety_signal="possible_gas_leak" if gas_leak else "none")
    return IntakeResponse(source="fallback", result=reconcile(draft, result))


def validate_model_grounding(draft: IntakeRequest, result: IntakeResult) -> None:
    report = normalize_intake_text(draft.report)
    if any(normalize_intake_text(item) not in report for item in result.symptoms):
        raise ValueError("symptom is not grounded in the report")
    if draft.hot_water_affected is not None and len(result.symptoms) > 11:
        raise ValueError("explicit hot-water answer requires a symptom slot")
    availability = [normalize_intake_text(item) for item in availability_excerpts(draft.report, include_context=True)]
    if any(not any(normalize_intake_text(item) in excerpt for excerpt in availability)
           for item in result.availability_preferences):
        raise ValueError("availability is not grounded in a stated preference")
    if result.urgency is not None and result.urgency != explicit_urgency(draft.report):
        raise ValueError("urgency is not supported by an explicit priority")


def extract(draft: IntakeRequest) -> IntakeResponse:
    if possible_gas_leak(draft.report):
        return fallback(draft, gas_leak=True)
    try:
        result = extract_with_model(draft)
        if result is not None:
            validate_model_grounding(draft, result)
            return IntakeResponse(source="model", result=reconcile(draft, result))
    except (httpx.HTTPError, ValueError, KeyError, TypeError):
        # Provider errors and invalid replies both leave manual intake available.
        pass
    return fallback(draft)
