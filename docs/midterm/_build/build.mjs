// 把 docs/midterm 的 A～D Markdown 排版成 A4 PDF 與 Word 檔（封面、目錄、頁碼）。
// 用法：node docs/midterm/_build/build.mjs [--only A] [--shots <資料夾>]
// 需求：Node 22 以上、本機安裝 Chrome 或 Edge、可連網（從 CDN 載入 marked、mermaid、paged.js、docx）。
//
// 使用案例圖與泳道圖：原始碼放在 figures/src/<名稱>.usecase 或 .swimlane，
// Markdown 以 ![說明](figures/<名稱>.png) 引用。PDF 內直接排入向量圖，
// 同時重新產生 figures/<名稱>.png，供 GitHub、VS Code 預覽與轉 Word 時顯示。
//
// Word 檔（docx/）由 docx-writer.js 組成，圖是從排版好的頁面擷取的 PNG，與 PDF 相同。
// 目錄是 Word 欄位，開檔時 Word 會詢問是否更新，選「是」即可產生目錄頁碼。

import { spawn } from 'node:child_process';
import { existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(HERE, '..');
const HTML_DIR = join(HERE, 'html');
const PDF_DIR = join(ROOT, 'pdf');
const DOCX_DIR = join(ROOT, 'docx');
const FIG_DIR = join(ROOT, 'figures');
const FIG_SRC_DIR = join(FIG_DIR, 'src');
const FIG_KINDS = ['usecase', 'swimlane'];

const args = process.argv.slice(2);
const argValue = (name) => {
  const i = args.indexOf(name);
  return i >= 0 ? args[i + 1] : undefined;
};
const only = argValue('--only');
const shotsDir = argValue('--shots');

const BROWSERS = [
  process.env.CHROME_PATH,
  'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
  'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe',
  '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
  '/usr/bin/google-chrome',
].filter(Boolean);

const CSS = String.raw`
:root { --body-font: "Times New Roman", "DFKai-SB", "標楷體", "BiauKai", "Microsoft JhengHei", serif; }
@page { size: A4; margin: 2.4cm 2.2cm 2.4cm 2.2cm; }
@page cover { margin: 2.4cm 2.2cm; }
html, body { margin: 0; padding: 0; background: #fff; color: #000; }
body { font-family: var(--body-font); font-size: 12pt; line-height: 1.65; }
#stage { width: 16.6cm; }
.cover { page: cover; text-align: center; break-after: page; }
.cover .school { font-size: 26pt; font-weight: bold; margin-top: .4cm; letter-spacing: .1em; }
.cover .school-en { font-size: 15pt; margin-top: .3cm; }
.cover .dept { font-size: 20pt; font-weight: bold; margin-top: .9cm; }
.cover .course { font-size: 18pt; margin-top: .7cm; }
.cover .title { font-size: 30pt; font-weight: bold; margin-top: 1.9cm; letter-spacing: .08em; }
.cover .title-en { font-size: 18pt; margin-top: .4cm; }
.cover .info { display: inline-block; text-align: left; margin-top: 1.9cm; font-size: 15pt; line-height: 1.9; }
.cover .info .row { display: flex; }
.cover .info .label { width: 5.2em; text-align: justify; text-align-last: justify; margin-right: .4em; }
.cover .date { font-size: 15pt; margin-top: 1.2cm; }
.toc { page: toc; break-after: page; }
.toc h1.toc-title { text-align: center; font-size: 18pt; margin: 0 0 .6cm; }
.toc .entry { display: flex; align-items: baseline; font-size: 12pt; line-height: 1.9; }
.toc .entry .text { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.toc .entry .dots { flex: 1; border-bottom: 1.5px dotted #000; margin: 0 .3em; transform: translateY(-.3em); min-width: 1em; }
.toc .entry .num { min-width: 1.6em; text-align: right; }
.toc .l1 { font-weight: bold; margin-top: .25em; }
.toc .l2 { padding-left: 2em; }
.toc .l3 { padding-left: 4em; }
.content h1 { break-before: page; text-align: center; font-size: 18pt; margin: 0 0 .6cm; }
.content h2 { font-size: 14pt; margin: .9em 0 .4em; break-after: avoid; }
.content h3 { font-size: 12.5pt; margin: .8em 0 .3em; break-after: avoid; }
.content h4 { font-size: 12pt; margin: .6em 0 .3em; break-after: avoid; }
.content p { margin: .3em 0; text-indent: 2em; text-align: justify; }
.content li > p, .content td p { text-indent: 0; }
.content ul, .content ol { margin: .2em 0 .4em; padding-left: 2.2em; }
.content li { margin: .1em 0; }
.content table { width: 100%; border-collapse: collapse; margin: .5em 0 .8em; font-size: 10.5pt; line-height: 1.45; }
.content th, .content td { border: 1px solid #000; padding: 3px 6px; vertical-align: top; }
.content th { background: #e8e8e8; font-weight: bold; text-align: center; }
.content tr { break-inside: avoid; }
.content code { font-family: Consolas, "Courier New", monospace; font-size: .88em; }
.content strong { font-weight: bold; }
.figure { text-align: center; margin: .6em 0 .8em; break-inside: avoid; }
#render-box, .figure { font-family: "Microsoft JhengHei", "微軟正黑體", sans-serif; font-size: 16px; line-height: 1.5; text-indent: 0; }
#render-box p, .content .figure p { margin: 0; text-indent: 0; text-align: center; }
.figure svg { display: inline-block; }
.figure.error { border: 2px solid #c00; color: #c00; padding: .5em; text-align: left; font-size: 10pt; white-space: pre-wrap; }
.page-footer { position: absolute; left: 0; right: 0; bottom: 1.1cm; text-align: center; font-size: 10pt; font-family: var(--body-font); }
.pagedjs_page { position: relative; }
#render-box { position: absolute; left: -10000px; top: 0; width: 16.6cm; }
`;

// 找出 Markdown 引用的 figures/<名稱>.png 中，有原始碼的使用案例圖與泳道圖
function figuresFor(markdown) {
  const figures = {};
  for (const [, name] of markdown.matchAll(/\]\(figures\/([\w.-]+)\.png\)/g)) {
    const kind = FIG_KINDS.find((k) => existsSync(join(FIG_SRC_DIR, `${name}.${k}`)));
    if (!kind) throw new Error(`找不到圖的原始碼：figures/src/${name}.usecase 或 .swimlane`);
    figures[name] = { kind, src: readFileSync(join(FIG_SRC_DIR, `${name}.${kind}`), 'utf8') };
  }
  return figures;
}

