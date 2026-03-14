from __future__ import annotations

import asyncio
import base64
import hashlib
from math import ceil
from pathlib import Path
from uuid import uuid4

from nonebot import get_plugin_config, logger, on_command, get_driver
from nonebot.adapters.onebot.v11 import Bot, GroupMessageEvent, Message, MessageEvent, MessageSegment
from nonebot.adapters.onebot.v11.exception import ActionFailed
from nonebot.params import CommandArg
from nonebot.plugin import PluginMetadata

from .config import Config
from .service import EHentaiClient, SearchOptions
from .r2 import init_r2_manager, get_r2_manager

__plugin_meta__ = PluginMetadata(
    name="nonebot-plugin-ehentai",
    description="Search and download gallery zip from E-Hentai",
    usage="/search <name>\n/download <name>",
    config=Config,
    type="application",
    supported_adapters={"~onebot.v11"},
)

plugin_config = get_plugin_config(Config)

# 初始化 R2 管理器
driver = get_driver()

@driver.on_startup
async def _init_r2():
    """插件启动时初始化 R2 管理器"""
    await init_r2_manager(plugin_config)


def build_client() -> EHentaiClient:
    return EHentaiClient(
        site=plugin_config.ehentai_site,
        base_url=plugin_config.ehentai_base_url,
        cookie=plugin_config.ehentai_cookie,
        ipb_member_id=plugin_config.ehentai_ipb_member_id,
        ipb_pass_hash=plugin_config.ehentai_ipb_pass_hash,
        igneous=plugin_config.ehentai_igneous,
        cf_clearance=plugin_config.ehentai_cf_clearance,
        user_agent=plugin_config.ehentai_user_agent,
        timeout=plugin_config.ehentai_timeout,
        proxy=plugin_config.ehentai_proxy,
        backend=plugin_config.ehentai_http_backend,
        http3=plugin_config.ehentai_http3,
        desktop_site=plugin_config.ehentai_desktop_site,
        impersonate=plugin_config.ehentai_impersonate,
        enable_direct_ip=plugin_config.ehentai_enable_direct_ip,
        curl_cffi_skip_on_error=plugin_config.ehentai_curl_cffi_skip_on_error,
    )


def build_search_options() -> SearchOptions:
    return SearchOptions(
        f_cats=plugin_config.ehentai_search_f_cats,
        advsearch=plugin_config.ehentai_search_advsearch,
        f_sh=plugin_config.ehentai_search_f_sh,
        f_sto=plugin_config.ehentai_search_f_sto,
        f_sfl=plugin_config.ehentai_search_f_sfl,
        f_sfu=plugin_config.ehentai_search_f_sfu,
        f_sft=plugin_config.ehentai_search_f_sft,
        f_srdd=plugin_config.ehentai_search_f_srdd,
        f_spf=plugin_config.ehentai_search_f_spf,
        f_spt=plugin_config.ehentai_search_f_spt,
    )


async def send_message_with_retry(
    cmd, text: str, max_retries: int = 3, retry_delay: float = 1.0
) -> None:
    """
    发送消息并自动重试（处理 NapCat ActionFailed 错误）
    
    Args:
        cmd: 命令对象（需要有 finish 或 send 方法）
        text: 消息文本
        max_retries: 最大重试次数
        retry_delay: 重试延迟（秒）
    """
    # NapCat 单条消息限制约 4KB (~2000 汉字)，留 20% 安全余量
    max_single_msg_bytes = 3000
    
    # 如果消息过大，分段处理
    text_bytes = text.encode("utf-8")
    if len(text_bytes) > max_single_msg_bytes:
        lines = text.split("\n")
        current_chunk = ""
        chunk_list = []
        
        for line in lines:
            test_text = current_chunk + line + "\n"
            if len(test_text.encode("utf-8")) > max_single_msg_bytes and current_chunk:
                chunk_list.append(current_chunk.rstrip())
                current_chunk = line + "\n"
            else:
                current_chunk = test_text
        
        if current_chunk:
            chunk_list.append(current_chunk.rstrip())
        
        # 发送分段消息
        for chunk in chunk_list:
            for attempt in range(max_retries):
                try:
                    await cmd.send(chunk)
                    break
                except ActionFailed as e:
                    if attempt < max_retries - 1:
                        logger.warning(
                            f"发送消息失败 (第 {attempt + 1} 次尝试)，{retry_delay}秒后重试: {e.retcode} {e.message}"
                        )
                        await asyncio.sleep(retry_delay)
                    else:
                        raise RuntimeError(f"消息发送失败（已重试 {max_retries} 次）: {e.message}")
        
        # 最后发送 finish 标记
        await cmd.finish()
    else:
        # 消息正常，直接发送
        for attempt in range(max_retries):
            try:
                await cmd.finish(text)
                break
            except ActionFailed as e:
                if attempt < max_retries - 1:
                    logger.warning(
                        f"发送消息失败 (第 {attempt + 1} 次尝试)，{retry_delay}秒后重试: {e.retcode} {e.message}"
                    )
                    await asyncio.sleep(retry_delay)
                else:
                    logger.error(f"消息发送失败（已重试 {max_retries} 次）: {e.message}")
                    raise RuntimeError(f"消息发送失败: {e.message}")


