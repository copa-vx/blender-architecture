#!/bin/sh
# Make the Python stubs of service/app/ from service/proto/chat.proto (a copy of
# docs/celaut/chat.proto of celaut-project/chatui). The stubs are not versioned: the
# Dockerfile makes them in a build stage, as Copa-ai/personal-nutrition does.
#
#   python3.11 -m venv .venv && .venv/bin/pip install -r service/requirements-dev.txt
#   PATH=$PWD/.venv/bin:$PATH sh service/gen_proto.sh [out_dir]
set -eu
here="$(cd "$(dirname "$0")" && pwd)"
out="${1:-$here/app}"
mkdir -p "$out"
python3 -m grpc_tools.protoc -I "$here/proto" --python_out="$out" --grpc_python_out="$out" "$here/proto/chat.proto"
# chat.proto has no package, so the stub imports its module by a bare name.
sed -i.bak 's/^import chat_pb2 as chat__pb2$/from . import chat_pb2 as chat__pb2/' "$out/chat_pb2_grpc.py"
rm -f "$out/chat_pb2_grpc.py.bak"
