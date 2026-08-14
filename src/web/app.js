/* Card Studio — designer, tray compositor and print driver.
 *
 * One rule shapes this file: there is exactly ONE renderer, drawFace().
 * The editor preview, the tray preview, the batch thumbnails and the 600 dpi
 * print raster all call it with a different pixels-per-millimetre. A second
 * renderer would be a second set of rounding errors, and rounding errors here
 * are ink landing off the edge of a physical card.
 */

'use strict';

// ── constants ────────────────────────────────────────────────────────────

const MM_PER_IN = 25.4;
const PT_PER_IN = 72;
const CARD = { w: 85.6, h: 53.98 };      // ISO/IEC 7810 ID-1 (CR-80)
const CORNER_R = 3.18;
const SAFE = 4.0;                         // recommended keep-out from trim
// The margin the PRINTER cannot reach. Inkjet PVC stops short of the card edge,
// which is why a printed card has a white rim even when the artwork is black to
// the last pixel. Anything inside this band is not "close to the edge", it is
// GONE — and you find out after the card is through the printer.
//
// Backgrounds should still run past it: a background that stops at the bezel
// leaves a visible gap when the sheet feeds a fraction off. Content must not.
// These are MEASURED, not assumed. Calipering the four white margins on a printed
// card and solving with tools/calibrate.py gave 1.885 mm horizontal and 2.020 mm
// vertical on the reference machine. An earlier guess of 1.0 mm was about half the
// real value, which is the worst kind of wrong here: it says content is safe when
// it is about to be cut off.
//
// Calibration does NOT change these. It centres the print, which equalises the
// four margins; the bezel is what remains once they are equal.
/* WHAT THE PRINTER CANNOT REACH — measured from the DEVICE, not from a card.
 *
 * These were 1.885 and 2.02, and both were wrong in a way that took a full audit
 * to see. They came from calipering a printed card's white border and assigning
 * all of it to the printer. That card's ARTWORK carried its own ~1.9 mm white
 * frame, which the measurement could not distinguish from an unreachable band —
 * so design white got promoted to printer physics, and then the app started
 * enforcing it. Decoding the PDFs settles it: the two calipered cards have
 * 1.91 mm and 1.99 mm of white INSIDE their own raster; a full-bleed card printed
 * on the same tray has 0.00 mm.
 *
 * The arithmetic that should have caught it earlier: the loss was 4.40 % across
 * and 7.48 % down. One scale factor cannot be two percentages — an isotropic
 * scale forces the ratio 85.6/53.98 = 1.586, and the measured ratio was 0.933.
 * It was never a scale. It was a constant band, and a constant band comes from
 * something additive.
 *
 * The real number comes from the printer, which answers when asked: for this
 * tray's 120 x 120 media it reports 0.1 mm on all four edges, and the residual
 * left over after removing the artwork's own frame is 0.02-0.14 mm. So this is a
 * fallback for when the device does not answer, and it is deliberately small —
 * an overstated keep-out costs you the edge of every design forever, silently.
 *
 * NEVER PAINT THESE. They warn. A white border you can see is S.frame. */
let DEVICE_MARGIN_X = 0.1;
let DEVICE_MARGIN_Y = 0.1;
let DEVICE_MARGIN_SOURCE = 'fallback (printer not queried)';

/* Replace the fallback with the device's own answer, when there is one. Called
 * once at boot from the bootstrap payload. An absent or malformed reply leaves
 * the fallback in place — a printer that is asleep is normal, and it must not
 * read as "this printer has no margins". */
function adoptDeviceMargins(dm) {
  if (!dm || typeof dm.x !== 'number' || typeof dm.y !== 'number') return false;
  DEVICE_MARGIN_X = dm.x;
  DEVICE_MARGIN_Y = dm.y;
  DEVICE_MARGIN_SOURCE = dm.source || 'printer';
  return true;
}
const BEZEL_X = 0.1;
const BEZEL_Y = 0.1;
const BEZEL = 0.1;

/* RFID/NFC antenna keep-out, ISO/IEC 14443-1:2018 Annex A.1 (Class 1 PICC).
 * The coil sits in the band between a centred 81 x 49 mm rectangle and a
 * centred 64 x 34 mm one. That band is 8.5 mm wide at the sides and 7.5 mm
 * top and bottom — far larger than any trim margin, which is the trap: a
 * design that clears the trim can still sit straight on top of the antenna,
 * where the card is raised and ink lies unevenly. */
const RFID = { outer: { w: 81.0, h: 49.0 }, inner: { w: 64.0, h: 34.0 } };

const FONTS = [
  'Helvetica Neue', 'Avenir Next', 'SF Pro Display', 'Futura', 'Gill Sans',
  'Optima', 'Georgia', 'Baskerville', 'Didot', 'American Typewriter',
  'Copperplate', 'Impact', 'Trebuchet MS', 'Verdana', 'Menlo', 'Courier New',
];

const KINDS = {
  text:    'Text',
  image:   'Image',
  rect:    'Shape',
  ellipse: 'Ellipse',
  line:    'Line',
  qr:      'QR',
  barcode: 'Barcode',
};

// ── state ────────────────────────────────────────────────────────────────

const S = {
  boot: null,
  profileKey: null,
  profile: null,
  doc: null,
  face: 0,
  sel: null,
  zoom: 1,
  showSafe: true,
  /* A WHITE BORDER THE DESIGNER WANTS. Not a printer constraint.
   *
   * This was called `margin`, defaulted ON, and carried the fitted 1.885/2.02 —
   * three decisions that combined into one bad outcome: every exported card lost
   * about 11.7 % of its face to a white frame nobody chose, sized from a
   * measurement error. A constraint and a design choice were the same object, so
   * a number that was only ever a guess about the printer became ink.
   *
   * They are separate now. What the printer cannot reach is DEVICE_MARGIN_*, is
   * read from the device, and is never painted. This is a frame, it is off until
   * asked for, and when it is on it prints exactly as previewed. */
  /* ON by default now, at 2 mm, because bleeding was tried on real cards and
   * lost: ink past the edge gets clipped ragged by the tray and needs sealing
   * immediately or it smears. A frame stops the ink short instead, so there is
   * nothing wet at the vulnerable edge and nothing to clean off the tray.
   *
   * 2 mm rather than a hair: it has to read as a deliberate border rather than
   * a printing error. It sits inside the card's 3.18 mm corner radius, so the
   * inner corner keeps a 1.18 mm curve and still looks like a card.
   *
   * This is a design choice with a chosen number — NOT the old fitted 1.885,
   * which claimed to be the printer's limit and was really a measurement of
   * someone's artwork. What the printer cannot reach is 0.1 mm, it comes from
   * the device, and it is never painted. */
  frame: { show: true, x: 2.0, y: 2.0, square: false },
  // Overprint past the card edge so no unprinted PVC shows. The ink lands on the
  // tray, which then needs wiping — that is the trade, and it is the user's to
  // make, so it defaults to off.
  bleed: 0,
  showGrid: false,
  showRfid: true,
  printer: null,
  caps: {},
  records: [],
  fields: [],
  batchIndex: 0,
  dragging: null,
  guides: [],
  // Reader state. Deliberately OUTSIDE S.doc: isDirty() is a stringify of S.doc, so
  // a card appearing on the reader would otherwise mark the design unsaved and start
  // prompting on window close for something the user never edited.
  nfc: { available: null, reader: null, present: false, card: null, poll: null, busy: false },
};

const imgCache = new Map();
const codeCache = new Map();

// ── small utils ──────────────────────────────────────────────────────────

const $  = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));
const clamp = (v, a, b) => Math.min(b, Math.max(a, v));
const round = (v, d = 2) => Math.round(v * 10 ** d) / 10 ** d;
const uid = () => 'e' + Math.random().toString(36).slice(2, 9);
const mm2px = (mm, pxmm) => mm * pxmm;
const pt2mm = (pt) => (pt / PT_PER_IN) * MM_PER_IN;

function toast(msg, kind = '') {
  const t = $('#toast');
  t.textContent = msg;
  t.className = 'toast is-on ' + (kind ? 'is-' + kind : '');
  clearTimeout(toast._t);
  toast._t = setTimeout(() => { t.className = 'toast'; }, kind === 'err' ? 6500 : 2600);
}

function setStatus(msg) { $('#status').textContent = msg || ''; }

/* THE ONE SEAM between the desktop app and the static web build.
 *
 * Everything else in this file — the renderer, the document model, the whole
 * designer — is identical in both. Only the backend differs, so only the
 * backend is swapped: backend.js defines window.CS_BACKEND before this file
 * loads. The desktop one talks HTTP to server.py; the web one implements the
 * same calls against browser APIs.
 *
 * Do NOT fork this file to make a web version. Two copies of a renderer drift,
 * and then a fix lands in one of them. */
async function api(path, body) {
  return CS_BACKEND.call(path, body);
}

/** What the current backend can actually do. Drives UI that would otherwise
 *  advertise a capability the build does not have. */
function can(feature) {
  return !!(CS_BACKEND.capabilities && CS_BACKEND.capabilities[feature]);
}

// ── document model ───────────────────────────────────────────────────────

/* "Is there work here that is not on disk?" — asked before anything that
 * discards the document (closing the window, opening another card). Derived by
 * comparing against the last-saved serialisation rather than a hand-maintained
 * flag, because a flag has to be remembered at every mutation site and this
 * does not. */
let savedSnapshot = '';

function docSnapshot() {
  try { return S.doc ? JSON.stringify(S.doc) : ''; } catch (_) { return ''; }
}

function markSaved() { savedSnapshot = docSnapshot(); }

function isDirty() { return !!S.doc && docSnapshot() !== savedSnapshot; }

function blankFace(bg = '#ffffff') {
  return { bg: { type: 'color', color: bg }, elements: [] };
}

function newDoc(name = 'Untitled Card') {
  return { name, card: { ...CARD }, faces: [blankFace(), blankFace('#f4f4f5')] };
}

function face() { return S.doc.faces[S.face]; }

function defaults(type) {
  const c = S.doc.card;
  const base = { id: uid(), type, rot: 0, opacity: 1, hidden: false };
  switch (type) {
    case 'text':
      return { ...base, x: 6, y: 8, w: 50, h: 8, text: 'Name Surname', font: 'Helvetica Neue',
               size: 14, weight: 600, italic: false, color: '#111111', align: 'left',
               valign: 'middle', lineHeight: 1.2, tracking: 0 };
    case 'rect':
      return { ...base, x: 0, y: 0, w: c.w, h: 14, fill: '#1c2530', stroke: '', strokeW: 0.3, radius: 0 };
    case 'ellipse':
      return { ...base, x: 8, y: 14, w: 20, h: 20, fill: '#d8dde3', stroke: '', strokeW: 0.3 };
    case 'line':
      return { ...base, x: 6, y: 26, w: 40, h: 0, stroke: '#c2c8d0', strokeW: 0.4 };
    case 'image':
      // Full card by default. A photo on a card almost always wants to be the
      // card — dropping it in as a 26 mm square just makes everyone resize it.
      return { ...base, x: 0, y: 0, w: c.w, h: c.h, src: '', fit: 'cover', radius: 0 };
    case 'photo':
      return { ...defaults('image'), radius: 13, w: 26, h: 26, _photo: true };
    case 'qr':
      return { ...base, x: 62, y: 26, w: 20, h: 20, text: 'https://example.com',
               ec: 'M', dark: '#000000', light: '#ffffff', quiet: 2 };
    case 'barcode':
      return { ...base, x: 6, y: 42, w: 46, h: 9, text: '000117', dark: '#000000',
               light: '#ffffff', showText: true, textSize: 6 };
    default:
      return base;
  }
}

