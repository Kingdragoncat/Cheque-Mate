from __future__ import annotations

import io
import json
import mimetypes
import os
import re
import shutil
import socket
import subprocess
import sys
import tarfile
import threading
import time
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent
PROJECT_DIR = (
    _HERE / "Pygame-Template"
    if (_HERE / "Pygame-Template" / "src").is_dir()
    else _HERE
)
SRC_DIR = PROJECT_DIR / "src"
BUILD_WEB_DIR = PROJECT_DIR / "build" / "web"

WATCH_MAP: dict[str, Path] = {
    "assets/main.py": PROJECT_DIR / "main.py",
    "assets/src/factory_data.py": SRC_DIR / "factory_data.py",
    "assets/src/factory_sim.py": SRC_DIR / "factory_sim.py",
    "assets/src/factory_renderer.py": SRC_DIR / "factory_renderer.py",
    "assets/src/main.py": SRC_DIR / "main.py",
    "assets/assets/fonts/ui_bold.ttf": PROJECT_DIR / "assets" / "fonts" / "ui_bold.ttf",
    "assets/assets/forklift/spritesheet.png": PROJECT_DIR / "assets" / "forklift" / "spritesheet.png",
    "assets/assets/forklift/loading_corner.png": PROJECT_DIR / "assets" / "forklift" / "loading_corner.png",
    "assets/assets/intro/manor.png": PROJECT_DIR / "assets" / "intro" / "manor.png",
    "assets/assets/intro/facility_ext.png": PROJECT_DIR / "assets" / "intro" / "facility_ext.png",
    "assets/assets/intro/office_int.png": PROJECT_DIR / "assets" / "intro" / "office_int.png",
    "assets/assets/intro/car.png": PROJECT_DIR / "assets" / "intro" / "car.png",
    "assets/assets/music/lukrembo_affogato.ogg": PROJECT_DIR / "assets" / "music" / "lukrembo_affogato.ogg",
    "assets/assets/music/massobeats_peach_prosecco.ogg": PROJECT_DIR / "assets" / "music" / "massobeats_peach_prosecco.ogg",
}
TEMPLATE_PATH = PROJECT_DIR / "web_template.tmpl"

HOST = os.environ.get("LIVE_HOST", "0.0.0.0")
PORT = int(os.environ.get("LIVE_PORT", "8080"))

CLOUDFLARED_FALLBACK = Path(
    r"C:\Users\jonah\.gemini\antigravity\brain\bf454772-acd0-4c0b-acec-ed8200a76353\scratch\cloudflared.exe"
)
TRYCF_RE = re.compile(r"https://[a-zA-Z0-9-]+\.trycloudflare\.com")

EXTRA_MIME_TYPES = {
    ".wasm": "application/wasm",
    ".apk": "application/vnd.android.package-archive",
    ".gz": "application/gzip",
    ".js": "application/javascript; charset=utf-8",
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".json": "application/json",
    ".ttf": "font/ttf",
    ".ogg": "audio/ogg",
    ".mp3": "audio/mpeg",
}

LIVE_RELOAD_SNIPPET = """
<script>
(() => {
  let currentVer = null;
  async function checkLiveVersion() {
    try {
      const res = await fetch("/__live_version?t=" + Date.now(), { cache: "no-store" });
      if (!res.ok) return;
      const data = await res.json();
      if (currentVer === null) {
        currentVer = data.version;
      } else if (data.version !== currentVer && !data.last_error) {
        location.reload();
      }
    } catch (_) {}
  }
  setInterval(checkLiveVersion, 1000);
  checkLiveVersion();
})();
</script>
"""


def _snapshot_mtimes() -> dict[Path, float]:
    snap: dict[Path, float] = {}
    for p in WATCH_MAP.values():
        try:
            snap[p] = p.stat().st_mtime
        except FileNotFoundError:
            snap[p] = 0.0
    return snap


def _guess_mime(path: Path) -> str:
    ext = path.suffix.lower()
    if ext in EXTRA_MIME_TYPES:
        return EXTRA_MIME_TYPES[ext]
    guessed, _ = mimetypes.guess_type(path.name)
    return guessed or "application/octet-stream"


