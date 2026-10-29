# script.py
# Runs LLM-written Python in an isolated subprocess. The script has no filesystem, network or OS access;
# it can only use the `ava` bridge: allowlisted tools, the LLM, and create/append-only markdown notes.
import ast
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

TIMEOUT_SECONDS = 120
MAX_TOOL_CALLS = 40
MAX_OUTPUT_CHARS = 8000
MAX_RESULT_CHARS = 20000
MAX_NOTE_BYTES = 200_000
NOTES_SUBDIR = "AVA Scripts"
LLM_MODEL = "openai/gpt-oss-20b"

# Only read-only or additive tools. Nothing here can delete or overwrite.
# Deliberately EXCLUDED: send_whatsapp_message (can't unsend), resolve_completed_task,
# run_system_maintenance, launch_system_application, get_visual_context (screen contents).
# Add telegram / google-doc tools here once they exist.
SCRIPT_ALLOWED_TOOLS = {
    "basic_web_search", "get_weather_forecast", "execute_deep_research",
    "check_for_new_emails", "read_email_log",
    "view_active_tasks", "get_agenda_for_date",
    "add_new_task", "store_fact", "create_google_calendar_event",
}

ALLOWED_IMPORTS = {
    "json", "re", "datetime", "math", "collections", "itertools",
    "textwrap", "statistics", "string", "typing", "functools",
}
BLOCKED_NAMES = {
    "open", "exec", "eval", "compile", "__import__", "getattr", "setattr",
    "delattr", "globals", "locals", "vars", "dir", "input", "breakpoint",
    "exit", "quit", "type",
}


def _vet_script(script: str):
    """Static pre-check. Returns a problem description, or None if the script looks OK."""
    try:
        tree = ast.parse(script)
    except SyntaxError as e:
        return f"Syntax error: {e}"
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] not in ALLOWED_IMPORTS:
                    return f"Import '{alias.name}' is not allowed."
        elif isinstance(node, ast.ImportFrom):
            if node.level or (node.module or "").split(".")[0] not in ALLOWED_IMPORTS:
                return f"Import from '{node.module}' is not allowed."
        elif isinstance(node, ast.Attribute) and node.attr.startswith("_"):
            return f"Access to attribute '{node.attr}' is not allowed."
        elif isinstance(node, ast.Name) and (node.id in BLOCKED_NAMES or node.id.startswith("__")):
            return f"Use of '{node.id}' is not allowed."
    return None


# Runs inside the child process. Its real stdout is reserved for the JSON bridge;
# the script's own print() output is captured separately.
RUNNER = r'''
import sys, os, io, json, builtins, traceback
from types import SimpleNamespace

_in = os.fdopen(os.dup(0), "r", encoding="utf-8")
_out = os.fdopen(os.dup(1), "w", encoding="utf-8")
_buf = io.StringIO()
sys.stdin = io.StringIO("")
sys.stdout = _buf
sys.stderr = _buf

def _send(obj):
    _out.write(json.dumps(obj) + "\n")
    _out.flush()

def _rpc(kind, **payload):
    _send({"type": kind, **payload})
    reply = json.loads(_in.readline())
    if not reply.get("ok"):
        raise RuntimeError(reply.get("error", "call failed"))
    return reply["result"]

_init = json.loads(_in.readline())
_allowed = set(_init["imports"])
_real_import = builtins.__import__

def _guarded_import(name, globals=None, locals=None, fromlist=(), level=0):
    if level or name.split(".")[0] not in _allowed:
        raise ImportError("import '%s' is not allowed" % name)
    return _real_import(name, globals, locals, fromlist, level)

_names = """print len range enumerate zip map filter sorted reversed min max sum
any all abs round str int float bool list dict set tuple frozenset isinstance
repr format iter next slice divmod chr ord hash __build_class__
Exception ValueError KeyError TypeError IndexError RuntimeError ImportError
StopIteration""".split()
_safe = {n: getattr(builtins, n) for n in _names if hasattr(builtins, n)}
_safe["__import__"] = _guarded_import

ava = SimpleNamespace(
    run=lambda tool, **kw: _rpc("call", name=tool, args=kw),
    ask=lambda prompt: _rpc("llm", prompt=prompt),
    read_note=lambda filename: _rpc("read_note", filename=filename),
    append_note=lambda filename, text: _rpc("append_note", filename=filename, text=text),
)

try:
    exec(compile(_init["code"], "<ava_script>", "exec"),
         {"__builtins__": _safe, "__name__": "ava_script", "ava": ava})
    _send({"type": "done", "ok": True, "output": _buf.getvalue()})
except BaseException:
    _send({"type": "done", "ok": False, "output": _buf.getvalue(),
           "error": traceback.format_exc(limit=3)})
'''


