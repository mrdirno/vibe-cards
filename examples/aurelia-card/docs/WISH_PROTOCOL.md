# WISH PROTOCOL — CARD 04 AURELIA KRESLING CORONA 01 — Direct Supabase
## Run PB-49-14-07 — Tap/Scan → Tool → Bottom Wish Bar

### Flow
1. Physical Card has NTAG213 25mm sewable + QR v6 41x41 H EC 30% outer 28mm / inner 22mm both encode: https://kikko.craftworks/tool/AURELIA-CORONA-001?tap=1#wish-it-better
2. Tap phone (NFC) or Scan QR → opens interactive tool (index.html / interactive_tool.html)
3. Tool opens auto-scrolls to bottom fixed bar: WISH IT BETTER
4. Bottom bar textarea + submit → direct POST to Supabase wishes table anon insert, no email

### NFC Spec
- Chip: NTAG213 25mm sewable puck, 3x Ø1.5mm sew holes, 22mm coil, 0.2mm ferrite back isolating from copper C110 shim, mount on Tyvek-only zone left of occipital slit
- NDEF: URI record U + payload URL
- URL: https://kikko.craftworks/tool/AURELIA-CORONA-001?tap=1#wish-it-better
- Write with NFC Tools, lock read-only

### QR Spec
- Content: Same URL as NFC, NOT mailto
- Version 6, 41x41 modules, H 30% EC, outer 28mm, inner 22mm, quiet zone 4 modules, colors #10243E on #F2E8CF
- Outer: 28mm white patch border 0.4mm #111, inner 22mm QR image box_size 12 border 4
- Image: PNG data URI data:image/png;base64,... ingestible

### Supabase Schema Direct
```sql
create table wishes (
  id uuid primary key default gen_random_uuid(),
  card_id text not null, -- AURELIA-CORONA-001
  run_id text not null, -- PB-49-14-07
  wish_text text not null check (char_length(wish_text) between 3 and 500),
  source text not null check (source in ('nfc_tap','qr_scan','tool_direct')),
  created_at timestamp with time zone default now(),
  meta jsonb
);
alter table wishes enable row level security;
create policy "allow anon insert direct" on wishes for insert to anon with check (true);
```

### Frontend Direct POST Bottom Bar
See index.html bottom bar implementation.

END CARD 04 PB-49-14-07
