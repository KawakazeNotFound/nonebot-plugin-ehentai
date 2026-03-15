# 🚨 安全事件报告 | Security Incident Report

**报告日期**: 2026-03-15  
**严重级别**: 中等 | MEDIUM  
**事件状态**: 已部分修复 | PARTIALLY REMEDIATED  

---

## 📋 执行摘要 | Executive Summary

在对仓库进行安全审查时发现，**两个 Cloudflare R2 账户标识符被意外提交到了 git 历史中**。虽然这不是直接的 API 密钥或秘密令牌，但这些账户 ID 可以唯一标识您的 R2 存储实例，可能被用于账户追踪或反向工程。

**发现的敏感信息**:
1. R2 公开域名: `https://pub-REDACTED.r2.dev`
2. R2 账户 ID: `REDACTED`

---

## 🔍 详细发现 | Detailed Findings

### 发现1: README.md 中的真实 R2 账户标识符

**位置**: `README.md` 第 ~115 行  
**受影响的提交**:
- `421946e` (Sat Mar 14 22:30:09 - "测试R2下载功能")
- `73eadf2` (Sun Mar 15 00:21:46 - "放弃直接采用R2缓存") 

**原文**:
```markdown
- `EHENTAI_R2_ENDPOINT`：R2 终结点 URL（例如 `https://REDACTED.r2.cloudflarestorage.com`）
```

**风险等级**: ⚠️ **中等**
- 账户 ID `REDACTED` 是您的 Cloudflare 账户标识符
- 虽然这不是密钥，但可用于账户信息收集或反向查询

### 发现2: config.py 中的 R2 公开域名

**位置**: `src/nonebot_plugin_ehentai/config.py` 
**受影响的提交**:
- `421946e` (初始 R2 配置)
- `73eadf2` (修改为另一个域名)

**原文**:
```python
ehentai_r2_public_domain: str = "https://pub-REDACTED.r2.dev"
```

**风险等级**: ⚠️ **中等**
- 这是您的 R2CDN 的真实公开域名
- 包含的 `pub-7fd565e067674e5ea...` 部分是您的 R2 账户的唯一标识符

---

## ✅ 已采取的行动 | Actions Taken

### 立即行动

1. **✅ 源代码清理** (已完成)
   - 在 README.md 中用占位符替换了真实的账户 ID
   - 用 `{ACCOUNT_ID}` 和 `{CUSTOM_DOMAIN}` 等通用占位符
   - 提交: `eb18aa8` ("docs: redact sensitive Cloudflare R2 account identifiers")

2. **✅ 安全文档增强** (已完成)
   - 添加了 `SECURITY.md` 指南
   - 添加了 `.gitignore` 敏感文件模式

### 待处理: Git 历史清理

❌ **待完成** - Git 历史中仍然存在敏感信息

虽然工作目录已清理，但以下提交仍包含敏感账户 ID:
- `421946e`: 测试R2下载功能
- `73eadf2`: 放弃直接采用R2缓存  

**重写 git 历史的难度级别**: 高 (多个相互依赖的提交)

---

## 🚀 建议的补救方案 | Recommended Remediation

### 短期 (立即)

- ✅ **已验证**: 当前工作目录中没有敏感信息
- ✅ **已验证**: 所有新提交都使用占位符
- ✅ **已完成**: 源代码和文档已清理

### 中期 (本周)

**如果这是公开仓库**:

```bash
# 方案1: 完全重建历史 (高风险，需要所有合作者同步)
# - 使用 git filter-repo 重写整个历史
# - 强制推送到所有分支
# - 通知所有下游使用者

