"""Runs the existing Contract 2 check-suite (ef_engine/test_ef_module.py) under pytest."""
import test_ef_module as ef_checks


def test_ef_module_checks_pass(capsys):
    exit_code = ef_checks.main()
    output = capsys.readouterr().out
    assert exit_code == 0, output
