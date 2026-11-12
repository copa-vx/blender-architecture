"""Tests of the chat service with no Blender: a fake renderer writes the files.

    sh service/gen_proto.sh && python3 -m pytest service/tests -q

The gRPC tests talk to a real server on a free local port, over h2c.
"""

import hashlib
import json
import os
import sys
import time

import grpc
import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(REPO, "service"))
sys.path.insert(0, REPO)

from app import chat_pb2 as pb  # noqa: E402
from app import chat_pb2_grpc as rpc  # noqa: E402
from app.architect import Architect  # noqa: E402
from app.chat import Chat  # noqa: E402
from app.render import RenderError  # noqa: E402
from app.server import make_server  # noqa: E402
from blender.model import House  # noqa: E402

SHA3 = hashlib.sha3_256(b"").digest()
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


class FakeRenderer:
    def __init__(self, tmp, fail=False):
        self.tmp, self.fail, self.calls = tmp, fail, []

    def render(self, house_json, quality="normal", progress=None, cancelled=None):
        self.calls.append((json.loads(house_json), quality))
        if self.fail:
            raise RenderError("Blender ended with code 1")
        progress(0.5, "Sample 4/8")
        run = os.path.join(self.tmp, "r%d" % len(self.calls))
        os.makedirs(run)
        paths = {k: os.path.join(run, "house." + k) for k in ("json", "blend", "png")}
        open(paths["json"], "w").write(house_json)
        open(paths["blend"], "wb").write(b"BLENDER-v405" + b"\x01" * 100)
        open(paths["png"], "wb").write(PNG)
        return dict(png=paths["png"], blend=paths["blend"], json=paths["json"], seconds=1.5, log=[])


class FakeTurn:
    """The part of chat.Turn that the architect uses."""

    def __init__(self, text):
        self.user_text, self.text, self.title, self.posts, self.status = text, "", None, [], "open"
        self.suggestions = ()

    def write(self, text):
        self.text += text

    def set_title(self, title):
        self.title = title

    def finish(self, suggestions=()):
        self.status, self.suggestions = "completed", suggestions

    def fail(self, error):
        self.status, self.error = "failed", error

    def progress(self, *a):
        pass

    def cancelled(self):
        return False

    def check(self):
        pass

    def post(self, text, files=(), suggestions=(), metadata=None):
        self.posts.append((text, files, suggestions))


@pytest.fixture
def architect(tmp_path):
    return Architect(FakeRenderer(str(tmp_path)), examples_dir=os.path.join(REPO, "examples"))


def say(architect, text):
    turn = FakeTurn(text)
    architect.answer(turn)
    return turn


# -- the architect (no gRPC) --------------------------------------------------------


def test_help_has_widget_keyboard_and_suggestions(architect):
    turn = say(architect, "help")
    assert "Blender" in turn.text and "```html" in turn.text and "```keyboard" in turn.text
    assert turn.status == "completed" and len(turn.suggestions) == 3
    assert turn.title.startswith("House 10 x 8 m")


def test_readme_example_in_spanish(architect):
    turn = say(architect, "Crea una casa de 120 m², con dos plantas, tres dormitorios y un tejado a dos aguas")
    h = architect.house
    h.validate()
    assert len(h.floors) == 2 and abs(h.area - 120) < 0.5
    assert [r.name for r in h.floors[0].rooms] == ["salon", "cocina"]
    assert len(h.floors[1].rooms) == 3
    assert turn.text.startswith("Hecho:") and turn.title.startswith("Casa ")


def test_edits_in_english_and_undo(architect):
    say(architect, "12 x 9, pitch 40, style medieval, stone walls on, 8 trees, seed 4")
    h = architect.house
    assert (h.width, h.depth, h.roof.pitch, h.style, h.stone_walls, h.tree_count, h.seed) == \
        (12.0, 9.0, 40.0, "medieval", True, 8, 4)
    say(architect, "add a floor")
    assert len(architect.house.floors) == 2
    architect.house.validate()
    say(architect, "undo")
    assert len(architect.house.floors) == 1


def test_keyboard_apply_line_round_trips(architect):
    say(architect, "Width 14, depth 10, 3 floors, pitch 30, style modern, 0 trees, stone walls off, render")
    h = architect.house
    assert (h.width, h.depth, len(h.floors), h.roof.pitch, h.style, h.tree_count, h.stone_walls) == \
        (14.0, 10.0, 3, 30.0, "modern", 0, False)
    assert architect.renderer.calls[-1][1] == "normal"


def test_invalid_change_keeps_the_house(architect):
    before = architect.house.to_dict()
    turn = say(architect, "width 200")
    assert "cannot" in turn.text and architect.house.to_dict() == before
    turn = say(architect, "9 rooms")
    assert architect.house.to_dict() == before


def test_flat_roof_is_refused_honestly(architect):
    turn = say(architect, "flat roof please")
    assert "gable" in turn.text


def test_unknown_text_gets_help(architect):
    turn = say(architect, "qwerty zzz")
    assert "did not understand" in turn.text


def test_json_round_trip(architect):
    turn = say(architect, "json")
    raw = turn.text[turn.text.index("```json") + 7:turn.text.index("```", turn.text.index("```json") + 7)]
    house = House.from_json(raw)
    say(architect, "20 x 12")
    turn = say(architect, raw)
    assert "Loaded" in turn.text and architect.house.width == house.width