search_cmd = on_command("search", priority=10, block=True)
download_cmd = on_command("download", priority=10, block=True)


@search_cmd.handle()
async def handle_search(args: Message = CommandArg()) -> None:
    keyword = args.extract_plain_text().strip()
    logger.info(f"[搜索处理] 开始处理搜索请求: keyword='{keyword}'")
    if not keyword:
        logger.warning(f"[搜索处理] 搜索无效")
        await search_cmd.finish("用法: /search [Name]")

    client = build_client()
    options = build_search_options()
    logger.info(f"[搜索处理] 创建 EHentai 客户端")
    logger.debug(f"[搜索处理] backend={client.backend}, enable_direct_ip={client.enable_direct_ip}")

    try:
        logger.info(f"[搜索处理] 下发搜索请求")
        results = await client.search(keyword, plugin_config.ehentai_max_results, options)
    except Exception as error:
        logger.error(f"[搜索处理] 搜索失败: {type(error).__name__}: {error}", exc_info=True)
        await search_cmd.finish(f"搜索失败: {error}")

    logger.info(f"[搜索处理] 搜索成功，找到 {len(results)} 个结果")

    if not results:
        await search_cmd.finish("没有找到结果，或当前 Cookie 权限不足。")

    # 只取第一个结果
    gallery = results[0]
    logger.info(f"[搜索处理] 返回第一个结果: {gallery.title}")

    # 构建消息：标题 + URL
    message_text = f"{gallery.title}\n{gallery.url}"

    # 如果有封面，构建带图片的消息
    if gallery.cover_url:
        logger.debug(f"[搜索处理] 封面 URL: {gallery.cover_url}")
        try:
            # 构建消息：图片 + 标题 + URL
            msg = Message()
            msg.append(MessageSegment.image(gallery.cover_url))
            msg.append(MessageSegment.text(f"\n{message_text}"))
            await search_cmd.finish(msg)
        except Exception as e:
            logger.warning(f"[搜索处理] 发送图片失败: {e}，降级为文本消息")
            await search_cmd.finish(message_text)
    else:
        # 没有封面，只发送文本
        await search_cmd.finish(message_text)


async def upload_to_group_file(bot: Bot, group_id: int, file_path: Path) -> None:
    logger.info(f"[上传] 开始上传群文件: group_id={group_id}, file={file_path.name}, size={file_path.stat().st_size / 1024 / 1024:.2f} MB")
    max_retries = 2
    for attempt in range(max_retries):
        try:
            await bot.call_api(
                "upload_group_file",
                group_id=group_id,
                file=str(file_path.resolve()),
                name=file_path.name,
            )
            logger.info(f"[上传] 群文件上传成功")
            return
        except Exception as error:
            if attempt < max_retries - 1:
                logger.warning(f"[上传] 群文件上传失败 (第 {attempt + 1} 次尝试): {type(error).__name__}, 1秒后重试...")
                await asyncio.sleep(1)
            else:
                logger.error(f"[上传] 群文件上传失败: {type(error).__name__}: {error}", exc_info=True)
                raise


def calculate_sha256(file_path: Path) -> str:
    hasher = hashlib.sha256()
    with file_path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


