# RFID reader case — v7

A two-piece printable enclosure for a USB RFID reader board, so the reader is a device on
a desk rather than a bare PCB on a cable. Print both halves, drop the board in, snap shut.

![case lineage preview](preview_case_lineage_v3.png)

*(preview is the v3 ancestor — same seal mechanism and surface treatment, thin-lid split.)*

## Files

| File | What |
|---|---|
| `rfid_case_bottom_v7.stl` | bottom half — print broad-face down |
| `rfid_case_top_v7.stl` | top half — print broad-face down |
| `gen_rfid_reader_case_v7.py` | the generator that produced both |

```bash
python3 gen_rfid_reader_case_v7.py      # regenerate the STLs
```

The generator is included because the STL is an *output*, not the design. Changing the
cavity for a different board is a constant at the top of the file, not mesh surgery.

## Print settings

- **Both halves broad-face DOWN**, seam up. The seal features open upward in that pose, so
  there are no overhangs and no supports.
- Bed: ~120 × 90 mm is enough for either half.
- The gyroid relief on the outer faces is a recess, printed as a bed-side detail — a
  smooth sheet works better than a textured one.

## The snap fit — read before printing a batch

The halves close with a **tongue-and-groove joint plus a retention bead**, split at the
Z mid-plane so the two halves are balanced (~11 mm each) rather than a thin lid on a deep
tray.

> **Clearances are sub-millimetre** (`TG_CLEAR = 0.2` mm per side) and the smoothing pass
> (`SMOOTH_SIGMA = 0.7`) rounds the tongue toward a near-zero-clearance press fit. It seals
> well and it can be tight to seat.
>
> **Print one set and try the fit before printing several.** If it will not seat, raise
> `TG_CLEAR` and regenerate; if it will not stay shut, raise the bead diameter. Both are
> single constants near the top of the generator.

This is the one step in the whole project with no cheap rehearsal — a test print *is* the
rehearsal, which is why it is worth the hour.

## Lineage

v7 continues the **v3 → v6** line, not the simplified v4/v5 detour:

- **v3** introduced the real tongue-and-groove-plus-bead seal and engraved the gyroid into
  both broad faces (rather than leaving them flat), keeping the RF tap surface intact.
- **v6** re-split the body at the **Z mid-plane** into two balanced clamshell halves and
  adopted a calmer gyroid cell size (`SCALE_MIN/MAX = 4.2/7.2`) so the pattern reads as a
  surface rather than as noise.
- **v7** is v6 with the tuning settled.

## Fit

Sized around a ~14 mm-tall USB reader board with a USB cutout on one end. A different
board means editing the cavity constants (`CLR`, `WALL`, `USB_W`) and regenerating — the
generator is parametric for exactly this reason.

Licensed MIT along with the rest of the project: print it, remix it, sell prints of it.
