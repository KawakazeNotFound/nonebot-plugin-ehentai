from __future__ import annotations

import argparse
import json
from typing import Optional

from bs4 import BeautifulSoup
from curl_cffi import requests


def fetch(url: str, proxy: str, cookie: str, http3: bool, impersonate: str):
    kwargs = {
        "impersonate": impersonate,
        "headers": {
            "User-Agent": (
                "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36"
            ),
            "Accept": (
                "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,"
                "image/webp,image/apng,*/*;q=0.8"
            ),
            "Accept-Language": "en-US,en;q=0.9",
            **({"Cookie": cookie} if cookie else {}),
        },
    }
    if proxy:
        kwargs["proxies"] = {"http": proxy, "https": proxy}
    if http3:
        from curl_cffi.const import CurlHttpVersion

        kwargs["http_version"] = CurlHttpVersion.V3
    return requests.get(url, **kwargs)


def merge_cookie_string(
    raw_cookie: str,
    ipb_member_id: str,
    ipb_pass_hash: str,
    igneous: str,
    cf_clearance: str,
    host: str,
) -> str:
    if raw_cookie:
        return raw_cookie

    parts: list[str] = []
    if ipb_member_id:
        parts.append(f"ipb_member_id={ipb_member_id}")
    if ipb_pass_hash:
        parts.append(f"ipb_pass_hash={ipb_pass_hash}")
    if cf_clearance:
        parts.append(f"cf_clearance={cf_clearance}")
    if "e-hentai.org" in host:
        parts.append("nw=1")
    if "exhentai.org" in host and igneous:
        parts.append(f"igneous={igneous}")
    return "; ".join(parts)


def inspect_html(url: str, proxy: str, cookie: str, http3: bool, impersonate: str) -> None:
    resp = fetch(url, proxy, cookie, http3, impersonate)
    soup = BeautifulSoup(resp.text, "html.parser")
    print(f"URL: {url}")
    print(f"status: {resp.status_code}")
    print(f"title: {soup.title.string if soup.title else ''}")
    print(f"has_itg: {soup.select_one('table.itg') is not None}")
    print(f"glink_count: {len(soup.select('table.itg .glname a[href], table.itg a.glink[href]'))}")
    print(f"has_login_prompt: {'This page requires you to log on.' in resp.text}")
    print(f"prefix: {resp.text[:300].replace(chr(10), ' ')}")
    print("-")


def inspect_api(api_url: str, gid: Optional[str], token: Optional[str], proxy: str, cookie: str, http3: bool, impersonate: str) -> None:
    payload = {"method": "gdata", "gidlist": [], "namespace": 1}
    if gid and token:
        payload["gidlist"].append([int(gid), token])

    kwargs = {
        "impersonate": impersonate,
        "headers": {
            "User-Agent": (
                "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36"
            ),
            "Content-Type": "application/json",
            **({"Cookie": cookie} if cookie else {}),
        },
        "data": json.dumps(payload),
    }
    if proxy:
        kwargs["proxies"] = {"http": proxy, "https": proxy}
    if http3:
        from curl_cffi.const import CurlHttpVersion

        kwargs["http_version"] = CurlHttpVersion.V3

    resp = requests.post(api_url, **kwargs)
    print(f"API: {api_url}")
    print(f"status: {resp.status_code}")
    print(f"body: {resp.text[:500]}")
    print("-")


def main() -> None:
    parser = argparse.ArgumentParser(description="Test E-Hentai / ExHentai HTML and API access")
    parser.add_argument("--proxy", default="", help="HTTP/HTTPS proxy, e.g. http://127.0.0.1:7890")
    parser.add_argument("--cookie", default="", help="Raw Cookie header for E-Hentai / ExHentai")
    parser.add_argument("--ipb-member-id", default="", help="Identity cookie: ipb_member_id")
    parser.add_argument("--ipb-pass-hash", default="", help="Identity cookie: ipb_pass_hash")
    parser.add_argument("--igneous", default="", help="ExHentai cookie: igneous")
    parser.add_argument("--cf-clearance", default="", help="Cloudflare cookie: cf_clearance")
    parser.add_argument("--gid", default="530350", help="Gallery gid for gdata API test")
    parser.add_argument("--token", default="8b3c7e4a21", help="Gallery token for gdata API test")
    parser.add_argument("--http3", action="store_true", help="Use HTTP/3")
    parser.add_argument("--impersonate", default="chrome124", help="curl_cffi impersonate profile")
    args = parser.parse_args()

    e_cookie = merge_cookie_string(
        args.cookie,
        args.ipb_member_id,
        args.ipb_pass_hash,
        args.igneous,
        args.cf_clearance,
        "e-hentai.org",
    )
    ex_cookie = merge_cookie_string(
        args.cookie,
        args.ipb_member_id,
        args.ipb_pass_hash,
        args.igneous,
        args.cf_clearance,
        "exhentai.org",
    )

    inspect_html("https://e-hentai.org/?f_search=naruto", args.proxy, e_cookie, args.http3, args.impersonate)
    inspect_html("https://e-hentai.org/g/530350/8b3c7e4a21/", args.proxy, e_cookie, args.http3, args.impersonate)
    inspect_html("https://e-hentai.org/archiver.php?gid=530350&token=8b3c7e4a21", args.proxy, e_cookie, args.http3, args.impersonate)
    inspect_html("https://exhentai.org/", args.proxy, ex_cookie, args.http3, args.impersonate)

    inspect_api("https://api.e-hentai.org/api.php", args.gid, args.token, args.proxy, e_cookie, args.http3, args.impersonate)
    inspect_api("https://s.exhentai.org/api.php", args.gid, args.token, args.proxy, ex_cookie, args.http3, args.impersonate)


if __name__ == "__main__":
    main()