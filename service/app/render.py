"""Render a house with headless Blender: build_house.py of this repository, unchanged.

    blender --background --factory-startup -t <threads> --python build_house.py -- \
        house.json --out house.blend --render house.png --engine CYCLES ...

The microVM has no GPU and no display, so the engine is Cycles on the CPU (EEVEE and
Workbench need an OpenGL context). The progress comes from the "Sample n/m" lines that
Cycles prints.
"""

import os
import re
import subprocess
import threading
import time

SAMPLE = re.compile(r"Sample (\d+)/(\d+)")

#: name -> (width, height, samples)
QUALITY = {
    "draft": (640, 480, 8),
    "normal": (1024, 768, 24),
    "high": (1600, 1200, 64),
}


class RenderError(Exception):
    pass


class Renderer:
    def __init__(self, blender=None, script=None, work=None, threads=None, timeout=None, engine=None):
        env = os.environ.get
        self.blender = blender or env("BLENDER_BIN", "blender")
        self.script = script or env("BUILD_HOUSE", os.path.join(env("REPO_DIR", "/opt/blender-architecture"), "build_house.py"))
        self.work = work or env("WORK_DIR", "/work")
        self.threads = int(threads or env("RENDER_THREADS", "0"))  # 0: Blender uses every CPU
        self.timeout = float(timeout or env("RENDER_TIMEOUT_S", "1200"))
        self.engine = engine or env("RENDER_ENGINE", "CYCLES")
        self.count = 0
        self.lock = threading.Lock()

    def render(self, house_json, quality="normal", progress=None, cancelled=None):
        """Write the model, run Blender, return dict(png, blend, json, seconds, log).

        `progress(fraction, text)` gets the samples; `cancelled()` True kills Blender."""
        width, height, samples = QUALITY.get(quality, QUALITY["normal"])
        with self.lock:
            self.count += 1
            run = os.path.join(self.work, "render-%03d" % self.count)
        os.makedirs(run, exist_ok=True)
        paths = {k: os.path.join(run, "house." + k) for k in ("json", "blend", "png")}
        with open(paths["json"], "w", encoding="utf-8") as handle:
            handle.write(house_json)
        command = [self.blender, "--background", "--factory-startup"]
        if self.threads > 0:
            command += ["-t", str(self.threads)]
        command += ["--python", self.script, "--", paths["json"], "--out", paths["blend"],
                    "--render", paths["png"], "--engine", self.engine, "--samples", str(samples),
                    "--width", str(width), "--height", str(height)]
        started = time.monotonic()
        log = []
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                   stdin=subprocess.DEVNULL, text=True, errors="replace", cwd=run)
        stopper = threading.Event()

        def watch():  # the read loop blocks, so the time limit and the cancel are here
            while not stopper.wait(1.0):
                late = time.monotonic() - started > self.timeout
                if late or (cancelled and cancelled()):
                    log.append("[render] stopped: %s" % ("time limit" if late else "cancelled"))
                    process.kill()
                    return

        threading.Thread(target=watch, daemon=True).start()
        last = -1.0
        try:
            for line in process.stdout:
                line = line.rstrip()
                if line.startswith("[build_house]") or "Error" in line or "error" in line:
                    log.append(line)
                match = SAMPLE.search(line)
                if match and progress:
                    done, total = int(match.group(1)), max(1, int(match.group(2)))
                    fraction = 0.1 + 0.85 * done / total
                    if fraction - last >= 0.05 or done == total:
                        last = fraction
                        progress(fraction, "Sample %d/%d" % (done, total))
            code = process.wait()
        finally:
            stopper.set()
        seconds = time.monotonic() - started
        if cancelled and cancelled():
            raise RenderError("cancelled")
        if code != 0 or not os.path.exists(paths["png"]):
            tail = [l for l in log if not l.startswith("[build_house]   ")][-6:]
            raise RenderError("Blender ended with code %s. %s" % (code, " | ".join(tail)[-700:]))
        return dict(png=paths["png"], blend=paths["blend"], json=paths["json"],
                    seconds=seconds, log=log, width=width, height=height, samples=samples)

    def version(self):
        try:
            out = subprocess.run([self.blender, "--version"], capture_output=True, text=True, timeout=60)
            return (out.stdout.splitlines() or ["?"])[0].strip()
        except (OSError, subprocess.SubprocessError) as error:
            return "unavailable (%s)" % type(error).__name__
