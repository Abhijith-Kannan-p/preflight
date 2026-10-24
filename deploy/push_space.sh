#!/usr/bin/env bash
# Publish the backend to a Hugging Face Docker Space.
#
#   HF_TOKEN=hf_xxx ./deploy/push_space.sh kabhijith/preflight-api
#   DRY_RUN=1 ./deploy/push_space.sh kabhijith/preflight-api   # assemble only, print the folder
#
# Builds a clean Space repo (Dockerfile + README at the root, plus backend/ and data/) in a
# temporary folder and force-pushes it to the Space. The token needs "write" access; it is
# only used for this push and is never stored in the repository. Only committed files are
# included, so commit first.
set -euo pipefail

SPACE="${1:?usage: HF_TOKEN=... deploy/push_space.sh <user>/<space>}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
WORK="$(mktemp -d)"
if [ -z "${DRY_RUN:-}" ]; then
  : "${HF_TOKEN:?set HF_TOKEN to a Hugging Face write token}"
  trap 'rm -rf "$WORK"' EXIT
fi

cp "$ROOT/deploy/hf-space/Dockerfile" "$ROOT/deploy/hf-space/README.md" "$WORK/"
mkdir -p "$WORK/backend" "$WORK/data"
# Code and seed data only: no virtualenv, caches, tests or local secrets.
(cd "$ROOT/backend" && git ls-files -z -- . ':!tests' | xargs -0 -I{} cp --parents {} "$WORK/backend/")
(cd "$ROOT/data" && git ls-files -z | xargs -0 -I{} cp --parents {} "$WORK/data/")

if [ -n "${DRY_RUN:-}" ]; then
  echo "$WORK"
  exit 0
fi

cd "$WORK"
git init -q -b main
git lfs install --local >/dev/null 2>&1 || true
printf '*.pdf filter=lfs diff=lfs merge=lfs -text\n*.docx filter=lfs diff=lfs merge=lfs -text\n' > .gitattributes
git add -A
git -c user.name="preflight-deploy" -c user.email="deploy@preflight.invalid" \
  commit -q -m "Deploy Preflight backend from $(git -C "$ROOT" rev-parse --short HEAD)"
git push -q --force "https://user:${HF_TOKEN}@huggingface.co/spaces/${SPACE}" main
echo "Pushed to https://huggingface.co/spaces/${SPACE} - the build log is on the Space page."