async def upload_file_stream(bot: Bot, file_path: Path) -> str:
    logger.info(f"[流上传] 开始流上传: file={file_path.name}, size={file_path.stat().st_size / 1024 / 1024:.2f} MB")
    chunk_size = max(64 * 1024, plugin_config.ehentai_stream_chunk_size)
    file_size = file_path.stat().st_size
    total_chunks = max(1, ceil(file_size / chunk_size))
    stream_id = str(uuid4())
    logger.debug(f"[流上传] stream_id={stream_id}, chunk_size={chunk_size}, total_chunks={total_chunks}")
    expected_sha256 = calculate_sha256(file_path)
    logger.debug(f"[流上传] 计算文件校验和: {expected_sha256[:16]}...")

    with file_path.open("rb") as file:
        chunk_index = 0
        while True:
            chunk = file.read(chunk_size)
            if not chunk:
                break
            logger.debug(f"[流上传] 上传数据块 {chunk_index + 1}/{total_chunks}")
            try:
                await bot.call_api(
                    "upload_file_stream",
                    stream_id=stream_id,
                    chunk_data=base64.b64encode(chunk).decode("utf-8"),
                    chunk_index=chunk_index,
                    total_chunks=total_chunks,
                    file_size=file_size,
                    expected_sha256=expected_sha256,
                    filename=file_path.name,
                    file_retention=plugin_config.ehentai_stream_file_retention_ms,
                )
            except Exception as error:
                logger.error(f"[流上传] 上传数据块失败: {type(error).__name__}: {error}")
                raise
            chunk_index += 1

    logger.info(f"[流上传] 所有数据块上传结束，发送完成信号")
    complete_resp = await bot.call_api(
        "upload_file_stream",
        stream_id=stream_id,
        is_complete=True,
    )
    logger.debug(f"[流上传] 完成响应: {complete_resp}")

    if isinstance(complete_resp, dict):
        stream_path = complete_resp.get("file_path")
        if isinstance(stream_path, str) and stream_path:
            logger.info(f"[流上传] 完成，获得文件路径: {stream_path}")
            return stream_path

    logger.error(f"[流上传] 完成但没有获得文件路径")
    raise RuntimeError("upload_file_stream completed but no file_path returned")


async def upload_to_group_file_with_fallback(
    bot: Bot, group_id: int, local_file_path: Path
) -> None:
    logger.info(f"[上传] 开始上传文件: group_id={group_id}, file={local_file_path.name}")
    if plugin_config.ehentai_stream_upload_first:
        logger.debug(f"[上传] 自配置优先使用流上传")
        try:
            logger.info(f"[上传] 正在执行流上传")
            napcat_file_path = await upload_file_stream(bot, local_file_path)
            logger.info(f"[上传] 流上传成功，今使用流路径上传群文件")
            try:
                await bot.call_api(
                    "upload_group_file",
                    group_id=group_id,
                    file=napcat_file_path,
                    name=local_file_path.name,
                )
                logger.info(f"[上传] 群文件上传成功")
                return
            except Exception as error:
                logger.error(f"[上传] 使用流路径上传群文件失败: {type(error).__name__}: {error}")
                raise
        except Exception as error:
            logger.warning(
                f"[上传] 流上传失败，今降级为使用本地路径的正常上传: {type(error).__name__}: {error}",
                exc_info=False,
            )

    logger.info(f"[上传] 使用本地路径上传")
    await upload_to_group_file(bot, group_id, local_file_path)


