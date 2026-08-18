# REXI-008 — authorship and provenance

**What this card depicts.** A family's dog. Every face that ships is *generated
artwork*, not a photograph of her. No real person appears on any face.

**What was deliberately left out.** The arriving package contained a folder of
source photographs, including a screenshot of a private message thread from a
family member. None of it ships. The card needs none of it, and a private
message is not ours to publish. The words on the card are written from the
facts in that message — sleeps a lot, sudden bursts of energy, barks at hello
and goodbye — never quoted from it.

**What is not connected.** The real tag is physical and lives on the dog. This
page does not link to it, write it, or record it. No address, phone number or
contact route appears on the card or the page. The QR opens this page and
nothing else.

**Human choices.** Which faces ship; the front/back pairing; every word of the
copy; the decision to reserve a printed sticker circle rather than imply the
chip is printable; and the decision that the pet-details route stores nothing
server-side.

**Tools.** Image generation for the faces. The back face and the sticker face
were composed with Pillow from repo assets (`src/web/marks/tap-*.png`) and a QR
built by `tools/make_qr.swift`, verified by `tools/qrdecode` against the
finished face rather than the source file.