def _note_path(filename) -> Path:
    vault = os.environ.get("OBSIDIAN_VAULT_PATH") or os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "ava_vault"
    )
    name = str(filename)
    if not re.fullmatch(r"[\w .\-]{1,80}", name):
        raise ValueError("Note name may only use letters, numbers, spaces, '.', '-', '_'.")
    if not name.lower().endswith(".md"):
        name += ".md"
    folder = (Path(vault) / NOTES_SUBDIR).resolve()
    folder.mkdir(parents=True, exist_ok=True)
    path = (folder / name).resolve()
    if path.parent != folder:
        raise ValueError("Note must live directly inside the scripts folder.")
    return path


def _handle_request(msg: dict, dispatch) -> dict:
    """Runs one bridge request from the sandboxed script, in the parent process."""
    try:
        kind = msg.get("type")

        if kind == "call":
            name = msg.get("name")
            if name not in SCRIPT_ALLOWED_TOOLS:
                raise PermissionError(f"Tool '{name}' is not available to scripts.")
            if dispatch is None:
                raise RuntimeError("No tool dispatcher attached.")
            result = dispatch(name, msg.get("args") or {})
            return {"ok": True, "result": str(result)[:MAX_RESULT_CHARS]}

        if kind == "llm":
            from groq import Groq
            resp = Groq().chat.completions.create(
                model=LLM_MODEL,
                messages=[{"role": "user", "content": str(msg.get("prompt", ""))[:30000]}],
                temperature=0.2,
            )
            return {"ok": True, "result": resp.choices[0].message.content or ""}

        if kind == "read_note":
            path = _note_path(msg.get("filename"))
            text = path.read_text(encoding="utf-8") if path.exists() else ""
            return {"ok": True, "result": text[:MAX_RESULT_CHARS]}

        if kind == "append_note":
            path = _note_path(msg.get("filename"))
            text = str(msg.get("text", ""))
            current = path.stat().st_size if path.exists() else 0
            if current + len(text.encode("utf-8")) > MAX_NOTE_BYTES:
                raise ValueError("Note size limit reached.")
            with open(path, "a", encoding="utf-8") as f:  # append only, never "w"
                f.write(text if text.endswith("\n") else text + "\n")
            return {"ok": True, "result": f"Appended to {path.name}"}

        raise ValueError(f"Unknown request type '{kind}'")
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


def execute_python_code(script: str, dispatch=None) -> str:
    """
    Runs an LLM-written script in an isolated subprocess. The script can only reach the outside world
    through the `ava` bridge. `dispatch(tool_name, args)` is supplied by the router.
    """
    problem = _vet_script(script)
    if problem:
        return f"Error: script rejected before running. {problem}"

    env = {"PYTHONIOENCODING": "utf-8"}  # no API keys or other secrets reach the child
    if "SYSTEMROOT" in os.environ:  # required for Python to start on Windows
        env["SYSTEMROOT"] = os.environ["SYSTEMROOT"]

    final, timed_out = None, threading.Event()
    popen_extra = {"creationflags": subprocess.CREATE_NO_WINDOW} if sys.platform == "win32" else {}

    with tempfile.TemporaryDirectory() as scratch:
        runner_path = os.path.join(scratch, "runner.py")
        Path(runner_path).write_text(RUNNER, encoding="utf-8")

        proc = subprocess.Popen(
            [sys.executable, "-I", runner_path],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            text=True, encoding="utf-8", cwd=scratch, env=env, **popen_extra,
        )
        timer = threading.Timer(TIMEOUT_SECONDS, lambda: (timed_out.set(), proc.kill()))
        timer.start()
        try:
            proc.stdin.write(json.dumps({"code": script, "imports": sorted(ALLOWED_IMPORTS)}) + "\n")
            proc.stdin.flush()
            calls = 0
            while True:
                line = proc.stdout.readline()
                if not line:
                    break
                msg = json.loads(line)
                if msg.get("type") == "done":
                    final = msg
                    break
                calls += 1
                if calls > MAX_TOOL_CALLS:
                    reply = {"ok": False, "error": "Tool-call limit reached."}
                else:
                    reply = _handle_request(msg, dispatch)
                proc.stdin.write(json.dumps(reply) + "\n")
                proc.stdin.flush()
        except (BrokenPipeError, ValueError, OSError):
            pass
        finally:
            timer.cancel()
            proc.kill()
            proc.wait()

    if timed_out.is_set():
        return f"Error: script exceeded {TIMEOUT_SECONDS}s and was stopped."
    if final is None:
        return "Error: script process ended unexpectedly."

    output = (final.get("output") or "")[:MAX_OUTPUT_CHARS]
    if final.get("ok"):
        return f"Success: {output}" if output else "Success: Script executed with no print output."
    return f"Error during execution:\n{final.get('error', '')}\n{output}".strip()
