"""
Answer verification — the main hallucination guard.

1. Rule checks (free, deterministic)
   - citations that point to passages that don't exist
   - factual sentences without any citation
   - numbers/figures in the answer that appear in none of the passages
2. LLM claim check (fast model, JSON mode)
   - each claim is judged supported / unsupported against the passages

Produces a status (verified / partially_verified / unverified / not_applicable),
a score in [0, 1], and the list of problems used to repair the answer.
"""

import re
from dataclasses import asdict, dataclass, field

from loguru import logger

from config import settings
from llm.groq_client import complete_json
from llm.prompt_templates import VERIFIER_SYSTEM_PROMPT, VERIFIER_USER_TEMPLATE, format_context

CITATION_RE = re.compile(r"\[(\d{1,2}(?:\s*[,–-]\s*\d{1,2})*)(?:\s*,\s*p\.?\s*\d+)?\]")
NOT_COVERED_RE = re.compile(r"not covered in the loaded documents|do not contain enough information", re.I)
NUMBER_RE = re.compile(r"(?<![\w.\[])(\d{1,3}(?:,\d{2,3})+|\d+(?:\.\d+)?)(?![\w\]])")
LIST_MARKER_RE = re.compile(r"^\s*(?:[-*•]|\d{1,2}[.)])\s+")
SMALL_NUMBER_WORDS = {
    "1": "one", "2": "two", "3": "three", "4": "four", "5": "five", "6": "six", "7": "seven",
    "8": "eight", "9": "nine", "10": "ten", "11": "eleven", "12": "twelve", "15": "fifteen",
    "30": "thirty", "60": "sixty", "90": "ninety",
}
MAX_LLM_CLAIMS = 14


@dataclass
class Claim:
    id: int
    text: str
    citations: list[int]


@dataclass
class VerificationReport:
    status: str
    score: float
    method: str
    claims_checked: int = 0
    supported: int = 0
    unsupported_claims: list[dict] = field(default_factory=list)
    uncited_claims: list[str] = field(default_factory=list)
    invalid_citations: list[int] = field(default_factory=list)
    unsupported_numbers: list[str] = field(default_factory=list)

    @property
    def needs_repair(self) -> bool:
        return self.status in ("unverified", "partially_verified") and bool(
            self.unsupported_claims or self.invalid_citations or self.unsupported_numbers or self.uncited_claims
        )

    def problems(self) -> list[str]:
        out = [f'- Unsupported: "{c["claim"]}" ({c.get("reason", "not in sources")})' for c in self.unsupported_claims]
        out += [f"- Cites passage [{n}], which does not exist" for n in self.invalid_citations]
        out += [f"- The figure {n} does not appear in any source passage" for n in self.unsupported_numbers]
        out += [f'- No citation: "{c}"' for c in self.uncited_claims]
        return out

    def to_dict(self) -> dict:
        data = asdict(self)
        data["citation_issues"] = [f"[{n}]" for n in self.invalid_citations]
        return data


def _parse_citations(text: str) -> list[int]:
    nums: list[int] = []
    for group in CITATION_RE.findall(text):
        for part in re.split(r"\s*,\s*", group):
            if re.search(r"[–-]", part):
                a, b = (int(x) for x in re.split(r"\s*[–-]\s*", part)[:2])
                nums.extend(range(min(a, b), max(a, b) + 1))
            elif part.strip().isdigit():
                nums.append(int(part))
    return nums


def _strip_markdown(line: str) -> str:
    line = LIST_MARKER_RE.sub("", line)
    line = re.sub(r"^#+\s*", "", line)
    return line.replace("**", "").replace("__", "").strip()


def extract_claims(answer: str) -> list[Claim]:
    """Splits an answer into checkable sentences, keeping trailing citations attached."""
    claims: list[Claim] = []
    for raw_line in answer.splitlines():
        line = _strip_markdown(raw_line)
        if not line or NOT_COVERED_RE.search(line):
            continue
        parts = re.split(r"(?<=[.!?])\s+(?=[A-Z(“\"])", line)
        merged: list[str] = []
        for part in parts:
            lead = re.match(r"^((?:\[[^\]]+\]\s*)+)(.*)$", part)
            if lead and merged:
                merged[-1] += " " + lead.group(1).strip()
                part = lead.group(2)
            if part.strip():
                merged.append(part.strip())
        for sentence in merged:
            if len(sentence.split()) < 5 or (sentence.endswith(":") and len(sentence) < 80):
                continue
            claims.append(Claim(len(claims) + 1, sentence, _parse_citations(sentence)))
    return claims


