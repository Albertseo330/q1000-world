import json
import os
import queue
import subprocess
import threading
import time
import uuid
from collections import deque

import runpod


KATAGO_PATH = os.getenv("KATAGO_PATH", "/opt/katago/katago")
MODEL_PATH = os.getenv("KATAGO_MODEL", "/opt/katago/model.bin.gz")
CONFIG_PATH = os.getenv("KATAGO_CONFIG", "/opt/katago/analysis.cfg")
WORKER_SECRET = os.getenv("Q1000_WORKER_SECRET", "")
MAX_TURNS = int(os.getenv("Q1000_MAX_TURNS", "400"))
MAX_VISITS = int(os.getenv("Q1000_MAX_VISITS", "600"))
DEFAULT_VISITS = int(os.getenv("Q1000_DEFAULT_VISITS", "120"))

_engine = None
_stdout_reader = None
_stderr_reader = None
_results = queue.Queue()
_stderr_tail = deque(maxlen=80)
_lock = threading.Lock()


def _stdout_loop(process):
    for line in process.stdout:
        line = line.strip()
        if not line:
            continue
        try:
            _results.put(json.loads(line))
        except json.JSONDecodeError:
            print(f"KataGo non-JSON stdout: {line}", flush=True)


def _stderr_loop(process):
    for line in process.stderr:
        line = line.rstrip()
        if not line:
            continue
        _stderr_tail.append(line)
        print(f"KataGo stderr: {line}", flush=True)


def _engine_error(prefix):
    details = "\n".join(_stderr_tail)
    if details:
        return RuntimeError(f"{prefix}\n{details}")
    return RuntimeError(prefix)


def _start_engine():
    global _engine, _stdout_reader, _stderr_reader

    if _engine and _engine.poll() is None:
        return

    _stderr_tail.clear()

    _engine = subprocess.Popen(
        [
            KATAGO_PATH,
            "analysis",
            "-model",
            MODEL_PATH,
            "-config",
            CONFIG_PATH,
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )

    _stdout_reader = threading.Thread(
        target=_stdout_loop,
        args=(_engine,),
        daemon=True,
    )
    _stderr_reader = threading.Thread(
        target=_stderr_loop,
        args=(_engine,),
        daemon=True,
    )

    _stdout_reader.start()
    _stderr_reader.start()

    time.sleep(0.5)

    return_code = _engine.poll()
    if return_code is not None:
        raise _engine_error(
            f"KataGo exited during startup with code {return_code}"
        )


def _coordinate(value):
    value = str(value).strip().upper()

    if value == "PASS":
        return value

    if len(value) < 2 or value[0] == "I":
        raise ValueError("Invalid Go coordinate")

    return value


def _moves(raw_moves):
    if not isinstance(raw_moves, list) or len(raw_moves) > MAX_TURNS:
        raise ValueError("Invalid or excessive move list")

    cleaned = []

    for item in raw_moves:
        if not isinstance(item, list) or len(item) != 2:
            raise ValueError("Each move must be [color, coordinate]")

        color = str(item[0]).upper()

        if color not in ("B", "W"):
            raise ValueError("Move color must be B or W")

        cleaned.append([color, _coordinate(item[1])])

    return cleaned


def _initial_stones(raw_stones):
    if raw_stones is None:
        return []

    if not isinstance(raw_stones, list) or len(raw_stones) > 20:
        raise ValueError("Invalid initial stones")

    return _moves(raw_stones)


def _query(data):
    size = int(data.get("boardSize", 19))

    if size not in (9, 13, 19):
        raise ValueError("Board size must be 9, 13, or 19")

    moves = _moves(data.get("moves", []))
    turns = data.get("analyzeTurns")

    if turns is None:
        turns = list(range(len(moves) + 1))

    if not isinstance(turns, list) or len(turns) > MAX_TURNS + 1:
        raise ValueError("Invalid analyzeTurns")

    turns = sorted({int(turn) for turn in turns})

    if any(turn < 0 or turn > len(moves) for turn in turns):
        raise ValueError("analyzeTurns contains an invalid turn")

    visits = min(
        MAX_VISITS,
        max(1, int(data.get("maxVisits", DEFAULT_VISITS))),
    )

    request_id = f"q1000-{uuid.uuid4().hex}"

    query = {
        "id": request_id,
        "moves": moves,
        "initialStones": _initial_stones(
            data.get("initialStones")
        ),
        "rules": str(data.get("rules", "japanese")),
        "komi": float(data.get("komi", 6.5)),
        "boardXSize": size,
        "boardYSize": size,
        "analyzeTurns": turns,
        "maxVisits": visits,
        "includePolicy": True,
        "includeOwnership": bool(
            data.get("includeOwnership", False)
        ),
        "includePVVisits": True,
    }

    return request_id, turns, visits, query


def handler(event):
    started = time.monotonic()
    data = event.get("input") or {}

    if WORKER_SECRET and data.get("workerSecret") != WORKER_SECRET:
        raise PermissionError(
            "Unauthorized Q1000 analysis request"
        )

    request_id, turns, visits, query = _query(data)

    deadline = time.monotonic() + min(
        540,
        max(
            30,
            int(data.get("timeoutSeconds", 300)),
        ),
    )

    outputs = []

    with _lock:
        _start_engine()

        if _engine.stdin is None:
            raise _engine_error("KataGo stdin is unavailable")

        _engine.stdin.write(
            json.dumps(query, separators=(",", ":")) + "\n"
        )
        _engine.stdin.flush()

        while len(outputs) < len(turns):
            return_code = _engine.poll()

            if return_code is not None:
                raise _engine_error(
                    f"KataGo exited during analysis with code {return_code}"
                )

            remaining = deadline - time.monotonic()

            if remaining <= 0:
                raise _engine_error(
                    "KataGo analysis exceeded the Q1000 time limit"
                )

            try:
                result = _results.get(
                    timeout=min(1.0, remaining)
                )
            except queue.Empty:
                continue

            if result.get("id") == request_id:
                outputs.append(result)

    outputs.sort(
        key=lambda item: int(item.get("turnNumber", 0))
    )

    return {
        "engine": "KataGo",
        "analysisCount": len(outputs),
        "maxVisits": visits,
        "elapsedMs": round(
            (time.monotonic() - started) * 1000
        ),
        "results": outputs,
    }


runpod.serverless.start({"handler": handler})
