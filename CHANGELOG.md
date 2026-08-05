# Changelog

## 1.0.0

The first version this is willing to be run against a real plant.

Nothing in the model changed for this release. What changed is what the build
refuses to ship: nine gates now run in CI, including the query plan check, the
export check and the release check, and the two generated documents fail the
build when they drift.

Added since 0.2.0:

- the trap fitting history, so a station remembers every trap it has held and a
  warranty can be checked against the one that is in it
- the repair effectiveness report, which asks whether a repair held at the next
  survey rather than at the retest
- the sensitivity sweep, which moves each assumption on its own
- the rule coverage report, which tells a dead rule from a busy one
- `dripleg doctor`, which runs every check and exits non zero when one fails
- `dripleg fleet`, for a book holding more than one plant
- quarantine files, so a bad import can be fixed in the file and re-run

Fixed:

- work order numbers were counted per site and are the primary key, so the
  second plant on a book was handed a number the first already had and the
  upsert quietly moved the existing order onto the other plant's trap
- a register batch was one statement per station; it is now one statement

## 0.2.0

Reports share one rendering path rather than five copies of the same two
methods, and `write_to` is on all of them.

Development dependencies moved: pytest 8.3.5 and ruff 0.9.7. Nothing in the
runtime dependency set changed; click stays pinned at 8.1.8.

Added since 0.1.0:

- the sizing audit, which holds a drip station against the condensate it has to
  clear rather than against the steam it might lose
- the accrual meter, so an open job carries what it has cost since it was found
- the spares list, one line per part with an allowance
- rule exclusions per site, on the record and with a reason
- the crew calibration report, over-calling and under-calling counted apart
- the book audit, for the inconsistencies foreign keys cannot catch
- two more CI gates: the workflow checker and the command reference

## 0.1.0

First cut. Units, the saturated steam table, the asset register, the store with
its numbered migrations, surveys, the diagnosis engine, Napier loss, the cost
and emissions model, repairs and work orders, the programme, ingest, the
reports and the command line.
