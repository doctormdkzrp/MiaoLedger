"""首页落地页：给家里人看的、也用来发安装包的静态页。

一个函数、一段 HTML，没有外部依赖、不引模板引擎——页面小、加载快，
放在 ECS 上被手机打开时基本秒开（3Mbps 的机器也不心疼）。

设计上的取舍：
- 页面不放任何接口细节（版本号、路径、错误信息都不露），只给「装 App」一件事；
- 自动挑 /apk 目录里最新那个 .apk 当下载链接，以后换包不用改代码；
- 服务状态用一次 fetch 打 /health，失败就显示「稍后再试」，不报错给人看。
"""
from __future__ import annotations

import os
from pathlib import Path

_DEFAULT_APK = "haoli-1.1.0-debug.apk"


def latest_apk_name() -> str:
    """取 APK 目录里最新的那个安装包；目录空或不存在就返回默认名。"""
    d = Path(os.getenv("APK_DIR", "/apk"))
    try:
        files = [p for p in d.glob("*.apk") if p.is_file()]
    except OSError:
        return _DEFAULT_APK
    if not files:
        return _DEFAULT_APK
    newest = max(files, key=lambda p: p.stat().st_mtime)
    return newest.name


def render(apk_name: str | None = None) -> str:
    apk = apk_name or latest_apk_name()
    return _HTML.replace("{{APK}}", apk)


_HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="theme-color" content="#fbf7f1">
<title>小喵记账 · 家里的账</title>
<style>
  :root {
    --bg: #fbf7f1;
    --card: #ffffff;
    --ink: #3a342e;
    --muted: #8b8177;
    --line: #efe7dc;
    --accent: #e0803c;
    --accent-soft: #fdf1e6;
    --ok: #4c9a6a;
  }
  * { box-sizing: border-box; -webkit-tap-highlight-color: transparent; }
  body {
    margin: 0;
    padding: 32px 20px 48px;
    background: radial-gradient(120% 80% at 50% 0%, #fff8ef 0%, var(--bg) 55%, #f7f1e8 100%);
    color: var(--ink);
    font-family: -apple-system, BlinkMacSystemFont, "PingFang SC", "Hiragino Sans GB",
                 "Microsoft YaHei", "Helvetica Neue", Arial, sans-serif;
    line-height: 1.65;
    min-height: 100vh;
  }
  .wrap { max-width: 460px; margin: 0 auto; }
  .card {
    background: var(--card);
    border: 1px solid var(--line);
    border-radius: 20px;
    padding: 28px 22px 24px;
    box-shadow: 0 10px 30px -18px rgba(120, 90, 60, .35);
  }
  .title { display: flex; align-items: center; gap: 10px; margin: 0 0 6px; }
  .title h1 { font-size: 22px; margin: 0; letter-spacing: .5px; font-weight: 650; }
  .paw { font-size: 22px; }
  .lead { margin: 0 0 22px; color: var(--muted); font-size: 14.5px; }
  .btn {
    display: block; width: 100%; text-align: center; text-decoration: none;
    background: var(--accent); color: #fff; font-size: 16.5px; font-weight: 600;
    padding: 15px 16px; border-radius: 14px;
    box-shadow: 0 8px 18px -10px rgba(224, 128, 60, .9);
    transition: transform .12s ease, box-shadow .12s ease;
  }
  .btn:active { transform: translateY(1px); box-shadow: 0 4px 10px -8px rgba(224,128,60,.9); }
  .btn-sub { display:block; text-align:center; margin-top: 10px; font-size: 12.5px; color: var(--muted); }
  .steps { margin: 24px 0 0; padding: 0; list-style: none; }
  .steps li {
    display: flex; gap: 12px; align-items: flex-start;
    padding: 12px 0; border-top: 1px dashed var(--line); font-size: 14px;
  }
  .steps li:first-child { border-top: 0; }
  .num {
    flex: 0 0 24px; height: 24px; border-radius: 50%;
    background: var(--accent-soft); color: var(--accent);
    font-size: 12.5px; font-weight: 700;
    display: flex; align-items: center; justify-content: center;
  }
  code {
    background: #f6f1e9; border: 1px solid var(--line); border-radius: 8px;
    padding: 2px 7px; font-size: 13px; word-break: break-all;
    font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    color: #6b5c4b;
  }
  .status {
    display: flex; align-items: center; gap: 8px; justify-content: center;
    margin-top: 22px; font-size: 13px; color: var(--muted);
  }
  .dot { width: 8px; height: 8px; border-radius: 50%; background: #c9c0b4; }
  .dot.ok { background: var(--ok); box-shadow: 0 0 0 4px rgba(76,154,106,.12); }
  .foot { margin-top: 20px; text-align: center; font-size: 12px; color: #b0a597; }
  .seal { text-align: center; margin: 18px 0 26px; font-size: 13px; color: var(--muted); }
</style>
</head>
<body>
  <div class="wrap">
    <div class="seal">🏠 家里那本账，两个人一起记</div>

    <div class="card">
      <div class="title"><span class="paw">🐾</span><h1>小喵记账</h1></div>
      <p class="lead">张嘴说一句「买菜三十八」，它就替你记好。<br>账只存自己手机和自家服务器上，不交给别人。</p>

      <a class="btn" href="/apk/{{APK}}" download>下载安卓版</a>
      <span class="btn-sub">点一下从自家服务器直接下载，不经过应用商店</span>

      <ul class="steps">
        <li><span class="num">1</span><div>下载后按提示安装。手机若提示「未知来源」，允许一次即可。</div></li>
        <li><span class="num">2</span><div>打开 App，服务器地址填<br><code>https://jz.doctormdkzrp.cn</code></div></li>
        <li><span class="num">3</span><div>用张汝沛给你的<b>邀请码</b>注册，再设一个 6 位数字密码，就完事了。</div></li>
      </ul>

      <div class="status"><span class="dot" id="dot"></span><span id="st">正在看一眼服务…</span></div>
    </div>

    <p class="foot">自家服务器 · 账本不上云 · 想换手机时喊一声就能整个搬走</p>
  </div>

<script>
  fetch('/health', {cache: 'no-store'})
    .then(function (r) { return r.ok ? r.json() : Promise.reject(); })
    .then(function () {
      document.getElementById('dot').className = 'dot ok';
      document.getElementById('st').textContent = '服务正常，随时可以记一笔';
    })
    .catch(function () {
      document.getElementById('st').textContent = '服务这会儿有点忙，稍后再试一次';
    });
</script>
</body>
</html>
"""
