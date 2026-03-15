from __future__ import annotations

from collections.abc import Sequence
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
        lines.append(f"{index}. {gallery.title}")
        lines.append(gallery.url)

        extra: list[str] = []
        if gallery.category:
            extra.append(f"分类: {gallery.category}")
        if gallery.pages > 0:
            extra.append(f"页数: {gallery.pages}")
        if gallery.uploader:
            extra.append(f"上传者: {gallery.uploader}")

        if extra:
            lines.append(" | ".join(extra))

        lines.append("")

    return "\n".join(lines).strip()