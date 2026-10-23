// 把 ```swimlane 區塊畫成直向泳道圖（SVG）。
//
// 語法：
//   lanes: 主辦方 | 平台管理員 | 系統
//   o1 主辦方 1: 申請成為主辦方          步驟：代號 泳道 列號: 文字（<br> 可換行）
//   s0 系統 2?: 兩隊都報到？              列號後加 ? 表示判斷（菱形）
//   o1 -> a1                              實線箭頭
//   s0 -> r1 : 是                         箭頭加標籤
//   c3 ..> s4                             虛線箭頭
(function () {
  const FONT = '"Microsoft JhengHei", "微軟正黑體", sans-serif';
  const FS = 13;
  const LINE = 17;
  const HEADER = 34;
  const GAP = 22;
  const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const ctx = document.createElement('canvas').getContext('2d');
  ctx.font = FS + 'px ' + FONT;

  function wrap(text, width) {
    const out = [];
    for (const part of text.split(/<br\s*\/?>/i)) {
      let line = '';
      for (const ch of part) {
        if (line && ctx.measureText(line + ch).width > width) { out.push(line); line = ''; }
        line += ch;
      }
      out.push(line);
    }
    return out;
  }

  function parse(src) {
    const lanes = [];
    const steps = [];
    const edges = [];
    for (const raw of src.split('\n')) {
      const line = raw.trim();
      if (!line || line.startsWith('%%')) continue;
      let m;
      if ((m = line.match(/^lanes\s*:\s*(.+)$/))) {
        lanes.push(...m[1].split('|').map((x) => x.trim()));
      } else if ((m = line.match(/^(\w+)\s*(->|\.\.>)\s*(\w+)(?:\s*:\s*(.+))?$/))) {
        edges.push({ from: m[1], to: m[3], dashed: m[2] === '..>', label: m[4] || '' });
      } else if ((m = line.match(/^(\w+)\s+(\S+)\s+(\d+)(\?)?\s*:\s*(.+)$/))) {
        steps.push({ id: m[1], lane: m[2], row: Number(m[3]), decision: !!m[4], text: m[5] });
      } else {
        throw new Error('泳道圖無法解析這一行：' + line);
      }
    }
    return { lanes, steps, edges };
  }

  function render(src, maxW) {
    const { lanes, steps, edges } = parse(src);
    const laneW = Math.floor(maxW / lanes.length);
    const boxW = laneW - 16;
    const byId = {};
    for (const s of steps) {
      const li = lanes.indexOf(s.lane);
      if (li < 0) throw new Error('泳道圖找不到泳道：' + s.lane);
      s.li = li;
      s.lines = wrap(s.text, s.decision ? boxW - 40 : boxW - 8);
      s.h = s.decision ? Math.max(58, s.lines.length * LINE + 30) : s.lines.length * LINE + 14;
      byId[s.id] = s;
    }
    const rows = [...new Set(steps.map((s) => s.row))].sort((a, b) => a - b);
    const rowY = {};
    let y = HEADER + GAP / 2;
    for (const r of rows) {
      const h = Math.max(...steps.filter((s) => s.row === r).map((s) => s.h));
      rowY[r] = { top: y, h };
      y += h + GAP;
    }
    const H = y - GAP / 2 + 6;
    const W = laneW * lanes.length;
    for (const s of steps) {
      s.cx = s.li * laneW + laneW / 2;
      s.cy = rowY[s.row].top + rowY[s.row].h / 2;
      s.w = boxW;
      s.top = s.cy - s.h / 2;
      s.bottom = s.cy + s.h / 2;
    }

    const parts = [];
    parts.push('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ' + W + ' ' + H + '" width="' + W + '" height="' + H + '" font-family=\'' + FONT + '\' font-size="' + FS + '">');
    parts.push('<defs><marker id="sl-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="#333"/></marker></defs>');
    lanes.forEach((name, i) => {
      const x = i * laneW;
      parts.push('<rect x="' + x + '" y="0" width="' + laneW + '" height="' + H + '" fill="' + (i % 2 ? '#ffffff' : '#f6f6f6') + '" stroke="#555" stroke-width="1"/>');
      parts.push('<rect x="' + x + '" y="0" width="' + laneW + '" height="' + HEADER + '" fill="#dcdcdc" stroke="#555" stroke-width="1"/>');
      parts.push('<text x="' + (x + laneW / 2) + '" y="' + (HEADER / 2 + 5) + '" text-anchor="middle" font-weight="bold" font-size="14">' + esc(name) + '</text>');
    });

    const blocked = (lane, fromRow, toRow) => steps.some((s) => s.li === lane && s.row > fromRow && s.row < toRow);
    for (const e of edges) {
      const a = byId[e.from];
      const b = byId[e.to];
      if (!a || !b) throw new Error('泳道圖箭頭的步驟不存在：' + e.from + ' → ' + e.to);
      let d;
      let lx;
      let ly;
      if (a.row === b.row) {
        const dir = b.cx > a.cx ? 1 : -1;
        const x1 = a.cx + dir * a.w / 2;
        const x2 = b.cx - dir * b.w / 2;
        d = 'M' + x1 + ',' + a.cy + ' H' + x2;
        lx = (x1 + x2) / 2; ly = a.cy - 5;
      } else if (b.row > a.row && !blocked(b.li, a.row, b.row) && !(a.li === b.li && blocked(a.li, a.row, b.row))) {
        const ym = a.bottom + GAP / 2;
        d = a.cx === b.cx ? 'M' + a.cx + ',' + a.bottom + ' V' + b.top : 'M' + a.cx + ',' + a.bottom + ' V' + ym + ' H' + b.cx + ' V' + b.top;
        lx = a.cx === b.cx ? a.cx + 6 : (a.cx + b.cx) / 2; ly = a.cx === b.cx ? a.bottom + 14 : ym - 4;
      } else {
        // 繞行目標泳道右側的空隙，避開中間的步驟
        const gx = b.li * laneW + laneW - 6;
        const ym = a.bottom + GAP / 2;
        const tx = b.cx + b.w / 2;
        d = 'M' + a.cx + ',' + a.bottom + ' V' + ym + ' H' + gx + ' V' + b.cy + ' H' + tx;
        lx = gx - 4; ly = ym + 14;
      }
      parts.push('<path d="' + d + '" fill="none" stroke="#333" stroke-width="1.3"' + (e.dashed ? ' stroke-dasharray="5,4"' : '') + ' marker-end="url(#sl-arrow)"/>');
      if (e.label) parts.push('<text x="' + lx + '" y="' + ly + '" font-size="12" text-anchor="' + (a.row === b.row || a.cx === b.cx ? 'start' : 'middle') + '" fill="#000" paint-order="stroke" stroke="#fff" stroke-width="3">' + esc(e.label) + '</text>');
    }

    for (const s of steps) {
      if (s.decision) {
        const hw = s.w / 2;
        const hh = s.h / 2;
        parts.push('<polygon points="' + s.cx + ',' + s.top + ' ' + (s.cx + hw) + ',' + s.cy + ' ' + s.cx + ',' + s.bottom + ' ' + (s.cx - hw) + ',' + s.cy + '" fill="#fff6dd" stroke="#555" stroke-width="1.2"/>');
      } else {
        parts.push('<rect x="' + (s.cx - s.w / 2) + '" y="' + s.top + '" width="' + s.w + '" height="' + s.h + '" rx="7" fill="#ffffff" stroke="#555" stroke-width="1.2"/>');
      }
      const startY = s.cy - (s.lines.length - 1) * LINE / 2 + 4.5;
      s.lines.forEach((t, i) => {
        parts.push('<text x="' + s.cx + '" y="' + (startY + i * LINE) + '" text-anchor="middle">' + esc(t) + '</text>');
      });
    }
    parts.push('</svg>');
    return parts.join('');
  }

  window.renderSwimlane = render;
})();
