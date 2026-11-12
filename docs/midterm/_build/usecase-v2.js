// 把 ```usecase 區塊畫成 UML 使用案例圖（SVG）。
// 這是使用案例修訂版（B-軟體需求分析文件-使用案例修訂版.md）專用的版本，由 build-v2.mjs 載入；
// 比 usecase.js 多了整體圖的功能群框語法，且關聯線接到橢圓朝向參與者的那一端。審核通過後可取代 usecase.js。
//
// 語法：
//   system: 1.0 帳號與身分                 系統邊界標題
//   actor visitor left 1.5: 訪客            參與者：代號 left|right 列號: 名稱（列號可為小數）
//   uc u1 1 1: 註冊並驗證 Email              使用案例：代號 欄(1|2) 列: 名稱
//   visitor -- u1                           關聯（可加 : 標籤）
//   u2 ..> u1 : extend                      «include»／«extend» 虛線箭頭
//
// 整體圖用的語法（把各功能群畫成系統邊界內的框）：
//   width: 760                              圖寬（未指定時使用版面寬度；較寬的圖排版時會等比縮小）
//   rowheight: 40                           每列高度（預設 58）
//   package p7 0.03 0.48 1 6: 7.0 觀賽與通知  功能群框：代號（可省略）、左右位置（佔邊界寬度的比例 0～1）、起訖列: 標題
//   visitor -- p7                           參與者連到功能群框：線接到框朝向參與者的那一邊
//   uc u1 at 0.255 2: 7.1 瀏覽賽事            使用案例自由放置：at 橫向位置（佔邊界寬度的比例） 列
(function () {
  const FONT = '"Microsoft JhengHei", "微軟正黑體", sans-serif';
  const FS = 13;
  const TOP = 40;
  const ACTOR_W = 92;
  const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const ctx = document.createElement('canvas').getContext('2d');
  ctx.font = FS + 'px ' + FONT;
  const measure = (t) => ctx.measureText(t).width;

  function wrap(text, width) {
    if (measure(text) <= width) return [text];
    const out = [];
    let line = '';
    for (const ch of text) {
      if (line && measure(line + ch) > width) { out.push(line); line = ''; }
      line += ch;
    }
    out.push(line);
    return out;
  }

  function parse(src) {
    const d = { title: '', width: 0, row: 58, packages: [], actors: [], ucs: [], links: [] };
    for (const raw of src.split('\n')) {
      const line = raw.trim();
      if (!line || line.startsWith('%%')) continue;
      let m;
      if ((m = line.match(/^system\s*:\s*(.+)$/))) d.title = m[1];
      else if ((m = line.match(/^actor\s+(\w+)\s+(left|right)\s+([\d.]+)\s*:\s*(.+)$/))) d.actors.push({ id: m[1], side: m[2], row: Number(m[3]), name: m[4] });
      else if ((m = line.match(/^width\s*:\s*(\d+)$/))) d.width = Number(m[1]);
      else if ((m = line.match(/^rowheight\s*:\s*(\d+)$/))) d.row = Number(m[1]);
      else if ((m = line.match(/^package\s+(?:([A-Za-z_]\w*)\s+)?([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s*:\s*(.+)$/))) d.packages.push({ id: m[1], x0: Number(m[2]), x1: Number(m[3]), r0: Number(m[4]), r1: Number(m[5]), name: m[6] });
      else if ((m = line.match(/^uc\s+(\w+)\s+([12])\s+([\d.]+)\s*:\s*(.+)$/))) d.ucs.push({ id: m[1], col: Number(m[2]), row: Number(m[3]), name: m[4] });
      else if ((m = line.match(/^uc\s+(\w+)\s+at\s+([\d.]+)\s+([\d.]+)\s*:\s*(.+)$/))) d.ucs.push({ id: m[1], fx: Number(m[2]), row: Number(m[3]), name: m[4] });
      else if ((m = line.match(/^(\w+)\s*(--|\.\.>)\s*(\w+)(?:\s*:\s*(.+))?$/))) d.links.push({ from: m[1], to: m[3], kind: m[2], label: m[4] || '' });
      else throw new Error('使用案例圖無法解析這一行：' + line);
    }
    return d;
  }

  // 從橢圓中心朝 (px, py) 的方向，求橢圓邊上的點
  function onEllipse(e, px, py) {
    const dx = px - e.cx;
    const dy = py - e.cy;
    const k = 1 / Math.sqrt((dx * dx) / (e.rx * e.rx) + (dy * dy) / (e.ry * e.ry));
    return [e.cx + dx * k, e.cy + dy * k];
  }

  function render(src, pageW) {
    const d = parse(src);
    const W = d.width || pageW;
    const ROW = d.row;
    const hasRight = d.actors.some((a) => a.side === 'right');
    const bx1 = ACTOR_W;
    const bx2 = hasRight ? W - ACTOR_W : W - 8;
    const colX = { 1: bx1 + (bx2 - bx1) * 0.27, 2: bx1 + (bx2 - bx1) * 0.73 };
    const maxText = d.packages.length ? Math.min(...d.packages.map((k) => (k.x1 - k.x0) * (bx2 - bx1))) - 40 : (bx2 - bx1) / 2 - 40;
    const rows = d.ucs.map((u) => u.row).concat(d.actors.map((a) => a.row), d.packages.map((k) => k.r1));
    const lastRow = Math.max(...rows);
    const rowY = (r) => TOP + (r - 0.5) * ROW;
    const H = rowY(lastRow) + ROW / 2 + 14;
    const byId = {};
    for (const u of d.ucs) {
      u.lines = wrap(u.name, maxText);
      const tw = Math.max(...u.lines.map(measure));
      u.cx = u.fx !== undefined ? bx1 + (bx2 - bx1) * u.fx : colX[u.col];
      u.cy = rowY(u.row);
      u.rx = Math.max(62, tw / 2 + 22);
      u.ry = u.lines.length > 1 ? 25 : Math.min(19, ROW / 2 - 3);
      byId[u.id] = u;
    }
    for (const a of d.actors) {
      a.x = a.side === 'left' ? ACTOR_W / 2 : W - ACTOR_W / 2;
      a.y = rowY(a.row) - 8;
      byId[a.id] = a;
    }

    const p = [];
    p.push('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ' + W + ' ' + H + '" width="' + W + '" height="' + H + '" font-family=\'' + FONT + '\' font-size="' + FS + '">');
    p.push('<defs><marker id="uc-open" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" markerHeight="8" orient="auto"><path d="M0,0 L10,5 L0,10" fill="none" stroke="#333" stroke-width="1.4"/></marker></defs>');
    p.push('<rect x="' + bx1 + '" y="6" width="' + (bx2 - bx1) + '" height="' + (H - 12) + '" fill="#fafafa" stroke="#444" stroke-width="1.2"/>');
    p.push('<text x="' + (bx1 + bx2) / 2 + '" y="26" text-anchor="middle" font-weight="bold" font-size="14">' + esc(d.title) + '</text>');
    for (const k of d.packages) {
      const x = bx1 + (bx2 - bx1) * k.x0;
      const y = rowY(k.r0) - ROW / 2;
      const w = (bx2 - bx1) * (k.x1 - k.x0);
      const h = rowY(k.r1) - rowY(k.r0) + ROW;
      Object.assign(k, { px: x, py: y, pw: w, ph: h, isPackage: true });
      if (k.id) byId[k.id] = k;
      // 依功能群編號上色（1.0 藍、2.0 綠、3.0 黃、4.0 橘、5.0 紫、6.0 紅、7.0 青）
      const PALETTE = [['#e4eefa', '#6b9bd1'], ['#e5f3e3', '#6aa864'], ['#fcf2d4', '#cfa22e'], ['#fde6d2', '#df8a3e'], ['#eee5f6', '#9a70bf'], ['#fae3e3', '#d26b6b'], ['#def2ef', '#4ba398']];
      const ci = (parseInt(k.name, 10) || 1) - 1;
      const [fill, stroke] = PALETTE[ci % PALETTE.length];
      p.push('<rect x="' + x + '" y="' + y + '" width="' + w + '" height="' + h + '" rx="12" fill="' + fill + '" stroke="' + stroke + '" stroke-width="1.4"/>');
      p.push('<text x="' + (x + w / 2) + '" y="' + (y + ROW / 2 + 5) + '" text-anchor="middle" font-weight="bold">' + esc(k.name) + '</text>');
    }

    for (const l of d.links) {
      const a = byId[l.from];
      const b = byId[l.to];
      if (!a || !b) throw new Error('使用案例圖的連線端點不存在：' + l.from + ' → ' + l.to);
      if (l.kind === '--' && (a.isPackage || b.isPackage)) {
        const actor = a.isPackage ? b : a;
        const k = a.isPackage ? a : b;
        const ax = actor.x + (actor.side === 'left' ? 14 : -14);
        const ay = actor.y + 6;
        // 接到框朝向參與者的那一邊；參與者在框的高度範圍內時畫成水平線
        const ex = actor.side === 'left' ? k.px : k.px + k.pw;
        const ey = Math.max(k.py + 14, Math.min(k.py + k.ph - 14, ay));
        p.push('<line x1="' + ax + '" y1="' + ay + '" x2="' + ex + '" y2="' + ey + '" stroke="#333" stroke-width="1.2"/>');
      } else if (l.kind === '--') {
        const actor = a.rx ? b : a;
        const uc = a.rx ? a : b;
        const ax = actor.x + (actor.side === 'left' ? 14 : -14);
        const ay = actor.y + 6;
        // 連到橢圓朝向參與者的那一端，避免斜線穿過同一欄的其他使用案例
        const ex = uc.cx + (ax > uc.cx ? uc.rx : -uc.rx);
        const ey = uc.cy;
        p.push('<line x1="' + ax + '" y1="' + ay + '" x2="' + ex + '" y2="' + ey + '" stroke="#333" stroke-width="1.2"/>');
        if (l.label) p.push('<text x="' + (ax + ex) / 2 + '" y="' + ((ay + ey) / 2 - 4) + '" font-size="11.5" text-anchor="middle" paint-order="stroke" stroke="#fff" stroke-width="3">' + esc(l.label) + '</text>');
      } else {
        const [sx, sy] = onEllipse(a, b.cx, b.cy);
        const [tx, ty] = onEllipse(b, a.cx, a.cy);
        p.push('<line x1="' + sx + '" y1="' + sy + '" x2="' + tx + '" y2="' + ty + '" stroke="#333" stroke-width="1.2" stroke-dasharray="5,4" marker-end="url(#uc-open)"/>');
        const label = '«' + (l.label || 'include') + '»';
        // 標籤沿箭頭的法線方向推開，距離剛好讓文字框不碰到線（水平線放上方、垂直線放右側；與 usecase.js 相同）
        const dx = tx - sx;
        const dy = ty - sy;
        const len = Math.hypot(dx, dy) || 1;
        let nx = -dy / len;
        let ny = dx / len;
        if (ny > 0.001 || (Math.abs(ny) <= 0.001 && nx < 0)) { nx = -nx; ny = -ny; }
        const lw = measure(label) * (11.5 / FS);
        const lh = 12;
        const off = Math.abs(nx) * lw / 2 + Math.abs(ny) * lh / 2 + 3;
        const lx = (sx + tx) / 2 + nx * off;
        const ly = (sy + ty) / 2 + ny * off + 4;
        p.push('<text x="' + lx + '" y="' + ly + '" font-size="11.5" text-anchor="middle" paint-order="stroke" stroke="#fafafa" stroke-width="4">' + esc(label) + '</text>');
      }
    }

    for (const u of d.ucs) {
      p.push('<ellipse cx="' + u.cx + '" cy="' + u.cy + '" rx="' + u.rx + '" ry="' + u.ry + '" fill="#ffffff" stroke="#444" stroke-width="1.2"/>');
      const y0 = u.cy - (u.lines.length - 1) * 8.5 + 4.5;
      u.lines.forEach((t, i) => p.push('<text x="' + u.cx + '" y="' + (y0 + i * 17) + '" text-anchor="middle">' + esc(t) + '</text>'));
    }

    for (const a of d.actors) {
      const { x, y } = a;
      p.push('<g stroke="#222" stroke-width="1.6" fill="none">' +
        '<circle cx="' + x + '" cy="' + (y - 16) + '" r="7" fill="#fff"/>' +
        '<line x1="' + x + '" y1="' + (y - 9) + '" x2="' + x + '" y2="' + (y + 10) + '"/>' +
        '<line x1="' + (x - 12) + '" y1="' + (y - 3) + '" x2="' + (x + 12) + '" y2="' + (y - 3) + '"/>' +
        '<line x1="' + x + '" y1="' + (y + 10) + '" x2="' + (x - 9) + '" y2="' + (y + 24) + '"/>' +
        '<line x1="' + x + '" y1="' + (y + 10) + '" x2="' + (x + 9) + '" y2="' + (y + 24) + '"/></g>');
      p.push('<text x="' + x + '" y="' + (y + 40) + '" text-anchor="middle">' + esc(a.name) + '</text>');
    }
    p.push('</svg>');
    return p.join('');
  }

  window.renderUseCase = render;
})();
