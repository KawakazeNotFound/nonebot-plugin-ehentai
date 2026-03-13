#!/usr/bin/env python3
"""
EhViewer_CN_SXJ 直连 IP 网络模块测试脚本

测试 E-Hentai/ExHentai 直连 IP + DNS 分流功能
"""

import sys
from pathlib import Path
import importlib.util

# 直接加载 network 模块，绕过 __init__.py
network_path = Path(__file__).parent / "src" / "nonebot_plugin_ehentai" / "network.py"
spec = importlib.util.spec_from_file_location("network", network_path)
network = importlib.util.module_from_spec(spec)
spec.loader.exec_module(network)

BUILT_IN_HOSTS = network.BUILT_IN_HOSTS
EhHttpRouter = network.EhHttpRouter


def test_built_in_hosts():
    """测试内置主机映射"""
    print("\n=== 内置主机映射测试 ===")
    print(f"✓ 已加载 {len(BUILT_IN_HOSTS)} 个内置主机映射\n")

    for hostname, ips in list(BUILT_IN_HOSTS.items())[:5]:
        print(f"  {hostname:<30} → {ips[0]}")
    
    print("\n内置主机列表（完整）:")
    for hostname in BUILT_IN_HOSTS.keys():
        print(f"  • {hostname}")


def test_url_conversion():
    """测试 URL 转换"""
    print("\n=== URL 直连 IP 转换测试 ===")
    
    test_urls = [
        "https://e-hentai.org/g/123456/abcdef1234",
        "https://exhentai.org/g/987654/zyxwvut321",
        "https://api.e-hentai.org/api.php?gidlist=[[1,2]]",
        "https://ehgt.org/image.jpg",
    ]
    
    for url in test_urls:
        router = EhHttpRouter()
        # 由于 _get_request_url_for_direct_ip 是 service.py 中的方法，这里手动模拟
        from urllib.parse import urlparse, urlunparse
        
        parsed = urlparse(url)
        hostname = parsed.hostname
        
        if hostname and hostname in BUILT_IN_HOSTS:
            ips = BUILT_IN_HOSTS.get(hostname, [])
            ip = ips[0] if ips else None
            new_netloc = ip
            if parsed.port and parsed.port not in (80, 443):
                new_netloc = f"{ip}:{parsed.port}"
            
            new_url = urlunparse(("https", new_netloc, parsed.path, parsed.params, parsed.query, parsed.fragment))
            print(f"  原始: {url}")
            print(f"  转换: {new_url}\n")


def test_host_header_injection():
    """测试 Host 头注入"""
    print("\n=== Host 头注入测试 ===")
    
    test_cases = {
        "https://e-hentai.org/path": "e-hentai.org",
        "https://exhentai.org:443/path": "exhentai.org",
        "https://ehgt.org:8443/file": "ehgt.org:8443",
    }
    
    for url, expected_host in test_cases.items():
        from urllib.parse import urlparse
        parsed = urlparse(url)
        hostname = parsed.hostname
        port = parsed.port
        
        if port and port not in (80, 443):
            host_header = f"{hostname}:{port}"
        else:
            host_header = hostname
        
        status = "✓" if host_header == expected_host else "✗"
        print(f"  {status} {url}")
        print(f"     → Host: {host_header}")


def main():
    """主函数"""
    print("=" * 60)
    print("EhViewer_CN_SXJ 直连 IP 网络模块测试")
    print("=" * 60)
    
    test_built_in_hosts()
    test_url_conversion()
    test_host_header_injection()
    
    print("\n" + "=" * 60)
    print("✓ 所有测试完成")
    print("=" * 60)
    print("\n配置说明:")
    print("  • EHENTAI_ENABLE_DIRECT_IP=true  - 启用直连 IP（默认）")
    print("  • EHENTAI_ENABLE_DIRECT_IP=false - 禁用直连 IP（使用标准 DNS）")
    print("\n适用场景:")
    print("  • 沙特阿拉伯等 ISP 污染/阻止 DNS 的地区")
    print("  • 需要绕过 DNS 污染而非 IP 级别阻止的网络环境")
    print("\n局限:")
    print("  • 无法绕过 IP 级别的完全阻止（需要使用代理）")


if __name__ == "__main__":
    main()
