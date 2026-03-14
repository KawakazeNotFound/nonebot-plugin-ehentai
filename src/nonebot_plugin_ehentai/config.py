from pydantic import BaseModel, field_validator


class Config(BaseModel):
    ehentai_site: str = "e"
    ehentai_base_url: str = "https://e-hentai.org"
    ehentai_cookie: str = ""
    ehentai_ipb_member_id: str = ""
    ehentai_ipb_pass_hash: str = ""
    ehentai_igneous: str = ""
    ehentai_cf_clearance: str = ""
    ehentai_user_agent: str = (
        "Mozilla/5.0 (Linux; Android 10; K) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36"
    )
    ehentai_timeout: int = 20
    ehentai_max_results: int = 5
    ehentai_download_dir: str = "data/ehentai"
    ehentai_proxy: str = ""
    ehentai_http_backend: str = "httpx"
    ehentai_http3: bool = True
    ehentai_desktop_site: bool = False
    ehentai_impersonate: str = "chrome124"
    ehentai_enable_direct_ip: bool = True  # EhViewer_CN_SXJ 直连 IP 方案（用于绕过网络限制）
    ehentai_curl_cffi_skip_on_error: bool = True  # 搜索时 curl_cffi 失败立即降级到 httpx，不重试
    ehentai_stream_upload_first: bool = True
    ehentai_stream_chunk_size: int = 256 * 1024
    ehentai_stream_file_retention_ms: int = 5 * 60 * 1000
    ehentai_search_f_cats: int = 0
    ehentai_search_advsearch: bool = False
    ehentai_search_f_sh: bool = False
    ehentai_search_f_sto: bool = False
    ehentai_search_f_sfl: bool = False
    ehentai_search_f_sfu: bool = False
    ehentai_search_f_sft: bool = False
    ehentai_search_f_srdd: int = 0
    ehentai_search_f_spf: int = 0
    ehentai_search_f_spt: int = 0
    
    # Cloudflare R2 备用上传配置
    ehentai_r2_access_key_id: str = ""
    ehentai_r2_secret_access_key: str = ""
    ehentai_r2_bucket_name: str = "ehentai"
    ehentai_r2_endpoint: str = ""
    ehentai_r2_public_domain: str = "https://pub-REDACTED.r2.dev"
    ehentai_r2_max_total_size_mb: int = 3072  # 3GB in MB
    ehentai_r2_file_retention_hours: int = 24
    ehentai_r2_enabled: bool = False

    @field_validator(
        "ehentai_cookie",
        "ehentai_ipb_member_id",
        "ehentai_ipb_pass_hash",
        "ehentai_igneous",
        "ehentai_cf_clearance",
        "ehentai_r2_access_key_id",
        "ehentai_r2_secret_access_key",
        "ehentai_r2_endpoint",
        mode="before",
    )
    @classmethod
    def coerce_cookie_values(cls, value: object) -> str:
        if value is None:
            return ""
        return str(value)