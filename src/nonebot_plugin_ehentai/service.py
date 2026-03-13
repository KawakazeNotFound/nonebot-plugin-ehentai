from __future__ import annotations

import asyncio
import re
import ssl
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from urllib.parse import urlencode

import httpx
from bs4 import BeautifulSoup
from nonebot import logger

from .network import EhHttpRouter, BUILT_IN_HOSTS

try:
    from curl_cffi import requests as curl_requests
    from curl_cffi.const import CurlHttpVersion
except ImportError:
    curl_requests = None
    CurlHttpVersion = None


GALLERY_URL_RE = re.compile(
    r"https?://(?:exhentai\.org|e-hentai\.org(?:/lofi)?)/(?:g|mpv)/(\d+)/([0-9a-f]{10})"
)
INSUFFICIENT_FUNDS_MSG = "You do not have enough funds to download this archive."
NEED_HATH_CLIENT_MSG = "You must have a H@H client assigned to your account to use this feature."
CHROME_DESKTOP_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
CHROME_ACCEPT = (
    "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,"
    "image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7"
)
CHROME_ACCEPT_LANGUAGE = "en-US,en;q=0.9"


@dataclass
class GalleryResult:
    title: str
    url: str
    gid: str
    token: str


@dataclass
class ArchiveOption:
    res: str
    name: str
    size: str
    cost: str
    is_hath: bool


@dataclass
class SearchOptions:
    f_cats: int = 0
    advsearch: bool = False
    f_sh: bool = False
    f_sto: bool = False
    f_sfl: bool = False
    f_sfu: bool = False
    f_sft: bool = False
    f_srdd: int = 0
    f_spf: int = 0
    f_spt: int = 0


