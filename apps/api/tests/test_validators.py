"""Tests for the validation module (unit tests for ValidationReport)."""

from app.jobs.validators import ValidationReport


class TestValidationReport:
    def test_empty_report_is_ok(self):
        report = ValidationReport()
        assert report.ok
        assert report.total_checks == 0

    def test_pass_increments(self):
        report = ValidationReport()
        report.add_pass("check 1")
        report.add_pass("check 2")
        assert report.total_checks == 2
        assert report.passed == 2
        assert report.ok

    def test_warning_does_not_fail(self):
        report = ValidationReport()
        report.add_pass("check 1")
        report.add_warning("low coverage")
        assert report.ok
        assert len(report.warnings) == 1

    def test_error_makes_not_ok(self):
        report = ValidationReport()
        report.add_pass("check 1")
        report.add_error("duplicate found")
        assert not report.ok
        assert len(report.errors) == 1

    def test_summary(self):
        report = ValidationReport()
        report.add_pass("a")
        report.add_warning("b")
        report.add_error("c")
        s = report.summary()
        assert s["total_checks"] == 3
        assert s["passed"] == 1
        assert s["warnings"] == 1
        assert s["errors"] == 1
        assert not s["ok"]
