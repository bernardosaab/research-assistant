from typer.testing import CliRunner

from research_assistant.cli import app

runner = CliRunner()


def test_serve_command_calls_uvicorn_run_with_default_port(monkeypatch):
    captured = {}

    def fake_run(app_path, host, port):
        captured["app_path"] = app_path
        captured["host"] = host
        captured["port"] = port

    monkeypatch.setattr("uvicorn.run", fake_run)

    result = runner.invoke(app, ["serve"])

    assert result.exit_code == 0
    assert captured["app_path"] == "research_assistant.web.app:app"
    assert captured["host"] == "127.0.0.1"
    assert captured["port"] == 8000


def test_serve_command_respects_custom_port(monkeypatch):
    captured = {}

    def fake_run(app_path, host, port):
        captured["port"] = port

    monkeypatch.setattr("uvicorn.run", fake_run)

    result = runner.invoke(app, ["serve", "--port", "9000"])

    assert result.exit_code == 0
    assert captured["port"] == 9000