function htmlFor(meta, doc, markdown, figures) {
  const data = JSON.stringify({ meta, doc, markdown, figures }).replace(/</g, '\\u003c');
  return `<!doctype html>
<html lang="zh-Hant">
<head>
<meta charset="utf-8">
<title>${doc.title}</title>
<link rel="stylesheet" data-pagedjs-ignore href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.2/css/all.min.css">
<style>${CSS}</style>
<script>window.PagedConfig = { auto: false };</script>
<script src="https://cdn.jsdelivr.net/npm/marked@12.0.2/marked.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/mermaid@11.4.1/dist/mermaid.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/pagedjs@0.4.3/dist/paged.polyfill.js"></script>
<script src="../swimlane.js"></script>
<script src="../usecase.js"></script>
<script src="../docx-writer.js"></script>
</head>
<body>
<div id="render-box"></div>
<div id="stage"></div>
<script>
window.__DATA__ = ${data};
window.__ERRORS__ = [];
window.__FIGURE_PNGS__ = {};
window.__DONE__ = false;
const xhrOpen = XMLHttpRequest.prototype.open;
XMLHttpRequest.prototype.open = function (method, url) { this.__url = url; return xhrOpen.apply(this, arguments); };
const describe = (err) => (err && err.target) ? ('事件 ' + err.type + '，來源 ' + (err.target.constructor && err.target.constructor.name) + ' ' + (err.target.__url || err.target.responseURL || err.target.src || err.target.href || '')) : (err && err.stack ? err.stack : String(err));
(async () => {
  const { meta, doc, markdown, figures } = window.__DATA__;
  const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  try {
    // 1. Markdown 轉 HTML
    const content = document.createElement('section');
    content.className = 'content';
    // 圖檔引用先改成 data 屬性，避免瀏覽器去載入尚未排版的 PNG
    content.innerHTML = marked.parse(markdown, { gfm: true, breaks: true }).replace(/<img src="(figures\\/[^"]+)"/g, '<img data-figure="$1"');

    // 短欄位（如「實體」「PK」）不斷行，避免被擠成直排
    content.querySelectorAll('td, th').forEach((c) => { if (c.textContent.trim().length <= 6) c.style.whiteSpace = 'nowrap'; });

    // 2. 標題編號，供目錄定位
    const heads = [...content.querySelectorAll('h1, h2, h3')];
    heads.forEach((h, i) => { h.id = 'h' + i; });

    // 3. 繪製 Mermaid 圖
    await document.fonts.ready;
    try { await document.fonts.load('900 16px "Font Awesome 6 Free"'); } catch (e) {}
    mermaid.initialize({
      startOnLoad: false,
      securityLevel: 'loose',
      theme: 'neutral',
      fontFamily: '"Microsoft JhengHei", "微軟正黑體", sans-serif',
      themeVariables: {
        fontFamily: '"Microsoft JhengHei", "微軟正黑體", sans-serif', fontSize: '16px',
        taskBkgColor: '#cfe2f3', taskBorderColor: '#3d6fa5', taskTextColor: '#000', taskTextDarkColor: '#000', taskTextLightColor: '#000', taskTextOutsideColor: '#000', taskTextClickableColor: '#000',
        doneTaskBkgColor: '#e6e6e6', doneTaskBorderColor: '#8c8c8c', activeTaskBkgColor: '#fde9c9', activeTaskBorderColor: '#c58a2b',
        sectionBkgColor: '#f5f5f5', altSectionBkgColor: '#ffffff', sectionBkgColor2: '#f5f5f5', gridColor: '#e0e0e0', todayLineColor: 'transparent',
      },
      flowchart: { htmlLabels: true, useMaxWidth: false, padding: 10 },
      sequence: { useMaxWidth: false, mirrorActors: false, wrap: false, width: 110, actorMargin: 30, boxMargin: 8, messageMargin: 32, actorFontSize: 15, messageFontSize: 15, noteFontSize: 15, actorFontFamily: '"Microsoft JhengHei"', messageFontFamily: '"Microsoft JhengHei"', noteFontFamily: '"Microsoft JhengHei"' },
      class: { useMaxWidth: false },
      state: { useMaxWidth: false },
      er: { useMaxWidth: false, fontSize: 14 },
      gantt: { useMaxWidth: false, fontSize: 12, sectionFontSize: 13, barHeight: 18, barGap: 5, topPadding: 40, leftPadding: 150, gridLineStartPadding: 30 },
    });
    const box = document.getElementById('render-box');
    const maxW = box.getBoundingClientRect().width;
    const maxH = 22 * 37.795;
    // 等比縮小到版心內；縮得太小時提出警告
    const fit = (el, label) => {
      const vb = (el.getAttribute('viewBox') || '').split(/[\\s,]+/).map(Number);
      const w = vb[2] || parseFloat(el.getAttribute('width')) || maxW;
      const h = vb[3] || parseFloat(el.getAttribute('height')) || 300;
      const scale = Math.min(1, maxW / w, maxH / h);
      el.removeAttribute('style');
      el.setAttribute('width', Math.round(w * scale));
      el.setAttribute('height', Math.round(h * scale));
      if (scale < 0.62) window.__ERRORS__.push('WARN ' + label + ' 縮放 ' + scale.toFixed(2));
    };
    // 每張圖以 data-key 標記，Word 檔依此對應到同一張圖
    // 泳道圖：自訂語法，直接產生 SVG
    for (const [i, code] of [...content.querySelectorAll('pre > code.language-swimlane')].entries()) {
      const fig = document.createElement('div');
      fig.className = 'figure';
      fig.dataset.key = 'swimlane-' + i;
      try {
        fig.innerHTML = window.renderSwimlane(code.textContent, Math.floor(maxW));
        fit(fig.querySelector('svg'), '泳道圖');
      } catch (err) {
        fig.classList.add('error');
        fig.textContent = '泳道圖錯誤：' + err.message;
        window.__ERRORS__.push('ERROR 泳道圖：' + err.message);
      }
      code.parentElement.replaceWith(fig);
    }
    // 使用案例圖：自訂語法，直接產生 SVG
    for (const [i, code] of [...content.querySelectorAll('pre > code.language-usecase')].entries()) {
      const fig = document.createElement('div');
      fig.className = 'figure';
      fig.dataset.key = 'usecase-' + i;
      try {
        fig.innerHTML = window.renderUseCase(code.textContent, Math.floor(maxW));
        fit(fig.querySelector('svg'), '使用案例圖');
      } catch (err) {
        fig.classList.add('error');
        fig.textContent = '使用案例圖錯誤：' + err.message;
        window.__ERRORS__.push('ERROR 使用案例圖：' + err.message);
      }
      code.parentElement.replaceWith(fig);
    }
    // 以圖檔引用的使用案例圖與泳道圖：PDF 排入向量圖，並另存 PNG 給 Markdown 預覽使用
    const toPng = async (svg) => {
      const vb = svg.match(/viewBox="0 0 ([\\d.]+) ([\\d.]+)"/);
      const w = Number(vb[1]);
      const h = Number(vb[2]);
      const img = new Image();
      img.src = 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(svg);
      await img.decode();
      const canvas = document.createElement('canvas');
      canvas.width = Math.round(w * 2);
      canvas.height = Math.round(h * 2);
      const g = canvas.getContext('2d');
      g.fillStyle = '#ffffff';
      g.fillRect(0, 0, canvas.width, canvas.height);
      g.drawImage(img, 0, 0, canvas.width, canvas.height);
      return canvas.toDataURL('image/png');
    };
    for (const img of [...content.querySelectorAll('img[data-figure]')]) {
      const m = img.getAttribute('data-figure').match(/^figures\\/([\\w.-]+)\\.png$/);
      if (!m || !figures[m[1]]) continue;
      const { kind, src } = figures[m[1]];
      const label = kind === 'usecase' ? '使用案例圖' : '泳道圖';
      const fig = document.createElement('div');
      fig.className = 'figure';
      fig.dataset.key = 'img-' + m[1];
      try {
        const svg = kind === 'usecase' ? window.renderUseCase(src, Math.floor(maxW)) : window.renderSwimlane(src, Math.floor(maxW));
        window.__FIGURE_PNGS__[m[1]] = await toPng(svg);
        fig.innerHTML = svg;
        fit(fig.querySelector('svg'), label + ' ' + m[1]);
      } catch (err) {
        fig.classList.add('error');
        fig.textContent = label + '錯誤（' + m[1] + '）：' + err.message;
        window.__ERRORS__.push('ERROR ' + label + ' ' + m[1] + '：' + err.message);
      }
      const p = img.parentElement;
      (p.tagName === 'P' && p.childElementCount === 1 && !p.textContent.trim() ? p : img).replaceWith(fig);
    }
    const blocks = [...content.querySelectorAll('pre > code.language-mermaid')];
    for (let i = 0; i < blocks.length; i++) {
      const code = blocks[i].textContent;
      const fig = document.createElement('div');
      fig.className = 'figure';
      fig.dataset.key = 'mermaid-' + i;
      try {
        const { svg } = await mermaid.render('mmd' + i, code, box);
        fig.innerHTML = svg;
        fit(fig.querySelector('svg'), '圖 #' + (i + 1) + '（' + code.split('\\n')[0] + '）');
      } catch (err) {
        fig.classList.add('error');
        fig.textContent = 'Mermaid 錯誤（圖 #' + (i + 1) + '）：' + (err && err.message ? err.message : err);
        window.__ERRORS__.push('ERROR 圖 #' + (i + 1) + '：' + (err && err.message ? err.message : err));
      }
      blocks[i].parentElement.replaceWith(fig);
      box.innerHTML = '';
    }

    // 4. 封面與目錄
    const members = meta.members.map((m, i) =>
      '<div class="row"><span class="label">' + (i === 0 ? '組 員' : '') + '</span><span>' + (i === 0 ? '：' : '　') + esc(m) + '</span></div>').join('');
    const cover = '<section class="cover">' +
      '<div class="school">' + esc(meta.school) + '</div>' +
      '<div class="school-en">' + esc(meta.school_en) + '</div>' +
      '<div class="dept">' + esc(meta.department) + '</div>' +
      '<div class="course">' + esc(meta.course) + '</div>' +
      '<div class="title">' + esc(doc.title) + '</div>' +
      '<div class="title-en">' + esc(doc.title_en) + '</div>' +
      '<div class="info">' +
        '<div class="row"><span class="label">題 目</span><span>：' + esc(meta.project) + '</span></div>' +
        '<div class="row"><span class="label">授課教授</span><span>：' + esc(meta.advisor) + '</span></div>' +
        '<div class="row"><span class="label">組 長</span><span>：' + esc(meta.leader) + '</span></div>' +
        members +
      '</div>' +
      '<div class="date">' + esc(meta.date) + '</div>' +
      '</section>';
    const toc = '<section class="toc"><h1 class="toc-title">目錄</h1>' + heads.map((h) =>
      '<div class="entry l' + h.tagName[1] + '"><span class="text">' + esc(h.textContent) + '</span><span class="dots"></span><span class="num" data-for="' + h.id + '"></span></div>').join('') + '</section>';

    const stage = document.getElementById('stage');
    stage.innerHTML = cover + toc;
    stage.appendChild(content);

    // 5. 分頁
    // 先移出頁面：Paged.js 會把文件中所有 style 元素當成樣式表處理，SVG 內的 style 會讓它出錯
    const html = stage.innerHTML;
    stage.remove();
    box.remove();
    await window.PagedPolyfill.preview(html, undefined, document.body);

    // 6. 頁碼（內文從第 1 頁起算，封面與目錄不編頁碼）與目錄頁碼
    const pages = [...document.querySelectorAll('.pagedjs_page')];
    const firstH1 = document.getElementById('h0');
    const firstContent = firstH1 ? pages.indexOf(firstH1.closest('.pagedjs_page')) : 0;
    const total = pages.length - firstContent;
    pages.forEach((p, i) => {
      if (i < firstContent) return;
      const f = document.createElement('div');
      f.className = 'page-footer';
      f.textContent = '第 ' + (i - firstContent + 1) + ' 頁，共 ' + total + ' 頁';
      p.appendChild(f);
    });
    document.querySelectorAll('.toc .num').forEach((n) => {
      const target = document.getElementById(n.dataset.for);
      const page = target && target.closest('.pagedjs_page');
      if (page) n.textContent = String(pages.indexOf(page) - firstContent + 1);
    });
    window.__PAGES__ = pages.length;
  } catch (err) {
    window.__ERRORS__.push('ERROR 排版失敗：' + describe(err));
  }
  window.__DONE__ = true;
})();
</script>
</body>
</html>`;
}

