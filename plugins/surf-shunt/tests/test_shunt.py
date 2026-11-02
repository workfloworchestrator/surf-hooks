import io
import json
import sys
import urllib.error
from email.message import Message
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import shunt  # noqa: E402

SETTINGS = shunt.Settings(
    base_url="https://proxy.example", api_key="key", model="gpt-oss-120b", timeout=5, max_input_tokens=1000
)


class FakeResponse(io.BytesIO):
    def __init__(self, payload: dict, model_group: str | None = "gpt-oss-120b"):
        super().__init__(json.dumps(payload).encode())
        self.headers = Message()
        if model_group:
            self.headers["x-litellm-model-group"] = model_group


def answer(content: str) -> dict:
    return {"choices": [{"message": {"content": content}}]}


@pytest.fixture
def fake_proxy(monkeypatch):
    calls = []

    def install(response=None, error=None):
        def urlopen(request, timeout):
            calls.append(json.loads(request.data))
            if error:
                raise error
            return response

        monkeypatch.setattr(shunt.urllib.request, "urlopen", urlopen)
        return calls

    return install


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        pytest.param("```python\nx = 1\n```", "x = 1", id="fenced-with-language"),
        pytest.param("```\nx = 1\ny = 2\n```\n", "x = 1\ny = 2", id="fenced-trailing-newline"),
        pytest.param("x = 1", "x = 1", id="unfenced"),
        pytest.param('doc = """\n```\nexample\n```\n"""', 'doc = """\n```\nexample\n```\n"""', id="inner-fences-kept"),
    ],
)
def test_strip_fences(raw: str, expected: str):
    assert shunt.strip_fences(raw) == expected


ENV_NAMES = [
    "SURF_SHUNT_MODEL", "SURF_SHUNT_READ_MODEL", "SURF_SHUNT_WRITE_MODEL", "SURF_SHUNT_BASE_URL",
    "SURF_SHUNT_API_KEY", "ANTHROPIC_BASE_URL", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_API_KEY",
]


@pytest.fixture
def clean_env(monkeypatch):
    for name in ENV_NAMES:
        monkeypatch.delenv(name, raising=False)

    def apply(env: dict):
        for name, value in env.items():
            monkeypatch.setenv(name, value)

    return apply


PROXY = {"ANTHROPIC_BASE_URL": "https://proxy", "ANTHROPIC_AUTH_TOKEN": "token"}


@pytest.mark.parametrize(
    ("env", "role", "expected_model"),
    [
        pytest.param({}, "READ", "gpt-oss-120b", id="default"),
        pytest.param({"SURF_SHUNT_MODEL": "DeepSeek-V4.1-Flash"}, "WRITE", "DeepSeek-V4.1-Flash", id="shared"),
        pytest.param({"SURF_SHUNT_MODEL": "a", "SURF_SHUNT_READ_MODEL": "b"}, "READ", "b", id="role-override"),
    ],
)
def test_load_settings_model(clean_env, env, role, expected_model):
    clean_env({**PROXY, **env})
    assert shunt.load_settings(role).model == expected_model


@pytest.mark.parametrize(
    ("env", "expected"),
    [
        pytest.param(PROXY, ("https://proxy", "token"), id="claude-code-proxy"),
        pytest.param(
            {"ANTHROPIC_BASE_URL": "https://proxy", "ANTHROPIC_API_KEY": "key"}, ("https://proxy", "key"),
            id="claude-code-proxy-api-key",
        ),
        pytest.param({"SURF_SHUNT_API_KEY": "surf"}, ("https://llms.automation.surf.net", "surf"), id="surf-key"),
        pytest.param(
            {**PROXY, "SURF_SHUNT_BASE_URL": "https://surf", "SURF_SHUNT_API_KEY": "surf"}, ("https://surf", "surf"),
            id="surf-wins",
        ),
    ],
)
def test_load_settings_endpoint(clean_env, env, expected):
    clean_env(env)
    settings = shunt.load_settings("READ")
    assert (settings.base_url, settings.api_key) == expected


@pytest.mark.parametrize(
    "env",
    [
        pytest.param({}, id="nothing"),
        pytest.param({"ANTHROPIC_API_KEY": "real-anthropic-key"}, id="anthropic-key-without-proxy"),
        pytest.param({**PROXY, "SURF_SHUNT_BASE_URL": "https://surf"}, id="surf-url-without-surf-key"),
    ],
)
def test_load_settings_never_mixes_hosts_and_keys(clean_env, env):
    clean_env(env)
    with pytest.raises(shunt.ShuntError):
        shunt.load_settings("READ")


