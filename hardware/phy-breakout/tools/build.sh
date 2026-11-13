#!/bin/sh
# Rebuild everything from design.py and check it. Usage: tools/build.sh [path to KiCad.app]
# KiCad 8.0.9 is the version this was generated and checked with.
set -e
cd "$(dirname "$0")/.."
APP="${1:-/Applications/KiCad/KiCad.app}"
CLI="$APP/Contents/MacOS/kicad-cli"
PY="$APP/Contents/Frameworks/Python.framework/Versions/Current/bin/python3"
"$PY" tools/design.py
"$PY" tools/schematic.py
(cd tools && "$PY" pcb.py)
mkdir -p reports
"$CLI" sch erc --severity-all --exit-code-violations -o reports/erc.txt phy-breakout.kicad_sch
"$CLI" pcb drc --severity-all --schematic-parity --exit-code-violations -o reports/drc.txt phy-breakout.kicad_pcb
