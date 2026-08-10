/* Vibe Cards — PDF writer, browser build.
 *
 * A faithful port of src/pdfwriter.py's build_pdf(). It exists because the
 * static build has no Python: the desktop app rasterises each card in the
 * browser and posts it to the server to be composed; here the same bytes are
 * composed in the page itself.
 *
 * The whole value of this file is that a card lands in the tray pocket. Every
 * number below is physical: getting the matrix wrong does not look wrong on
 * screen, it prints a ruined PVC card. Keep it a PORT — if pdfwriter.py
 * changes, change this to match rather than improving it independently.
 *
 * Loaded as a CLASSIC script, not a module, and that is deliberate: index.html
 * loads backend.js then app.js as plain scripts, and a module script is
 * deferred — app.js would run before CS_BACKEND existed and boot() would fail
 * on a blank page. It exposes window.CS_PDF, and also module.exports so the
 * parity test can require() it in Node.
 *
 * Scope note: the desktop writer accepts JPEG and PNG. This one accepts JPEG
 * only, and that is not a shortcut — buildPlacements() in app.js always emits
 * `canvas.toDataURL('image/jpeg', quality)`, so PNG is unreachable here. A
 * PNG path would be untested code guarding an impossible case. If a caller
 * ever sends PNG it throws rather than silently mis-embedding.
 */

const PT_PER_MM = 72 / 25.4;

function mmToPt(mm) { return mm * PT_PER_MM; }

/* PDF reals: no exponent notation (illegal in PDF), no trailing zeros.
 * Mirrors pdfwriter.py _fmt exactly — a mismatch here is a silently different
 * geometry, so it is ported character for character rather than paraphrased. */
function fmt(v) {
  if (v === Math.trunc(v) && Math.abs(v) < 1e9) return String(Math.trunc(v));
  let s = v.toFixed(6).replace(/0+$/, '').replace(/\.$/, '');
  return (s === '' || s === '-' || s === '-0') ? '0' : s;
}

/* cos/sin of NEGATIVE the rotation: rotate_deg is CLOCKWISE about the rect
 * centre, and PDF space is y-up, so a clockwise turn is a negative angle.
 * sin(-90) = -1, not +1.
 *
 * Getting 90 and 270 the wrong way round here is invisible on screen and prints
 * a card upside down in the pocket. The parity test in tools/pdf_parity.mjs
 * exists because this port had exactly that bug on the first write; it compares
 * every rotation against pdfwriter.py rather than trusting the reasoning above. */
const TRIG = {
  0:   [1, 0],
  90:  [0, -1],
  180: [-1, 0],
  270: [0, 1],
};

/**
 * The `cm` matrix [a b c d e f] mapping an image XObject's unit square onto the
 * requested rect, rotated about that rect's centre.
 *
 * Two coordinate systems meet here and they disagree on which way is up: the
 * design model measures y DOWN from the page's top-left, PDF measures y UP from
 * the bottom-left. `cy` is where that flip happens. Port of _placement_matrix.
 */
function placementMatrix(xMm, yMm, wMm, hMm, pageHMm, rotateDeg) {
  const rot = ((rotateDeg | 0) % 360 + 360) % 360;
  const trig = TRIG[rot];
  if (!trig) throw new Error(`rotate_deg must be 0, 90, 180 or 270 — got ${rotateDeg}`);
  const [cosT, sinT] = trig;

  const w = mmToPt(wMm);
  const h = mmToPt(hMm);
  const cx = mmToPt(xMm + wMm / 2);
  const cy = mmToPt(pageHMm - (yMm + hMm / 2));   // <- the flip

  return [
    w * cosT,
    w * sinT,
    -h * sinT,
    h * cosT,
    cx - (w / 2) * cosT + (h / 2) * sinT,
    cy - (w / 2) * sinT - (h / 2) * cosT,
  ];
}

// ── byte plumbing ─────────────────────────────────────────────────────────
// Offsets in the xref table are BYTE offsets, so everything is assembled as
// Uint8Arrays. Building this as a string and encoding at the end would put the
// offsets out by however many multi-byte characters preceded them, and the
// reader would show a repair prompt.

const enc = new TextEncoder();
const b = (s) => enc.encode(s);

function concat(chunks) {
  let n = 0;
  for (const c of chunks) n += c.length;
  const out = new Uint8Array(n);
  let o = 0;
  for (const c of chunks) { out.set(c, o); o += c.length; }
  return out;
}

/** `<< dict /Length n >> stream … endstream` — port of _stream_obj. */
function streamObj(dictBody, payload) {
  return concat([
    b(`<< ${dictBody}${dictBody ? ' ' : ''}/Length ${payload.length} >>\nstream\n`),
    payload,
    b('\nendstream'),
  ]);
}