def test_examples_load_and_windows(architect):
    say(architect, "example medieval")
    assert architect.house.name == "medieval_house"
    n = sum(len(f.windows) for f in architect.house.floors)
    say(architect, "add a window")
    assert sum(len(f.windows) for f in architect.house.floors) == n + 1
    architect.house.validate()


def test_render_posts_three_files(architect):
    turn = say(architect, "render draft")
    assert turn.status == "completed" and "Rendered" in turn.text
    text, files, suggestions = turn.posts[0]
    assert [f[2] for f in files] == ["image/png", "application/json", "application/x-blender"]
    assert "```keyboard" in text and suggestions
    assert architect.renderer.calls[0][1] == "draft"


def test_render_failure_fails_the_answer(tmp_path):
    a = Architect(FakeRenderer(str(tmp_path), fail=True), examples_dir=os.path.join(REPO, "examples"))
    turn = say(a, "render")
    assert turn.status == "failed" and "code 1" in turn.error


# -- the gRPC interface ------------------------------------------------------------


@pytest.fixture
def stub(tmp_path):
    architect = Architect(FakeRenderer(str(tmp_path)), examples_dir=os.path.join(REPO, "examples"))
    chat = Chat(architect)
    chat.set_title(architect.title())
    server, port = make_server(chat, host="127.0.0.1", port=0)
    server.start()
    channel = grpc.insecure_channel("127.0.0.1:%d" % port)
    yield rpc.ChatServiceStub(channel), rpc.FileServiceStub(channel), chat
    channel.close()
    server.stop(0)
    chat.close()


def send(chat_stub, text, key=None):
    return chat_stub.SendMessage(pb.SendMessageRequest(
        content=[pb.ContentPart(text=pb.TextContent(text=text))], idempotency_key=key), timeout=10)


def wait_final(chat_stub, count, timeout=10):
    deadline = time.time() + timeout
    while time.time() < deadline:
        messages = list(chat_stub.GetMessages(pb.GetMessagesRequest(), timeout=10))
        if len(messages) >= count and all(m.status in (pb.MESSAGE_STATUS_COMPLETED, pb.MESSAGE_STATUS_FAILED)
                                          for m in messages):
            return messages
        time.sleep(0.05)
    raise AssertionError("not final: %s" % messages)


def test_grpc_capabilities_and_title(stub):
    chat_stub, _, _ = stub
    caps = chat_stub.GetCapabilities(pb.GetCapabilitiesRequest(), timeout=10)
    assert list(caps.accepted_mime_types) == [] and caps.supports_cancel and not caps.supports_fork
    conv = chat_stub.GetConversation(pb.GetConversationRequest(), timeout=10)
    assert conv.title.startswith("House")


def test_grpc_render_and_download(stub):
    chat_stub, file_stub, _ = stub
    user = send(chat_stub, "two floors and render", key="k1")
    assert user.sequence == 1 and user.idempotency_key == "k1"
    again = send(chat_stub, "two floors and render", key="k1")
    assert again.message_id == user.message_id
    messages = wait_final(chat_stub, 3)
    assert [m.sequence for m in messages] == [1, 2, 3]
    files = messages[2]
    assert files.reply_to_message_id == user.message_id and len(files.suggestions) == 3
    image = next(p.image.file for p in files.content if p.WhichOneof("kind") == "image")
    sha3 = next(h for h in image.hashes if h.type == SHA3)
    data = b"".join(c.chunk for c in file_stub.DownloadFile(pb.DownloadFileRequest(hash=sha3), timeout=10))
    assert data == PNG and hashlib.sha3_256(data).digest() == sha3.value
    found = list(file_stub.QueryFiles(iter([pb.QueryFilesRequest(hash=sha3)]), timeout=10))
    assert found[0].available


def test_grpc_attachment_is_unsupported_media(stub):
    chat_stub, _, _ = stub
    ref = pb.FileReference(hashes=[pb.Hash(type=SHA3, value=b"\x01" * 32)], mime_type="image/png", size_bytes=10)
    with pytest.raises(grpc.RpcError) as info:
        chat_stub.SendMessage(pb.SendMessageRequest(content=[pb.ContentPart(image=pb.ImageContent(file=ref))]),
                              timeout=10)
    assert info.value.code() == grpc.StatusCode.INVALID_ARGUMENT
    assert dict(info.value.trailing_metadata())["chat-reason"] == "unsupported_media"


def test_grpc_connect_streams_events(stub):
    chat_stub, _, _ = stub
    import queue
    out = queue.Queue()

    def requests():
        yield pb.ClientEvent(subscribe=pb.SubscribeRequest(after_sequence=0))
        yield pb.ClientEvent(event_id="e1", send_message=pb.SendMessageRequest(
            content=[pb.ContentPart(text=pb.TextContent(text="hello"))], idempotency_key="c1"))
        out.get()

    kinds = []
    for event in chat_stub.Connect(requests(), timeout=10):
        kind = event.WhichOneof("event")
        kinds.append(kind)
        if kind == "message_status_changed" and event.message_status_changed.status == pb.MESSAGE_STATUS_COMPLETED:
            out.put(None)
            break
    assert kinds[0] == "subscription_ready" and "message_created" in kinds and "message_delta" in kinds
