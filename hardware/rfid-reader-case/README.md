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

- **Both halves broad-face DOWN**, seam up. The seal features open upward in that pose.
  The surface pattern does overhang, which an earlier version of this page denied: with
  bed contact excluded, 10.3% of the bottom half's surface area and 10.7% of the top
  half's sits more than 45 degrees off vertical (2,919 mm² of 28,400 and 2,896 mm² of
  27,074). It is the ceiling of the pattern recess, not the seal. Those are short spans
  and a slicer may bridge them without supports, but nobody has sliced or printed this,
  so that is a statement about the shape and not about your printer.
- Bed: each half is **77 × 112 mm**. A 120 × 90 mm bed fits one only with the 112 mm
  side along the 120 mm axis.
- The gyroid relief on the outer faces is a recess, printed as a bed-side detail — a
  smooth sheet works better than a textured one.

### A known break in the top half, near the seam

Measured on the shipped file, the top half has a band 0.5 mm tall, sitting 2.55 to
2.95 mm above its seam face, where the outer wall is **open**. Draw horizontal lines
across the part at that height and a quarter of them (49 of 192 at the worst height)
pass clean through the whole part without touching any material. Above and below that
band the count is zero. The bottom half is clean: the same test returns zero at all 36
heights sampled through it.

The mesh topology says the same thing from the other side. Both halves are watertight
single bodies, but the top half has a genus of 41 against the bottom half's 4 — 41
tunnels through the solid instead of 4.

The cause is two cuts meeting. The seam groove is cut in behind the outer face, and the
surface pattern is cut 1.5 mm in from outside. Where the groove roof and the pattern
cross, on the top half only, there is not enough wall left between them.

Nothing has been printed, so what a slicer does with a 0.5 mm gap is genuinely unknown:
it may bridge it and leave a mark, or leave a slot you can see light through. Note that
the generator's own header says the pattern is never carved through the wall. On the top
half, in this band, that is not true. If you want a case with no chance of a gap at the
seam, wait for the next revision.

### Nobody has printed this yet

Every number on this page was measured from the two STL files, not from a print. Both are
watertight single bodies of 263,724 and 253,692 triangles and 39.296 and 36.141 cm³, and
the files here are byte-identical to the ones those measurements were taken from. No
version 7 has ever come off a bed, so nothing here is a claim about how it prints, how it
fits the board, or how it survives handling. If you print one before we do, we would like
to hear what happened.

## The snap fit — read before printing a batch

The halves close with a **tongue-and-groove joint plus a retention bead**, rather than a
thin lid on a deep tray. They are close in height but not equal, and the split is not the
Z mid-plane: the bottom measures **13.996 mm** tall and the top **11.999 mm**, because the
bottom's tongue stands 2 mm above its seam shoulder. An earlier version of this page said
both were about 11 mm.

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
