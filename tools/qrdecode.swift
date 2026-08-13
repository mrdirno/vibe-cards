import Foundation
import Vision
import AppKit

// Decode any barcode in an image using the system Vision framework.
// A card whose QR does not decode is a dead card, and that cannot be judged by eye.
for path in CommandLine.arguments.dropFirst() {
    guard let img = NSImage(contentsOfFile: path),
          let cg = img.cgImage(forProposedRect: nil, context: nil, hints: nil) else {
        print("\(path): unreadable"); continue
    }
    let req = VNDetectBarcodesRequest()
    try? VNImageRequestHandler(cgImage: cg, options: [:]).perform([req])
    let found = (req.results ?? [])
    if found.isEmpty { print("\((path as NSString).lastPathComponent): NO BARCODE DETECTED (\(cg.width)x\(cg.height))") }
    for r in found {
        print("\((path as NSString).lastPathComponent): \(r.symbology.rawValue) -> \(r.payloadStringValue ?? "<no payload>")")
    }
}
