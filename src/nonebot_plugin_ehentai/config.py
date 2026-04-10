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
    ehentai_download_timeout: int = 60  # 单机文件下载超时时间（秒）
    ehentai_min_cache_file_size_kb: int = 100  # 最小缓存文件大小（KB），小于此大小的文件视为残留
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
    ehentai_upload_to_group_file: bool = False  # 默认禁用群文件上传，避免 NapCat 不稳定导致的错误
    ehentai_prefer_r2_over_group_file: bool = True  # 默认优先使用 R2 上传
    ehentai_use_napcat_stream_upload: bool = True  # 默认开启流上传（如果用户手动启用了群文件上传，此项更稳定）
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
    ehentai_r2_public_domain: str = "https://botgeneratedcontent.0061226.xyz"
    ehentai_r2_max_total_size_mb: int = 3072  # 3GB in MB
    ehentai_r2_file_retention_hours: int = 24
    ehentai_r2_enabled: bool = False

    # Cloudflare D1 数据库配置
    ehentai_d1_account_id: str = "" # 如果为空，尝试从 R2 Endpoint 自动提取
    ehentai_d1_database_id: str = ""
    ehentai_d1_api_token: str = "" # 需要有 D1 编辑权限的令牌
    ehentai_d1_enabled: bool = False
    ehentai_d1_auto_cleanup_expired_metadata: bool = False  # 是否自动清理 D1 过期记录（默认关闭，保留下载历史）

    # 消息展现与清理配置
    ehentai_download_message_type: str = "single_bubble" # "single_bubble" 或 "forward"
    ehentai_auto_cleanup_local: bool = True # 是否启用每日凌晨自动清理本地缓存
    ehentai_auto_cleanup_time: str = "03:00" # 定时清理的具体时间（24小时制）

    @field_validator(
        "ehentai_cookie",
        "ehentai_ipb_member_id",
        "ehentai_ipb_pass_hash",
        "ehentai_igneous",
        "ehentai_cf_clearance",
        "ehentai_r2_access_key_id",
        "ehentai_r2_secret_access_key",
        "ehentai_r2_endpoint",
        "ehentai_d1_account_id",
        "ehentai_d1_database_id",
        "ehentai_d1_api_token",
        mode="before",
    )
    @classmethod
    def coerce_cookie_values(cls, value: object) -> str:
        if value is None:
            return ""
        return str(value)