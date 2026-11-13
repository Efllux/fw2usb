#!/bin/sh
# SPDX-License-Identifier: CERN-OHL-S-2.0
set -eu
exec python3 "$(dirname "$0")/run.py"
