#!/usr/bin/env python3
"""
RFID reader case — v7  (v6 with the tuning settled: snap-seal carried from v3, KUNAI MID-PLANE split, Orin-drawer cell clamp)

LINEAGE / OPERATOR DIRECTIVES (2026-06-01):
  - Start from the v3 snap-and-seal line (NOT the simplified v4/v5). v3 had the
    KUNAI bead+tongue+groove join — keep it.
  - "slice it in half from the thickness ... do like the kunai from the MIDDLE of
    the plane not top": v3 was a thin 5 mm lid on a 17 mm base. v6 is a Z-axis
    CLAMSHELL split at the Z MID-PLANE -> two balanced halves (~11 mm each), the
    seam at center, exactly like kunai_360_onex_v4.py:489 half(). The tongue+bead
    (bottom half) rises into the groove (top half) AT the mid-plane; each half
    prints broad-face DOWN / seam UP so the seal opens upward (no overhang).
  - "same limitation sizes we had for the orin drawer so the waves don't come out
    too small and too big": adopt the Orin drawer's gyroid cell clamp VERBATIM
    (pearl_box_v2_voxel_v4.py build_drawer): SCALE_MIN/MAX = 4.2/7.2, W_XY=W_Z=
    0.048 (isotropic), TWIST_K=0.01, cs clamped to [4.2,7.2]. v3 used 3.0/5.5,
    W_XY=0.14, TWIST_K=0.04 -> busy/uneven waves. The drawer band = mid-range.

SURVIVABILITY (scar feedback_gyroid_additive_not_carved): the gyroid is ENGRAVED
into a solid skin, never abs(g)-t carved THROUGH the wall. Broad (Z) faces are a
solid GYR_WALL skin; the maze is a shallow GYR_VOID recess -> >= GYR_BACK solid
behind. Side/end walls solid WALL. No lace.

Reader (operator-measured): 70 (X) x 105 (Y) x 14 (Z) mm. USB on a short (70 mm,
X-centered) side, 11 mm wide x full thickness, open through a side wall.

ASSEMBLY (KUNAI clamshell): two halves meet on the Z mid-plane. Camera sits in the
enclosed cavity. Tongue+snap-bead on the bottom-half seam ring clicks into the
groove in the top-half seam ring = retention + dust/light seal, hardware-free.

Print (QCC-4): each half BROAD-FACE DOWN (its outer gyroid face on the bed), seam
UP. The gyroid is a shallow vertical-walled recess on the down face; tongue/groove
open upward -> no overhang, brim-free (island-cleaned lands give bed contact).

QCC: QCC-2 solid backing >= GYR_BACK behind the engrave; QCC-3 the seam is an
OPENABLE snap join (documented exception, like KUNAI's openable magnet/seal seam);
QCC-4 orientation declared; QCC-5 gaussian-manifold + floater drop + assert
is_watertight.

Run:  python3 gen_rfid_reader_case_v7.py
Out:  rfid_case_top_v7.stl, rfid_case_bottom_v7.stl
"""
import os
import numpy as np
import trimesh
from skimage import measure
from scipy import ndimage

# ── reader + case parameters (mm) ─────────────────────────────────────────
READER_X, READER_Y, READER_Z = 70.0, 105.0, 14.0
CLR        = 0.4                       # cavity clearance per side
WALL       = 3.0                       # solid side/end (X,Y) wall thickness
GYR_WALL   = 4.0                       # broad-face (Z) wall thickness (carries the engrave)
GYR_VOID   = 1.5                       # gyroid engrave depth (shallow) — Orin-drawer-ish relief
GYR_BACK   = GYR_WALL - GYR_VOID       # 2.5 mm solid behind the maze (QCC-2)
RIM_W      = 3.0                       # thin solid border around each broad face (no dead rim)
GROOVE_LEVEL = -0.15                   # engrave where coral_field < this (fat lands, thin channels)
MIN_LAND_MM2 = 8.0                     # island-clean threshold
USB_W      = 11.0
RES        = 0.5
PAD        = 2.0
SMOOTH_SIGMA = 0.7                     # 2-manifold gyroid edges (KUNAI:379)
MIN_BODY_FACES = 500                   # QCC-5 floater drop

# ── Orin-drawer gyroid cell clamp (pearl_box_v2_voxel_v4.py build_drawer) VERBATIM ──
SCALE     = 1.2
SCALE_MIN = 4.2        # was v3-rfid 3.0  -> Orin drawer 4.2 (waves not too big)
SCALE_MAX = 7.2        # was v3-rfid 5.5  -> Orin drawer 7.2 (waves not too small)
W_XY      = 0.048      # was v3-rfid 0.14 -> Orin drawer 0.048 (bigger, calmer cells)
W_Z       = 0.048      # isotropic
TWIST_K   = 0.01       # was v3-rfid 0.04 -> Orin drawer 0.01 (gentle twist)

