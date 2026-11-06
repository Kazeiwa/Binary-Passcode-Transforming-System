#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "$0")"
python_command="${BIP_PYTHON:-python3}"
if ! command -v "$python_command" >/dev/null 2>&1; then
  echo '未找到Python。请安装Python 3.11及以上，或用BIP_PYTHON指定解释器。' >&2
  exit 1
fi
if ! "$python_command" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)'; then
  echo '需要Python 3.11及以上，请升级Python或设置BIP_PYTHON。' >&2
  exit 1
fi
if [ "$#" -eq 0 ] || [ "$1" = 'gui' ]; then
  if ! "$python_command" -c 'import tkinter' >/dev/null 2>&1; then
    echo '缺少Tk。Debian/Ubuntu请安装python3-tk和python3-venv。' >&2
    exit 1
  fi
fi
if [ ! -x .venv/bin/python ]; then
  if ! "$python_command" -m venv .venv; then
    echo '无法创建虚拟环境。请安装对应版本venv组件并确认目录可写。' >&2
    exit 1
  fi
fi
if ! .venv/bin/python -m pip --version >/dev/null 2>&1; then
  echo '虚拟环境缺少pip，请安装Python的venv/ensurepip组件后重建.venv。' >&2
  exit 1
fi
if ! .venv/bin/python -c 'import PIL, numpy, cryptography, reedsolo' >/dev/null 2>&1; then
  echo '首次启动：正在安装运行依赖，请稍候…'
  .venv/bin/python -m pip install -r requirements.txt
fi
exec .venv/bin/python binary_image_passcode.py "$@"
