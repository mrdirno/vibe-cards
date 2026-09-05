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

Measured on the shipped file, the top half's outer wall is **open** near the seam: draw
horizontal lines across the part and some of them pass clean through it without touching
any material.

**This page previously said that break was a single band 0.5 mm tall. It is 3.0 mm tall,
and the earlier figure was our sampling rather than the part.** The test steps up the part
in slices; at its default 0.2 mm spacing it lands on 3 bad heights spanning 0.6 mm. Re-run
at 0.05 mm on the same file it finds **13 bad heights spanning 3.0 mm, from 0.05 mm to
3.00 mm above the seam face**. It was stepping over its own failures. The finer number is
the honest one.

Please also ignore the "49 of 192 lines" this page used to quote, and treat any such count
with suspicion, including ours. The number of open lines is a property of how finely you
probe, not of the part: the same test on the same file reports 53 open lines at 0.5 mm line
spacing and 105 at 0.25 mm. Only *where* the break is stays put.

The bottom half is clean: the same test at the same fine 0.05 mm spacing returns zero at
all 279 heights through it.

The topology is consistent with that, though it is weaker evidence than it looks. Both
halves are watertight single bodies, but the top half's surface has genus 41 against the
bottom half's 4. That counts handles in the surface, which is not the same as holes you
can see through: the version 3 ancestor of this case has genus 229 and passes the
line test cleanly, because its tunnels are enclosed channels rather than openings. The
line test is the evidence here; the genus is a hint that pointed at which half to look at.

The cause is arithmetic. The seam groove is cut in behind the outer face, which leaves
the outer seal lip far thinner than the 3.0 mm the wall is elsewhere: measured through
that band, the lip runs between 0.77 and 1.19 mm. The surface pattern is cut 1.5 mm in
from outside. A 1.5 mm cut into a lip that is at most 1.19 mm thick removes it. The
bottom half is unaffected because its seam feature is a tongue that stands proud of the
seam face rather than a groove cut behind it, so nothing thins its wall there.

**This page used to say that what a slicer does with that gap was "genuinely unknown". It
is no longer unknown.** The file was run through OrcaSlicer 2.3.1 on the unmodified
Anycubic Kobra S1 0.4 mm vendor profile, and the machine instructions were read back. The
slicer does not bridge it. Binning the outer wall into 720 sectors around the part, the
share of the ring that receives no plastic at all is:

| height on the part | ring with no plastic |
|---|---|
| 13.90 mm | 19.9 % |
| 14.00 mm | 25.1 % |
| 14.20 mm | 28.3 % |
| 18.50 mm (ordinary wall, for comparison) | 3.1 % |

That 3.1 % floor is the USB opening, which is meant to be there. So at the seam the printer
is told to leave a fifth to a quarter of the outer wall empty, and it will. Expect a slot
you can see light through, not a bridged mark.

Note that the generator's own header says the pattern is never carved through the wall. On
the top half, in this band, that is not true.

A repaired top half has been measured and closes the gap — on the same slicer it reads the
same 3.1 % as ordinary wall — but nothing has been printed and no revision has been
published yet. If you want a case with no chance of a gap at the seam, wait for it.

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