const TEMPLATES = {
  'tres-raices-front': {
    label: 'Tres Ra\u00edces \u2014 front',
    build: () => ({
      bg: { type: 'color', color: '#ffffff' },
      elements: [{ ...defaults('image'), x: 0, y: 0, w: 85.6, h: 53.98, radius: 0,
                   fit: 'cover', src: 'cards/raices-front.png' }],
    }),
  },
  'tres-raices-back': {
    label: 'Tres Ra\u00edces \u2014 back',
    build: () => ({
      bg: { type: 'color', color: '#ffffff' },
      elements: [{ ...defaults('image'), x: 0, y: 0, w: 85.6, h: 53.98, radius: 0,
                   fit: 'cover', src: 'cards/raices-back.png' }],
    }),
  },
  'tierra-trazo-front': {
    label: 'Tierra y Trazo \u2014 front',
    build: () => ({
      bg: { type: 'color', color: '#ffffff' },
      elements: [{ ...defaults('image'), x: 0, y: 0, w: 85.6, h: 53.98, radius: 0,
                   fit: 'cover', src: 'cards/tierra-front.png' }],
    }),
  },
  'tierra-trazo-back': {
    label: 'Tierra y Trazo \u2014 back',
    build: () => ({
      bg: { type: 'color', color: '#ffffff' },
      elements: [{ ...defaults('image'), x: 0, y: 0, w: 85.6, h: 53.98, radius: 0,
                   fit: 'cover', src: 'cards/tierra-back.png' }],
    }),
  },

  // --- Gift cards, whole-face artwork -----------------------------------
  // These four are a single full-bleed image, not a composition: the art was
  // authored elsewhere and rasterised at 600 dpi (2022 x 1275 for the trim
  // box). One image element rather than a bg image, because allImagesReady()
  // only waits on elements -- a bg image can still be undecoded when the print
  // path exports, and an undecoded frame bakes out black.
  'abrazo-nica-front': {
    label: 'Abrazo Nica \u2014 front',
    build: () => ({
      bg: { type: 'color', color: '#ffffff' },
      elements: [{ ...defaults('image'), x: 0, y: 0, w: 85.6, h: 53.98, radius: 0,
                   fit: 'cover', src: 'cards/abrazo-front.png' }],
    }),
  },
  'abrazo-nica-back': {
    label: 'Abrazo Nica \u2014 back',
    build: () => ({
      bg: { type: 'color', color: '#ffffff' },
      elements: [{ ...defaults('image'), x: 0, y: 0, w: 85.6, h: 53.98, radius: 0,
                   fit: 'cover', src: 'cards/abrazo-back.png' }],
    }),
  },
  'asin-sala-front': {
    label: 'Asin at Sala \u2014 front',
    build: () => ({
      bg: { type: 'color', color: '#ffffff' },
      elements: [{ ...defaults('image'), x: 0, y: 0, w: 85.6, h: 53.98, radius: 0,
                   fit: 'cover', src: 'cards/asin-front.png' }],
    }),
  },
  'asin-sala-back': {
    label: 'Asin at Sala \u2014 back',
    build: () => ({
      bg: { type: 'color', color: '#ffffff' },
      elements: [{ ...defaults('image'), x: 0, y: 0, w: 85.6, h: 53.98, radius: 0,
                   fit: 'cover', src: 'cards/asin-back.png' }],
    }),
  },
  // ── Founder card ──────────────────────────────────────────────────────
  // Two faces, applied one at a time because the Template control replaces the
  // face you are looking at.
  //
  // Geometry: CR-80 is 85.6 x 53.98 mm and the safe zone is 3 mm, so nothing
  // starts before x=3 or ends after x=82.6. An earlier version of this template
  // ran the text column to x=84 — inside the card, outside the safe zone, and the
  // first thing a trimmer eats.
  //
  // `size` is in POINTS: 15 pt is 5.29 mm, and bold caps run about 0.72 em per
  // character, so "PAYOPAY" is ~26.7 mm in a 44 mm column.
  'founder-card': {
    label: 'Founder card — front',
    build: () => ({
      bg: { type: 'image', src: 'textures/black-suede.jpg', color: '#0a0a0a' },
      elements: [
        { ...defaults('image'), x: 8, y: 16, w: 22, h: 22, radius: 11, src: 'founder.png' },
        { ...defaults('text'), x: 36, y: 9.5, w: 44, h: 6.5, text: 'ALDRIN', size: 15, weight: 700, color: '#ffffff', tracking: .3 },
        { ...defaults('text'), x: 36, y: 16, w: 44, h: 6.5, text: 'PAYOPAY', size: 15, weight: 700, color: '#ffffff', tracking: .3 },
        { ...defaults('line'), x: 36, y: 24.2, w: 34, h: 0, stroke: '#4a4a4a', strokeW: .4 },
        { ...defaults('text'), x: 36, y: 26, w: 44, h: 4.6, text: 'Founder', size: 8.5, weight: 500, color: '#d2d2d2' },
        { ...defaults('text'), x: 36, y: 30.6, w: 44, h: 4.6, text: 'Persona 500 LLC', size: 8.5, weight: 500, color: '#8c8c8c' },
        { ...defaults('text'), x: 36, y: 36, w: 44, h: 5, text: 'persona500.com', size: 9, weight: 700, color: '#ffffff' },
        { ...defaults('text'), x: 36, y: 41.8, w: 44, h: 3.6, text: 'RFID · FOUNDER · CR-80', size: 5.5, weight: 500, color: '#5a5a5a', tracking: 1.2 },
        // Tap mark, bottom-right. 10.3 mm is 12% of the card width, which survives
        // silhouette fill down to a 48 px thumbnail — tested. 7 mm in clears the
        // 4 mm keep-out and the measured 2.02 mm unprintable margin.
        { ...defaults('image'), x: 68.3, y: 36.7, w: 10.3, h: 10.3, src: 'marks/tap-white.png' },
      ],
    }),
  },
  'founder-card-back': {
    label: 'Founder card — back',
    build: () => ({
      bg: { type: 'image', src: 'textures/black-suede.jpg', color: '#0a0a0a' },
      elements: [
        { ...defaults('text'), x: 8, y: 12.5, w: 46, h: 7, text: 'VIBE CARDS', size: 16, weight: 700, color: '#ffffff', tracking: .5 },
        { ...defaults('text'), x: 8, y: 21.5, w: 46, h: 4.4, text: 'Standardized RFID · CR-80', size: 8, weight: 500, color: '#d2d2d2' },
        { ...defaults('text'), x: 8, y: 26, w: 46, h: 4.4, text: 'Open-source tray printing', size: 8, weight: 500, color: '#8c8c8c' },
        { ...defaults('text'), x: 8, y: 32, w: 46, h: 4.8, text: 'mrdirno.github.io/vibe-cards', size: 8.5, weight: 700, color: '#ffffff' },
        { ...defaults('text'), x: 8, y: 38.6, w: 46, h: 3.6, text: 'TAP OR SCAN · SAME URL', size: 5.5, weight: 500, color: '#5a5a5a', tracking: 1.2 },
        // A QR needs light under it and a quiet zone around it; on a black card
        // that means an actual white patch, not a lighter shade of the texture.
        // 24 mm rather than 21: at 21 the module pitch is 0.488 mm, which needs a
        // phone at 12-15 cm. 24 mm buys back ~14% and makes arm's length work.
        { ...defaults('rect'), x: 55.6, y: 14, w: 26, h: 26, fill: '#ffffff', radius: 1.5 },
        { ...defaults('qr'), x: 56.6, y: 15, w: 24, h: 24, text: 'https://mrdirno.github.io/vibe-cards/' },
      ],
    }),
  },
  // ── Place card ────────────────────────────────────────────────────────
  // The archive register, not the luxury one. A place is interesting because of
  // what is specifically true of it — the market, the alloy, the calipered
  // dimension, the coordinates — so the card carries facts rather than mood.
  // Density is the point: a nearly empty card says nothing and cannot be wished
  // better, because there is nothing on it to correct.
  /* ── Guatemala, GT-001 ────────────────────────────────────────────────
   *
   * Finished artwork, placed and not rebuilt. There is a `place-front`
   * template below that reconstructs this card from primitives, and it is the
   * wrong tool for a card someone has already designed: re-typesetting a
   * finished face in a different renderer changes it, and every change is a
   * loss when the original was approved.
   *
   * So these are one image element at exactly card size, `cover` fit, no
   * overlay and nothing editable on top. Cover preserves aspect and crops the
   * overflow — the art is 1.5846 against the card's 1.5858, a 0.08 % crop,
   * which is under half a pixel at 600 dpi. Nothing is stretched.
   *
   * MEASURED, because it decides whether a frame is free or expensive — how
   * close the ink comes to each edge:
   *
   *            top    bottom  left   right
   *   archive  7.36    0.00   0.00   0.00     ink to the edge; a frame CUTS content
   *   sleek    4.06    3.98   5.08   5.00     already framed; up to ~4 mm is free
   *
   * The sleek pair is print-ready today. The archive pair loses its footer
   * strip to any frame at all — including "WISH THE PAGE BETTER", which is the
   * network hook — so it wants a re-export with the content pulled in ~3 mm,
   * or it prints frameless and accepts what the tray masks.
   *
   * The QR on the archive back is DECORATIVE. It is about 18 modules across and
   * no QR version has 18 — the smallest real one is 21x21 — and it decodes at
   * no scale (tested 1x, 2x, 4x, 8x, 12x through the system barcode detector).
   * It cannot be fixed by printing it larger. It also cannot be replaced yet,
   * because GT-001 has no destination to point at. The chip is what makes this
   * card work; the QR is ink that looks like a QR.
   *
   * Artwork by Meta AI, commissioned by the card's owner. Included as a
   * template at the owner's instruction. */
  'gt-sleek-front': {
    label: 'Guatemala GT-001 — sleek, front',
    build: () => ({
      bg: { type: 'color', color: '#f4f1e8' },
      elements: [{ ...defaults('image'), src: 'templates/gt-sleek-front.jpg', fit: 'cover', radius: 0 }],
    }),
  },
  'gt-sleek-back': {
    label: 'Guatemala GT-001 — sleek, back',
    build: () => ({
      bg: { type: 'color', color: '#f4f1e8' },
      elements: [{ ...defaults('image'), src: 'templates/gt-sleek-back.jpg', fit: 'cover', radius: 0 }],
    }),
  },
  'gt-archive-front': {
    label: 'Guatemala GT-001 — archive, front',
    build: () => ({
      bg: { type: 'color', color: '#1b1d22' },
      elements: [{ ...defaults('image'), src: 'templates/gt-archive-front.jpg', fit: 'cover', radius: 0 }],
    }),
  },
  'gt-archive-back': {
    label: 'Guatemala GT-001 — archive, back',
    build: () => ({
      bg: { type: 'color', color: '#f2f3f4' },
      elements: [{ ...defaults('image'), src: 'templates/gt-archive-back.jpg', fit: 'cover', radius: 0 }],
    }),
  },
  'place-front': {
    label: 'Place card — front',
    build: () => ({
      bg: { type: 'linear', from: '#15171c', to: '#0d0e11', angle: 155 },
      elements: [
        { ...defaults('text'), x: 7, y: 6.5, w: 50, h: 4, text: 'NODE // GT-001', size: 6.5, weight: 600, color: '#8d95a3', font: 'Menlo', tracking: 1.4 },
        { ...defaults('text'), x: 7, y: 14, w: 62, h: 11, text: 'GUATEMALA', size: 21, weight: 700, color: '#ffffff', tracking: .4 },
        { ...defaults('line'), x: 7, y: 27.5, w: 30, h: 0, stroke: '#3b8ed0', strokeW: .5 },
        { ...defaults('text'), x: 7, y: 30, w: 68, h: 4.4, text: 'TIKAL · ANTIGUA · ATITLÁN · QUETZAL · CEIBA', size: 7, weight: 500, color: '#c3cbd6', tracking: .3 },
        { ...defaults('text'), x: 7, y: 35.4, w: 45, h: 4.4, text: '15.7835° N / 90.2302° W', size: 7, weight: 500, color: '#7f8896', font: 'Menlo' },
        { ...defaults('text'), x: 7, y: 43.5, w: 70, h: 4, text: 'SPECIMEN 74.74 mm · ZINC ALLOY · ENAMEL · EST. 2026', size: 5.8, weight: 500, color: '#5f6773', font: 'Menlo', tracking: .6 },
        // Tap mark, bottom-right. 10.3 mm is 12% of the card width, which survives
        // silhouette fill down to a 48 px thumbnail — tested. 7 mm in clears the
        // 4 mm keep-out and the measured 2.02 mm unprintable margin.
        { ...defaults('image'), x: 68.3, y: 36.7, w: 10.3, h: 10.3, src: 'marks/tap-white.png' },
      ],
    }),
  },
  'place-back': {
    label: 'Place card — back',
    build: () => ({
      bg: { type: 'color', color: '#f4f3ef' },
      elements: [
        { ...defaults('text'), x: 7, y: 7, w: 46, h: 8, text: 'GUATEMALA', size: 16, weight: 700, color: '#14161a', tracking: .2 },
        { ...defaults('text'), x: 7, y: 15.5, w: 46, h: 4.6, text: 'NETWORKED SPECIMEN ARCHIVE', size: 7.5, weight: 700, color: '#2f7ab8', tracking: .5 },
        { ...defaults('text'), x: 7, y: 21.5, w: 45, h: 8, text: 'This card is a physical hash of a place.\nScan to evolve it.', size: 7.5, weight: 500, color: '#3d434c' },
        { ...defaults('text'), x: 7, y: 31.5, w: 46, h: 3.8, text: 'ORIGIN   ANTIGUA / TIKAL MARKETS', size: 6.4, weight: 500, color: '#3d434c', font: 'Menlo' },
        { ...defaults('text'), x: 7, y: 35.3, w: 46, h: 3.8, text: 'ALLOY    ZINC + ANTIQUE SILVER', size: 6.4, weight: 500, color: '#3d434c', font: 'Menlo' },
        { ...defaults('text'), x: 7, y: 39.1, w: 46, h: 3.8, text: 'DIM      74.74 × 32.71 mm (calipered)', size: 6.4, weight: 500, color: '#3d434c', font: 'Menlo' },
        { ...defaults('text'), x: 7, y: 42.9, w: 46, h: 3.8, text: 'GENOME   GT-001-2026', size: 6.4, weight: 500, color: '#3d434c', font: 'Menlo' },
        // 24 mm, not 21: at 21 the module pitch needs a phone at 12-15 cm.
        { ...defaults('qr'), x: 57, y: 15, w: 24, h: 24, text: 'https://mrdirno.github.io/vibe-cards/' },
        { ...defaults('text'), x: 57, y: 40.5, w: 24, h: 3.6, text: 'SCAN → WISH IT BETTER', size: 5.2, weight: 600, color: '#5f6773', font: 'Menlo', tracking: .4 },
        // Tap mark, bottom-right. 10.3 mm is 12% of the card width, which survives
        // silhouette fill down to a 48 px thumbnail — tested. 7 mm in clears the
        // 4 mm keep-out and the measured 2.02 mm unprintable margin.
        { ...defaults('image'), x: 7, y: 6.5, w: 10.3, h: 10.3, src: 'marks/tap-black.png' },
      ],
    }),
  },
  'access-badge': {
    label: 'Access badge',
    build: () => ({
      bg: { type: 'color', color: '#ffffff' },
      elements: [
        { ...defaults('rect'), x: 0, y: 0, w: 26, h: CARD.h, fill: '#12212e', radius: 0 },
        { ...defaults('rect'), x: 0, y: 0, w: 26, h: 3.2, fill: '#e0a63c', radius: 0 },
        { ...defaults('text'), x: 3.5, y: 6, w: 19, h: 6, text: 'ACCESS', size: 9, weight: 700,
          color: '#e0a63c', tracking: 1.4 },
        { ...defaults('image'), x: 3.5, y: 14, w: 19, h: 19, radius: 9.5, src: '' },
        { ...defaults('text'), x: 3.5, y: 36, w: 19, h: 5, text: '{{ID}}', size: 8, weight: 500,
          color: '#9fb0bf', font: 'Menlo' },
        { ...defaults('text'), x: 31, y: 9, w: 50, h: 8, text: '{{Name}}', size: 15, weight: 650, color: '#12212e' },
        { ...defaults('text'), x: 31, y: 18, w: 50, h: 5, text: '{{Role}}', size: 8.5, weight: 500, color: '#5c6b7a', tracking: .6 },
        { ...defaults('line'), x: 31, y: 25, w: 30, h: 0, stroke: '#dde2e8', strokeW: .35 },
        { ...defaults('qr'), x: 62, y: 29, w: 19, h: 19, text: '{{ID}}' },
        { ...defaults('text'), x: 31, y: 30, w: 28, h: 4, text: 'VALID THRU', size: 6, weight: 600,
          color: '#96a4b2', tracking: 1 },
        { ...defaults('text'), x: 31, y: 34, w: 28, h: 6, text: '{{Expires}}', size: 10, weight: 600,
          color: '#12212e', font: 'Menlo' },
      ],
    }),
  },
  'member-card': {
    label: 'Member card',
    build: () => ({
      bg: { type: 'linear', from: '#1b1f2a', to: '#39435c', angle: 135 },
      elements: [
        { ...defaults('text'), x: 7, y: 7, w: 50, h: 7, text: 'MEMBER', size: 8, weight: 700,
          color: '#e0a63c', tracking: 2.2 },
        { ...defaults('rect'), x: 7, y: 19, w: 11, h: 8.4, fill: '#d9b25c', radius: 1.2 },
        { ...defaults('line'), x: 7, y: 23.2, w: 11, h: 0, stroke: '#8a6f31', strokeW: .3 },
        { ...defaults('text'), x: 7, y: 33, w: 60, h: 7, text: '{{Name}}', size: 13, weight: 600, color: '#ffffff' },
        { ...defaults('text'), x: 7, y: 42, w: 45, h: 5, text: '{{ID}}', size: 9, weight: 500,
          color: '#aeb8cc', font: 'Menlo', tracking: 1.6 },
        { ...defaults('qr'), x: 64, y: 32, w: 15, h: 15, text: '{{ID}}', dark: '#ffffff', light: '#1b1f2a' },
      ],
    }),
  },
  'minimal-id': {
    label: 'Minimal ID',
    build: () => ({
      bg: { type: 'color', color: '#fbfbfa' },
      elements: [
        { ...defaults('image'), x: 6, y: 6, w: 24, h: 30, radius: 1.5, src: '' },
        { ...defaults('text'), x: 34, y: 8, w: 46, h: 7, text: '{{Name}}', size: 14, weight: 600, color: '#16181c' },
        { ...defaults('text'), x: 34, y: 17, w: 46, h: 5, text: '{{Role}}', size: 8, weight: 500, color: '#767c85' },
        { ...defaults('line'), x: 34, y: 24, w: 46, h: 0, stroke: '#dcdedf', strokeW: .3 },
        { ...defaults('barcode'), x: 34, y: 28, w: 46, h: 11, text: '{{ID}}', textSize: 5.5 },
        { ...defaults('text'), x: 6, y: 40, w: 24, h: 5, text: '{{ID}}', size: 7, weight: 500,
          color: '#767c85', font: 'Menlo' },
      ],
    }),
  },
  'blank': { label: 'Blank', build: () => blankFace() },
};

// ── field substitution ───────────────────────────────────────────────────

function resolve(text, rec) {
  if (!text) return '';
  if (!rec) return text;
  return String(text).replace(/\{\{\s*([^}]+?)\s*\}\}/g, (m, key) => {
    const k = Object.keys(rec).find((h) => h.toLowerCase() === key.toLowerCase());
    return k ? rec[k] : m;
  });
}

// ── asset loading ────────────────────────────────────────────────────────

function getImage(src) {
  if (!src) return null;
  if (imgCache.has(src)) return imgCache.get(src);
  const img = new Image();
  img.onload = () => { render(); renderTray(); };
  img.src = src;
  imgCache.set(src, img);
  return img;
}

function allImagesReady(doc) {
  const srcs = [];
  doc.faces.forEach((f) => f.elements.forEach((e) => { if (e.type === 'image' && e.src) srcs.push(e.src); }));
  return Promise.all(srcs.map((src) => new Promise((res) => {
    const img = getImage(src);
    if (!img || img.complete) return res();
    img.addEventListener('load', res, { once: true });
    img.addEventListener('error', res, { once: true });
  })));
}

function qrMatrix(text, ec) {
  const key = 'q ' + ec + ' ' + text;
  if (codeCache.has(key)) return codeCache.get(key);
  let m = null;
  try { m = window.QR ? window.QR.encode(text || ' ', { ecLevel: ec || 'M' }) : null; }
  catch (err) { m = null; }
  codeCache.set(key, m);
  return m;
}

function barcodeBars(text) {
  const key = 'b ' + text;
  if (codeCache.has(key)) return codeCache.get(key);
  let b = null;
  try { b = window.Barcode ? window.Barcode.code128(text || '0') : null; }
  catch (err) { b = null; }
  codeCache.set(key, b);
  return b;
}

// ── THE renderer ─────────────────────────────────────────────────────────

function roundRectPath(ctx, x, y, w, h, r) {
  const rr = Math.max(0, Math.min(r, Math.min(w, h) / 2));
  ctx.beginPath();
  ctx.moveTo(x + rr, y);
  ctx.lineTo(x + w - rr, y);
  ctx.arcTo(x + w, y, x + w, y + rr, rr);
  ctx.lineTo(x + w, y + h - rr);
  ctx.arcTo(x + w, y + h, x + w - rr, y + h, rr);
  ctx.lineTo(x + rr, y + h);
  ctx.arcTo(x, y + h, x, y + h - rr, rr);
  ctx.lineTo(x, y + rr);
  ctx.arcTo(x, y, x + rr, y, rr);
  ctx.closePath();
}

function drawBackground(ctx, bg, w, h, pxmm) {
  const W = mm2px(w, pxmm), H = mm2px(h, pxmm);
  if (!bg || bg.type === 'color') {
    ctx.fillStyle = (bg && bg.color) || '#ffffff';
    ctx.fillRect(0, 0, W, H);
  } else if (bg.type === 'image') {
    // A card stock texture, drawn cover-fit so it fills the face at any aspect
    // without stretching -- a stretched grain reads as a printing fault.
    // Painted under a colour first: getImage() is async, so the very first frame
    // has no bitmap yet, and without the fill that frame is transparent, which
    // becomes black in the JPEG the print path embeds.
    ctx.fillStyle = bg.color || '#000000';
    ctx.fillRect(0, 0, W, H);
    const img = getImage(bg.src);
    if (img && img.complete && img.naturalWidth) {
      const s = Math.max(W / img.naturalWidth, H / img.naturalHeight);
      const dw = img.naturalWidth * s, dh = img.naturalHeight * s;
      ctx.drawImage(img, (W - dw) / 2, (H - dh) / 2, dw, dh);
    }
  } else if (bg.type === 'linear') {
    const a = ((bg.angle || 0) * Math.PI) / 180;
    const cx = W / 2, cy = H / 2;
    const len = (Math.abs(W * Math.cos(a)) + Math.abs(H * Math.sin(a))) / 2;
    const g = ctx.createLinearGradient(cx - Math.cos(a) * len, cy - Math.sin(a) * len,
                                       cx + Math.cos(a) * len, cy + Math.sin(a) * len);
    g.addColorStop(0, bg.from || '#ffffff');
    g.addColorStop(1, bg.to || '#cccccc');
    ctx.fillStyle = g;
    ctx.fillRect(0, 0, W, H);
  }
}

function wrapLines(ctx, text, maxPx) {
  const out = [];
  String(text).split('\n').forEach((para) => {
    if (!para) { out.push(''); return; }
    const words = para.split(/\s+/);
    let line = '';
    words.forEach((word) => {
      const test = line ? line + ' ' + word : word;
      if (maxPx > 0 && ctx.measureText(test).width > maxPx && line) { out.push(line); line = word; }
      else line = test;
    });
    out.push(line);
  });
  return out;
}

