# Changelog

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
