from __future__ import annotations

import otto.brain_cli as brain_cli


def test_brain_cli_all_announces_progress(monkeypatch, capsys):
    monkeypatch.setattr(brain_cli, "run_brain_self_model", lambda: {"status": "ok"})
    monkeypatch.setattr(brain_cli, "run_brain_predictions", lambda: {"status": "ok"})
    monkeypatch.setattr(brain_cli, "run_brain_ritual_cycle", lambda: {"status": "ok"})

    exit_code = brain_cli.main(["all"])

    captured = capsys.readouterr().out
    assert exit_code == 0
    assert "[Otto] Brain all = self-model + predictions + ritual." in captured
    assert "[Otto] Starting ritual cycle. Scan phase can take 30-60s on a full vault..." in captured
    assert "=== Otto Brain All ===" in captured


def test_brain_cli_ritual_announces_scan_cost(monkeypatch, capsys):
    monkeypatch.setattr(brain_cli, "run_brain_ritual_cycle", lambda: {"status": "ok"})

    exit_code = brain_cli.main(["ritual"])

    captured = capsys.readouterr().out
    assert exit_code == 0
    assert "[Otto] Running brain ritual cycle. Scan phase can take 30-60s on a full vault..." in captured
    assert "Ritual cycle: {'status': 'ok'}" in captured
