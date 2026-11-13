"""blender-architecture as a Celaut service: the chat interface of chatui (chat.md revision 6)
on the port of the slot; the answers change the parametric house and render it in Blender.

Run as `python3 -m app.main` from the directory that holds `app/`, with the repository root
(`blender/`, `build_house.py`, `examples/`) on PYTHONPATH (REPO_DIR).
"""

import logging
import os
import signal
import sys
import threading

sys.path.insert(0, os.environ.get("REPO_DIR", "/opt/blender-architecture"))

from .architect import Architect  # noqa: E402
from .chat import Chat  # noqa: E402
from .render import Renderer  # noqa: E402
from .server import make_server  # noqa: E402


def main():
    logging.basicConfig(level=logging.INFO, stream=sys.stderr,
                        format="%(asctime)s %(name)s %(levelname)s %(message)s")
    renderer = Renderer()
    os.makedirs(renderer.work, exist_ok=True)
    architect = Architect(renderer)
    chat = Chat(architect)
    chat.set_title(architect.title())
    server, port = make_server(chat, port=int(os.environ.get("PORT", "50051")))
    server.start()
    logging.info("blender-architecture: chat gRPC on port %d; %s; engine %s",
                 port, renderer.version(), renderer.engine)

    done = threading.Event()

    def stop(signum, frame):
        logging.info("signal %d: stop", signum)
        server.stop(5)
        done.set()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    done.wait()


if __name__ == "__main__":
    main()
