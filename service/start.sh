#!/bin/sh
# Entry point of the microVM (service.json -> init.entry_path). nodo does not apply the ENV of the image and
# the guest has no /etc/hosts, so both are set here. The chat server runs as an unprivileged user.
set -u
grep -qs "^127.0.0.1[[:space:]].*localhost" /etc/hosts || printf "127.0.0.1 localhost\n::1 localhost ip6-localhost\n" >> /etc/hosts
chmod 0644 /etc/hosts 2>/dev/null || true
mkdir -p /work /work/home && chown -R 10001:10001 /work && chmod 0700 /work
cd /opt/blender-architecture/service || exit 2
export REPO_DIR=/opt/blender-architecture WORK_DIR=/work HOME=/work/home PORT=50051 \
       BLENDER_BIN=/opt/blender/blender PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 \
       PATH=/usr/local/bin:/usr/bin:/bin LANG=C.UTF-8
exec setpriv --reuid 10001 --regid 10001 --clear-groups --no-new-privs /usr/local/bin/python3 -m app.main
