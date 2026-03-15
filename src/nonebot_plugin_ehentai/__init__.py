from __future__ import annotations

import asyncio
import base64
import hashlib
from math import ceil
from pathlib import Path
from uuid import uuid4

from nonebot import get_plugin_config, logger, on_command, get_driver, require
from nonebot.adapters.onebot.v11 import (
    Bot, 
    GroupMessageEvent, 
    Message, 
    MessageEvent, 
    MessageSegment, 
    ActionFailed
)
from nonebot.exception import FinishedException
from nonebot.params import CommandArg
from nonebot.plugin import PluginMetadata

# 引入定时任务支持
try:
    require("nonebot_plugin_apscheduler")
    from nonebot_plugin_apscheduler import scheduler
    HAS_SCHEDULER = True
except Exception:
    HAS_SCHEDULER = False
    logger.warning("[定时清理] 未发现 nonebot_plugin_apscheduler，自动清理功能将不可用")

from .config import Config
from .service import EHentaiClient, SearchOptions
from .search_logic import (
    SearchExecutionError,
    execute_gallery_search,
    format_search_results_message,
    pick_first_result,
)
from .r2 import init_r2_manager, get_r2_manager
from .d1 import init_d1_manager, get_d1_manager

__plugin_meta__ = PluginMetadata(
    name="nonebot-plugin-ehentai",
    description="Search and download gallery zip from E-Hentai",
    usage="/search <name>\n/download <name>",
    config=Config,
    type="application",
    supported_adapters={"~onebot.v11"},
)

plugin_config = get_plugin_config(Config)

# 初始化 R2 和 D1 管理器
driver = get_driver()

@driver.on_startup
async def _init_managers():
    """插件启动时初始化外部管理器"""
    await init_r2_manager(plugin_config)
    await init_d1_manager(plugin_config)


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
        min_cache_file_size_kb=plugin_config.ehentai_min_cache_file_size_kb,
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


def safe_exception_text(error: Exception) -> str:
    """安全地将异常转换为字符串，防止 JSON-like 错误信息导致的 KeyError
    
    特别处理 NoneBot ActionFailed，避免其 message 属性含 JSON 导致的问题
    """
    # 特殊处理 ActionFailed（NoneBot OneBot 适配器）
    if type(error).__name__ == "ActionFailed":
        try:
            # ActionFailed 的关键字段：status, retcode, message
            attrs = []
            for attr in ["status", "retcode", "wording"]:
                val = getattr(error, attr, None)
                if val is not None:
                    attrs.append(f"{attr}={val!r}")
            if attrs:
                return f"ActionFailed({', '.join(attrs)})"
        except Exception:
            pass  # 如果上述方式也失败，fallback 到通用方式
    
    # 通用方式：尝试 str()
    try:
        text = str(error)
        return text
    except Exception as e:
        # 第二层：尝试 repr()
        try:
            text = repr(error)
            return text
        except Exception:
            # 最后的兜底：只返回异常类型名称
            return f"{type(error).__name__}(unprintable)"


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
        results = await execute_gallery_search(
            client,
            keyword,
            plugin_config.ehentai_max_results,
            options,
        )
    except SearchExecutionError as error:
        await search_cmd.finish(f"搜索失败: {error}")

    logger.info(f"[搜索处理] 搜索成功，找到 {len(results)} 个结果")

    if not results:
        await search_cmd.finish("没有找到结果，或当前 Cookie 权限不足。")

    message_text = format_search_results_message(keyword, results)
    await send_message_with_retry(search_cmd, message_text)


def calculate_sha256(file_path: Path) -> str:
    hasher = hashlib.sha256()
    with file_path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


