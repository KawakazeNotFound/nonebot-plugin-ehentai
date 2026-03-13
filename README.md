# nonebot-plugin-ehentai

一个用于 NoneBot2 + OneBot11（NapCat）的插件，提供：

- `/search [Name]`：按名称搜索本子
- `/download [Name]`：下载压缩包并上传到当前群文件

## 安装

在你的 NoneBot 项目中安装（开发阶段也可以本地 editable 安装）：

```bash
pip install -e .
```

并确保你的 `pyproject.toml`（或 `bot.py` 加载逻辑）加载了插件：

```toml
[tool.nonebot]
plugins = ["nonebot_plugin_ehentai"]
```

## 配置

在 `.env` 中添加以下配置：

```env
EHENTAI_SITE=e
EHENTAI_BASE_URL=https://e-hentai.org
EHENTAI_COOKIE=
EHENTAI_IPB_MEMBER_ID=
EHENTAI_IPB_PASS_HASH=
EHENTAI_IGNEOUS=
EHENTAI_CF_CLEARANCE=
EHENTAI_TIMEOUT=20
EHENTAI_MAX_RESULTS=5
EHENTAI_DOWNLOAD_DIR=data/ehentai
EHENTAI_PROXY=
EHENTAI_HTTP_BACKEND=curl_cffi
EHENTAI_HTTP3=true
EHENTAI_DESKTOP_SITE=false
EHENTAI_IMPERSONATE=chrome124
EHENTAI_STREAM_UPLOAD_FIRST=true
EHENTAI_STREAM_CHUNK_SIZE=262144
EHENTAI_STREAM_FILE_RETENTION_MS=300000
EHENTAI_SEARCH_F_CATS=0
EHENTAI_SEARCH_ADVSEARCH=false
EHENTAI_SEARCH_F_SH=false
EHENTAI_SEARCH_F_STO=false
EHENTAI_SEARCH_F_SFL=false
EHENTAI_SEARCH_F_SFU=false
EHENTAI_SEARCH_F_SFT=false
EHENTAI_SEARCH_F_SRDD=0
EHENTAI_SEARCH_F_SPF=0
EHENTAI_SEARCH_F_SPT=0
```

### 配置说明

- `EHENTAI_SITE`：站点选择，`e` 表示 `e-hentai.org`，`ex` 表示 `exhentai.org`
- `EHENTAI_BASE_URL`：站点地址；通常无需手改，程序会优先根据 `EHENTAI_SITE` 选择站点
- `EHENTAI_COOKIE`：原始 Cookie Header；若填写，将优先于下方身份 Cookie 配置
- `EHENTAI_IPB_MEMBER_ID`：EhViewer 身份 Cookie 之一
- `EHENTAI_IPB_PASS_HASH`：EhViewer 身份 Cookie 之一
- `EHENTAI_IGNEOUS`：ExHentai 访问常用 Cookie；使用 `exhentai` 时通常需要
- `EHENTAI_CF_CLEARANCE`：Cloudflare 验证 Cookie；如有可一并填写
- `EHENTAI_TIMEOUT`：请求超时秒数
- `EHENTAI_MAX_RESULTS`：`/search` 返回条数上限
- `EHENTAI_DOWNLOAD_DIR`：压缩包下载到本地的目录
- `EHENTAI_PROXY`：可选代理（例如 `http://127.0.0.1:7890`）
- `EHENTAI_HTTP_BACKEND`：HTTP 后端，支持 `curl_cffi` 或 `httpx`
- `EHENTAI_HTTP3`：在 `curl_cffi` 后端下是否优先使用 HTTP/3
- `EHENTAI_DESKTOP_SITE`：是否使用桌面站风格 UA；默认关闭，更接近 EhViewer 绕 Cloudflare 时的移动站策略
- `EHENTAI_IMPERSONATE`：`curl_cffi` 浏览器指纹，例如 `chrome124`
- `EHENTAI_STREAM_UPLOAD_FIRST`：是否优先使用 `upload_file_stream`（推荐开启）
- `EHENTAI_STREAM_CHUNK_SIZE`：流式上传分片大小（字节）
- `EHENTAI_STREAM_FILE_RETENTION_MS`：流式上传后 NapCat 临时文件保留时长（毫秒）
- `EHENTAI_SEARCH_F_CATS`：分类过滤参数（对应 E-Hentai `f_cats`）
- `EHENTAI_SEARCH_ADVSEARCH`：是否启用高级搜索（对应 `advsearch=1`）
- `EHENTAI_SEARCH_F_SH`：高级搜索-启用删除画廊过滤（`f_sh=on`）
- `EHENTAI_SEARCH_F_STO`：高级搜索-仅有种子（`f_sto=on`）
- `EHENTAI_SEARCH_F_SFL`：高级搜索-禁用语言过滤（`f_sfl=on`）
- `EHENTAI_SEARCH_F_SFU`：高级搜索-禁用上传者过滤（`f_sfu=on`）
- `EHENTAI_SEARCH_F_SFT`：高级搜索-禁用标签过滤（`f_sft=on`）
- `EHENTAI_SEARCH_F_SRDD`：高级搜索最低评分（`f_srdd`，>0 生效）
- `EHENTAI_SEARCH_F_SPF`：页数下限（`f_spf`，>0 生效）
- `EHENTAI_SEARCH_F_SPT`：页数上限（`f_spt`，>0 生效）

## 指令

- `/search [Name]`：搜索并返回若干条结果（标题 + 链接）
- `/download [Name]`：
  1. 按关键词搜索
  2. 取第一条结果
  3. 解析归档下载链接并下载 zip
  4. 优先调用 `upload_file_stream` 上传到 NapCat 侧临时文件
  5. 再调用 `upload_group_file` 上传到当前群
  6. 若 stream 接口失败，自动回退到本地路径直传 `upload_group_file`

## NapCat 说明

本插件默认优先使用 Stream API：`upload_file_stream`，并使用 `upload_group_file` 完成群文件发送。

如果你当前 NapCat 配置不支持该接口，请确认：

1. 连接的是 OneBot11 协议
2. `upload_file_stream` 和 `upload_group_file` 在当前实现里可用

若你的实现是其他上传方式（例如你有自定义发送文件 API），告诉我接口名和参数，我可以直接改成你的版本。

## Cookie 登录说明

本插件已按 EhViewer 的思路支持“身份 Cookie”登录，而不是只依赖单个原始 Cookie 字符串。

- 对 `e-hentai`：至少建议提供 `EHENTAI_IPB_MEMBER_ID` 与 `EHENTAI_IPB_PASS_HASH`
- 对 `exhentai`：除上述两项外，通常还需要 `EHENTAI_IGNEOUS`
- `EHENTAI_CF_CLEARANCE` 可选，但在某些网络环境下有帮助
- 程序会像 EhViewer 一样，对 `e-hentai.org` 自动附加 `nw=1`

如果你已经从浏览器或 EhViewer 导出了完整 Cookie，也可以直接填 `EHENTAI_COOKIE`，此时程序会优先使用它。
