"""
Article scheduling logic - Phase 2 placeholder.

In Phase 2, this module will manage:
- Article topic queues per site
- Publication frequency limits
- Scheduling metadata in the state database

For MVP: not used. OpenClaw is triggered manually by the user.
"""


def get_next_topic(site_name: str) -> dict | None:
    """
    Phase 2: Return the next topic from the queue for a given site.
    MVP: Not implemented.
    """
    raise NotImplementedError("Scheduling is Phase 2. Trigger OpenClaw manually for MVP.")


def is_quota_reached(site_name: str, daily_limit: int = 3) -> bool:
    """
    Phase 2: Check if the daily article quota has been reached.
    MVP: Always returns False (no limit enforced).
    """
    return False
