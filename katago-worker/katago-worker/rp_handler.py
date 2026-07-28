import json
import os
import queue
import subprocess
import threading
import time
import uuid

import runpod


KATAGO_PATH = os.getenv("KATAGO_PATH", "/opt/katago/katago")
MODEL_PATH = os.getenv("KATAGO_MODEL", "/opt/katago/model.bin.gz")
CONFIG_PATH = os.getenv("KATAGO_CONFIG", "/opt/katago/analysis.cfg")
WORKER_SECRET = os.getenv("Q1000_WORKER_SECRET", "")
MAX_TURNS = int(os.getenv("Q1000_MAX_TURNS", "400"))
MAX_VISITS = int(os.getenv("Q1000_MAX_VISITS", "600"))
DEFAULT_VISITS = int(os.getenv("Q1000_DEFAULT_VISITS", "120"))

_engine = None
_reader = None
_results = queue.Queue()
_lock = threading.Lock()


def _reader_loop(process):
    for line in process.stdout:
        line = line.strip()
        if not line:
            continue
        try:
            _results.put(json.loads(line))
        except json.JSONDecodeError:
            continue


def _start_engine():
    global _engine, _reader
    if _engine and _engine.poll() is None:
        return
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
    _reader = threading.Thread(
        target=_reader_loop,
        args=(_engine,),
        daemon=True,
    )
    _reader.start()


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
        "initialStones": _initial_stones(data.get("initialStones")),
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

        _engine.stdin.write(
            json.dumps(query, separators=(",", ":")) + "\n"
        )
        _engine.stdin.flush()

        while len(outputs) < len(turns):
            remaining = deadline - time.monotonic()

            if remaining <= 0:
                raise TimeoutError(
                    "KataGo analysis exceeded the Q1000 time limit"
                )

            result = _results.get(timeout=remaining)

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
