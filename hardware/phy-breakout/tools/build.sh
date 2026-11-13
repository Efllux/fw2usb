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

# Fabrication outputs.
OUT=fab
rm -rf "$OUT"; mkdir -p "$OUT/gerbers" "$OUT/assembly"
"$CLI" pcb export gerbers -o "$OUT/gerbers/" \
  --layers F.Cu,In1.Cu,In2.Cu,B.Cu,F.Paste,B.Paste,F.SilkS,B.SilkS,F.Mask,B.Mask,Edge.Cuts \
  --subtract-soldermask phy-breakout.kicad_pcb
"$CLI" pcb export drill -o "$OUT/gerbers/" --format excellon --excellon-separate-th \
  --generate-map --map-format gerberx2 phy-breakout.kicad_pcb
"$CLI" pcb export pos --format csv --units mm --side both -o "$OUT/assembly/pick-and-place.csv" phy-breakout.kicad_pcb
cp BOM.csv "$OUT/assembly/BOM.csv"
"$CLI" pcb export svg --layers F.Fab,F.SilkS,Edge.Cuts --exclude-drawing-sheet --page-size-mode 2 \
  -o "$OUT/assembly/assembly-top.svg" phy-breakout.kicad_pcb
"$CLI" pcb export svg --layers B.Fab,B.SilkS,Edge.Cuts --mirror --exclude-drawing-sheet --page-size-mode 2 \
  -o "$OUT/assembly/assembly-bottom.svg" phy-breakout.kicad_pcb
