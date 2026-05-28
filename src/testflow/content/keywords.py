"""
Keyword stub - Phase 3 placeholder.

In Phase 3, this will integrate with Ahrefs/SEMrush API for real keyword data.
For MVP, returns placeholder data based on the seed keyword.
"""


def get_keyword_ideas(seed_keyword: str, n: int = 5) -> list[dict]:
    """
    Return keyword ideas for a seed keyword.

    Phase 3: Replace with Ahrefs/SEMrush API call.
    MVP: Returns placeholder data.
    """
    # Placeholder - OpenClaw uses PriceRunner keyword tree natively
    return [
        {"keyword": seed_keyword, "volume": None, "difficulty": None, "source": "seed"},
    ]