def test_chat_sends_request_without_fallbacks(fake_proxy):
    calls = fake_proxy(FakeResponse(answer("  - ok  ")))
    assert shunt.chat(SETTINGS, "system", "user") == "- ok"
    assert calls[0]["model"] == "gpt-oss-120b"
    assert calls[0]["disable_fallbacks"] is True


@pytest.mark.parametrize(
    ("response", "error", "message"),
    [
        pytest.param(FakeResponse(answer("hi"), model_group="claude-opus-5-5"), None, "answered with", id="rerouted"),
        pytest.param(FakeResponse(answer("")), None, "no answer", id="empty"),
        pytest.param(FakeResponse({"choices": []}), None, "no answer", id="no-choices"),
        pytest.param(
            None,
            urllib.error.HTTPError(
                "u", 500, "err", Message(), io.BytesIO(b'{"error": {"message": "Service Unavailable"}}')
            ),
            "HTTP 500: Service Unavailable",
            id="http-error",
        ),
        pytest.param(None, urllib.error.URLError("timed out"), "timed out", id="unreachable"),
        pytest.param(None, TimeoutError("read timed out"), "read timed out", id="read-timeout"),
    ],
)
def test_chat_failures(fake_proxy, response, error, message):
    fake_proxy(response, error)
    with pytest.raises(shunt.ShuntError, match=message):
        shunt.chat(SETTINGS, "system", "user")


def test_chat_strips_think_blocks(fake_proxy):
    fake_proxy(FakeResponse(answer("<think>hmm</think>\n- answer")))
    assert shunt.chat(SETTINGS, "system", "user") == "- answer"


def test_chat_refuses_oversized_request(fake_proxy):
    calls = fake_proxy(FakeResponse(answer("x")))
    with pytest.raises(shunt.ShuntError, match="over the 1000 limit"):
        shunt.chat(SETTINGS, "system", "x" * 5000)
    assert calls == []


def test_wrap_files(tmp_path: Path):
    path = tmp_path / "a.py"
    path.write_text("x = 1")
    assert shunt.wrap_files([str(path)]) == f'<file path="{path}">\nx = 1\n</file>\n\n'


def test_wrap_files_rejects_missing(tmp_path: Path):
    with pytest.raises(shunt.ShuntError, match="not found"):
        shunt.wrap_files([str(tmp_path / "nope.py")])


@pytest.fixture
def configured(monkeypatch):
    monkeypatch.setenv("SURF_SHUNT_API_KEY", "key")
    monkeypatch.setenv("SURF_SHUNT_MODEL", "gpt-oss-120b")


def test_bulk_read_cli(configured, fake_proxy, tmp_path: Path, capsys):
    source = tmp_path / "service.py"
    source.write_text("def handler(): ...")
    calls = fake_proxy(FakeResponse(answer("- `handler`: does nothing")))

    shunt.main(["bulk-read", "--question", "What is here?", "--paths", str(source)])

    user_message = calls[0]["messages"][1]["content"]
    assert "def handler(): ..." in user_message
    assert user_message.endswith("Question: What is here?\n")
    assert capsys.readouterr().out == "- `handler`: does nothing\n"


def test_code_write_cli_writes_target(configured, fake_proxy, tmp_path: Path):
    reference = tmp_path / "test_ref.py"
    reference.write_text("def test_ref(): ...")
    target = tmp_path / "out" / "test_new.py"
    fake_proxy(FakeResponse(answer("```python\ndef test_new(): ...\n```")))

    shunt.main(["code-write", "--spec", "tests", "--reference", str(reference), "--target", str(target)])

    assert target.read_text() == "def test_new(): ...\n"


def test_code_write_cli_keeps_existing_target(configured, fake_proxy, tmp_path: Path, capsys):
    reference = tmp_path / "ref.py"
    reference.write_text("x = 1")
    target = tmp_path / "existing.py"
    target.write_text("keep me")
    calls = fake_proxy(FakeResponse(answer("y = 2")))

    with pytest.raises(SystemExit) as exit_info:
        shunt.main(["code-write", "--spec", "s", "--reference", str(reference), "--target", str(target)])

    assert exit_info.value.code == 1
    assert "--force" in capsys.readouterr().err
    assert target.read_text() == "keep me"
    assert calls == []