# ── KUNAI clamshell seam (tongue + groove + snap bead) at the Z mid-plane ──
# (carried from v3 snap-seal + kunai_360_onex_v4.py:489 half(); on the mid-plane now)
MATE_LAND  = 2.5       # flat solid land around the seam ring (clean mating faces)
TG_IN      = 1.4       # tongue ring: inner edge this far in from the wall outline
TG_OUT     = 3.0       # tongue ring: outer edge this far in
TG_CLEAR   = 0.2       # groove clearance per side
SNAP       = 0.5       # snap-bead protrusion (clicks past the groove mouth)
TONGUE_H   = 2.5       # tongue height above the mid-plane / groove depth

# ── derived geometry ──────────────────────────────────────────────────────
INNER_X = READER_X + 2 * CLR          # 70.8
INNER_Y = READER_Y + 2 * CLR          # 105.8
CAV_Z   = READER_Z + 1.0              # 15.0  internal Z (1 mm play)

OUT_X   = INNER_X + 2 * WALL          # 76.8
OUT_Y   = INNER_Y + 2 * WALL          # 111.8
OUT_Z   = CAV_Z + 2 * GYR_WALL        # 23.0  total thickness (two broad-face skins)
MIDZ    = OUT_Z / 2.0                 # 11.5  clamshell split plane -> two ~11.5 mm halves
CX, CY  = OUT_X / 2.0, OUT_Y / 2.0

OUT = os.path.dirname(os.path.abspath(__file__))


def coral_field(X, Y, Z):
    """resonant_coral_field_clean — abs(gyroid)-0.6 maze, Orin-drawer cell clamp, twist about center."""
    freq_osc = 0.05 / SCALE
    # book-match: fold X about CX everywhere it enters the field (incl. the cell-size
    # modulation), so the whole maze is mirror-symmetric across the portrait centerline.
    Xb = CX - np.abs(X - CX)
    mod = np.sin((Xb + Y + Z * 0.5) * freq_osc) * 0.5 + 0.5
    cs = SCALE_MIN + mod * (SCALE_MAX - SCALE_MIN)
    cs_mid = (SCALE_MIN + SCALE_MAX) * 0.5
    cs = np.where(cs < cs_mid, cs * 2.0, cs).astype(np.float32)   # the drawer's clamp
    # BOOK-MATCH (operator 2026-06-01): fold X about the portrait centerline so every
    # point sees the same field as its mirror twin across CX -> a symmetric, mirrored
    # ("open book" / Rorschach) maze down the long axis. abs() makes f(X)=f(2*CX-X).
    dx = -np.abs(X - CX); dy = Y - CY
    tw = np.sqrt(dx * dx + dy * dy) * (TWIST_K / SCALE)
    xt = dx * np.cos(tw) - dy * np.sin(tw)
    yt = dx * np.sin(tw) + dy * np.cos(tw)
    SX = xt * cs * W_XY; SY = yt * cs * W_XY; SZ = Z * cs * W_Z
    val = np.sin(SX) * np.cos(SY) + np.sin(SY) * np.cos(SZ) + np.sin(SZ) * np.cos(SX)
    return (np.abs(val) - 0.6).astype(np.float32)


def grid():
    xr = np.arange(-PAD, OUT_X + PAD, RES, dtype=np.float32)
    yr = np.arange(-PAD, OUT_Y + PAD, RES, dtype=np.float32)
    zr = np.arange(-PAD, OUT_Z + PAD, RES, dtype=np.float32)
    X, Y, Z = np.meshgrid(xr, yr, zr, indexing="ij")
    return X, Y, Z, (xr[0], yr[0], zr[0])


def _ring2d(X2, Y2, t_in, t_out):
    """Rectangular ring band between insets t_in and t_out from the OUT_X/OUT_Y outline."""
    outer = (X2 >= t_in) & (X2 <= OUT_X - t_in) & (Y2 >= t_in) & (Y2 <= OUT_Y - t_in)
    inner = (X2 >= t_out) & (X2 <= OUT_X - t_out) & (Y2 >= t_out) & (Y2 <= OUT_Y - t_out)
    return outer & ~inner


