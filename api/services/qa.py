import re

from interfaces.qa_check import IQACheck


class MetaDescriptionLengthCheck(IQACheck):
    @property
    def check_id(self) -> str:
        return "QA-001"

    @property
    def severity(self) -> str:
        return "BLOCKER"

    def evaluate(self, content: str, context: dict) -> dict:
        # meta_description is injected by _run_python_qa from the optimize_seo seo.description field
        meta = context.get("meta_description", "")
        length = len(meta)
        if not meta:
            return {"passed": False, "message": "Meta description missing or empty"}
        passed = 120 <= length <= 160
        return {
            "passed": passed,
            "message": f"Meta description length {length} chars (required: 120-160)" if not passed else "OK",
        }


class NoRawUrlsCheck(IQACheck):
    @property
    def check_id(self) -> str:
        return "QA-002"

    @property
    def severity(self) -> str:
        return "BLOCKER"

    def evaluate(self, content: str, context: dict) -> dict:
        # Strip markdown links [text](url) - those are intentional and get converted at publish time.
        # Only flag URLs that appear as bare text outside of link syntax.
        stripped = re.sub(r'\[[^\]]*\]\(https?://[^)]+\)', '', content)
        urls = re.findall(r"https?://", stripped)
        passed = len(urls) == 0
        return {
            "passed": passed,
            "message": f"Found {len(urls)} bare URL(s) in article body" if not passed else "OK",
        }


class MinWordCountCheck(IQACheck):
    @property
    def check_id(self) -> str:
        return "QA-003"

    @property
    def severity(self) -> str:
        return "BLOCKER"

    def evaluate(self, content: str, context: dict) -> dict:
        min_words = context.get("min_words", 800)
        word_count = len(content.split())
        passed = word_count >= min_words
        return {
            "passed": passed,
            "message": f"Word count {word_count} below minimum {min_words}" if not passed else "OK",
        }


class NoDashCheck(IQACheck):
    """No em/en dashes anywhere - the strongest AI tell and a hard house rule.
    The generator prompt forbids them; this enforces it deterministically so a
    stray dash can never reach publish."""

    @property
    def check_id(self) -> str:
        return "QA-004"

    @property
    def severity(self) -> str:
        return "BLOCKER"

    def evaluate(self, content: str, context: dict) -> dict:
        em = content.count("—")   # em dash
        en = content.count("–")   # en dash
        total = em + en
        return {
            "passed": total == 0,
            "message": "OK" if total == 0
            else f"Found {em} em-dash and {en} en-dash char(s); use plain hyphens",
        }


# AI-slop phrases that almost never appear in genuine human affiliate writing.
# Mirrors the hard bans in prompts/generate_base.txt - kept here so QA enforces
# them deterministically instead of trusting the model to obey.
_FORBIDDEN_PHRASES = (
    "det er værd at bemærke",
    "det er værd at nævne",
    "man kan argumentere for",
    "det er alligevel rimeligt at",
    "som nævnt ovenfor",
    "som tidligere nævnt",
    "i denne anmeldelse",
    "i dette indlæg",
    "i dette udvalg",
    "velkommen til",
    "briefen",
    "analytisk set",
    "popularityrank",
    "popularityscore",
)


class ForbiddenPhraseCheck(IQACheck):
    """Block AI-slop phrases and the brief's forbidden superlatives. These are
    hard bans (per generate_base.txt and the brief's compliance rules), so a hit
    blocks and triggers a regenerate rather than shipping slop."""

    @property
    def check_id(self) -> str:
        return "QA-005"

    @property
    def severity(self) -> str:
        return "BLOCKER"

    def evaluate(self, content: str, context: dict) -> dict:
        lc = content.lower()
        banned = list(_FORBIDDEN_PHRASES)
        compliance = (context.get("brief") or {}).get("compliance") or {}
        banned += [s.lower() for s in compliance.get("forbidden_superlatives", [])]
        hits = sorted({p for p in banned if p and p in lc})
        return {
            "passed": not hits,
            "message": "OK" if not hits else f"Found banned phrase(s): {', '.join(hits)}",
        }


class QAService:
    """
    Runs all registered QA checks against article content.
    Register new checks via register_check() - no core logic changes needed.
    """

    def __init__(self) -> None:
        self._checks: list[IQACheck] = []
        # Register built-in checks
        self.register_check(MetaDescriptionLengthCheck())
        self.register_check(NoRawUrlsCheck())
        self.register_check(MinWordCountCheck())
        self.register_check(NoDashCheck())
        self.register_check(ForbiddenPhraseCheck())

    def register_check(self, check: IQACheck) -> None:
        self._checks.append(check)

    def run(self, content: str, context: dict) -> dict:
        results = []
        blockers_failed = 0

        for check in self._checks:
            result = check.evaluate(content, context)
            results.append({
                "check_id": check.check_id,
                "severity": check.severity,
                "passed": result["passed"],
                "message": result["message"],
            })
            if not result["passed"] and check.severity == "BLOCKER":
                blockers_failed += 1

        return {
            "passed": blockers_failed == 0,
            "blocker_failures": blockers_failed,
            "results": results,
        }


qa_service = QAService()
