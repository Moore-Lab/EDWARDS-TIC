"""
tic_pump.py

Turbo pump control module for the Edwards TIC.

Reads pump telemetry (speed, power, current, voltage, temperature) and
sends start/stop/speed-setpoint commands via the shared TICConnection object.

Parameter IDs
-------------
These cover the standard Edwards EXT turbo pump controller built into the TIC.
Verify against your TIC manual (section "RS232 parameter list") — the exact
object numbers depend on the firmware version and attached pump model.

  READ parameters
  ---------------
  904 — Pump state          (0–7, see PumpState; also used for start/stop)
  905 — Pump speed          (%, 0.0–110.0)
  906 — Pump power          (W)

  WRITE parameters
  ----------------
  904 — Start / Stop        (!C904 1 = start, !C904 0 = stop)

Date: 2026-04-16
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from typing import Optional

from tic_connection import TICConnection


# ---------------------------------------------------------------------------
# Parameter IDs
# ---------------------------------------------------------------------------

PARAM_STATE = 904   # Turbo pump state (?V) and start/stop (!C 1/0)
PARAM_SPEED = 905   # Turbo speed, % of full speed
PARAM_POWER = 906   # Turbo power, W


# ---------------------------------------------------------------------------
# Pump state (discrete values returned by ?V904)
# ---------------------------------------------------------------------------

class PumpState(IntEnum):
    """Discrete pump states returned in the first field of ?V904."""
    STOPPED          = 0
    STARTING_DELAY   = 1
    STOPPING_SHORT   = 2
    STOPPING_NORMAL  = 3
    RUNNING          = 4
    ACCELERATING     = 5
    FAULT_BRAKING    = 6
    BRAKING          = 7


_STATE_NAMES = {
    PumpState.STOPPED:         "Stopped",
    PumpState.STARTING_DELAY:  "Starting",
    PumpState.STOPPING_SHORT:  "Stopping",
    PumpState.STOPPING_NORMAL: "Stopping",
    PumpState.RUNNING:         "Running",
    PumpState.ACCELERATING:    "Accelerating",
    PumpState.FAULT_BRAKING:   "FAULT",
    PumpState.BRAKING:         "Braking",
}


@dataclass
class PumpTelemetry:
    """All pump readings from a single poll."""
    state:     Optional[int]   = None   # PumpState value (0–7) from ?V904
    speed_pct: Optional[float] = None   # % of full speed from ?V905
    power_w:   Optional[float] = None   # Watts from ?V906
    errors:    dict = None

    def __post_init__(self):
        if self.errors is None:
            self.errors = {}

    @property
    def is_running(self) -> bool:
        return self.state in (PumpState.STARTING_DELAY,
                              PumpState.RUNNING,
                              PumpState.ACCELERATING)

    @property
    def at_speed(self) -> bool:
        return self.state == PumpState.RUNNING

    @property
    def has_fault(self) -> bool:
        return self.state == PumpState.FAULT_BRAKING

    @property
    def status_str(self) -> str:
        if self.state is None:
            return "Unknown"
        try:
            return _STATE_NAMES[PumpState(self.state)]
        except (ValueError, KeyError):
            return f"State {self.state}"

    def __str__(self) -> str:
        parts = [f"Status: {self.status_str}"]
        if self.speed_pct is not None:
            parts.append(f"Speed: {self.speed_pct:.1f}%")
        if self.power_w is not None:
            parts.append(f"Power: {self.power_w:.1f} W")
        return "  |  ".join(parts)


class TICPump:
    """
    Controls and monitors the turbo pump via the Edwards TIC.

    Args:
        connection: Open TICConnection instance.

    Example:
        pump = TICPump(conn)
        pump.start()
        tel = pump.read_telemetry()
        print(tel.speed_pct)
        pump.stop()
    """

    def __init__(self, connection: TICConnection):
        self._conn = connection

    # =========================================================================
    # Pump commands
    # =========================================================================

    def start(self) -> bool:
        """Send the start command to the turbo pump."""
        ok = self._conn.write_param(PARAM_STATE, 1)
        if ok:
            print("Turbo pump start command sent")
        return ok

    def stop(self) -> bool:
        """Send the stop command to the turbo pump."""
        ok = self._conn.write_param(PARAM_STATE, 0)
        if ok:
            print("Turbo pump stop command sent")
        return ok

    # =========================================================================
    # Pump telemetry
    # =========================================================================

    def read_telemetry(self) -> PumpTelemetry:
        """
        Poll all available pump parameters and return a PumpTelemetry object.

        Parameters that cannot be read are left as None; errors are collected
        in telemetry.errors rather than propagated.
        """
        tel = PumpTelemetry()

        params = [
            (PARAM_STATE, "state"),
            (PARAM_SPEED, "speed"),
            (PARAM_POWER, "power"),
        ]

        for param_id, key in params:
            try:
                raw = self._conn.query_float(param_id)
                if key == "state":
                    tel.state     = int(raw)
                elif key == "speed":
                    tel.speed_pct = raw
                elif key == "power":
                    tel.power_w   = raw
            except Exception as e:
                tel.errors[key] = str(e)

        return tel

    def is_running(self) -> Optional[bool]:
        """Return True if the pump is currently running, None on read error."""
        try:
            state = self._conn.query_int(PARAM_STATE)
            return state in (PumpState.STARTING_DELAY,
                             PumpState.RUNNING,
                             PumpState.ACCELERATING)
        except Exception:
            return None

    def speed_pct(self) -> Optional[float]:
        """Return current pump speed in %, or None on error."""
        try:
            return self._conn.query_float(PARAM_SPEED)
        except Exception:
            return None


# =============================================================================
# Standalone test
# =============================================================================

if __name__ == "__main__":
    import sys
    port = sys.argv[1] if len(sys.argv) > 1 else "COM3"

    with TICConnection(port) as conn:
        pump = TICPump(conn)
        tel = pump.read_telemetry()
        print(f"\nPump telemetry:")
        print(f"  {tel}")
        if tel.errors:
            print(f"  Read errors: {tel.errors}")
