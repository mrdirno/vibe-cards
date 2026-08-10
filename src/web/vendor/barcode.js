/*
 * barcode.js — dependency-free Code 128 encoder (ISO/IEC 15417).
 *
 * Plain <script> include; exposes a single global:
 *
 *   window.Barcode.code128(text, opts) -> { bars: number[] }
 *
 * `bars` are element widths in MODULES, alternating dark, light, dark, ...
 * starting with DARK and (per the Code 128 stop pattern) ending with DARK.
 * Quiet zones are the caller's job: the spec requires >= 10 modules of light
 * on each side.
 *
 * opts.forceSet : 'A' | 'B' | 'C' — pin the whole payload to one code set.
 *                 Omitted (the normal case) => optimal automatic A/B/C
 *                 selection, including SHIFT and Code C run packing.
 *
 * Throws a descriptive Error for anything not representable in Code 128
 * (non-ASCII, ASCII > 127, odd-length digits under forceSet 'C', ...).
 */
(function (global) {
  'use strict';

  // Element-width patterns, indexed by code value 0..106. Six elements each
  // (bar,space,bar,space,bar,space = 11 modules); 106 (STOP) is seven
  // elements = 13 modules, the trailing "2" being the final 2-module bar.
  var PATTERNS = [
    '212222', '222122', '222221', '121223', '121322', // 0-4
    '131222', '122213', '122312', '132212', '221213', // 5-9
    '221312', '231212', '112232', '122132', '122231', // 10-14
    '113222', '123122', '123221', '223211', '221132', // 15-19
    '221231', '213212', '223112', '312131', '311222', // 20-24
    '321122', '321221', '312212', '322112', '322211', // 25-29
    '212123', '212321', '232121', '111323', '131123', // 30-34
    '131321', '112313', '132113', '132311', '211313', // 35-39
    '231113', '231311', '112133', '112331', '132131', // 40-44
    '113123', '113321', '133121', '313121', '211331', // 45-49
    '231131', '213113', '213311', '213131', '311123', // 50-54
    '311321', '331121', '312113', '312311', '332111', // 55-59
    '314111', '221411', '431111', '111224', '111422', // 60-64
    '121124', '121421', '141122', '141221', '112214', // 65-69
    '112412', '122114', '122411', '142112', '142211', // 70-74
    '241211', '221114', '413111', '241112', '134111', // 75-79
    '111242', '121142', '121241', '114212', '124112', // 80-84
    '124211', '411212', '421112', '421211', '212141', // 85-89
    '214121', '412121', '111143', '111341', '131141', // 90-94
    '114113', '114311', '411113', '411311', '113141', // 95-99
    '114131', '311141', '411131', '211412', '211214', // 100-104
    '211232', '2331112'                               // 105 (START C), 106 (STOP)
  ];

  var SHIFT = 98;                 // shift the NEXT character to the other set (A<->B)
  var SWITCH = { A: 101, B: 100, C: 99 };   // "switch to X", valid from any other set
  var START = { A: 103, B: 104, C: 105 };
  var STOP = 106;

  var INF = Infinity;

  // --- character classification -------------------------------------------

  // Code A covers ASCII 0..95 (controls + SP..'_'); Code B covers ASCII 32..127.
  function inA(c) { return c >= 0 && c <= 95; }
  function inB(c) { return c >= 32 && c <= 127; }
  function isDigit(c) { return c >= 48 && c <= 57; }

  function valueA(c) { return c >= 32 ? c - 32 : c + 64; }
  function valueB(c) { return c - 32; }

  // --- code-set planner ----------------------------------------------------

  /*
   * Optimal set selection by backward dynamic programming.
   *
   *   dp[i][s]   = minimum codewords to encode codes[i..] given we are in set s
   *   base[i][s] = same, but forced to consume at least one character AT i
   *                without a leading set switch
   *
   * A switch to any other set costs exactly one codeword and reaches every
   * other set, so a second consecutive switch is never useful — which makes
   *
   *   dp[i][s] = min( base[i][s], 1 + min_{t != s} base[i][t] )
   *
   * exact (no fixpoint iteration needed) and keeps the recurrence acyclic:
   * base[i][*] only ever reads dp[i+1][*] / dp[i+2][*].
   */
  // Fixed order => deterministic tie-breaking. B leads because equal-cost ties
  // are overwhelmingly ordinary text, and Start B is the conventional choice
  // there (matches what reference encoders emit, so symbols diff cleanly).
  var SETS = ['B', 'A', 'C'];

  function plan(codes) {
    var n = codes.length;
    var dp = new Array(n + 1);
    var base = new Array(n + 1);

    dp[n] = { A: 0, B: 0, C: 0 };
    // dp[n+1] is read by the Code C branch when a pair would run past the end;
    // that branch is guarded by isDigit(codes[i+1]) so the slot is never used,
    // but keep it defined so the arithmetic below is total.
    dp[n + 1] = { A: INF, B: INF, C: INF };

    for (var i = n - 1; i >= 0; i--) {
      var c = codes[i];
      var b = { A: INF, B: INF, C: INF };

      // Code A: direct, else borrow one B-only character via SHIFT (2 codewords).
      if (inA(c)) b.A = 1 + dp[i + 1].A;
      else if (inB(c)) b.A = 2 + dp[i + 1].A;

      // Code B: mirror image.
      if (inB(c)) b.B = 1 + dp[i + 1].B;
      else if (inA(c)) b.B = 2 + dp[i + 1].B;

      // Code C: one codeword per digit PAIR — the run-of-digits optimisation.
      if (isDigit(c) && i + 1 < n && isDigit(codes[i + 1])) b.C = 1 + dp[i + 2].C;

      base[i] = b;
      dp[i] = {
        A: Math.min(b.A, 1 + Math.min(b.B, b.C)),
        B: Math.min(b.B, 1 + Math.min(b.A, b.C)),
        C: Math.min(b.C, 1 + Math.min(b.A, b.B))
      };
    }

    // Pick the cheapest start set. Because a switch costs 1, the argmin of
    // dp[0][*] always satisfies dp[0][s] === base[0][s], so reconstruction
    // never has to switch out of the start character.
    var set = SETS[0];
    for (var k = 1; k < SETS.length; k++) {
      if (dp[0][SETS[k]] < dp[0][set]) set = SETS[k];
    }
    if (dp[0][set] === INF) {
      // Unreachable: unencodable characters are rejected before planning.
      throw new Error('Barcode.code128: payload cannot be encoded in Code 128');
    }

    // Walk the optimal path forward, emitting codewords.
    var out = [START[set]];
    var pos = 0;
    while (pos < n) {
      if (base[pos][set] !== dp[pos][set]) {
        // The optimum requires changing set before consuming this character.
        var next = null;
        for (var j = 0; j < SETS.length; j++) {
          var t = SETS[j];
          if (t !== set && 1 + base[pos][t] === dp[pos][set]) { next = t; break; }
        }
        out.push(SWITCH[next]);
        set = next;
      }
      pos = emit(codes, pos, set, out);
    }
    return out;
  }

  // Encode exactly one character (or one digit pair in Code C) at `pos` in the
  // current set; returns the next position.
  function emit(codes, pos, set, out) {
    var c = codes[pos];
    if (set === 'C') {
      out.push((c - 48) * 10 + (codes[pos + 1] - 48));
      return pos + 2;
    }
    if (set === 'A') {
      if (inA(c)) out.push(valueA(c));
      else { out.push(SHIFT); out.push(valueB(c)); }
    } else {
      if (inB(c)) out.push(valueB(c));
      else { out.push(SHIFT); out.push(valueA(c)); }
    }
    return pos + 1;
  }

  // Single-set encoding for opts.forceSet — no switches, no shifts.
  function planForced(codes, set) {
    var n = codes.length;
    if (set === 'C') {
      if (n % 2 !== 0) {
        throw new Error('Barcode.code128: forceSet "C" needs an even number of digits, got ' + n);
      }
      for (var i = 0; i < n; i++) {
        if (!isDigit(codes[i])) {
          throw new Error('Barcode.code128: forceSet "C" accepts digits only; ' +
            'offending character ' + describe(codes[i]) + ' at index ' + i);
        }
      }
    } else {
      var ok = set === 'A' ? inA : inB;
      for (var j = 0; j < n; j++) {
        if (!ok(codes[j])) {
          throw new Error('Barcode.code128: character ' + describe(codes[j]) +
            ' at index ' + j + ' is not in code set ' + set);
        }
      }
    }
    var out = [START[set]];
    var pos = 0;
    while (pos < n) pos = emit(codes, pos, set, out);
    return out;
  }

  function describe(c) {
    return (c >= 32 && c <= 126)
      ? '"' + String.fromCharCode(c) + '" (0x' + c.toString(16) + ')'
      : '0x' + c.toString(16);
  }

  // --- public API ----------------------------------------------------------

  function code128(text, opts) {
    opts = opts || {};
    if (typeof text !== 'string' || text.length === 0) {
      throw new Error('Barcode.code128: text must be a non-empty string');
    }

    // Reject anything outside 7-bit ASCII up front, with the exact position.
    var codes = new Array(text.length);
    for (var i = 0; i < text.length; i++) {
      var c = text.charCodeAt(i);
      if (c > 127) {
        throw new Error('Barcode.code128: character ' + describe(c) + ' at index ' + i +
          ' is not representable in Code 128 (7-bit ASCII only)');
      }
      codes[i] = c;
    }

    var values;
    if (opts.forceSet != null) {
      var set = String(opts.forceSet).toUpperCase();
      if (set !== 'A' && set !== 'B' && set !== 'C') {
        throw new Error('Barcode.code128: forceSet must be "A", "B" or "C", got ' +
          JSON.stringify(opts.forceSet));
      }
      values = planForced(codes, set);
    } else {
      values = plan(codes);
    }

    // Modulo-103 checksum: start value + sum(position * value), positions
    // 1-indexed over the data codewords only.
    var sum = values[0];
    for (var k = 1; k < values.length; k++) sum += k * values[k];
    values.push(sum % 103);
    values.push(STOP);

    // Flatten patterns to element widths. Every symbol has an even element
    // count (6), so dark/light alternation is preserved across concatenation
    // and the 7-element stop leaves the run ending on a dark bar.
    var bars = [];
    for (var m = 0; m < values.length; m++) {
      var p = PATTERNS[values[m]];
      for (var e = 0; e < p.length; e++) bars.push(p.charCodeAt(e) - 48);
    }
    return { bars: bars };
  }

  global.Barcode = { code128: code128 };
})(typeof window !== 'undefined' ? window : globalThis);
