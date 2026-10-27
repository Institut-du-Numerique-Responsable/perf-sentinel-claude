#!/usr/bin/env bash
# Builds a tiny git repository in the current directory: <fixture>/base on main,
# then <fixture>/change as one commit on a feature branch (when it exists).
# Usage: build.sh <fixture> [branch]
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
fixture=$1
branch=${2:-feature/PROJ-1234-client-contracts}

fx_git() { git -c user.name=fixture -c user.email=fixture@example.com -c commit.gpgsign=false "$@"; }

fx_git init -q -b main
cp -R "$here/$fixture/base/." .
fx_git add -A
fx_git commit -q -m "chore: initial import"
if [ -d "$here/$fixture/change" ]; then
  fx_git checkout -q -b "$branch"
  cp -R "$here/$fixture/change/." .
  fx_git add -A
  fx_git commit -q -m "feat: implement the change"
fi
