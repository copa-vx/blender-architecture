"""A minimal chat.md (revision 6) client for the e2e check of the service.

    python3 client/chat_client.py <host:port> "<turn 1>" ["<turn 2>" ...] [--out DIR]

It reads the capabilities, opens `Connect`, sends each turn over the stream (with an
`idempotency_key` and an `event_id`), waits until every answer of the turn is final (a
render has two: the streamed progress answer and the message with the files), downloads
the files with `DownloadFile`, checks their SHA3-256 hashes and writes them to DIR. At the
end it reads the history with `GetMessages` and checks that `sequence` has no gap. It
prints one line for each event that matters and a JSON summary on the last line.

Stubs: `service/gen_proto.sh` makes `service/app/chat_pb2*.py`.
"""

import argparse
import hashlib
import json
import os
import queue
import sys
import threading
import time
import uuid

import grpc

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "service"))
from app import chat_pb2 as pb  # noqa: E402
from app import chat_pb2_grpc as rpc  # noqa: E402

FINAL = (pb.MESSAGE_STATUS_COMPLETED, pb.MESSAGE_STATUS_FAILED, pb.MESSAGE_STATUS_CANCELLED)
SHA3 = hashlib.sha3_256(b"").digest()
T0 = time.monotonic()


def log(text):
    print("[%7.1f] %s" % (time.monotonic() - T0, text), flush=True)


def text_of(message):
    return "".join(p.text.text for p in message.content if p.WhichOneof("kind") == "text")