function drawElement(ctx, el, pxmm, rec) {
  if (el.hidden) return;
  const X = mm2px(el.x, pxmm), Y = mm2px(el.y, pxmm);
  const W = mm2px(el.w, pxmm), H = mm2px(el.h, pxmm);

  ctx.save();
  ctx.globalAlpha = el.opacity == null ? 1 : el.opacity;
  if (el.rot) {
    ctx.translate(X + W / 2, Y + H / 2);
    ctx.rotate((el.rot * Math.PI) / 180);
    ctx.translate(-(X + W / 2), -(Y + H / 2));
  }

  switch (el.type) {
    case 'rect': {
      roundRectPath(ctx, X, Y, W, H, mm2px(el.radius || 0, pxmm));
      if (el.fill) { ctx.fillStyle = el.fill; ctx.fill(); }
      if (el.stroke && el.strokeW > 0) {
        ctx.strokeStyle = el.stroke; ctx.lineWidth = mm2px(el.strokeW, pxmm); ctx.stroke();
      }
      break;
    }
    case 'ellipse': {
      ctx.beginPath();
      ctx.ellipse(X + W / 2, Y + H / 2, W / 2, H / 2, 0, 0, Math.PI * 2);
      if (el.fill) { ctx.fillStyle = el.fill; ctx.fill(); }
      if (el.stroke && el.strokeW > 0) {
        ctx.strokeStyle = el.stroke; ctx.lineWidth = mm2px(el.strokeW, pxmm); ctx.stroke();
      }
      break;
    }
    case 'line': {
      ctx.beginPath();
      ctx.moveTo(X, Y + H / 2);
      ctx.lineTo(X + W, Y + H / 2);
      ctx.strokeStyle = el.stroke || '#000';
      ctx.lineWidth = Math.max(1, mm2px(el.strokeW || 0.3, pxmm));
      ctx.lineCap = 'round';
      ctx.stroke();
      break;
    }
    case 'image': {
      const img = getImage(el.src);
      roundRectPath(ctx, X, Y, W, H, mm2px(el.radius || 0, pxmm));
      ctx.save();
      ctx.clip();
      if (img && img.complete && img.naturalWidth) {
        const ar = img.naturalWidth / img.naturalHeight, box = W / H;
        let dw = W, dh = H, dx = X, dy = Y;
        if (el.fit === 'contain') {
          if (ar > box) { dh = W / ar; dy = Y + (H - dh) / 2; } else { dw = H * ar; dx = X + (W - dw) / 2; }
        } else if (el.fit !== 'fill') { // cover
          if (ar > box) { dw = H * ar; dx = X - (dw - W) / 2; } else { dh = W / ar; dy = Y - (dh - H) / 2; }
        }
        ctx.drawImage(img, dx, dy, dw, dh);
      } else {
        // placeholder: reads as "drop a photo here" without pretending to be art
        ctx.fillStyle = '#e9ebee'; ctx.fillRect(X, Y, W, H);
        ctx.strokeStyle = '#c6cad0';
        ctx.lineWidth = Math.max(1, mm2px(0.25, pxmm));
        ctx.setLineDash([mm2px(1.2, pxmm), mm2px(1.2, pxmm)]);
        ctx.strokeRect(X, Y, W, H);
        ctx.setLineDash([]);
        ctx.fillStyle = '#9aa1aa';
        ctx.font = `${Math.max(6, mm2px(2.6, pxmm))}px ${FONTS[0]}`;
        ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
        ctx.fillText('photo', X + W / 2, Y + H / 2);
      }
      ctx.restore();
      break;
    }
    case 'text': {
      const txt = resolve(el.text, rec);
      const px = (el.size / PT_PER_IN) * MM_PER_IN * pxmm;   // size is in points
      ctx.font = `${el.italic ? 'italic ' : ''}${el.weight || 400} ${px}px "${el.font || FONTS[0]}", sans-serif`;
      ctx.fillStyle = el.color || '#000';
      ctx.textBaseline = 'alphabetic';
      if (ctx.letterSpacing !== undefined) ctx.letterSpacing = `${mm2px((el.tracking || 0) * 0.1, pxmm)}px`;

      const lines = wrapLines(ctx, txt, W);
      const lh = px * (el.lineHeight || 1.2);
      const block = lines.length * lh;
      let ty = Y + px * 0.82;
      if (el.valign === 'middle') ty = Y + (H - block) / 2 + px * 0.82;
      else if (el.valign === 'bottom') ty = Y + H - block + px * 0.82;

      ctx.textAlign = el.align === 'center' ? 'center' : el.align === 'right' ? 'right' : 'left';
      const tx = el.align === 'center' ? X + W / 2 : el.align === 'right' ? X + W : X;
      lines.forEach((ln, i) => ctx.fillText(ln, tx, ty + i * lh));
      if (ctx.letterSpacing !== undefined) ctx.letterSpacing = '0px';
      break;
    }
    case 'qr': {
      const m = qrMatrix(resolve(el.text, rec), el.ec);
      const side = Math.min(W, H);
      const ox = X + (W - side) / 2, oy = Y + (H - side) / 2;
      if (el.light) { ctx.fillStyle = el.light; ctx.fillRect(ox, oy, side, side); }
      if (!m) {
        ctx.fillStyle = '#b03b2a';
        ctx.font = `${Math.max(6, side * 0.11)}px ${FONTS[0]}`;
        ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
        ctx.fillText('QR error', ox + side / 2, oy + side / 2);
        break;
      }
      const q = el.quiet == null ? 2 : el.quiet;
      const cells = m.size + q * 2;
      const cs = side / cells;
      ctx.fillStyle = el.dark || '#000';
      for (let r = 0; r < m.size; r++) {
        for (let c = 0; c < m.size; c++) {
          if (!m.modules[r][c]) continue;
          // +0.5px bleed closes hairline seams between modules at low preview zoom
          ctx.fillRect(ox + (c + q) * cs, oy + (r + q) * cs, cs + 0.5, cs + 0.5);
        }
      }
      break;
    }
    case 'barcode': {
      const b = barcodeBars(resolve(el.text, rec));
      if (el.light) { ctx.fillStyle = el.light; ctx.fillRect(X, Y, W, H); }
      if (!b) {
        ctx.fillStyle = '#b03b2a';
        ctx.font = `${Math.max(6, H * 0.3)}px ${FONTS[0]}`;
        ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
        ctx.fillText('barcode error', X + W / 2, Y + H / 2);
        break;
      }
      const capPx = el.showText ? (el.textSize / PT_PER_IN) * MM_PER_IN * pxmm * 1.35 : 0;
      const barH = H - capPx;
      const total = b.bars.reduce((a, v) => a + v, 0);
      const unit = W / total;
      let x = X, dark = true;
      ctx.fillStyle = el.dark || '#000';
      b.bars.forEach((wUnits) => {
        if (dark) ctx.fillRect(x, Y, wUnits * unit + 0.4, barH);
        x += wUnits * unit;
        dark = !dark;
      });
      if (el.showText) {
        ctx.fillStyle = el.dark || '#000';
        ctx.font = `500 ${(el.textSize / PT_PER_IN) * MM_PER_IN * pxmm}px Menlo, monospace`;
        ctx.textAlign = 'center'; ctx.textBaseline = 'alphabetic';
        ctx.fillText(resolve(el.text, rec), X + W / 2, Y + H - capPx * 0.15);
      }
      break;
    }
  }
  ctx.restore();
}

/** Draw one card face into ctx with its top-left at the current origin. */
function drawFace(ctx, faceDoc, card, pxmm, rec) {
  ctx.save();
  roundRectPath(ctx, 0, 0, mm2px(card.w, pxmm), mm2px(card.h, pxmm), mm2px(CORNER_R, pxmm));
  ctx.clip();
  drawBackground(ctx, faceDoc.bg, card.w, card.h, pxmm);
  faceDoc.elements.forEach((el) => drawElement(ctx, el, pxmm, rec));
  ctx.restore();
}

/* Grow an edge-touching element outward so bleed reaches it.
 *
 * Bleed used to move the elements and stretch only the BACKGROUND, which meant
 * the one case people actually hit did nothing at all: `defaults('image')`
 * creates every added image at exactly x:0 y:0 w:card.w h:card.h, so a
 * full-card photo is card-sized inside an oversized canvas and the whole bleed
 * ring is background showing through. Measured before this: element ink was
 * 85.556 mm at bleed 0, 1 AND 2 mm. You would enable bleed, get ink on the tray,
 * wipe the tray, and the card would come out byte-identical.
 *
 * Only fills grow, and only on the edges they already touch:
 *
 *  - IMAGES and unstroked RECTS grow. They are floods; a flood is meant to run
 *    off the edge, and 1 mm more of a photograph is still that photograph.
 *  - TEXT, QR and BARCODE never grow. Scaling a full-card QR by 2 mm pushes its
 *    quiet zone off the card and it stops scanning — a silent failure that looks
 *    like a printing problem.
 *  - An element flush to the left edge only grows LEFT. Growing all four sides
 *    would move its right edge inward relative to the card and shift the layout,
 *    which is the exact bug bleed-by-scaling has.
 */
function bledElement(el, card, bleed) {
  if (!bleed) return el;
  const GROWS = el.type === 'image' || (el.type === 'rect' && !el.stroke);
  if (!GROWS || el.rot) return el;          // a rotated element has no axis-aligned edge to extend

  const T = 0.01;                            // flush means flush, to a hundredth of a mm
  const L = el.x <= T, U = el.y <= T;
  const R = el.x + el.w >= card.w - T, D = el.y + el.h >= card.h - T;
  if (!(L || R || U || D)) return el;

  return { ...el,
    x: el.x - (L ? bleed : 0),
    y: el.y - (U ? bleed : 0),
    w: el.w + (L ? bleed : 0) + (R ? bleed : 0),
    h: el.h + (U ? bleed : 0) + (D ? bleed : 0) };
}

/** Render a face to an offscreen canvas at print resolution. */
function rasterise(faceDoc, card, dpi, rec, bleed = 0, frame = undefined) {
  const pxmm = dpi / MM_PER_IN;
  const cv = document.createElement('canvas');
  cv.width = Math.round((card.w + bleed * 2) * pxmm);
  cv.height = Math.round((card.h + bleed * 2) * pxmm);
  const ctx = cv.getContext('2d');
  // White under everything: PVC is white, and an unpainted alpha channel
  // becomes black in a JPEG.
  ctx.fillStyle = '#ffffff';
  ctx.fillRect(0, 0, cv.width, cv.height);
  // Print uses square corners — the physical card supplies the radius, and
  // clipping it here would leave white arcs of ink short of the real edge.
  ctx.save();
  // TRUE bleed, not a scale-up. The BACKGROUND is painted across the oversized
  // area and the elements are shifted into the middle, so every element keeps its
  // exact millimetre size and position on the card. Scaling the whole face
  // instead would enlarge the type and creep the layout outward — a 1 mm bleed on
  // an 85.6 mm card is 2.3%, which is enough to push a QR under its own quiet
  // zone.
  drawBackground(ctx, faceDoc.bg, card.w + bleed * 2, card.h + bleed * 2, pxmm);
  ctx.translate(mm2px(bleed, pxmm), mm2px(bleed, pxmm));
  faceDoc.elements.forEach((el) => drawElement(ctx, bledElement(el, card, bleed), pxmm, rec));
  ctx.restore();

  /* The margin, painted LAST and at full opacity, so what came out of the
   * printer matches what the Design tab showed. It masks rather than shrinks:
   * an element under the band is covered, exactly as the preview draws it. The
   * alternative — scaling the artwork to fit inside — would make the preview a
   * lie in the other direction, showing type at a size it will not print at.
   *
   * Measured from the CARD edge, which is inset by `bleed`. Bleed and margin are
   * opposite answers to the same problem (ink short of the edge, versus ink past
   * it), so using both at once is unusual but not wrong: it prints a white band
   * inside the card and floods the overhang, which is what you want when the
   * tray masks a different amount on each side. */
  drawBezel(ctx, mm2px(card.w, pxmm), mm2px(card.h, pxmm), pxmm, 1,
            mm2px(bleed, pxmm), mm2px(bleed, pxmm), cv.width, cv.height, frame);
  return cv;
}

// ── editor canvas ────────────────────────────────────────────────────────

const RULER = 20;        // px gutter for the mm rulers
const PAD = 16;

function basePxmm() { return 4.6; }                      // 100% ≈ screen-legible
function pxmm() { return basePxmm() * S.zoom; }

function canvasGeom() {
  const p = pxmm();
  return {
    p,
    ox: RULER + PAD,
    oy: RULER + PAD,
    w: Math.round(S.doc.card.w * p),
    h: Math.round(S.doc.card.h * p),
  };
}

/* One rule, same as drawFace(): the empty state is derived from the document,
 * never toggled by hand at call sites. render() is the single chokepoint every
 * mutation already goes through, so it cannot drift out of sync. */
function syncEmptyState() {
  const box = $('#canvasEmpty');
  if (!box) return;
  box.hidden = !S.doc || face().elements.length > 0;
}

function render() {
  if (!S.doc) return;
  syncEmptyState();
  syncClipWarning();
  const cv = $('#canvas');
  const g = canvasGeom();
  const dpr = window.devicePixelRatio || 1;
  const totalW = g.ox + g.w + PAD;
  const totalH = g.oy + g.h + PAD;
  cv.width = Math.round(totalW * dpr);
  cv.height = Math.round(totalH * dpr);
  cv.style.width = totalW + 'px';
  cv.style.height = totalH + 'px';
  const ctx = cv.getContext('2d');
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, totalW, totalH);

  drawRulers(ctx, g);

  // card body + shadow
  ctx.save();
  ctx.translate(g.ox, g.oy);
  ctx.shadowColor = 'rgba(0,0,0,.55)';
  ctx.shadowBlur = 22; ctx.shadowOffsetY = 8;
  roundRectPath(ctx, 0, 0, g.w, g.h, mm2px(CORNER_R, g.p));
  ctx.fillStyle = '#fff';
  ctx.fill();
  ctx.shadowColor = 'transparent';
  drawFace(ctx, face(), S.doc.card, g.p, null);
  ctx.restore();

  ctx.save();
  ctx.translate(g.ox, g.oy);
  if (S.showGrid) drawGrid(ctx, g);
  if (S.showRfid) drawRfid(ctx, g);
  if (S.showSafe) drawSafe(ctx, g);
  drawGuides(ctx, g);
  drawSelection(ctx, g);
  ctx.restore();

  drawLayers();
}

function drawRulers(ctx, g) {
  ctx.save();
  ctx.fillStyle = '#0f1116';
  ctx.fillRect(0, 0, g.ox + g.w + PAD, RULER);
  ctx.fillRect(0, 0, RULER, g.oy + g.h + PAD);
  ctx.strokeStyle = '#2a303a';
  ctx.lineWidth = 1;
  ctx.font = '9px "SF Mono", Menlo, monospace';
  ctx.fillStyle = '#6b7280';

  ctx.textAlign = 'center'; ctx.textBaseline = 'bottom';
  for (let mm = 0; mm <= S.doc.card.w; mm += 1) {
    const x = g.ox + mm2px(mm, g.p) + 0.5;
    const major = mm % 10 === 0, mid = mm % 5 === 0;
    if (!major && !mid && g.p < 5) continue;
    ctx.beginPath();
    ctx.moveTo(x, RULER); ctx.lineTo(x, RULER - (major ? 7 : mid ? 5 : 3));
    ctx.stroke();
    if (major) ctx.fillText(String(mm), x, RULER - 8);
  }
  ctx.textAlign = 'right'; ctx.textBaseline = 'middle';
  for (let mm = 0; mm <= S.doc.card.h; mm += 1) {
    const y = g.oy + mm2px(mm, g.p) + 0.5;
    const major = mm % 10 === 0, mid = mm % 5 === 0;
    if (!major && !mid && g.p < 5) continue;
    ctx.beginPath();
    ctx.moveTo(RULER, y); ctx.lineTo(RULER - (major ? 7 : mid ? 5 : 3), y);
    ctx.stroke();
    if (major) ctx.fillText(String(mm), RULER - 9, y);
  }
  ctx.restore();
}

function drawGrid(ctx, g) {
  ctx.save();
  ctx.strokeStyle = 'rgba(88,166,240,.16)';
  ctx.lineWidth = 1;
  for (let mm = 5; mm < S.doc.card.w; mm += 5) {
    const x = Math.round(mm2px(mm, g.p)) + .5;
    ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, g.h); ctx.stroke();
  }
  for (let mm = 5; mm < S.doc.card.h; mm += 5) {
    const y = Math.round(mm2px(mm, g.p)) + .5;
    ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(g.w, y); ctx.stroke();
  }
  ctx.restore();
}

/** The white card stock the printer cannot reach. Shared by the design canvas and
 *  the tray preview so the two never disagree about where ink stops. */
const MARGIN_KEY = 'cs.frame';

function loadMargin() {
  try {
    const v = JSON.parse(localStorage.getItem(MARGIN_KEY));
    if (v && typeof v === 'object') Object.assign(S.frame, v);
  } catch { /* a corrupt value must not take the editor down */ }
}

function saveMargin() {
  try { localStorage.setItem(MARGIN_KEY, JSON.stringify(S.frame)); } catch { /* private mode */ }
}

/** How far this profile can bleed before a placement leaves the page.
 *
 *  Derived per profile, never a constant. A 2.0 mm cap taken from the Canon MP
 *  tray sends the 55×91 rear tray's placement to x = −1.49 mm, off the page — its
 *  slot sits 0.51 mm from the edge. The number belongs to the tray, so it is
 *  computed from the tray. Also bounded by half the gap between slots, or a large
 *  bleed on the upper card overprints the lower one.
 */
function maxBleedMm() {
  const p = S.profile;
  if (!p || !p.slots || !p.slots.length) return 0;
  const pw = p.page_mm.w, ph = p.page_mm.h;
  let lim = Infinity;
  p.slots.forEach((s) => {
    lim = Math.min(lim, s.x, s.y, pw - (s.x + s.w), ph - (s.y + s.h));
  });
  for (let i = 1; i < p.slots.length; i++) {
    const a = p.slots[i - 1], b = p.slots[i];
    lim = Math.min(lim, (b.y - (a.y + a.h)) / 2);
  }
  // Round DOWN to the slider step so the control can never offer a value the
  // page cannot take.
  return Math.max(0, Math.floor(Math.max(0, lim) * 4) / 4);
}

function wireBleed() {
  const r = $('#bleedRange'), out = $('#bleedOut'), note = $('#bleedNote');
  if (!r) return;
  const cap = maxBleedMm();
  r.max = cap;
  r.disabled = cap <= 0;
  if (parseFloat(r.value) > cap) r.value = cap;
  try {
    const v = parseFloat(localStorage.getItem('cs.bleed'));
    if (Number.isFinite(v)) { S.bleed = v; r.value = v; }
  } catch { /* private mode */ }
  const sync = () => {
    S.bleed = parseFloat(r.value) || 0;
    out.textContent = S.bleed ? S.bleed.toFixed(2) + ' mm' : 'off';
    note.textContent = cap <= 0
      ? 'This tray has no room to bleed — its slots sit on the page edge.'
      : S.bleed
        ? `Ink runs ${S.bleed.toFixed(2)} mm past every edge and lands on the tray. Wipe it between runs. This tray allows up to ${cap.toFixed(2)} mm.`
        : `No bleed: ink stops at the card edge, and any misfeed shows as a white sliver. This tray allows up to ${cap.toFixed(2)} mm.`;
    try { localStorage.setItem('cs.bleed', String(S.bleed)); } catch {}
    renderTray();
  };
  r.oninput = sync;
  sync();
}

function wireMargin() {
  const show = $('#showMargin'), mx = $('#marginX'), my = $('#marginY'), seg = $('#marginShape');
  if (!show) return;
  const sync = () => {
    show.checked = S.frame.show;
    mx.value = S.frame.x;
    my.value = S.frame.y;
    $$('#marginShape .seg-btn').forEach((b) =>
      b.classList.toggle('is-on', (b.dataset.shape === 'square') === S.frame.square));
    $('#marginCtl').classList.toggle('is-off', !S.frame.show);
  };
  const commit = () => { saveMargin(); sync(); render(); };

  show.onchange = () => { S.frame.show = show.checked; commit(); };
  // Clamped, because a margin wider than the card would fill the canvas white and
  // look like the app broke.
  const num = (el, key) => el.oninput = () => {
    const v = parseFloat(el.value);
    if (Number.isFinite(v)) { S.frame[key] = Math.min(8, Math.max(0, v)); commit(); }
  };
  num(mx, 'x'); num(my, 'y');
  seg.onclick = (e) => {
    const b = e.target.closest('.seg-btn'); if (!b) return;
    S.frame.square = b.dataset.shape === 'square';
    commit();
  };
  sync();
}

function roundRectSub(ctx, x, y, w, h, r) {
  // Same shape as roundRectPath but WITHOUT beginPath, so two of them can share
  // one path for an even-odd fill. roundRectPath resets the path, which silently
  // discards the first rectangle.
  const rr = Math.max(0, Math.min(r, Math.min(w, h) / 2));
  ctx.moveTo(x + rr, y);
  ctx.lineTo(x + w - rr, y);
  ctx.arcTo(x + w, y, x + w, y + rr, rr);
  ctx.lineTo(x + w, y + h - rr);
  ctx.arcTo(x + w, y + h, x + w - rr, y + h, rr);
  ctx.lineTo(x + rr, y + h);
  ctx.arcTo(x, y + h, x, y + h - rr, rr);
  ctx.lineTo(x, y + rr);
  ctx.arcTo(x, y, x + rr, y, rr);
  ctx.closePath();
}

