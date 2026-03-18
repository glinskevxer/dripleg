"""Numbered migrations, applied in order, with a checksum on what was applied.

There is no migration framework here on purpose. The whole schema is a few
hundred lines of SQL and the interesting behaviour is one rule: a migration
that has already run must not have changed since it ran. Editing an applied
migration is the way a schema quietly diverges between one plant's book and the
next, and the divergence is only found months later by a report that returns
nothing.

So each migration carries a sha256 of its own SQL, the book records the
checksum it applied, and a mismatch stops everything before the first read.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from dripleg.errors import ConflictError
from dripleg.store.db import Database

__all__ = ["MIGRATIONS", "Migration", "applied_migrations", "migrate", "schema_version"]

_LEDGER = """
CREATE TABLE IF NOT EXISTS schema_migration (
    number      INTEGER PRIMARY KEY,
    name        TEXT NOT NULL,
    checksum    TEXT NOT NULL,
    applied_at  TEXT NOT NULL DEFAULT (datetime('now'))
)
"""


@dataclass(frozen=True)
class Migration:
    number: int
    name: str
    sql: str

    @property
    def checksum(self) -> str:
        return hashlib.sha256(self.sql.strip().encode("utf-8")).hexdigest()

    def __str__(self) -> str:
        return f"{self.number:03d} {self.name}"


MIGRATION_001 = Migration(
    1,
    "sites areas and headers",
    """
    CREATE TABLE site (
        code                    TEXT PRIMARY KEY,
        name                    TEXT NOT NULL,
        operator                TEXT NOT NULL,
        programme_start_month   INTEGER NOT NULL DEFAULT 1,
        fuel_price_basis        TEXT NOT NULL,
        CHECK (programme_start_month BETWEEN 1 AND 12)
    );

    CREATE TABLE area (
        site_code   TEXT NOT NULL REFERENCES site(code) ON DELETE CASCADE,
        code        TEXT NOT NULL,
        name        TEXT NOT NULL,
        cost_centre TEXT NOT NULL,
        parent_code TEXT,
        PRIMARY KEY (site_code, code),
        CHECK (parent_code IS NULL OR parent_code <> code)
    );

    CREATE TABLE header (
        site_code           TEXT NOT NULL,
        area_code           TEXT NOT NULL,
        system_code         TEXT NOT NULL,
        name                TEXT NOT NULL,
        operating_psia      REAL NOT NULL,
        design_psia         REAL NOT NULL,
        discharge_psia      REAL NOT NULL,
        destination         TEXT NOT NULL,
        PRIMARY KEY (site_code, area_code, system_code),
        FOREIGN KEY (site_code, area_code) REFERENCES area(site_code, code) ON DELETE CASCADE,
        CHECK (operating_psia > 0),
        CHECK (design_psia >= operating_psia),
        CHECK (discharge_psia <= operating_psia)
    );

    CREATE INDEX header_by_area ON header (site_code, area_code);
    """,
)

MIGRATION_002 = Migration(
    2,
    "trap models profiles and stations",
    """
    CREATE TABLE trap_model (
        manufacturer            TEXT NOT NULL,
        code                    TEXT NOT NULL,
        principle               TEXT NOT NULL,
        orifice_diameter_in     REAL NOT NULL,
        max_operating_psia      REAL NOT NULL,
        max_back_pressure_pct   REAL NOT NULL,
        connection_size_in      REAL NOT NULL,
        connection_type         TEXT NOT NULL,
        list_price_cents        INTEGER NOT NULL,
        discontinued            INTEGER NOT NULL DEFAULT 0,
        replaced_by             TEXT,
        PRIMARY KEY (manufacturer, code),
        CHECK (orifice_diameter_in > 0),
        CHECK (max_back_pressure_pct > 0 AND max_back_pressure_pct <= 100),
        CHECK (list_price_cents >= 0),
        CHECK (discontinued IN (0, 1)),
        CHECK (replaced_by IS NULL OR discontinued = 1),
        CHECK (replaced_by IS NULL OR replaced_by <> code)
    );

    CREATE TABLE operating_profile (
        site_code       TEXT NOT NULL REFERENCES site(code) ON DELETE CASCADE,
        code            TEXT NOT NULL,
        name            TEXT NOT NULL,
        pattern         TEXT NOT NULL,
        load_factor     REAL NOT NULL DEFAULT 1.0,
        campaign_months TEXT NOT NULL DEFAULT '',
        PRIMARY KEY (site_code, code),
        CHECK (load_factor > 0 AND load_factor <= 1),
        CHECK ((pattern = 'campaign') = (campaign_months <> ''))
    );

    CREATE TABLE trap_station (
        site_code               TEXT NOT NULL,
        tag                     TEXT NOT NULL,
        area_code               TEXT NOT NULL,
        system_code             TEXT NOT NULL,
        sequence                INTEGER NOT NULL,
        model_manufacturer      TEXT NOT NULL,
        model_code              TEXT NOT NULL,
        service                 TEXT NOT NULL,
        accessibility           TEXT NOT NULL,
        criticality             TEXT NOT NULL,
        profile_code            TEXT NOT NULL,
        installed_on            TEXT NOT NULL,
        removed_on              TEXT,
        destination             TEXT,
        strainer_fitted         INTEGER NOT NULL DEFAULT 1,
        isolation_valves        INTEGER NOT NULL DEFAULT 2,
        test_valve_fitted       INTEGER NOT NULL DEFAULT 0,
        insulated               INTEGER NOT NULL DEFAULT 1,
        interval_months_override INTEGER,
        note                    TEXT NOT NULL DEFAULT '',
        PRIMARY KEY (site_code, tag),
        FOREIGN KEY (site_code, area_code, system_code)
            REFERENCES header(site_code, area_code, system_code) ON DELETE CASCADE,
        FOREIGN KEY (model_manufacturer, model_code)
            REFERENCES trap_model(manufacturer, code),
        FOREIGN KEY (site_code, profile_code)
            REFERENCES operating_profile(site_code, code),
        CHECK (sequence >= 1),
        CHECK (isolation_valves BETWEEN 0 AND 2),
        CHECK (removed_on IS NULL OR removed_on >= installed_on),
        CHECK (interval_months_override IS NULL
               OR interval_months_override BETWEEN 1 AND 60)
    );

    CREATE INDEX station_by_header ON trap_station (site_code, area_code, system_code);
    CREATE INDEX station_by_service ON trap_station (site_code, service);
    CREATE INDEX station_by_model ON trap_station (model_manufacturer, model_code);
    """,
)

MIGRATION_003 = Migration(
    3,
    "surveys routes and observations",
    """
    CREATE TABLE survey (
        site_code   TEXT NOT NULL REFERENCES site(code) ON DELETE CASCADE,
        reference   TEXT NOT NULL,
        name        TEXT NOT NULL,
        contractor  TEXT NOT NULL,
        started_on  TEXT NOT NULL,
        finished_on TEXT,
        PRIMARY KEY (site_code, reference),
        CHECK (finished_on IS NULL OR finished_on >= started_on)
    );

    CREATE TABLE route (
        site_code        TEXT NOT NULL REFERENCES site(code) ON DELETE CASCADE,
        code             TEXT NOT NULL,
        name             TEXT NOT NULL,
        minutes_per_stop REAL NOT NULL DEFAULT 6.0,
        walk_minutes     REAL NOT NULL DEFAULT 30.0,
        PRIMARY KEY (site_code, code),
        CHECK (minutes_per_stop > 0),
        CHECK (walk_minutes >= 0)
    );

    CREATE TABLE route_stop (
        site_code  TEXT NOT NULL,
        route_code TEXT NOT NULL,
        position   INTEGER NOT NULL,
        tag        TEXT NOT NULL,
        PRIMARY KEY (site_code, route_code, position),
        UNIQUE (site_code, route_code, tag),
        FOREIGN KEY (site_code, route_code) REFERENCES route(site_code, code) ON DELETE CASCADE,
        CHECK (position >= 0)
    );

    CREATE TABLE observation (
        site_code           TEXT NOT NULL,
        survey_reference    TEXT NOT NULL,
        tag                 TEXT NOT NULL,
        observed_on         TEXT NOT NULL,
        technician          TEXT NOT NULL,
        reported_condition  TEXT NOT NULL,
        ultrasonic_db       REAL,
        ultrasonic_seconds  REAL,
        ultrasonic_cycles   INTEGER,
        ultrasonic_khz      REAL,
        upstream_f          REAL,
        downstream_f        REAL,
        ambient_f           REAL,
        temperature_method  TEXT,
        sight_glass         TEXT,
        measured_psia       REAL,
        note                TEXT NOT NULL DEFAULT '',
        photo_reference     TEXT,
        PRIMARY KEY (site_code, survey_reference, tag),
        FOREIGN KEY (site_code, survey_reference)
            REFERENCES survey(site_code, reference) ON DELETE CASCADE,
        CHECK (ultrasonic_db IS NULL OR (ultrasonic_db >= 0 AND ultrasonic_db <= 120)),
        CHECK (ultrasonic_cycles IS NULL OR ultrasonic_cycles >= 0),
        CHECK ((ultrasonic_db IS NULL) = (ultrasonic_seconds IS NULL)),
        CHECK ((upstream_f IS NULL) = (downstream_f IS NULL)),
        CHECK ((upstream_f IS NULL) = (temperature_method IS NULL))
    );

    CREATE INDEX observation_by_tag ON observation (site_code, tag, observed_on);
    CREATE INDEX observation_by_condition ON observation (site_code, reported_condition);
    """,
)

MIGRATION_004 = Migration(
    4,
    "findings and work orders",
    """
    CREATE TABLE finding (
        site_code           TEXT NOT NULL,
        survey_reference    TEXT NOT NULL,
        tag                 TEXT NOT NULL,
        diagnosed           TEXT NOT NULL,
        reported            TEXT NOT NULL,
        confidence          REAL NOT NULL,
        flags               TEXT NOT NULL DEFAULT '',
        rules_fired         TEXT NOT NULL DEFAULT '',
        pounds_per_hour     REAL NOT NULL DEFAULT 0,
        pounds_per_year     REAL NOT NULL DEFAULT 0,
        fuel_mmbtu_per_year REAL NOT NULL DEFAULT 0,
        tonnes_co2e         REAL NOT NULL DEFAULT 0,
        annual_cost_cents   INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY (site_code, survey_reference, tag),
        FOREIGN KEY (site_code, survey_reference, tag)
            REFERENCES observation(site_code, survey_reference, tag) ON DELETE CASCADE,
        CHECK (confidence >= 0 AND confidence <= 1),
        CHECK (pounds_per_hour >= 0),
        CHECK (pounds_per_year >= 0),
        CHECK (annual_cost_cents >= 0)
    );

    CREATE INDEX finding_by_cost ON finding (site_code, annual_cost_cents DESC);
    CREATE INDEX finding_by_condition ON finding (site_code, diagnosed);

    CREATE TABLE work_order (
        number                TEXT PRIMARY KEY,
        site_code             TEXT NOT NULL REFERENCES site(code) ON DELETE CASCADE,
        tag                   TEXT NOT NULL,
        action                TEXT NOT NULL,
        state                 TEXT NOT NULL,
        raised_on             TEXT NOT NULL,
        due_on                TEXT NOT NULL,
        assigned_to           TEXT,
        started_on            TEXT,
        completed_on          TEXT,
        verified_on           TEXT,
        estimated_cost_cents  INTEGER NOT NULL,
        actual_cost_cents     INTEGER,
        CHECK (due_on >= raised_on),
        CHECK (estimated_cost_cents >= 0),
        CHECK (actual_cost_cents IS NULL OR actual_cost_cents >= 0),
        CHECK (completed_on IS NULL OR completed_on >= raised_on),
        CHECK (verified_on IS NULL OR completed_on IS NOT NULL),
        CHECK (verified_on IS NULL OR verified_on >= completed_on),
        CHECK (state <> 'verified' OR verified_on IS NOT NULL)
    );

    CREATE INDEX work_order_by_tag ON work_order (site_code, tag);
    CREATE INDEX work_order_by_state ON work_order (site_code, state, due_on);

    CREATE TABLE work_order_event (
        number   TEXT NOT NULL REFERENCES work_order(number) ON DELETE CASCADE,
        position INTEGER NOT NULL,
        note     TEXT NOT NULL,
        PRIMARY KEY (number, position),
        CHECK (position >= 0)
    );
    """,
)

MIGRATION_005 = Migration(
    5,
    "the boiler house numbers a site is costed on",
    """
    CREATE TABLE cost_basis (
        site_code               TEXT PRIMARY KEY REFERENCES site(code) ON DELETE CASCADE,
        fuel_per_mmbtu          TEXT NOT NULL,
        water_per_kgal          TEXT NOT NULL,
        effluent_per_kgal       TEXT NOT NULL,
        chemical_per_kgal       TEXT NOT NULL,
        labour_per_hour         TEXT NOT NULL,
        permit_cost_cents       INTEGER NOT NULL DEFAULT 0,
        feedwater_f             REAL NOT NULL,
        boiler_efficiency       REAL NOT NULL,
        condensate_returned     REAL NOT NULL,
        receiver_vent_fraction  REAL NOT NULL,
        fuel                    TEXT NOT NULL,
        effective_from          TEXT NOT NULL,
        CHECK (boiler_efficiency > 0 AND boiler_efficiency <= 1),
        CHECK (condensate_returned >= 0 AND condensate_returned <= 1),
        CHECK (receiver_vent_fraction >= 0 AND receiver_vent_fraction <= 1),
        CHECK (permit_cost_cents >= 0),
        CHECK (feedwater_f > 32)
    );
    """,
)

MIGRATION_006 = Migration(
    6,
    "the geometry a sizing check needs",
    """
    ALTER TABLE trap_station ADD COLUMN pipe_nominal TEXT;
    ALTER TABLE trap_station ADD COLUMN run_length_ft REAL;
    ALTER TABLE trap_station ADD COLUMN warmup_minutes REAL;
    """,
)

MIGRATION_007 = Migration(
    7,
    "rules a site has switched off",
    """
    CREATE TABLE rule_exclusion (
        site_code    TEXT NOT NULL REFERENCES site(code) ON DELETE CASCADE,
        rule_code    TEXT NOT NULL,
        reason       TEXT NOT NULL,
        excluded_on  TEXT NOT NULL,
        PRIMARY KEY (site_code, rule_code),
        CHECK (length(trim(reason)) > 0)
    );
    """,
)

MIGRATION_008 = Migration(
    8,
    "findings the plant has decided to live with",
    """
    CREATE TABLE accepted_risk (
        site_code    TEXT NOT NULL,
        tag          TEXT NOT NULL,
        reason       TEXT NOT NULL,
        accepted_by  TEXT NOT NULL,
        accepted_on  TEXT NOT NULL,
        review_on    TEXT NOT NULL,
        PRIMARY KEY (site_code, tag),
        FOREIGN KEY (site_code, tag)
            REFERENCES trap_station(site_code, tag) ON DELETE CASCADE,
        CHECK (review_on > accepted_on),
        CHECK (length(trim(reason)) > 0),
        CHECK (length(trim(accepted_by)) > 0)
    );

    CREATE INDEX accepted_risk_by_review ON accepted_risk (site_code, review_on);
    """,
)

MIGRATIONS: tuple[Migration, ...] = (
    MIGRATION_001,
    MIGRATION_002,
    MIGRATION_003,
    MIGRATION_004,
    MIGRATION_005,
    MIGRATION_006,
    MIGRATION_007,
    MIGRATION_008,
)


def schema_version(book: Database) -> int:
    """The highest migration number this book has applied, or zero."""

    if not book.has_table("schema_migration"):
        return 0
    return int(book.scalar("SELECT COALESCE(MAX(number), 0) FROM schema_migration") or 0)


def applied_migrations(book: Database) -> dict[int, str]:
    """Migration number to the checksum the book recorded for it."""

    if not book.has_table("schema_migration"):
        return {}
    rows = book.query("SELECT number, checksum FROM schema_migration ORDER BY number")
    return {int(row["number"]): str(row["checksum"]) for row in rows}


def _check_history(book: Database) -> None:
    known = {m.number: m for m in MIGRATIONS}
    for number, checksum in applied_migrations(book).items():
        migration = known.get(number)
        if migration is None:
            raise ConflictError(
                f"this book has migration {number:03d} applied and this build does not have it"
            )
        if migration.checksum != checksum:
            raise ConflictError(f"migration {migration} has changed since this book applied it")


def migrate(book: Database, *, up_to: int | None = None) -> list[Migration]:
    """Apply whatever is outstanding and return what was applied.

    Each migration lands in its own transaction together with its ledger row,
    so a failure halfway through a run leaves the book at the last migration
    that finished rather than somewhere between two.
    """

    book.execute(_LEDGER)
    _check_history(book)
    ceiling = up_to if up_to is not None else MIGRATIONS[-1].number
    done = set(applied_migrations(book))
    run: list[Migration] = []
    for migration in sorted(MIGRATIONS, key=lambda m: m.number):
        if migration.number in done or migration.number > ceiling:
            continue
        with book.transaction():
            book.execute_batch(migration.sql)
            book.execute(
                "INSERT INTO schema_migration (number, name, checksum) VALUES (?, ?, ?)",
                (migration.number, migration.name, migration.checksum),
            )
        run.append(migration)
    return run
