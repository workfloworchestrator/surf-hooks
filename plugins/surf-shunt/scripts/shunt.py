#!/usr/bin/env python3
"""
surf-shunt: delegate I/O-heavy work to an on-prem model behind the SURF LiteLLM proxy.

  shunt.py bulk-read  --question "..." --paths a.py b.py
  shunt.py code-write --spec "..." --reference ref.py [--target out.py] [--force]

Every call is one-shot: the files go to the worker model, only its answer comes
back. The answer goes to stdout, a one-line usage note to stderr.

Configuration (environment):
  SURF_SHUNT_MODEL              model for both roles (default: gpt-oss-120b)
  SURF_SHUNT_READ_MODEL         override for bulk-read
  SURF_SHUNT_WRITE_MODEL        override for code-write
  SURF_SHUNT_BASE_URL           proxy URL (default: $ANTHROPIC_BASE_URL, else llms.automation.surf.net)
  SURF_SHUNT_API_KEY            proxy key (default: $ANTHROPIC_AUTH_TOKEN, else $ANTHROPIC_API_KEY)
  SURF_SHUNT_TIMEOUT            seconds per call (default: 300)
  SURF_SHUNT_MAX_INPUT_TOKENS   refuse requests estimated above this (default: 100000)
"""

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

DEFAULT_BASE_URL = "https://llms.automation.surf.net"
DEFAULT_MODEL = "gpt-oss-120b"
DEFAULT_TIMEOUT = 300
# gpt-oss-120b has a 128k window; leave headroom for the answer
DEFAULT_MAX_INPUT_TOKENS = 100_000

BULK_READER_PROMPT = (
    "You are a precise code analyst. Read the provided files and answer the question concisely. "
    "Output structured bullets only. No greetings, no prose, no preambles, no summaries. "
    "Lead every bullet with the exact name, type, or line number. Use nested bullets for details. "
    "Skip anything the caller did not ask for. If the files do not contain the answer, say so."
)

CODE_WRITER_PROMPT = (
    "You generate code files based on a spec and reference files. Match the existing patterns, "
    "conventions, naming, and style exactly. Output only the code for the requested file - "
    "no explanations, no markdown fences. If the spec is ambiguous, make reasonable choices "
    "that match the patterns in the reference code."
)

FENCED = re.compile(r"\A```[^\n]*\n(?P<body>.*?)\n?```\Z", re.DOTALL)
# Reasoning models served without a reasoning parser leak their thoughts inline
THINK_BLOCK = re.compile(r"<think>.*?</think>\s*", re.DOTALL)


class ShuntError(Exception):
    pass


@dataclass(frozen=True)
class Settings:
    base_url: str
    api_key: str
    model: str
    timeout: int
    max_input_tokens: int


def _env_int(name: str, default: int) -> int:
    value = os.environ.get(name, "")
    return int(value) if value.isdigit() else default


def _first_env(*names: str) -> str:
    return next((os.environ[name] for name in names if os.environ.get(name)), "")


def load_settings(role: str) -> Settings:
    api_key = _first_env("SURF_SHUNT_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_API_KEY")
    if not api_key:
        raise ShuntError("no API key: set SURF_SHUNT_API_KEY (or ANTHROPIC_AUTH_TOKEN)")
    return Settings(
        base_url=_first_env("SURF_SHUNT_BASE_URL", "ANTHROPIC_BASE_URL") or DEFAULT_BASE_URL,
        api_key=api_key,
        model=_first_env(f"SURF_SHUNT_{role}_MODEL", "SURF_SHUNT_MODEL") or DEFAULT_MODEL,
        timeout=_env_int("SURF_SHUNT_TIMEOUT", DEFAULT_TIMEOUT),
        max_input_tokens=_env_int("SURF_SHUNT_MAX_INPUT_TOKENS", DEFAULT_MAX_INPUT_TOKENS),
    )


def estimate_tokens(text: str) -> int:
    return len(text) // 4


def _http_error_message(exc: urllib.error.HTTPError) -> str:
    raw = exc.read().decode("utf-8", errors="replace")
    try:
        return json.loads(raw)["error"]["message"]
    except (json.JSONDecodeError, KeyError, TypeError):
        return raw[:500]


