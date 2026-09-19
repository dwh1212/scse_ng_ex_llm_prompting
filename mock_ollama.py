"""Minimal fake Ollama server for end-to-end testing of investigate.py.
Serves POST /api/chat and returns scripted Qwen-like responses based on the
description contained in the request. Run on 127.0.0.1:11434.
"""
import json
from http.server import BaseHTTPRequestHandler, HTTPServer


def scripted_content(user_payload):
    """Return a realistic model response for the given user prompt text."""
    text = user_payload.get("content", "")
    # Match only the description line, not the embedded items JSON.
    marker = "Lost item description: "
    if marker in text:
        desc = text.split(marker, 1)[1].split("\n\n", 1)[0]
    else:
        desc = text
    low = desc.lower()
    if "unicorn" in low or "dinosaur" in low:
        return '{"matches": [], "confidence": "LOW"}'
    if "black bag" in low or "backpack" in low:
        return '{"matches": ["F101"], "confidence": "MEDIUM"}'
    if "laptop" in low or "charger" in low:
        return '{"matches": ["F104"], "confidence": "HIGH"}'
    if "water" in low or "bottle" in low:
        return '{"matches": ["F102"], "confidence": "MEDIUM"}'
    return '{"matches": ["F101", "F102"], "confidence": "LOW"}'


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_POST(self):
        if self.path != "/api/chat":
            self.send_response(404)
            self.end_headers()
            return
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length) or b"{}")
        last_user = ""
        for m in body.get("messages", []):
            if m.get("role") == "user":
                last_user = m.get("content", "")
        content = scripted_content({"content": last_user})
        resp = {
            "model": body.get("model", "qwen2.5:1.5b"),
            "created_at": "2026-09-18T00:00:00.000Z",
            "message": {"role": "assistant", "content": content},
            "done": True,
            "total_duration": 1,
            "load_duration": 1,
            "prompt_eval_count": 1,
            "eval_count": 1,
        }
        data = json.dumps(resp).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path == "/api/version":
            data = json.dumps({"version": "0.34.2"}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        else:
            self.send_response(404)
            self.end_headers()


if __name__ == "__main__":
    print("Fake Ollama listening on 127.0.0.1:11434", flush=True)
    HTTPServer(("127.0.0.1", 11434), Handler).serve_forever()
