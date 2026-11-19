"""首页落地页：独立的产品展示页（单文件、零外部依赖）。

结构：吸顶导航 / 首屏（文案 + 手机示意）/ 功能卡 / 三步上手 / 常见问题 / 页脚。
只用系统字体与内联 SVG，不拉任何外部资源；APK 链接自动取 /apk 里最新的包。
页面上不出现个人信息、邀请码与接口路径。
"""
from __future__ import annotations

import os
from pathlib import Path

_DEFAULT_APK = "haoli-1.1.0-debug.apk"


def latest_apk_name() -> str:
    d = Path(os.getenv("APK_DIR", "/apk"))
    try:
        files = [p for p in d.glob("*.apk") if p.is_file()]
    except OSError:
        return _DEFAULT_APK
    if not files:
        return _DEFAULT_APK
    return max(files, key=lambda p: p.stat().st_mtime).name


def _apk_size(name: str) -> str:
    d = Path(os.getenv("APK_DIR", "/apk"))
    try:
        mb = (d / name).stat().st_size / 1024 / 1024
    except OSError:
        return "约 19 MB"
    return f"{mb:.0f} MB"


def render(apk_name: str | None = None) -> str:
    apk = apk_name or latest_apk_name()
    return _HTML.replace("{{APK}}", apk).replace("{{SIZE}}", _apk_size(apk))


