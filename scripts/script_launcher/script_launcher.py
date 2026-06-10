# -*- coding: utf-8 -*-
r"""
Local web launcher for YMM4 scripts.

Usage:
  python scripts\script_launcher\script_launcher.py
  python scripts\script_launcher\script_launcher.py --list-scripts

Notes:
  - Uses only the Python standard library.
  - Serves a local web UI at http://127.0.0.1:<port>/.
  - Runs one script at a time and writes logs to logs/script_launcher/.
"""

from __future__ import annotations

import argparse
import json
import json.decoder
import mimetypes
import os
import socket
import subprocess
import sys
import threading
import uuid
import webbrowser
from dataclasses import dataclass, field
from datetime import datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Literal
from urllib.parse import unquote, urlparse


ROOT_DIR = Path(__file__).resolve().parents[2]
STATIC_DIR = Path(__file__).resolve().parent / "web"
DEFAULT_LOG_DIR = ROOT_DIR / "logs" / "script_launcher"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8766

FieldKind = Literal["text", "int", "path", "bool"]


@dataclass(frozen=True)
class OptionField:
    key: str
    label: str
    flag: str
    kind: FieldKind = "text"
    default: str | int | bool = ""
    help_text: str = ""
    required: bool = False
    placeholder: str = ""

    def to_json(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "label": self.label,
            "flag": self.flag,
            "kind": self.kind,
            "default": self.default,
            "helpText": self.help_text,
            "required": self.required,
            "placeholder": self.placeholder,
        }


@dataclass(frozen=True)
class ScriptDefinition:
    key: str
    title: str
    description: str
    script_path: Path
    run_label: str = "実行"
    warning: str = ""
    fields: tuple[OptionField, ...] = field(default_factory=tuple)

    def to_json(self) -> dict[str, Any]:
        relative_script_path = self.script_path.relative_to(ROOT_DIR)
        return {
            "key": self.key,
            "title": self.title,
            "description": self.description,
            "scriptPath": str(relative_script_path),
            "runLabel": self.run_label,
            "warning": self.warning,
            "fields": [field_def.to_json() for field_def in self.fields],
        }


SCRIPT_DEFINITIONS: tuple[ScriptDefinition, ...] = (
    ScriptDefinition(
        key="insert_gap_layer",
        title="セリフ間の空白を作る",
        description="YMM4 MCP経由で、指定レイヤー上のセリフアイテム間に必要な空白フレームを作ります。",
        script_path=ROOT_DIR / "scripts" / "insert_gap_layer" / "insert_gap_layer.py",
        run_label="YMM4へ反映して保存",
        warning="実行するとYMM4上のプロジェクトへ反映し、そのまま保存します。",
        fields=(
            OptionField(
                key="base_url",
                label="MCP API URL",
                flag="--base-url",
                default="http://localhost:8765/api",
                help_text="通常は変更不要です。",
            ),
            OptionField(
                key="layer",
                label="対象レイヤー",
                flag="--layer",
                default="01",
                placeholder="01",
                help_text="例: 01 / 1 / 02",
            ),
            OptionField(
                key="gap",
                label="空白フレーム",
                flag="--gap",
                kind="int",
                default=12,
                help_text="0以上の整数。",
            ),
        ),
    ),
    ScriptDefinition(
        key="split_group_direct_ymmp",
        title="GroupItemをセリフ区間に分割",
        description=".ymmpを直接読み、対象GroupItemを中性.* のセリフ区間だけに合わせて分割します。",
        script_path=ROOT_DIR / "scripts" / "split_group_direct_ymmp" / "split_group_direct_ymmp.py",
        run_label="dry-run / 実行",
        warning="--applyを有効にすると.ymmpを上書きします。先にYMM4で保存して閉じてください。",
        fields=(
            OptionField(
                key="project",
                label=".ymmpファイル",
                flag="--project",
                kind="path",
                required=True,
                placeholder=r"C:\path\project.ymmp",
            ),
            OptionField(
                key="group_memo",
                label="グループ備考トークン",
                flag="--group-memo",
                default="t",
            ),
            OptionField(
                key="group_layers",
                label="グループレイヤー",
                flag="--group-layers",
                default="",
                placeholder="1,10",
                help_text="空欄なら備考トークンで判定します。",
            ),
            OptionField(
                key="speaker_regex",
                label="話者名の正規表現",
                flag="--speaker-regex",
                default="中性.*",
            ),
            OptionField(
                key="voice_layers",
                label="セリフレイヤー",
                flag="--voice-layers",
                default="",
                placeholder="3,4",
                help_text="空欄なら話者名だけで判定します。",
            ),
            OptionField(
                key="voice_tail_trim",
                label="末尾カット",
                flag="--voice-tail-trim",
                kind="int",
                default=12,
            ),
            OptionField(
                key="next_voice_gap",
                label="次セリフ前の余白",
                flag="--next-voice-gap",
                kind="int",
                default=0,
            ),
            OptionField(
                key="apply",
                label=".ymmpを上書きする",
                flag="--apply",
                kind="bool",
                default=False,
                help_text="オフの場合はdry-runです。",
            ),
        ),
    ),
)