@download_cmd.handle()
async def handle_download(
    bot: Bot, event: MessageEvent, args: Message = CommandArg()
) -> None:
    raw_input = args.extract_plain_text().strip()
    
    # 解析 -original 标志
    use_original = "-original" in raw_input
    keyword = raw_input.replace("-original", "").strip()
    
    logger.info(f"[下载处理] 开始处理下载请求: keyword='{keyword}', use_original={use_original}")
    if not keyword:
        logger.warning(f"[下载处理] 下载无效")
        await download_cmd.finish("用法: /download [-original] [Name]")

    client = build_client()
    options = build_search_options()
    quality = "original" if use_original else "resample"
    await download_cmd.send(f"正在搜索并准备下载（{quality}版本），请稍候...")
    logger.info(f"[下载处理] 创建 EHentai 客户端，开始流程，质量={quality}")
    logger.debug(f"[下载处理] backend={client.backend}, enable_direct_ip={client.enable_direct_ip}")

    if not client.has_login_cookies():
        logger.error(f"[下载处理] 客户端没有登录 Cookie")
        await download_cmd.finish(
            "下载归档需要登录 Cookie。请在 .env 中至少配置 EHENTAI_IPB_MEMBER_ID 和 EHENTAI_IPB_PASS_HASH。"
        )

    if plugin_config.ehentai_site.lower() == "ex" and not client.has_ex_cookie():
        logger.error(f"[下载处理] ExHentai 需要 igneous Cookie")
        await download_cmd.finish(
            "当前站点为 exhentai，除 EHENTAI_IPB_MEMBER_ID / EHENTAI_IPB_PASS_HASH 外，通常还需要 EHENTAI_IGNEOUS。"
        )

    if not isinstance(event, GroupMessageEvent):
        logger.error(f"[下载处理] 不是群记事件")
        await download_cmd.finish("/download 仅支持群聊使用（需要上传群文件）。")

    try:
        logger.info(f"[下载处理] 下发搜索请求")
        results = await client.search(keyword, 1, options)
    except Exception as error:
        logger.error(f"[下载处理] 搜索失败: {type(error).__name__}: {error}", exc_info=True)
        await download_cmd.finish(f"搜索失败: {error}")

    if not results:
        logger.warning(f"[下载处理] 未找到可下载的内容")
        await download_cmd.finish("没有找到可下载的本子。")

    gallery = results[0]
    logger.info(f"[下载处理] 找到目标: gid={gallery.gid}, title={gallery.title[:50]}")

    try:
        logger.info(f"[下载处理] 解析存档下载链接")
        archive_url = await client.resolve_archive_url(gallery.url, prefer_original=use_original)
    except Exception as error:
        logger.error(f"[下载处理] 解析存档失败: {type(error).__name__}: {error}", exc_info=True)
        await download_cmd.finish(f"解析下载链接失败: {error}")

    if not archive_url:
        logger.warning(f"[下载处理] 未能获取存档下载链接")
        await download_cmd.finish(
            "未能获取压缩包下载链接，可能需要有效的 E-Hentai/ExHentai Cookie 权限。"
        )

    download_dir = Path(plugin_config.ehentai_download_dir)
    file_name = f"{gallery.gid}_{gallery.token}.zip"
    file_path = download_dir / file_name
    logger.info(f"[下载处理] 开始下载存档文件")
    logger.debug(f"[下载处理] 下载 URL: {archive_url}")
    logger.debug(f"[下载处理] 保存路径: {file_path}")

    try:
        logger.info(f"[下载处理] 下载文件")
        await client.download_file(archive_url, file_path)
        logger.info(f"[下载处理] 下载文件成功")
    except Exception as error:
        logger.error(f"[下载处理] 下载文件失败: {type(error).__name__}: {error}", exc_info=True)
        await download_cmd.finish(f"下载失败: {error}")

    try:
        logger.info(f"[下载处理] 开始上传群文件")
        await upload_to_group_file_with_fallback(bot, event.group_id, file_path)
        logger.info(f"[下载处理] 上传群文件成功")
    except Exception as error:
        logger.error(f"[下载处理] 上传群文件失败: {type(error).__name__}: {error}", exc_info=True)
        # 上传失败时，尝试 R2 备用方案
        file_size_mb = file_path.stat().st_size / 1024 / 1024
        r2_manager = get_r2_manager()
        
        if r2_manager and r2_manager.is_available:
            logger.info(f"[下载处理] 群文件上传失败，尝试 R2 备用上传...")
            try:
                r2_url = await r2_manager.upload_file(str(file_path), file_path.name)
                if r2_url:
                    logger.info(f"[下载处理] R2 上传成功: {r2_url}")
                    # 获取统计信息
                    stats = await r2_manager.get_upload_stats()
                    msg = (
                        f"✓ 下载完成！\n"
                        f"群文件上传失败，已备用上传到 R2 CDN\n\n"
                        f"下载链接：\n{r2_url}\n\n"
                        f"链接有效期: {r2_manager.retention_hours} 小时\n"
                        f"R2 用量: {stats.get('total_size_mb', 0):.1f}/{stats.get('max_size_mb', 0):.0f} MB "
                        f"({stats.get('usage_percent', 0):.1f}%)"
                    )
                    await download_cmd.finish(msg)
                    return
                else:
                    logger.error(f"[下载处理] R2 上传失败")
            except Exception as r2_error:
                logger.error(f"[下载处理] R2 上传异常: {type(r2_error).__name__}: {r2_error}", exc_info=True)
        
        # R2 也不可用，返回文件信息
        try:
            msg = (
                f"✓ 下载完成！\n"
                f"但群文件上传超时/失败（{type(error).__name__}）\n\n"
                f"文件信息：\n"
                f"- 文件名: {file_path.name}\n"
                f"- 大小: {file_size_mb:.2f} MB\n"
                f"- 路径: {file_path}\n\n"
                f"请稍候 30 秒后手动下载，或联系管理员。"
            )
            await download_cmd.finish(msg)
        except ActionFailed:
            logger.error(f"[下载处理] 无法通知用户")
            pass
        return

    # 最后的完成消息（紧凑格式）
    title_short = gallery.title[:30] + "..." if len(gallery.title) > 30 else gallery.title
    logger.info(f"[下载处理] 整个汇总程序完成: {title_short}")
    try:
        await download_cmd.finish(f"✓ 完成: {title_short}")
    except ActionFailed:
        logger.warning(f"[下载处理] 无法发送完成消息")