_HTML = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="theme-color" content="#fff8f1">
<meta name="description" content="小喵记账：语音录入支出的 Android 记账 App，账目保存在手机本地与自建服务器上。">
<title>小喵记账 · 语音记账 App</title>
<link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'><ellipse cx='16' cy='21' rx='8' ry='6.4' fill='%23ff7a45'/><ellipse cx='7.4' cy='12.8' rx='3.2' ry='4' fill='%23ff7a45'/><ellipse cx='13.2' cy='8.8' rx='3.2' ry='4.2' fill='%23ff7a45'/><ellipse cx='19.6' cy='8.8' rx='3.2' ry='4.2' fill='%23ff7a45'/><ellipse cx='25.4' cy='12.8' rx='3.2' ry='4' fill='%23ff7a45'/></svg>">
<style>
  :root{
    --bg:#fff8f1; --card:#ffffff;
    --ink:#2f2822; --mut:#8b7d70; --line:#f0e4d6;
    --acc:#ff7a45; --acc2:#ffb020; --mint:#2fae87; --blue:#4a90e2;
    --soft:0 18px 40px -26px rgba(150,110,70,.55);
    --r:22px;
    --sans:-apple-system,BlinkMacSystemFont,"PingFang SC","Hiragino Sans GB","Microsoft YaHei","Noto Sans SC",sans-serif;
    --mono:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;
  }
  *{box-sizing:border-box}
  html{scroll-behavior:smooth}
  body{margin:0;background:var(--bg);color:var(--ink);font-family:var(--sans);
    line-height:1.72;-webkit-font-smoothing:antialiased;overflow-x:hidden}
  .blob{position:fixed;border-radius:50%;filter:blur(90px);opacity:.5;z-index:0;pointer-events:none}
  .blob.a{width:420px;height:420px;background:#ffd9c2;top:-140px;left:-120px}
  .blob.b{width:380px;height:380px;background:#cdeee2;bottom:-160px;right:-140px;opacity:.45}
  .wrap{position:relative;z-index:2;max-width:1080px;margin:0 auto;padding:0 22px}

  header{position:sticky;top:0;z-index:30;backdrop-filter:blur(14px);
    background:linear-gradient(180deg,rgba(255,248,241,.92),rgba(255,248,241,.6));
    border-bottom:1px solid var(--line)}
  nav{display:flex;align-items:center;justify-content:space-between;height:62px}
  .brand{display:flex;align-items:center;gap:9px;text-decoration:none;color:var(--ink);font-weight:700;letter-spacing:.4px}
  .brand svg{width:26px;height:26px;fill:var(--acc)}
  .navlinks{display:flex;gap:24px;font-size:.92rem}
  .navlinks a{color:var(--mut);text-decoration:none;transition:color .2s}
  .navlinks a:hover{color:var(--acc)}
  .nav-cta{background:var(--acc);color:#fff;text-decoration:none;font-weight:600;font-size:.9rem;
    padding:9px 16px;border-radius:11px;box-shadow:0 10px 20px -12px rgba(255,122,69,.9)}

  .hero{padding:74px 0 56px;display:grid;grid-template-columns:1.06fr .94fr;gap:52px;align-items:center}
  .kicker{display:inline-flex;align-items:center;gap:8px;font-size:.82rem;color:var(--acc);
    background:#fff1e7;border:1px solid #ffdcc7;padding:5px 12px;border-radius:999px;margin-bottom:20px}
  h1{font-size:clamp(2.15rem,5.2vw,3.5rem);line-height:1.16;margin:0 0 18px;font-weight:800;letter-spacing:-.5px}
  h1 .grad{background:linear-gradient(105deg,var(--acc) 10%,var(--acc2) 90%);
    -webkit-background-clip:text;background-clip:text;-webkit-text-fill-color:transparent}
  .sub{margin:0 0 26px;color:#6b5f54;font-size:1.06rem;max-width:34em}
  .cta{display:flex;gap:12px;flex-wrap:wrap;align-items:center}
  .btn{display:inline-flex;align-items:center;gap:9px;text-decoration:none;
    padding:14px 22px;border-radius:14px;font-weight:650;font-size:1rem;transition:transform .16s,box-shadow .16s}
  .btn.p{background:var(--acc);color:#fff;box-shadow:0 16px 30px -16px rgba(255,122,69,.95)}
  .btn.p:hover{transform:translateY(-2px);box-shadow:0 22px 36px -18px rgba(255,122,69,.95)}
  .btn.g{background:#fff;color:var(--ink);border:1px solid var(--line)}
  .btn.g:hover{border-color:#ffcfae}
  .meta{display:flex;gap:16px;flex-wrap:wrap;margin-top:18px;font-size:.86rem;color:var(--mut)}
  .dot{width:8px;height:8px;border-radius:50%;background:#d5c8b9}
  .dot.ok{background:var(--mint);box-shadow:0 0 0 4px rgba(47,174,135,.14)}

  .phone-wrap{display:flex;justify-content:center;position:relative}
  .phone-wrap::before{content:"";position:absolute;width:340px;height:340px;border-radius:50%;
    background:radial-gradient(circle,#ffe0cb 0%,rgba(255,224,203,0) 68%);z-index:-1}
  .phone{width:304px;border-radius:42px;background:linear-gradient(160deg,#fff,#fff3e7);
    border:1px solid #f1dfcc;box-shadow:0 44px 80px -38px rgba(150,110,70,.65),0 0 0 7px rgba(255,255,255,.65);
    padding:16px 14px 14px;animation:float 6s ease-in-out infinite}
  @keyframes float{0%,100%{transform:translateY(0) rotate(-.4deg)}50%{transform:translateY(-10px) rotate(.4deg)}}
  .notch{width:92px;height:20px;border-radius:0 0 13px 13px;background:#f3e3d3;margin:-16px auto 10px}
  .screen{background:#fffaf4;border-radius:30px;padding:14px 14px 12px;border:1px solid #f6eadd}
  .sbar{display:flex;justify-content:space-between;font-size:.6rem;color:#bcae9f;margin-bottom:8px;letter-spacing:.5px}
  .home-bar{width:104px;height:4px;border-radius:2px;background:#ecdccb;margin:12px auto 2px}
  .screen-top{display:flex;justify-content:space-between;align-items:baseline;font-size:.78rem;color:var(--mut);margin-bottom:12px}
  .screen-top b{color:var(--ink);font-size:1.3rem;font-weight:750;letter-spacing:-.3px}
  .row{display:flex;justify-content:space-between;align-items:center;gap:10px;
    background:#fff;border:1px solid #f4e8da;border-radius:14px;padding:11px 13px;margin-bottom:10px}
  .row .l{display:flex;flex-direction:column;gap:2px}
  .row .n{font-size:.94rem;font-weight:600}
  .row .t{font-size:.72rem;color:var(--mut)}
  .row .amt{font-weight:700;font-variant-numeric:tabular-nums}
  .row .amt.in{color:var(--mint)}
  .mic{margin:14px auto 2px;width:62px;height:62px;border-radius:50%;
    background:linear-gradient(150deg,var(--acc),var(--acc2));
    display:flex;align-items:center;justify-content:center;
    box-shadow:0 14px 26px -12px rgba(255,122,69,.95)}
  .mic svg{width:26px;height:26px;fill:#fff}
  .mic-hint{text-align:center;font-size:.74rem;color:var(--mut);margin-top:8px}

  section{padding:64px 0}
  .slabel{font-size:.8rem;color:var(--acc);letter-spacing:2px;margin-bottom:8px}
  h2{font-size:clamp(1.5rem,3.2vw,2.05rem);margin:0 0 10px;font-weight:750;letter-spacing:-.3px}
  .slead{color:var(--mut);margin:0 0 34px;max-width:38em}

  .grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(268px,1fr));gap:18px}
  .card{background:var(--card);border:1px solid var(--line);border-radius:var(--r);
    padding:24px 22px;box-shadow:var(--soft);transition:transform .2s,border-color .2s}
  .card:hover{transform:translateY(-4px);border-color:#ffd9c2}
  .ico{width:42px;height:42px;border-radius:13px;display:flex;align-items:center;justify-content:center;margin-bottom:14px}
  .ico svg{width:22px;height:22px}
  .ico.a{background:#fff0e6}.ico.a svg{fill:var(--acc)}
  .ico.b{background:#e9f7f1}.ico.b svg{fill:var(--mint)}
  .ico.c{background:#eaf2fd}.ico.c svg{fill:var(--blue)}
  .ico.d{background:#fff6e0}.ico.d svg{fill:#e0a000}
  .card h3{margin:0 0 6px;font-size:1.06rem;font-weight:700}
  .card p{margin:0;color:#6f6357;font-size:.94rem}
  h1,h2,.sub,.slead,.card p,.step p,details p{text-wrap:pretty}

  .steps{display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:18px}
  .step{background:var(--card);border:1px solid var(--line);border-radius:var(--r);padding:24px 22px;box-shadow:var(--soft)}
  .step .no{width:30px;height:30px;border-radius:10px;background:#fff0e6;color:var(--acc);
    font-weight:800;font-size:.9rem;display:flex;align-items:center;justify-content:center;margin-bottom:12px}
  .step h3{margin:0 0 6px;font-size:1rem;font-weight:700}
  .step p{margin:0;color:#6f6357;font-size:.92rem}
  .url{display:inline-flex;align-items:center;gap:10px;margin-top:10px;
    background:#fff8f1;border:1px dashed #f0d8c2;border-radius:12px;padding:9px 12px;
    font-family:var(--mono);font-size:.84rem;color:#7a5c44;cursor:pointer;transition:.2s;max-width:100%}
  .url:hover{border-color:var(--acc);color:var(--acc)}
  .url svg{width:14px;height:14px;fill:currentColor;flex:0 0 auto}
  .url span{overflow-wrap:anywhere}

  details{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:18px 22px;margin-bottom:12px;box-shadow:var(--soft)}
  details summary{cursor:pointer;font-weight:650;font-size:1rem;list-style:none;
    display:flex;justify-content:space-between;align-items:center;gap:12px}
  details summary::-webkit-details-marker{display:none}
  details summary::after{content:"+";color:var(--acc);font-weight:700;font-size:1.15rem}
  details[open] summary::after{content:"–"}
  details p{margin:12px 0 0;color:#6f6357;font-size:.94rem}

  footer{padding:44px 0 60px;border-top:1px solid var(--line);margin-top:26px}
  .foot-in{display:flex;justify-content:space-between;align-items:center;gap:18px;flex-wrap:wrap;font-size:.86rem;color:var(--mut)}
  .foot-in .l{display:flex;align-items:center;gap:9px}
  .foot-in svg{width:20px;height:20px;fill:var(--acc);opacity:.8}

  @media (max-width:860px){
    .hero{grid-template-columns:1fr;gap:34px;padding-top:46px}
    .phone-wrap{order:-1}
    .phone{width:250px}
    .navlinks{display:none}
    section{padding:48px 0}
  }
  @media (prefers-reduced-motion:reduce){*{animation:none!important;transition:none!important}}
</style>
</head>
<body>
<div class="blob a"></div><div class="blob b"></div>

<header>
  <div class="wrap">
    <nav>
      <a class="brand" href="#top">
        <svg viewBox="0 0 32 32" aria-hidden="true"><ellipse cx="16" cy="21" rx="8" ry="6.4"/><ellipse cx="7.4" cy="12.8" rx="3.2" ry="4"/><ellipse cx="13.2" cy="8.8" rx="3.2" ry="4.2"/><ellipse cx="19.6" cy="8.8" rx="3.2" ry="4.2"/><ellipse cx="25.4" cy="12.8" rx="3.2" ry="4"/></svg>
        小喵记账
      </a>
      <div class="navlinks">
        <a href="#features">功能</a>
        <a href="#howto">安装</a>
        <a href="#faq">常见问题</a>
      </div>
      <a class="nav-cta" href="/apk/{{APK}}" download>下载</a>
    </nav>
  </div>
</header>

<main id="top">
  <div class="wrap">
    <div class="hero">
      <div class="copy">
        <div class="kicker"><span class="dot" id="dot"></span><span id="st">正在检查服务状态</span></div>
        <h1>按住说话，<br><span class="grad">松手记一笔账</span></h1>
        <p class="sub">按住麦克风说一句「午饭 25」，松手后 App 识别金额、分类和时间，记入当月账本。账本主库保存在手机本地，没有网络时可以继续记账，联网后上传到自建服务器。</p>
        <div class="cta">
          <a class="btn p" href="/apk/{{APK}}" download>
            <svg viewBox="0 0 24 24" width="18" height="18" fill="#fff" aria-hidden="true"><path d="M12 3v11l4-4 1.4 1.4L12 17.8 6.6 11.4 8 10l4 4V3zM5 19h14v2H5z"/></svg>
            下载安卓版 · {{SIZE}}
          </a>
          <a class="btn g" href="#features">查看功能</a>
        </div>
        <div class="meta">
          <span>MIT 协议开源</span><span>无广告</span><span>Android 8.0 及以上</span><span>账本存本地与自建服务器</span>
        </div>
      </div>

      <div class="phone-wrap" aria-hidden="true">
        <div class="phone">
          <div class="notch"></div>
          <div class="screen">
            <div class="sbar"><span>9:41</span><span>●●● ▮</span></div>
            <div class="screen-top"><span>11 月</span><b>¥ 3,286</b></div>
            <div class="row"><div class="l"><span class="n">买菜</span><span class="t">今天 18:20 · 餐饮</span></div><span class="amt">-38.00</span></div>
            <div class="row"><div class="l"><span class="n">打车</span><span class="t">今天 09:05 · 交通</span></div><span class="amt">-26.00</span></div>
            <div class="row"><div class="l"><span class="n">工资</span><span class="t">11-10 · 收入</span></div><span class="amt in">+8,200</span></div>
            <div class="mic"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 15a3 3 0 003-3V6a3 3 0 10-6 0v6a3 3 0 003 3zm5-3a5 5 0 01-10 0H5a7 7 0 006 6.9V22h2v-3.1A7 7 0 0019 12h-2z"/></svg></div>
            <div class="mic-hint">按住说话，松手识别</div>
            <div class="home-bar"></div>
          </div>
        </div>
      </div>
    </div>
  </div>

  <section id="features">
    <div class="wrap">
      <div class="slabel">功能</div>
      <h2>App 提供的功能</h2>
      <p class="slead">一共六项。图片记账、预算、账户、共享账本、多币种不在范围内。</p>
      <div class="grid">
        <div class="card">
          <div class="ico a"><svg viewBox="0 0 24 24"><path d="M12 15a3 3 0 003-3V6a3 3 0 10-6 0v6a3 3 0 003 3zm5-3a5 5 0 01-10 0H5a7 7 0 006 6.9V22h2v-3.1A7 7 0 0019 12h-2z"/></svg></div>
          <h3>语音录入</h3>
          <p>按住麦克风按钮说话，松手后识别出金额、分类和时间，生成一笔记录。识别有误的字段可以在编辑页修改。</p>
        </div>
        <div class="card">
          <div class="ico b"><svg viewBox="0 0 24 24"><path d="M3 8.5A2.5 2.5 0 015.5 6h13A2.5 2.5 0 0121 8.5v7a2.5 2.5 0 01-2.5 2.5h-13A2.5 2.5 0 013 15.5v-7z"/><path d="M3 2l18 20" stroke="#2fae87" stroke-width="1.8"/></svg></div>
          <h3>断网可用</h3>
          <p>账本主库是手机本地数据库，没有网络时可以记账。恢复网络后自动上传到服务端。</p>
        </div>
        <div class="card">
          <div class="ico c"><svg viewBox="0 0 24 24"><path d="M12 3l8 3.5v5.2c0 4.6-3.2 8.2-8 9.3-4.8-1.1-8-4.7-8-9.3V6.5L12 3z"/></svg></div>
          <h3>自托管</h3>
          <p>服务端运行在自己的云主机上，保存账目备份与账号数据。数据库是单个 SQLite 文件，可以整份复制迁移。</p>
        </div>
        <div class="card">
          <div class="ico d"><svg viewBox="0 0 24 24"><path d="M12 2l1.9 5.6L20 9.5l-4.6 3.8L16.6 20 12 16.6 7.4 20l1.2-6.7L4 9.5l6.1-1.9L12 2z"/></svg></div>
          <h3>分类学习</h3>
          <p>修改一笔记录的分类后，App 把「关键词到分类」保存为规则，同类记录优先使用新分类。备注、金额、时间的修改不生成规则。</p>
        </div>
        <div class="card">
          <div class="ico a"><svg viewBox="0 0 24 24"><path d="M4 5h16a2 2 0 012 2v8a2 2 0 01-2 2H9l-5 4v-4a2 2 0 01-2-2V7a2 2 0 012-2z"/></svg></div>
          <h3>自然语言查询</h3>
          <p>输入「这个月吃饭花了多少」，模型把这句话转换成时间、分类、账本等查询条件，金额和笔数由数据库统计，模型不读取明细。</p>
        </div>
        <div class="card">
          <div class="ico b"><svg viewBox="0 0 24 24"><path d="M3 7h18v11a2 2 0 01-2 2H5a2 2 0 01-2-2V7z"/><path d="M7 3h10v3H7z" /></svg></div>
          <h3>部署要求</h3>
          <p>服务端在 2 核 2G 规格的云主机上运行，数据库为 SQLite。每天 03:00 自动备份到对象存储，保留 30 天。</p>
        </div>
      </div>
    </div>
  </section>

  <section id="howto">
    <div class="wrap">
      <div class="slabel">安装</div>
      <h2>三步完成安装</h2>
      <p class="slead">安装包由本站直接下载，不经过应用商店。</p>
      <div class="steps">
        <div class="step">
          <div class="no">1</div>
          <h3>下载安装包</h3>
          <p>点页面顶部或首屏的下载按钮。系统提示「未知来源应用」时选择允许，然后安装。</p>
        </div>
        <div class="step">
          <div class="no">2</div>
          <h3>填写服务器地址</h3>
          <p>App 打开后的第一屏是登录页，第一栏为「服务器地址」。点下面这行复制，粘贴到该栏。</p>
          <div class="url" id="copy-url" title="点击复制">
            <svg viewBox="0 0 24 24"><path d="M9 3h9a2 2 0 012 2v9h-2V5H9V3zM5 7h9a2 2 0 012 2v10a2 2 0 01-2 2H5a2 2 0 01-2-2V9a2 2 0 012-2z"/></svg>
            <span id="url-text">https://jz.doctormdkzrp.cn</span>
          </div>
        </div>
        <div class="step">
          <div class="no">3</div>
          <h3>注册账号</h3>
          <p>在登录页选择注册，填写邀请码，设置 6 位数字密码。邀请码单独找管理员要。</p>
        </div>
      </div>
    </div>
  </section>

  <section id="faq">
    <div class="wrap">
      <div class="slabel">常见问题</div>
      <h2>三个常见问题</h2>
      <details>
        <summary>服务器关机时还能记账吗？</summary>
        <p>能。账本主库在手机上，服务器关机期间照常记账。服务器恢复后，未上传的记录自动补传。</p>
      </details>
      <details>
        <summary>语音识别和 AI 解析会上传什么？</summary>
        <p>只上传当次那句话。语音识别把这段音频发送到云端识别服务，AI 解析把这句文本发送到大模型服务。账本明细不参与这两次调用，也不会整库外传。</p>
      </details>
      <details>
        <summary>账目可以导出吗？</summary>
        <p>可以。App 可以把账目导出为 9 列 CSV；服务端数据库是单个 SQLite 文件，复制即可迁移。项目以 MIT 协议开源。</p>
      </details>
    </div>
  </section>
</main>

<footer>
  <div class="wrap foot-in">
    <div class="l">
      <svg viewBox="0 0 32 32" aria-hidden="true"><ellipse cx="16" cy="21" rx="8" ry="6.4"/><ellipse cx="7.4" cy="12.8" rx="3.2" ry="4"/><ellipse cx="13.2" cy="8.8" rx="3.2" ry="4.2"/><ellipse cx="19.6" cy="8.8" rx="3.2" ry="4.2"/><ellipse cx="25.4" cy="12.8" rx="3.2" ry="4"/></svg>
      小喵记账 · 自托管记账 App
    </div>
    <div>MIT 协议 · 服务端自建</div>
  </div>
</footer>

<script>
  (function () {
    fetch('/health', { cache: 'no-store' })
      .then(function (r) { return r.ok ? r.json() : Promise.reject(); })
      .then(function () {
        document.getElementById('dot').className = 'dot ok';
        document.getElementById('st').textContent = '服务正常';
      })
      .catch(function () {
        document.getElementById('st').textContent = '服务未响应';
      });

    var box = document.getElementById('copy-url');
    if (!box) return;
    box.addEventListener('click', function () {
      var span = document.getElementById('url-text');
      var text = span.textContent;
      var flash = function () {
        var old = span.textContent;
        span.textContent = '已复制';
        setTimeout(function () { span.textContent = old; }, 1200);
      };
      if (navigator.clipboard) {
        navigator.clipboard.writeText(text).then(flash, flash);
      } else {
        var ta = document.createElement('textarea');
        ta.value = text;
        document.body.appendChild(ta);
        ta.select();
        try { document.execCommand('copy'); } catch (e) {}
        document.body.removeChild(ta);
        flash();
      }
    });
  })();
</script>
</body>
</html>
"""
