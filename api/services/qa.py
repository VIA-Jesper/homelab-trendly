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
        passed = 150 <= length <= 160
        return {
            "passed": passed,
            "message": f"Meta description length {length} chars (required: 150-160)" if not passed else "OK",
        }


class NoRawUrlsCheck(IQACheck):
    @property
    def check_id(self) -> str:
        return "QA-002"

    @property
    def severity(self) -> str:
        return "BLOCKER"

    def evaluate(self, content: str, context: dict) -> dict:
        # Strip markdown links [text](url) — those are intentional and get converted at publish time.
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