class WasmLiveHost:
    """Serves pygbag WebAssembly build and updates bundled Python files on save."""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.stop_event = threading.Event()
        self.version: int = 1
        self.last_error: str | None = None
        self._mtimes: dict[Path, float] = _snapshot_mtimes()
        self.apk_path = self._find_apk()

    def _find_apk(self) -> Path:
        apks = sorted(BUILD_WEB_DIR.glob("*.apk"))
        if apks:
            return apks[0]
        return BUILD_WEB_DIR / "pygame-template.apk"

    def ensure_build_exists(self) -> None:
        if not (BUILD_WEB_DIR / "index.html").is_file() or not self.apk_path.is_file():
            print("[live_server] build/web missing; running pygbag --build --archive ...", flush=True)
            cmd = [sys.executable, "-m", "pygbag", "--title", "Cheque Mate"]
            if TEMPLATE_PATH.is_file():
                cmd += ["--template", TEMPLATE_PATH.name]
            cmd += ["--build", "--archive", "main.py"]
            subprocess.check_call(cmd, cwd=str(PROJECT_DIR))
            self.apk_path = self._find_apk()
        self._sync_custom_index()
        self._refresh_archives()

    def _sync_custom_index(self) -> None:
        if not TEMPLATE_PATH.is_file():
            return
        idx_file = BUILD_WEB_DIR / "index.html"
        need_sync = not idx_file.is_file() or idx_file.stat().st_mtime < TEMPLATE_PATH.stat().st_mtime
        if not need_sync and idx_file.is_file():
            existing = idx_file.read_text(encoding="utf-8", errors="ignore")
            if "background: green" in existing or "shell.interactive()" in existing:
                need_sync = True
        if not need_sync:
            return
        raw = TEMPLATE_PATH.read_text(encoding="utf-8")
        raw = re.sub(r"\{%-?\s*if cookiecutter\.comment.*?\{%\s*endif\s*%\}", "", raw, flags=re.S)
        replacements = {
            "{{cookiecutter.cdn}}": "https://pygame-web.github.io/cdn/0.9.3/",
            "{{cookiecutter.PYBUILD}}": "3.12",
            "{{cookiecutter.title}}": "Cheque Mate",
            "{{cookiecutter.archive}}": "pygame-template",
            "{{cookiecutter.version}}": "0.9.3",
            "{{cookiecutter.width}}": "1280",
            "{{cookiecutter.height}}": "720",
            "{{cookiecutter.directory}}": "pygame-template",
            "{{cookiecutter.authors}}": "pgw",
            "{{cookiecutter.spdx}}": "cookiecutter.spdx",
            "{{cookiecutter.xtermjs}}": "0",
            "{{cookiecutter.ume_block}}": "1",
            "{{cookiecutter.can_close}}": "0",
            "{{cookiecutter.autorun}}": "0",
        }
        for k, v in replacements.items():
            raw = raw.replace(k, v)
        BUILD_WEB_DIR.mkdir(parents=True, exist_ok=True)
        idx_file.write_text(raw, encoding="utf-8")

    def _refresh_archives(self) -> bool:
        """Validate changed .py files and update both .apk (zip) and .tar.gz atomically."""
        for arc_name, src_path in WATCH_MAP.items():
            if not src_path.is_file() or src_path.suffix != ".py":
                continue
            try:
                source = src_path.read_text(encoding="utf-8")
                compile(source, str(src_path), "exec")
            except Exception as exc:
                self.last_error = f"{src_path.name}: {type(exc).__name__}: {exc}"
                print(f"[live_server] Syntax check skipped reload: {self.last_error}", flush=True)
                return False

        if not self.apk_path.is_file():
            return False

        tar_path = self.apk_path.with_suffix(".tar.gz")
        tmp_apk = self.apk_path.with_suffix(".apk.tmp")
        tmp_tar = self.apk_path.with_suffix(".tar.gz.tmp")
        now_sec = int(time.time())

        with self.lock:
            entries: list[tuple[str, bytes]] = []
            seen: set[str] = set()
            with zipfile.ZipFile(self.apk_path, "r") as zin:
                for info in zin.infolist():
                    arc = info.filename.replace("\\", "/")
                    seen.add(arc)
                    if arc in WATCH_MAP and WATCH_MAP[arc].is_file():
                        data = WATCH_MAP[arc].read_bytes()
                    else:
                        data = zin.read(info.filename)
                    entries.append((arc, data))

            for arc, src_path in WATCH_MAP.items():
                if arc not in seen and src_path.is_file():
                    entries.append((arc, src_path.read_bytes()))

            with zipfile.ZipFile(
                tmp_apk, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9
            ) as zout:
                for arc, data in entries:
                    zout.writestr(arc, data)

            with tarfile.open(tmp_tar, "w:gz") as tout:
                for arc, data in entries:
                    ti = tarfile.TarInfo(name=arc)
                    ti.size = len(data)
                    ti.mtime = now_sec
                    ti.mode = 0o644
                    tout.addfile(ti, io.BytesIO(data))

            os.replace(tmp_apk, self.apk_path)
            os.replace(tmp_tar, tar_path)

            music_src_dir = PROJECT_DIR / "assets" / "music"
            if music_src_dir.is_dir():
                music_dst_dir = BUILD_WEB_DIR / "assets" / "music"
                music_dst_dir.mkdir(parents=True, exist_ok=True)
                for track in music_src_dir.glob("*.ogg"):
                    shutil.copy2(track, music_dst_dir / track.name)

        self.last_error = None
        return True

    def watch_loop(self) -> None:
        while not self.stop_event.is_set():
            time.sleep(0.35)
            cur = _snapshot_mtimes()
            if cur != self._mtimes:
                self._mtimes = cur
                if self._refresh_archives():
                    self.version += 1
                    ts = time.strftime("%H:%M:%S")
                    print(
                        f"[live_server {ts}] Updated WASM bundle (v{self.version})",
                        flush=True,
                    )


