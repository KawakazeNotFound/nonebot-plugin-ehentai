from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timezone
from typing import Optional

from nonebot import logger

from .service import EHentaiClient, GalleryResult, SearchOptions


class SearchExecutionError(RuntimeError):
    """Raised when search request fails."""


def _safe_error_text(error: Exception) -> str:
    try:
        return str(error)
    except Exception:
        return repr(error)


async def execute_gallery_search(
    client: EHentaiClient,
    keyword: str,
    limit: int,
    options: Optional[SearchOptions] = None,
) -> list[GalleryResult]:
    logger.info(f"[搜索流程] 发起搜索: keyword='{keyword}', limit={limit}")
    try:
        results = await client.search(keyword, limit, options)
    except Exception as error:
        err_text = _safe_error_text(error)
        logger.error(
            f"[搜索流程] 搜索失败: {type(error).__name__}: {err_text}",
            exc_info=False,
        )
        raise SearchExecutionError(err_text) from error

    logger.info(f"[搜索流程] 搜索成功，结果数: {len(results)}")
    return results


def pick_first_result(results: Sequence[GalleryResult]) -> Optional[GalleryResult]:
    if not results:
        return None
    return results[0]


def _normalize_text(value: str) -> str:
    return " ".join((value or "").split()).strip()


def build_search_render_payload(
    keyword: str,
    results: Sequence[GalleryResult],
    display_limit: Optional[int] = None,
) -> dict[str, object]:
    """构造给图片渲染脚本的规范化数据。

    约束：
    1. 字段名和类型稳定，便于脚本直接消费。
    2. 文本统一做空白折叠，避免换行或多空格影响排版。
    3. 所有可选字段回退为空字符串/默认值，避免 None 判断。
    """
    if display_limit is None or display_limit <= 0:
        display_count = len(results)
    else:
        display_count = min(display_limit, len(results))

    items: list[dict[str, object]] = []
    for index, gallery in enumerate(results[:display_count], start=1):
        rating = gallery.rating if gallery.rating >= 0 else 0.0
        item = {
            "index": index,
            "gid": str(gallery.gid),
            "token": str(gallery.token),
            "title": _normalize_text(gallery.title),
            "title_jpn": _normalize_text(gallery.title_jpn),
            "has_japanese_title": 1 if gallery.has_japanese_title else 0,
            "url": _normalize_text(gallery.url),
            "cover_url": _normalize_text(gallery.cover_url),
            "category": _normalize_text(gallery.category),
            "uploader": _normalize_text(gallery.uploader),
            "posted": _normalize_text(gallery.posted),
            "pages": int(gallery.pages or 0),
            "rating": float(rating),
            "is_disowned": 1 if gallery.disowned else 0,
            "favorited": int(gallery.favorited),
            "tags": [_normalize_text(tag) for tag in (gallery.tags or []) if _normalize_text(tag)],
        }
        items.append(item)

    return {
        "schema_version": "search-render-v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "keyword": _normalize_text(keyword),
        "total_count": len(results),
        "display_count": display_count,
        "items": items,
    }


def format_search_results_message(
    keyword: str,
    results: Sequence[GalleryResult],
    display_limit: Optional[int] = None,
) -> str:
    if not results:
        return "没有找到结果，或当前 Cookie 权限不足。"

    if display_limit is None or display_limit <= 0:
        display_count = len(results)
    else:
        display_count = min(display_limit, len(results))

    lines: list[str] = [
        f"关键词: {keyword}",
        f"共找到 {len(results)} 条结果，展示前 {display_count} 条:",
        "",
    ]

    for index, gallery in enumerate(results[:display_count], start=1):
        lines.append(f"{index}. {_normalize_text(gallery.title)}")
        if gallery.title_jpn:
            lines.append(f"日文原文: {_normalize_text(gallery.title_jpn)}")
        lines.append(f"日文原文标记: {gallery.has_japanese_title}")
        lines.append(_normalize_text(gallery.url))

        extra: list[str] = []
        if gallery.category:
            extra.append(f"分类: {_normalize_text(gallery.category)}")
        if gallery.pages > 0:
            extra.append(f"页数: {gallery.pages}")
        if gallery.uploader:
            extra.append(f"上传者: {_normalize_text(gallery.uploader)}")

        if extra:
            lines.append(" | ".join(extra))

        lines.append("")

    return "\n".join(lines).strip()