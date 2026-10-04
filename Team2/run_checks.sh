#!/usr/bin/env bash
# Rerun every check behind Super Mona Kart, from the repository root:
#
#   Team2/run_checks.sh [OUT_DIR]        # screenshots go to OUT_DIR (default /tmp/smk-checks)
#
# Steps (each prints PASS, FAIL or SKIP; the script exits 1 if any FAIL):
#   1. logic tests (standard library only)
#   2. the repository's app and team validators
#   3. art regenerates byte-for-byte (needs Pillow; SKIP without it)
#   4. emulator: unmodified 2026 badge apps still run (fidelity check)
#   5. emulator: boot, Grand Prix menus and a race
#   6. emulator: physical switches only - back out, time trial, Up+Down pause
#   7. emulator: two badges race each other over UDP
# Steps 4-7 need the simulator from Team2/setup_simulator.sh (SKIP without it).

set -uo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."
OUT="${1:-/tmp/smk-checks}"
SIM="${BADGEWARE_SIMULATOR:-$HOME/badgeware-simulator}"
APP=Team2/super_mona_kart
FAILS=0
mkdir -p "$OUT"

result() {  # name, status
    printf '%-58s %s\n' "$1" "$2"
    [ "$2" = FAIL ] && FAILS=$((FAILS + 1))
    return 0
}

run() {  # name, command...
    local name="$1"; shift
    if "$@" > "$OUT/$(echo "$name" | tr ' /:' '___').log" 2>&1; then
        result "$name" PASS
    else
        result "$name" FAIL
        tail -15 "$OUT/$(echo "$name" | tr ' /:' '___').log" | sed 's/^/    /'
    fi
}

sim() {  # badgesim.py with this checkout's simulator
    BADGEWARE_SIMULATOR="$SIM" python3 Team2/badgesim.py "$@"
}

echo "Super Mona Kart checks (logs and screenshots in $OUT)"
echo

run "1 logic tests" python3 -m unittest Team2/test_super_mona_kart.py
run "2 app validator" python3 .github/skills/badge-app-builder/scripts/validate_app.py "$APP"
run "2 team validator" python3 .github/skills/badge-app-builder/scripts/validate_submissions.py Team2

if python3 -c "import PIL" 2>/dev/null; then
    python3 Team2/make_assets.py > "$OUT/3_assets.log" 2>&1
    if git diff --quiet -- "$APP/assets" "$APP/scenery.py"; then
        result "3 art regenerates identically" PASS
    else
        result "3 art regenerates identically" FAIL
        git diff --stat -- "$APP/assets" "$APP/scenery.py" | sed 's/^/    /'
        echo "    (if you changed art on purpose, commit the new files)"
    fi
else
    result "3 art regenerates identically (pip install pillow)" SKIP
fi

if [ ! -x "$SIM/build-pv3-headless/micropython" ]; then
    for n in "4 emulator: unmodified badge apps" "5 emulator: Grand Prix race" \
             "6 emulator: switches only, time trial, pause" "7 emulator: two-badge party race"; do
        result "$n (run Team2/setup_simulator.sh)" SKIP
    done
else
    for a in plucky_cluck tennis demos; do
        run "4 emulator: unmodified badge app $a" \
            sim "badge/apps/$a" --frames 240 --press 30-34:SELECT --shots 200 --out "$OUT/app_$a"
    done

    # title -> Grand Prix -> racer -> Normal -> intro -> countdown -> 4 s of racing
    run "5 emulator: Grand Prix race" sim "$APP" --frames 760 \
        --press 30-32:SELECT --press 60-62:SELECT --press 90-92:SELECT --press 120-122:SELECT \
        --press 520-560:RIGHT --press 600-660:BACK --press 600-660:LEFT \
        --shots 45,75,105,160,330,470,630,759 --out "$OUT/grand_prix"

    # Left backs out of the menu, Time Trial, a track, then hold Up+Down to pause
    run "6 emulator: switches only, time trial, pause" sim "$APP" --frames 700 \
        --press 20-22:SELECT --press 40-42:LEFT --press 60-62:SELECT --press 80-82:DOWN \
        --press 90-92:DOWN --press 100-102:SELECT --press 120-122:RIGHT --press 130-132:SELECT \
        --press 150-152:RIGHT --press 160-162:SELECT --press 470-472:SELECT \
        --press 520-560:UP --press 520-560:DOWN --shots 50,110,140,170,480,600 --out "$OUT/switches"

    # two badges on 127.0.0.1: both open Party; the host (lower id) starts
    party() {
        sim "$APP" --frames 1500 --realtime --port-offset "$1" \
            --press 30-32:SELECT --press 50-52:DOWN --press 56-58:DOWN --press 62-64:DOWN \
            --press 75-77:SELECT --press 260-262:SELECT --shots 200,330,560,1000 \
            --out "$OUT/party_$1" > "$OUT/7_party_$1.log" 2>&1
    }
    party 0 & P0=$!
    party 1 & P1=$!
    wait $P0; S0=$?
    wait $P1; S1=$?
    if [ $S0 -eq 0 ] && [ $S1 -eq 0 ] && grep -q "party: race" "$OUT/7_party_0.log" \
            && grep -q "party: race" "$OUT/7_party_1.log"; then
        result "7 emulator: two-badge party race" PASS
    else
        result "7 emulator: two-badge party race" FAIL
        tail -5 "$OUT/7_party_0.log" "$OUT/7_party_1.log" | sed 's/^/    /'
    fi
fi

echo
if [ $FAILS -eq 0 ]; then
    echo "All checks passed."
else
    echo "$FAILS check(s) failed."
    exit 1
fi