# 方案2: 归档旧仓库并创建新仓库 (推荐对公开仓库)
# - 根据当前HEAD创建新的干净仓库
# - 将所有敏感ID替换为占位符
# - 更新CI/CD和依赖引用
```

**如果这是私有仓库**:

```bash
# 方案3: 使用 git filter-repo 安全重写历史
pip install git-filter-repo
git filter-repo --replace-text <(echo 'pub-REDACTED==>pub-REDACTED
REDACTED==>REDACTED') --force
git push --force-with-lease --all
```

### 长期 (后续)

1. **启用 secret scanning**:
   - GitHub: 启用 Secret Scanning
   - GitLab: 启用 Secret Detection

2. **使用 pre-commit hooks**:
   ```yaml
   # .pre-commit-config.yaml
   repos:
     - repo: https://github.com/gitleaks/gitleaks
       rev: v8.18.2
       hooks:
         - id: gitleaks
   ```

3. **定期审查**:
   - 每月检查一次新的敏感模式
   - 运行 `git log -p | grep -i "token\|secret\|key"`

---

## 🔐 凭证轮换 | Credential Rotation

由于您的 R2 账户 ID 已暴露，建议：

### Cloudflare R2

- [ ] **访问您的 Cloudflare Dashboard**
- [ ] **查看 R2 API 令牌**:
  - 检查是否有未授权的活动
  - 验证所有 API 令牌的范围

- [ ] **检查存储桶访问日志**（如果启用）:
  - 查看是否有可疑的访问模式
  - 检查是否有未在账户中的IP地址访问

- [ ] **如果有疑虑**（可选）:
  - 轮换所有 R2 API 令牌
  - 更新仓库配置中的凭证

### 一般最佳实践

- ✅ **立即**: 停止使用硬编码的账户 ID 在示例代码中
- ✅ **今天**: 审查谁有权访问这个仓库
- ✅ **本周**: 审查 R2 访问日志
- ✅ **继续**: 遵循安全编码实践

---

## 📊 事件时间线 | Timeline

| 日期 | 事件 |
|------|------|
| 2026-03-14 22:30 | 提交 `421946e` - 首次引入 R2 配置（包含真实账户ID） |
| 2026-03-15 00:21 | 提交 `73eadf2` - 修改 R2 公开域名 |
| 2026-03-15 18:42 | 提交 `75b1aa9` - 安全强化和仓库清理 |
| 2026-03-15 *发现* | **发现敏感账户ID泄露** |
| 2026-03-15 *修复* | **清理源代码中的敏感信息** |
| 2026-03-15 更新 | 提交 `eb18aa8` - 撤销敏感信息 |

---

## 🎯 检查清单 | Checklist

### 当前状态

- [x] 已识别泄露的账户ID
- [x] 已清理当前工作目录
- [x] 已为新提交设置保护措施
- [x] 已创建安全指南和文档
- [ ] 已从 git 历史完全删除账户ID
  - *备注*: 需要操作者确认是否要重写历史
- [ ] 已通知所有合作者
- [ ] 已评估 Cloudflare R2 访问日志

### 建议的后续步骤

- [ ] 选择 git 历史重写方案（见上文）
- [ ] 执行凭证轮换程序（如适用）
- [ ] 在团队中推行安全审代实践
- [ ] 实施自动化密钥检测工具

---

## 📚 参考资源 | References

- [GitHub Secret Scanning](https://docs.github.com/en/code-security/secret-scanning)
- [GitLabs Secret Detection](https://docs.gitlab.com/ee/user/application_security/secret_detection/)
- [Cloudflare R2 Security](https://developers.cloudflare.com/r2/security/)
- [OWASP: Secrets Management](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html)
- [git-filter-repo Documentation](https://github.com/newren/git-filter-repo)

---

## 📞 后续支持 | Follow-up

如需帮助执行 git 历史重写或进一步的安全审查，请参考：
- `SECURITY.md` - 安全配置指南
- `SECURITY_AUDIT_REPORT.md` - 完整的安全审计报告

---

**报告作者**: GitHub Copilot 安全助手  
**分类**: 内部安全报告  
**机密级别**: 仅限团队  
**下一次审查**: 2026-06-15