def kunai_groove_mask(X2, Y2):
    """Full-coverage gyroid grooves on a broad face: one constant-Z slice, footprint
       eroded only RIM_W (thin border), island-cleaned. 2-D bool. (KUNAI broad-face method)."""
    Zc = np.full_like(X2, MIDZ)                  # one constant slice (reads as the real maze)
    cf2 = coral_field(X2, Y2, Zc)
    foot = (X2 >= 0) & (X2 <= OUT_X) & (Y2 >= 0) & (Y2 <= OUT_Y)
    inner = ndimage.binary_erosion(foot, iterations=max(1, int(round(RIM_W / RES))))
    g2 = (cf2 < GROOVE_LEVEL) & inner
    # island-clean: merge tiny solid LAND blobs into the groove (sweep-prone)
    inv = (~g2) & inner
    lbl, n = ndimage.label(inv)
    if n:
        sizes = np.bincount(lbl.ravel())
        min_cells = int(round(MIN_LAND_MM2 / (RES * RES)))
        small = np.where(sizes < min_cells)[0]
        small = small[small != 0]
        if small.size:
            g2 = g2 | np.isin(lbl, small)
    return g2


def build_volume():
    """Whole closed case as one field; halves are cut + sealed in half()."""
    X, Y, Z, origin = grid()
    vol = np.full(X.shape, -1.0, dtype=np.float32)

    outer = ((X >= 0) & (X <= OUT_X) & (Y >= 0) & (Y <= OUT_Y) & (Z >= 0) & (Z <= OUT_Z))
    cav = ((X >= WALL) & (X <= WALL + INNER_X) &
           (Y >= WALL) & (Y <= WALL + INNER_Y) &
           (Z >= GYR_WALL) & (Z <= GYR_WALL + CAV_Z))
    vol[outer & ~cav] = 1.0                          # solid skin (walls + both broad faces)

    # full-coverage KUNAI gyroid engraved into BOTH broad faces (Orin-drawer cells)
    X2 = X[:, :, 0]; Y2 = Y[:, :, 0]
    g2 = kunai_groove_mask(X2, Y2)
    zb_bot = (Z[0, 0, :] >= 0.0) & (Z[0, 0, :] < GYR_VOID)               # -Z face
    zb_top = (Z[0, 0, :] > OUT_Z - GYR_VOID) & (Z[0, 0, :] <= OUT_Z)     # +Z face
    vol[g2[:, :, None] & (zb_bot | zb_top)[None, None, :]] = -1.0

    # ── SIDES (operator 2026-06-01: "include the sides") ──
    # Same maze engraved into all 4 perimeter walls, inward from each outer side
    # face by GYR_VOID. Continuous with the broad-face field (one coral_field), so
    # the pattern wraps the corners. Side walls are WALL=3.0 -> >=1.5 mm solid
    # behind the groove (watertight). `& (vol > 0)` carves only existing wall, never
    # the cavity. Bands sit outside the cavity (cavity starts at Y/X = WALL = 3.0).
    cf3 = coral_field(X, Y, Z)
    g3 = cf3 < GROOVE_LEVEL
    side = (((Y >= 0.0) & (Y < GYR_VOID)) | ((Y > OUT_Y - GYR_VOID) & (Y <= OUT_Y)) |
            ((X >= 0.0) & (X < GYR_VOID)) | ((X > OUT_X - GYR_VOID) & (X <= OUT_X)))
    vol[g3 & side & (vol > 0)] = -1.0

    # USB slot: centered in X on the -Y short wall, full internal Z, open through the wall
    usb = ((X >= CX - USB_W / 2) & (X <= CX + USB_W / 2) &
           (Y >= -1.0) & (Y <= WALL + 0.5) &
           (Z >= GYR_WALL) & (Z <= GYR_WALL + CAV_Z))
    vol[usb] = -1.0

    return vol, origin


