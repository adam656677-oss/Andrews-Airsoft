#!/usr/bin/env bash
# Build the whole environment set (materials -> architecture -> props), with
# renders and lineups. Usage: build_all.sh [4096|2048|1024]
# PYTHON: a python with bpy (or use: blender -b -P <script> -- ...).
set -euo pipefail
PY=${PYTHON:-python}
RES=${1:-4096}
cd "$(dirname "$0")"
"$PY" materials.py --res "$RES"
"$PY" architecture.py --res "$RES"
"$PY" props.py --res "$RES"
