// 把 Markdown 組成 Word 檔（封面、目錄、頁碼與圖），在 build.mjs 開啟的排版頁面中執行。
//
// 用法：window.buildDocx(images) 回傳 .docx 的 base64。
//   images 是 build.mjs 從排版好的頁面擷取的圖：{ 'mermaid-0': { data: PNG 的 base64, w, h }, ... }，
//   鍵值與 build.mjs 給 .figure 的 data-key 相同，所以 Word 檔中的圖與 PDF 一致。
// 版面比照 PDF：A4、邊界 2.4／2.2 cm、標楷體＋Times New Roman 12 pt；目錄是 Word 欄位，開檔時更新。
(function () {
  const DOCX_URL = 'https://unpkg.com/docx@9.5.1/dist/index.umd.cjs';
  const TEXT_WIDTH = 9412; // 版心 16.6 cm（twip）
  const FONT = { ascii: 'Times New Roman', hAnsi: 'Times New Roman', eastAsia: '標楷體', cs: 'Times New Roman' };
  const MONO = { ascii: 'Consolas', hAnsi: 'Consolas', eastAsia: '標楷體', cs: 'Consolas' };
  const BORDER = { style: 'single', size: 4, color: '000000' };
  const NO_BORDER = { style: 'none', size: 0, color: 'FFFFFF' };
  const ENTITIES = { amp: '&', lt: '<', gt: '>', quot: '"', '#39': "'", nbsp: ' ' };
  const unescape = (s) => String(s).replace(/&(amp|lt|gt|quot|#39|nbsp);/g, (m, e) => ENTITIES[e]);
  const bytes = (b64) => Uint8Array.from(atob(b64), (c) => c.charCodeAt(0));
  // 表格欄寬估算：10.5 pt 字在 Word 中約占的寬度（twip），全形字 210、英文大寫 150、其他半形 110
  const width = (s) => [...s].reduce((n, ch) => n + (ch.charCodeAt(0) >= 0x2e80 ? 210 : /[A-Z]/.test(ch) ? 150 : 110), 0);

  const loadDocx = () => window.docx ? Promise.resolve(window.docx) : new Promise((ok, fail) => {
    const s = document.createElement('script');
    s.src = DOCX_URL;
    s.onload = () => ok(window.docx);
    s.onerror = () => fail(new Error('無法載入 ' + DOCX_URL));
    document.head.appendChild(s);
  });

  window.buildDocx = async (images) => {
    const D = await loadDocx();
    const { meta, doc, markdown } = window.__DATA__;
    const A = D.AlignmentType;
    const counters = {};
    let firstHeading = true;

    // 行內元素轉成 TextRun；fmt 帶粗體、斜體、等寬、字級與超連結樣式
    function textRuns(text, fmt) {
      return unescape(text).split('\n').map((line, i) => new D.TextRun({
        text: line,
        break: i ? 1 : undefined,
        bold: fmt.bold,
        italics: fmt.italics,
        strike: fmt.strike,
        size: fmt.code ? Math.round((fmt.size || 24) * 0.88) : fmt.size,
        font: fmt.code ? MONO : undefined,
        style: fmt.link ? 'Hyperlink' : undefined,
      }));
    }
    function runs(tokens, fmt = {}) {
      const out = [];
      for (const t of tokens || []) {
        if (t.type === 'strong') out.push(...runs(t.tokens, { ...fmt, bold: true }));
        else if (t.type === 'em') out.push(...runs(t.tokens, { ...fmt, italics: true }));
        else if (t.type === 'del') out.push(...runs(t.tokens, { ...fmt, strike: true }));
        else if (t.type === 'codespan') out.push(...textRuns(t.text, { ...fmt, code: true }));
        else if (t.type === 'br' || (t.type === 'html' && /^<br\s*\/?>$/i.test(t.text.trim()))) out.push(new D.TextRun({ break: 1 }));
        else if (t.type === 'link') out.push(new D.ExternalHyperlink({ link: t.href, children: runs(t.tokens, { ...fmt, link: true }) }));
        else if (t.type === 'image') out.push(imageRun(imageKey(t)));
        else if (t.tokens) out.push(...runs(t.tokens, fmt));
        else if (t.text) out.push(...textRuns(t.text, fmt));
      }
      return out;
    }

    // 圖：置中，尺寸與 PDF 相同（CSS px，docx 以 96 dpi 換算）
    const imageKey = (t) => 'img-' + (t.href.match(/figures\/([\w.-]+)\.png$/) || [])[1];
    function imageRun(key) {
      const img = images[key];
      if (!img) return new D.TextRun({ text: '〔缺圖：' + key + '〕', color: 'C00000' });
      return new D.ImageRun({ type: 'png', data: bytes(img.data), transformation: { width: img.w, height: img.h } });
    }
    const figure = (key) => new D.Paragraph({ alignment: A.CENTER, spacing: { before: 120, after: 160, line: 240 }, children: [imageRun(key)] });

    function table(t) {
      const rows = [t.header, ...t.rows];
      const cols = t.header.length;
      const need = Array.from({ length: cols }, (_, c) => Math.max(1, ...rows.map((r) =>
        Math.max(...unescape(r[c].text).split(/<br\s*\/?>/i).map((seg) => width(seg.replace(/[`*]/g, '')))))));
      // 短欄位依內容給足寬度（不斷行），其餘寬度依內容長度（取 0.75 次方，避免最長欄位獨占）分給長欄位
      const short = need.map((n) => n <= 2200);
      const fixed = need.map((n, c) => short[c] ? n + 240 : 0);
      const fixedSum = fixed.reduce((a, b) => a + b, 0);
      const longW = need.map((n, c) => short[c] ? 0 : Math.min(n, 12600) ** 0.75);
      const longSum = longW.reduce((a, b) => a + b, 0);
      const rest = longSum ? Math.max(TEXT_WIDTH * 0.4, TEXT_WIDTH - fixedSum) : 0;
      const k = (TEXT_WIDTH - rest) / fixedSum;
      const widths = need.map((n, c) => Math.round(short[c] ? fixed[c] * k : longW[c] / longSum * rest));
      widths[cols - 1] += TEXT_WIDTH - widths.reduce((a, b) => a + b, 0);
      const align = (i, header) => header || t.align[i] === 'center' ? A.CENTER : t.align[i] === 'right' ? A.RIGHT : A.LEFT;
      return [
        new D.Table({
          width: { size: TEXT_WIDTH, type: D.WidthType.DXA },
          layout: D.TableLayoutType.FIXED,
          columnWidths: widths,
          borders: { top: BORDER, bottom: BORDER, left: BORDER, right: BORDER, insideHorizontal: BORDER, insideVertical: BORDER },
          rows: rows.map((r, ri) => new D.TableRow({
            tableHeader: ri === 0,
            cantSplit: true,
            children: r.map((cell, i) => new D.TableCell({
              width: { size: widths[i], type: D.WidthType.DXA },
              shading: ri === 0 ? { fill: 'E8E8E8', type: D.ShadingType.CLEAR, color: 'auto' } : undefined,
              margins: { top: 30, bottom: 30, left: 90, right: 90 },
              children: [new D.Paragraph({ alignment: align(i, ri === 0), spacing: { line: 280, after: 0 }, children: runs(cell.tokens, { size: 21, bold: ri === 0 }) })],
            })),
          })),
        }),
        new D.Paragraph({ spacing: { line: 240, after: 0 }, children: [] }),
      ];
    }

    // 編號清單直接寫出「1.」，每個清單各自從頭編號；項目符號用 Word 的清單格式
    function list(t, level) {
      const out = [];
      const indent = 480 * (level + 1);
      t.items.forEach((item, i) => {
        let first = true;
        // 有子清單的項目與子清單排在同一頁
        const keepNext = item.tokens.some((c) => c.type === 'list') || undefined;
        for (const c of item.tokens) {
          if (c.type === 'space') continue;
          if (c.type === 'list') { out.push(...list(c, level + 1)); continue; }
          if (c.type !== 'text' && c.type !== 'paragraph') { out.push(...blocks([c])); continue; }
          const children = runs(c.tokens || [c]);
          if (!first) out.push(new D.Paragraph({ indent: { left: indent }, keepNext, children }));
          else if (t.ordered) out.push(new D.Paragraph({
            indent: { left: indent, hanging: 480 },
            tabStops: [{ type: D.TabStopType.LEFT, position: indent }],
            keepNext,
            children: [new D.TextRun((Number(t.start) || 1) + i + '.\t'), ...children],
          }));
          else out.push(new D.Paragraph({ numbering: { reference: 'bullet', level: Math.min(level, 2) }, keepNext, children }));
          first = false;
        }
      });
      return out;
    }

    function blocks(tokens) {
      const out = [];
      for (const t of tokens) {
        if (t.type === 'heading') {
          out.push(new D.Paragraph({ heading: D.HeadingLevel['HEADING_' + Math.min(t.depth, 4)], pageBreakBefore: t.depth === 1 && !firstHeading, children: runs(t.tokens) }));
          firstHeading = false;
        } else if (t.type === 'paragraph') {
          const solo = t.tokens.filter((x) => !(x.type === 'text' && !x.text.trim()));
          if (solo.length && solo.every((x) => x.type === 'image')) solo.forEach((x) => out.push(figure(imageKey(x))));
          else out.push(new D.Paragraph({ alignment: A.JUSTIFIED, indent: { firstLine: 480 }, children: runs(t.tokens) }));
        } else if (t.type === 'list') {
          out.push(...list(t, 0));
        } else if (t.type === 'table') {
          out.push(...table(t));
        } else if (t.type === 'code' && ['mermaid', 'swimlane', 'usecase'].includes(t.lang)) {
          counters[t.lang] = (counters[t.lang] || 0) + 1;
          out.push(figure(t.lang + '-' + (counters[t.lang] - 1)));
        } else if (t.type === 'code') {
          t.text.split('\n').forEach((line) => out.push(new D.Paragraph({ spacing: { line: 240, after: 0 }, shading: { fill: 'F2F2F2', type: D.ShadingType.CLEAR, color: 'auto' }, children: [new D.TextRun({ text: line, font: MONO, size: 20 })] })));
        } else if (t.type === 'blockquote') {
          out.push(...blocks(t.tokens));
        } else if (t.type === 'hr') {
          out.push(new D.Paragraph({ border: { bottom: BORDER }, children: [] }));
        } else if (t.type !== 'space' && t.text) {
          out.push(new D.Paragraph({ children: runs([t]) }));
        }
      }
      return out;
    }

    // 封面：比照 PDF 的封面版面
    const line = (text, size, before, bold) => new D.Paragraph({ alignment: A.CENTER, spacing: { before, after: 0, line: 240 }, children: [new D.TextRun({ text, size, bold })] });
    const info = [['題目', meta.project], ['授課教授', meta.advisor], ['組長', meta.leader], ...meta.members.map((m, i) => [i ? '' : '組員', m, i > 0])];
    const cell = (children, w) => new D.TableCell({ width: { size: w, type: D.WidthType.DXA }, borders: { top: NO_BORDER, bottom: NO_BORDER, left: NO_BORDER, right: NO_BORDER }, children });
    const infoTable = new D.Table({
      alignment: A.CENTER,
      width: { size: 6600, type: D.WidthType.DXA },
      columnWidths: [1700, 4900],
      borders: { top: NO_BORDER, bottom: NO_BORDER, left: NO_BORDER, right: NO_BORDER, insideHorizontal: NO_BORDER, insideVertical: NO_BORDER },
      rows: info.map(([label, value, cont]) => new D.TableRow({ children: [
        cell([new D.Paragraph({ alignment: A.DISTRIBUTE, spacing: { line: 432, after: 0 }, children: [new D.TextRun({ text: label, size: 30 })] })], 1700),
        cell([new D.Paragraph({ spacing: { line: 432, after: 0 }, children: [new D.TextRun({ text: (cont ? '　' : '：') + value, size: 30 })] })], 4900),
      ] })),
    });
    const cover = [
      line(meta.school, 52, 220, true),
      line(meta.school_en, 30, 170),
      line(meta.department, 40, 510, true),
      line(meta.course, 36, 400),
      line(doc.title, 60, 1080, true),
      line(doc.title_en, 36, 230),
      new D.Paragraph({ spacing: { before: 1080, after: 0 }, children: [] }),
      infoTable,
      line(meta.date, 30, 680),
    ];

    const page = { size: { width: 11906, height: 16838 }, margin: { top: 1361, bottom: 1361, left: 1247, right: 1247, footer: 624 } };
    const footer = new D.Footer({ children: [new D.Paragraph({ alignment: A.CENTER, children: [new D.TextRun({ size: 20, children: ['第 ', D.PageNumber.CURRENT, ' 頁，共 ', D.PageNumber.TOTAL_PAGES_IN_SECTION, ' 頁'] })] })] });
    const heading = (size, before, after) => ({ run: { font: FONT, size, bold: true, color: '000000' }, paragraph: { spacing: { before, after }, keepNext: true, keepLines: true } });
    const h1 = heading(36, 0, 340);
    h1.paragraph.alignment = A.CENTER;

    const body = blocks(marked.lexer(markdown, { gfm: true, breaks: true }));
    const file = new D.Document({
      creator: meta.group || '',
      title: doc.title,
      description: doc.title_en,
      features: { updateFields: true },
      styles: {
        default: {
          document: { run: { font: FONT, size: 24 }, paragraph: { spacing: { line: 360, after: 40 } } },
          heading1: h1,
          heading2: heading(28, 240, 120),
          heading3: heading(25, 200, 80),
          heading4: heading(24, 160, 60),
        },
      },
      numbering: {
        config: [{
          reference: 'bullet',
          levels: ['•', '–', '•'].map((text, level) => ({
            level, format: D.LevelFormat.BULLET, text, alignment: A.LEFT,
            style: { paragraph: { indent: { left: 480 * (level + 1), hanging: 300 } }, run: { font: 'Times New Roman' } },
          })),
        }],
      },
      sections: [
        { properties: { page }, children: cover },
        {
          properties: { page, type: D.SectionType.NEXT_PAGE },
          children: [
            new D.Paragraph({ alignment: A.CENTER, spacing: { after: 340 }, children: [new D.TextRun({ text: '目錄', size: 36, bold: true })] }),
            new D.TableOfContents('目錄', { hyperlink: true, headingStyleRange: '1-3' }),
          ],
        },
        { properties: { page: { ...page, pageNumbers: { start: 1 } }, type: D.SectionType.NEXT_PAGE }, footers: { default: footer }, children: body },
      ],
    });
    return D.Packer.toBase64String(file);
  };
})();
