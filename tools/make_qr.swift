// make_qr.swift — generate a print-ready QR for a card, and PROVE it scans.
//
// Why Swift and not a Python library: this repo has no install step, and macOS
// already ships CoreImage, which both generates QR codes (CIQRCodeGenerator) and
// reads them back (CIDetector). Same reason make_icon.py shells out to iconutil.
// A dependency you do not add is a dependency that cannot rot.
//
// The generator emits one pixel per QR module. Scaling that up with any smoothing
// produces grey edges, and grey edges are what makes a printed code fail to scan
// at small sizes — so the upscale is nearest-neighbour with interpolation
// explicitly disabled, and every module lands on a whole-pixel boundary.
//
// It also adds the 4-module quiet zone. CIQRCodeGenerator does not, and a QR
// printed hard against artwork with no margin is the single most common reason a
// card-sized code will not read.
//
//   swift tools/make_qr.swift --text "https://…" --out card_qr.png [--px 2048]
//                             [--ec Q] [--transparent] [--dark RRGGBB]
//
// Always verifies by decoding its own output; exits non-zero if it cannot be read.

import Foundation
import CoreImage
import CoreGraphics
import ImageIO
import UniformTypeIdentifiers

func die(_ m: String) -> Never { FileHandle.standardError.write((m + "\n").data(using: .utf8)!); exit(1) }

// ---- arguments ----
var text = "", out = "", px = 2048, ec = "Q", transparent = false
var dark: (UInt8, UInt8, UInt8) = (0, 0, 0)
var a = Array(CommandLine.arguments.dropFirst()), i = 0
while i < a.count {
    switch a[i] {
    case "--text": i += 1; text = i < a.count ? a[i] : ""
    case "--out": i += 1; out = i < a.count ? a[i] : ""
    case "--px": i += 1; px = Int(i < a.count ? a[i] : "") ?? 2048
    case "--ec": i += 1; ec = (i < a.count ? a[i] : "Q").uppercased()
    case "--transparent": transparent = true
    case "--dark":
        i += 1
        let h = i < a.count ? a[i] : "000000"
        if h.count == 6, let v = Int(h, radix: 16) {
            dark = (UInt8((v >> 16) & 255), UInt8((v >> 8) & 255), UInt8(v & 255))
        }
    default: die("unknown argument: \(a[i])")
    }
    i += 1
}
if text.isEmpty || out.isEmpty { die("usage: --text <string> --out <file.png> [--px N] [--ec L|M|Q|H] [--transparent] [--dark RRGGBB]") }
guard ["L", "M", "Q", "H"].contains(ec) else { die("--ec must be L, M, Q or H") }

// ---- generate the raw module grid (1 px per module) ----
guard let filter = CIFilter(name: "CIQRCodeGenerator") else { die("CIQRCodeGenerator unavailable") }
filter.setValue(text.data(using: .isoLatin1) ?? text.data(using: .utf8)!, forKey: "inputMessage")
filter.setValue(ec, forKey: "inputCorrectionLevel")
guard let raw = filter.outputImage else { die("could not encode — is the text too long for a QR?") }

let ctx = CIContext(options: [.useSoftwareRenderer: true])
guard let rawCG = ctx.createCGImage(raw, from: raw.extent) else { die("could not rasterise") }
let modules = rawCG.width                                  // square
let quiet = 4                                              // REQUIRED margin, in modules
let total = modules + quiet * 2

// Round the output so every module is an exact whole number of pixels. A QR whose
// modules are 7.3 px wide has a different width on some rows than others, and that
// is a scan failure that looks like a rendering nicety.
let scale = max(1, px / total)
let side = total * scale

// ---- draw: nearest-neighbour, hard edges ----
let cs = CGColorSpaceCreateDeviceRGB()
guard let bmp = CGContext(data: nil, width: side, height: side, bitsPerComponent: 8,
                          bytesPerRow: 0, space: cs,
                          bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue)
else { die("could not allocate bitmap") }

bmp.interpolationQuality = .none
bmp.setShouldAntialias(false)