function findBrowser() {
  const found = BROWSERS.find((p) => existsSync(p));
  if (!found) throw new Error('找不到 Chrome 或 Edge，請以 CHROME_PATH 指定瀏覽器路徑');
  return found;
}

async function launch() {
  const userDir = mkdtempSync(join(tmpdir(), 'midterm-pdf-'));
  const proc = spawn(findBrowser(), [
    '--headless=new', '--disable-gpu', '--no-first-run', '--no-default-browser-check',
    '--remote-debugging-port=0', `--user-data-dir=${userDir}`, 'about:blank',
  ], { stdio: 'ignore' });
  const portFile = join(userDir, 'DevToolsActivePort');
  for (let i = 0; i < 100 && !existsSync(portFile); i++) await new Promise((r) => setTimeout(r, 100));
  const [port, path] = readFileSync(portFile, 'utf8').trim().split('\n');
  const ws = new WebSocket(`ws://127.0.0.1:${port}${path}`);
  await new Promise((res, rej) => { ws.onopen = res; ws.onerror = rej; });
  let seq = 0;
  const pending = new Map();
  const listeners = [];
  ws.onmessage = (ev) => {
    const msg = JSON.parse(ev.data);
    if (msg.id && pending.has(msg.id)) {
      const { resolve: ok, reject: fail } = pending.get(msg.id);
      pending.delete(msg.id);
      msg.error ? fail(new Error(JSON.stringify(msg.error))) : ok(msg.result);
    } else if (msg.method) {
      listeners.forEach((fn) => fn(msg));
    }
  };
  const send = (method, params = {}, sessionId) => new Promise((ok, fail) => {
    const id = ++seq;
    pending.set(id, { resolve: ok, reject: fail });
    ws.send(JSON.stringify({ id, method, params, sessionId }));
  });
  const close = () => {
    try { ws.close(); } catch {}
    proc.kill();
    setTimeout(() => { try { rmSync(userDir, { recursive: true, force: true }); } catch {} }, 1500);
  };
  return { send, listeners, close };
}

