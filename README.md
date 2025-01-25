# dripleg

Steam trap survey register and steam loss accounting.

A drip leg is the pocket welded into the bottom of a steam main so condensate
falls out of the flow before it reaches the trap underneath. The trap is
supposed to pass that condensate and hold the steam back. When it stops doing
that, it does not stop working in any way anybody notices: it just blows live
steam into the return line, or out of a vent, every hour of every day until
somebody walks up to it with a meter.

This is the register those walks land in, and the arithmetic that turns a
reading into a number the plant manager can act on.

## What is in here

- a saturated steam table, read between its rows and guarded at both ends
- the plant asset register: sites, areas, headers, traps and what they drain
- surveys, routes, visits and the readings a technician actually writes down
- a diagnosis engine that knows an inverted bucket does not sound like a disc
- Napier orifice loss, with severity, back pressure and the hours the leg runs
- fuel, makeup water, chemical and emissions costing off that loss
- repair recommendations ranked by what they pay back
- the survey programme: intervals, due dates, coverage, overdue

## Running it

    python -m pip install -e ".[dev]"
    python -m pytest -q

## Units

Pressure is absolute inside and gauge on the way out. Temperature readings and
temperature differences are different types on purpose. Money is a whole number
of cents and prices are exact decimal. Nothing crosses a layer as a bare float.