if transparent {
    bmp.clear(CGRect(x: 0, y: 0, width: side, height: side))
} else {
    bmp.setFillColor(CGColor(red: 1, green: 1, blue: 1, alpha: 1))
    bmp.fill(CGRect(x: 0, y: 0, width: side, height: side))
}

// Read the 1x grid and paint each dark module as a solid rectangle. Painting
// rectangles rather than scaling the image is what guarantees no soft edge
// survives, whatever the graphics stack decides to do.
guard let data = rawCG.dataProvider?.data, let ptr = CFDataGetBytePtr(data) else { die("no pixel data") }
let bpr = rawCG.bytesPerRow, bpp = rawCG.bitsPerPixel / 8
bmp.setFillColor(CGColor(red: CGFloat(dark.0) / 255, green: CGFloat(dark.1) / 255,
                         blue: CGFloat(dark.2) / 255, alpha: 1))
for y in 0..<modules {
    for x in 0..<modules {
        let lum = ptr[y * bpr + x * bpp]
        if lum < 128 {                                     // dark module
            // CGImage origin is top-left; CGContext is bottom-left. Flip y.
            let px0 = (x + quiet) * scale
            let py0 = (modules - 1 - y + quiet) * scale
            bmp.fill(CGRect(x: px0, y: py0, width: scale, height: scale))
        }
    }
}

guard let outImage = bmp.makeImage() else { die("could not compose image") }

// ---- write ----
let url = URL(fileURLWithPath: out)
guard let dest = CGImageDestinationCreateWithURL(url as CFURL, UTType.png.identifier as CFString, 1, nil)
else { die("could not create \(out)") }
CGImageDestinationAddImage(dest, outImage, nil)
guard CGImageDestinationFinalize(dest) else { die("could not write \(out)") }

// ---- VERIFY: decode our own output ----
// A QR that does not scan is worse than no QR, because it gets printed on a
// physical object before anyone finds out. Never emit one we have not read back.
//
// A transparent QR is decoded COMPOSITED ONTO WHITE, because that is the only way
// it can ever be scanned: a reader needs light/dark contrast, and transparency
// supplies neither. Verifying the bare file would fail for a reason that says
// nothing about whether the asset works — and, worse, passing it un-composited
// would let us ship a code that only scans if someone happens to place it on a
// light background. Check it the way it will be used, and say so in the output.
var verifyImage = outImage
if transparent {
    guard let flat = CGContext(data: nil, width: side, height: side, bitsPerComponent: 8,
                               bytesPerRow: 0, space: cs,
                               bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue)
    else { die("could not allocate verification bitmap") }
    flat.setFillColor(CGColor(red: 1, green: 1, blue: 1, alpha: 1))
    flat.fill(CGRect(x: 0, y: 0, width: side, height: side))
    flat.draw(outImage, in: CGRect(x: 0, y: 0, width: side, height: side))
    guard let composited = flat.makeImage() else { die("could not composite for verification") }
    verifyImage = composited
}
let written = CIImage(cgImage: verifyImage)
let detector = CIDetector(ofType: CIDetectorTypeQRCode, context: ctx,
                          options: [CIDetectorAccuracy: CIDetectorAccuracyHigh])
let found = (detector?.features(in: written) as? [CIQRCodeFeature])?.compactMap { $0.messageString } ?? []
guard let got = found.first else { die("VERIFY FAILED — the image we just wrote does not decode") }
guard got == text else { die("VERIFY FAILED — decoded \(got) but encoded \(text)") }

// Smallest size this can be printed and still read. The rule of thumb readers rely
// on is roughly 0.4 mm per module for a phone camera at normal distance; below that
// the modules blur into each other under ink spread. Reported so nobody has to
// guess how big to place it on a CR-80 card that is only 53.98 mm tall.
let minMM = Double(total) * 0.4

print("""
{"ok":true,"out":"\(out)","decoded":"\(got)","modules":\(modules),"quiet":\(quiet),\
"scale":\(scale),"side_px":\(side),"ec":"\(ec)","transparent":\(transparent),\
"verified_on_white":\(transparent),"min_print_mm":\(String(format: "%.1f", minMM))}
""")