/* The unprintable band around a card.
 *
 * ONE geometry, two callers. On screen it paints at 88% so the artwork stays
 * visible underneath; on export it paints at 100%, because there it is not an
 * annotation — it is the instruction to lay down no ink. `ox`/`oy` exist for the
 * bleed case, where the card does not start at the raster's origin.
 *
 * This used to be a preview overlay and nothing else, so a card designed with the
 * margin visible exported dark to the very edge: the screen promised a white
 * border and the PDF did not have one. A preview that disagrees with the artifact
 * is worse than no preview, because it is believed. */
function drawBezel(ctx, w, h, pxmm, alpha = 0.88, ox = 0, oy = 0, outerW = 0, outerH = 0,
                   frame = undefined) {
  /* The frame is an ARGUMENT, not a global read.
   *
   * It used to read S.frame directly, and that is how the calibration target got
   * masked: the target renders through the same rasteriser, so the frame painted
   * over tick 0, tick 1 and the corner L — the exact marks the card asks you to
   * read. The instruction on the card says "read the lowest tick you can still
   * see"; the lowest visible would have been 2, the truth was −0.4, and you would
   * have nudged the next print 2.4 mm the wrong way and spent a card finding out.
   *
   * A renderer that reads global state cannot be called safely from a context
   * that needs different state. Passing it in makes "no frame here" expressible
   * — `rasterise(..., null)` — instead of something every future caller has to
   * remember not to inherit. */
  const F = frame === undefined ? S.frame : frame;
  if (!F || !F.show) return;
  const X = (mm) => mm2px(mm, pxmm);
  const BEZEL_X = F.x, BEZEL_Y = F.y;
  // Both edges follow the card's curve. The margin on a real card is a band that
  // runs around a rounded rectangle, not a square frame — inset a rounded corner
  // by d and the radius drops by d, which is why the inner radius is derived
  // rather than picked.
  const rOuter = X(CORNER_R);
  const rInner = F.square ? 0 : X(Math.max(0.4, CORNER_R - BEZEL_X));
  /* The outer boundary runs PAST the card, not along it.
   *
   * It used to be a rounded rect on the card's own outline, which looks right
   * and is wrong: the four corner nubs — the area outside the curve but inside
   * the bounding box — fell OUTSIDE the fill and kept their artwork. On screen
   * that is invisible, because the preview is clipped to the same curve. In the
   * export, which deliberately does not clip corners, it printed as a dark wedge
   * at each extreme corner of the card. A 240× crop of the top-left corner is
   * what finally showed it; four edge scans had passed, because an edge scan
   * samples along the edges and a corner is not on one.
   *
   * So the band is bounded by the raster itself. If you asked for a margin you
   * asked for no ink near the edge, and that has to include the corners. */
  ctx.save();
  ctx.beginPath();
  roundRectSub(ctx, 0, 0, outerW || w, outerH || h, outerW ? 0 : rOuter);
  roundRectSub(ctx, ox + X(BEZEL_X), oy + X(BEZEL_Y),
               w - X(BEZEL_X * 2), h - X(BEZEL_Y * 2), rInner);
  // Pure white on export. There is no white ink in an inkjet — white IS the
  // absence of ink, which is exactly what an unprintable band should receive.
  ctx.fillStyle = alpha >= 1 ? '#ffffff' : `rgba(247,247,245,${alpha})`;
  ctx.fill('evenodd');
  ctx.restore();
}

function drawSafe(ctx, g) {
  const X = (mm) => mm2px(mm, g.p);
  const clipped = S.doc ? clippedElements(S.doc.faces[S.face], S.doc.card).length : 0;
  ctx.save();

  // The unprintable margin, drawn as what it physically IS: bare white card stock
  // where the printer lays no ink. Showing it as the real thing means the canvas
  // matches the card that comes out; an earlier version drew a red warning band,
  // which told you something was wrong without showing you what you would get.
  //
  // Nearly opaque rather than solid, so artwork underneath stays faintly visible
  // and it is obvious the ink is being covered rather than deleted.
  drawBezel(ctx, g.w, g.h, g.p);

  // Where the ink actually starts. Turns red only when something is sitting in
  // the margin, so the colour means "you have a problem" rather than "there is a
  // margin", which is always true and therefore not worth a colour.
  ctx.strokeStyle = clipped ? 'rgba(224,103,76,.9)' : 'rgba(120,120,128,.55)';
  ctx.lineWidth = 1;
  if (S.frame.show) {
    roundRectPath(ctx, X(S.frame.x), X(S.frame.y),
                  g.w - X(S.frame.x * 2), g.h - X(S.frame.y * 2),
                  S.frame.square ? 0 : X(Math.max(0.4, CORNER_R - S.frame.x)));
    ctx.stroke();
  }

  // The text keep-out, further in.
  ctx.strokeStyle = 'rgba(224,166,60,.55)';
  ctx.setLineDash([4, 3]);
  ctx.strokeRect(X(SAFE), X(SAFE), g.w - X(SAFE * 2), g.h - X(SAFE * 2));
  ctx.restore();
}

/** Say so in the footer when something is sitting in the bezel. The shaded band
 *  is only useful to someone already looking at that corner of the card. */
/** Calibration presets shipped with the profile: someone else's measured card,
 *  offered as a starting point. Applied to the fields, never saved behind the
 *  user's back — their tray is not the tray these numbers came from. */
function renderCalPresets() {
  const wrap = $('#calPresetWrap'), sel = $('#calPreset'), note = $('#calPresetNote');
  if (!wrap || !sel) return;
  const list = (S.profile && S.profile.calibration_presets) || [];
  wrap.hidden = list.length === 0;
  if (!list.length) return;
  sel.innerHTML = '<option value="">a measured card…</option>' +
    list.map((p, i) => `<option value="${i}">${escapeHtml(p.label)}  (dx ${p.dx}, dy ${p.dy})</option>`).join('');
  sel.onchange = () => {
    const p = list[sel.value];
    if (!p) { note.textContent = ''; return; }
    $('#calDx').value = p.dx;
    $('#calDy').value = p.dy;
    const m = p.measured_margins_mm;
    note.textContent = (m ? `Measured top ${m.top} · bottom ${m.bottom} · left ${m.left} · right ${m.right} mm. ` : '')
      + 'Loaded into the fields — print, measure your own four margins, then Save.';
    render();
  };
}

function syncClipWarning() {
  const el = $('#clipWarn');
  if (!el || !S.doc) return;
  const n = clippedElements(S.doc.faces[S.face], S.doc.card).length;
  el.hidden = n === 0;
  if (n) el.textContent = `${n} element${n > 1 ? 's' : ''} in the unprintable edge — will be cut off`;
}

/** Elements whose ink lands where the printer cannot reach.
 *  Backgrounds are exempt: they are SUPPOSED to run into the bezel. */
function clippedElements(faceDoc, card) {
  return (faceDoc.elements || []).filter((el) => {
    // An element that covers the whole card is bleeding on purpose — that is what
    // you want a background to do, and warning about it would train people to
    // ignore the warning.
    const bleeds = el.x <= 0 && el.y <= 0 &&
                   el.x + el.w >= card.w && el.y + el.h >= card.h;
    if (bleeds) return false;
    const bx = S.frame.x, by = S.frame.y;
    return el.x < bx || el.y < by ||
           el.x + el.w > card.w - bx || el.y + el.h > card.h - by;
  });
}

function drawRfid(ctx, g) {
  const c = S.doc.card;
  const ox = (c.w - RFID.outer.w) / 2, oy = (c.h - RFID.outer.h) / 2;
  const ix = (c.w - RFID.inner.w) / 2, iy = (c.h - RFID.inner.h) / 2;
  const X = (mm) => mm2px(mm, g.p);

  ctx.save();
  // Shade only the band, using even-odd so the safe interior stays clear.
  ctx.beginPath();
  ctx.rect(X(ox), X(oy), X(RFID.outer.w), X(RFID.outer.h));
  ctx.rect(X(ix), X(iy), X(RFID.inner.w), X(RFID.inner.h));
  ctx.fillStyle = 'rgba(224,103,76,.055)';
  ctx.fill('evenodd');

  ctx.strokeStyle = 'rgba(224,103,76,.45)';
  ctx.setLineDash([3, 3]);
  ctx.lineWidth = 1;
  ctx.strokeRect(X(ox), X(oy), X(RFID.outer.w), X(RFID.outer.h));
  ctx.strokeRect(X(ix), X(iy), X(RFID.inner.w), X(RFID.inner.h));
  ctx.setLineDash([]);

  if (g.p > 3) {
    ctx.fillStyle = 'rgba(224,103,76,.72)';
    ctx.font = `${Math.max(7, X(1.25))}px "SF Mono", Menlo, monospace`;
    ctx.textAlign = 'left'; ctx.textBaseline = 'middle';
    ctx.fillText('antenna', X(ox + 1.2), X(oy + (iy - oy) / 2));
  }
  ctx.restore();
}

function drawGuides(ctx, g) {
  if (!S.guides.length) return;
  ctx.save();
  ctx.strokeStyle = '#e0a63c';
  ctx.lineWidth = 1;
  S.guides.forEach((gd) => {
    ctx.beginPath();
    if (gd.axis === 'x') { const x = Math.round(mm2px(gd.mm, g.p)) + .5; ctx.moveTo(x, -6); ctx.lineTo(x, g.h + 6); }
    else { const y = Math.round(mm2px(gd.mm, g.p)) + .5; ctx.moveTo(-6, y); ctx.lineTo(g.w + 6, y); }
    ctx.stroke();
  });
  ctx.restore();
}

const HANDLES = ['nw', 'n', 'ne', 'e', 'se', 's', 'sw', 'w'];

function handlePoints(el, p) {
  const X = mm2px(el.x, p), Y = mm2px(el.y, p), W = mm2px(el.w, p), H = mm2px(el.h, p);
  return {
    nw: [X, Y], n: [X + W / 2, Y], ne: [X + W, Y], e: [X + W, Y + H / 2],
    se: [X + W, Y + H], s: [X + W / 2, Y + H], sw: [X, Y + H], w: [X, Y + H / 2],
  };
}

function drawSelection(ctx, g) {
  const el = selected();
  if (!el) return;
  const X = mm2px(el.x, g.p), Y = mm2px(el.y, g.p), W = mm2px(el.w, g.p), H = mm2px(el.h, g.p);
  ctx.save();
  ctx.strokeStyle = '#58a6f0';
  ctx.lineWidth = 1;
  ctx.strokeRect(Math.round(X) + .5, Math.round(Y) + .5, Math.round(W), Math.round(H));
  const pts = handlePoints(el, g.p);
  ctx.fillStyle = '#0d0e11';
  HANDLES.forEach((k) => {
    const [hx, hy] = pts[k];
    ctx.beginPath(); ctx.rect(hx - 3.5, hy - 3.5, 7, 7);
    ctx.fill(); ctx.stroke();
  });
  ctx.restore();
}

function selected() { return face().elements.find((e) => e.id === S.sel) || null; }

// ── hit testing + drag ───────────────────────────────────────────────────

function evtMM(e) {
  const cv = $('#canvas');
  const r = cv.getBoundingClientRect();
  const g = canvasGeom();
  return {
    x: (e.clientX - r.left - g.ox) / g.p,
    y: (e.clientY - r.top - g.oy) / g.p,
  };
}

function hitHandle(e) {
  const el = selected();
  if (!el) return null;
  const cv = $('#canvas').getBoundingClientRect();
  const g = canvasGeom();
  const px = e.clientX - cv.left - g.ox, py = e.clientY - cv.top - g.oy;
  const pts = handlePoints(el, g.p);
  return HANDLES.find((k) => Math.abs(pts[k][0] - px) <= 6 && Math.abs(pts[k][1] - py) <= 6) || null;
}

function hitElement(mm) {
  const els = face().elements;
  for (let i = els.length - 1; i >= 0; i--) {
    const el = els[i];
    if (el.hidden) continue;
    const pad = el.type === 'line' ? 1.5 : 0;
    if (mm.x >= el.x - pad && mm.x <= el.x + el.w + pad &&
        mm.y >= el.y - pad && mm.y <= el.y + el.h + pad) return el;
  }
  return null;
}

function snapCandidates(exceptId) {
  const c = S.doc.card;
  const xs = [0, c.w / 2, c.w, SAFE, c.w - SAFE];
  const ys = [0, c.h / 2, c.h, SAFE, c.h - SAFE];
  face().elements.forEach((el) => {
    if (el.id === exceptId || el.hidden) return;
    xs.push(el.x, el.x + el.w / 2, el.x + el.w);
    ys.push(el.y, el.y + el.h / 2, el.y + el.h);
  });
  return { xs, ys };
}

function snap(el, moving) {
  const TOL = 0.6;
  const { xs, ys } = snapCandidates(el.id);
  const guides = [];
  const tryAxis = (vals, cands) => {
    let best = null;
    vals.forEach(({ v, adj }) => {
      cands.forEach((c) => {
        const d = Math.abs(v - c);
        if (d < TOL && (!best || d < best.d)) best = { d, delta: c - v, at: c };
      });
    });
    return best;
  };
  if (moving) {
    const bx = tryAxis([{ v: el.x }, { v: el.x + el.w / 2 }, { v: el.x + el.w }], xs);
    const by = tryAxis([{ v: el.y }, { v: el.y + el.h / 2 }, { v: el.y + el.h }], ys);
    if (bx) { el.x += bx.delta; guides.push({ axis: 'x', mm: bx.at }); }
    if (by) { el.y += by.delta; guides.push({ axis: 'y', mm: by.at }); }
  }
  S.guides = guides;
}

function initCanvasEvents() {
  const cv = $('#canvas');

  cv.addEventListener('mousedown', (e) => {
    const mm = evtMM(e);
    const h = hitHandle(e);
    if (h) {
      const el = selected();
      S.dragging = { mode: 'resize', handle: h, start: mm, orig: { ...el } };
      return;
    }
    const el = hitElement(mm);
    S.sel = el ? el.id : null;
    buildInspector();
    if (el) S.dragging = { mode: 'move', start: mm, orig: { x: el.x, y: el.y } };
    render();
  });

  window.addEventListener('mousemove', (e) => {
    if (!S.doc) return;
    const mm = evtMM(e);
    $('#cursorReadout').textContent = `${round(mm.x, 1)} , ${round(mm.y, 1)} mm`;
    if (!S.dragging) return;
    const el = selected();
    if (!el) return;
    const dx = mm.x - S.dragging.start.x, dy = mm.y - S.dragging.start.y;

    if (S.dragging.mode === 'move') {
      el.x = round(S.dragging.orig.x + dx, 2);
      el.y = round(S.dragging.orig.y + dy, 2);
      if (e.shiftKey) { if (Math.abs(dx) > Math.abs(dy)) el.y = S.dragging.orig.y; else el.x = S.dragging.orig.x; }
      snap(el, true);
    } else {
      const o = S.dragging.orig, h = S.dragging.handle;
      const MIN = 1;
      if (h.includes('e')) el.w = Math.max(MIN, round(o.w + dx, 2));
      if (h.includes('s')) el.h = Math.max(MIN, round(o.h + dy, 2));
      if (h.includes('w')) { const nx = Math.min(o.x + dx, o.x + o.w - MIN); el.x = round(nx, 2); el.w = round(o.w + (o.x - nx), 2); }
      if (h.includes('n')) { const ny = Math.min(o.y + dy, o.y + o.h - MIN); el.y = round(ny, 2); el.h = round(o.h + (o.y - ny), 2); }
      if (e.shiftKey && o.w && o.h) {
        const ar = o.w / o.h;
        if (h === 'se' || h === 'nw' || h === 'ne' || h === 'sw') el.h = round(el.w / ar, 2);
      }
    }
    render();
    syncInspectorValues();
  });

  window.addEventListener('mouseup', () => {
    if (S.dragging) { S.dragging = null; S.guides = []; render(); }
  });

  cv.addEventListener('dblclick', () => {
    const el = selected();
    if (el && el.type === 'text') { const inp = $('#insp-text'); if (inp) { inp.focus(); inp.select(); } }
    if (el && el.type === 'image') pickImageFor(el);
  });
}

// ── layers + inspector ───────────────────────────────────────────────────

