#!/usr/bin/env python3
"""fill_sim — SCALE-L01-B bench prototype: hardware-in-the-loop fill simulator.

Deliverable 3 of Hugh's deep-research ask (weight-improvement-q-answers-003).
Simulates the three industrial pieces so SerialBackend + the two-stage fill
control loop can be developed before any industrial hardware is purchased:

  (a) continuous-output scale stream — HX711 + 5 kg load cell at ~10 Hz
      (Adafruit 5974 breakout + 4541 load cell), or a built-in synthetic
      fill profile when no hardware is attached (default);
  (b) on/off valve actuation — LED/relay on GPIO (HIGH=open), optional
      SG90 servo for partial-open dribble simulation;
  (c) e-stop — normally-closed pushbutton: circuit OPEN (button pressed
      OR wire broken) = STOP. Fail-safe by construction.

Protocol: SMA SCP-0499 standard frames (scalemanufacturers.org), chosen by
deep-research 2026-06-12 because motion/stability is in-band in every frame:

    <LF><s><r><n><m><f><xxxxxx.xxx><uuu><CR>
    weight field fixed 10 chars right-justified; unit 3 chars;
    <m> = 'M' while in motion, ' ' when settled.

SMA is host-polled: 'W' returns one frame, 'R' streams continuously.
Open question (research follow-up): add a Toledo-continuous framer too.

HX711 notes (verified): use hx711-rpi-py (endail) — compiled C++/lgpio
clocking; pure-Python bit-bang is unreliable because PD_SCK held high
>=60 us power-cycles the chip (Avia datasheet). On Debian trixie/py3.13
libhx711 + bindings need a from-source build; bench rig targets Pi 4-class.

Usage:
  python3 fill_sim.py                      # synthetic fill, stdio frames
  python3 fill_sim.py --pty                # create a pty for SerialBackend
  python3 fill_sim.py --hx711              # real HX711 on DOUT=5 SCK=6
  python3 fill_sim.py --target-kg 2.0      # bench-scale stand-in for 200 kg
"""

import argparse
import os
import sys
import time

# --- GPIO pins (BCM) --------------------------------------------------------
PIN_VALVE = 17      # LED/relay: HIGH = valve open
PIN_SERVO = 18      # optional SG90 dribble simulation
PIN_ESTOP = 27      # NC pushbutton to GND: LOW = ok, HIGH (open) = STOP
PIN_HX_DOUT = 5
PIN_HX_SCK = 6

KG_PER_S_COARSE = 0.080   # bench-scale synthetic rates (5 kg load cell world)
KG_PER_S_DRIBBLE = 0.005
DRIBBLE_OFFSET_KG = 0.150  # switch coarse->dribble this far before target
IN_FLIGHT_KG = 0.012       # synthetic material still falling after valve close
PREACT_KG = 0.010          # cut this far before target; must track IN_FLIGHT.
#   never-under spec: PREACT_KG < IN_FLIGHT_KG, so the fill lands just OVER
#   target. Real controller must LEARN preact from measured in-flight per fill
#   (first run of this stub used preact=0.010 with in-flight=0 and correctly
#   rejected itself UNDER — that failure mode is the whole point of preact).
SETTLE_S = 1.5

STATE_IDLE, STATE_COARSE, STATE_DRIBBLE, STATE_SETTLE, STATE_DONE, STATE_ESTOP = (
    "IDLE", "COARSE", "DRIBBLE", "SETTLE", "DONE", "ESTOP")


def sma_frame(kg: float, in_motion: bool) -> bytes:
    """SCP-0499: <LF><s><r><n><m><f><xxxxxx.xxx><uuu><CR>"""
    s = "Z" if abs(kg) < 0.0005 else " "   # center-of-zero
    r = " "                                # range 1
    n = " "                                # gross
    m = "M" if in_motion else " "
    f = " "
    w = f"{kg:10.3f}"                      # fixed 10 chars, right-justified
    return f"\n{s}{r}{n}{m}{f}{w}kg \r".encode("ascii")