SCRIPT_BY_KEY = {definition.key: definition for definition in SCRIPT_DEFINITIONS}


class RunState:
    def __init__(self, run_id: str, script: ScriptDefinition, command: list[str], log_path: Path) -> None:
        self.run_id = run_id
        self.script = script
        self.command = command
        self.log_path = log_path
        self.started_at = datetime.now()
        self.finished_at: datetime | None = None
        self.return_code: int | None = None
        self.status = "running"
        self.output = ""
        self.process: subprocess.Popen[str] | None = None
        self.lock = threading.Lock()

    def append(self, text: str) -> None:
        with self.lock:
            self.output += text

    def snapshot(self) -> dict[str, Any]:
        with self.lock:
            return {
                "runId": self.run_id,
                "scriptKey": self.script.key,
                "scriptTitle": self.script.title,
                "status": self.status,
                "returnCode": self.return_code,
                "startedAt": self.started_at.isoformat(timespec="seconds"),
                "finishedAt": self.finished_at.isoformat(timespec="seconds") if self.finished_at else None,
                "command": subprocess.list2cmdline(self.command),
                "logPath": str(self.log_path),
                "output": self.output,
            }


RUNS: dict[str, RunState] = {}
ACTIVE_RUN_ID: str | None = None
RUNS_LOCK = threading.Lock()
LOG_DIR = DEFAULT_LOG_DIR


def build_command(script: ScriptDefinition, raw_options: dict[str, Any]) -> list[str]:
    command = [sys.executable, str(script.script_path)]

    for field_def in script.fields:
        raw_value = raw_options.get(field_def.key, field_def.default)

        if field_def.kind == "bool":
            if bool(raw_value):
                command.append(field_def.flag)
            continue

        value = str(raw_value).strip()
        if field_def.required and not value:
            raise ValueError(f"{field_def.label} を指定してください。")
        if value == "":
            continue

        if field_def.kind == "int":
            try:
                number = int(value)
            except ValueError as e:
                raise ValueError(f"{field_def.label} は整数で指定してください。") from e
            if number < 0:
                raise ValueError(f"{field_def.label} は0以上で指定してください。")
            value = str(number)

        command.extend([field_def.flag, value])

    return command


def start_run(script_key: str, options: dict[str, Any]) -> RunState:
    global ACTIVE_RUN_ID

    script = SCRIPT_BY_KEY.get(script_key)
    if script is None:
        raise ValueError("未知のスクリプトです。")
    if not script.script_path.exists():
        raise ValueError(f"スクリプトが見つかりません: {script.script_path}")

    command = build_command(script, options)

    with RUNS_LOCK:
        if ACTIVE_RUN_ID is not None:
            active = RUNS.get(ACTIVE_RUN_ID)
            if active is not None and active.status == "running":
                raise ValueError("別のスクリプトが実行中です。")

        LOG_DIR.mkdir(parents=True, exist_ok=True)
        run_id = uuid.uuid4().hex[:12]
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_path = LOG_DIR / f"{timestamp}_{script.key}.log"
        run_state = RunState(run_id, script, command, log_path)
        RUNS[run_id] = run_state
        ACTIVE_RUN_ID = run_id

    thread = threading.Thread(target=run_process, args=(run_state,), daemon=True)
    thread.start()
    return run_state


def run_process(run_state: RunState) -> None:
    global ACTIVE_RUN_ID

    header = (
        f"[{format_time()}] START {run_state.script.title}\n"
        f"cwd: {ROOT_DIR}\n"
        f"command: {subprocess.list2cmdline(run_state.command)}\n"
        f"log: {run_state.log_path}\n\n"
    )
    run_state.append(header)

    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"

    with run_state.log_path.open("w", encoding="utf-8", newline="\n") as log_file:
        log_file.write(header)
        log_file.flush()

        try:
            process = subprocess.Popen(
                run_state.command,
                cwd=ROOT_DIR,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=env,
            )
        except OSError as e:
            message = f"ERROR: {e}\n"
            run_state.append(message)
            log_file.write(message)
            with run_state.lock:
                run_state.status = "failed"
                run_state.finished_at = datetime.now()
            with RUNS_LOCK:
                if ACTIVE_RUN_ID == run_state.run_id:
                    ACTIVE_RUN_ID = None
            return

        run_state.process = process
        assert process.stdout is not None

        for line in process.stdout:
            run_state.append(line)
            log_file.write(line)
            log_file.flush()

        return_code = process.wait()
        footer = f"\n[{format_time()}] END exit code {return_code}\n"
        run_state.append(footer)
        log_file.write(footer)

    with run_state.lock:
        run_state.return_code = return_code
        run_state.finished_at = datetime.now()
        run_state.status = "success" if return_code == 0 else "failed"

    with RUNS_LOCK:
        if ACTIVE_RUN_ID == run_state.run_id:
            ACTIVE_RUN_ID = None


