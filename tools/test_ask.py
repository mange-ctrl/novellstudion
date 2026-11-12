"""Testar ask-kommandot mot en lokal låtsasserver (Ollama + OpenAI-format)."""

import argparse
import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import cli  # noqa: E402

PORT = 11555


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length) or b"{}")
        if self.path == "/api/generate":
            assert "prompt" in body, "Ollama-anrop saknar prompt"
            payload = {"response": f"SVAR-OLLAMA modell={body.get('model')} prompt={len(body['prompt'])}"}
        elif self.path == "/v1/chat/completions":
            assert body["messages"][0]["role"] == "user"
            payload = {
                "choices": [
                    {"message": {"content": f"SVAR-OPENAI modell={body.get('model')} prompt={len(body['messages'][0]['content'])}"}}
                ]
            }
        else:
            self.send_error(404)
            return
        data = json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):
        pass


server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
threading.Thread(target=server.serve_forever, daemon=True).start()

base = f"http://127.0.0.1:{PORT}"
common = dict(
    db="out/stil.db", k=1, per_story=1, length=300,
    base_url=base, temperature=0.8, max_tokens=100,
    out_dir="out/test-ask", from_file=None, query="en scen vid en sjö",
)

for backend, model in (("ollama", "mock-modell"), ("openai", "mock-gpt")):
    args = argparse.Namespace(**common, backend=backend, model=model, api_key="testnyckel")
    print(f"\n=== {backend} ===")
    code = cli.cmd_ask(args)
    print("exit:", code)

print("\n=== FILER ===")
for f in sorted(Path("out/test-ask").glob("*.md")):
    print(f"  {f.name}: {f.read_text(encoding='utf-8').strip()[:80]}")

server.shutdown()
