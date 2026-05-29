from abc import ABC, abstractmethod


class IQACheck(ABC):
    """
    Interface for individual QA validation checks.

    Implement this to add new quality checks without modifying core QA logic.
    Each check evaluates one specific aspect of the generated content.

    Severity levels:
    - BLOCKER: check must pass before the article can proceed or publish
    - WARNING: flagged in output but does not block the pipeline

    Register implementations in services/qa.py via QAService.register_check().

    Example checks to implement:
    - Meta description length (150-160 chars) - BLOCKER
    - Keyword density (0.5-2.5%) - WARNING
    - Affiliate disclosure present - BLOCKER
    - No raw URLs in content - BLOCKER
    - Minimum word count - BLOCKER
    - CTA shortcode present - BLOCKER
    """

    @property
    @abstractmethod
    def check_id(self) -> str:
        """Unique identifier, e.g. 'QA-001'"""
        ...

    @property
    @abstractmethod
    def severity(self) -> str:
        """BLOCKER or WARNING"""
        ...

    @abstractmethod
    def evaluate(self, content: str, context: dict) -> dict:
        """
        Evaluate the content against this check.

        Returns:
            {
                "passed": bool,
                "message": str   # human-readable result or failure reason
            }
        """
        ...
