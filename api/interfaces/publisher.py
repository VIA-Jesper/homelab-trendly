from abc import ABC, abstractmethod


class IPublisher(ABC):
    """
    Interface for publishing completed articles.

    Implement this to push finished articles to any destination:
    - WordPress (via REST API)
    - Headless CMS (Contentful, Sanity, etc.)
    - Local filesystem as .md files
    - Static site generator content folders
    - Custom CMS endpoints

    Register the implementation in services/pipeline.py.
    The publisher is called when a job reaches status "complete".
    """

    @abstractmethod
    async def publish(self, job_id: str, content: str, context: dict) -> dict:
        """
        Publish a completed article.

        Args:
            job_id: The job UUID string
            content: Final article content (markdown or HTML)
            context: Job context dict (contains keyword, article_type, site info, etc.)

        Returns:
            {
                "success": bool,
                "url": str | None,    # published URL if available
                "error": str | None   # error message if success is False
            }
        """
        ...
