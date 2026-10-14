#!/bin/sh
set -eu
projects_directory=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$projects_directory"
if [ ! -x .venv/bin/python ]; then
  echo '请先按 README 创建本模块 .venv 并安装依赖。' >&2
  exit 1
fi
exec .venv/bin/python -m projects_service serve "$@"