def _numbers_in(text: str) -> list[str]:
    text = CITATION_RE.sub(" ", text)
    return [n for n in NUMBER_RE.findall(text)]


def _normalize_number(n: str) -> str:
    return n.replace(",", "")


def _number_supported(num: str, source_text: str) -> bool:
    norm = _normalize_number(num)
    if re.search(rf"(?<![\d.]){re.escape(norm)}(?![\d])", source_text):
        return True
    word = SMALL_NUMBER_WORDS.get(norm)
    return bool(word and re.search(rf"\b{word}\b", source_text, re.I))


def rule_check(answer: str, chunks: list[dict]) -> tuple[list[Claim], list[int], list[str], list[str]]:
    claims = extract_claims(answer)
    n_sources = len(chunks)
    invalid = sorted({n for n in _parse_citations(answer) if n < 1 or n > n_sources})
    uncited = [c.text for c in claims if not c.citations]

    source_text = " ".join(c["chunk_text"] for c in chunks).replace(",", "")
    unsupported_numbers: list[str] = []
    for claim in claims:
        for num in _numbers_in(claim.text):
            if not _number_supported(num, source_text) and num not in unsupported_numbers:
                unsupported_numbers.append(num)
    return claims, invalid, uncited, unsupported_numbers


def llm_check(claims: list[Claim], chunks: list[dict]) -> dict[int, dict]:
    """Returns {claim_id: {"supported": bool, "reason": str}} for checked claims."""
    selected = claims[:MAX_LLM_CLAIMS]
    claims_text = "\n".join(f"{c.id}. {CITATION_RE.sub('', c.text).strip()[:300]}" for c in selected)
    data = complete_json(
        [
            {"role": "system", "content": VERIFIER_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": VERIFIER_USER_TEMPLATE.format(
                    context=format_context(chunks, max_chars=settings.max_context_chars),
                    claims=claims_text,
                ),
            },
        ],
        model=settings.groq_fast_model,
        max_tokens=900,
    )
    results: dict[int, dict] = {}
    for item in data.get("results", []) if isinstance(data, dict) else []:
        try:
            results[int(item["id"])] = {
                "supported": bool(item.get("supported")),
                "reason": str(item.get("reason", ""))[:160],
            }
        except (KeyError, TypeError, ValueError):
            continue
    return results


def verify_answer(answer: str, chunks: list[dict], use_llm: bool | None = None) -> VerificationReport:
    if not chunks or not answer.strip():
        return VerificationReport(status="not_applicable", score=0.0, method="none")

    claims, invalid, uncited, bad_numbers = rule_check(answer, chunks)
    if not claims:
        return VerificationReport(status="not_applicable", score=1.0, method="rules")

    use_llm = settings.enable_llm_verifier if use_llm is None else use_llm
    method = "rules"
    unsupported: list[dict] = []
    supported = sum(1 for c in claims if c.citations)

    if use_llm:
        try:
            judged = llm_check(claims, chunks)
            if judged:
                method = "rules+llm"
                unsupported = [
                    {"claim": c.text, "reason": judged[c.id]["reason"]}
                    for c in claims
                    if c.id in judged and not judged[c.id]["supported"]
                ]
                supported = sum(1 for c in claims if judged.get(c.id, {}).get("supported", True))
        except Exception as e:
            logger.warning(f"LLM verification failed, using rules only: {e}")

    score = supported / len(claims)
    if bad_numbers:
        score *= 0.75
    if invalid:
        score *= 0.5
    score = round(score, 3)

    if score >= settings.verification_pass_score and not invalid and not bad_numbers:
        status = "verified"
    elif score >= 0.5:
        status = "partially_verified"
    else:
        status = "unverified"

    return VerificationReport(
        status=status,
        score=score,
        method=method,
        claims_checked=len(claims),
        supported=supported,
        unsupported_claims=unsupported,
        uncited_claims=uncited if method == "rules" else [],
        invalid_citations=invalid,
        unsupported_numbers=bad_numbers,
    )
