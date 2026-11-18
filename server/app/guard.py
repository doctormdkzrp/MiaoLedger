"""轻量防护：单 IP 请求频率限制 + 请求体大小上限。

为什么自己做而不装 WAF：这套是个人服务，前面没有 CDN，扫描器和爬虫会直接打到
uvicorn 上。这里挡的是「刷」和「扫」——被刷满 CPU/带宽导致服务不可用，才是这台
2 核 2G 的小机器最现实的风险（不是被人拿下）。

规则（都能用环境变量改，默认值按生产取）：
- RATE_LIMIT_PER_MIN（默认 120）：每分钟每 IP 的请求数上限，超了返回 429；
  取 0 关掉限流（测试环境用）。
- MAX_BODY_BYTES（默认 12MB）：请求体上限，超了直接 413。语音片段几百 KB，
  12MB 足够，挡住那种拿大 body 灌流量的。
- TRUST_PROXY（默认 0）：只有在前面加了 CDN/反代（ESA、Nginx）时才设 1，
  这时才读 X-Forwarded-For 取真实客户端 IP。直连部署下绝不能开，否则
  任何人都能伪造 XFF 绕过限流。
- /health 与 /apk/ 不计入限流（探活与装包）。

内存滑动窗口，按 IP 分桶；IP 桶超过 2 万个时整体清空一次，避免被海量源 IP 撑爆内存。
"""
from __future__ import annotations

import os
import time
from collections import deque

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

WINDOW_SECONDS = 60.0
MAX_BUCKETS = 20000


def _limit() -> int:
    try:
        return int(os.getenv("RATE_LIMIT_PER_MIN", "120"))
    except ValueError:
        return 120


def _max_body() -> int:
    try:
        return int(os.getenv("MAX_BODY_BYTES", str(12 * 1024 * 1024)))
    except ValueError:
        return 12 * 1024 * 1024


class GuardMiddleware(BaseHTTPMiddleware):
    def __init__(self, app):
        super().__init__(app)
        self._hits: dict[str, deque] = {}

    async def dispatch(self, request, call_next):
        path = request.url.path
        if path == "/health" or path.startswith("/apk/"):
            return await call_next(request)

        # 1) 请求体上限
        raw_len = request.headers.get("content-length", "")
        if raw_len.isdigit() and int(raw_len) > _max_body():
            return JSONResponse({"detail": "请求体太大"}, status_code=413)

        # 2) 频率限制
        limit = _limit()
        if limit > 0:
            ip = request.client.host if request.client else "unknown"
            if os.getenv("TRUST_PROXY", "0") == "1":
                xff = request.headers.get("x-forwarded-for", "")
                if xff:
                    ip = xff.split(",")[0].strip() or ip
            now = time.monotonic()
            q = self._hits.get(ip)
            if q is None:
                if len(self._hits) >= MAX_BUCKETS:
                    self._hits.clear()
                q = self._hits[ip] = deque()
            while q and now - q[0] > WINDOW_SECONDS:
                q.popleft()
            if len(q) >= limit:
                retry = int(WINDOW_SECONDS - (now - q[0])) + 1
                return JSONResponse(
                    {"detail": "请求太频繁，稍后再试"},
                    status_code=429,
                    headers={"Retry-After": str(retry)},
                )
            q.append(now)

        return await call_next(request)