class Conversation:
    def __init__(self, address):
        self.channel = grpc.insecure_channel(address)
        self.chat = rpc.ChatServiceStub(self.channel)
        self.files = rpc.FileServiceStub(self.channel)
        self.messages = {}
        self.title = None
        self.progress = []
        self.events = queue.Queue()
        self.outgoing = queue.Queue()
        self.lock = threading.Lock()

    def wait_ready(self, timeout):
        deadline = time.monotonic() + timeout
        while True:
            try:
                return self.chat.GetCapabilities(pb.GetCapabilitiesRequest(), timeout=10)
            except grpc.RpcError as error:
                if time.monotonic() > deadline:
                    raise
                log("waiting for the service (%s)" % error.code().name)
                time.sleep(3)

    def connect(self):
        def requests():
            yield pb.ClientEvent(subscribe=pb.SubscribeRequest(after_sequence=0), event_id="sub")
            while True:
                item = self.outgoing.get()
                if item is None:
                    return
                yield item

        def read():
            try:
                for event in self.chat.Connect(requests()):
                    self._apply(event)
            except grpc.RpcError as error:
                log("stream ended: %s" % error.code().name)

        threading.Thread(target=read, daemon=True).start()

    def _apply(self, event):
        kind = event.WhichOneof("event")
        with self.lock:
            if kind == "message_created":
                m = event.message_created.message
                self.messages[m.message_id] = m
            elif kind == "message_delta":
                d = event.message_delta
                m = self.messages[d.message_id]
                if m.content and m.content[-1].WhichOneof("kind") == "text":
                    m.content[-1].text.text += d.text_append
                else:
                    m.content.add().text.text = d.text_append
            elif kind == "message_status_changed":
                c = event.message_status_changed
                m = self.messages[c.message_id]
                m.status = c.status
                if c.error:
                    m.error = c.error
                m.suggestions.extend(c.suggestions)
            elif kind == "message_progress":
                p = event.message_progress
                self.progress.append(round(p.progress, 2))
                if len(self.progress) % 4 == 1:
                    log("progress %.0f%% %s" % (100 * p.progress, p.description))
            elif kind == "conversation_title_changed":
                self.title = event.conversation_title_changed.title
                log("title: %s" % self.title)
            elif kind == "subscription_ready":
                self.title = event.subscription_ready.title or self.title
                log("subscribed (latest %d, title %r)" % (event.subscription_ready.latest_sequence, self.title))
            elif kind == "error":
                log("protocol error: %s %s" % (event.error.code, event.error.message))
        self.events.put(kind)

    def send(self, text):
        key = uuid.uuid4().hex[:16]
        self.outgoing.put(pb.ClientEvent(event_id="e" + key, send_message=pb.SendMessageRequest(
            content=[pb.ContentPart(text=pb.TextContent(text=text))], idempotency_key=key)))
        log("sent: %s" % text)
        return key

    def answers_to(self, key, timeout):
        """Wait until the answers of the user message of `key` are final: one answer, or two
        when the first one is a render."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            with self.lock:
                user = next((m for m in self.messages.values() if m.idempotency_key == key), None)
                if user:
                    answers = sorted((m for m in self.messages.values()
                                      if m.from_service and m.reply_to_message_id == user.message_id),
                                     key=lambda m: m.sequence)
                    if answers and all(a.status in FINAL for a in answers):
                        first = answers[0]
                        render = text_of(first).startswith(("Rendering", "Renderizando")) or "Rendering" in text_of(first)
                        if (not render or len(answers) >= 2 or first.status != pb.MESSAGE_STATUS_COMPLETED):
                            return [pb.Message.FromString(a.SerializeToString()) for a in answers]
            try:
                self.events.get(timeout=5)
            except queue.Empty:
                pass
        raise TimeoutError("no answer in %d s" % timeout)

    def download(self, ref, path):
        sha3 = next(h for h in ref.hashes if h.type == SHA3)
        data = b"".join(c.chunk for c in self.files.DownloadFile(pb.DownloadFileRequest(hash=sha3), timeout=120))
        assert len(data) == ref.size_bytes, (len(data), ref.size_bytes)
        assert hashlib.sha3_256(data).digest() == sha3.value, "hash mismatch"
        with open(path, "wb") as handle:
            handle.write(data)
        return len(data)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("address")
    parser.add_argument("turns", nargs="+")
    parser.add_argument("--out", default="out")
    parser.add_argument("--timeout", type=int, default=1800)
    args = parser.parse_args()
    os.makedirs(args.out, exist_ok=True)
    c = Conversation(args.address)
    caps = c.wait_ready(900)
    log("capabilities: accepted=%s max_file=%d cancel=%s" % (
        list(caps.accepted_mime_types), caps.max_file_bytes, caps.supports_cancel))
    c.connect()
    summary = {"turns": []}
    ok = True
    for turn in args.turns:
        t = time.monotonic()
        key = c.send(turn)
        answers = c.answers_to(key, args.timeout)
        item = {"sent": turn, "seconds": round(time.monotonic() - t, 1), "answers": []}
        for a in answers:
            status = pb.MessageStatus.Name(a.status)
            body = text_of(a)
            log("answer %d (%s):\n%s" % (a.sequence, status, body if len(body) < 1500 else body[:1500] + " [...]"))
            if a.suggestions:
                log("suggestions: %s" % list(a.suggestions))
            entry = {"sequence": a.sequence, "status": status, "suggestions": list(a.suggestions),
                     "chars": len(body), "keyboard": "```keyboard" in body, "widget": "```html" in body}
            if a.error:
                entry["error"] = a.error
                ok = False
            for part in a.content:
                kind = part.WhichOneof("kind")
                ref = getattr(part, kind).file if kind in ("image", "audio") else (part.file if kind == "file" else None)
                if ref is None:
                    continue
                name = "%03d-%s" % (a.sequence, ref.filename or ("%s.bin" % kind))
                size = c.download(ref, os.path.join(args.out, name))
                entry.setdefault("files", []).append({"kind": kind, "mime": ref.mime_type, "name": name, "bytes": size})
                log("downloaded %s %s %s (%d bytes, SHA3-256 ok)" % (kind, ref.mime_type, name, size))
            if a.metadata:
                entry["metadata"] = dict(a.metadata)
            item["answers"].append(entry)
            ok = ok and a.status == pb.MESSAGE_STATUS_COMPLETED
        summary["turns"].append(item)
    history = list(c.chat.GetMessages(pb.GetMessagesRequest(after_sequence=0), timeout=30))
    sequences = [m.sequence for m in history]
    summary["history"] = len(history)
    summary["sequence_ok"] = sequences == list(range(1, len(history) + 1))
    summary["title"] = c.title
    summary["progress_events"] = len(c.progress)
    c.outgoing.put(None)
    summary["ok"] = ok and summary["sequence_ok"]
    print(json.dumps(summary))
    return 0 if summary["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
