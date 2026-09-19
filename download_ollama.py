"""Concurrent chunked downloader for the Ollama installer.
Splits the remaining download into ~50MB pieces, uses fresh connections per
piece, and rotates through GitHub proxy mirrors to work around per-connection
bandwidth throttling. Restart-safe: resumes from existing part files.
"""
import os
import sys
import threading
import time
import queue

import httpx

TOTAL = 1569993232
N_CHUNKS = 8
CHUNK = (TOTAL + N_CHUNKS - 1) // N_CHUNKS
PREFIX = r"C:\Users\Lenovo\AppData\Local\Temp\OllamaSetup.exe"
CHUNK_DIR = r"C:\Users\Lenovo\AppData\Local\Temp\ollama_chunks"
PIECE = 50 * 1024 * 1024  # 50 MB per connection
MIRRORS = [
    "https://gh.ddlc.top",
    "https://gh-proxy.com",
    "https://ghproxy.net",
]
TARGET = "https://github.com/ollama/ollama/releases/download/v0.34.2/OllamaSetup.exe"

lock = threading.Lock()
done_chunks = set()
failed_chunks = set()
piece_count = [0]

os.makedirs(CHUNK_DIR, exist_ok=True)
P = os.path.getsize(PREFIX) if os.path.exists(PREFIX) else 0

# Single-instance lock: refuse to start if another downloader is running.
LOCK = os.path.join(CHUNK_DIR, ".downloader.lock")
try:
    fd = os.open(LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    os.write(fd, str(os.getpid()).encode())
    os.close(fd)
except FileExistsError:
    print("Another downloader instance is running (lock file exists). Exiting.", flush=True)
    sys.exit(2)


def chunk_range(k):
    start = k * CHUNK
    if k == 0:
        start = max(start, P)
    end = min(k * CHUNK + CHUNK - 1, TOTAL - 1)
    return start, end


def part_path(k):
    return os.path.join(CHUNK_DIR, "part_%02d.bin" % k)


def normalize_parts():
    """Truncate any part file that is larger than its expected size
    (can happen after a previous run with duplicate appends)."""
    for k in range(N_CHUNKS):
        start, end = chunk_range(k)
        expected = end - start + 1
        fpath = part_path(k)
        if os.path.exists(fpath) and os.path.getsize(fpath) > expected:
            with open(fpath, "r+b") as f:
                f.truncate(expected)
            print(f"normalized chunk {k} to {expected}", flush=True)


def download_piece(k, start, end, mirror):
    url = mirror + "/" + TARGET
    headers = {"Range": f"bytes={start}-{end}"}
    buf = bytearray()
    with httpx.Client(timeout=httpx.Timeout(60.0, connect=20.0)) as client:
        with client.stream("GET", url, headers=headers, follow_redirects=True) as r:
            r.raise_for_status()
            for chunk_b in r.iter_bytes(1024 * 256):
                buf.extend(chunk_b)
                if len(buf) > (end - start + 1) * 2:
                    raise RuntimeError("server sent too much data")
    data = bytes(buf)
    if len(data) != (end - start + 1):
        raise RuntimeError(f"short read {len(data)} != {end - start + 1}")
    return data


def download_chunk(k):
    start, end = chunk_range(k)
    total_len = end - start + 1
    fpath = part_path(k)
    while True:
        have = os.path.getsize(fpath) if os.path.exists(fpath) else 0
        if have >= total_len:
            break
        pstart = start + have
        pend = min(pstart + PIECE - 1, end)
        ok = False
        for attempt in range(5):
            mirror = MIRRORS[(k + attempt) % len(MIRRORS)]
            try:
                data = download_piece(k, pstart, pend, mirror)
                with open(fpath, "ab") as f:
                    f.write(data)
                ok = True
                with lock:
                    piece_count[0] += 1
                print(f"chunk {k}: +{len(data)} bytes (now {have + len(data)}/{total_len}) via {mirror}",
                      flush=True)
                break
            except Exception as e:
                print(f"chunk {k}: piece {pstart}-{pend} failed via {mirror} ({type(e).__name__}: {e})",
                      flush=True)
                time.sleep(2)
        if not ok:
            raise RuntimeError(f"chunk {k} piece {pstart}-{pend} failed after 5 attempts")


def worker(q):
    while True:
        try:
            k = q.get_nowait()
        except queue.Empty:
            return
        try:
            download_chunk(k)
            with lock:
                done_chunks.add(k)
            print(f"CHUNK {k} COMPLETE", flush=True)
        except Exception as e:
            with lock:
                failed_chunks.add(k)
            print(f"CHUNK {k} FAILED: {e}", flush=True)
        finally:
            q.task_done()


def main():
    normalize_parts()
    q = queue.Queue()
    for k in range(N_CHUNKS):
        q.put(k)
    threads = [threading.Thread(target=worker, args=(q,), daemon=True) for _ in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    print("=" * 60, flush=True)
    print(f"completed chunks: {sorted(done_chunks)}", flush=True)
    print(f"failed chunks: {sorted(failed_chunks)}", flush=True)
    try:
        os.remove(LOCK)
    except OSError:
        pass
    if failed_chunks:
        sys.exit(1)


if __name__ == "__main__":
    main()
