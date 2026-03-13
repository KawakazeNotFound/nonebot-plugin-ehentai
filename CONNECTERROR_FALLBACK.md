# ConnectError 自动 Fallback 机制

## 问题

在沙特阿拉伯 Ubuntu 部署时，直连 IP 模式可能遇到 `httpx.ConnectError`：

```
httpx.ConnectError
下载函数出错
```

这表示：IP 级别的完全阻止（不只是 DNS 污染）

## 解决方案

已添加 **自动 Fallback 机制**，当直连 IP 失败时：

### 工作流程

```
搜索/下载/获取归档链接
  ↓
[尝试] 直连 IP 模式
  │
  ├─ 成功 → 返回结果 ✓
  │
  └─ 连接错误 (ConnectError/SSLError/TimeoutError)
      ↓
      [自动切换] 到标准 DNS 模式
      ↓
      [重试] 使用正常 DNS 查询
      ↓
      ├─ 成功 → 返回结果 ✓
      └─ 失败 → 报错 ✗
```

### 检测的错误类型

- `httpx.ConnectError` - 连接被拒绝/重置
- `httpx.SSLError` - SSL 握手失败
- `TimeoutError` - 连接超时
- `OSError` - 底层网络错误

### 代码位置

**src/nonebot_plugin_ehentai/service.py**

#### 新增方法：`_is_connect_error()`

```python
@staticmethod
def _is_connect_error(error: Exception) -> bool:
    """检测是否是连接错误（应该 fallback 到标准 DNS）"""
    from httpx import ConnectError as HttpxConnectError
    if isinstance(error, (HttpxConnectError, httpx.SSLError, TimeoutError)):
        return True
    if isinstance(error, OSError) and "Connection" in str(error):
        return True
    return False
```

#### 修改的方法

1. **`search()`** - 搜索时自动 fallback
2. **`resolve_archive_url()`** - 获取归档链接时自动 fallback
3. **`download_file()`** - 下载时自动 fallback

### 关键特性

✅ **自动切换** - 用户无需手动配置  
✅ **临时降级** - 仅当前操作降级，不影响之后的请求  
✅ **日志输出** - 记录 fallback 事件以便调试  
✅ **单次重试** - 降级后自动重试一次  
✅ **向前兼容** - 对现有代码无影响

### 日志输出示例

```
[WARNING] 直连 IP 下载失败，自动降级到标准 DNS 模式: httpx.ConnectError
[INFO] 使用标准 DNS 重试下载...
[INFO] 下载完成
```

## 部署说明

### 无需修改配置

直连 IP 模式仍是默认启用：
```bash
EHENTAI_ENABLE_DIRECT_IP=true
```

自动 fallback 对用户完全透明。

### 调试模式

查看 fallback 事件：
```bash
# 在 Ubuntu 服务器
journalctl -u nonebot -f --grep="直连 IP"
```

## 场景分析

### 场景 1：DNS 污染（有效）
```
搜索 e-hentai.org
  → 直连 IP 104.20.18.168 ✓
  → 返回搜索结果
```

### 场景 2：IP 级别阻止（现在可处理）
```
搜索 e-hentai.org
  → 直连 IP 104.20.18.168 → ConnectError ✗
  → 自动 fallback 到 DNS 查询
  → DNS 查询 e-hentai.org → 获得真实 IP
  → 连接被 ISP 阻止 ✗✗✗
  → 显示错误信息
```

**此场景需要代理/VPN**

### 场景 3：Cloudflare SSL 问题（现在可处理）
```
搜索 e-hentai.org
  → 直连 IP 104.20.18.168 + Host 头
  → SSL 握手失败 (SSLError) ✗
  → 自动 fallback 到标准方式
  → 标准 HTTPS 连接 ✓
  → 返回搜索结果
```

## 与现有机制的兼容

- **QUIC TLS 1.3 降级** - 独立的机制，不冲突
- **SSL/Connection 错误降级** - 在 fallback 后执行
- **curry_cffi 后端** - 优先级更高，不受影响
- **消息重试** - 在 NoneBot 层面，不受影响

## 后续改进方向

### 短期
- ✓ 已实现 ConnectError 自动 fallback
- ✓ 已实现日志记录

### 中期计划
- [ ] IP 列表动态更新（定期检测活跃 IP）
- [ ] DNS-over-HTTPS 作为第三备选
- [ ] 代理链路集成

### 长期计划
- [ ] ML 推荐最快 IP 路线
- [ ] 区域检测和自动策略选择

## 测试

使用已有的 `/search` 和 `/download` 命令：

```bash
# 测试搜索
/search [keyword]

# 测试下载（需要 Cookie）
/download [keyword]
```

若看到日志中有 "自动降级到标准 DNS 模式"，说明 fallback 机制正在工作。