async def upload_file_stream(bot: Bot, file_path: Path) -> str:
    logger.info(
        f"[流上传] 开始传输文件到 NapCat: {file_path.name} ({file_path.stat().st_size / 1024 / 1024:.2f} MB)"
    )
    chunk_size = max(64 * 1024, plugin_config.ehentai_stream_chunk_size)
    file_size = file_path.stat().st_size
    total_chunks = max(1, ceil(file_size / chunk_size))
    stream_id = str(uuid4())
    expected_sha256 = calculate_sha256(file_path)

    last_resp = None
    with file_path.open("rb") as file:
        for i in range(total_chunks):
            chunk = file.read(chunk_size)
            is_last = (i == total_chunks - 1)
            
            try:
                # 根据 2.md 规范：在最后一个分块中发送 is_complete=True
                # 必填参数：stream_id, file_retention
                last_resp = await bot.call_api(
                    "upload_file_stream",
                    stream_id=stream_id,
                    chunk_data=base64.b64encode(chunk).decode("utf-8"),
                    chunk_index=i,
                    total_chunks=total_chunks,
                    file_size=file_size,
                    expected_sha256=expected_sha256,
                    filename=file_path.name,
                    file_retention=plugin_config.ehentai_stream_file_retention_ms,
                    is_complete=is_last,
                )
            except Exception as error:
                logger.error(f"[流上传] 数据块 {i} 发送失败: {safe_exception_text(error)}")
                raise

    # 尝试从最后一次响应中获取文件路径
    if last_resp:
        # 情况 1: data 是字典，包含 file_path (NapCat 特色)
        if isinstance(last_resp, dict):
            if path := last_resp.get("file_path"):
                logger.info(f"[流上传] 成功，获得路径: {path}")
                return str(path)
        # 情况 2: data 直接是字符串路径 (对齐 BaseResponse 规范)
        if isinstance(last_resp, str) and (last_resp.startswith("/") or "temp" in last_resp):
            logger.info(f"[流上传] 成功，获得路径字符串: {last_resp}")
            return last_resp

    logger.error(f"[流上传] 失败，未获得返回路径。响应数据: {last_resp}")
    raise RuntimeError("流上传完成但未获得有效的返回路径")


