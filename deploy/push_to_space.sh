#!/usr/bin/env bash
# Publish the current git HEAD to a Hugging Face Space (Docker SDK).
#
#   deploy/push_to_space.sh https://huggingface.co/spaces/<user>/<space-name>
#
# Git will ask for your Hugging Face username and an access token (write scope) as the
# password. The Space needs a README.md with YAML front matter, so a copy of the repo is
# made with deploy/huggingface/SPACE_README.md as its README - your GitHub README is
# left untouched.
set -euo pipefail

SPACE_URL="${1:?usage: deploy/push_to_space.sh https://huggingface.co/spaces/<user>/<space-name>}"
REPO_ROOT="$(git rev-parse --show-toplevel)"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

git -C "$REPO_ROOT" archive HEAD | tar -x -C "$WORK"
cp "$REPO_ROOT/deploy/huggingface/SPACE_README.md" "$WORK/README.md"

cd "$WORK"
git init -q -b main
git add -A
git -c user.name="deploy" -c user.email="deploy@localhost" commit -q -m "Deploy $(git -C "$REPO_ROOT" rev-parse --short HEAD)"
git push --force "$SPACE_URL" main
echo "Pushed. The Space now rebuilds the Docker image - watch the 'Logs' tab."
