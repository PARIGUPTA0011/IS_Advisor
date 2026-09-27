"""IS-Advisor demo server. Offline, standard library only.

    python demo/server.py               # http://localhost:8765
    python demo/server.py --port 9000

No LLM, no API key, and by default no network at all: the knowledge graph is
read from the same CSVs Neo4j is loaded from (set KG_BACKEND=neo4j or auto to
use a reachable Neo4j instead). Startup loads the embedding model once, which
takes 20-60 s on CPU; every request after that takes a few seconds.

Endpoints
    GET  /                 the demo page
    GET  /api/health       what is loaded
    GET  /api/sample       the sample tender text
    POST /api/analyze      {"text": "...", "top_k": 5}  -> analysis JSON
    POST /api/analyze-pdf  raw PDF bytes                -> analysis JSON (+ extracted text)
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

DEMO_DIR = Path(__file__).resolve().parent
REPO_ROOT = DEMO_DIR.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "Semantic_Analysis"))

SAMPLE = REPO_ROOT / "Semantic_Analysis" / "data" / "sample_tender.txt"
MAX_BODY = 25 * 1024 * 1024

_advisor = None
_lock = threading.Lock()          # the encoder is not re-entrant; one analysis at a time


class Handler(BaseHTTPRequestHandler):
    server_version = "IS-Advisor/1.0"

    def log_message(self, fmt, *args):  # quieter console: one line per request
        sys.stderr.write(f"  {self.command} {self.path} {args[1] if len(args) > 1 else ''}\n")

    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status: int, payload: dict) -> None:
        self._send(status, json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                   "application/json; charset=utf-8")

    def _body(self) -> bytes:
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_BODY:
            raise ValueError("file too large (25 MB limit)")
        return self.rfile.read(length)

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            self._send(200, (DEMO_DIR / "static" / "index.html").read_bytes(), "text/html; charset=utf-8")
        elif self.path == "/api/health":
            self._json(200, {"status": "ok", "kg_backend": type(_advisor.kg).__name__,
                             "dense_retrieval": _advisor.retriever.dense is not None,
                             "indexed_standards": len(_advisor.retriever.corpus)})
        elif self.path == "/api/sample":
            self._json(200, {"text": SAMPLE.read_text(encoding="utf-8")})
        else:
            self._json(404, {"error": "not found"})

    def do_POST(self):
        try:
            if self.path == "/api/analyze":
                payload = json.loads(self._body() or b"{}")
                text = (payload.get("text") or "").strip()
                if not text:
                    return self._json(400, {"error": "empty specification"})
                return self._json(200, self._analyze(text, payload.get("top_k")))
            if self.path == "/api/analyze-pdf":
                from is_advisor.documents import ScannedPdfError, read_document

                data = self._body()
                if not data.startswith(b"%PDF"):
                    return self._json(400, {"error": "not a PDF file"})
                with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as fh:
                    fh.write(data)
                    tmp = fh.name
                try:
                    text = read_document(Path(tmp))
                except ScannedPdfError as exc:
                    return self._json(422, {"error": f"scanned PDF: {exc}"})
                finally:
                    os.unlink(tmp)
                result = self._analyze(text, None)
                result["extracted_text"] = text
                return self._json(200, result)
            return self._json(404, {"error": "not found"})
        except Exception as exc:  # the page shows the message instead of hanging
            return self._json(500, {"error": f"{exc.__class__.__name__}: {exc}"})

    @staticmethod
    def _analyze(text: str, top_k) -> dict:
        with _lock:
            if top_k:
                _advisor.top_k = max(1, min(int(top_k), 10))
            start = time.time()
            result = _advisor.analyze(text)
            result["seconds"] = round(time.time() - start, 2)
            return result


def main() -> int:
    global _advisor
    parser = argparse.ArgumentParser(description="Run the IS-Advisor demo.")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--host", default="127.0.0.1")
    args = parser.parse_args()

    # Offline by default: a demo must not depend on venue Wi-Fi.
    os.environ.setdefault("KG_BACKEND", "local")
    print("Loading the index, embedding model and knowledge graph (20-60 s on CPU)...", flush=True)
    from demo.advisor import Advisor

    _advisor = Advisor()
    print(f"  knowledge graph: {type(_advisor.kg).__name__}")
    print(f"  dense retrieval: {'on' if _advisor.retriever.dense is not None else 'OFF (keyword only)'}")
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"Ready: http://localhost:{args.port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
