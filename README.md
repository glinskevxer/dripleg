# dripleg

Steam trap survey register and steam loss accounting.

A drip leg is the pocket welded into the bottom of a steam main so condensate
falls out of the flow before it reaches the trap underneath. The trap is
supposed to pass that condensate and hold the steam back. When it stops doing
that it does not stop working in any way anybody notices: it blows live steam
into the return line, or out of a vent, every hour of every day until somebody
walks up to it with a meter.

This is the register those walks land in, the engine that decides what a set of
readings means, and the arithmetic that turns a reading into a number a plant
manager can act on.

## What it does

    dripleg init
    dripleg site add WRX1 "Wrexham paper mill" --operator "Bryn Paper"
    dripleg area add B12 "Number 2 machine" --cost-centre PM2
    dripleg header add B12 MP "Machine room main" --psig 125 --discharge-psig 15
    dripleg model add Halden TD52 --principle thermodynamic_disc \
        --orifice 0.093 --pmo 600 --price 184.00
    dripleg profile add CONT Continuous
    dripleg trap import register.csv
    dripleg survey open S2025-1 Spring --contractor "Vane Energy" --started 2025-04-07
    dripleg survey import S2025-1 export.csv --quarantine bad.csv
    dripleg survey report S2025-1
    dripleg loss report S2025-1 --save
    dripleg work list S2025-1 --budget 5000
    dripleg work raise S2025-1 --budget 5000
    dripleg programme scorecard S2025-1

`--json` on any command gives the same answer as a json object instead of a
table, and `dripleg doctor` runs every check on the book and exits non zero if
anything is wrong.

## The parts that are worth reading

**The steam table** is a table, not a correlation, because a survey report gets
argued over by people holding a printed one. It is read between its rows in log
pressure and it raises rather than extrapolating off either end.

**The diagnosis engine** does not produce a verdict. It produces evidence, one
piece per rule that fired, and the verdict falls out of the evidence afterwards
with the reasons printed under it. A rule knows nothing about the other rules.

**The loss calculation** is Napier with a discharge coefficient, a severity
factor off the condition code, a back pressure curve, and the hours the leg is
actually live. All six assumptions are printed with the answer and
`dripleg loss sensitivity` moves each one on its own.

**The cost model** splits on where the trap discharges. A trap blowing into a
closed return feels like it should cost much less than a vented one. It does
not: the latent heat is given up in the return line where nothing uses it, and
the credit is the sensible heat of hot water. That is worked out rather than
assumed either way.

**The programme** counts traps nobody has ever surveyed separately from traps
that are late, because the first is a register problem and no amount of survey
crew fixes it.

## Running it

    python -m pip install -e ".[dev]"
    python -m pytest -q
    python -m dripleg.tools.smoke

The build holds itself to nine gates besides the tests: ruff, mypy strict, a
coverage floor, the migration checker, the workflow checker, the export
checker, the query plan checker, the release checker, and two generated
documents that fail the build when they drift. `docs/index.md` says what each
one refuses.

## Units

Pressure is absolute inside and gauge on the way out. A temperature reading and
a temperature difference are different types on purpose. Money is a whole
number of cents and prices are exact decimal. Nothing crosses a layer as a bare
float.