async function renderDoc(cdp, htmlPath, pdfPath, docxPath, label) {
  const { targetId } = await cdp.send('Target.createTarget', { url: 'about:blank' });
  const { sessionId } = await cdp.send('Target.attachToTarget', { targetId, flatten: true });
  const s = (m, p) => cdp.send(m, p, sessionId);
  const consoleErrors = [];
  const onEvent = (msg) => {
    if (msg.sessionId !== sessionId) return;
    if (msg.method === 'Runtime.exceptionThrown') consoleErrors.push(msg.params.exceptionDetails.text + ' ' + (msg.params.exceptionDetails.exception?.description || ''));
    if (msg.method === 'Runtime.consoleAPICalled' && msg.params.type === 'error') consoleErrors.push(msg.params.args.map((a) => a.value ?? a.description).join(' '));
    if (msg.method === 'Network.requestWillBeSent') requests.set(msg.params.requestId, msg.params.request.url);
    if (msg.method === 'Network.loadingFailed') consoleErrors.push('無法載入 ' + (requests.get(msg.params.requestId) || '?') + '：' + msg.params.errorText);
  };
  const requests = new Map();
  cdp.listeners.push(onEvent);
  await s('Page.enable');
  await s('Runtime.enable');
  await s('Network.enable');
  await s('Emulation.setDeviceMetricsOverride', { width: 1000, height: 1400, deviceScaleFactor: 1, mobile: false });
  await s('Page.navigate', { url: pathToFileURL(htmlPath).href });
  const started = Date.now();
  let done = false;
  while (!done && Date.now() - started < 180000) {
    await new Promise((r) => setTimeout(r, 500));
    const r = await s('Runtime.evaluate', { expression: 'window.__DONE__ === true', returnByValue: true });
    done = r.result.value === true;
  }
  if (!done) {
    const r = await s('Runtime.evaluate', { expression: 'JSON.stringify(window.__ERRORS__ || [])', returnByValue: true });
    throw new Error(`${label}：排版逾時\n  ${[...JSON.parse(r.result.value || '[]'), ...consoleErrors].join('\n  ')}`);
  }
  const info = await s('Runtime.evaluate', { expression: 'JSON.stringify({ errors: window.__ERRORS__, pages: window.__PAGES__, figures: window.__FIGURE_PNGS__ })', returnByValue: true });
  const { errors, pages, figures } = JSON.parse(info.result.value);
  for (const [name, dataUrl] of Object.entries(figures)) {
    writeFileSync(join(FIG_DIR, `${name}.png`), Buffer.from(dataUrl.split(',')[1], 'base64'));
  }
  const pdf = await s('Page.printToPDF', { printBackground: true, preferCSSPageSize: true, displayHeaderFooter: false });
  writeFileSync(pdfPath, Buffer.from(pdf.data, 'base64'));

  if (shotsDir) {
    mkdirSync(shotsDir, { recursive: true });
    const rects = await s('Runtime.evaluate', {
      expression: 'JSON.stringify([...document.querySelectorAll(".pagedjs_page")].map(p => { const r = p.getBoundingClientRect(); return { x: r.left + scrollX, y: r.top + scrollY, w: r.width, h: r.height }; }))',
      returnByValue: true,
    });
    const list = JSON.parse(rects.result.value);
    for (let i = 0; i < list.length; i++) {
      const { x, y, w, h } = list[i];
      const shot = await s('Page.captureScreenshot', { format: 'png', captureBeyondViewport: true, clip: { x, y, width: w, height: h, scale: 1 } });
      writeFileSync(join(shotsDir, `${label}-p${String(i + 1).padStart(2, '0')}.png`), Buffer.from(shot.data, 'base64'));
    }
  }
  let docxError;
  try {
    await writeDocx(s, docxPath);
  } catch (err) {
    docxError = err.message;
  }
  cdp.listeners.splice(cdp.listeners.indexOf(onEvent), 1);
  await cdp.send('Target.closeTarget', { targetId });
  return { errors, pages, consoleErrors, figureCount: Object.keys(figures).length, docxError };
}

