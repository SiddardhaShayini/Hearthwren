"""Tests for ErrorRecoveryEngine."""

from pathlib import Path
from hearthwren.config import HearthwrenConfig
from hearthwren.recovery import ErrorRecoveryEngine, FailureAnalysis


def test_failure_analysis_from_traceback(tmp_path: Path):
    engine = ErrorRecoveryEngine(workspace_root=tmp_path)
    culprit = tmp_path / "calc.py"
    culprit.write_text("def divide(a, b):\n    return a / b\n", encoding="utf-8")

    mock_test_result = {
        "stdout": f'Traceback (most recent call last):\n  File "{culprit}", line 2, in divide\nZeroDivisionError: division by zero\n',
        "stderr": "",
        "failures_detected": ["ZeroDivisionError: division by zero"],
    }

    analysis = engine.analyze_failure(mock_test_result)
    assert analysis.error_type == "ZeroDivisionError"
    assert "division by zero" in analysis.message
    assert analysis.culprit_file == "calc.py"
    assert analysis.culprit_line == 2
    assert analysis.code_snippet is not None
    assert "return a / b" in analysis.code_snippet


def test_bounded_repair_attempts(tmp_path: Path):
    cfg = HearthwrenConfig(max_repair_attempts=3)
    engine = ErrorRecoveryEngine(workspace_root=tmp_path, config=cfg)

    dummy_analysis = FailureAnalysis(
        error_type="AssertionError",
        message="Expected 42, got 0",
        culprit_file="test_sample.py",
        culprit_line=10,
        code_snippet="assert 0 == 42",
        raw_evidence=["assert 0 == 42"],
    )

    # Attempt 1: can auto retry
    prop1 = engine.propose_repair(dummy_analysis, attempt=1)
    assert prop1.can_auto_retry is True
    assert prop1.attempt == 1

    # Attempt 2: can auto retry
    prop2 = engine.propose_repair(dummy_analysis, attempt=2)
    assert prop2.can_auto_retry is True

    # Attempt 3: last attempt
    prop3 = engine.propose_repair(dummy_analysis, attempt=3)
    assert prop3.can_auto_retry is False

    # Attempt 4: over budget, halts repair loop
    prop4 = engine.propose_repair(dummy_analysis, attempt=4)
    assert prop4.can_auto_retry is False
    assert "STOPPING REPAIR LOOP" in prop4.recommendation
