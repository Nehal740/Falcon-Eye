"""Output verification: injection, secret-leak, evidence and consistency checks.

Like ``policy.py`` this module has no database or web imports. It receives
plain data and returns a plain result, so it is easy to test and cannot
quietly depend on a paid AI service.

What it can and cannot do (read docs/VERIFICATION.md)
-----------------------------------------------------
* It compares an agent's text with the evidence the agent supplies, and with
  what Falcon Eye itself recorded about that agent. It does NOT know facts
  about the world. Without evidence it can only say "not verified".
* All checks are heuristics (word overlap, patterns, number comparison).
  They produce false positives and false negatives. Risk levels come from
  written rules (see ``assess``), not from a probability.
* The result can only make a decision STRICTER. It never grants permission.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field

LIMITATIONS = ("Heuristic checks against the evidence you supplied. Not proof of truth; "
               "can miss problems and can flag correct text.")

MAX_TEXT = 20_000
RISKS = ("LOW", "MEDIUM", "HIGH", "CRITICAL")


@dataclass
class Signal:
    code: str          # stable machine name, e.g. "prompt_injection.override"
    family: str        # injection | secret | claim | contradiction | reference | report | argument
    severity: str      # info | medium | high
    detail: str        # short, human readable. NEVER contains secret values.

    def as_dict(self) -> dict:
        return {"code": self.code, "family": self.family,
                "severity": self.severity, "detail": self.detail}


# ----------------------------------------------------------------- patterns

_INJECTION = [
    ("override", "high", r"\b(ignore|disregard|forget|override)\b[^.\n]{0,40}\b(previous|prior|above|earlier|all|any|your)\b[^.\n]{0,30}\b(instructions?|rules?|prompts?|guidelines?|polic(?:y|ies))"),
    ("role_hijack", "medium", r"\b(you are now|from now on you|act as|pretend (to be|you are)|new persona|developer mode|jailbreak|\bDAN\b)"),
    ("prompt_exfiltration", "high", r"\b(reveal|show|print|repeat|output|leak|tell me)\b[^.\n]{0,40}\b(system prompt|hidden (instructions|prompt)|your instructions|initial prompt)"),
    ("tool_steering", "high", r"\b(call|run|execute|invoke|use)\b[^.\n]{0,25}\b(tool|function|command|shell|script)\b[^.\n]{0,40}\b(without|do not|don't|never)\b[^.\n]{0,20}\b(ask|approval|confirm|asking|tell|verification)"),
    ("approval_evasion", "high", r"\b(do not|don't|never|skip|bypass|disable)\b[^.\n]{0,25}\b(approval|firewall|falcon eye|policy|security check|human review|confirmation|safeguards?)"),
    ("delimiter_spoof", "medium", r"(<\s*/?\s*(system|assistant)\s*>|\[/?INST\]|###\s*(system|instruction)|<\|im_(start|end)\|>)"),
    ("exfil_instruction", "high", r"\b(send|post|upload|email|forward|exfiltrate)\b[^.\n]{0,40}\b(to|at)\b[^.\n]{0,30}(https?://|@\w)[^.\n]{0,60}\b(password|credential|secret|api key|token|\.env|private key)"),
]

_SECRETS = [
    ("falcon_eye_agent_key", r"\bfe_live_[0-9a-f]{12}_[A-Za-z0-9_-]{20,}"),
    ("aws_access_key", r"\bAKIA[0-9A-Z]{16}\b"),
    ("private_key_block", r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    ("github_token", r"\bgh[pousr]_[A-Za-z0-9]{30,}"),
    ("api_key_sk", r"\bsk-[A-Za-z0-9_-]{20,}"),
    ("groq_key", r"\bgsk_[A-Za-z0-9]{20,}"),
    ("google_api_key", r"\bAIza[0-9A-Za-z_-]{30,}"),
    ("jwt", r"\beyJ[A-Za-z0-9_-]{8,}\.eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}"),
    ("password_assignment", r"(?i)\b(password|passwd|pwd|secret|api[_-]?key|token)\b\s*[:=]\s*['\"]?[^\s'\"]{6,}"),
]

_DANGEROUS_ARGS = [
    ("path_traversal", r"(\.\./|\.\.\\|%2e%2e%2f)"),
    ("shell_chaining", r"(;|&&|\|\||\|)\s*(rm|del|curl|wget|nc|powershell|bash|sh|chmod|dd)\b"),
    ("command_substitution", r"(\$\(|`[^`]+`)"),
    ("sql_injection", r"(?i)('\s*(or|and)\s*'?\d|;\s*(drop|delete|truncate|update)\s+\w+|union\s+select|--\s*$)"),
    ("sensitive_path", r"(?i)(/etc/(shadow|passwd)|\.ssh[/\\]|id_rsa|\.env\b|system32[/\\]config)"),
]

_STOP = set("""the and for are was were has have had that this with from into onto about over under than then
their there they them its it's our your you his her she him but not nor can could would should will shall
may might must been being also just only very more most some any all each per via using used use""".split())
_HEDGE = re.compile(r"\b(may|might|could|possibly|perhaps|probably|i think|i believe|appears? to|seems? to|likely)\b", re.I)
_NEGATION = re.compile(r"\b(not|no|never|none|cannot|can't|isn't|aren't|wasn't|weren't|didn't|doesn't|don't|without)\b", re.I)
_NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?%?")
_CVE = re.compile(r"\bCVE-\d{4}-\d{4,7}\b", re.I)
_URL = re.compile(r"https?://[^\s)>\]\"']+", re.I)
_ENDPOINT = re.compile(r"(?<![\w/])/(?:v\d+|api)/[A-Za-z0-9_\-./{}]+")
_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+|\n+")


# ----------------------------------------------------------------- helpers

def text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", "ignore")).hexdigest()


def _numbers(s: str) -> set[str]:
    return {n.replace(",", "").rstrip("%").rstrip(".") for n in _NUMBER.findall(s)}


def _words(s: str) -> set[str]:
    return {w for w in re.findall(r"[a-z][a-z\-_]{2,}", s.lower()) if w not in _STOP}


def _sentences(s: str) -> list[str]:
    return [x.strip() for x in _SENT_SPLIT.split(s) if len(x.strip()) >= 8]


def _flatten(value, out: list[str], depth: int = 0) -> None:
    if depth > 4 or len(out) > 200:
        return
    if isinstance(value, dict):
        for k, v in value.items():
            out.append(str(k))
            _flatten(v, out, depth + 1)
    elif isinstance(value, (list, tuple)):
        for v in value:
            _flatten(v, out, depth + 1)
    elif value is not None:
        out.append(str(value))


# ----------------------------------------------------------------- scanners

def scan_injection(text: str) -> list[Signal]:
    found = []
    for name, severity, pattern in _INJECTION:
        if re.search(pattern, text, re.I):
            found.append(Signal(f"prompt_injection.{name}", "injection", severity,
                                f"Text looks like an attempt to steer the agent ({name.replace('_', ' ')})."))
    return found


def scan_secrets(text: str) -> list[Signal]:
    found = []
    for name, pattern in _SECRETS:
        if re.search(pattern, text):
            found.append(Signal(f"secret.{name}", "secret", "high",
                                f"Text appears to contain a secret ({name.replace('_', ' ')})."))
    return found


def redact(text: str) -> str:
    for _name, pattern in _SECRETS:
        text = re.sub(pattern, "[REDACTED]", text)
    return text


def scan_arguments(arguments) -> list[Signal]:
    parts: list[str] = []
    _flatten(arguments, parts)
    blob = "\n".join(parts)
    found = [Signal(f"argument.{name}", "argument", "high",
                    f"Tool arguments contain a risky pattern ({name.replace('_', ' ')}).")
             for name, pattern in _DANGEROUS_ARGS if re.search(pattern, blob)]
    found += [Signal(s.code.replace("secret.", "argument_secret."), "argument", "high",
                     "Tool arguments contain what looks like a secret.") for s in scan_secrets(blob)]
    found += [Signal(s.code.replace("prompt_injection.", "argument_injection."), "argument", s.severity,
                     "Tool arguments contain instruction-like text.")
              for s in scan_injection(blob) if s.severity == "high"]
    return found


# ----------------------------------------------------------------- claims

def _checkable(sentence: str, endpoints_handled: bool = False) -> bool:
    if sentence.rstrip().endswith("?") or _HEDGE.search(sentence):
        return False
    if endpoints_handled:  # endpoints are checked separately against the known list
        sentence = _ENDPOINT.sub(" ", sentence)
    return bool(_NUMBER.search(sentence) or _CVE.search(sentence)
                or _URL.search(sentence) or _ENDPOINT.search(sentence))


def _support(claim: str, evidence: list[dict]) -> tuple[str, str | None]:
    """Return (SUPPORTED | CONTRADICTED | UNSUPPORTED, evidence id)."""
    claim_words, claim_nums = _words(claim), _numbers(claim)
    if not claim_words:
        return "UNSUPPORTED", None
    best = (0.0, None, "")
    for item in evidence:
        for sent in _sentences(item["text"]) or [item["text"]]:
            overlap = len(claim_words & _words(sent)) / len(claim_words)
            if overlap > best[0]:
                best = (overlap, item["id"], sent)
    overlap, ev_id, sent = best
    if overlap < 0.5:
        # Specific identifiers (CVE, URL, endpoint) may still appear verbatim.
        ids = _CVE.findall(claim) + _URL.findall(claim) + _ENDPOINT.findall(claim)
        if ids and not claim_nums - _numbers(" ".join(ids)):
            for item in evidence:
                if all(i.lower() in item["text"].lower() for i in ids):
                    return "SUPPORTED", item["id"]
        return "UNSUPPORTED", None
    if claim_nums:
        ev_nums = _numbers(sent)
        if ev_nums and not claim_nums <= ev_nums:
            return "CONTRADICTED", ev_id
        if not ev_nums:
            return "UNSUPPORTED", ev_id
    if bool(_NEGATION.search(claim)) != bool(_NEGATION.search(sent)) and overlap >= 0.6:
        return "CONTRADICTED", ev_id
    return "SUPPORTED", ev_id


def _self_contradictions(sentences: list[str]) -> list[tuple[str, str]]:
    pairs = []
    for i, a in enumerate(sentences):
        for b in sentences[i + 1:]:
            wa, wb = _words(a), _words(b)
            if not wa or not wb or len(wa & wb) / min(len(wa), len(wb)) < 0.6:
                continue
            na, nb = _numbers(a), _numbers(b)
            if (na and nb and not na & nb) or (
                    bool(_NEGATION.search(a)) != bool(_NEGATION.search(b)) and not na and not nb):
                pairs.append((a[:80], b[:80]))
    return pairs[:5]


def _reference_signals(text: str, evidence: list[dict], known_endpoints: list[str] | None) -> list[Signal]:
    signals = []
    ev_blob = "\n".join(e["text"] for e in evidence).lower()
    for ep in sorted(set(_ENDPOINT.findall(text)))[:20]:
        if known_endpoints:
            ok = any(ep.rstrip("/.").lower() == k.lower() or re.fullmatch(
                re.sub(r"\\\{[^}]+\\\}", r"[^/]+", re.escape(k.lower())), ep.rstrip("/.").lower())
                for k in known_endpoints)
            if not ok:
                signals.append(Signal("reference.unknown_endpoint", "reference", "high",
                                      f"Endpoint {ep[:60]} is not in the list of known endpoints."))
        elif ep.lower() not in ev_blob:
            signals.append(Signal("reference.unverified_endpoint", "reference", "medium",
                                  f"Endpoint {ep[:60]} is not mentioned in the evidence."))
    for cve in sorted(set(c.upper() for c in _CVE.findall(text)))[:20]:
        if cve.lower() not in ev_blob:
            signals.append(Signal("reference.unverified_cve", "reference", "medium",
                                  f"{cve} is not mentioned in the evidence."))
    for url in sorted(set(_URL.findall(text)))[:20]:
        if url.lower().rstrip("/.,") not in ev_blob:
            signals.append(Signal("reference.unverified_url", "reference", "medium",
                                  "A link in the text does not appear in the evidence."))
    return signals


def _report_signals(reported: list[dict], known: list[dict]) -> list[Signal]:
    """Compare 'I did X' claims with what Falcon Eye actually recorded."""
    signals = []
    for rep in reported[:20]:
        action = str(rep.get("action", "")).lower()
        resource = str(rep.get("resource", "") or "")
        matches = [k for k in known if str(k.get("action", "")).lower() == action
                   and (not resource or str(k.get("resource", "") or "") == resource)]
        if not matches:
            signals.append(Signal("report.unseen_action", "report", "high",
                                  f"Agent says it did '{action[:40]}', but Falcon Eye has no recent record of asking."))
            continue
        usable = [m for m in matches if m.get("decision") == "ALLOW"
                  or (m.get("decision") == "REQUIRE_APPROVAL" and m.get("approval_status") == "APPROVED")]
        if not usable:
            signals.append(Signal("report.contradicted_action", "report", "high",
                                  f"Agent says it did '{action[:40]}', but Falcon Eye blocked it or it was not approved."))
    return signals


# ----------------------------------------------------------------- assessment

def assess(signals: list[Signal], *, consequential: bool, has_tool_call: bool,
           checkable: int, evidence_given: bool, sensitivity: str = "standard") -> tuple[str, list[str]]:
    """Written rules, strongest first. Returns (risk level, reasons)."""
    codes = [s.code for s in signals]
    fam = lambda f, sev=None: [s for s in signals if s.family == f and (sev is None or s.severity == sev)]  # noqa: E731
    contradiction = bool(fam("contradiction")) or any(c == "claim.contradicted" for c in codes)
    report_bad = bool(fam("report", "high"))
    contradicted_report = "report.contradicted_action" in codes
    bad_args = bool(fam("argument", "high"))
    inj_high = bool(fam("injection", "high"))
    secret = bool(fam("secret"))
    unsupported = [c for c in codes if c in ("claim.unsupported",) or c.startswith("reference.")]
    unknown_ep = "reference.unknown_endpoint" in codes

    reasons: list[str] = []
    if consequential and (contradicted_report or bad_args or contradiction or (inj_high and has_tool_call)):
        risk = "CRITICAL"
        if contradicted_report:
            reasons.append("The agent reports an action that Falcon Eye blocked or that was never approved.")
        if bad_args:
            reasons.append("The tool call arguments contain a dangerous pattern or a secret.")
        if contradiction:
            reasons.append("The output contradicts the evidence or itself, and it drives an action.")
        if inj_high and has_tool_call:
            reasons.append("Instruction-like text was found alongside a tool call.")
    elif contradiction or report_bad or bad_args or inj_high or secret or unknown_ep:
        risk = "HIGH"
        if contradiction:
            reasons.append("The output contradicts the supplied evidence or itself.")
        if report_bad:
            reasons.append("The agent's report of what it did does not match Falcon Eye's records.")
        if bad_args:
            reasons.append("Arguments contain a risky pattern or secret.")
        if inj_high:
            reasons.append("The text contains a strong prompt-injection signal.")
        if secret:
            reasons.append("The text appears to contain a secret.")
        if unknown_ep:
            reasons.append("The text mentions an endpoint that is not in the known list.")
    elif unsupported or fam("injection") or (checkable and not evidence_given):
        risk = "MEDIUM"
        if unsupported:
            reasons.append("Some checkable statements or references are not supported by the evidence.")
        if fam("injection"):
            reasons.append("The text contains a weaker prompt-injection signal.")
        if checkable and not evidence_given:
            reasons.append("No evidence was supplied, so statements could not be verified.")
    else:
        risk = "LOW"
        reasons.append("No problems found by the checks that were possible.")
    return risk, reasons


def decide(risk: str, *, consequential: bool, secret: bool, sensitivity: str = "standard") -> tuple[str, bool]:
    """Return (decision, flagged). ALLOW / REQUIRE_APPROVAL / BLOCK."""
    if risk == "CRITICAL":
        return "BLOCK", True
    if risk == "HIGH":
        if consequential or secret or sensitivity == "strict":
            return "REQUIRE_APPROVAL", True
        return "ALLOW", True
    if risk == "MEDIUM":
        if sensitivity == "strict" and consequential:
            return "REQUIRE_APPROVAL", True
        return "ALLOW", True
    return "ALLOW", False


# ----------------------------------------------------------------- main entry

def verify(text: str, *, evidence: list[dict] | None = None, kind: str = "response",
           tool_call: dict | None = None, reported_actions: list[dict] | None = None,
           known_actions: list[dict] | None = None, known_endpoints: list[str] | None = None,
           consequential: bool = False, sensitivity: str = "standard") -> dict:
    evidence = [e for e in (evidence or []) if e.get("text")]
    text = text[:MAX_TEXT]
    consequential = consequential or bool(tool_call) or kind in ("tool_call", "report")
    signals: list[Signal] = []

    signals += scan_injection(text)
    signals += scan_secrets(text)
    if tool_call:
        signals += scan_arguments(tool_call.get("arguments"))
    for ev in evidence:  # evidence is untrusted too: it may carry injected instructions
        signals += [Signal(s.code.replace("prompt_injection.", "evidence_injection."), "injection",
                           s.severity, "The supplied evidence itself contains instruction-like text.")
                    for s in scan_injection(ev["text"]) if s.severity == "high"][:1]

    sentences = _sentences(text)
    claims = [s for s in sentences if _checkable(s, bool(known_endpoints))]
    supported, unsupported, contradicted, evidence_used = [], [], [], set()
    for claim in claims[:60]:
        if not evidence:
            unsupported.append(claim[:200])
            continue
        verdict, ev_id = _support(claim, evidence)
        if ev_id:
            evidence_used.add(ev_id)
        {"SUPPORTED": supported, "CONTRADICTED": contradicted, "UNSUPPORTED": unsupported}[verdict].append(claim[:200])
    if evidence:
        if unsupported:
            signals.append(Signal("claim.unsupported", "claim", "medium",
                                  f"{len(unsupported)} statement(s) are not supported by the evidence."))
        if contradicted:
            signals.append(Signal("claim.contradicted", "claim", "high",
                                  f"{len(contradicted)} statement(s) conflict with the evidence."))
    for a, b in _self_contradictions(sentences):
        signals.append(Signal("contradiction.internal", "contradiction", "high",
                              f"Two statements disagree: \"{a}\" / \"{b}\""))
    signals += _reference_signals(text, evidence, known_endpoints)
    if reported_actions:
        signals += _report_signals(reported_actions, known_actions or [])

    risk, reasons = assess(signals, consequential=consequential, has_tool_call=bool(tool_call),
                           checkable=len(claims), evidence_given=bool(evidence), sensitivity=sensitivity)
    secret = any(s.family == "secret" for s in signals)
    decision, flagged = decide(risk, consequential=consequential, secret=secret, sensitivity=sensitivity)

    if contradicted or any(s.family in ("contradiction", "report") for s in signals):
        status = "CONTRADICTED"
    elif not evidence:
        status = "NOT_VERIFIED" if claims else "NO_CHECKABLE_CLAIMS"
    elif not claims:
        status = "NO_CHECKABLE_CLAIMS"
    elif unsupported:
        status = "PARTIALLY_VERIFIED"
    else:
        status = "VERIFIED"

    result = {
        "verification_status": status,
        "risk_level": risk,
        "decision": decision,
        "flagged": flagged,
        "requires_human_approval": decision == "REQUIRE_APPROVAL",
        "reasons": reasons,
        "supported_claims": [redact(x) for x in supported[:20]],
        "unsupported_claims": [redact(x) for x in unsupported[:20]],
        "contradicted_claims": [redact(x) for x in contradicted[:20]],
        "evidence_used": sorted(evidence_used),
        "signals": [{**s.as_dict(), "detail": redact(s.detail)} for s in signals][:40],
        "checked": {"claims_checked": len(claims), "evidence_items": len(evidence),
                    "tool_call": bool(tool_call), "consequential": consequential},
        "limitations": LIMITATIONS,
    }
    if secret:
        result["redacted_text"] = redact(text)
    if unsupported or contradicted:
        result["regeneration_hint"] = (
            "Rewrite using only the supplied evidence. State which facts are supported, which are "
            "assumptions, and what information is missing. Do not invent numbers, links or endpoints.")
    return result