// Word 檔：以 2 倍解析度擷取排版好的每張圖，交給頁面中的 docx-writer.js 組成文件
async function writeDocx(s, docxPath) {
  await s('Emulation.setDeviceMetricsOverride', { width: 1000, height: 1400, deviceScaleFactor: 2, mobile: false });
  const r = await s('Runtime.evaluate', {
    expression: 'JSON.stringify([...document.querySelectorAll(".figure[data-key]")].map(f => { const g = f.querySelector("svg"); if (!g) return null; const b = g.getBoundingClientRect(); return { key: f.dataset.key, x: b.left + scrollX, y: b.top + scrollY, w: b.width, h: b.height }; }).filter(Boolean))',
    returnByValue: true,
  });
  const images = {};
  for (const { key, x, y, w, h } of JSON.parse(r.result.value)) {
    if (images[key]) continue;
    const shot = await s('Page.captureScreenshot', { format: 'png', captureBeyondViewport: true, clip: { x, y, width: w, height: h, scale: 1 } });
    images[key] = { data: shot.data, w: Math.round(w), h: Math.round(h) };
  }
  const out = await s('Runtime.evaluate', { expression: `window.buildDocx(${JSON.stringify(images)})`, awaitPromise: true, returnByValue: true });
  if (out.exceptionDetails) throw new Error(out.exceptionDetails.exception?.description || out.exceptionDetails.text);
  writeFileSync(docxPath, Buffer.from(out.result.value, 'base64'));
}

