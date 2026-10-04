#!/usr/bin/env bash
# Build the firmware-faithful Universe 2026 badge simulator used by Team2.
#
#   Team2/setup_simulator.sh [DEST]      # default DEST: ~/badgeware-simulator
#
# What it does, from pinned upstream commits so every teammate gets the same
# simulator:
#   1. clones pimoroni/badgeware-simulator and applies Team2/badgesim.patch
#      (PicoVector v3.1.0 build, 2026 keys, case lights, badge runtime stubs)
#   2. adds pimoroni/picovector-micropython v3.1.0, the version the badge
#      firmware pins (pimoroni/tufty2350 ci/micropython.sh)
#   3. vendors the firmware's own badgeware Python runtime and ROM fonts from
#      pimoroni/tufty2350 (tools/sync_runtime_2026.py, three asserted patches)
#   4. builds a windowed binary (build-pv3) and a headless one (build-pv3-headless)
#
# Needs git, cmake, a C/C++ compiler and Python 3. Tested on macOS (Apple
# silicon, Xcode command line tools). On Linux, install libxi-dev and
# libxcursor-dev first; the Linux build is untested.

set -euo pipefail

SIM_REPO=https://github.com/pimoroni/badgeware-simulator
SIM_COMMIT=fddeb7fc13cc98415ead50acee76b2d8c5d58c26
PV_REPO=https://github.com/pimoroni/picovector-micropython
PV_COMMIT=1338077eaaab2ca60bc91653f79f48996b34e469      # tag v3.1.0
TUFTY_REPO=https://github.com/pimoroni/tufty2350
TUFTY_COMMIT=ee84772fb7f7d5424e9593029caba815c6f89c80

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEST="${1:-$HOME/badgeware-simulator}"
JOBS="$(getconf _NPROCESSORS_ONLN 2>/dev/null || echo 4)"

step() { printf '\n==> %s\n' "$*"; }

if [ -e "$DEST" ]; then
    echo "error: $DEST already exists; remove it or pass another directory" >&2
    exit 1
fi

step "Cloning badgeware-simulator at ${SIM_COMMIT:0:7}"
git clone --quiet "$SIM_REPO" "$DEST"
git -C "$DEST" checkout --quiet "$SIM_COMMIT"
git -C "$DEST" submodule update --init --quiet
git -C "$DEST/lib/micropython" submodule update --init --quiet lib/micropython-lib lib/mbedtls

step "Applying Team2/badgesim.patch"
git -C "$DEST" apply --whitespace=nowarn "$HERE/badgesim.patch"
cp "$DEST/lib/micropython/lib/micropython-lib/python-stdlib/datetime/datetime.py" \
   "$DEST/runtime2026/stubs/datetime.py"

step "Adding picovector-micropython v3.1.0 (${PV_COMMIT:0:7})"
git clone --quiet "$PV_REPO" "$DEST/lib/picovector-micropython"
git -C "$DEST/lib/picovector-micropython" checkout --quiet "$PV_COMMIT"
git -C "$DEST/lib/picovector-micropython" submodule update --init --quiet

step "Vendoring the badge firmware runtime from tufty2350 (${TUFTY_COMMIT:0:7})"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
git clone --quiet "$TUFTY_REPO" "$TMP/tufty2350"
git -C "$TMP/tufty2350" checkout --quiet "$TUFTY_COMMIT"
python3 "$DEST/tools/sync_runtime_2026.py" "$TMP/tufty2350"

if [ "$(uname)" = "Darwin" ]; then
    export SDKROOT="$(xcrun --sdk macosx --show-sdk-path)"
fi

step "Building the windowed simulator (build-pv3)"
cmake -S "$DEST/micropython" -B "$DEST/build-pv3" > "$DEST/build-pv3.log" 2>&1
cmake --build "$DEST/build-pv3" -j"$JOBS" >> "$DEST/build-pv3.log" 2>&1 \
    || { tail -30 "$DEST/build-pv3.log"; exit 1; }

step "Building the headless simulator (build-pv3-headless)"
cmake -S "$DEST/micropython" -B "$DEST/build-pv3-headless" -DHEADLESS=TRUE > "$DEST/build-pv3-headless.log" 2>&1
cmake --build "$DEST/build-pv3-headless" -j"$JOBS" >> "$DEST/build-pv3-headless.log" 2>&1 \
    || { tail -30 "$DEST/build-pv3-headless.log"; exit 1; }

step "Done"
echo "Simulator ready in $DEST"
if [ "$DEST" != "$HOME/badgeware-simulator" ]; then
    echo "Tell badgesim.py where it is:  export BADGEWARE_SIMULATOR=$DEST"
fi
echo "Play:   python3 Team2/badgesim.py Team2/super_mona_kart --play"
echo "Checks: Team2/run_checks.sh"