class EHentaiClient:
    def __init__(
        self,
        site: str,
        base_url: str,
        cookie: str,
        ipb_member_id: str,
        ipb_pass_hash: str,
        igneous: str,
        cf_clearance: str,
        user_agent: str,
        timeout: int,
        proxy: str = "",
        backend: str = "httpx",
        http3: bool = False,
        desktop_site: bool = False,
        impersonate: str = "chrome124",
        enable_direct_ip: bool = True,
    ) -> None:
        self.site = site.lower()
        self.base_url = self._resolve_base_url(site, base_url)
        effective_user_agent = CHROME_DESKTOP_USER_AGENT if desktop_site else user_agent
        self.headers = {
            "User-Agent": effective_user_agent,
            "Accept": CHROME_ACCEPT,
            "Accept-Language": CHROME_ACCEPT_LANGUAGE,
        }
        self.raw_cookie = cookie.strip()
        self.ipb_member_id = ipb_member_id.strip()
        self.ipb_pass_hash = ipb_pass_hash.strip()
        self.igneous = igneous.strip()
        self.cf_clearance = cf_clearance.strip()
        self.timeout = timeout
        self.proxy = proxy
        self.backend = backend.lower()
        self.http3 = http3
        self.desktop_site = desktop_site
        self.impersonate = impersonate
        self.enable_direct_ip = enable_direct_ip

    @staticmethod
    def _resolve_base_url(site: str, base_url: str) -> str:
        normalized_site = site.lower()
        if normalized_site == "ex":
            return "https://exhentai.org"
        if normalized_site == "e":
            return "https://e-hentai.org"
        return base_url.rstrip("/")

    def has_identity_cookies(self) -> bool:
        return bool(self.ipb_member_id and self.ipb_pass_hash)

    def has_login_cookies(self) -> bool:
        return bool(self.raw_cookie or self.has_identity_cookies())

    def has_ex_cookie(self) -> bool:
        return bool(self.raw_cookie or (self.has_identity_cookies() and self.igneous))

    def _cookie_pairs_for_url(self, url: str) -> list[tuple[str, str]]:
        host = url.lower()
        cookie_pairs: list[tuple[str, str]] = []

        if self.raw_cookie:
            return []

        if self.ipb_member_id:
            cookie_pairs.append(("ipb_member_id", self.ipb_member_id))
        if self.ipb_pass_hash:
            cookie_pairs.append(("ipb_pass_hash", self.ipb_pass_hash))
        if self.cf_clearance:
            cookie_pairs.append(("cf_clearance", self.cf_clearance))
        if "e-hentai.org" in host:
            cookie_pairs.append(("nw", "1"))
        if "exhentai.org" in host and self.igneous:
            cookie_pairs.append(("igneous", self.igneous))

        return cookie_pairs

    def _build_cookie_header(self, url: str) -> str:
        if self.raw_cookie:
            return self.raw_cookie
        cookie_pairs = self._cookie_pairs_for_url(url)
        return "; ".join(f"{key}={value}" for key, value in cookie_pairs if value)

    def _headers_for_url(self, url: str) -> dict[str, str]:
        headers = dict(self.headers)
        cookie_header = self._build_cookie_header(url)
        if cookie_header:
            headers["Cookie"] = cookie_header

        # 对于直连 IP，注入原始 Host 头以通过 Cloudflare 验证
        if self.enable_direct_ip:
            from urllib.parse import urlparse
            parsed = urlparse(url)
            hostname = parsed.hostname
            if hostname and hostname in BUILT_IN_HOSTS:
                port = parsed.port
                if port and port not in (80, 443):
                    headers["Host"] = f"{hostname}:{port}"
                else:
                    headers["Host"] = hostname

        return headers

    def _client(self) -> httpx.AsyncClient:
        # 使用直连 IP 的 httpx 客户端（EhViewer_CN_SXJ 方案）
        if self.enable_direct_ip:
            kwargs: dict = {
                "timeout": self.timeout,
                "verify": False,
                "follow_redirects": True,
            }
            if self.proxy:
                kwargs["proxy"] = self.proxy

            # 构建内置 IP 直连规则
            mounts = {}
            for hostname, ips in BUILT_IN_HOSTS.items():
                if ips:
                    ip = ips[0]
                    # 为每个主机名创建直连规则
                    for scheme in ["http", "https"]:
                        mount_key = f"{scheme}://{hostname}"
                        mounts[mount_key] = httpx.AsyncHTTPTransport(verify=False)

            if mounts:
                kwargs["mounts"] = mounts

            kwargs["headers"] = self.headers.copy()
            if self.raw_cookie or self.has_identity_cookies():
                # 添加 HTTP2 支持用于 IP 直连
                pass

            client = httpx.AsyncClient(**kwargs)
            return client

        # 降级到默认 httpx 客户端（禁用直连 IP）
        kwargs: dict = {
            "timeout": self.timeout,
            "follow_redirects": True,
        }
        if self.proxy:
            kwargs["proxy"] = self.proxy
        return httpx.AsyncClient(**kwargs)

    def _curl_request_kwargs(self) -> dict:
        return self._curl_request_kwargs_with_http3(self.http3)

    def _curl_request_kwargs_with_http3(self, http3: bool) -> dict:
        kwargs: dict = {
            "timeout": self.timeout,
            "allow_redirects": True,
            "impersonate": self.impersonate,
        }
        if self.proxy:
            kwargs["proxies"] = {"http": self.proxy, "https": self.proxy}
        if http3 and CurlHttpVersion is not None:
            kwargs["http_version"] = CurlHttpVersion.V3
        return kwargs

    def _curl_session(self, http3: Optional[bool] = None):
        if curl_requests is None:
            raise RuntimeError("未安装 curl_cffi，无法使用浏览器仿真后端")
        if http3 is None:
            return curl_requests.Session(**self._curl_request_kwargs())
        return curl_requests.Session(**self._curl_request_kwargs_with_http3(http3))

    @staticmethod
    def _is_quic_tls_error(error: Exception) -> bool:
        return "quic needs at least tls version 1.3" in str(error).lower()

    @staticmethod
    def _should_fallback_to_httpx(error: Exception) -> bool:
        message = str(error).lower()
        if "connection reset by peer" in message:
            return True
        if "curl: (35)" in message:
            return True
        if "ssl" in message and "curl:" in message:
            return True
        return False

    @staticmethod
    def _is_login_required_page(body: str) -> bool:
        lowered = body.lower()
        return "this page requires you to log on." in lowered or "e-hentai.org login" in lowered

    @staticmethod
    def _raise_for_response(resp) -> None:
        if getattr(resp, "status_code", None) == 451:
            raise RuntimeError(
                "当前网络环境访问 E-Hentai 被 451 拦截。请配置 EHENTAI_PROXY，或在可访问该站点的网络环境下运行。"
            )
        resp.raise_for_status()

    def _normalize_gallery_url(self, href: str) -> str:
        if href.startswith("http://") or href.startswith("https://"):
            return href
        return f"{self.base_url}{href if href.startswith('/') else '/' + href}"

    def _get_request_url_for_direct_ip(self, original_url: str) -> str:
        """
        对于直连 IP 模式，将 URL 中的主机名转换为预设的 IP 地址

        例：
        - https://e-hentai.org/path → https://104.20.18.168/path
        - https://exhentai.org/path → https://178.175.128.251/path
        """
        if not self.enable_direct_ip:
            return original_url

        from urllib.parse import urlparse, urlunparse

        parsed = urlparse(original_url)
        hostname = parsed.hostname

        # 检查是否是已知的 e-hentai 相关主机
        if hostname and hostname in BUILT_IN_HOSTS:
            ips = BUILT_IN_HOSTS.get(hostname, [])
            if ips:
                # 强制使用 HTTPS 和 IP 地址
                new_netloc = ips[0]
                if parsed.port and parsed.port not in (80, 443):
                    new_netloc = f"{ips[0]}:{parsed.port}"

                new_parsed = (
                    "https",  # 总是使用 HTTPS
                    new_netloc,
                    parsed.path,
                    parsed.params,
                    parsed.query,
                    parsed.fragment,
                )
                return urlunparse(new_parsed)

        return original_url

    def _extract_gid_token(self, gallery_url: str) -> Optional[tuple[str, str]]:
        normalized = self._normalize_gallery_url(gallery_url)
        match = GALLERY_URL_RE.search(normalized)
        if not match:
            return None
        return match.group(1), match.group(2)

    def _build_search_url(self, keyword: str, options: Optional[SearchOptions]) -> str:
        params: dict[str, str] = {"f_search": keyword}
        if options is None:
            return f"{self.base_url}/?{urlencode(params)}"

        if options.f_cats > 0:
            params["f_cats"] = str(options.f_cats)

        adv_enabled = options.advsearch or any(
            [
                options.f_sh,
                options.f_sto,
                options.f_sfl,
                options.f_sfu,
                options.f_sft,
                options.f_srdd > 0,
                options.f_spf > 0,
                options.f_spt > 0,
            ]
        )

        if adv_enabled:
            params["advsearch"] = "1"
            if options.f_sh:
                params["f_sh"] = "on"
            if options.f_sto:
                params["f_sto"] = "on"
            if options.f_sfl:
                params["f_sfl"] = "on"
            if options.f_sfu:
                params["f_sfu"] = "on"
            if options.f_sft:
                params["f_sft"] = "on"
            if options.f_srdd > 0:
                params["f_srdd"] = str(options.f_srdd)
            if options.f_spf > 0:
                params["f_spf"] = str(options.f_spf)
            if options.f_spt > 0:
                params["f_spt"] = str(options.f_spt)

        return f"{self.base_url}/?{urlencode(params)}"

    def _parse_search_results(self, body: str, limit: int) -> list[GalleryResult]:
        soup = BeautifulSoup(body, "html.parser")
        if soup.select_one(".searchwarn") is not None:
            return []

        anchors = soup.select("table.itg .glname a[href], table.itg a.glink[href]")

        results: list[GalleryResult] = []
        seen: set[str] = set()
        for anchor in anchors:
            href_raw = anchor.get("href", "").strip()
            title = anchor.get_text(" ", strip=True)
            if not href_raw or not title:
                continue

            href = self._normalize_gallery_url(href_raw)
            gid_token = self._extract_gid_token(href)
            if not gid_token:
                continue

            gid, token = gid_token
            dedupe_key = f"{gid}:{token}"
            if dedupe_key in seen:
                continue

            seen.add(dedupe_key)
            results.append(GalleryResult(title=title, url=href, gid=gid, token=token))
            if len(results) >= limit:
                break

        return results

    def _search_from_response(self, resp, limit: int) -> list[GalleryResult]:
        body = resp.text
        if getattr(resp, "status_code", None) not in (200, 451):
            self._raise_for_response(resp)

        results = self._parse_search_results(body, limit)
        if results:
            return results

        if getattr(resp, "status_code", None) == 451:
            raise RuntimeError(
                "搜索页返回 451，且正文中未解析出图集列表。请配置 EHENTAI_PROXY，或切换到可访问 E-Hentai 的网络环境。"
            )

        return results

    def _search_sync(
        self,
        keyword: str,
        limit: int,
        options: Optional[SearchOptions],
        http3: Optional[bool] = None,
    ) -> list[GalleryResult]:
        search_url = self._build_search_url(keyword, options)
        with self._curl_session(http3=http3) as session:
            resp = session.get(search_url, headers=self._headers_for_url(search_url))
            return self._search_from_response(resp, limit)

    @staticmethod
    def _is_connect_error(error: Exception) -> bool:
        """检测是否是连接错误（应该 fallback 到标准 DNS）"""
        from httpx import ConnectError as HttpxConnectError
        if isinstance(error, (HttpxConnectError, ssl.SSLError, TimeoutError)):
            return True
        if isinstance(error, OSError) and "Connection" in str(error):
            return True
        return False

    async def search(
        self, keyword: str, limit: int = 5, options: Optional[SearchOptions] = None
    ) -> list[GalleryResult]:
        logger.info(f"[搜索] 开始搜索: keyword='{keyword}', limit={limit}, backend={self.backend}")
        if self.backend == "curl_cffi":
            try:
                logger.debug(f"[搜索] 使用 curl_cffi 后端搜索")
                return await asyncio.to_thread(self._search_sync, keyword, limit, options)
            except Exception as error:
                logger.warning(f"[搜索] curl_cffi 搜索出错: {type(error).__name__}: {error}")
                if self.http3 and self._is_quic_tls_error(error):
                    logger.info(f"[搜索] 检测到 QUIC/TLS 错误，自动降级到 HTTP/1.1")
                    return await asyncio.to_thread(
                        self._search_sync, keyword, limit, options, False
                    )
                if not self._should_fallback_to_httpx(error):
                    logger.error(f"[搜索] 错误不可恢复，抛出异常")
                    raise
                logger.info(f"[搜索] 将使用 httpx 后端作为备选")

        search_url = self._build_search_url(keyword, options)
        logger.debug(f"[搜索] 构建的搜索 URL: {search_url}")

        # 先尝试直连 IP 模式
        if self.enable_direct_ip:
            try:
                request_url = self._get_request_url_for_direct_ip(search_url)
                logger.debug(f"[搜索] 使用直连 IP 模式: {request_url}")
                async with httpx.AsyncClient(
                    timeout=self.timeout,
                    verify=False,
                    follow_redirects=True,
                ) as client:
                    logger.debug(f"[搜索] 发送搜索请求 (直连 IP)")
                    resp = await client.get(request_url, headers=self._headers_for_url(search_url))
                logger.info(f"[搜索] 直连 IP 搜索成功，状态码: {resp.status_code}")
                return self._search_from_response(resp, limit)
            except Exception as error:
                if self._is_connect_error(error):
                    logger.warning(
                        f"[搜索] 直连 IP 连接失败，自动降级到标准 DNS: {type(error).__name__}: {error}",
                    )
                    # 临时禁用直连 IP
                    self.enable_direct_ip = False
                    try:
                        # 重试一次
                        logger.info(f"[搜索] 使用标准 DNS 重试搜索")
                        async with httpx.AsyncClient(
                            timeout=self.timeout,
                            verify=False,
                            follow_redirects=True,
                        ) as client:
                            logger.debug(f"[搜索] 发送搜索请求 (标准 DNS)")
                            resp = await client.get(search_url, headers=self._headers_for_url(search_url))
                        logger.info(f"[搜索] 标准 DNS 搜索成功，状态码: {resp.status_code}")
                        return self._search_from_response(resp, limit)
                    finally:
                        self.enable_direct_ip = True
                else:
                    logger.error(f"[搜索] 直连 IP 发生非连接错误: {type(error).__name__}: {error}")
                    raise

        # 使用标准客户端
        logger.debug(f"[搜索] 使用标准 DNS 模式")
        async with httpx.AsyncClient(
            timeout=self.timeout,
            verify=False,
            follow_redirects=True,
        ) as client:
            logger.debug(f"[搜索] 发送搜索请求 (标准 DNS)")
            resp = await client.get(search_url, headers=self._headers_for_url(search_url))
        logger.info(f"[搜索] 搜索成功，状态码: {resp.status_code}")
        return self._search_from_response(resp, limit)

    async def _get_archive_page(self, client: httpx.AsyncClient, gid: str, token: str) -> str:
        archive_page_url = f"{self.base_url}/archiver.php?gid={gid}&token={token}"
        logger.debug(f"[存档] 获取存档页面: {archive_page_url}")
        # 对于直连 IP，将主机名转换为 IP
        request_url = self._get_request_url_for_direct_ip(archive_page_url) if self.enable_direct_ip else archive_page_url
        logger.debug(f"[存档] 请求 URL: {request_url}, 直连模式: {self.enable_direct_ip}")
        resp = await client.get(
            request_url, headers=self._headers_for_url(archive_page_url)
        )
        logger.debug(f"[存档] 获取存档页面响应: 状态码={resp.status_code}")
        self._raise_for_response(resp)
        if self._is_login_required_page(resp.text):
            logger.error(f"[存档] 需要登录 Cookie 才能访问")
            raise RuntimeError("下载归档需要已登录的 E-Hentai/ExHentai Cookie")
        return resp.text

    def _parse_archive_options(self, body: str) -> list[ArchiveOption]:
        soup = BeautifulSoup(body, "html.parser")

        options: list[ArchiveOption] = []
        archive_blocks = soup.select("#db > div > div")
        for block in archive_blocks:
            style = (block.get("style") or "").replace(" ", "").lower()
            if "color:#cccccc" in style:
                continue

            input_tag = block.select_one("form input[value]")
            size_tag = block.select_one("p strong")
            cost_tag = block.select_one("div strong")
            if not input_tag or not size_tag or not cost_tag:
                continue

            res = input_tag.get("value", "").strip()
            if not res:
                continue

            options.append(
                ArchiveOption(
                    res=res,
                    name="",
                    size=size_tag.get_text(" ", strip=True),
                    cost=cost_tag.get_text(" ", strip=True).replace(",", ""),
                    is_hath=False,
                )
            )

        hath_pattern = re.compile(
            r"do_hathdl\('([0-9]+|org)'\)\">([^<]+)</a></p>\s*"
            r"<p>([\w. ]+)</p>\s*<p>([\w. ]+)</p>",
            flags=re.IGNORECASE,
        )
        for match in hath_pattern.finditer(body):
            options.append(
                ArchiveOption(
                    res=match.group(1),
                    name=match.group(2),
                    size=match.group(3),
                    cost=match.group(4),
                    is_hath=True,
                )
            )

        return options

    def _request_archive_download_url_sync(
        self,
        session,
        gid: str,
        token: str,
        archive_option: ArchiveOption,
    ) -> Optional[str]:
        archive_url = f"{self.base_url}/archiver.php?gid={gid}&token={token}"
        payload: dict[str, str] = {}

        if archive_option.is_hath:
            payload["hathdl_xres"] = archive_option.res
        else:
            payload["dltype"] = archive_option.res
            payload["dlcheck"] = (
                "Download Original Archive"
                if archive_option.res == "org"
                else "Download Resample Archive"
            )

        def do_post() -> Optional[str]:
            resp = session.post(
                archive_url, data=payload, headers=self._headers_for_url(archive_url)
            )
            self._raise_for_response(resp)
            body = resp.text
            if NEED_HATH_CLIENT_MSG in body:
                raise RuntimeError("当前账号未分配 H@H 客户端，无法使用该下载方式")
            if INSUFFICIENT_FUNDS_MSG in body:
                raise RuntimeError("当前账号 GP/Credits 不足，无法下载该归档")

            soup = BeautifulSoup(body, "html.parser")
            continue_link = soup.select_one("#continue a[href]")
            if continue_link is None:
                return None

            href = continue_link.get("href", "").strip()
            if not href:
                return None

            full = self._normalize_gallery_url(href)
            return f"{full}?start=1"

        result = do_post()
        if result is None and not archive_option.is_hath:
            time.sleep(1)
            result = do_post()
        return result

    def _resolve_archive_url_sync(
        self, gallery_url: str, http3: Optional[bool] = None
    ) -> Optional[str]:
        gid_token = self._extract_gid_token(gallery_url)
        if not gid_token:
            return None

        gid, token = gid_token
        archive_page_url = f"{self.base_url}/archiver.php?gid={gid}&token={token}"

        with self._curl_session(http3=http3) as session:
            archive_resp = session.get(
                archive_page_url, headers=self._headers_for_url(archive_page_url)
            )
            self._raise_for_response(archive_resp)
            archive_page = archive_resp.text
            if self._is_login_required_page(archive_page):
                raise RuntimeError("下载归档需要已登录的 E-Hentai/ExHentai Cookie")
            if NEED_HATH_CLIENT_MSG in archive_page:
                return None

            options = self._parse_archive_options(archive_page)
            if not options:
                return None

            preferred = next(
                (item for item in options if not item.is_hath and item.res == "org"),
                None,
            )
            if preferred is None:
                preferred = next((item for item in options if not item.is_hath), options[0])

            return self._request_archive_download_url_sync(session, gid, token, preferred)

    async def _request_archive_download_url(
        self,
        client: httpx.AsyncClient,
        gid: str,
        token: str,
        archive_option: ArchiveOption,
    ) -> Optional[str]:
        archive_url = f"{self.base_url}/archiver.php?gid={gid}&token={token}"
        # 对于直连 IP，将主机名转换为 IP
        request_url = self._get_request_url_for_direct_ip(archive_url)
        payload: dict[str, str] = {}

        if archive_option.is_hath:
            payload["hathdl_xres"] = archive_option.res
        else:
            payload["dltype"] = archive_option.res
            if archive_option.res == "org":
                payload["dlcheck"] = "Download Original Archive"
            else:
                payload["dlcheck"] = "Download Resample Archive"

        async def do_post() -> Optional[str]:
            resp = await client.post(
                request_url,
                data=payload,
                headers=self._headers_for_url(archive_url),
            )
            self._raise_for_response(resp)

            body = resp.text
            if NEED_HATH_CLIENT_MSG in body:
                raise RuntimeError("当前账号未分配 H@H 客户端，无法使用该下载方式")
            if INSUFFICIENT_FUNDS_MSG in body:
                raise RuntimeError("当前账号 GP/Credits 不足，无法下载该归档")

            soup = BeautifulSoup(body, "html.parser")
            continue_link = soup.select_one("#continue a[href]")
            if continue_link is None:
                return None

            href = continue_link.get("href", "").strip()
            if not href:
                return None

            full = self._normalize_gallery_url(href)
            return f"{full}?start=1"

        result = await do_post()
        if result is None and not archive_option.is_hath:
            await asyncio.sleep(1)
            result = await do_post()
        return result

    async def resolve_archive_url(self, gallery_url: str) -> Optional[str]:
        logger.info(f"[存档] 开始解析存档下载链接: {gallery_url}")
        if self.backend == "curl_cffi":
            try:
                logger.debug(f"[存档] 使用 curl_cffi 后端解析")
                return await asyncio.to_thread(self._resolve_archive_url_sync, gallery_url)
            except Exception as error:
                logger.warning(f"[存档] curl_cffi 解析出错: {type(error).__name__}: {error}")
                if self.http3 and self._is_quic_tls_error(error):
                    logger.info(f"[存档] 检测到 QUIC/TLS 错误，自动降级到 HTTP/1.1")
                    return await asyncio.to_thread(self._resolve_archive_url_sync, gallery_url, False)
                if not self._should_fallback_to_httpx(error):
                    logger.error(f"[存档] 错误不可恢复，抛出异常")
                    raise
                logger.info(f"[存档] 将使用 httpx 后端作为备选")

        gid_token = self._extract_gid_token(gallery_url)
        if not gid_token:
            logger.warning(f"[存档] 无法从 URL 提取 gid/token")
            return None

        gid, token = gid_token
        logger.debug(f"[存档] 提取到 gid={gid}, token={token}")

        # 先尝试直连 IP 模式
        if self.enable_direct_ip:
            try:
                logger.debug(f"[存档] 使用直连 IP 模式")
                async with httpx.AsyncClient(
                    timeout=self.timeout,
                    verify=False,
                    follow_redirects=True,
                ) as client:
                    logger.debug(f"[存档] 获取存档页面 (直连 IP)")
                    archive_page = await self._get_archive_page(client, gid, token)
                    if NEED_HATH_CLIENT_MSG in archive_page:
                        logger.warning(f"[存档] 需要 H@H 客户端")
                        return None

                    logger.debug(f"[存档] 解析存档选项")
                    options = self._parse_archive_options(archive_page)
                    if not options:
                        logger.warning(f"[存档] 未找到可用的存档选项")
                        return None

                    preferred = next(
                        (item for item in options if not item.is_hath and item.res == "org"),
                        None,
                    )
                    if preferred is None:
                        preferred = next((item for item in options if not item.is_hath), options[0])
                    logger.debug(f"[存档] 选择存档: {preferred.res}")
                    url = await self._request_archive_download_url(client, gid, token, preferred)
                    logger.info(f"[存档] 成功获取下载链接 (直连 IP)")
                    return url
            except Exception as error:
                if self._is_connect_error(error):
                    logger.warning(
                        f"[存档] 直连 IP 连接失败，自动降级到标准 DNS: {type(error).__name__}: {error}",
                    )
                    # 临时禁用直连 IP，重试
                    self.enable_direct_ip = False
                    try:
                        logger.info(f"[存档] 使用标准 DNS 重试")
                        async with httpx.AsyncClient(
                            timeout=self.timeout,
                            verify=False,
                            follow_redirects=True,
                        ) as client:
                            logger.debug(f"[存档] 获取存档页面 (标准 DNS)")
                            archive_page = await self._get_archive_page(client, gid, token)
                            if NEED_HATH_CLIENT_MSG in archive_page:
                                logger.warning(f"[存档] 需要 H@H 客户端")
                                return None

                            logger.debug(f"[存档] 解析存档选项")
                            options = self._parse_archive_options(archive_page)
                            if not options:
                                logger.warning(f"[存档] 未找到可用的存档选项")
                                return None

                            preferred = next(
                                (item for item in options if not item.is_hath and item.res == "org"),
                                None,
                            )
                            if preferred is None:
                                preferred = next((item for item in options if not item.is_hath), options[0])
                            logger.debug(f"[存档] 选择存档: {preferred.res}")
                            url = await self._request_archive_download_url(client, gid, token, preferred)
                            logger.info(f"[存档] 成功获取下载链接 (标准 DNS)")
                            return url
                    finally:
                        self.enable_direct_ip = True
                else:
                    logger.error(f"[存档] 直连 IP 发生非连接错误: {type(error).__name__}: {error}")
                    raise

        # 使用标准客户端
        logger.debug(f"[存档] 使用标准 DNS 模式")
        async with httpx.AsyncClient(
            timeout=self.timeout,
            verify=False,
            follow_redirects=True,
        ) as client:
            logger.debug(f"[存档] 获取存档页面 (标准 DNS)")
            archive_page = await self._get_archive_page(client, gid, token)
            if NEED_HATH_CLIENT_MSG in archive_page:
                logger.warning(f"[存档] 需要 H@H 客户端")
                return None

            logger.debug(f"[存档] 解析存档选项")
            options = self._parse_archive_options(archive_page)
            if not options:
                logger.warning(f"[存档] 未找到可用的存档选项")
                return None

            preferred = next(
                (item for item in options if not item.is_hath and item.res == "org"),
                None,
            )
            if preferred is None:
                preferred = next((item for item in options if not item.is_hath), options[0])
            logger.debug(f"[存档] 选择存档: {preferred.res}")
            url = await self._request_archive_download_url(client, gid, token, preferred)
            logger.info(f"[存档] 成功获取下载链接 (标准 DNS)")
            return url

    def _download_file_sync(
        self, url: str, save_path: Path, http3: Optional[bool] = None
    ) -> Path:
        save_path.parent.mkdir(parents=True, exist_ok=True)
        with self._curl_session(http3=http3) as session:
            with session.stream("GET", url, headers=self._headers_for_url(url)) as resp:
                self._raise_for_response(resp)
                with save_path.open("wb") as file:
                    for chunk in resp.iter_content(chunk_size=1024 * 128):
                        if chunk:
                            file.write(chunk)
        return save_path

    async def download_file(self, url: str, save_path: Path) -> Path:
        logger.info(f"[下载] 开始下载文件: {url}")
        logger.debug(f"[下载] 保存路径: {save_path}")
        if self.backend == "curl_cffi":
            try:
                logger.debug(f"[下载] 使用 curl_cffi 后端")
                return await asyncio.to_thread(self._download_file_sync, url, save_path)
            except Exception as error:
                logger.warning(f"[下载] curl_cffi 下载出错: {type(error).__name__}: {error}")
                if self.http3 and self._is_quic_tls_error(error):
                    logger.info(f"[下载] 检测到 QUIC/TLS 错误，自动降级到 HTTP/1.1")
                    return await asyncio.to_thread(self._download_file_sync, url, save_path, False)
                if not self._should_fallback_to_httpx(error):
                    logger.error(f"[下载] 错误不可恢复，抛出异常")
                    raise
                logger.info(f"[下载] 将使用 httpx 后端作为备选")

        save_path.parent.mkdir(parents=True, exist_ok=True)
        logger.debug(f"[下载] 创建下载目录成功")

        # 先尝试直连 IP 模式
        if self.enable_direct_ip:
            try:
                request_url = self._get_request_url_for_direct_ip(url)
                logger.debug(f"[下载] 使用直连 IP 模式: {request_url}")
                async with self._client() as client:
                    logger.debug(f"[下载] 开始下载流 (直连 IP)")
                    async with client.stream("GET", request_url, headers=self._headers_for_url(url)) as resp:
                        self._raise_for_response(resp)
                        logger.debug(f"[下载] 响应状态码: {resp.status_code}")
                        downloaded = 0
                        with save_path.open("wb") as file:
                            async for chunk in resp.aiter_bytes(chunk_size=1024 * 128):
                                file.write(chunk)
                                downloaded += len(chunk)
                        logger.info(f"[下载] 直连 IP 下载成功，大小: {downloaded / 1024 / 1024:.2f} MB")
                return save_path
            except Exception as error:
                # 直连 IP 失败（ConnectError、SSLError 等），自动 fallback
                from httpx import ConnectError as HttpxConnectError
                if isinstance(error, (HttpxConnectError, ssl.SSLError, TimeoutError)):
                    logger.warning(
                        f"[下载] 直连 IP 连接失败，自动降级到标准 DNS: {type(error).__name__}: {error}",
                        exc_info=True
                    )
                    # 临时禁用直连 IP
                    self.enable_direct_ip = False
                    try:
                        # 重试一次
                        logger.info(f"[下载] 使用标准 DNS 重试下载")
                        async with httpx.AsyncClient(
                            timeout=self.timeout,
                            verify=False,
                            follow_redirects=True,
                        ) as client:
                            logger.debug(f"[下载] 开始下载流 (标准 DNS)")
                            async with client.stream("GET", url, headers=self._headers_for_url(url)) as resp:
                                self._raise_for_response(resp)
                                logger.debug(f"[下载] 响应状态码: {resp.status_code}")
                                downloaded = 0
                                with save_path.open("wb") as file:
                                    async for chunk in resp.aiter_bytes(chunk_size=1024 * 128):
                                        file.write(chunk)
                                        downloaded += len(chunk)
                            logger.info(f"[下载] 标准 DNS 下载成功，大小: {downloaded / 1024 / 1024:.2f} MB")
                        return save_path
                    finally:
                        # 恢复设置
                        self.enable_direct_ip = True
                else:
                    # 其他错误直接抛出
                    logger.error(f"[下载] 直连 IP 发生非连接错误: {type(error).__name__}: {error}")
                    raise

        # 降级到标准 httpx 客户端
        logger.debug(f"[下载] 使用标准 DNS 模式")
        async with httpx.AsyncClient(
            timeout=self.timeout,
            verify=False,
            follow_redirects=True,
        ) as client:
            logger.debug(f"[下载] 开始下载流 (标准 DNS)")
            async with client.stream("GET", url, headers=self._headers_for_url(url)) as resp:
                self._raise_for_response(resp)
                logger.debug(f"[下载] 响应状态码: {resp.status_code}")
                downloaded = 0
                with save_path.open("wb") as file:
                    async for chunk in resp.aiter_bytes(chunk_size=1024 * 128):
                        file.write(chunk)
                        downloaded += len(chunk)
            logger.info(f"[下载] 下载成功，大小: {downloaded / 1024 / 1024:.2f} MB")

        return save_path