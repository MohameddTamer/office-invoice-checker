# Critique — Office Invoice Checker

Method note: this project shipped without its own critique file in the
first rounds; its build and deepening evidence lives in the
portfolio-level documents (WAVE2-CRITIQUE.md and DEEPENING-CRITIQUE.md
in ~/workspace/github-profile/). This file was opened for the redesign
round and holds the redesign evidence; the numbers it protects were
verified by hand there and are re-verified below.

## Redesign — English-only editorial auditor's ledger (2026-10-24)

The owner rejected the previous skin as a design he had seen before
and ordered two things: everything user facing in English, and a
front end from the current design world. The mapping in
DESIGN-RESEARCH.md sends this project to the Editorial Auditor's
Ledger. DESIGN.md in this folder is the design record.

What changed:
- frontend/index.html rebuilt: lang en, LTR, ledger cream paper, ink
  rules, Fraunces + IBM Plex Mono from Google Fonts with serif and
  mono fallbacks. A nameplate with a drawn ledger mark and a dateline
  strip replaces the old header. Offices render as broadsheet
  articles: headline, an italic standfirst generated from the numbers
  that states the finding in one sentence, then a ruled table with
  vertical column rules and a double rule above each office total.
- The signature interaction: hovering or tapping an overbilled line
  draws an animated SVG red-pencil ellipse around the overpaid figure
  (stroke-dashoffset, about 300ms, respects prefers-reduced-motion)
  while the auditor's margin note for that line fades in. In print,
  circles and notes render fully drawn.
- The total overbilled is set as a headline figure in red Plex Mono,
  not a stat card. The report chart's worked-days bars are hatched
  SVG pattern fills instead of a second flat color.
- Controls styled end to end: ink-underlined date, number and select
  fields (the select carries a drawn chevron), the CSV file input
  hidden behind a labelled button with the chosen file name in mono.
  No raw native control is visible.
- The login screen and every label, empty state and error string are
  English. The only Arabic left anywhere in the project was five
  comments in backend/seed.py explaining the seeded traps; those are
  English now, and the trap facts themselves are untouched.

Evidence:
- Tests before the redesign: tests/test_api.py passed (assert-based;
  it asserts the seeded totals directly), tests/test_deepening.py 52
  checks passed. After: both pass unchanged — test_api "Invoice
  checker api tests passed", test_deepening 52 of 52.
- Numbers unchanged, and they are asserted inside test_api.py itself,
  so the passing suite is the proof: the seeded period totals
  EGP 2,700 overbilled at the 450 day rate and EGP 3,000 at 500.
  Per courier, unchanged: Karim S. billed 12, worked 11, +450,
  overbilled, 2 present-on-leave days; Mahmoud R. +2 days, +900;
  Hassan M. +3 days, +1,350 with 3 present-on-leave days; Youssef A.
  billed a day short, -450, flagged underbilled; Omar E. exact.
  Per office: North Gate Office 450, Delta Lines 900, Sahel Partners
  1,350 — same as the hand-checked figures recorded at build time.
- A scan of the project tree finds zero Arabic characters in code,
  page, tests and docs after the conversion.

Honest notes on the direction:
- The margin notes are generated from the line's own numbers (extra
  days, present-on-leave count), not free text an auditor typed. They
  read like an auditor because the facts are specific; a real
  deployment would want a notes field per line, which the schema does
  not have yet.
- The pencil ellipse is one wobble path reused at every variance. At
  a glance it reads hand-drawn; stared at across ten rows, the same
  wobble repeats. Two or three path variants would fix that and were
  left out for scope, recorded here rather than hidden.
- The standfirst for a clean office says there is nothing for the red
  pencil. True today; a period where every office is clean renders
  three quiet articles, and the headline figure reads EGP 0 — still
  set in red, because the figure's color is fixed by the stylesheet
  rather than by its value. That is the one place the color rule
  bends, and it is visible here rather than explained away.
- The page was verified in markup, CSS and script syntax
  (node --check), and by the API tests reading it from the booted
  server — not rendered in a device browser in this round, same
  limit as before.
