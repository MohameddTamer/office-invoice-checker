# Changelog

## 0.4
English-only rebuild of everything user facing, and a new skin with a point of view. The page is now an editorial auditor's ledger: a newspaper nameplate, offices written up as articles with a standfirst that says the finding in one sentence, ruled broadsheet tables with double rules under the totals, and the auditor's red pencil drawing itself around any figure the station overpaid, with the note appearing in the margin. Fraunces for the editorial voice, IBM Plex Mono for every pound. The arithmetic did not move: the seeded period still totals EGP 2,700 overbilled at the 450 day rate and EGP 3,000 at 500. DESIGN.md records the direction, CRITIQUE.md the evidence.

## 0.3
The deepening round. CSV import for invoice lines with a named skipped rows report, a report endpoint behind a printable view with an inline SVG chart, an admin backup endpoint writing a timestamped database copy, a live config readout, a rotating log file, and environment variable configuration. Fifty two new checks in tests/test_deepening.py.

## 0.2
Present but on leave is now its own column. It used to hide inside the worked days count and it is exactly the kind of day an invoice should not quietly include. Underbilled lines get flagged too, not just the overbilled ones.

## 0.1
First working version. Invoice lines checked against attendance minus leave over a chosen range, day rate configurable.