/** data: URL → { bytes, mime }. */
function dataUrlToBytes(dataUrl) {
  const m = /^data:([^;,]+)?(;base64)?,/.exec(dataUrl || '');
  if (!m) throw new Error('not a data: URL');
  const mime = (m[1] || '').toLowerCase();
  const body = dataUrl.slice(m[0].length);
  if (!m[2]) return { bytes: enc.encode(decodeURIComponent(body)), mime };
  const bin = atob(body);
  const out = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
  return { bytes: out, mime };
}

/* Width/height/components come from the JPEG itself, never from the caller.
 * The desktop writer parses the JPEG for exactly this reason: a declared size
 * that disagrees with the actual scan data renders as garbage or not at all,
 * and trusting the canvas would make that failure possible whenever the two
 * drift. Minimal SOF scan — enough to be correct, not a full decoder. */
function jpegInfo(bytes) {
  if (bytes[0] !== 0xFF || bytes[1] !== 0xD8) throw new Error('not a JPEG (no SOI)');
  let i = 2;
  while (i < bytes.length) {
    if (bytes[i] !== 0xFF) { i++; continue; }             // resync past fill bytes
    let marker = bytes[i + 1];
    while (marker === 0xFF) { i++; marker = bytes[i + 1]; }
    i += 2;
    if (marker === 0xD8 || marker === 0x01 || (marker >= 0xD0 && marker <= 0xD7)) continue;
    if (marker === 0xD9 || marker === 0xDA) break;         // EOI / start of scan
    const len = (bytes[i] << 8) | bytes[i + 1];
    // SOF0/1/2/3, 5-7, 9-11, 13-15 carry the frame header. DHT/DAC/DQT do not.
    const isSOF = (marker >= 0xC0 && marker <= 0xCF) &&
                  marker !== 0xC4 && marker !== 0xC8 && marker !== 0xCC;
    if (isSOF) {
      return {
        precision: bytes[i + 2],
        height: (bytes[i + 3] << 8) | bytes[i + 4],
        width: (bytes[i + 5] << 8) | bytes[i + 6],
        ncomp: bytes[i + 7],
      };
    }
    i += len;
  }
  throw new Error('no JPEG frame header (SOF) found');
}

/**
 * Compose a single-page PDF, exactly page_w_mm × page_h_mm, with images placed
 * at exact physical coordinates. Returns a Blob.
 *
 * images: [{ image: dataURL (JPEG), x_mm, y_mm, w_mm, h_mm, rotate_deg }]
 *   x_mm/y_mm are the TOP-LEFT corner of the placement rect, from the page's
 *   TOP-LEFT. Drawn in list order; later entries paint over earlier ones.
 */
