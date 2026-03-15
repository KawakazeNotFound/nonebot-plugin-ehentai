#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
import importlib.util
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType
from urllib.parse import urlparse

import httpx

ROOT_DIR = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = ROOT_DIR / "scripts"
TEMPLATE_PATH = SCRIPTS_DIR / "test.html"
DEFAULT_OUTPUT_PATH = ROOT_DIR / "aidetest" / "test.preview.html"
ITEM_BLOCK_RE = re.compile(r"<!-- \{\{#items\}\} -->(.*?)<!-- \{\{/items\}\} -->", re.S)
PLACEHOLDER_RE = re.compile(r"\{\{([a-zA-Z0-9_]+)\}\}")


def load_search_debug_module() -> ModuleType:
    module_path = SCRIPTS_DIR / "search_debug.py"
    spec = importlib.util.spec_from_file_location("search_debug", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("无法加载 search_debug.py")

    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def normalize_text(value: object) -> str:
    return " ".join(str(value or "").split()).strip()


def escape_text(value: object, fallback: str = "-") -> str:
    normalized = normalize_text(value)
    if not normalized:
        normalized = fallback
    return html.escape(normalized, quote=True)


def replace_placeholders(template: str, values: dict[str, object]) -> str:
    def repl(match: re.Match[str]) -> str:
        key = match.group(1)
        return escape_text(values.get(key, ""))

    return PLACEHOLDER_RE.sub(repl, template)


def fetch_results(search_debug: ModuleType, args: argparse.Namespace) -> dict[str, object]:
    base_url = search_debug.resolve_base_url(args.site, args.base_url)
    host = urlparse(base_url).netloc
    cookie = search_debug.merge_cookie(
        raw_cookie=args.cookie,
        ipb_member_id=args.ipb_member_id,
        ipb_pass_hash=args.ipb_pass_hash,
        igneous=args.igneous,
        cf_clearance=args.cf_clearance,
        host=host,
    )

    url = search_debug.build_search_url(base_url, args.keyword, args.f_cats, args.advsearch)
    headers = {
        "User-Agent": search_debug.DEFAULT_UA,
        "Accept": (
            "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,"
            "image/webp,image/apng,*/*;q=0.8"
        ),
        "Accept-Language": "en-US,en;q=0.9",
    }
    if cookie:
        headers["Cookie"] = cookie

    proxy = args.proxy or None
    with httpx.Client(
        timeout=args.timeout,
        follow_redirects=True,
        verify=not args.insecure,
        proxy=proxy,
        headers=headers,
    ) as client:
        resp = client.get(url)

    results = search_debug.parse_results(resp.text, base_url, max(1, args.limit))
    api_url = search_debug.resolve_metadata_api_url(base_url)
    search_debug.enrich_japanese_titles(
        results=results,
        api_url=api_url,
        timeout=args.timeout,
        proxy=proxy,
        verify=not args.insecure,
        cookie=cookie,
    )

    items: list[dict[str, object]] = []
    for index, item in enumerate(results, start=1):
        items.append(
            {
                "index": index,
                "gid": item.gid,
                "token": item.token,
                "title": item.title,
                "title_jpn": item.title_jpn or "无日文原文",
                "url": item.url,
                "category": item.category or "Unknown",
                "uploader": item.uploader or "Unknown",
                "posted": item.posted or "Unknown",
                "pages": item.pages,
                "rating": item.rating if item.rating >= 0 else 0,
                "cover_url": item.cover_url or "无封面链接",
                "tags": " / ".join(item.tags) if item.tags else "(no tags)",
            }
        )

    return {
        "schema_version": "test-preview-v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "keyword": args.keyword,
        "total_count": len(results),
        "display_count": len(items),
        "items": items,
    }


def render_template(template_text: str, payload: dict[str, object]) -> str:
    item_match = ITEM_BLOCK_RE.search(template_text)
    if item_match is None:
        raise RuntimeError("模板中未找到 items 重复块")

    item_block = item_match.group(1)
    rendered_items = "\n".join(
        replace_placeholders(item_block, item_values)
        for item_values in payload.get("items", [])
    )

    result = ITEM_BLOCK_RE.sub(rendered_items, template_text)
    top_level_values = {key: value for key, value in payload.items() if key != "items"}
    return replace_placeholders(result, top_level_values)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="将真实搜索结果渲染进 test.html 模板")
    parser.add_argument("keyword", nargs="?", default="Kawakaze", help="搜索关键词")
    parser.add_argument("--site", choices=["e", "ex", "custom"], default="e")
    parser.add_argument("--base-url", default="https://e-hentai.org")
    parser.add_argument("--limit", type=int, default=3)
    parser.add_argument("--timeout", type=int, default=20)
    parser.add_argument("--proxy", default="")
    parser.add_argument("--cookie", default="")
    parser.add_argument("--ipb-member-id", default="")
    parser.add_argument("--ipb-pass-hash", default="")
    parser.add_argument("--igneous", default="")
    parser.add_argument("--cf-clearance", default="")
    parser.add_argument("--f-cats", type=int, default=0)
    parser.add_argument("--advsearch", action="store_true")
    parser.add_argument("--insecure", action="store_true")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT_PATH))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    search_debug = load_search_debug_module()
    payload = fetch_results(search_debug, args)
    template_text = TEMPLATE_PATH.read_text(encoding="utf-8")
    rendered = render_template(template_text, payload)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(rendered, encoding="utf-8")

    print(f"Preview written to: {output_path}")
    print(f"Items rendered: {payload['display_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())