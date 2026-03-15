# 安全指南 | Security Guidelines

## 敏感信息配置 | Sensitive Information Configuration

本项目包含多个需要敏感凭证的模块。请按照以下步骤配置：

### 1. 环境变量配置 | Environment Variables

创建 `.env.local` 文件（**请勿提交到git**）：

```bash
# E-Hentai 凭证
EHENTAI_COOKIE=your_cookieP_value
EHENTAI_IPB_MEMBER_ID=your_ipb_member_id
EHENTAI_IPB_PASS_HASH=your_ipb_pass_hash
EHENTAI_IGNEOUS=your_igneous_value
EHENTAI_CF_CLEARANCE=your_cf_clearance_value

# Cloudflare R2 配置
EHENTAI_R2_ACCESS_KEY_ID=your_r2_access_key
EHENTAI_R2_SECRET_ACCESS_KEY=your_r2_secret_key
EHENTAI_R2_ENDPOINT=https://your-account.r2.cloudflarestorage.com

# Cloudflare D1 配置
EHENTAI_D1_ACCOUNT_ID=your_account_id
EHENTAI_D1_DATABASE_ID=your_database_id
EHENTAI_D1_API_TOKEN=your_d1_api_token
```

### 2. 代码配置 | Code Configuration

在 NoneBot2 的 `bot.py` 或配置文件中设置：

```python
# bot.py 或配置文件
nonebot_config = {
    "ehentai_cookie": os.getenv("EHENTAI_COOKIE", ""),
    "ehentai_ipb_member_id": os.getenv("EHENTAI_IPB_MEMBER_ID", ""),
    "ehentai_r2_access_key_id": os.getenv("EHENTAI_R2_ACCESS_KEY_ID", ""),
    "ehentai_r2_secret_access_key": os.getenv("EHENTAI_R2_SECRET_ACCESS_KEY", ""),
    "ehentai_d1_api_token": os.getenv("EHENTAI_D1_API_TOKEN", ""),
}
```

### 3. Android 签名密钥 | Android Signing Key

如果构建 EhViewer Android 项目，请参考 `Ehviewer/EhViewer/app/keystore/` 目录。

**重要**：`*.jks` 和 `*.key` 文件已被添加到 `.gitignore`，不会被提交。

## 安全最佳实践 | Security Best Practices

### 提交前检查 | Pre-commit Checks

- ✅ 运行 `git diff --cached` 检查不会暴露敏感信息
- ✅ 使用 `.env.local` 或环境变量管理敏感信息
- ✅ 不要将 `config.json`、`.env`、`keystore` 等提交到 git
- ✅ 定期审查 `git log` 检查是否有敏感信息被意外提交

### 密钥轮换 | Key Rotation

如果不小心泄露任何密钥：

1. **立即删除**本地的敏感文件
2. **重新生成**或**撤销** API 令牌、密钥等
3. 运行 `git reflog expire --expire=now --all && git gc --prune=now` 清理 git 历史
4. 新建分支并推送修复

### Git 历史安全 | Git History Security

检查 git 历史中是否有敏感信息：

```bash
# 搜索常见的敏感词
git log -p --all -S "api_token" -S "secret" -S "password" | grep -i "token\|secret\|password"

# 查找各种密钥文件
git ls-files | grep -E "\.(jks|key|pem|p12|pfx)$"

# 检查已删除但在历史中的文件
git log --diff-filter=D --summary | grep -E "\.(jks|key|pem)$"
```

## 依赖项安全 | Dependencies Security

此项目使用以下依赖项：
- `boto3` - AWS SDK（用于 R2 存储）
- `httpx` - HTTP 客户端
- `beautifulsoup4` - HTML 解析

定期更新依赖项以获取安全补丁：

```bash
pip install --upgrade -r requirements.txt
```

## 报告安全问题 | Reporting Security Issues

如果发现安全漏洞，请通过私密方式报告，**不要**在 GitHub Issue 中公开讨论。

---

**最后更新 | Last Updated**: 2026-03-15