def _make_handler(host_obj: WasmLiveHost) -> type[BaseHTTPRequestHandler]:
    web_root = BUILD_WEB_DIR.resolve()

    class WasmHandler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
            return

        def _send_bytes(self, status: int, content_type: str, data: bytes) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self) -> None:
            req_path = self.path.split("?", 1)[0]

            if req_path == "/__live_version":
                payload = json.dumps(
                    {"version": host_obj.version, "last_error": host_obj.last_error}
                ).encode("utf-8")
                self._send_bytes(200, "application/json", payload)
                return

            if req_path in ("/", "/index.html"):
                idx_file = BUILD_WEB_DIR / "index.html"
                html = idx_file.read_text(encoding="utf-8")
                if "</body>" in html:
                    html = html.replace("</body>", LIVE_RELOAD_SNIPPET + "\n</body>", 1)
                else:
                    html = html + LIVE_RELOAD_SNIPPET
                self._send_bytes(200, "text/html; charset=utf-8", html.encode("utf-8"))
                return

            if req_path == "/pygametemplate.apk":
                req_path = f"/{host_obj.apk_path.name}"

            rel = req_path.lstrip("/")
            if rel.startswith("assets/music/"):
                music_root = (PROJECT_DIR / "assets" / "music").resolve()
                music_target = (PROJECT_DIR / rel).resolve()
                if music_target.is_relative_to(music_root) and music_target.is_file():
                    self._send_bytes(200, _guess_mime(music_target), music_target.read_bytes())
                    return

            target = (BUILD_WEB_DIR / rel).resolve()
            if not target.is_relative_to(web_root) or not target.is_file():
                self._send_bytes(404, "text/plain; charset=utf-8", b"Not Found")
                return

            with host_obj.lock:
                data = target.read_bytes()
            self._send_bytes(200, _guess_mime(target), data)

    return WasmHandler


class QuietThreadingHTTPServer(ThreadingHTTPServer):
    allow_reuse_address = True
    daemon_threads = True

    def handle_error(self, request: Any, client_address: Any) -> None:
        return


def _discover_urls(port: int) -> list[str]:
    ips: list[str] = ["127.0.0.1"]
    try:
        for ip in socket.gethostbyname_ex(socket.gethostname())[2]:
            if (
                not ip.startswith("127.")
                and not ip.startswith("169.254.")
                and not ip.startswith("100.")
                and ip not in ips
            ):
                ips.append(ip)
    except OSError:
        pass
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            if not ip.startswith("100.") and ip not in ips:
                ips.append(ip)
    except OSError:
        pass
    return [f"http://{ip}:{port}" for ip in ips]


def _find_cloudflared() -> str | None:
    found = shutil.which("cloudflared")
    if found:
        return found
    for candidate in (CLOUDFLARED_FALLBACK, PROJECT_DIR / "cloudflared.exe"):
        if candidate.is_file():
            return str(candidate)
    return None


def _start_cloudflare_tunnel(port: int) -> tuple[subprocess.Popen[str] | None, str | None]:
    exe = _find_cloudflared()
    if not exe:
        return None, None

    proc = subprocess.Popen(
        [
            exe,
            "tunnel",
            "--url",
            f"http://127.0.0.1:{port}",
            "--protocol",
            "http2",
            "--no-autoupdate",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    url_holder: list[str] = []
    ready = threading.Event()

    def _drain() -> None:
        assert proc.stdout is not None
        for line in proc.stdout:
            m = TRYCF_RE.search(line)
            if m and not url_holder:
                url_holder.append(m.group(0))
                ready.set()

    threading.Thread(target=_drain, daemon=True).start()
    ready.wait(timeout=15.0)
    return proc, (url_holder[0] if url_holder else None)


def main() -> None:
    host_obj = WasmLiveHost()
    host_obj.ensure_build_exists()

    watcher = threading.Thread(target=host_obj.watch_loop, daemon=True)
    watcher.start()

    server = QuietThreadingHTTPServer((HOST, PORT), _make_handler(host_obj))
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()

    print("Cheque Mate WebAssembly Live Server running (60 FPS client-side)!", flush=True)
    for url in _discover_urls(PORT):
        print(f"  -> Local: {url}", flush=True)

    cf_proc, public_url = _start_cloudflare_tunnel(PORT)
    if public_url:
        print(f"  -> PUBLIC WEB URL (any PC, no Tailscale): {public_url}", flush=True)
    elif cf_proc is not None:
        print("  -> Cloudflare tunnel started (waiting for public URL)...", flush=True)

    try:
        while server_thread.is_alive():
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        host_obj.stop_event.set()
        if cf_proc is not None and cf_proc.poll() is None:
            cf_proc.terminate()
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    main()