class SyntheticScale:
    """Fill profile driven by the valve state the controller sets."""

    def __init__(self):
        self.kg = 0.0
        self.flow = 0.0      # kg/s, set via valve commands
        self.tail_kg = 0.0   # in-flight material still landing after cutoff
        self._last = time.monotonic()

    def set_flow(self, rate_kg_s: float) -> None:
        if rate_kg_s == 0.0 and self.flow > 0.0:
            self.tail_kg = IN_FLIGHT_KG   # valve closed: stream keeps falling
        self.flow = rate_kg_s

    def read_kg(self) -> float:
        now = time.monotonic()
        dt = now - self._last
        self.kg += self.flow * dt
        if self.flow == 0.0 and self.tail_kg > 0.0:
            drip = min(self.tail_kg, 0.010 * dt)
            self.kg += drip
            self.tail_kg -= drip
        self._last = now
        return self.kg


class Hx711Scale:
    """Real HX711 via hx711-rpi-py (build libhx711 from source on trixie)."""

    def __init__(self):
        from HX711 import SimpleHX711, Rate  # hx711-rpi-py
        # TODO: calibrate refUnit/offset with known masses (see README).
        self._hx = SimpleHX711(PIN_HX_DOUT, PIN_HX_SCK, -370, -367471)
        self._hx.setUnit("kg")

    def read_kg(self) -> float:
        return float(self._hx.weight(3))  # median of 3 (library default style)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--hx711", action="store_true", help="read real HX711")
    ap.add_argument("--pty", action="store_true", help="expose frames on a pty")
    ap.add_argument("--target-kg", type=float, default=2.0)
    ap.add_argument("--gpio", action="store_true", help="drive real GPIO pins")
    args = ap.parse_args()

    scale = Hx711Scale() if args.hx711 else SyntheticScale()

    valve = estop_pressed = None
    if args.gpio:
        from gpiozero import LED, Button
        valve = LED(PIN_VALVE)
        # NC to GND with pull-up: ok = pressed (held closed -> LOW).
        # Released button OR broken wire -> HIGH -> emergency stop.
        _btn = Button(PIN_ESTOP, pull_up=True)
        estop_pressed = lambda: not _btn.is_pressed  # noqa: E731
    else:
        estop_pressed = lambda: False  # noqa: E731

    out = sys.stdout.buffer
    if args.pty:
        master, slave = os.openpty()
        print(f"SerialBackend port: {os.ttyname(slave)}", file=sys.stderr)
        out = os.fdopen(master, "wb")

    def set_flow(rate_kg_s: float) -> None:
        if isinstance(scale, SyntheticScale):
            scale.set_flow(rate_kg_s)
        if valve is not None:
            valve.on() if rate_kg_s > 0 else valve.off()
        # TODO: SG90 partial-open angle for dribble when servo wired.

    state, target = STATE_IDLE, args.target_kg
    settle_until = 0.0
    last_kg = 0.0
    print(f"fill_sim: target {target} kg — starting COARSE", file=sys.stderr)
    state = STATE_COARSE
    set_flow(KG_PER_S_COARSE)

    while True:
        t0 = time.monotonic()
        kg = scale.read_kg()
        in_motion = abs(kg - last_kg) > 0.0005
        last_kg = kg

        if estop_pressed() and state not in (STATE_ESTOP,):
            state = STATE_ESTOP
            set_flow(0.0)
            print("E-STOP (circuit open) — valve closed", file=sys.stderr)
        elif state == STATE_COARSE and kg >= target - DRIBBLE_OFFSET_KG:
            state = STATE_DRIBBLE
            set_flow(KG_PER_S_DRIBBLE)
        elif state == STATE_DRIBBLE and kg >= target - PREACT_KG:
            state = STATE_SETTLE
            set_flow(0.0)
            settle_until = t0 + SETTLE_S
        elif state == STATE_SETTLE and t0 >= settle_until and not in_motion:
            state = STATE_DONE
            err = kg - target
            ok = 0.0 <= err  # never-under tolerance: err must be >= 0
            print(f"DONE: {kg:.3f} kg (err {err:+.3f}) "
                  f"{'OK' if ok else 'UNDER — REJECT'}", file=sys.stderr)

        out.write(sma_frame(kg, in_motion))
        out.flush()
        if state == STATE_DONE:
            return 0
        time.sleep(max(0.0, 0.1 - (time.monotonic() - t0)))  # ~10 Hz


if __name__ == "__main__":
    sys.exit(main())
