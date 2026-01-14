from __future__ import annotations

from dripleg.store.audit import BookAudit, BookFinding


def test_a_clean_audit_says_so() -> None:
    audit = BookAudit(site="WRX1", findings=[])
    assert audit.is_clean
    assert audit.kinds() == {}
    assert str(audit) == "WRX1: nothing wrong"


def test_findings_are_counted_by_kind() -> None:
    audit = BookAudit(
        site="WRX1",
        findings=[
            BookFinding("orphan", "a"),
            BookFinding("orphan", "b"),
            BookFinding("empty survey", "c"),
        ],
    )
    assert audit.kinds() == {"empty survey": 1, "orphan": 2}
    assert len(audit.of_kind("orphan")) == 2
    assert audit.of_kind("nothing") == []
    assert not audit.is_clean
    assert str(audit) == "WRX1: 3 findings"


def test_a_finding_prints_its_kind_and_detail() -> None:
    assert str(BookFinding("orphan", "WO-1 is against nothing")) == (
        "orphan: WO-1 is against nothing"
    )
