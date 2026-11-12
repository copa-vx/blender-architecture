# Celaut service of blender-architecture: one microVM with headless Blender and the chat server
# (chat.md revision 6 of celaut-project/chatui) that drives it.
# The Dockerfile only builds the file system: CMD/ENTRYPOINT/EXPOSE/ENV are ignored by nodo; the start
# is service.json -> init.entry_path (/opt/blender-architecture/start.sh) and the port is service.json -> api.
# The COPY origins of the project start with "./": the packer rewrites them to service/... (docs/PACKING.md).

ARG DEBIAN_SNAPSHOT=20261004T000000Z

# --- Blender: the official linux-x64 build, checked by its sha256 (5.1, the series the repository was tested with) ---
# download.blender.org answers 403 to some clients, so a mirror is tried first; the checksum makes the source
# irrelevant. There is no official Linux arm64 build, so the service is linux/amd64 only.
FROM debian:bookworm-slim@sha256:88200866dfff7ea7f5cbcb6ec7c8a701889efe6fe859fe64d6990e4b07ea4171 AS blender
ARG DEBIAN_SNAPSHOT
RUN sed -i \
      -e "s|^URIs: http://deb.debian.org/debian\$|URIs: http://snapshot.debian.org/archive/debian/${DEBIAN_SNAPSHOT}|" \
      -e "s|^URIs: http://deb.debian.org/debian-security\$|URIs: http://snapshot.debian.org/archive/debian-security/${DEBIAN_SNAPSHOT}|" \
      -e '/^URIs: /a Check-Valid-Until: no' \
      /etc/apt/sources.list.d/debian.sources \
    && apt-get -o Acquire::Retries=5 update \
    && apt-get -o Acquire::Retries=5 install --no-install-recommends -y curl ca-certificates xz-utils \
    && rm -rf /var/lib/apt/lists/*
ARG BLENDER_VERSION=5.1.2
ARG BLENDER_SERIES=5.1
ARG BLENDER_SHA256=aaccb355f50183979b698bcce7467103a76261b5fa59f4972295842662a285fb
RUN f="blender-${BLENDER_VERSION}-linux-x64.tar.xz" \
    && for url in "https://mirrors.ocf.berkeley.edu/blender/release/Blender${BLENDER_SERIES}/$f" \
                  "https://download.blender.org/release/Blender${BLENDER_SERIES}/$f"; do \
         curl -fsSL --retry 5 -o /tmp/blender.tar.xz "$url" \
           && echo "${BLENDER_SHA256}  /tmp/blender.tar.xz" | sha256sum -c - && break; \
         rm -f /tmp/blender.tar.xz; \
       done \
    && test -s /tmp/blender.tar.xz \
    && mkdir /opt/blender && tar -xJf /tmp/blender.tar.xz --strip-components=1 -C /opt/blender \
    && rm /tmp/blender.tar.xz \
    # GPU kernels of Cycles (CUDA, HIP, oneAPI): the microVM has no GPU. The CPU kernels are in the binary.
    && rm -rf "/opt/blender/${BLENDER_SERIES}/scripts/addons_core/cycles/lib" \
    && rm -rf /opt/blender/${BLENDER_SERIES}/python/lib/python3*/test

# --- gRPC stubs of the chat: made here with grpcio-tools; the image only has grpcio and protobuf ---
FROM python:3.11-slim-bookworm@sha256:94a8fee35252d06ab75856f15f12c7bae67b10e8a6da93c7fded82b2610926cd AS stubs
RUN pip install --no-cache-dir grpcio-tools==1.76.0 protobuf==6.31.1
COPY ./service /src/service
RUN sed -i 's/\r$//' /src/service/gen_proto.sh && mkdir /stubs && sh /src/service/gen_proto.sh /stubs

# --- The image ---
FROM python:3.11-slim-bookworm@sha256:94a8fee35252d06ab75856f15f12c7bae67b10e8a6da93c7fded82b2610926cd
ARG DEBIAN_SNAPSHOT
# The X11/GL libraries that the official Blender binary links, also in --background mode.
RUN sed -i \
      -e "s|^URIs: http://deb.debian.org/debian\$|URIs: http://snapshot.debian.org/archive/debian/${DEBIAN_SNAPSHOT}|" \
      -e "s|^URIs: http://deb.debian.org/debian-security\$|URIs: http://snapshot.debian.org/archive/debian-security/${DEBIAN_SNAPSHOT}|" \
      -e '/^URIs: /a Check-Valid-Until: no' \
      /etc/apt/sources.list.d/debian.sources \
    && apt-get -o Acquire::Retries=5 update \
    && apt-get -o Acquire::Retries=5 install --no-install-recommends -y \
        libx11-6 libxi6 libxxf86vm1 libxfixes3 libxrender1 libxkbcommon0 libsm6 libice6 \
        libgl1 libegl1 libglx0 libwayland-client0 libwayland-cursor0 libwayland-egl1 libdecor-0-0 \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 10001 ba \
    && useradd --uid 10001 --gid 10001 --no-create-home --shell /usr/sbin/nologin ba
RUN pip install --no-cache-dir grpcio==1.76.0 protobuf==6.31.1
COPY --from=blender /opt/blender /opt/blender
RUN ln -s /opt/blender/blender /usr/local/bin/blender

# The repository: the parametric model, the generator, the headless builder and the examples.
COPY ./blender /opt/blender-architecture/blender
COPY ./build_house.py /opt/blender-architecture/build_house.py
COPY ./examples /opt/blender-architecture/examples
COPY ./service /opt/blender-architecture/service
COPY --from=stubs /stubs/ /opt/blender-architecture/service/app/
COPY ./service/start.sh /opt/blender-architecture/start.sh
RUN sed -i 's/\r$//' /opt/blender-architecture/start.sh \
    && chmod 0755 /opt/blender-architecture/start.sh \
    && find /opt/blender-architecture -name '__pycache__' -prune -exec rm -rf {} + \
    && chmod -R a+rX /opt/blender-architecture

# Smoke test at build time: Blender starts, the generator builds a house, Cycles (not a fallback engine)
# renders 1 sample; the chat server imports. A missing library fails the build here, not on the node.
RUN blender --background --factory-startup --python /opt/blender-architecture/build_house.py -- \
        /opt/blender-architecture/examples/small_house.json --render /tmp/smoke.png \
        --engine CYCLES --samples 1 --width 64 --height 48 > /tmp/smoke.log 2>&1 \
    || { tail -40 /tmp/smoke.log; exit 1; }; \
    test -s /tmp/smoke.png && grep -E "^\[build_house\] (rendering with CYCLES|wrote)" /tmp/smoke.log \
    && grep -q "rendering with CYCLES" /tmp/smoke.log \
    && rm -rf /tmp/smoke.png /tmp/smoke.log \
    && cd /opt/blender-architecture/service \
    && REPO_DIR=/opt/blender-architecture python3 -c "import sys; sys.path.insert(0, '/opt/blender-architecture'); import app.server, app.architect, app.main"
