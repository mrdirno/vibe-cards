#!/usr/bin/env python3
"""Pre-render a rotating globe as a sprite sheet.

    python3 tools/make_globe.py TEXTURE.jpg OUT.webp [--size 360] [--frames 24]
                               [--elev 18] [--tilt 23.4] [--dim 0.55]

A real sphere, not a texture slid behind a circle: every pixel is ray-cast
against the sphere and sampled from the equirectangular source, so the graticule
curves and the poles pinch the way they should.

Rendered at build time, which is why the page needs no canvas, no WebGL, no
JavaScript and no permission. The whole animation is one image and a CSS
`steps()`.

--elev is the vantage, and it has to agree with whatever the globe is sitting
next to. If a card in the same scene is tilted 64 degrees, the camera is about 26
degrees above the table and the globe must be seen from above too, or it reads as
pasted on.

The sheet steps in PIXELS on the page: percentage background-position resolves
against (container - image), not as a plain offset, so a percentage step lands
between frames and the sphere jitters.
"""

from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

try:
    import numpy as np
    from PIL import Image
except ImportError:
    print("make_globe.py needs Pillow and numpy (build-time only)", file=sys.stderr)
    raise SystemExit(2)


def render(tex_path: Path, size: int, frames: int, elev_deg: float,
           tilt_deg: float, dim: float, ss: int = 2) -> Image.Image:
    tex = Image.open(tex_path).convert("RGB")
    tw, th = tex.size
    T = np.asarray(tex).astype(np.float32) / 255.0

    n = size * ss
    r = n / 2
    yy, xx = np.mgrid[0:n, 0:n].astype(np.float32)
    nx, ny = (xx - r) / r, (yy - r) / r
    d2 = nx * nx + ny * ny
    inside = d2 <= 1.0
    nz = np.sqrt(np.clip(1.0 - d2, 0, 1))
    vx, vy, vz = nx, -ny, nz                      # screen y is down

    e = math.radians(-elev_deg)
    ce, se = math.cos(e), math.sin(e)
    wx, wy, wz = vx, vy * ce - vz * se, vy * se + vz * ce
    t = math.radians(-tilt_deg)
    ct, st = math.cos(t), math.sin(t)
    wx, wy = wx * ct - wy * st, wx * st + wy * ct

    # Light upper-left-front, so a scene lighting from that side agrees.
    L = np.array([-0.55, 0.62, 0.56], np.float32)
    L /= np.linalg.norm(L)
    lam = np.clip(vx * L[0] + vy * L[1] + vz * L[2], 0, 1)
    shade = (0.16 + 0.94 * lam)[..., None] * dim
    limb = (np.clip(nz, 0, 1) ** 0.35)[..., None]
    spec = (lam ** 34)[..., None] * 0.30 * dim

    sheet = Image.new("RGBA", (size * frames, size), (0, 0, 0, 0))
    for f in range(frames):
        a = 2 * math.pi * f / frames
        ca, sa = math.cos(a), math.sin(a)
        rx, rz = wx * ca + wz * sa, -wx * sa + wz * ca
        lat = np.arcsin(np.clip(wy, -1, 1))
        lon = np.arctan2(rx, rz)
        u = ((lon / (2 * math.pi) + 0.5) % 1.0) * (tw - 1)
        v = (0.5 - lat / math.pi) * (th - 1)
        col = T[np.clip(v.astype(np.int32), 0, th - 1),
                np.clip(u.astype(np.int32), 0, tw - 1)]
        col = col * shade * limb + spec
        rgba = np.zeros((n, n, 4), np.float32)
        rgba[..., :3] = np.clip(col, 0, 1)
        rgba[..., 3] = inside
        frame = Image.fromarray((rgba * 255).astype(np.uint8), "RGBA") \
                     .resize((size, size), Image.LANCZOS)
        sheet.paste(frame, (f * size, 0), frame)
    return sheet


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("texture", type=Path, help="equirectangular source, 2:1")
    ap.add_argument("out", type=Path)
    ap.add_argument("--size", type=int, default=360, help="frame size, px")
    ap.add_argument("--frames", type=int, default=24)
    ap.add_argument("--elev", type=float, default=18.0, help="camera elevation, degrees")
    ap.add_argument("--tilt", type=float, default=23.4, help="axial tilt, degrees")
    ap.add_argument("--dim", type=float, default=1.0,
                    help="brightness multiplier; below 1 for a background globe "
                         "that must not compete with what is in front of it")
    ap.add_argument("--quality", type=int, default=80)
    a = ap.parse_args(argv)

    if not a.texture.exists():
        print(f"no such texture: {a.texture}", file=sys.stderr)
        return 1

    sheet = render(a.texture, a.size, a.frames, a.elev, a.tilt, a.dim)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(a.out, "WEBP", quality=a.quality, method=6)
    print(f"{a.out} {sheet.size} {a.out.stat().st_size/1024:.0f} KB "
          f"({a.frames} frames @ {a.size}px, elev {a.elev}, dim {a.dim})")
    print(f"  css: background-size:{a.size*a.frames}px {a.size}px; "
          f"steps({a.frames}) to background-position-x:-{a.size*a.frames}px")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
