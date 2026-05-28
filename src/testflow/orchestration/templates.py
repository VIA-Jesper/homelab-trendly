"""
Article template loader.

Templates are YAML files in templates/ that define the structural contract
for each article type: required sections, word counts, required elements, tone.
"""
from pathlib import Path

import yaml
from pydantic import BaseModel

TEMPLATES_DIR = Path("templates")


class TemplateSection(BaseModel):
    id: str
    heading: str
    purpose: str
    target_words: int
    required_elements: list[str] = []


class ArticleTemplate(BaseModel):
    type: str
    display_name: str
    schema_type: str
    tone_guidance: str
    min_products: int
    max_products: int
    required_sections: list[TemplateSection]


def load_template(article_type: str) -> ArticleTemplate:
    """Load an article template by type name."""
    path = TEMPLATES_DIR / f"{article_type}.yaml"
    if not path.exists():
        available = list_templates()
        raise ValueError(f"Unknown article type: {article_type!r}. Available: {available}")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return ArticleTemplate(**data)


def list_templates() -> list[str]:
    """Return list of available template type names."""
    if not TEMPLATES_DIR.exists():
        return []
    return [p.stem for p in TEMPLATES_DIR.glob("*.yaml")]