async def upload_to_group_file_with_fallback(
    bot: Bot, group_id: int, local_file_path: Path
) -> None:
    """上传文件到群文件

    策略：
    1. 优先使用流式上传（Stream Upload），这是最稳定的方案，不依赖磁盘路径权限。
    2. 如果流式上传失败，作为最后的保底尝试本地直传。
    """
    file_name = local_file_path.name
    
    # 强制优先流式上传（鉴于目前路径直传在用户环境下频发权限/内核错误）
    # 如果用户显式关闭了流上传，我们才考虑本地优先
    use_stream_first = getattr(plugin_config, "ehentai_use_napcat_stream_upload", True)

    async def _do_upload(path_or_url: str, mode_label: str) -> bool:
        """执行具体的 upload_group_file 调用"""
        max_retries = 3
        # 更加激进的退避时间，针对 NTQQ 的内核同步问题
        retry_delays = [5, 12, 25]
        
        for attempt in range(max_retries + 1):
            try:
                # 严格遵循 NapCat OpenAPI 规范 (1.md)
                # 必填参数：group_id (str), file (str), name (str), upload_file (bool)
                await bot.call_api(
                    "upload_group_file",
                    group_id=str(group_id),
                    file=path_or_url,
                    name=file_name,
                    upload_file=True,
                )
                logger.info(f"[上传] {mode_label} 成功")
                return True
            except Exception as e:
                err_text = safe_exception_text(e)
                
                # 如果是明确的权限错误，且不是最后一次尝试，直接认为该模式失效
                if any(x in err_text.lower() for x in ["not found", "permission denied", "access denied"]):
                    logger.warning(f"[上传] {mode_label} 路径不可访问: {err_text}")
                    return False

                if attempt < max_retries:
                    wait = retry_delays[attempt]
                    logger.warning(
                        f"[上传] {mode_label} 失败（第 {attempt + 1} 次），将在 {wait}s 后重试: {err_text}"
                    )
                    await asyncio.sleep(wait)
                else:
                    logger.error(f"[上传] {mode_label} 最终失败: {err_text}")
                    return False
        return False

    # 定义两种尝试方式
    async def try_stream_way() -> bool:
        try:
            logger.info(f"[上传] 正在通过流式接口将文件传输至 NapCat...")
            temp_path = await upload_file_stream(bot, local_file_path)
            # 【关键】流传输完成后，给 NapCat 和 NTQQ 充足的时间处理文件锁和磁盘落盘
            logger.info(f"[上传] 流传输完成，预留 2s 缓冲时间等待内核同步...")
            await asyncio.sleep(2.5)
            return await _do_upload(temp_path, "流式上传")
        except Exception as e:
            logger.warning(f"[上传] 流式传输环节失败: {safe_exception_text(e)}")
            return False

    async def try_local_way() -> bool:
        # 转换为 Linux 风格的绝对路径
        abs_path = str(local_file_path.resolve()).replace("\\", "/")
        if not abs_path.startswith("/"):
            abs_path = "/" + abs_path
        
        # 鉴于 file:/// 可能导致部分版本解析失败，我们尝试纯路径和协议路径
        file_uri = f"file://{abs_path}"
        logger.info(f"[上传] 尝试本地路径直传...")
        await asyncio.sleep(1) # IO 缓冲
        return await _do_upload(file_uri, "本地直传")

    # 执行逻辑：优先流式 -> 其次本地
    if use_stream_first:
        if await try_stream_way():
            return
        logger.info("[上传] 流式上传失败，尝试最后的本地直传保底...")
        if await try_local_way():
            return
    else:
        if await try_local_way():
            return
        logger.info("[上传] 本地直传失败，尝试流式上传补偿...")
        if await try_stream_way():
            return

    raise RuntimeError("所有群文件上传方案（流式+本地）均已失败，请检查 NapCat 日志或 R2 配置")



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
        results = await execute_gallery_search(client, keyword, 1, options)
    except SearchExecutionError as error:
        await download_cmd.finish(f"搜索失败: {error}")

    if not results:
        logger.warning(f"[下载处理] 未找到可下载的内容")
        await download_cmd.finish("没有找到可下载的本子。")

    gallery = pick_first_result(results)
    if gallery is None:
        logger.warning(f"[下载处理] 搜索返回空结果")
        await download_cmd.finish("没有找到可下载的本子。")
    logger.info(f"[下载处理] 找到目标: gid={gallery.gid}, title={gallery.title[:50]}")

    try:
        logger.info(f"[下载处理] 解析存档下载链接")
        archive_url = await client.resolve_archive_url(gallery.url, prefer_original=use_original)
    except Exception as error:
        err_text = safe_exception_text(error)
        logger.error(f"[下载处理] 解析存档失败: {type(error).__name__}: {err_text}", exc_info=False)
        await download_cmd.finish(f"解析下载链接失败: {err_text}")

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
        err_text = safe_exception_text(error)
        logger.error(f"[下载处理] 下载文件失败: {type(error).__name__}: {err_text}", exc_info=False)
        await download_cmd.finish(f"下载失败: {err_text}")

    # 决策：是否尝试上传到群文件
    should_try_group_file = plugin_config.ehentai_upload_to_group_file
    
    # 如果配置了"优先 R2"且 R2 可用，跳过群文件上传
    if should_try_group_file and plugin_config.ehentai_prefer_r2_over_group_file:
        r2_manager = get_r2_manager()
        if r2_manager and r2_manager.is_available:
            logger.info(f"[下载处理] 配置优先用 R2，跳过群文件上传")
            should_try_group_file = False
    
    if should_try_group_file:
        try:
            logger.info(f"[下载处理] 开始上传群文件")
            await upload_to_group_file_with_fallback(bot, event.group_id, file_path)
            logger.info(f"[下载处理] 上传群文件成功")
            # 群文件上传成功，完成
            title_short = gallery.title[:30] + "..." if len(gallery.title) > 30 else gallery.title
            logger.info(f"[下载处理] 整个下载上传流程完成: {title_short}")
            try:
                await download_cmd.finish(f"✓ 完成: {title_short}")
            except ActionFailed:
                logger.error(f"[下载处理] 无法通知用户完成")
                pass
            return
        except Exception as error:
            err_text = safe_exception_text(error)
            logger.error(
                f"[下载处理] 上传群文件失败: {type(error).__name__}: {err_text}",
                exc_info=False,
            )
            logger.info(f"[下载处理] 群文件上传失败，尝试 R2 备用方案")
    else:
        logger.info(f"[下载处理] 配置未启用群文件上传，直接尝试 R2")
    
    # R2 备用方案
    file_size_mb = file_path.stat().st_size / 1024 / 1024
    r2_manager = get_r2_manager()
    
    if r2_manager and r2_manager.is_available:
        logger.info(f"[下载处理] 尝试 R2 备用上传...")
        try:
            r2_url = await r2_manager.upload_file(str(file_path), file_path.name)
            if r2_url:
                logger.info(f"[下载处理] R2 上传成功: {r2_url}")
                
                # 获取统计信息并记录 D1
                stats = await r2_manager.get_upload_stats()
                d1_manager = get_d1_manager()
                if d1_manager:
                    await d1_manager.record_download(
                        gid=str(gallery.gid),
                        title=gallery.title,
                        size_mb=file_size_mb,
                        user_id=str(event.user_id),
                        r2_url=r2_url,
                        retention_hours=r2_manager.retention_hours
                    )
                    # 顺便清理一下 D1 的过期记录
                    await d1_manager.cleanup_expired_metadata()

                # 标题安全清洗
                safe_title = gallery.title.encode("utf-8", errors="ignore").decode("utf-8")
                
                # 1. 准备封面 (下载到本地)
                cover_segment = None
                if gallery.cover_url:
                    cover_path = download_dir / "covers" / f"{gallery.gid}_cover.jpg"
                    cover_path.parent.mkdir(parents=True, exist_ok=True)
                    try:
                        await client.download_file(gallery.cover_url, cover_path)
                        cover_segment = MessageSegment.image(cover_path)
                    except Exception as e:
                        logger.warning(f"[下载处理] 封面处理失败: {safe_exception_text(e)}")

                # 2. 准备文本
                text_info = (
                    f"你请求的资源：\n{safe_title}\n\n"
                    f"下载链接：\n{r2_url}\n\n"
                    f"链接有效期：{r2_manager.retention_hours} 小时\n"
                    f"R2 用量：{stats.get('total_size_mb', 0):.1f}/{stats.get('max_size_mb', 0):.0f} MB "
                    f"({stats.get('usage_percent', 0):.1f}%)"
                )

                # 3. 根据配置发送消息
                msg_type = plugin_config.ehentai_download_message_type
                
                if msg_type == "forward":
                    # 合并转发模式
                    nodes = []
                    # 节点 1: 封面
                    if cover_segment:
                        nodes.append({"type": "node", "data": {"name": "EhBot", "uin": bot.self_id, "content": Message(cover_segment)}})
                    # 节点 2: 下载信息
                    nodes.append({"type": "node", "data": {"name": "EhBot", "uin": bot.self_id, "content": Message(text_info)}})
                    
                    try:
                        await bot.call_api("send_group_forward_msg", group_id=event.group_id, messages=nodes)
                        await download_cmd.finish()
                    except ActionFailed as e:
                        logger.warning(f"[下载处理] 转发消息失败: {e}，降级为单气泡发送")
                        msg_type = "single_bubble"

                if msg_type == "single_bubble":
                    # 单气泡图文模式
                    final_msg = Message()
                    if cover_segment:
                        final_msg.append(cover_segment)
                    final_msg.append(MessageSegment.text("\n" + text_info))
                    await download_cmd.finish(final_msg)
                
                return
            else:
                logger.error(f"[下载处理] R2 上传失败")
        except Exception as r2_error:
            if isinstance(r2_error, FinishedException):
                raise r2_error
            logger.error(
                f"[下载处理] R2 上传异常: {type(r2_error).__name__}: {safe_exception_text(r2_error)}",
                exc_info=False,
            )
    else:
        logger.warning(f"[下载处理] R2 不可用")
    
    # R2 也不可用，返回文件信息
    try:
        msg = (
            f"✓ 下载完成！\n"
            f"但上传失败（群文件/R2 均不可用）\n\n"
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


# --- 定时清理任务 ---
async def cleanup_task():
    """执行本地缓存和云端元数据的每日清理"""
    logger.info("[定时清理] 开始执行每日例行清理任务...")
    
    # 1. 清理本地缓存
    download_dir = Path(plugin_config.ehentai_download_dir)
    count = 0
    # 清理 ZIP
    for zip_file in download_dir.glob("*.zip"):
        try:
            zip_file.unlink()
            count += 1
        except Exception: pass
    # 清理封面
    for cover in (download_dir / "covers").glob("*.jpg"):
        try:
            cover.unlink()
            count += 1
        except Exception: pass
    logger.info(f"[定时清理] 已删除 {count} 个本地缓存文件")

    # 2. 清理 D1 过期元数据
    d1_manager = get_d1_manager()
    if d1_manager:
        await d1_manager.cleanup_expired_metadata()
        logger.info("[定时清理] 已同步清理 D1 过期元数据")

    # 3. R2 的物理清理已由 R2Manager 在上传新文件时自动处理

if HAS_SCHEDULER and plugin_config.ehentai_auto_cleanup_local:
    try:
        hour, minute = plugin_config.ehentai_auto_cleanup_time.split(":")
        scheduler.add_job(
            cleanup_task, 
            "cron", 
            hour=int(hour), 
            minute=int(minute), 
            id="ehentai_cleanup"
        )
        logger.info(f"[定时清理] 任务已注册，每天 {plugin_config.ehentai_auto_cleanup_time} 运行")
    except Exception as e:
        logger.error(f"[定时清理] 任务注册失败: {e}")