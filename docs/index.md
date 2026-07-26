# dripleg

Steam trap survey register and steam loss accounting.

## The documents

- [Commands](commands.md), generated from the command line itself
- [Schema](schema.md), generated from the migrations

Both are written by a program and checked in for readers. CI regenerates them
and fails the build if what is checked in has drifted, so neither can be stale.

## How the pieces sit

    units, steam           the physical types and the saturation table
      model                sites, areas, headers, trap models, stations
        store              sqlite, numbered migrations, one repository per area
        survey             routes, visits, readings, coverage
          diagnosis        rules over readings, evidence, one verdict
            loss           Napier, energy, cost, emissions, accrual
              repair       recommendations, priority, work orders, spares
              programme    schedule, reliability, trend, calibration
                report     text and json
                  cli      one click group per area

Nothing imports downward. The one shared thing that sits above the whole stack
is `thresholds.py`, which holds the numbers the survey standard works to.

## The gates

`ruff check`, `ruff format --check`, `mypy --strict`, `pytest`, and six
tools that hold the build to itself:

| gate | what it refuses |
| --- | --- |
| `coverage_gate` | a coverage floor, overall and per file |
| `check_migrations` | a migration set that will not apply to an empty book |
| `check_workflow` | a gate that CI does not run |
| `check_exports` | an `__all__` that names something that is not there |
| `query_plan` | a hot query that would scan a table |
| `release_check` | a loose pin, a version mismatch, an unwritten changelog |
| `schema_dump --check` | schema documentation that has drifted |
| `build_docs --check` | a command with no help, or a stale reference |
| `smoke` | a wheel that installs and does not work |

## Where the domain reasoning lives

Most of it is in the module docstrings, next to the code it explains. The three
worth reading first:

- `steam/table.py`, on why the steam table is a table and not a correlation
- `loss/energy.py`, on why a trap blowing into a closed return costs nearly
  what a vented one costs
- `diagnosis/heat_rules.py`, on the one thing temperature cannot tell you
