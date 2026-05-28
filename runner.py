#!/usr/bin/env python3
"""
runner.py - TestFlow CLI entry point.

Does NOT call any LLM - OpenClaw does all reasoning.
Handles:
  1. Pre-flight checks (tool server health, env vars, site YAML validation)
  2. Dry-run mode (fetch products + run compliance pipeline without publishing)
  3. Prompt generation (print the OpenClaw instruction to paste)
  4. Category discovery helper

Usage:
  # Pre-flight
  python runner.py --site sites/site-one.yaml --check

  # Dry run
  python runner.py --site sites/site-one.yaml --products "Roomba j9+" --dry-run

  # Generate OpenClaw prompt
  python runner.py --site sites/site-one.yaml --products "Roomba j9+"
  python runner.py --site sites/site-one.yaml --topic "Bedste robotstovsuger 2025" --template best-of-list

  # Category discovery helper
  python runner.py --discover "robotstovsuger"
"""
import argparse
import sys
import os

import httpx
from pathlib import Path

TOOL_SERVER = f"http://{os.getenv('TOOL_SERVER_HOST', 'localhost')}:{os.getenv('TOOL_SERVER_PORT', '8000')}"


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="TestFlow pipeline CLI")
    p.add_argument("--site", help="Path to site YAML (e.g. sites/site-one.yaml)")
    p.add_argument("--products", nargs="+", help="Specific product name(s) for Mode A")
    p.add_argument("--topic", help="Article topic (Mode B, free text)")
    p.add_argument("--keyword", help="SEO keyword (optional override)")
    p.add_argument("--template", choices=["best-of-list", "single-review", "comparison", "versus", "buying-guide"])
    p.add_argument("--dry-run", action="store_true", help="Fetch products + audit only; no LLM, no publish")
    p.add_argument("--check", action="store_true", help="Pre-flight checks only")
    p.add_argument("--discover", metavar="QUERY", help="Discover PriceRunner category IDs for a product type")
    return p


def check_tool_server() -> bool:
    try:
        r = httpx.get(f"{TOOL_SERVER}/health", timeout=3)
        return r.status_code == 200 and r.json().get("status") == "ok"
    except Exception:
        return False


def check_env() -> list[str]:
    required = ["PRICERUNNER_AFFILIATE_ID", "PRICERUNNER_PARTNER_ID"]
    return [k for k in required if not os.getenv(k)]


def load_site(path: str):
    import yaml
    from testflow.models import SiteConfig
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    return SiteConfig(**data)


def preflight(site_path: str | None) -> bool:
    ok = True
    if check_tool_server():
        print("checkmark Tool server healthy")
    else:
        print("x Tool server not running. Start with: ./scripts/start.sh")
        ok = False

    missing = check_env()
    if missing:
        print(f"x Missing env vars: {', '.join(missing)}")
        ok = False
    else:
        print("checkmark Required env vars set")

    if site_path:
        try:
            site = load_site(site_path)
            print(f"checkmark Site config loaded: {site.name} ({site.url})")
        except Exception as e:
            print(f"x Site config error: {e}")
            ok = False
    return ok


def dry_run(site_path: str, products: list[str] | None, topic: str | None) -> None:
    if not preflight(site_path):
        sys.exit(1)
    print("\nDry run: fetching products from tool server...")
    try:
        r = httpx.post(
            f"{TOOL_SERVER}/tools/fetch_products",
            json={"category_id": 1613, "limit": 5},  # default to robotstovsuger for demo
            timeout=20,
        )
        r.raise_for_status()
        products_found = r.json().get("products", [])
        print(f"checkmark Products fetched: {len(products_found)}")
        for p in products_found[:3]:
            print(f"  - {p['name']} | {p.get('price_display', 'N/A')} | {p['url']}")
    except Exception as e:
        print(f"x Product fetch failed: {e}")
    print("\nDry run complete. No article generated, no draft created.")


def generate_prompt(
    products: list[str] | None, topic: str | None, template: str | None, site: str
) -> str:
    if products:
        instruction = f"Write an article about: {', '.join(products)}"
        if template:
            instruction += f" (use template: {template})"
    elif topic:
        instruction = f"Write an article: {topic}"
        if template:
            instruction += f" (use template: {template})"
    else:
        instruction = "Help me create a new affiliate article."
    instruction += f"\nSite: {site}"
    return instruction


def discover_categories(query: str) -> None:
    try:
        r = httpx.post(f"{TOOL_SERVER}/tools/discover_categories", json={"query": query}, timeout=20)
        r.raise_for_status()
        cats = r.json().get("categories", [])
    except Exception as e:
        print(f"x Category discovery failed: {e}")
        print("  Make sure the tool server is running: ./scripts/start.sh")
        return
    if not cats:
        print(f"No categories found for '{query}'")
        return
    print(f"\nPriceRunner categories matching '{query}':")
    for c in cats[:10]:
        print(f"  {c['id']:>6}  {c['name']}  (parent: {c.get('parent', '')})")
    print("\nAdd the best match to sites/pricerunner-categories.yaml")


def main() -> None:
    from dotenv import load_dotenv
    load_dotenv()

    args = build_parser().parse_args()

    if args.discover:
        discover_categories(args.discover)
        return

    if args.check:
        ok = preflight(args.site)
        sys.exit(0 if ok else 1)

    if args.dry_run:
        if not args.site:
            print("--site is required for --dry-run")
            sys.exit(1)
        dry_run(args.site, args.products, args.topic)
        return

    if not args.site:
        print("--site is required")
        sys.exit(1)
    if not preflight(args.site):
        sys.exit(1)

    prompt = generate_prompt(args.products, args.topic, args.template, args.site)
    print("\n" + "-" * 60)
    print("Paste this into OpenClaw:")
    print("-" * 60)
    print(prompt)
    print("-" * 60)


if __name__ == "__main__":
    main()
