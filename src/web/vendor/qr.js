/*
 * qr.js — dependency-free QR Code encoder (ISO/IEC 18004 / JIS X 0510).
 *
 * Loaded with a plain <script> tag; exposes a single global:
 *
 *   window.QR.encode(text, opts) -> { size, modules, version, ecLevel, mask, mode }
 *
 *     opts.ecLevel    'L' | 'M' | 'Q' | 'H'   (default 'M')
 *     opts.minVersion 1..40                   (default 1)
 *     opts.maxVersion 1..40                   (default 40)
 *     opts.mask       0..7                    (default: auto, lowest penalty)
 *     opts.eci        'auto' | true | false   (default 'auto' — emit ECI 26/UTF-8
 *                                              only when the payload has non-ASCII bytes)
 *
 *   modules is boolean[size][size], indexed [row][col]; true = dark.
 *   No quiet zone is included — the caller adds the mandatory 4-module margin.
 *
 * Supports every version 1..40 at all four EC levels, byte (UTF-8), numeric and
 * alphanumeric modes. Kanji mode is deliberately not implemented (it would need a
 * Shift-JIS table); CJK text is carried losslessly as UTF-8 bytes instead.
 *
 * Structure/table derivation follows the reference formulation in Project Nayuki's
 * QR Code generator (MIT), reimplemented here as a single self-contained script.
 */