def half(vol, origin, which):
    """KUNAI clamshell half: clip at the Z mid-plane + add the snap-seal ring on the seam.
       bottom: solid below MIDZ + a tongue ring (with snap bead) rising above MIDZ.
       top   : solid above MIDZ + a groove ring (wider) receiving the tongue.
       Each half prints broad-face DOWN, seam UP -> seal opens upward, no overhang."""
    v = vol.copy()
    nx, ny, nz = v.shape
    z = origin[2] + np.arange(nz) * RES
    x = origin[0] + np.arange(nx) * RES
    y = origin[1] + np.arange(ny) * RES
    X2, Y2 = np.meshgrid(x, y, indexing="ij")

    # flat solid seam land so the two halves meet flat — but DON'T re-solidify across
    # the USB span (operator 2026-06-01: "don't put a barrier between the two pieces
    # for your usb port"). The mate band fills the wall ring solid; we then re-open the
    # USB column through it so the port stays a continuous opening across the seam, with
    # each half contributing an open half-channel (no bridge between the pieces).
    seam_band = (z > MIDZ - MATE_LAND) & (z < MIDZ + MATE_LAND)
    wall_ring = _ring2d(X2, Y2, 0.0, WALL)           # the solid wall footprint
    usb_col = (np.abs(X2 - CX) < USB_W / 2) & (Y2 < WALL + 0.5)   # USB footprint in the -Y wall
    seam_fill = wall_ring & ~usb_col                 # mate everywhere EXCEPT the USB span
    v[seam_fill[:, :, None] & seam_band[None, None, :]] = 1.0
    # keep the USB column carved open through the entire seam band (both halves)
    v[usb_col[:, :, None] & seam_band[None, None, :]] = -1.0

    # clip to this half
    if which == "bottom":
        v[:, :, z > MIDZ] = -1.0
    else:
        v[:, :, z < MIDZ] = -1.0

    tongue2d = _ring2d(X2, Y2, TG_IN, TG_OUT)
    bead2d   = _ring2d(X2, Y2, TG_IN - SNAP, TG_OUT)             # bead sits SNAP outboard of the tongue
    groove2d = _ring2d(X2, Y2, TG_IN - TG_CLEAR, TG_OUT + TG_CLEAR)
    relief2d = _ring2d(X2, Y2, TG_IN - SNAP - TG_CLEAR, TG_OUT + TG_CLEAR)
    # break the seam ring across the USB span on the -Y edge so it can't obstruct the port
    usb_open = (np.abs(X2 - CX) < USB_W / 2 + 2.0) & (Y2 < WALL + 1.0)
    for m in (tongue2d, bead2d, groove2d, relief2d):
        m &= ~usb_open

    zt   = (z >= MIDZ) & (z < MIDZ + TONGUE_H)
    zbed = (z >= MIDZ + 0.45 * TONGUE_H) & (z < MIDZ + 0.45 * TONGUE_H + 0.8)
    zg   = (z >= MIDZ - 0.01) & (z < MIDZ + TONGUE_H + 0.4)
    if which == "bottom":
        v[tongue2d[:, :, None] & zt[None, None, :]] = 1.0        # tongue rises from the seam
        v[bead2d[:, :, None]   & zbed[None, None, :]] = 1.0      # snap bead on the tongue
    else:
        v[groove2d[:, :, None] & zg[None, None, :]] = -1.0       # groove receives the tongue
        v[relief2d[:, :, None] & zbed[None, None, :]] = -1.0     # bead snaps into here

    return mesh_from_vol(v, origin)


def mesh_from_vol(vol, origin):
    vol = ndimage.gaussian_filter(vol.astype(np.float32), sigma=SMOOTH_SIGMA)
    verts, faces, _, _ = measure.marching_cubes(vol, level=0.0)
    verts = verts * RES + np.array(origin, dtype=np.float32)
    m = trimesh.Trimesh(vertices=verts, faces=faces, process=True)
    m.merge_vertices()
    bodies = m.split(only_watertight=False)
    keep = [b for b in bodies if len(b.faces) >= MIN_BODY_FACES]
    if not keep:
        keep = [max(bodies, key=lambda b: len(b.faces))]
    m = trimesh.util.concatenate(keep) if len(keep) > 1 else keep[0]
    m.merge_vertices()
    m.update_faces(m.nondegenerate_faces())
    m.remove_unreferenced_vertices()
    m.fix_normals()
    if not m.is_watertight:
        m.fill_holes()
    return m, len(bodies) - len(keep)


def main():
    vol, origin = build_volume()
    for name, which in (("bottom", "bottom"), ("top", "top")):
        m, dropped = half(vol, origin, which)
        assert m.is_watertight, f"rfid v7 {name}: watertight gate failed — investigate"
        path = os.path.join(OUT, f"rfid_case_{name}_v7.stl")
        m.export(path)
        d = m.bounds[1] - m.bounds[0]
        nb = len(m.split(only_watertight=False))
        print(f"[{name}] watertight={m.is_watertight} winding={m.is_winding_consistent} "
              f"faces={len(m.faces)} bodies={nb} floaters_dropped={dropped} "
              f"bbox={d[0]:.1f}x{d[1]:.1f}x{d[2]:.1f}mm")
    print(f"split: Z mid-plane MIDZ={MIDZ:.1f}mm -> two halves ~{MIDZ:.1f}mm each (KUNAI clamshell)")
    print(f"cells: Orin-drawer clamp SCALE_MIN/MAX={SCALE_MIN}/{SCALE_MAX} W_XY=W_Z={W_XY} TWIST_K={TWIST_K}")
    print(f"skin: GYR_WALL={GYR_WALL} engrave={GYR_VOID} -> {GYR_BACK}mm solid behind maze; walls {WALL}mm")
    print(f"seal: KUNAI tongue+bead -> groove on the mid-plane seam (TG {TG_IN}-{TG_OUT} SNAP {SNAP})")


if __name__ == "__main__":
    main()
