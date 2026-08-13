/* Desktop backend — talks HTTP to server.py.
 *
 * This is one half of the app's only platform seam; the other half is
 * web/backend.js, which implements the same two-property contract against
 * browser APIs for the static GitHub Pages build. app.js does not know which
 * one it got, and must never be forked to find out.
 *
 * Contract:
 *   CS_BACKEND.call(route, body?)  -> Promise<object>   (body undefined = GET)
 *   CS_BACKEND.capabilities        -> { printing, printerDiscovery, trayValidation,
 *                                       serverFiles, revealInFinder, batch }
 */
window.CS_BACKEND = {
  name: 'desktop',

  capabilities: {
    printing: true,           // can drive a real printer
    printerDiscovery: true,   // can enumerate printers and read their state
    trayValidation: true,     // IPP Validate-Job / CUPS dry run
    serverFiles: true,        // designs saved server-side, revealable in Finder
    revealInFinder: true,
    batch: true,
    nfc: true,                // can reach a PC/SC card reader
  },

  /* Every call carries the session token the server minted this run and stamped
   * into index.html. A page on another origin can still SEND requests to
   * 127.0.0.1, but it cannot read this token, so it cannot make any of them
   * count. See server.py SESSION_TOKEN and SECURITY.md. */
  token: (document.querySelector('meta[name="cs-token"]') || {}).content || '',

  async call(path, body) {
    const headers = { 'X-CS-Token': this.token };
    if (body !== undefined) headers['Content-Type'] = 'application/json';
    const res = await fetch(path, body === undefined
      ? { headers }
      : { method: 'POST', headers, body: JSON.stringify(body) });
    const json = await res.json().catch(() => ({ error: 'bad response' }));
    if (!res.ok && json.error) throw new Error(json.error);
    return json;
  },
};
