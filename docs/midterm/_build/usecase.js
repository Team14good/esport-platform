// 把 ```usecase 區塊畫成 UML 使用案例圖（SVG）。
//
// 語法：
//   system: 1.0 帳號與身分                 系統邊界標題
//   actor visitor left 1.5: 訪客            參與者：代號 left|right 列號: 名稱（列號可為小數）
//   uc u1 1 1: 註冊並驗證 Email              使用案例：代號 欄(1|2) 列: 名稱
//   visitor -- u1                           關聯（可加 : 標籤）
//   u2 ..> u1 : extend                      «include»／«extend» 虛線箭頭
(function () {
  const FONT = '"Microsoft JhengHei", "微軟正黑體", sans-serif';
  const FS = 13;
  const ROW = 58;
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
    const d = { title: '', actors: [], ucs: [], links: [] };
    for (const raw of src.split('\n')) {
      const line = raw.trim();
      if (!line || line.startsWith('%%')) continue;
      let m;
      if ((m = line.match(/^system\s*:\s*(.+)$/))) d.title = m[1];
      else if ((m = line.match(/^actor\s+(\w+)\s+(left|right)\s+([\d.]+)\s*:\s*(.+)$/))) d.actors.push({ id: m[1], side: m[2], row: Number(m[3]), name: m[4] });
      else if ((m = line.match(/^uc\s+(\w+)\s+([12])\s+([\d.]+)\s*:\s*(.+)$/))) d.ucs.push({ id: m[1], col: Number(m[2]), row: Number(m[3]), name: m[4] });
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

  function render(src, W) {
    const d = parse(src);
    const hasRight = d.actors.some((a) => a.side === 'right');
    const bx1 = ACTOR_W;
    const bx2 = hasRight ? W - ACTOR_W : W - 8;
    const colX = { 1: bx1 + (bx2 - bx1) * 0.27, 2: bx1 + (bx2 - bx1) * 0.73 };
    const maxText = (bx2 - bx1) / 2 - 40;
    const rows = d.ucs.map((u) => u.row).concat(d.actors.map((a) => a.row));
    const lastRow = Math.max(...rows);
    const rowY = (r) => TOP + (r - 0.5) * ROW;
    const H = rowY(lastRow) + ROW / 2 + 14;
    const byId = {};
    for (const u of d.ucs) {
      u.lines = wrap(u.name, maxText);
      const tw = Math.max(...u.lines.map(measure));
      u.cx = colX[u.col];
      u.cy = rowY(u.row);
      u.rx = Math.max(62, tw / 2 + 22);
      u.ry = u.lines.length > 1 ? 25 : 19;
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

    for (const l of d.links) {
      const a = byId[l.from];
      const b = byId[l.to];
      if (!a || !b) throw new Error('使用案例圖的連線端點不存在：' + l.from + ' → ' + l.to);
      if (l.kind === '--') {
        const actor = a.rx ? b : a;
        const uc = a.rx ? a : b;
        const ax = actor.x + (actor.side === 'left' ? 14 : -14);
        const ay = actor.y + 6;
        const [ex, ey] = onEllipse(uc, ax, ay);
        p.push('<line x1="' + ax + '" y1="' + ay + '" x2="' + ex + '" y2="' + ey + '" stroke="#333" stroke-width="1.2"/>');
        if (l.label) p.push('<text x="' + (ax + ex) / 2 + '" y="' + ((ay + ey) / 2 - 4) + '" font-size="11.5" text-anchor="middle" paint-order="stroke" stroke="#fff" stroke-width="3">' + esc(l.label) + '</text>');
      } else {
        const [sx, sy] = onEllipse(a, b.cx, b.cy);
        const [tx, ty] = onEllipse(b, a.cx, a.cy);
        p.push('<line x1="' + sx + '" y1="' + sy + '" x2="' + tx + '" y2="' + ty + '" stroke="#333" stroke-width="1.2" stroke-dasharray="5,4" marker-end="url(#uc-open)"/>');
        const label = '«' + (l.label || 'include') + '»';
        p.push('<text x="' + (sx + tx) / 2 + '" y="' + ((sy + ty) / 2 - 5) + '" font-size="11.5" text-anchor="middle" paint-order="stroke" stroke="#fafafa" stroke-width="4">' + esc(label) + '</text>');
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