const meta = JSON.parse(readFileSync(join(ROOT, 'meta.json'), 'utf8'));
mkdirSync(HTML_DIR, { recursive: true });
mkdirSync(PDF_DIR, { recursive: true });
mkdirSync(DOCX_DIR, { recursive: true });
mkdirSync(FIG_DIR, { recursive: true });
const cdp = await launch();
let failed = false;
try {
  for (const doc of meta.docs) {
    const label = doc.file[0];
    if (only && !only.split(',').includes(label)) continue;
    const markdown = readFileSync(join(ROOT, doc.file), 'utf8');
    const base = doc.file.replace(/\.md$/, '');
    const htmlPath = join(HTML_DIR, `${base}.html`);
    writeFileSync(htmlPath, htmlFor(meta, doc, markdown, figuresFor(markdown)));
    const outName = `${base}-軟工期中${meta.group ? '-' + meta.group : ''}`;
    const { errors, pages, consoleErrors, figureCount, docxError } = await renderDoc(cdp, htmlPath, join(PDF_DIR, `${outName}.pdf`), join(DOCX_DIR, `${outName}.docx`), label);
    console.log(`${label}：${outName}.pdf（${pages ?? '?'} 頁，含封面與目錄）${docxError ? '' : '、.docx'}${figureCount ? `，更新 ${figureCount} 張圖檔` : ''}`);
    if (docxError) { console.log('  ERROR Word 檔：' + docxError); failed = true; }
    for (const e of errors) { console.log('  ' + e); if (e.startsWith('ERROR')) failed = true; }
    for (const e of consoleErrors) console.log('  console: ' + e);
  }
} finally {
  cdp.close();
}
process.exitCode = failed ? 1 : 0;
