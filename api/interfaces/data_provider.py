from abc import ABC, abstractmethod


class IDataProvider(ABC):
    """
    Interface for providing job context data to the orchestrator.

    Implement this to plug in external data sources:
    - Product catalogs
    - Keyword gap analysis
    - Competitor analysis
    - Trend data
    - SEO metrics

    The returned dict is stored as job.context (JSONB) and passed
    to the agent as part of each step's input.
    """

    @abstractmethod
    async def get_context(self, site_id: str) -> dict:
        """
        Return a context dict for a new job on the given site.
        Must include at minimum: article_type, target_keyword.
        All other fields are optional and extensible.
        """
        ...