function drawLayers() {
  const ul = $('#layers');
  ul.innerHTML = '';
  face().elements.slice().reverse().forEach((el) => {
    const li = document.createElement('li');
    li.className = el.id === S.sel ? 'is-sel' : '';
    const label = el.type === 'text' ? (el.text || 'Text')
      : el.type === 'qr' ? (el.text || 'QR')
      : el.type === 'barcode' ? (el.text || 'Barcode')
      : el.type === 'image' ? (el.src ? 'Image' : 'Photo slot')
      : KINDS[el.type] || el.type;
    li.innerHTML = `<span class="l-kind">${(KINDS[el.type] || el.type).slice(0, 4)}</span>
                    <span class="l-name">${escapeHtml(String(label).slice(0, 34))}</span>
                    <span class="l-hide">${el.hidden ? '○' : '●'}</span>`;
    li.onclick = () => { S.sel = el.id; buildInspector(); render(); };
    li.querySelector('.l-hide').onclick = (ev) => { ev.stopPropagation(); el.hidden = !el.hidden; render(); };
    ul.appendChild(li);
  });
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

/* A QR that is too dense to scan wastes a physical card, and you cannot tell
 * by looking at it on screen. Report the real module pitch in millimetres and
 * say plainly when it has gone past what a phone will read. The ~v10 ceiling
 * is from decoder testing: past it, detectors struggle to localise the symbol
 * at card size even when the data is intact. */
function qrReadout(el) {
  const m = qrMatrix(resolve(el.text, null), el.ec);
  if (!m) return '<p class="note" style="color:#e0674c">Payload too long for this error-correction level — shorten it or drop to L.</p>';
  const q = el.quiet == null ? 2 : el.quiet;
  const pitch = Math.min(el.w, el.h) / (m.size + q * 2);
  const tight = pitch < 0.4;
  const dense = (m.version || 0) > 10;
  return `<p class="note">
    <span style="color:${tight ? '#e0674c' : '#8d95a3'}">v${m.version || '?'} · ${m.size}×${m.size} modules · ${round(pitch, 3)} mm per module</span>
    ${tight ? '<br><strong style="color:#e0674c">Modules under 0.4 mm — inkjet spread on PVC will close them. Enlarge the code or shorten the payload.</strong>' : ''}
    ${!tight && dense ? '<br><span style="color:#e0a63c">Version above 10 — scanners often fail to lock on at card size. Shorten the payload if you can.</span>' : ''}
  </p>`;
}

function fieldNum(label, key, step = 0.1, unit = 'mm') {
  return `<label>${label}<input type="number" data-k="${key}" step="${step}"><span class="unit">${unit}</span></label>`;
}

function buildInspector() {
  const box = $('#inspector');
  const el = selected();
  if (!el) { box.innerHTML = '<p class="empty">Select an element, or add one from the left.</p>'; return; }

  let html = `<div class="insp-group"><div class="insp-title">${KINDS[el.type] || el.type}</div>
    <div class="xy-grid">
      ${fieldNum('X', 'x')} ${fieldNum('Y', 'y')}
      ${fieldNum('W', 'w')} ${fieldNum('H', 'h')}
      ${fieldNum('Rot', 'rot', 1, '°')} ${fieldNum('Opac', 'opacity', 0.05, '')}
    </div></div>`;

  if (el.type === 'text') {
    html += `<div class="insp-group"><div class="insp-title">Content</div>
      <textarea id="insp-text" data-k="text" rows="3">${escapeHtml(el.text)}</textarea>
      <div class="field-row" style="margin-top:8px"><label>Font</label>
        <select data-k="font">${FONTS.map((f) => `<option ${f === el.font ? 'selected' : ''}>${f}</option>`).join('')}</select></div>
      <div class="xy-grid">
        ${fieldNum('Size', 'size', 0.5, 'pt')} ${fieldNum('Track', 'tracking', 0.1, '')}
        ${fieldNum('Leading', 'lineHeight', 0.05, '×')}
      </div>
      <div class="field-row" style="margin-top:7px"><label>Weight</label>
        <select data-k="weight">${[300, 400, 500, 600, 700, 800].map((w) => `<option value="${w}" ${+el.weight === w ? 'selected' : ''}>${w}</option>`).join('')}</select></div>
      <div class="field-row"><label>Align</label>
        <select data-k="align">${['left', 'center', 'right'].map((a) => `<option ${el.align === a ? 'selected' : ''}>${a}</option>`).join('')}</select></div>
      <div class="field-row"><label>Vertical</label>
        <select data-k="valign">${['top', 'middle', 'bottom'].map((a) => `<option ${el.valign === a ? 'selected' : ''}>${a}</option>`).join('')}</select></div>
      <div class="field-row"><label>Colour</label><input type="color" data-k="color" value="${el.color}"></div>
      <div class="field-row"><label></label><label class="chk"><input type="checkbox" data-k="italic" ${el.italic ? 'checked' : ''}><span>Italic</span></label></div>
    </div>`;
  }

  if (el.type === 'image') {
    html += `<div class="insp-group"><div class="insp-title">Image</div>
      <div class="btn-row"><button class="btn" id="insp-pick">Choose image…</button>
      ${el.src ? '<button class="btn btn-ghost" id="insp-clearimg">Remove</button>' : ''}</div>
      <div class="field-row" style="margin-top:8px"><label>Fit</label>
        <select data-k="fit">${['cover', 'contain', 'fill'].map((f) => `<option ${el.fit === f ? 'selected' : ''}>${f}</option>`).join('')}</select></div>
      <div class="xy-grid">${fieldNum('Radius', 'radius', 0.5)}</div>
      <div class="btn-row" style="margin-top:8px"><button class="btn btn-ghost" id="insp-circle">Make circular</button></div>
    </div>`;
  }

  if (el.type === 'rect' || el.type === 'ellipse') {
    html += `<div class="insp-group"><div class="insp-title">Fill &amp; stroke</div>
      <div class="field-row"><label>Fill</label><input type="color" data-k="fill" value="${el.fill || '#000000'}"></div>
      <div class="field-row"><label>Stroke</label><input type="color" data-k="stroke" value="${el.stroke || '#000000'}"></div>
      <div class="xy-grid">${fieldNum('Weight', 'strokeW', 0.05)}${el.type === 'rect' ? fieldNum('Radius', 'radius', 0.5) : ''}</div>
      <div class="btn-row" style="margin-top:8px"><button class="btn btn-ghost" id="insp-nostroke">No stroke</button>
      <button class="btn btn-ghost" id="insp-nofill">No fill</button></div>
    </div>`;
  }

  if (el.type === 'line') {
    html += `<div class="insp-group"><div class="insp-title">Stroke</div>
      <div class="field-row"><label>Colour</label><input type="color" data-k="stroke" value="${el.stroke}"></div>
      <div class="xy-grid">${fieldNum('Weight', 'strokeW', 0.05)}</div></div>`;
  }

  if (el.type === 'qr') {
    html += `<div class="insp-group"><div class="insp-title">QR</div>
      <textarea data-k="text" rows="2">${escapeHtml(el.text)}</textarea>
      <div class="field-row" style="margin-top:8px"><label>Correction</label>
        <select data-k="ec">${['L', 'M', 'Q', 'H'].map((v) => `<option ${el.ec === v ? 'selected' : ''}>${v}</option>`).join('')}</select></div>
      <div class="field-row"><label>Dark</label><input type="color" data-k="dark" value="${el.dark}"></div>
      <div class="field-row"><label>Light</label><input type="color" data-k="light" value="${el.light}"></div>
      <div class="xy-grid">${fieldNum('Quiet', 'quiet', 1, 'mod')}</div>
      ${qrReadout(el)}
    </div>`;
  }

  if (el.type === 'barcode') {
    html += `<div class="insp-group"><div class="insp-title">Barcode — Code 128</div>
      <input type="text" data-k="text" value="${escapeHtml(el.text)}">
      <div class="field-row" style="margin-top:8px"><label>Bars</label><input type="color" data-k="dark" value="${el.dark}"></div>
      <div class="field-row"><label>Ground</label><input type="color" data-k="light" value="${el.light}"></div>
      <div class="xy-grid">${fieldNum('Caption', 'textSize', 0.5, 'pt')}</div>
      <div class="field-row"><label></label><label class="chk"><input type="checkbox" data-k="showText" ${el.showText ? 'checked' : ''}><span>Show number</span></label></div>
    </div>`;
  }

  html += `<div class="insp-group"><div class="insp-title">Arrange</div>
    <div class="btn-row">
      <button class="btn btn-ghost" data-align="left">⇤</button>
      <button class="btn btn-ghost" data-align="cx">↔</button>
      <button class="btn btn-ghost" data-align="right">⇥</button>
      <button class="btn btn-ghost" data-align="top">⇧</button>
      <button class="btn btn-ghost" data-align="cy">↕</button>
      <button class="btn btn-ghost" data-align="bottom">⇩</button>
    </div></div>`;

  box.innerHTML = html;
  syncInspectorValues();

  box.querySelectorAll('[data-k]').forEach((inp) => {
    const k = inp.dataset.k;
    const ev = inp.type === 'checkbox' || inp.tagName === 'SELECT' || inp.type === 'color' ? 'change' : 'input';
    inp.addEventListener(ev, () => {
      const e2 = selected(); if (!e2) return;
      if (inp.type === 'checkbox') e2[k] = inp.checked;
      else if (inp.type === 'number') e2[k] = parseFloat(inp.value) || 0;
      else e2[k] = inp.value;
      render();
    });
    if (inp.type === 'number' || inp.type === 'text' || inp.tagName === 'TEXTAREA') {
      inp.addEventListener('keydown', (ev2) => ev2.stopPropagation());
    }
  });

  const on = (sel, fn) => { const n = $(sel, box); if (n) n.onclick = fn; };
  on('#insp-pick', () => pickImageFor(selected()));
  on('#insp-clearimg', () => { selected().src = ''; render(); buildInspector(); });
  on('#insp-circle', () => { const e2 = selected(); e2.h = e2.w; e2.radius = e2.w / 2; render(); buildInspector(); });
  on('#insp-nostroke', () => { selected().stroke = ''; render(); });
  on('#insp-nofill', () => { selected().fill = ''; render(); });

  box.querySelectorAll('[data-align]').forEach((b) => b.onclick = () => {
    const e2 = selected(), c = S.doc.card; if (!e2) return;
    const a = b.dataset.align;
    if (a === 'left') e2.x = SAFE;
    if (a === 'right') e2.x = c.w - SAFE - e2.w;
    if (a === 'cx') e2.x = round((c.w - e2.w) / 2, 2);
    if (a === 'top') e2.y = SAFE;
    if (a === 'bottom') e2.y = c.h - SAFE - e2.h;
    if (a === 'cy') e2.y = round((c.h - e2.h) / 2, 2);
    render(); syncInspectorValues();
  });
}

function syncInspectorValues() {
  const el = selected(); if (!el) return;
  $$('#inspector [data-k]').forEach((inp) => {
    if (document.activeElement === inp) return;
    const v = el[inp.dataset.k];
    if (inp.type === 'checkbox') inp.checked = !!v;
    else if (inp.type === 'number') inp.value = v == null ? '' : round(v, 2);
    else if (v != null) inp.value = v;
  });
}

// ── element actions ──────────────────────────────────────────────────────

function addElement(type) {
  if (type === 'image') { importPhotos(); return; }
  const el = defaults(type);
  if (type === 'photo') el.type = 'image';
  face().elements.push(el);
  S.sel = el.id;
  buildInspector();
  render();
  if (el.type === 'image') pickImageFor(el);
}

function readAsDataURL(file) {
  return new Promise((res, rej) => {
    const rd = new FileReader();
    rd.onload = () => res(rd.result);
    rd.onerror = rej;
    rd.readAsDataURL(file);
  });
}

/** Place a photo as the full card, underneath everything already on that face. */
function placeFullCard(faceIndex, src) {
  const el = defaults('image');
  el.src = src;
  el.x = 0; el.y = 0; el.w = S.doc.card.w; el.h = S.doc.card.h;
  el.fit = 'cover';
  // Bottom of the stack: a full-card image dropped on top would hide the text.
  S.doc.faces[faceIndex].elements.unshift(el);
  return el;
}

/**
 * Import one or more photos.
 *   1 photo  → fills the card. Both tray slots already print that same face,
 *              so one photo becomes both cards in the tray.
 *   2 photos → first fills the front face, second the back, and the tray is
 *              set top = front / bottom = back, so one load prints both.
 * Extra files beyond two are ignored — the tray only holds two cards.
 */
async function importPhotos(fileList) {
  const dropped = fileList ? Array.from(fileList) : null;
  const files = dropped
    ? dropped.filter((f) => f.type.startsWith('image/'))
    : await new Promise((res) => {
        const pick = $('#filePick');
        pick.multiple = true;
        pick.onchange = () => { const f = Array.from(pick.files); pick.value = ''; res(f); };
        pick.click();
      });
  if (!files.length) {
    // Silence here is the worst answer: the card is unchanged and the user has
    // no idea whether the app is broken or the file is. Name the actual reason.
    if (dropped && dropped.length) {
      const what = dropped[0].name.split('.').pop().toUpperCase();
      toast(`${what} is not an image Card Studio can place — use PNG, JPEG, GIF or WebP`, 'err');
    }
    return;
  }

  const srcs = [];
  for (const f of files.slice(0, 2)) srcs.push(await readAsDataURL(f));

  // A file can claim image/* and still be undecodable — a renamed .heic, a
  // truncated download. It would land as an element that draws nothing, which
  // reads as "the app lost my photo".
  for (let i = 0; i < srcs.length; i++) {
    const ok = await new Promise((res) => {
      const probe = new Image();
      probe.onload = () => res(true);
      probe.onerror = () => res(false);
      probe.src = srcs[i];
    });
    if (!ok) {
      toast(`${files[i].name} could not be decoded — HEIC and RAW need converting to JPEG first`, 'err');
      return;
    }
  }

  if (srcs.length === 1) {
    const el = placeFullCard(S.face, srcs[0]);
    S.sel = el.id;
    toast('Photo fills the card — both tray slots print it');
  } else {
    placeFullCard(0, srcs[0]);
    placeFullCard(1, srcs[1]);
    $('#slotA').value = 'front';
    $('#slotB').value = 'back';
    S.sel = null;
    toast('Two photos: first → top slot, second → bottom slot');
    if (files.length > 2) {
      setTimeout(() => toast(`${files.length - 2} extra photo(s) ignored — the tray holds two cards`, 'err'), 1800);
    }
  }

  await allImagesReady(S.doc);
  buildInspector();
  render();
  renderTray();
}

function pickImageFor(el) {
  if (!el) return;
  const pick = $('#filePick');
  pick.multiple = false;
  pick.onchange = () => {
    const f = pick.files[0];
    if (!f) return;
    const rd = new FileReader();
    rd.onload = () => {
      el.src = rd.result;
      const probe = new Image();
      probe.onload = () => {
        // adopt the image's aspect ratio so nothing is silently squashed
        const ar = probe.naturalWidth / probe.naturalHeight;
        if (el.fit === 'cover' && Math.abs(ar - el.w / el.h) > 0.02 && !el.radius) el.h = round(el.w / ar, 2);
        render(); buildInspector();
      };
      probe.src = rd.result;
      render(); buildInspector();
    };
    rd.readAsDataURL(f);
    pick.value = '';
  };
  pick.click();
}

function deleteSel() {
  const els = face().elements;
  const i = els.findIndex((e) => e.id === S.sel);
  if (i >= 0) { els.splice(i, 1); S.sel = null; buildInspector(); render(); }
}

function duplicateSel() {
  const el = selected(); if (!el) return;
  const copy = { ...el, id: uid(), x: el.x + 2, y: el.y + 2 };
  face().elements.push(copy);
  S.sel = copy.id;
  buildInspector(); render();
}

function reorder(dir) {
  const els = face().elements;
  const i = els.findIndex((e) => e.id === S.sel);
  if (i < 0) return;
  const j = clamp(i + dir, 0, els.length - 1);
  if (i === j) return;
  els.splice(j, 0, els.splice(i, 1)[0]);
  render();
}

// ── tray view ────────────────────────────────────────────────────────────

function slotAssignments() {
  return [$('#slotA').value, $('#slotB').value];
}

function renderTray() {
  if (!S.profile) return;
  const cv = $('#trayCanvas');
  const page = S.profile.page_mm;
  const scale = 4.4;
  const dpr = window.devicePixelRatio || 1;
  const W = page.w * scale, H = page.h * scale;
  cv.width = W * dpr; cv.height = H * dpr;
  cv.style.width = W + 'px'; cv.style.height = H + 'px';
  const ctx = cv.getContext('2d');
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

  // the tray body
  ctx.fillStyle = '#1b1e24';
  ctx.strokeStyle = '#333a45';
  ctx.lineWidth = 1;
  roundRectPath(ctx, .5, .5, W - 1, H - 1, 8);
  ctx.fill(); ctx.stroke();

  // page grid every 10 mm — reads as a measuring surface
  ctx.strokeStyle = 'rgba(255,255,255,.045)';
  for (let mm = 10; mm < page.w; mm += 10) {
    ctx.beginPath(); ctx.moveTo(mm * scale, 0); ctx.lineTo(mm * scale, H); ctx.stroke();
  }
  for (let mm = 10; mm < page.h; mm += 10) {
    ctx.beginPath(); ctx.moveTo(0, mm * scale); ctx.lineTo(W, mm * scale); ctx.stroke();
  }

  const cal = S.profile.calibration || { dx: 0, dy: 0 };
  const assigns = slotAssignments();

  S.profile.slots.forEach((slot, i) => {
    const x = (slot.x + cal.dx) * scale, y = (slot.y + cal.dy) * scale;
    const w = slot.w * scale, h = slot.h * scale;
    ctx.save();
    ctx.translate(x, y);

    const assign = assigns[i];
    if (assign && assign !== 'blank' && S.bleed) {
      // Show where the ink actually lands. The overshoot is the whole point of
      // bleed and it is also the mess on the tray, so it should be visible before
      // the print rather than discovered after it.
      ctx.save();
      ctx.fillStyle = 'rgba(224,166,60,.22)';
      ctx.fillRect(-S.bleed * scale, -S.bleed * scale,
                   w + S.bleed * 2 * scale, h + S.bleed * 2 * scale);
      ctx.restore();
    }
    if (assign && assign !== 'blank') {
      roundRectPath(ctx, 0, 0, w, h, CORNER_R * scale);
      ctx.save(); ctx.clip();
      ctx.fillStyle = '#fff'; ctx.fillRect(0, 0, w, h);
      drawFace(ctx, S.doc.faces[assign === 'back' ? 1 : 0], S.doc.card, scale,
               S.records.length ? S.records[Math.min(S.batchIndex * 2 + i, S.records.length - 1)] : null);
      ctx.restore();
      // The unprintable margin, same as the design canvas. This is the view people
      // check before committing a tray of cards, so leaving it off here meant the
      // one preview that matters showed ink reaching the edge when it will not.
      if (S.showSafe) drawBezel(ctx, w, h, scale);
      ctx.strokeStyle = 'rgba(224,166,60,.75)'; ctx.lineWidth = 1;
      roundRectPath(ctx, .5, .5, w - 1, h - 1, CORNER_R * scale); ctx.stroke();
    } else {
      roundRectPath(ctx, .5, .5, w - 1, h - 1, CORNER_R * scale);
      ctx.fillStyle = 'rgba(255,255,255,.04)'; ctx.fill();
      ctx.strokeStyle = 'rgba(255,255,255,.22)';
      ctx.setLineDash([5, 4]); ctx.lineWidth = 1; ctx.stroke(); ctx.setLineDash([]);
      ctx.fillStyle = '#6b7280';
      ctx.font = '11px "SF Mono", Menlo, monospace';
      ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
      ctx.fillText('blank card', w / 2, h / 2);
    }

    // Label lives in the tray's side margin, rotated. Above the slot it
    // collided with the card sitting above it.
    ctx.fillStyle = '#e0a63c';
    ctx.font = '600 10px "SF Mono", Menlo, monospace';
    ctx.textAlign = 'center'; ctx.textBaseline = 'bottom';
    ctx.save();
    ctx.translate(-5, h / 2);
    ctx.rotate(-Math.PI / 2);
    ctx.fillText(`${slot.name} · ${round(slot.x + cal.dx, 2)}, ${round(slot.y + cal.dy, 2)} mm`, 0, 0);
    ctx.restore();
    ctx.restore();
  });

  // feed-direction marker: the tray enters this edge first
  ctx.fillStyle = '#6b7280';
  ctx.font = '9px "SF Mono", Menlo, monospace';
  ctx.textAlign = 'center'; ctx.textBaseline = 'top';
  ctx.fillText('▲  leading edge — this side enters the printer first', W / 2, H - 14);

  $('#trayProfileName').textContent =
    `${S.profile.label} · ${page.w} × ${page.h} mm` + (cal.dx || cal.dy ? ` · offset ${round(cal.dx, 2)}, ${round(cal.dy, 2)} mm` : '');
  $('#trayNote').textContent = S.profile.geometry_note || '';
}

// ── print pipeline ───────────────────────────────────────────────────────

function currentOptions() {
  const o = {};
  const put = (k, id) => { const v = $(id).value; if (v) o[k] = v; };
  put('PageSize', '#optPageSize');
  put('InputSlot', '#optInputSlot');
  put('MediaType', '#optMediaType');
  put('cupsPrintQuality', '#optQuality');
  Object.assign(o, S.boot.profiles.print_defaults.lp_options);
  // profile media wins over the generic defaults
  Object.assign(o, {
    PageSize: $('#optPageSize').value || S.profile.cups.PageSize,
    InputSlot: $('#optInputSlot').value || S.profile.cups.InputSlot,
    MediaType: $('#optMediaType').value || S.profile.cups.MediaType,
  });
  return o;
}

async function buildPlacements(recordPair) {
  await allImagesReady(S.doc);
  const dpi = parseInt($('#dpiSel').value, 10) || 600;
  const quality = S.boot.profiles.print_defaults.jpeg_quality || 0.97;
  const assigns = slotAssignments();
  const placements = [];

  S.profile.slots.forEach((slot, i) => {
    const assign = assigns[i];
    if (!assign || assign === 'blank') return;
    const faceDoc = S.doc.faces[assign === 'back' ? 1 : 0];
    const rec = recordPair ? recordPair[i] : null;
    if (recordPair && !rec) return;                     // odd final pair — leave the slot unprinted
    const bleed = S.bleed || 0;
    const cv = rasterise(faceDoc, S.doc.card, dpi, rec, bleed);
    placements.push({
      image: cv.toDataURL('image/jpeg', quality),
      x_mm: slot.x - bleed, y_mm: slot.y - bleed,
      w_mm: slot.w + bleed * 2, h_mm: slot.h + bleed * 2,
      rotate_deg: slot.rotate || 0,
    });
  });
  return placements;
}

function printPayload(placements, name) {
  const cal = S.profile.calibration || { dx: 0, dy: 0 };
  return {
    page_mm: S.profile.page_mm,
    dx: cal.dx, dy: cal.dy,
    placements,
    name: name || S.doc.name,
    printer: S.printer,
    options: currentOptions(),
    copies: parseInt($('#copies').value, 10) || 1,
  };
}

async function doPrint(recordPair, label) {
  try {
    setStatus('rasterising…');
    const placements = await buildPlacements(recordPair);
    if (!placements.length) { toast('Both slots are set to blank — nothing to print.', 'err'); setStatus(''); return; }
    setStatus('sending to ' + S.printer + '…');
    const res = await api('/api/print', printPayload(placements, label));
    const log = $('#printLog');
    log.textContent = [res.command, res.stdout, res.stderr, 'pdf: ' + res.pdf].filter(Boolean).join('\n');
    if (res.ok && res.web) {
    // The web build downloaded a file; saying "queued" would describe a printer
    // that was never involved.
    toast('Downloaded ' + res.file + ' — print it at 100% scale', 'ok');
    setStatus(res.file);
  } else if (res.ok) { toast('Sent — ' + (res.job || 'queued'), 'ok'); setStatus('job ' + (res.job || '')); }
    else { toast('Print failed: ' + (res.stderr || 'see log'), 'err'); setStatus('print failed'); }
    setTimeout(refreshPrinterStatus, 4000);
    setTimeout(refreshPrinterStatus, 12000);
  } catch (err) {
    toast('Print error: ' + err.message, 'err');
    setStatus('error');
  }
}

/* Rasterise through the real CUPS filter chain and read the output size back.
 * A PDF whose page does not exactly match the media is silently cropped rather
 * than reported, so this is the only way to catch a geometry mistake without
 * spending a card. */
async function doDryRun() {
  try {
    setStatus('dry run — rasterising through the print filters…');
    const placements = await buildPlacements(null);
    if (!placements.length) { toast('Both slots are blank.', 'err'); setStatus(''); return; }
    const res = await api('/api/dryrun', printPayload(placements, 'dryrun'));
    const log = $('#printLog');
    if (!res.ok) {
      log.textContent = [res.command, res.error, res.stderr].filter(Boolean).join('\n');
      toast('Dry run failed: ' + (res.error || 'see log'), 'err');
      setStatus('dry run failed');
      return;
    }
    const page = S.profile.page_mm;
    const dw = Math.abs(res.width_mm - page.w), dh = Math.abs(res.height_mm - page.h);
    const good = dw < 0.15 && dh < 0.15;
    log.textContent =
      `raster   ${res.width_px} × ${res.height_px} px @ ${res.dpi} dpi, ${res.bpp} bpp\n` +
      `output   ${res.width_mm} × ${res.height_mm} mm\n` +
      `expected ${page.w} × ${page.h} mm\n` +
      (good ? '✓ geometry matches the media exactly — safe to print'
            : '✗ MISMATCH — the print would be cropped or shifted. Do not load cards.') +
      (res.bpp && res.bpp < 24 ? `\nnote: ${res.bpp} bpp — the filters treated this as greyscale.` : '') +
      `\n\n${res.command}`;
    toast(good ? `Geometry confirmed: ${res.width_mm} × ${res.height_mm} mm` : 'Geometry MISMATCH — see log',
          good ? 'ok' : 'err');
    setStatus(good ? 'dry run clean' : 'dry run mismatch');
  } catch (err) {
    toast('Dry run error: ' + err.message, 'err');
    setStatus('error');
  }
}

/* The printer only ever says "Check the printer." plus a number on its screen.
 * Surfacing that number, and what it means, is the difference between a
 * two-second fix and an evening of guessing. */
function renderPrinterStatus(st) {
  const box = $('#printerStatus');
  if (!st) { box.innerHTML = '<div class="pstat-line"><span class="pstat-dot is-unknown"></span><span>unavailable</span></div>'; return; }

  const blocked = !!st.support_code || !st.queue_enabled;
  const cls = blocked ? 'is-bad' : (st.reachable ? 'is-good' : 'is-warn');
  const head = !st.reachable ? 'printer not reachable on the network'
    : !st.queue_enabled ? 'print queue is stopped'
    : st.support_code ? `printer needs attention — code ${st.support_code}`
    : (st.lcd || 'ready');

  let html = `<div class="pstat-line"><span class="pstat-dot ${cls}"></span><strong>${escapeHtml(head)}</strong></div>`;

  if (st.support_code) {
    html += `<div class="pstat-fix">
      ${st.support_title ? `<div class="pstat-fix-t">${escapeHtml(st.support_title)}</div>` : ''}
      ${st.support_fix ? `<div>${escapeHtml(st.support_fix)}</div>`
                       : '<div>See Canon\'s page for this code.</div>'}
      <a href="${st.support_url}" target="_blank" rel="noopener">Canon support code ${st.support_code} →</a>
    </div>`;
  }

  html += `<div class="pstat-grid">
    <span>queue</span><span>${st.queue_enabled ? 'enabled' : 'STOPPED'}</span>
    <span>pending jobs</span><span>${st.pending_jobs}</span>
    ${st.lcd ? `<span>display</span><span>${escapeHtml(st.lcd)}</span>` : ''}
    ${st.host ? `<span>host</span><span>${escapeHtml(st.host)}</span>` : ''}
  </div>`;

  if (st.ink && st.ink.length) {
    html += '<div class="ink">' + st.ink.map((i) => {
      const lvl = Math.max(0, Math.min(100, i.level));
      // "Canon Magenta Ink Tank" -> "MAG". Slicing the raw name just gave
      // five cartridges all labelled "Cano".
      const label = (i.name.replace(/canon|ink|tank|cartridge/gi, '').replace(/[^A-Za-z]/g, '')
                     || i.name).slice(0, 3).toUpperCase();
      const tint = /magenta/i.test(i.name) ? '#d94fd0' : /cyan/i.test(i.name) ? '#3fb6d8'
                 : /yellow/i.test(i.name) ? '#d9c02a' : '#9aa1aa';
      return `<div class="ink-cell" title="${escapeHtml(i.name)} — ${lvl}%">
        <div class="ink-bar"><span style="height:${lvl}%;background:${tint}"></span></div>
        <div class="ink-lab">${escapeHtml(label)}</div></div>`;
    }).join('') + '</div>';
  }
  box.innerHTML = html;
}

/* Answers "is the tray actually selected?" by asking the printer itself with
 * an IPP Validate-Job — the real media-col on the wire, no ink, no card. */
async function checkTray() {
  const btn = $('#btnCheckTray');
  btn.disabled = true; const was = btn.textContent; btn.textContent = 'Checking…';
  try {
    const r = await api('/api/validate-tray', {
      printer: S.printer, page_mm: S.profile.page_mm, options: currentOptions(),
    });
    $('#printLog').textContent =
      (r.ok ? '\u2713 the printer ACCEPTED this exact job\n' : '\u2717 the printer REJECTED this job\n') +
      `status   ${r.status || r.error}\n` +
      (r.sent ? Object.entries(r.sent).map(([k, v]) => `${k.padEnd(14)} ${v}`).join('\n') : '');
    toast(r.ok ? `Tray selection confirmed — media-source=${r.sent['media-source']}`
               : `Printer rejected it: ${r.status || r.error}`, r.ok ? 'ok' : 'err');
  } catch (err) {
    toast('Check failed: ' + err.message, 'err');
  } finally { btn.disabled = false; btn.textContent = was; }
}

async function refreshPrinterStatus() {
  try {
    renderPrinterStatus(await api('/api/printer-status', { printer: S.printer }));
  } catch (err) { renderPrinterStatus(null); }
}

async function resetPrinter() {
  const btn = $('#btnResetPrinter');
  btn.disabled = true;
  const was = btn.textContent;
  btn.textContent = 'Resetting…';
  try {
    const res = await api('/api/reset-printer', { printer: S.printer });
    renderPrinterStatus(res.status);
    $('#printLog').textContent = res.steps.map((s) => `${s.ok ? 'ok  ' : 'FAIL'} ${s.step}${s.detail ? ' — ' + s.detail : ''}`).join('\n');
    const st = res.status || {};
    if (st.support_code) toast(`Queue cleared, but the printer still reports code ${st.support_code}`, 'err');
    else toast('Queue cleared — printer back to idle', 'ok');
  } catch (err) {
    toast('Reset failed: ' + err.message, 'err');
  } finally {
    btn.disabled = false;
    btn.textContent = was;
  }
}

async function doPdf() {
  try {
    setStatus('rasterising…');
    const placements = await buildPlacements(null);
    if (!placements.length) { toast('Both slots are blank.', 'err'); setStatus(''); return; }
    const res = await api('/api/pdf', printPayload(placements));
    $('#printLog').textContent = 'pdf: ' + res.pdf;
    toast('PDF written', 'ok');
    setStatus(res.pdf);
  } catch (err) { toast('PDF error: ' + err.message, 'err'); }
}

// ── calibration target ───────────────────────────────────────────────────

/* The calibration target.
 *
 * The readout trick: anything printed past a card edge simply never appears —
 * it lands on the tray, not the card. So a ladder of ticks numbered by their
 * distance from an edge reads the offset directly: if the print has shifted
 * 3 mm toward the left edge, ticks 0, 1 and 2 fall off the card and the first
 * one you can see is 3. No ruler needed for that direction.
 *
 * The two ladders are deliberately placed apart from each other and away from
 * the corner — an earlier version stacked them in the top-left and they were
 * unreadable where it mattered most.
 */
function calibrationFace() {
  const c = S.doc.card;
  const els = [];
  const push = (o) => els.push({ id: uid(), rot: 0, opacity: 1, ...o });
  const TICKS = 14;
  const HAIR = 0.22;

  // 5 mm inset frame — the coarse, at-a-glance check
  push({ type: 'rect', x: 5, y: 5, w: c.w - 10, h: c.h - 10, fill: '', stroke: '#000000', strokeW: 0.22, radius: 0 });

  // corner L at the intended (0,0): if alignment is perfect it hugs the corner
  push({ type: 'rect', x: 0, y: 0, w: 12, h: 0.4, fill: '#000000' });
  push({ type: 'rect', x: 0, y: 0, w: 0.4, h: 12, fill: '#000000' });

  // ── dx ladder: vertical ticks numbered by distance from the LEFT edge ──
  const dxY = 19, dxH = 5;
  for (let mm = 0; mm <= TICKS; mm++) {
    const major = mm % 5 === 0;
    push({ type: 'rect', x: mm, y: dxY, w: HAIR, h: major ? dxH : dxH * 0.5, fill: '#000000' });
    // Labels start AT their tick and read rightward. Centring them put the
    // "0" label at x = -3 mm, off the card — and 0 is the one you must read.
    if (major) push({ type: 'text', x: mm + 0.5, y: dxY + dxH + 0.4, w: 6, h: 3, text: String(mm),
                      font: 'Menlo', size: 5, weight: 700, color: '#000000',
                      align: 'left', valign: 'top', lineHeight: 1 });
  }
  push({ type: 'text', x: 0, y: dxY - 3.4, w: 26, h: 3, text: 'FROM LEFT EDGE →', font: 'Menlo',
         size: 4, weight: 700, color: '#000000', align: 'left', valign: 'middle', lineHeight: 1 });

  // ── dy ladder: horizontal ticks numbered by distance from the TOP edge ──
  const dyX = 46, dyW = 5;
  for (let mm = 0; mm <= TICKS; mm++) {
    const major = mm % 5 === 0;
    push({ type: 'rect', x: dyX, y: mm, w: major ? dyW : dyW * 0.5, h: HAIR, fill: '#000000' });
    if (major) push({ type: 'text', x: dyX + dyW + 0.6, y: mm + 0.3, w: 7, h: 3, text: String(mm),
                      font: 'Menlo', size: 5, weight: 700, color: '#000000',
                      align: 'left', valign: 'top', lineHeight: 1 });
  }
  push({ type: 'text', x: dyX - 1, y: TICKS + 1.4, w: 30, h: 3, text: '↓ FROM TOP EDGE', font: 'Menlo',
         size: 4, weight: 700, color: '#000000', align: 'left', valign: 'top', lineHeight: 1 });

  const cal = S.profile.calibration || { dx: 0, dy: 0 };
  push({ type: 'text', x: 6, y: 31, w: 74, h: 5, text: 'CARD STUDIO — TRAY CALIBRATION', font: 'Menlo',
         size: 6.5, weight: 700, color: '#000000', align: 'left', valign: 'middle', lineHeight: 1.2 });
  push({ type: 'text', x: 6, y: 36, w: 74, h: 13,
         text: `Read the LOWEST tick number you can still see on each ladder.\n`
             + `If tick 0 is visible but sits inside the edge, measure that gap\n`
             + `and enter it as a negative number.   offset now ${round(cal.dx, 2)}, ${round(cal.dy, 2)} mm`,
         font: 'Menlo', size: 4.6, weight: 400, color: '#000000', align: 'left', valign: 'top', lineHeight: 1.6 });

  // opposite-corner L, so an overshoot the other way is also visible
  push({ type: 'rect', x: c.w - 12, y: c.h - 0.4, w: 12, h: 0.4, fill: '#000000' });
  push({ type: 'rect', x: c.w - 0.4, y: c.h - 12, w: 0.4, h: 12, fill: '#000000' });

  return { bg: { type: 'color', color: '#ffffff' }, elements: els };
}

async function calibrationPlacements() {
  const dpi = parseInt($('#dpiSel').value, 10) || 600;
  const f = calibrationFace();
  return S.profile.slots.map((slot) => ({
    /* `null` frame, always. The target's whole job is to show where the ink
     * lands relative to the card edge — a frame over it destroys the reading it
     * exists to give, and does it invisibly, by painting out the low ticks. */
    image: rasterise(f, S.doc.card, dpi, null, 0, null).toDataURL('image/jpeg', 0.97),
    x_mm: slot.x, y_mm: slot.y, w_mm: slot.w, h_mm: slot.h, rotate_deg: slot.rotate || 0,
  }));
}

// ── batch ────────────────────────────────────────────────────────────────

function parseCSV(text) {
  const rows = [];
  let row = [], cur = '', q = false;
  for (let i = 0; i < text.length; i++) {
    const ch = text[i];
    if (q) {
      if (ch === '"' && text[i + 1] === '"') { cur += '"'; i++; }
      else if (ch === '"') q = false;
      else cur += ch;
    } else if (ch === '"') q = true;
    else if (ch === ',') { row.push(cur); cur = ''; }
    else if (ch === '\n') { row.push(cur); rows.push(row); row = []; cur = ''; }
    else if (ch !== '\r') cur += ch;
  }
  if (cur || row.length) { row.push(cur); rows.push(row); }
  return rows.filter((r) => r.some((c) => c.trim() !== ''));
}

function loadCSV(text) {
  const rows = parseCSV(text.trim());
  if (rows.length < 2) { S.records = []; S.fields = []; renderBatch(); return; }
  const heads = rows[0].map((h) => h.trim());
  S.fields = heads;
  S.records = rows.slice(1).map((r) => {
    const o = {};
    heads.forEach((h, i) => { o[h] = (r[i] || '').trim(); });
    return o;
  });
  S.batchIndex = 0;
  renderBatch();
  renderTray();
}

function renderBatch() {
  const chips = $('#fieldChips');
  chips.innerHTML = S.fields.map((f) => `<span class="chip" data-f="${escapeHtml(f)}">{{${escapeHtml(f)}}}</span>`).join('');
  chips.querySelectorAll('.chip').forEach((c) => c.onclick = () => {
    navigator.clipboard.writeText(`{{${c.dataset.f}}}`).then(() => toast(`Copied {{${c.dataset.f}}}`));
  });

  const grid = $('#batchGrid');
  grid.innerHTML = '';
  const which = $('#batchDesign').value === 'back' ? 1 : 0;
  const pair = Math.floor(S.batchIndex);
  S.records.forEach((rec, i) => {
    const wrap = document.createElement('div');
    wrap.className = 'batch-card' + (Math.floor(i / 2) === pair ? ' is-now' : '');
    const cv = document.createElement('canvas');
    const scale = 2.6, dpr = window.devicePixelRatio || 1;
    cv.width = S.doc.card.w * scale * dpr;
    cv.height = S.doc.card.h * scale * dpr;
    const ctx = cv.getContext('2d');
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.fillStyle = '#fff';
    ctx.fillRect(0, 0, S.doc.card.w * scale, S.doc.card.h * scale);
    drawFace(ctx, S.doc.faces[which], S.doc.card, scale, rec);
    wrap.appendChild(cv);
    const cap = document.createElement('div');
    cap.className = 'bc-cap';
    cap.innerHTML = `<span>#${i + 1}</span><span>${escapeHtml((rec[S.fields[0]] || '').slice(0, 18))}</span>`;
    wrap.appendChild(cap);
    wrap.onclick = () => { S.batchIndex = Math.floor(i / 2); renderBatch(); renderTray(); };
    grid.appendChild(wrap);
  });

  const pairs = Math.ceil(S.records.length / 2);
  $('#batchCount').textContent = S.records.length ? `${S.records.length} cards · ${pairs} tray loads` : '';
  $('#runState').textContent = S.records.length
    ? `Load ${S.batchIndex + 1} of ${pairs} — cards #${S.batchIndex * 2 + 1}${S.batchIndex * 2 + 2 <= S.records.length ? ' and #' + (S.batchIndex * 2 + 2) : ' (single, pair the slot with a blank)'}`
    : 'No data loaded.';
}

async function batchPrint() {
  if (!S.records.length) { toast('Load CSV data first.', 'err'); return; }
  const which = $('#batchDesign').value === 'back' ? 'back' : 'front';
  $('#slotA').value = which; $('#slotB').value = which;
  const pair = [S.records[S.batchIndex * 2], S.records[S.batchIndex * 2 + 1]];
  await doPrint(pair, `${S.doc.name}-batch-${S.batchIndex + 1}`);
}

// ── boot ─────────────────────────────────────────────────────────────────

function fillSelect(sel, values, current) {
  sel.innerHTML = values.map((v) => `<option ${v === current ? 'selected' : ''}>${escapeHtml(v)}</option>`).join('');
}

function applyProfile(key) {
  S.profileKey = key;
  S.profile = JSON.parse(JSON.stringify(S.boot.profiles.profiles[key]));
  $('#brandSub').textContent = `${S.profile.label} · ${S.profile.page_mm.w}×${S.profile.page_mm.h} mm`;
  const cal = S.profile.calibration || { dx: 0, dy: 0 };
  $('#calDx').value = cal.dx; $('#calDy').value = cal.dy;
  renderGeomTable();
  renderTray();
}

function renderGeomTable() {
  const p = S.profile;
  const cal = p.calibration || { dx: 0, dy: 0 };
  const rows = [
    ['profile', p.label],
    ['page', `${p.page_mm.w} × ${p.page_mm.h} mm`],
    ['card', `${S.doc.card.w} × ${S.doc.card.h} mm`],
    ...p.slots.map((s) => [`slot ${s.name}`, `${round(s.x + cal.dx, 2)}, ${round(s.y + cal.dy, 2)} mm`]),
    ['offset', `${round(cal.dx, 2)}, ${round(cal.dy, 2)} mm`],
    ['confidence', p.geometry_confidence || '—'],
    ['media', `${p.cups.PageSize} / ${p.cups.InputSlot} / ${p.cups.MediaType}`],
  ];
  $('#geomTable').innerHTML = rows.map(([a, b]) => `<tr><td>${escapeHtml(a)}</td><td>${escapeHtml(String(b))}</td></tr>`).join('');
  $('#geomNote').textContent = p.page_source || '';
}

function renderCalPreview() {
  const cv = $('#calPreview');
  if (!cv) return;
  // Size the backing store from the panel's real width so the preview scales
  // with the layout instead of overflowing it.
  const avail = Math.max(240, cv.parentElement.clientWidth - 2);
  const scale = avail / S.doc.card.w;
  const dpr = window.devicePixelRatio || 1;
  cv.width = Math.round(S.doc.card.w * scale * dpr);
  cv.height = Math.round(S.doc.card.h * scale * dpr);
  cv.style.width = '100%';
  cv.style.height = 'auto';
  const ctx = cv.getContext('2d');
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.fillStyle = '#fff';
  ctx.fillRect(0, 0, S.doc.card.w * scale, S.doc.card.h * scale);
  drawFace(ctx, calibrationFace(), S.doc.card, scale, null);
}

/* The buying guide, which is a SHOP and not a manual.
 *
 * It used to open with a diagnosis panel, a reader spec table, and six cards of
 * roughly a hundred and fifty words each — about nine hundred words to buy a $17
 * pack of cards. All of it was true and almost none of it was read. The failure
 * is not that the writing was bad; it is that a tab you visit to BUY something
 * was answering a question nobody had asked yet.
 *
 * So the tile carries what a purchase decision actually needs — a picture, a
 * price, one line, a button — and every word of the old guide is still here, one
 * disclosure away, where it is reference rather than an obstacle. Nothing was
 * deleted. It was demoted.
 *
 * The search string keeps its place inside the details, because a product link
 * rots in a month and "inkjet printable PVC cards CR80 30 mil" keeps working. */
function renderSupplies() {
  const sup = S.boot.supplies;
  if (!sup) return;
  const box = $('#suppliesView');
  const d = sup.diagnosis;
  const r = sup.your_reader;

  const tile = (it) => {
    const o = it.owned;
    // Every list is defaulted. One item missing one optional key used to throw
    // inside this template and blank the WHOLE tab, and the symptom — "supplies
    // shows nothing" — points nowhere near the one short row that caused it.
    const detail = `
      ${o ? `<p class="s-you"><strong>You bought:</strong> ${escapeHtml(o.product)} —
        ${escapeHtml(o.vendor)}, ${escapeHtml(o.pack)}, ${escapeHtml(o.price)}.
        <a href="${escapeHtml(o.url)}" target="_blank" rel="noopener">Re-order →</a></p>` : ''}
      <div class="s-search"><code>${escapeHtml(it.search)}</code>
        <button class="btn" data-copy="${escapeHtml(it.id)}">Copy</button></div>
      <div class="s-kw">
        ${(it.must_say || []).map((k) => `<span class="k yes">${escapeHtml(k)}</span>`).join('')}
        ${(it.avoid || []).map((k) => `<span class="k no">${escapeHtml(k)}</span>`).join('')}
      </div>
      <table class="s-specs">${(it.specs || []).map(([a, b, c]) =>
        `<tr><th>${escapeHtml(a)}</th><td>${escapeHtml(b)}</td><td class="s-why">${escapeHtml(c)}</td></tr>`).join('')}</table>
      ${(it.links || []).length > 1 ? `<div class="s-links">${(it.links || []).slice(1).map((l) =>
        `<a href="${escapeHtml(l.url)}" target="_blank" rel="noopener">${escapeHtml(l.label)} →</a>`).join('')}</div>` : ''}
      ${it.note ? `<p class="s-note">${escapeHtml(it.note)}</p>` : ''}`;

    return `<article class="s-tile${o ? ' is-owned' : ''}">
      <div class="s-art"><img src="${escapeHtml(it.art)}" alt="" width="160" height="108" loading="lazy"></div>
      <div class="s-body">
        <div class="s-need">${escapeHtml(it.need)}${o ? '<span class="s-tag">Bought</span>' : ''}</div>
        <h3>${escapeHtml(it.title.split('—')[0].trim())}</h3>
        <p class="s-blurb">${escapeHtml(it.blurb)}</p>
        <div class="s-foot">
          <span class="s-price">${escapeHtml(it.price)}</span>
          ${it.buy ? `<a class="s-buy" href="${escapeHtml(it.buy)}" target="_blank" rel="noopener">Buy</a>` : ''}
        </div>
        <details class="s-more"><summary>Specs &amp; what to avoid</summary>${detail}</details>
      </div>
    </article>`;
  };

  box.innerHTML = `
    <div class="s-grid">${sup.items.map(tile).join('')}</div>
    <details class="s-help">
      <summary>Ink beaded up, smeared, or wiped off?</summary>
      <p>${escapeHtml(d.cause)}</p>
      <ul>${d.checks.map((c) => `<li>${escapeHtml(c)}</li>`).join('')}</ul>
    </details>
    ${r ? `<details class="s-help"><summary>Your reader — ${escapeHtml(r.model)}</summary>
      <table class="s-specs">
        <tr><th>Reads</th><td colspan="2">${escapeHtml(r.proven_type)}</td></tr>
        <tr><th>Detected</th><td colspan="2">${escapeHtml(r.detected)}</td></tr>
        <tr><th>Evidence</th><td colspan="2">${escapeHtml(r.evidence)}</td></tr>
        <tr><th>Dual?</th><td colspan="2">${escapeHtml(r.dual_note)}</td></tr>
      </table>
      <p class="s-note"><strong>Free test —</strong> ${escapeHtml(r.free_test)}</p></details>` : ''}
    <details class="s-help"><summary>After printing</summary>
      <ul>${sup.handling.map((h) => `<li>${escapeHtml(h)}</li>`).join('')}</ul>
    </details>
    ${(sup.faq && sup.faq.length) ? `<details class="s-help"><summary>Questions that cost cards</summary>
      ${sup.faq.map((f) => `<div class="s-faq"><div class="s-q">${escapeHtml(f.q)}</div>
        <div class="s-a">${escapeHtml(f.a)}</div></div>`).join('')}
    </details>` : ''}`;

  box.querySelectorAll('[data-copy]').forEach((b) => b.onclick = () => {
    const it = sup.items.find((x) => x.id === b.dataset.copy);
    navigator.clipboard.writeText(it.search).then(() => {
      const was = b.textContent; b.textContent = 'Copied';
      setTimeout(() => { b.textContent = was; }, 1400);
      toast('Search terms copied — paste into Amazon or any search box');
    });
  });
}

/* Hide what this build genuinely cannot do, rather than leaving a control that
 * fails when pressed. Driven entirely by CS_BACKEND.capabilities, so adding a
 * capability to a backend is the only edit needed — there is no "if web" branch
 * anywhere else in this file.
 *
 * HIDDEN, not removed from the DOM: boot() and wireUI() address these nodes by
 * id (fillSelect on #printerSel, handlers on the print buttons), and deleting
 * them would mean guarding every one of those call sites against null. Hiding
 * gives the user the same honest surface with none of that risk. */
function applyCapabilities() {
  const hide = (sel) => document.querySelectorAll(sel).forEach((el) => {
    const row = el.closest('.field-row') || el;
    row.style.display = 'none';
  });

  if (!can('printerDiscovery')) {
    hide('#printerSel, #btnRefreshStatus, #btnResetPrinter, #btnEnableQueue');
    // These are CUPS job options. Without a print path they set nothing.
    // #dpiSel deliberately survives: it chooses the raster the PDF embeds.
    hide('#optPageSize, #optInputSlot, #optMediaType, #optQuality, #copies');
    const st = $('#printerStatus');
    if (st && st.closest('.panel')) st.closest('.panel').style.display = 'none';
  }
  if (!can('trayValidation')) hide('#btnCheckTray, #btnDryRun');
  if (!can('revealInFinder')) hide('#btnReveal');
  if (!can('batch')) hide('.tab[data-view="batch"]');
  if (!can('nfc')) hide('.tab[data-view="chip"]');

  if (!can('printing')) {
    // The button still does the most useful thing a page can do, so it is
    // relabelled rather than removed — and the label says exactly what happens.
    const p = $('#btnPrint'), top = $('#btnPrintTop'), pdf = $('#btnPdf');
    if (p) p.textContent = 'Download print-ready PDF';
    if (top) top.textContent = 'Download PDF';
    if (pdf) pdf.style.display = 'none';        // same action as the button above it
    document.body.classList.add('is-web-build');

    /* The likeliest real-world failure in this build is not a bug in it. The
     * PDF is exact; then a print dialog defaulting to "Fit to page" scales a
     * 120mm page down and prints a flawless, useless, wrong-sized card. The PDF
     * asks not to be scaled (/PrintScaling /None) but drivers may ignore it, so
     * it is also said in words, at the moment of the action rather than in a
     * README nobody opens. */
    const host = p && p.parentElement;
    if (host && !$('#webPrintNote')) {
      const note = document.createElement('p');
      note.id = 'webPrintNote';
      note.className = 'web-note';
      note.innerHTML =
        '<strong>Print it at 100%.</strong> In the print dialog set Scale to 100% ' +
        'and Paper Size to your 120 × 120 mm tray media — <em>not</em> "Fit to Page", ' +
        'which shrinks the page and prints undersized cards. ' +
        'For direct printing, tray validation and a no-ink dry run, use the desktop app.';
      host.appendChild(note);
    }
  }
}

/* ───────────────────────────── CHIP ─────────────────────────────
 * The reader half. Two things shape everything here.
 *
 * 1. api() does NOT throw on a 200 that carries {ok:false}. backend.js only throws
 *    when the HTTP status is an error, and nfcio answers every domain failure — no
 *    card, unformatted tag, locked tag, failed verify — as a 200 with ok:false. So
 *    every call below checks .ok explicitly. A try/catch here would catch nothing.
 *
 * 2. A card is untrusted input. Anything read off a tag goes through escapeHtml
 *    before it reaches innerHTML, and the URL is rendered as TEXT, never as a link:
 *    a tag can carry a scheme we refuse, and a clickable href is a different promise
 *    than a printed string. Nothing here fetches what the card points at.
 */

function chipDot(kind, text) {
  return `<div class="pstat-line"><span class="pstat-dot is-${kind}"></span><span>${escapeHtml(text)}</span></div>`;
}

function renderChipStatus() {
  const el = $('#chipStatus'); if (!el) return;
  const n = S.nfc;
  if (n.available === false) {
    el.innerHTML = chipDot('bad', 'no card reader on this machine');
  } else if (!n.reader) {
    el.innerHTML = chipDot('unknown', 'looking for a reader…');
  } else if (!n.present) {
    el.innerHTML = chipDot('warn', `${n.reader} — put a card on it`);
  } else {
    el.innerHTML = chipDot('good', `${n.reader} — card detected`);
  }
}

function renderChipCard() {
  const box = $('#chipCard'); if (!box) return;
  const c = S.nfc.card;
  if (!c) { box.innerHTML = ''; return; }
  if (!c.ok) { box.innerHTML = `<p class="chip-err">${escapeHtml(c.error || 'could not read this card')}</p>`; return; }

  const rows = [];
  const add = (k, v) => rows.push(`<div class="chip-row"><span>${escapeHtml(k)}</span><code>${escapeHtml(String(v))}</code></div>`);
  add('chip', c.chip || 'unknown');
  add('uid', c.uid || '—');
  if (c.capacity) add('capacity', `${c.capacity} bytes`);
  if (c.locked) add('locked', 'yes — this card can no longer be rewritten');

  if (c.url) add('address', c.url);
  // A payload our own policy refuses never appears as an address. It is shown as
  // raw text with the reason, because hiding it entirely would leave the user
  // staring at a card that reads "empty" while it demonstrably is not.
  if (c.url_raw) rows.push(`<div class="chip-row is-bad"><span>refused</span><code>${escapeHtml(c.url_raw)}</code></div>`
    + `<p class="chip-err">${escapeHtml(c.url_unsafe || '')}</p>`);
  if (c.epitaph) add('identity', c.epitaph);
  if (!c.url && !c.url_raw && !c.epitaph) add('contents', c.empty ? 'blank — nothing written yet' : 'unreadable');

  let head = '';
  if (c.card) {
    const d = c.card;
    head = `<div class="chip-id">${escapeHtml(d.id || '')}</div>`
         + `<div class="chip-title">${escapeHtml(d.title || '')}</div>`
         + `<div class="chip-meta">${escapeHtml([d.date, d.license, d.tool].filter(Boolean).join(' · '))}</div>`;
  }
  box.innerHTML = head + rows.join('');
}

async function readChip() {
  if (S.nfc.busy) return;                 // a write is in flight; do not queue behind it
  const st = await api('/api/nfc/status');
  S.nfc.available = st.available !== false;
  S.nfc.reader = st.reader || null;
  // `busy` means another operation holds the reader — not "no card". Leave the last
  // known presence alone rather than flickering the UI to "put a card on it".
  if (!st.busy) S.nfc.present = !!st.card_present;
  renderChipStatus();

  if (!S.nfc.present) {
    // Card lifted. Arm the next arrival — this is what makes "tap again to open
    // again" work, and what stops the 1.2 s poll from re-opening a tab forever
    // while a card simply sits there.
    S.nfc.card = null;
    S.nfc.openedFor = null;
    renderChipCard();
    return;
  }
  const card = await api('/api/nfc/read');
  if (card.busy) return;
  S.nfc.card = card;
  renderChipCard();
  maybeAutoOpen(card);
}

/** Open the card's address on arrival, once per arrival.
 *
 *  Fires on the transition to present, keyed by uid+url, and re-arms only when the
 *  card is removed. Without that key a polling loop opens a new browser tab every
 *  1.2 seconds for as long as the card lies on the reader — which is not a feature,
 *  it is a fork bomb made of tabs.
 *
 *  The server re-reads the tag and opens what is actually on it; this call carries no
 *  URL, so nothing here can steer where the browser goes. */
async function maybeAutoOpen(card) {
  if (!$('#chipAutoOpen')?.checked) return;
  if (!card || !card.ok || !card.url) return;
  const key = `${card.uid}|${card.url}`;
  if (S.nfc.openedFor === key) return;
  S.nfc.openedFor = key;                       // set BEFORE awaiting, or two polls race
  const r = await api('/api/nfc/open');
  if (r.ok) {
    toast('opening ' + r.url, 'ok');
  } else {
    // A refusal is worth showing: it is usually a card pointing somewhere the
    // browser should not be sent, and silence would read as "nothing happened".
    toast(r.error || 'could not open this card', 'err');
    const out = $('#chipWriteResult');
    if (out) out.innerHTML = `<p class="chip-err">${escapeHtml(r.error || '')}</p>`;
  }
}

function startChipPolling() {
  stopChipPolling();
  readChip();
  // Only while the view is open. status() costs a few ms, but a timer that runs when
  // nobody is looking is how a desktop app quietly becomes a background process.
  S.nfc.poll = setInterval(readChip, 1200);
}

function stopChipPolling() {
  if (S.nfc.poll) { clearInterval(S.nfc.poll); S.nfc.poll = null; }
}

/** Fill the inputs so writing is one click. A suggestion only — it never writes,
 *  because the bytes go onto a physical object.
 *
 *  The card ON THE READER wins over the design on screen. Re-programming an existing
 *  card is the common case by a distance, and the design's name is usually wrong for
 *  it: a card saved as "Untitled Card" would suggest the id UNTITLED-CARD for a tag
 *  already correctly stamped CARD-001. Read what is there, offer it back, let the
 *  user edit. Falling back to the design only matters for a blank tag. */
function chipFillFromDesign() {
  const url = $('#chipUrl'), epi = $('#chipEpitaph');
  const c = S.nfc.card;

  // 1. Whatever is already on the tag — the truth, and usually what you want back.
  if (c && c.ok && (c.url || c.epitaph)) {
    if (url && c.url) url.value = c.url;
    if (epi && c.epitaph) epi.value = c.epitaph;
    toast('filled from the card on the reader');
    return;
  }

  // 2. Blank tag: derive a starting point from the open design.
  const name = (S.doc && S.doc.name) || 'Untitled';
  const id = name.toUpperCase().replace(/[^A-Z0-9]+/g, '-').replace(/^-|-$/g, '').slice(0, 24) || 'CARD-001';
  const now = new Date();
  const ym = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`;
  // The base is not ours to invent, so the origin stays an obvious placeholder rather
  // than silently choosing a host for someone else's card.
  if (url && !url.value.trim()) url.value = `https://example.com/c/${id}`;
  if (epi && !epi.value.trim()) epi.value = `vc1|${id}|${name}|${ym}|MIT|vibe-cards`;
  toast('filled from the open design — edit the address before writing');
}

async function writeChip() {
  const url = ($('#chipUrl').value || '').trim();
  const epitaph = ($('#chipEpitaph').value || '').trim();
  const out = $('#chipWriteResult');
  if (!url) { toast('enter an address first', 'err'); return; }
  if (!S.nfc.present) { toast('no card on the reader', 'err'); return; }

  S.nfc.busy = true;
  out.innerHTML = '<p class="chip-note">writing…</p>';
  setStatus('writing card…');
  const r = await api('/api/nfc/write', epitaph ? { url, epitaph } : { url });
  S.nfc.busy = false;
  setStatus('');

  if (!r.ok) {
    out.innerHTML = `<p class="chip-err">${escapeHtml(r.error || 'write failed')}</p>`;
    toast('card not written', 'err');
  } else {
    const warn = (r.warnings || []).map((w) => `<p class="chip-note">${escapeHtml(w)}</p>`).join('');
    out.innerHTML = `<p class="chip-ok">written and verified — ${r.bytes} bytes, ${r.free} free</p>` + warn;
    toast('card written', 'ok');
  }
  readChip();
}

function switchView(name) {
  $$('.tab').forEach((t) => t.classList.toggle('is-active', t.dataset.view === name));
  $$('.view').forEach((v) => v.classList.toggle('is-active', v.dataset.view === name));
  if (name === 'tray') { renderTray(); refreshPrinterStatus(); wireBleed(); }
  if (name === 'batch') renderBatch();
  if (name === 'calibrate') { renderGeomTable(); renderCalPreview(); renderCalPresets(); }
  if (name === 'supplies') renderSupplies();
  // Polling is scoped to the view: entering starts it, leaving anything else stops it.
  if (name === 'chip') startChipPolling(); else stopChipPolling();
}

function wireUI() {
  loadMargin();
  wireMargin();
  wireBleed();
  $('#tabs').addEventListener('click', (e) => {
    const b = e.target.closest('.tab'); if (b) switchView(b.dataset.view);
  });

  $('#btnChipRefresh')?.addEventListener('click', readChip);
  $('#btnChipFromCard')?.addEventListener('click', chipFillFromDesign);
  $('#btnChipWrite')?.addEventListener('click', writeChip);

  $$('.tool').forEach((b) => b.onclick = () => addElement(b.dataset.add));
  $('#btnDelete').onclick = deleteSel;
  $('#btnDupe').onclick = duplicateSel;
  $('#btnRaise').onclick = () => reorder(1);
  $('#btnLower').onclick = () => reorder(-1);

  $('#faceSeg').addEventListener('click', (e) => {
    const b = e.target.closest('.seg-btn'); if (!b) return;
    $$('.seg-btn', $('#faceSeg')).forEach((x) => x.classList.toggle('is-on', x === b));
    S.face = +b.dataset.face;
    S.sel = null;
    buildInspector(); render();
    $('#bgColor').value = face().bg.color || '#ffffff';
  });

  $('#bgColor').onchange = (e) => { face().bg = { type: 'color', color: e.target.value }; render(); };
  $('#showSafe').onchange = (e) => { S.showSafe = e.target.checked; render(); };
  $('#showGrid').onchange = (e) => { S.showGrid = e.target.checked; render(); };
  $('#showRfid').onchange = (e) => { S.showRfid = e.target.checked; render(); };
  $('#docName').oninput = (e) => { S.doc.name = e.target.value; };

  const tpl = $('#templateSel');
  tpl.innerHTML = '<option value="">Start from…</option>' +
    Object.entries(TEMPLATES).map(([k, v]) => `<option value="${k}">${v.label}</option>`).join('');
  tpl.onchange = () => {
    if (!tpl.value) return;
    // A template REPLACES the face. Silent on an empty card — that is the whole
    // point of the picker — but never throw away work without asking.
    const busy = face().elements.length;
    if (busy && !confirm(`Replace this face with the ${TEMPLATES[tpl.value].label} template?\n\n${busy} element${busy > 1 ? 's' : ''} on the ${S.face ? 'back' : 'front'} will be discarded.`)) {
      tpl.value = '';
      return;
    }
    S.doc.faces[S.face] = TEMPLATES[tpl.value].build();
    S.sel = null;
    $('#bgColor').value = face().bg.color || '#ffffff';
    buildInspector(); render(); renderTray();
    tpl.value = '';
  };

  // Empty-state calls to action. They drive the SAME entry points as the rail and
  // the picker — no parallel import path to drift.
  $('#ceChoose').onclick = () => importPhotos();
  $('#ceTemplate').onclick = () => {
    tpl.focus();
    if (typeof tpl.showPicker === 'function') { try { tpl.showPicker(); return; } catch (_) { /* not user-gesture: fall through */ } }
    tpl.classList.add('is-pinged');
    setTimeout(() => tpl.classList.remove('is-pinged'), 1200);
  };

  $('#zoomIn').onclick = () => { S.zoom = clamp(S.zoom * 1.25, 0.4, 6); $('#zoomVal').textContent = Math.round(S.zoom * 100) + '%'; render(); };
  $('#zoomOut').onclick = () => { S.zoom = clamp(S.zoom / 1.25, 0.4, 6); $('#zoomVal').textContent = Math.round(S.zoom * 100) + '%'; render(); };
  $('#zoomFit').onclick = () => {
    const wrap = $('#canvasWrap').getBoundingClientRect();
    const avail = wrap.width - RULER - PAD * 3;
    S.zoom = clamp(avail / (S.doc.card.w * basePxmm()), 0.4, 6);
    $('#zoomVal').textContent = Math.round(S.zoom * 100) + '%';
    render();
  };

  ['#slotA', '#slotB'].forEach((id) => $(id).onchange = renderTray);
  $('#printerSel').onchange = async (e) => {
    S.printer = e.target.value;
    const res = await api('/api/printer', { printer: S.printer });
    S.caps = res.capabilities || {};
    fillCapSelects();
  };

  $('#btnPrint').onclick = () => doPrint(null);
  $('#btnPrintTop').onclick = () => { switchView('tray'); setTimeout(() => doPrint(null), 60); };
  $('#btnPdf').onclick = doPdf;
  $('#btnDryRun').onclick = doDryRun;
  $('#btnRefreshStatus').onclick = refreshPrinterStatus;
  $('#btnResetPrinter').onclick = resetPrinter;
  $('#btnCheckTray').onclick = checkTray;
  $('#btnReveal').onclick = () => api('/api/reveal', { what: 'output' });
  $('#btnEnableQueue').onclick = async () => {
    const r = await api('/api/enable-queue', { printer: S.printer });
    toast(r.ok ? 'Queue re-enabled' : 'Could not enable: ' + (r.stderr || '?'), r.ok ? 'ok' : 'err');
  };

  $('#btnSave').onclick = async () => {
    // The server derives the filename from the document name, so saving a second
    // doc under a name already on disk overwrites it with no trace. Ask, using
    // the real listing rather than guessing what the sanitiser will produce.
    const target = (await api('/api/designs')).designs
      .find((d) => d.name.toLowerCase() === (S.doc.name || '').trim().toLowerCase());
    if (target && !confirm(`"${target.name}" already exists (saved ${target.modified.replace('T', ' ')}).\n\nOverwrite it?`)) {
      toast('Not saved — rename the card in the title field first');
      return;
    }
    const res = await api('/api/save-design', { design: S.doc });
    markSaved();
    toast('Saved ' + res.file, 'ok');
  };

  /* Save existed without Open: designs were written to disk and then
   * unreachable from the UI forever. The server side was already complete
   * (/api/designs + /api/design/<file>) — only the front door was missing. */
  const openMenu = $('#openMenu');
  const closeOpenMenu = () => { openMenu.hidden = true; };
  $('#btnOpen').onclick = async (e) => {
    e.stopPropagation();
    if (!openMenu.hidden) return closeOpenMenu();
    let designs = [];
    try { designs = (await api('/api/designs')).designs || []; } catch (err) { toast(err.message, 'err'); return; }
    openMenu.innerHTML = designs.length
      ? designs.map((d) => `<button class="open-item" data-file="${escapeHtml(d.file)}">
           <span class="oi-name">${escapeHtml(d.name)}</span>
           <span class="oi-when">${escapeHtml(d.modified.replace('T', ' '))}</span>
         </button>`).join('')
      : '<p class="open-none">No saved cards yet — Save writes them here.</p>';
    openMenu.hidden = false;
    openMenu.querySelectorAll('.open-item').forEach((b) => {
      b.onclick = async () => {
        if (isDirty() && !confirm('Open a different card?\n\nUnsaved changes to the current card will be lost.')) return;
        try {
          const doc = await api('/api/design/' + encodeURIComponent(b.dataset.file));
          S.doc = doc;
          S.face = 0;
          S.sel = null;
          $('#docName').value = S.doc.name || 'Untitled Card';
          $('#bgColor').value = face().bg.color || '#ffffff';
          await allImagesReady(S.doc);
          markSaved();
          buildInspector(); render(); renderTray();
          toast('Opened ' + (S.doc.name || b.dataset.file), 'ok');
        } catch (err) {
          toast('Could not open: ' + err.message, 'err');
        }
        closeOpenMenu();
      };
    });
  };
  document.addEventListener('click', (e) => { if (!e.target.closest('.open-wrap')) closeOpenMenu(); });

  // batch
  $('#btnCsvFile').onclick = () => {
    const p = $('#csvPick');
    p.onchange = () => {
      const f = p.files[0]; if (!f) return;
      const rd = new FileReader();
      rd.onload = () => { $('#csvText').value = rd.result; loadCSV(rd.result); };
      rd.readAsText(f); p.value = '';
    };
    p.click();
  };
  $('#btnCsvSample').onclick = () => {
    const sample = 'Name,ID,Role,Expires\nAda Lovelace,000117,Engineering,2028-01\nAlan Turing,000118,Research,2028-01\nGrace Hopper,000119,Operations,2027-11';
    $('#csvText').value = sample; loadCSV(sample);
  };
  $('#btnCsvClear').onclick = () => { $('#csvText').value = ''; S.records = []; S.fields = []; renderBatch(); renderTray(); };
  $('#csvText').addEventListener('input', (e) => loadCSV(e.target.value));
  $('#batchDesign').onchange = renderBatch;
  $('#btnBatchPrint').onclick = batchPrint;
  $('#btnBatchNext').onclick = () => {
    const pairs = Math.ceil(S.records.length / 2);
    S.batchIndex = Math.min(S.batchIndex + 1, Math.max(0, pairs - 1));
    renderBatch(); renderTray();
  };
  $('#btnBatchReset').onclick = () => { S.batchIndex = 0; renderBatch(); renderTray(); };

  // calibrate
  $$('[data-nudge]').forEach((b) => b.onclick = () => {
    const [dx, dy] = b.dataset.nudge.split(',').map(Number);
    if (dx === 0 && dy === 0 && b.id === 'nudgeZero') { $('#calDx').value = 0; $('#calDy').value = 0; }
    else {
      $('#calDx').value = round(parseFloat($('#calDx').value || 0) + dx, 2);
      $('#calDy').value = round(parseFloat($('#calDy').value || 0) + dy, 2);
    }
    S.profile.calibration = { dx: parseFloat($('#calDx').value), dy: parseFloat($('#calDy').value) };
    renderTray(); renderGeomTable(); renderCalPreview();
  });
  ['#calDx', '#calDy'].forEach((id) => $(id).oninput = () => {
    S.profile.calibration = { dx: parseFloat($('#calDx').value) || 0, dy: parseFloat($('#calDy').value) || 0 };
    renderTray(); renderGeomTable(); renderCalPreview();
  });
  $('#btnCalSave').onclick = async () => {
    await api('/api/calibration', { profile: S.profileKey, dx: S.profile.calibration.dx, dy: S.profile.calibration.dy });
    toast('Offset saved for this machine', 'ok');
  };
  $('#btnCalApply').onclick = () => {
    const top = parseFloat($('#readTop').value), left = parseFloat($('#readLeft').value);
    if (isNaN(top) && isNaN(left)) { toast('Enter at least one reading.', 'err'); return; }
    const dx = round((parseFloat($('#calDx').value) || 0) + (isNaN(left) ? 0 : left), 2);
    const dy = round((parseFloat($('#calDy').value) || 0) + (isNaN(top) ? 0 : top), 2);
    $('#calDx').value = dx; $('#calDy').value = dy;
    S.profile.calibration = { dx, dy };
    renderTray(); renderGeomTable(); renderCalPreview();
    toast(`Offset now ${dx}, ${dy} mm — save it, then re-print the target.`);
  };
  $('#btnCalPrint').onclick = async () => {
    const placements = await calibrationPlacements();
    const res = await api('/api/print', printPayload(placements, 'calibration'));
    $('#printLog').textContent = [res.command, res.stdout, res.stderr].filter(Boolean).join('\n');
    toast(res.ok ? 'Calibration target sent' : 'Failed: ' + res.stderr, res.ok ? 'ok' : 'err');
  };
  $('#btnCalPdf').onclick = async () => {
    const placements = await calibrationPlacements();
    const res = await api('/api/pdf', printPayload(placements, 'calibration'));
    toast('PDF: ' + res.pdf, 'ok');
  };

  // keyboard
  window.addEventListener('keydown', (e) => {
    const tag = (e.target.tagName || '').toLowerCase();
    if (tag === 'input' || tag === 'textarea' || tag === 'select') return;
    const el = selected();
    if ((e.key === 'Backspace' || e.key === 'Delete') && el) { e.preventDefault(); deleteSel(); return; }
    if ((e.metaKey || e.ctrlKey) && e.key === 'd' && el) { e.preventDefault(); duplicateSel(); return; }
    if ((e.metaKey || e.ctrlKey) && e.key === 's') { e.preventDefault(); $('#btnSave').click(); return; }
    if ((e.metaKey || e.ctrlKey) && e.key === 'p') { e.preventDefault(); $('#btnPrintTop').click(); return; }
    if (el && e.key.startsWith('Arrow')) {
      e.preventDefault();
      const step = e.shiftKey ? 1 : 0.25;
      if (e.key === 'ArrowLeft') el.x = round(el.x - step, 2);
      if (e.key === 'ArrowRight') el.x = round(el.x + step, 2);
      if (e.key === 'ArrowUp') el.y = round(el.y - step, 2);
      if (e.key === 'ArrowDown') el.y = round(el.y + step, 2);
      render(); syncInspectorValues();
    }
    if (e.key === 'Escape') { S.sel = null; buildInspector(); render(); }
  });

  // A drop anywhere OUTSIDE the card used to hit the browser's own default:
  // Chrome navigates the window to the dropped file. In an --app window that
  // replaces Card Studio with a picture of your dog and takes the unsaved card
  // with it. The window is the app, so the whole document has to refuse drops;
  // the card area then opts back in below.
  document.addEventListener('dragover', (e) => e.preventDefault());
  document.addEventListener('drop', (e) => {
    e.preventDefault();
    if (!e.target.closest('#canvasWrap')) {
      toast('Drop it on the card itself to place a photo');
    }
  });

  // drag an image straight onto the card
  const wrap = $('#canvasWrap');
  wrap.addEventListener('dragover', (e) => { e.preventDefault(); wrap.classList.add('is-dropping'); });
  wrap.addEventListener('dragleave', (e) => { if (!wrap.contains(e.relatedTarget)) wrap.classList.remove('is-dropping'); });
  wrap.addEventListener('drop', (e) => {
    e.preventDefault();
    e.stopPropagation();
    wrap.classList.remove('is-dropping');
    // Same rule as the Image tool: one photo fills the card, two fill the two
    // tray slots. Dropping is the fastest path to a finished card.
    importPhotos(e.dataTransfer.files);
  });

  window.addEventListener('resize', () => render());
}

function fillCapSelects() {
  const cap = S.caps || {};
  const put = (id, key, fallback) => {
    const vals = (cap[key] && cap[key].values) || [];
    const sel = $(id);
    if (!vals.length) { sel.innerHTML = `<option>${escapeHtml(fallback)}</option>`; return; }
    fillSelect(sel, vals, fallback);
    if (!vals.includes(fallback)) sel.value = (cap[key].default || vals[0]);
  };
  put('#optPageSize', 'PageSize', S.profile.cups.PageSize);
  put('#optInputSlot', 'InputSlot', S.profile.cups.InputSlot);
  put('#optMediaType', 'MediaType', S.profile.cups.MediaType);
  put('#optQuality', 'cupsPrintQuality', 'High');
}

async function boot() {
  S.boot = await api('/api/bootstrap');
  adoptDeviceMargins(S.boot.device_margins);
  // Opens BLANK. A demo card on launch means the first thing anyone does is
  // delete someone else's design before starting their own; importing a photo
  // should be the first move, not the second. Templates stay one click away in
  // the Start-from picker, and the empty state points at both.
  S.doc = newDoc();
  markSaved();   // a fresh blank card is not unsaved work

  applyProfile(S.boot.profiles.default_profile);

  S.printer = S.boot.printer;
  S.caps = S.boot.capabilities || {};
  fillSelect($('#printerSel'), S.boot.printers.printers.map((p) => p.name), S.printer);
  fillCapSelects();

  ['#slotA', '#slotB'].forEach((id, i) => {
    $(id).innerHTML = `<option value="front">Front design</option><option value="back">Back design</option><option value="blank">Blank / skip</option>`;
    $(id).value = 'front';
  });
  $('#batchDesign').innerHTML = `<option value="front">Front design</option><option value="back">Back design</option>`;

  $('#bgColor').value = face().bg.color || '#ffffff';
  wireUI();
  applyCapabilities();
  initCanvasEvents();
  $('#zoomFit').click();
  buildInspector();
  render();
  renderTray();
  setStatus(`${S.printer || 'no printer'} · ${S.boot.profiles.profiles[S.profileKey].page_mm.w}×${S.boot.profiles.profiles[S.profileKey].page_mm.h} mm`);

  /* Through the seam, not a raw fetch. This heartbeat is what keeps the desktop
   * server alive (server.py watchdog, HEARTBEAT_TIMEOUT_S) — a bare fetch()
   * carries no session token, so it 403s, last_beat never advances and the
   * server exits ~90s after launch while the window sits there looking fine.
   * fetch() does not reject on 403 either, so the .catch() never fired and
   * nothing surfaced. In the web build the same call is answered locally. */
  setInterval(() => api('/api/ping').catch(() => {}), 20000);
  // Closing the window used to sendBeacon('/api/quit') — which shut the server
  // down instantly and took any unsaved card with it, including on an accidental
  // ⌘W. The server already has a heartbeat watchdog (HEARTBEAT_TIMEOUT_S) that
  // exits on its own once the pings stop, so the lifecycle is unchanged; it just
  // stops being instantaneous and unrecoverable. sendBeacon also cannot set the
  // X-CS-Token header, so this call could no longer authenticate anyway.
  window.addEventListener('beforeunload', (e) => {
    if (!isDirty()) return;
    e.preventDefault();
    e.returnValue = '';   // the browser shows its own "leave site?" prompt
    return '';
  });
}

boot().catch((err) => {
  document.body.innerHTML = `<pre style="padding:30px;color:#e0674c;font:13px monospace">Card Studio failed to start:\n\n${err.stack || err}</pre>`;
});
