"""开发标定入口的开关：未显式允许时不得查询分布或推进对局。"""

from __future__ import annotations

from tools.ninth_identity_calibration import main


def test_calibration_refuses_to_run_without_an_explicit_switch() -> None:
    assert main([]) == 2