def stop_run(run_id: str) -> RunState:
    run_state = RUNS.get(run_id)
    if run_state is None:
        raise ValueError("run_idが見つかりません。")
    if run_state.process is None or run_state.status != "running":
        return run_state

    run_state.append(f"\n[{format_time()}] STOP requested\n")
    run_state.process.terminate()
    with run_state.lock:
        run_state.status = "stopping"
    return run_state


def format_time() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def find_free_port(host: str, preferred_port: int) -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        result = sock.connect_ex((host, preferred_port))
    if result != 0:
        return preferred_port

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((host, 0))
        return int(sock.getsockname()[1])


class LauncherHandler(BaseHTTPRequestHandler):
    server_version = "YMM4ScriptLauncher/1.0"

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/api/scripts":
            self.send_json({"scripts": [definition.to_json() for definition in SCRIPT_DEFINITIONS]})
            return

        if path.startswith("/api/runs/"):
            run_id = path.rsplit("/", 1)[-1]
            run_state = RUNS.get(run_id)
            if run_state is None:
                self.send_json({"error": "run_idが見つかりません。"}, HTTPStatus.NOT_FOUND)
                return
            self.send_json(run_state.snapshot())
            return

        self.serve_static(path)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)

        if parsed.path == "/api/run":
            try:
                payload = self.read_json()
                run_state = start_run(str(payload.get("scriptKey", "")), dict(payload.get("options", {})))
            except (ValueError, json.decoder.JSONDecodeError) as e:
                self.send_json({"error": str(e)}, HTTPStatus.BAD_REQUEST)
                return
            self.send_json(run_state.snapshot())
            return

        if parsed.path.startswith("/api/runs/") and parsed.path.endswith("/stop"):
            run_id = parsed.path.split("/")[-2]
            try:
                run_state = stop_run(run_id)
            except ValueError as e:
                self.send_json({"error": str(e)}, HTTPStatus.NOT_FOUND)
                return
            self.send_json(run_state.snapshot())
            return

        self.send_json({"error": "Not found"}, HTTPStatus.NOT_FOUND)

    def serve_static(self, path: str) -> None:
        if path == "/":
            path = "/index.html"

        relative = unquote(path.lstrip("/"))
        static_path = (STATIC_DIR / relative).resolve()

        try:
            static_path.relative_to(STATIC_DIR.resolve())
        except ValueError:
            self.send_error(HTTPStatus.FORBIDDEN)
            return

        if not static_path.is_file():
            self.send_error(HTTPStatus.NOT_FOUND)
            return

        content_type = mimetypes.guess_type(str(static_path))[0] or "application/octet-stream"
        data = static_path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length).decode("utf-8")
        if not raw:
            return {}
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            raise ValueError("JSON objectを指定してください。")
        return payload

    def send_json(self, payload: dict[str, Any], status: HTTPStatus = HTTPStatus.OK) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, format_: str, *args: Any) -> None:
        print(f"[{format_time()}] {self.address_string()} {format_ % args}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="YMM4 scripts local web launcher.")
    parser.add_argument("--host", default=DEFAULT_HOST, help=f"bind host. default: {DEFAULT_HOST}")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"bind port. default: {DEFAULT_PORT}")
    parser.add_argument("--log-dir", type=Path, default=DEFAULT_LOG_DIR, help=f"log directory. default: {DEFAULT_LOG_DIR}")
    parser.add_argument("--open", action="store_true", help="起動後に既定ブラウザを開きます。")
    parser.add_argument("--list-scripts", action="store_true", help="UIに登録されているスクリプトを表示して終了します。")
    return parser


def main() -> int:
    global LOG_DIR

    args = build_parser().parse_args()
    LOG_DIR = args.log_dir

    if args.list_scripts:
        for definition in SCRIPT_DEFINITIONS:
            print(f"{definition.key}: {definition.title}")
        return 0

    port = find_free_port(args.host, args.port)
    url = f"http://{args.host}:{port}/"
    server = ThreadingHTTPServer((args.host, port), LauncherHandler)
    print(f"YMM4 scripts launcher: {url}")
    print("Press Ctrl+C to stop.")

    if args.open:
        webbrowser.open(url)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping server...")
    finally:
        server.server_close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