function buildPdf({ pageWmm, pageHmm, images, title, dx = 0, dy = 0 }) {
  if (!(pageWmm > 0) || !(pageHmm > 0)) {
    throw new Error(`page must be positive, got ${pageWmm}x${pageHmm} mm`);
  }

  // Objects 1..4 are catalog / pages / page / contents; images follow.
  const objs = [null, null, null, null];
  const xobjectEntries = [];
  let content = '';

  images.forEach((spec, idx) => {
    const wMm = Number(spec.w_mm), hMm = Number(spec.h_mm);
    if (!(wMm > 0) || !(hMm > 0)) {
      throw new Error(`images[${idx}]: w_mm/h_mm must be positive, got ${wMm}x${hMm}`);
    }
    const { bytes, mime } = dataUrlToBytes(spec.image);
    if (!/jpe?g/.test(mime)) {
      throw new Error(`images[${idx}]: expected a JPEG data URL, got "${mime}" — see the scope note at the top of pdf.js`);
    }
    const info = jpegInfo(bytes);
    const cs = info.ncomp === 3 ? '/DeviceRGB' : '/DeviceGray';

    objs.push(streamObj(
      '/Type /XObject /Subtype /Image' +
      ` /Width ${info.width} /Height ${info.height}` +
      ` /ColorSpace ${cs} /BitsPerComponent 8 /Filter /DCTDecode`,
      bytes,   // embedded byte-for-byte: no recompression, no generation loss
    ));
    const num = objs.length;
    xobjectEntries.push(`/Im${idx} ${num} 0 R`);

    // Calibration is a whole-page nudge, applied per placement exactly as the
    // desktop's compose_pdf does — not baked into the matrix separately.
    const m = placementMatrix(
      Number(spec.x_mm) + dx, Number(spec.y_mm) + dy,
      wMm, hMm, pageHmm, Number(spec.rotate_deg || 0),
    );
    content += `q\n${m.map(fmt).join(' ')} cm\n/Im${idx} Do\nQ\n`;
  });

  const pageWpt = mmToPt(pageWmm);
  const pageHpt = mmToPt(pageHmm);

  /* /PrintScaling /None asks the print dialog NOT to shrink-to-fit. This is the
   * one place the two builds legitimately differ from each other: the desktop
   * never goes through a print dialog (it hands the job to `lp` directly), but
   * the web build's whole delivery is "here is a PDF, you print it" — and a
   * dialog defaulting to Fit-to-Page rescales a 120mm page to ~43%, which prints
   * a perfect, useless, wrong-sized card. It is a hint, not a guarantee: Preview
   * and Acrobat honour it, some drivers ignore it, which is why the UI ALSO says
   * it in words. */
  objs[0] = b('<< /Type /Catalog /Pages 2 0 R' +
              ' /ViewerPreferences << /PrintScaling /None >> >>');
  objs[1] = b('<< /Type /Pages /Kids [3 0 R] /Count 1 >>');
  objs[2] = b(
    '<< /Type /Page /Parent 2 0 R /MediaBox [0 0 ' +
    `${fmt(pageWpt)} ${fmt(pageHpt)}]` +
    ` /Resources << /XObject << ${xobjectEntries.join(' ')} >>` +
    ' /ProcSet [/PDF /ImageB /ImageC /ImageI] >>' +
    ' /Contents 4 0 R >>'
  );
  objs[3] = streamObj('', b(content));

  let info = '/Producer (Vibe Cards web pdf.js) /CreationDate ' + pdfDate(new Date());
  if (title) info += ' /Title ' + pdfTextString(String(title));
  objs.push(b(`<< ${info} >>`));
  const infoNum = objs.length;

  // ── serialise, recording byte offsets for the xref table ────────────────
  const parts = [b('%PDF-1.4\n%\xE2\xE3\xCF\xD3\n')];
  let pos = parts[0].length;
  const offsets = [];
  objs.forEach((body, i) => {
    offsets.push(pos);
    const head = b(`${i + 1} 0 obj\n`);
    const tail = b('\nendobj\n');
    parts.push(head, body, tail);
    pos += head.length + body.length + tail.length;
  });

  const docId = pseudoId(pos, offsets);
  const xrefPos = pos;
  let xref = `xref\n0 ${objs.length + 1}\n0000000000 65535 f \n`;
  for (const off of offsets) xref += String(off).padStart(10, '0') + ' 00000 n \n';
  xref +=
    `trailer\n<< /Size ${objs.length + 1} /Root 1 0 R /Info ${infoNum} 0 R` +
    ` /ID [<${docId}> <${docId}>] >>\n` +
    `startxref\n${xrefPos}\n%%EOF\n`;
  parts.push(b(xref));

  const out = concat(parts);

  /* Cheap insurance against ever handing the user a file that opens with a
   * repair prompt: every recorded offset must land on its object header. This
   * is ported deliberately — it is the check that catches a byte-accounting
   * slip introduced by a later edit. */
  offsets.forEach((off, i) => {
    const head = b(`${i + 1} 0 obj`);
    for (let k = 0; k < head.length; k++) {
      if (out[off + k] !== head[k]) {
        throw new Error(`xref offset ${off} does not point at object ${i + 1}`);
      }
    }
  });

  return new Blob([out], { type: 'application/pdf' });
}

function pdfTextString(s) {
  // ASCII only here by construction (document names are sanitised upstream);
  // escape the three characters that would end the literal string early.
  return '(' + s.replace(/\\/g, '\\\\').replace(/\(/g, '\\(').replace(/\)/g, '\\)') + ')';
}

function pdfDate(d) {
  const p = (n) => String(n).padStart(2, '0');
  const off = -d.getTimezoneOffset();
  const sign = off >= 0 ? '+' : '-';
  return `(D:${d.getFullYear()}${p(d.getMonth() + 1)}${p(d.getDate())}` +
         `${p(d.getHours())}${p(d.getMinutes())}${p(d.getSeconds())}` +
         `${sign}${p(Math.floor(Math.abs(off) / 60))}'${p(Math.abs(off) % 60)}')`;
}

/* The desktop uses an MD5 of the file bytes for /ID. There is no sync MD5 in
 * the browser and /ID only needs to be a stable-per-document identifier, not a
 * digest — so this derives one from the same material without pretending to be
 * a hash. */
function pseudoId(totalLen, offsets) {
  let h1 = 0x9e3779b9 ^ totalLen, h2 = 0x85ebca6b ^ offsets.length;
  for (const o of offsets) {
    h1 = Math.imul(h1 ^ o, 0xc2b2ae35) >>> 0;
    h2 = Math.imul(h2 + o, 0x27d4eb2f) >>> 0;
  }
  const hex = (n) => (n >>> 0).toString(16).padStart(8, '0');
  return hex(h1) + hex(h2) + hex(Math.imul(h1 ^ h2, 0x165667b1)) + hex(h1 + h2);
}

// Dual export: window.CS_PDF in the browser, module.exports under Node so
// tools/pdf_parity.mjs can diff this against pdfwriter.py.
const CS_PDF = { mmToPt, fmt, placementMatrix, dataUrlToBytes, jpegInfo, buildPdf };
if (typeof window !== 'undefined') window.CS_PDF = CS_PDF;
if (typeof module !== 'undefined' && module.exports) module.exports = CS_PDF;
