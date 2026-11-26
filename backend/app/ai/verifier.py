"""The trust layer. A candidate claim becomes evidence only if its quote occurs exactly once in the immutable body.
Offsets are computed here, server-side, never taken from the model."""
from dataclasses import dataclass, field

ALLOWED: dict[str, set[str]] = {
    "initial_training": {"completed"},
    "knowledge_transfer": {"shadowing", "supported_execution", "independent_execution"},
    "standard_requests": {"independent", "occasional_support", "support_required"},
    "complex_scenarios": {"coverage_pending", "coverage_complete"},
    "overall_independence": {"reported_independent"},
    "onboarding_closure": {"reported_closed", "reported_open"},
    "technical_readiness_report": {"ready", "ready_with_support", "partially_ready", "not_ready"},
    "access": {"requested", "awaiting_approval", "approved", "not_provisioned", "active", "confirmed_usable"},
}
MAX_CLAIMS = 24
KEYS = {"scope", "value", "quote", "reference"}


@dataclass
class Verified:
    envelope_ok: bool
    accepted: list[dict] = field(default_factory=list)  # {scope, value, reference, quote, start, end}
    rejected: list[dict] = field(default_factory=list)  # {raw, reason}
    error: str | None = None

    @property
    def status(self) -> str:
        if not self.envelope_ok:
            return "failed"
        return "partial" if self.rejected else "ok"


def verify(body: str, response: object, source_label: str = "source") -> Verified:
    if not isinstance(response, dict) or set(response) != {"claims"} or not isinstance(response["claims"], list):
        return Verified(envelope_ok=False, error="Envelope must be exactly {\"claims\": [...]}")
    if len(response["claims"]) > MAX_CLAIMS:
        return Verified(envelope_ok=False, error=f"More than {MAX_CLAIMS} claims")

    out = Verified(envelope_ok=True)
    seen: set[tuple] = set()
    for raw in response["claims"]:
        reason = _check(body, raw, source_label)
        if reason:
            out.rejected.append({"raw": raw if isinstance(raw, dict) else {"value": repr(raw)}, "reason": reason})
            continue
        start = body.find(raw["quote"])
        key = (raw["scope"], raw["value"], raw.get("reference"), start)
        if key in seen:
            out.rejected.append({"raw": raw, "reason": "duplicate claim"})
            continue
        seen.add(key)
        end = start + len(raw["quote"])
        assert body[start:end] == raw["quote"]
        out.accepted.append(
            {
                "scope": raw["scope"],
                "value": raw["value"],
                "reference": raw.get("reference"),
                "quote": raw["quote"],
                "start": start,
                "end": end,
            }
        )
    return out


def _check(body: str, raw: object, label: str) -> str | None:
    if not isinstance(raw, dict):
        return "claim is not an object"
    extra = set(raw) - KEYS
    if extra:
        return f"unexpected keys: {', '.join(sorted(extra))}"
    scope, value, quote, ref = raw.get("scope"), raw.get("value"), raw.get("quote"), raw.get("reference")
    if scope not in ALLOWED or value not in ALLOWED[scope]:
        return f"unsupported scope/value pair: {scope}/{value}"
    if not isinstance(quote, str) or not quote.strip():
        return "empty quote"
    count = body.count(quote)
    if count == 0:
        return f"no exact match in {label}"
    if count > 1:
        return f"quote is ambiguous ({count} matches in {label}); a longer excerpt is needed"
    if scope == "access":
        if not isinstance(ref, str) or not ref.strip():
            return "access claim without a system reference"
        if ref not in quote:
            return "cited span does not contain the system reference"
    elif ref not in (None, ""):
        return "reference is only allowed for access claims"
    return None
