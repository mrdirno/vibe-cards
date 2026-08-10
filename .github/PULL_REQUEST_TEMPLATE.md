## What this changes

<!-- One paragraph. What was wrong, and what is different now. -->

## The eval

<!-- Per WISH_IT_BETTER.md §2. Worked examples in docs/EVALS.md. -->

**Claim:**
**How it could have failed:**
**What was observed:**
**Limits (what this does NOT cover):**

## Checklist

- [ ] `./tools/verify_contribution.sh` passes
- [ ] **E1** The eval could have failed — the failing condition is written above
- [ ] **E2** Verified at the artifact a user touches (built app / rendered page), not only the source
- [ ] **E3** Denominator reported; exclusions named
- [ ] **E4** Any sampling / truncation / top-N is stated
- [ ] **E5** Security- or data-relevant? An independent pass tried to refute it
- [ ] **L** The lesson is written where the next person will already be looking

<!-- Touching server.py, the print path, or file handling? SECURITY.md §6-8 applies. -->
