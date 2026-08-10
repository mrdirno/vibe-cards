/* Web backend — the static GitHub Pages build. No server, no Python.
 *
 * Implements the same two-property contract as src/web/backend.js against
 * browser APIs, so app.js is byte-identical in both builds. Where a call cannot
 * honestly be implemented in a page (driving a printer, enumerating printers,
 * asking a device to validate a tray) it returns a shaped, empty answer and the
 * capability flag is false, so the UI hides the control rather than offering
 * something that will not work.
 *
 * The one call that does real work here is /api/pdf: the browser has already
 * rasterised each card by the time it is made, so composing the PDF is pure
 * geometry — see pdf.js, which is a port of the desktop's pdfwriter.py and is
 * tested against it for byte-identical output.
 */
/* pdf.js is a classic script loaded before this one (see index.html) and exposes
 * window.CS_PDF. Not an import: a module here would defer past app.js.
 *
 * Read through window.CS_PDF at the CALL SITE rather than destructuring here.
 * Classic scripts share ONE global lexical scope and pdf.js already declares a
 * top-level `function buildPdf`, so a top-level `const { buildPdf }` in this
 * file is a redeclaration — it kills this whole script before it ever defines
 * CS_BACKEND, and the app then boots into a blank page with one console line. */

const LS_DESIGNS = 'vibecards.designs.v1';
const LS_SETTINGS = 'vibecards.settings.v1';

const readLS = (key, fallback) => {
  try { return JSON.parse(localStorage.getItem(key)) ?? fallback; }
  catch (_) { return fallback; }
};
const writeLS = (key, value) => {
  try {
    localStorage.setItem(key, JSON.stringify(value));
    return true;
  } catch (err) {
    // Designs embed base64 images and localStorage is ~5 MB. A silent failure
    // here would look exactly like a successful save, so it is surfaced.
    throw new Error(
      'Browser storage is full (about 5 MB). Download this card as a .card.json ' +
      'file to keep it, then delete a saved card to free space.'
    );
  }
};

const designKey = (name) =>
  (String(name || 'Untitled').replace(/[^A-Za-z0-9 ._-]+/g, '_').trim() || 'Untitled') + '.card.json';

function download(blob, filename) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  // Revoke late: Safari has been known to cancel an in-flight download when the
  // object URL is revoked in the same tick as the click.
  setTimeout(() => URL.revokeObjectURL(url), 10_000);
}

window.CS_BACKEND = {
  name: 'web',

  capabilities: {
    printing: false,          // a page cannot drive a printer — export a PDF instead
    printerDiscovery: false,
    trayValidation: false,
    serverFiles: false,       // designs live in localStorage + downloads
    revealInFinder: false,
    batch: false,             // needs multi-page PDF; see docs/ROADMAP.md
  },

  async call(path, body) {
    const route = path.split('?')[0];

    if (route === '/api/bootstrap') {
      // profiles.json and supplies.json are served as static files beside the
      // page. Relative URLs on purpose: this is hosted under a project subpath
      // (/vibe-cards/), so a leading slash would 404 against the user site root.
      const [profiles, supplies] = await Promise.all([
        fetch('profiles.json').then((r) => r.json()),
        fetch('supplies.json').then((r) => r.json()).catch(() => ({ items: [] })),
      ]);
      return {
        profiles,
        supplies,
        printers: { printers: [], default: null },
        printer: null,
        capabilities: {},
        settings: readLS(LS_SETTINGS, {}),
        designs: Object.values(readLS(LS_DESIGNS, {})).map((d) => d.meta),
        paths: { designs: 'browser storage', output: 'your Downloads folder' },
        pil: false,
        web: true,
      };
    }

    if (route === '/api/designs') {
      return { designs: Object.values(readLS(LS_DESIGNS, {})).map((d) => d.meta) };
    }

    if (route.startsWith('/api/design/')) {
      const file = decodeURIComponent(route.slice('/api/design/'.length));
      const store = readLS(LS_DESIGNS, {});
      if (!store[file]) throw new Error('not found');
      return store[file].doc;
    }

    if (route === '/api/save-design') {
      const doc = body.design;
      const file = designKey(doc.name);
      const store = readLS(LS_DESIGNS, {});
      store[file] = {
        doc,
        meta: { file, name: doc.name || 'Untitled Card', modified: new Date().toISOString().slice(0, 19) },
      };
      writeLS(LS_DESIGNS, store);
      return { ok: true, file, designs: Object.values(store).map((d) => d.meta) };
    }

    if (route === '/api/delete-design') {
      const store = readLS(LS_DESIGNS, {});
      delete store[body.file];
      writeLS(LS_DESIGNS, store);
      return { ok: true, designs: Object.values(store).map((d) => d.meta) };
    }

    if (route === '/api/settings') {
      const next = { ...readLS(LS_SETTINGS, {}), ...body };
      writeLS(LS_SETTINGS, next);
      return { ok: true, settings: next };
    }

    if (route === '/api/calibration') {
      const next = { ...readLS(LS_SETTINGS, {}), calibration: body };
      writeLS(LS_SETTINGS, next);
      return { ok: true, settings: next };
    }

    // The real work: compose the print-exact PDF and hand it to the user.
    if (route === '/api/pdf' || route === '/api/print') {
      const page = body.page_mm;
      const blob = window.CS_PDF.buildPdf({
        pageWmm: page.w,
        pageHmm: page.h,
        images: body.placements,
        dx: body.dx || 0,
        dy: body.dy || 0,
        title: body.name,
      });
      const name = (String(body.name || 'cards').replace(/[^A-Za-z0-9._-]+/g, '_')).slice(0, 60);
      download(blob, `${name}.pdf`);
      return {
        ok: true,
        web: true,
        file: `${name}.pdf`,
        bytes: blob.size,
        // /api/print is remapped to an export rather than refused: the button
        // the user pressed still does the most useful thing a page can do, and
        // the UI says so plainly rather than after the fact.
        note: 'Exported a print-exact PDF. Print it at 100% scale — see the printing note.',
      };
    }

    // Honest empties. Shaped like the server's replies so no call site needs a
    // web-specific branch, and paired with capabilities:false so the UI does
    // not offer these at all.
    if (route === '/api/printer-status') return { ok: false, web: true, alerts: [], ink: [] };
    if (route === '/api/dryrun') return { ok: false, web: true, error: 'Dry run needs the desktop app.' };
    if (route === '/api/validate-tray') return { ok: false, web: true, error: 'Tray validation needs the desktop app.' };
    if (route === '/api/printer') return { ok: true, printer: null };
    if (route === '/api/reset-printer') return { ok: false, web: true };
    if (route === '/api/enable-queue') return { ok: false, web: true };
    if (route === '/api/reveal') return { ok: false, web: true };
    if (route === '/api/ping') return { ok: true };
    if (route === '/api/quit') return { ok: true };

    throw new Error(`This build has no "${route}" — it runs without a server.`);
  },

  // Used by the web build's own controls (see the web build).
  _download: download,
  _designKey: designKey,
};