def chat(settings: Settings, system: str, user: str) -> str:
    tokens = estimate_tokens(system + user)
    if tokens > settings.max_input_tokens:
        raise ShuntError(
            f"request is ~{tokens} tokens, over the {settings.max_input_tokens} limit "
            f"for {settings.model}. Send fewer or smaller files per call."
        )

    body = {
        "model": settings.model,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "temperature": 0.2,
        # Never let the proxy reroute to another (possibly cloud-hosted) model
        "disable_fallbacks": True,
    }
    request = urllib.request.Request(
        f"{settings.base_url.rstrip('/')}/v1/chat/completions",
        data=json.dumps(body).encode(),
        headers={"Authorization": f"Bearer {settings.api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=settings.timeout) as response:
            payload = json.load(response)
            served_by = response.headers.get("x-litellm-model-group")
    except urllib.error.HTTPError as exc:
        raise ShuntError(f"{settings.model} returned HTTP {exc.code}: {_http_error_message(exc)}") from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        reason = getattr(exc, "reason", exc)
        raise ShuntError(f"could not get an answer from {settings.model} at {settings.base_url}: {reason}") from exc

    if served_by and served_by != settings.model:
        raise ShuntError(f"asked for {settings.model} but the proxy answered with {served_by}; answer discarded")

    choices = payload.get("choices") or [{}]
    content = THINK_BLOCK.sub("", choices[0].get("message", {}).get("content") or "").strip()
    if not content:
        raise ShuntError(f"{settings.model} returned no answer")
    return content


def strip_fences(text: str) -> str:
    match = FENCED.match(text.strip())
    return match["body"] if match else text


def wrap_files(paths: list[str]) -> str:
    missing = [path for path in paths if not Path(path).is_file()]
    if missing:
        raise ShuntError(f"file(s) not found: {', '.join(missing)}")
    return "".join(
        f'<file path="{path}">\n{Path(path).read_text(encoding="utf-8", errors="replace")}\n</file>\n\n'
        for path in paths
    )


def _report_usage(message: str, settings: Settings) -> None:
    print(f"[surf-shunt: ~{estimate_tokens(message)} input tokens -> {settings.model}]", file=sys.stderr)


def bulk_read(args: argparse.Namespace) -> None:
    settings = load_settings("READ")
    message = wrap_files(args.paths) + f"Question: {args.question}\n"
    print(chat(settings, BULK_READER_PROMPT, message))
    _report_usage(message, settings)


def code_write(args: argparse.Namespace) -> None:
    target = Path(args.target) if args.target else None
    if target and target.exists() and not args.force:
        raise ShuntError(f"{target} already exists; pass --force to overwrite it")

    settings = load_settings("WRITE")
    output_line = f"Output file: {target}\n\n" if target else ""
    message = f"Spec: {args.spec}\n\n{output_line}Reference files:\n\n{wrap_files(args.reference)}"
    code = strip_fences(chat(settings, CODE_WRITER_PROMPT, message))

    if target:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(code.rstrip("\n") + "\n", encoding="utf-8")
        print(f"Wrote {len(code.splitlines())} lines to {target}", file=sys.stderr)
    else:
        print(code)
    _report_usage(message, settings)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="shunt.py", description=__doc__.split("\n\n")[0])
    commands = parser.add_subparsers(dest="command", required=True)

    read = commands.add_parser("bulk-read", help="ask a question about one or more files")
    read.add_argument("--question", required=True)
    read.add_argument("--paths", nargs="+", required=True)
    read.set_defaults(handler=bulk_read)

    write = commands.add_parser("code-write", help="generate a file that follows reference files")
    write.add_argument("--spec", required=True)
    write.add_argument("--reference", nargs="+", required=True, help="file(s) whose patterns to match")
    write.add_argument("--target", help="write here instead of stdout")
    write.add_argument("--force", action="store_true", help="overwrite an existing --target")
    write.set_defaults(handler=code_write)
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    try:
        args.handler(args)
    except ShuntError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
