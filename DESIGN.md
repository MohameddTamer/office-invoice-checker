# Design — Office Invoice Checker

## Concept

An auditor does not decorate. He annotates. This page is set like the
front page of a small financial newspaper that exists for one story:
the gap between what the offices billed and what their people actually
worked. Each office is written up as an article — a headline, a
one-sentence standfirst that delivers the finding, and the ruled table
beneath it. The only flourish in the whole product is the auditor's
red pencil, and it appears only where money is wrong.

## Palette

| Role | Hex | Where it lives |
|---|---|---|
| Ledger cream | `#F7F2E7` | The paper itself (page tone; the sheet runs a whisper lighter, `#FBF7EC`) |
| Ink | `#1E1B16` | Type, rules, billed bars — everything structural |
| Column rule grey | `#CFC6B4` | The thin rules between ledger columns |
| Auditor red | `#B3402F` | Variances and margin notes only. Never a surface, never a button |
| Dim brown-grey | `#6E6455` | Datelines, secondary text |

One accent, used like a signature: if a page view shows red anywhere
except a variance figure, its pencil circle, or its margin note, the
design has failed.

## Type pairing

- **Fraunces** (variable, up to 900) for the editorial voice:
  nameplate, office headlines, standfirsts in italic, findings. Its
  old-style figures are banned from money by the pairing rule below.
  Fallbacks: Georgia, Times New Roman, serif.
- **IBM Plex Mono** (400–600) for every number that means money or
  days: tables, the headline figure, report totals, period stamps.
  `font-variant-numeric: tabular-nums` everywhere, so columns of
  pounds line up like they were typed on the same machine.
  Fallbacks: ui-monospace, SF Mono, Consolas.

## Signature layout move

The broadsheet office article. A nameplate with a double rule under
the dateline opens the sheet; below it, each office stands on its own
as an article with a standfirst that says the finding in prose before
a single number appears. Tables are ruled like a ledger — vertical
column rules, a heavy top rule on the header, and a 3px double rule
above every total. Sections are separated by double rules, not boxes;
there are no cards anywhere on the page.

## Signature interaction

Hover — or tap, on touch — a line that overbilled, and the auditor's
red pencil draws itself around the offending figure: an SVG ellipse
with a hand-set wobble, stroke animating in over about 300ms, while
the auditor's note fades into the margin column on the same row
("3 of the extra days were present-on-leave days. Start here.").
Nothing else on the page moves. In the printed report the circles and
notes are rendered drawn-in, because paper gets the finished audit,
not the animation.

## The brand mark

An open ledger, drawn in ink strokes: a rectangle, its centre spine,
three ruled lines on the left page, and one red ellipse on the right —
the whole product in one small drawing, mark and method together.

## Deliberately avoided

The shared recipe this replaces, and the anti-list behind it: the KPI
stat-card row (the total overbilled is a newspaper headline figure,
not a card), rounded corners (zero radius — paper has edges), pill
badges (findings are small-caps words: OVERBILLED, UNDERBILLED,
MATCHES), soft shadows, gradients, emoji as icons, traffic-light
palettes, and centred-everything hero layouts (the nameplate is
left-aligned editorial, the sheet is a column, not a billboard).
Native controls are styled as ink-underlined form entries in mono —
no raw browser file picker (it hides behind a labelled button with
the file name set beside it) and no default date fields. Also
avoided, on purpose: red as decoration, and green anywhere — an audit
that agrees with the record is written in ink, not celebrated.