(function (global) {
  'use strict';

  // ---------------------------------------------------------------------------
  // Spec tables
  // ---------------------------------------------------------------------------

  // Error-correction codewords per block, indexed [ecl][version]; version 0 unused.
  var ECC_CODEWORDS_PER_BLOCK = [
    // 1   2   3   4   5   6   7   8   9  10  11  12  13  14  15  16  17  18  19  20  21  22  23  24  25  26  27  28  29  30  31  32  33  34  35  36  37  38  39  40
    [-1,  7, 10, 15, 20, 26, 18, 20, 24, 30, 18, 20, 24, 26, 30, 22, 24, 28, 30, 28, 28, 28, 28, 30, 30, 26, 28, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30], // L
    [-1, 10, 16, 26, 18, 24, 16, 18, 22, 22, 26, 30, 22, 22, 24, 24, 28, 28, 26, 26, 26, 26, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28], // M
    [-1, 13, 22, 18, 26, 18, 24, 18, 22, 20, 24, 28, 26, 24, 20, 30, 24, 28, 28, 26, 30, 28, 30, 30, 30, 30, 28, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30], // Q
    [-1, 17, 28, 22, 16, 22, 28, 26, 26, 24, 28, 24, 28, 22, 24, 24, 30, 28, 28, 26, 28, 30, 24, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30]  // H
  ];

  // Number of error-correction blocks, indexed [ecl][version].
  var NUM_EC_BLOCKS = [
    [-1, 1, 1, 1, 1, 1, 2, 2, 2, 2, 4,  4,  4,  4,  4,  6,  6,  6,  6,  7,  8,  8,  9,  9, 10, 12, 12, 12, 13, 14, 15, 16, 17, 18, 19, 19, 20, 21, 22, 24, 25], // L
    [-1, 1, 1, 1, 2, 2, 4, 4, 4, 5, 5,  5,  8,  9,  9, 10, 10, 11, 13, 14, 16, 17, 17, 18, 20, 21, 23, 25, 26, 28, 29, 31, 33, 35, 37, 38, 40, 43, 45, 47, 49], // M
    [-1, 1, 1, 2, 2, 4, 4, 6, 6, 8, 8,  8, 10, 12, 16, 12, 17, 16, 18, 21, 20, 23, 23, 25, 27, 29, 34, 34, 35, 38, 40, 43, 45, 48, 51, 53, 56, 59, 62, 65, 68], // Q
    [-1, 1, 1, 2, 4, 4, 4, 5, 6, 8, 8, 11, 11, 16, 16, 18, 16, 19, 21, 25, 25, 25, 34, 30, 32, 35, 37, 40, 42, 45, 48, 51, 54, 57, 60, 63, 66, 70, 74, 77, 81]  // H
  ];

  var EC_LEVELS = { L: 0, M: 1, Q: 2, H: 3 };
  // Format-information 2-bit field for each level (NOT the same order as above).
  var EC_FORMAT_BITS = [1, 0, 3, 2];

  var ALPHANUM_CHARSET = '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ $%*+-./:';

  var MODE_NUMERIC = { bits: 0x1, ccWidths: [10, 12, 14], name: 'numeric' };
  var MODE_ALPHANUM = { bits: 0x2, ccWidths: [9, 11, 13], name: 'alphanumeric' };
  var MODE_BYTE = { bits: 0x4, ccWidths: [8, 16, 16], name: 'byte' };

  // Penalty weights from the spec (N1..N4).
  var PENALTY_N1 = 3, PENALTY_N2 = 3, PENALTY_N3 = 40, PENALTY_N4 = 10;

  var MIN_VERSION = 1, MAX_VERSION = 40;

  // ---------------------------------------------------------------------------
  // GF(256) arithmetic — primitive polynomial x^8 + x^4 + x^3 + x^2 + 1 (0x11D)
  // ---------------------------------------------------------------------------

  var GF_EXP = new Uint8Array(512);
  var GF_LOG = new Uint8Array(256);
  (function buildGaloisTables() {
    var x = 1;
    for (var i = 0; i < 255; i++) {
      GF_EXP[i] = x;
      GF_LOG[x] = i;
      x <<= 1;
      if (x & 0x100) x ^= 0x11D;
    }
    // Duplicate the cycle so exponent addition never needs a modulo.
    for (var j = 255; j < 512; j++) GF_EXP[j] = GF_EXP[j - 255];
  })();

  function gfMul(a, b) {
    if (a === 0 || b === 0) return 0;
    return GF_EXP[GF_LOG[a] + GF_LOG[b]];
  }

  /** Generator polynomial of degree `degree`, as coefficients of x^(d-1)..x^0 (monic x^d implied). */
  function rsComputeDivisor(degree) {
    if (degree < 1 || degree > 255) throw new RangeError('QR: bad RS degree ' + degree);
    var result = new Uint8Array(degree);
    result[degree - 1] = 1; // start with the monomial 1
    var root = 1;
    for (var i = 0; i < degree; i++) {
      // Multiply the current product by (x - r^i), in place.
      for (var j = 0; j < degree; j++) {
        result[j] = gfMul(result[j], root);
        if (j + 1 < degree) result[j] ^= result[j + 1];
      }
      root = gfMul(root, 0x02);
    }
    return result;
  }

  /** Remainder of data(x)*x^degree divided by divisor(x) — i.e. the EC codewords. */
  function rsComputeRemainder(data, divisor) {
    var result = new Uint8Array(divisor.length);
    for (var i = 0; i < data.length; i++) {
      var factor = data[i] ^ result[0];
      result.copyWithin(0, 1);
      result[result.length - 1] = 0;
      for (var j = 0; j < result.length; j++) result[j] ^= gfMul(divisor[j], factor);
    }
    return result;
  }

  // ---------------------------------------------------------------------------
  // Capacity math
  // ---------------------------------------------------------------------------

  /** Total data+EC modules (excluding function patterns and format/version info). */
  function numRawDataModules(ver) {
    var result = (16 * ver + 128) * ver + 64;
    if (ver >= 2) {
      var numAlign = Math.floor(ver / 7) + 2;
      result -= (25 * numAlign - 10) * numAlign - 55;
      if (ver >= 7) result -= 36; // two 18-bit version blocks
    }
    return result;
  }

  /** Number of 8-bit data codewords available at (ver, ecl), after EC is reserved. */
  function numDataCodewords(ver, ecl) {
    return (numRawDataModules(ver) >>> 3) -
      ECC_CODEWORDS_PER_BLOCK[ecl][ver] * NUM_EC_BLOCKS[ecl][ver];
  }

  /** Character-count-indicator width class: 0 for v1-9, 1 for v10-26, 2 for v27-40. */
  function ccWidth(mode, ver) {
    return mode.ccWidths[ver <= 9 ? 0 : (ver <= 26 ? 1 : 2)];
  }

  // ---------------------------------------------------------------------------
  // Bit buffer
  // ---------------------------------------------------------------------------

  function BitBuffer() { this.bits = []; }

  BitBuffer.prototype.append = function (value, len) {
    if (len < 0 || len > 31 || (len < 31 && value >>> len !== 0)) {
      throw new RangeError('QR: value does not fit in ' + len + ' bits');
    }
    for (var i = len - 1; i >= 0; i--) this.bits.push((value >>> i) & 1);
  };

  BitBuffer.prototype.length = function () { return this.bits.length; };

  // ---------------------------------------------------------------------------
  // Segmentation
  // ---------------------------------------------------------------------------

  function utf8Bytes(str) {
    // TextEncoder is present in every browser this app targets and in Node >= 11,
    // but keep a manual encoder so the file has no environmental assumptions.
    if (typeof TextEncoder === 'function') return new TextEncoder().encode(str);
    var out = [];
    for (var i = 0; i < str.length; i++) {
      var cp = str.codePointAt(i);
      if (cp > 0xFFFF) i++; // consumed a surrogate pair
      if (cp < 0x80) {
        out.push(cp);
      } else if (cp < 0x800) {
        out.push(0xC0 | (cp >> 6), 0x80 | (cp & 0x3F));
      } else if (cp < 0x10000) {
        out.push(0xE0 | (cp >> 12), 0x80 | ((cp >> 6) & 0x3F), 0x80 | (cp & 0x3F));
      } else {
        out.push(0xF0 | (cp >> 18), 0x80 | ((cp >> 12) & 0x3F),
                 0x80 | ((cp >> 6) & 0x3F), 0x80 | (cp & 0x3F));
      }
    }
    return Uint8Array.from(out);
  }

  function isNumeric(str) { return /^[0-9]*$/.test(str); }
  function isAlphanumeric(str) { return /^[0-9A-Z $%*+\-.\/:]*$/.test(str); }

  /**
   * Choose a single segment for the whole payload. Whole-string numeric and
   * alphanumeric are the two wins that matter for card payloads (serials, URLs in
   * caps); mixed-mode optimal segmentation is not worth its complexity here.
   */
  function makeSegment(text) {
    if (text.length > 0 && isNumeric(text)) {
      return { mode: MODE_NUMERIC, charCount: text.length, text: text, bytes: null };
    }
    if (text.length > 0 && isAlphanumeric(text)) {
      return { mode: MODE_ALPHANUM, charCount: text.length, text: text, bytes: null };
    }
    var bytes = utf8Bytes(text);
    return { mode: MODE_BYTE, charCount: bytes.length, text: text, bytes: bytes };
  }

  /** Bit length of a segment's payload (mode indicator and count field excluded). */
  function segmentDataBits(seg) {
    switch (seg.mode) {
      case MODE_NUMERIC: {
        var n = seg.charCount;
        return 10 * Math.floor(n / 3) + (n % 3 === 1 ? 4 : (n % 3 === 2 ? 7 : 0));
      }
      case MODE_ALPHANUM: {
        var m = seg.charCount;
        return 11 * Math.floor(m / 2) + (m % 2) * 6;
      }
      default:
        return seg.charCount * 8;
    }
  }

  function writeSegmentData(bb, seg) {
    var i;
    if (seg.mode === MODE_NUMERIC) {
      for (i = 0; i + 3 <= seg.text.length; i += 3) bb.append(parseInt(seg.text.substr(i, 3), 10), 10);
      var rem = seg.text.length - i;
      if (rem === 2) bb.append(parseInt(seg.text.substr(i, 2), 10), 7);
      else if (rem === 1) bb.append(parseInt(seg.text.substr(i, 1), 10), 4);
    } else if (seg.mode === MODE_ALPHANUM) {
      for (i = 0; i + 2 <= seg.text.length; i += 2) {
        bb.append(ALPHANUM_CHARSET.indexOf(seg.text.charAt(i)) * 45 +
                  ALPHANUM_CHARSET.indexOf(seg.text.charAt(i + 1)), 11);
      }
      if (i < seg.text.length) bb.append(ALPHANUM_CHARSET.indexOf(seg.text.charAt(i)), 6);
    } else {
      for (i = 0; i < seg.bytes.length; i++) bb.append(seg.bytes[i], 8);
    }
  }

  // ---------------------------------------------------------------------------
  // Codeword assembly
  // ---------------------------------------------------------------------------

  /**
   * Build the final (interleaved) codeword sequence for a chosen version.
   * Returns a Uint8Array of exactly (numRawDataModules >> 3) bytes.
   */
  function buildCodewords(seg, ver, ecl, useEci) {
    var bb = new BitBuffer();
    if (useEci) {
      bb.append(0x7, 4);  // ECI mode indicator
      bb.append(26, 8);   // ECI assignment 26 = UTF-8 (values 0..127 use one byte)
    }
    bb.append(seg.mode.bits, 4);
    bb.append(seg.charCount, ccWidth(seg.mode, ver));
    writeSegmentData(bb, seg);

    var capacityBits = numDataCodewords(ver, ecl) * 8;
    if (bb.length() > capacityBits) {
      throw new Error('QR: internal capacity overflow at version ' + ver); // guarded by caller
    }

    // Terminator (up to 4 zero bits), then pad to a byte boundary.
    var i;
    var terminator = Math.min(4, capacityBits - bb.length());
    for (i = 0; i < terminator; i++) bb.bits.push(0);
    while (bb.length() % 8 !== 0) bb.bits.push(0);

    // Alternating pad codewords 0xEC / 0x11 until the data capacity is full.
    for (var pad = 0xEC; bb.length() < capacityBits; pad ^= 0xEC ^ 0x11) bb.append(pad, 8);

    var data = new Uint8Array(bb.length() >>> 3);
    for (i = 0; i < bb.bits.length; i++) data[i >>> 3] |= bb.bits[i] << (7 - (i & 7));

    return interleave(data, ver, ecl);
  }

  /** Split data into RS blocks, compute EC per block, and interleave per the spec. */
  function interleave(data, ver, ecl) {
    var numBlocks = NUM_EC_BLOCKS[ecl][ver];
    var blockEccLen = ECC_CODEWORDS_PER_BLOCK[ecl][ver];
    var rawCodewords = numRawDataModules(ver) >>> 3;
    // The first `numShortBlocks` blocks are one codeword shorter than the rest.
    var numShortBlocks = numBlocks - rawCodewords % numBlocks;
    var shortBlockLen = Math.floor(rawCodewords / numBlocks);

    var divisor = rsComputeDivisor(blockEccLen);
    var blocks = [];
    for (var i = 0, k = 0; i < numBlocks; i++) {
      var datLen = shortBlockLen - blockEccLen + (i < numShortBlocks ? 0 : 1);
      var dat = data.subarray(k, k + datLen);
      k += datLen;
      var block = new Uint8Array(shortBlockLen + 1);
      block.set(dat, 0);
      block.set(rsComputeRemainder(dat, divisor), shortBlockLen + 1 - blockEccLen);
      blocks.push({ dat: dat, block: block });
    }

    // Interleave: column-major over the data region, then over the EC region.
    var result = new Uint8Array(rawCodewords);
    var pos = 0;
    for (var col = 0; col < shortBlockLen + 1; col++) {
      for (var b = 0; b < numBlocks; b++) {
        // Skip the padding cell that short blocks do not have in the data region.
        if (col === shortBlockLen - blockEccLen && b < numShortBlocks) continue;
        result[pos++] = blocks[b].block[col];
      }
    }
    if (pos !== rawCodewords) throw new Error('QR: interleave length mismatch');
    return result;
  }

  // ---------------------------------------------------------------------------
  // Matrix construction
  // ---------------------------------------------------------------------------

  function getBit(x, i) { return ((x >>> i) & 1) !== 0; }

  function Matrix(ver, ecl) {
    this.version = ver;
    this.ecl = ecl;
    this.size = ver * 4 + 17;
    this.modules = [];
    this.isFunction = [];
    for (var y = 0; y < this.size; y++) {
      this.modules.push(new Array(this.size).fill(false));
      this.isFunction.push(new Array(this.size).fill(false));
    }
  }

  Matrix.prototype.setFunctionModule = function (x, y, isDark) {
    this.modules[y][x] = isDark;
    this.isFunction[y][x] = true;
  };

  /** Centre positions of alignment patterns; empty for version 1. */
  Matrix.prototype.alignmentPositions = function () {
    if (this.version === 1) return [];
    var numAlign = Math.floor(this.version / 7) + 2;
    // Version 32 is the one case the general formula gets wrong.
    var step = (this.version === 32) ? 26
      : Math.ceil((this.version * 4 + 4) / (numAlign * 2 - 2)) * 2;
    var result = [6];
    for (var pos = this.size - 7; result.length < numAlign; pos -= step) result.splice(1, 0, pos);
    return result;
  };

  Matrix.prototype.drawFinderPattern = function (x, y) {
    // 7x7 finder plus its separator: dark where Chebyshev distance is 0, 2 or 3.
    for (var dy = -4; dy <= 4; dy++) {
      for (var dx = -4; dx <= 4; dx++) {
        var dist = Math.max(Math.abs(dx), Math.abs(dy));
        var xx = x + dx, yy = y + dy;
        if (xx >= 0 && xx < this.size && yy >= 0 && yy < this.size) {
          this.setFunctionModule(xx, yy, dist !== 2 && dist !== 4);
        }
      }
    }
  };

  Matrix.prototype.drawAlignmentPattern = function (x, y) {
    for (var dy = -2; dy <= 2; dy++) {
      for (var dx = -2; dx <= 2; dx++) {
        this.setFunctionModule(x + dx, y + dy, Math.max(Math.abs(dx), Math.abs(dy)) !== 1);
      }
    }
  };

  Matrix.prototype.drawFormatBits = function (mask) {
    var data = EC_FORMAT_BITS[this.ecl] << 3 | mask;
    var rem = data;
    for (var i = 0; i < 10; i++) rem = (rem << 1) ^ ((rem >>> 9) * 0x537); // BCH(15,5)
    var bits = ((data << 10 | rem) ^ 0x5412) >>> 0;                        // XOR mask 101010000010010

    // Copy 1 — around the top-left finder.
    for (i = 0; i <= 5; i++) this.setFunctionModule(8, i, getBit(bits, i));
    this.setFunctionModule(8, 7, getBit(bits, 6));
    this.setFunctionModule(8, 8, getBit(bits, 7));
    this.setFunctionModule(7, 8, getBit(bits, 8));
    for (i = 9; i < 15; i++) this.setFunctionModule(14 - i, 8, getBit(bits, i));

    // Copy 2 — split between the bottom-left and top-right finders.
    for (i = 0; i < 8; i++) this.setFunctionModule(this.size - 1 - i, 8, getBit(bits, i));
    for (i = 8; i < 15; i++) this.setFunctionModule(8, this.size - 15 + i, getBit(bits, i));
    this.setFunctionModule(8, this.size - 8, true); // the always-dark module
  };

  Matrix.prototype.drawVersionBits = function () {
    if (this.version < 7) return;
    var rem = this.version;
    for (var i = 0; i < 12; i++) rem = (rem << 1) ^ ((rem >>> 11) * 0x1F25); // BCH(18,6)
    var bits = (this.version << 12 | rem) >>> 0;

    // Two 6x3 blocks, mirrored about the diagonal.
    for (i = 0; i < 18; i++) {
      var dark = getBit(bits, i);
      var a = this.size - 11 + i % 3;
      var b = Math.floor(i / 3);
      this.setFunctionModule(a, b, dark);
      this.setFunctionModule(b, a, dark);
    }
  };

  Matrix.prototype.drawFunctionPatterns = function () {
    var i, j;
    // Timing patterns.
    for (i = 0; i < this.size; i++) {
      this.setFunctionModule(6, i, i % 2 === 0);
      this.setFunctionModule(i, 6, i % 2 === 0);
    }
    // Finder patterns (their separators overwrite the timing ends harmlessly).
    this.drawFinderPattern(3, 3);
    this.drawFinderPattern(this.size - 4, 3);
    this.drawFinderPattern(3, this.size - 4);

    // Alignment patterns, skipping the three that would collide with finders.
    var pos = this.alignmentPositions();
    var n = pos.length;
    for (i = 0; i < n; i++) {
      for (j = 0; j < n; j++) {
        if ((i === 0 && j === 0) || (i === 0 && j === n - 1) || (i === n - 1 && j === 0)) continue;
        this.drawAlignmentPattern(pos[i], pos[j]);
      }
    }

    // Reserve the format/version areas now (contents rewritten once the mask is known).
    this.drawFormatBits(0);
    this.drawVersionBits();
  };

  /** Lay the interleaved codewords into the zigzag data region. */
  Matrix.prototype.drawCodewords = function (data) {
    var i = 0;
    for (var right = this.size - 1; right >= 1; right -= 2) {
      if (right === 6) right = 5; // the vertical timing column is not a data column
      for (var vert = 0; vert < this.size; vert++) {
        for (var j = 0; j < 2; j++) {
          var x = right - j;
          var upward = ((right + 1) & 2) === 0;
          var y = upward ? this.size - 1 - vert : vert;
          if (!this.isFunction[y][x] && i < data.length * 8) {
            this.modules[y][x] = getBit(data[i >>> 3], 7 - (i & 7));
            i++;
          }
          // Remaining modules past the codeword stream stay light (remainder bits).
        }
      }
    }
    if (i !== data.length * 8) throw new Error('QR: codeword placement mismatch');
  };

  /** XOR the data region with mask pattern `mask` (self-inverse — call twice to undo). */
  Matrix.prototype.applyMask = function (mask) {
    for (var y = 0; y < this.size; y++) {
      for (var x = 0; x < this.size; x++) {
        var invert;
        switch (mask) {
          case 0: invert = (x + y) % 2 === 0; break;
          case 1: invert = y % 2 === 0; break;
          case 2: invert = x % 3 === 0; break;
          case 3: invert = (x + y) % 3 === 0; break;
          case 4: invert = (Math.floor(x / 3) + Math.floor(y / 2)) % 2 === 0; break;
          case 5: invert = (x * y) % 2 + (x * y) % 3 === 0; break;
          case 6: invert = ((x * y) % 2 + (x * y) % 3) % 2 === 0; break;
          case 7: invert = ((x + y) % 2 + (x * y) % 3) % 2 === 0; break;
          default: throw new RangeError('QR: bad mask ' + mask);
        }
        if (invert && !this.isFunction[y][x]) this.modules[y][x] = !this.modules[y][x];
      }
    }
  };

  // --- Penalty scoring (spec rules 1-4) --------------------------------------

  /** Push a run length into the 7-slot history, padding the first run with the border. */
  function finderAddHistory(runLen, hist, size) {
    if (hist[0] === 0) runLen += size; // the light quiet zone before the first run
    hist.pop();
    hist.unshift(runLen);
  }

  /** Count 1:1:3:1:1 finder-like patterns with a 4-wide light zone on either side. */
  function finderCountPatterns(hist) {
    var n = hist[1];
    var core = n > 0 && hist[2] === n && hist[3] === n * 3 && hist[4] === n && hist[5] === n;
    return (core && hist[0] >= n * 4 && hist[6] >= n ? 1 : 0) +
           (core && hist[6] >= n * 4 && hist[0] >= n ? 1 : 0);
  }

  function finderTerminate(runColor, runLen, hist, size) {
    if (runColor) { finderAddHistory(runLen, hist, size); runLen = 0; }
    runLen += size; // the light quiet zone after the last run
    finderAddHistory(runLen, hist, size);
    return finderCountPatterns(hist);
  }

  Matrix.prototype.penaltyScore = function () {
    var result = 0, x, y, runLen, runColor, hist;
    var size = this.size;

    // Rule 1 (rows) + rule 3 (rows).
    for (y = 0; y < size; y++) {
      runColor = false; runLen = 0; hist = [0, 0, 0, 0, 0, 0, 0];
      for (x = 0; x < size; x++) {
        if (this.modules[y][x] === runColor) {
          runLen++;
          if (runLen === 5) result += PENALTY_N1;
          else if (runLen > 5) result++;
        } else {
          finderAddHistory(runLen, hist, size);
          if (!runColor) result += finderCountPatterns(hist) * PENALTY_N3;
          runColor = this.modules[y][x];
          runLen = 1;
        }
      }
      result += finderTerminate(runColor, runLen, hist, size) * PENALTY_N3;
    }
    // Rule 1 (columns) + rule 3 (columns).
    for (x = 0; x < size; x++) {
      runColor = false; runLen = 0; hist = [0, 0, 0, 0, 0, 0, 0];
      for (y = 0; y < size; y++) {
        if (this.modules[y][x] === runColor) {
          runLen++;
          if (runLen === 5) result += PENALTY_N1;
          else if (runLen > 5) result++;
        } else {
          finderAddHistory(runLen, hist, size);
          if (!runColor) result += finderCountPatterns(hist) * PENALTY_N3;
          runColor = this.modules[y][x];
          runLen = 1;
        }
      }
      result += finderTerminate(runColor, runLen, hist, size) * PENALTY_N3;
    }

    // Rule 2 — 2x2 blocks of one colour.
    for (y = 0; y < size - 1; y++) {
      for (x = 0; x < size - 1; x++) {
        var c = this.modules[y][x];
        if (c === this.modules[y][x + 1] && c === this.modules[y + 1][x] && c === this.modules[y + 1][x + 1]) {
          result += PENALTY_N2;
        }
      }
    }

    // Rule 4 — deviation of the dark-module proportion from 50%.
    var dark = 0;
    for (y = 0; y < size; y++) for (x = 0; x < size; x++) if (this.modules[y][x]) dark++;
    var total = size * size;
    var k = Math.ceil(Math.abs(dark * 20 - total * 10) / total) - 1;
    result += k * PENALTY_N4;

    return result;
  };

  // ---------------------------------------------------------------------------
  // Public API
  // ---------------------------------------------------------------------------

  function encode(text, opts) {
    opts = opts || {};
    if (typeof text !== 'string') throw new TypeError('QR.encode: text must be a string');

    var levelName = (opts.ecLevel || 'M').toUpperCase();
    if (!(levelName in EC_LEVELS)) {
      throw new Error("QR.encode: ecLevel must be 'L', 'M', 'Q' or 'H' (got " + opts.ecLevel + ')');
    }
    var ecl = EC_LEVELS[levelName];

    var minVer = opts.minVersion === undefined ? MIN_VERSION : opts.minVersion | 0;
    var maxVer = opts.maxVersion === undefined ? MAX_VERSION : opts.maxVersion | 0;
    if (minVer < MIN_VERSION || minVer > MAX_VERSION || maxVer < minVer || maxVer > MAX_VERSION) {
      throw new RangeError('QR.encode: version range ' + minVer + '..' + maxVer + ' is out of 1..40');
    }

    var seg = makeSegment(text);

    // ECI 26 declares UTF-8 explicitly. Pure-ASCII payloads are identical under the
    // default ISO-8859-1 interpretation, so the 12 extra bits are only spent when a
    // non-ASCII byte is actually present.
    var useEci;
    if (opts.eci === true) useEci = true;
    else if (opts.eci === false) useEci = false;
    else useEci = seg.mode === MODE_BYTE && Array.prototype.some.call(seg.bytes, function (b) { return b >= 0x80; });
    var eciBits = useEci ? 12 : 0;

    // Smallest version in range whose data capacity holds the segment.
    var dataBits = segmentDataBits(seg);
    var version = -1;
    for (var v = minVer; v <= maxVer; v++) {
      var need = eciBits + 4 + ccWidth(seg.mode, v) + dataBits;
      // The count field must also be representable in its width at this version.
      if (seg.charCount >>> ccWidth(seg.mode, v) !== 0) continue;
      if (need <= numDataCodewords(v, ecl) * 8) { version = v; break; }
    }
    if (version === -1) {
      var cap = numDataCodewords(maxVer, ecl) * 8;
      throw new Error(
        'QR.encode: payload too large — ' + seg.charCount + ' ' + seg.mode.name +
        ' units need ' + (eciBits + 4 + ccWidth(seg.mode, maxVer) + dataBits) +
        ' bits but version ' + maxVer + '-' + levelName + ' holds ' + cap + ' bits'
      );
    }

    var codewords = buildCodewords(seg, version, ecl, useEci);

    var m = new Matrix(version, ecl);
    m.drawFunctionPatterns();
    m.drawCodewords(codewords);

    // Pick the mask: explicit if given, otherwise the lowest-penalty of all eight.
    var chosen;
    if (opts.mask !== undefined && opts.mask !== null) {
      chosen = opts.mask | 0;
      if (chosen < 0 || chosen > 7) throw new RangeError('QR.encode: mask must be 0..7');
      m.applyMask(chosen);
      m.drawFormatBits(chosen);
    } else {
      var best = Infinity;
      chosen = 0;
      for (var mask = 0; mask < 8; mask++) {
        m.applyMask(mask);
        m.drawFormatBits(mask);
        var score = m.penaltyScore();
        if (score < best) { best = score; chosen = mask; }
        m.applyMask(mask); // undo (XOR is its own inverse)
      }
      m.applyMask(chosen);
      m.drawFormatBits(chosen);
    }

    return {
      size: m.size,
      modules: m.modules,
      version: version,
      ecLevel: levelName,
      mask: chosen,
      mode: seg.mode.name,
      eci: useEci
    };
  }

  /** Max payload units (chars for numeric/alphanumeric, UTF-8 bytes for byte mode). */
  function capacity(version, ecLevel, mode) {
    var ecl = EC_LEVELS[(ecLevel || 'M').toUpperCase()];
    if (ecl === undefined) throw new Error('QR.capacity: bad ecLevel ' + ecLevel);
    var m = mode === 'numeric' ? MODE_NUMERIC : (mode === 'alphanumeric' ? MODE_ALPHANUM : MODE_BYTE);
    var bits = numDataCodewords(version, ecl) * 8 - 4 - ccWidth(m, version);
    if (m === MODE_BYTE) return Math.floor(bits / 8);
    if (m === MODE_ALPHANUM) {
      var n = Math.floor(bits / 11) * 2;
      return bits % 11 >= 6 ? n + 1 : n;
    }
    var d = Math.floor(bits / 10) * 3;
    var r = bits % 10;
    return r >= 7 ? d + 2 : (r >= 4 ? d + 1 : d);
  }

  global.QR = { encode: encode, capacity: capacity, VERSION: '1.0.0' };

})(typeof globalThis !== 'undefined' ? globalThis : this);
