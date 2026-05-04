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
  904 — Pump speed          (integer, % of full speed)
  905 — Pump power          (W)
  906 — Pump current        (A)
  907 — Pump voltage        (V)
  908 — Pump temperature    (°C)
  909 — Pump state enum     (0=stopped, 2=running, 6=at-speed — NOT a bitmask)

  WRITE parameters
  ----------------
  910 — Start / Stop        (1 = start, 0 = stop)
  904 — Normal-speed target (integer, % of full speed; 0 resets to full)

Note on pump state vs. bitmask
-------------------------------
The TIC returns a state-machine integer from parameter 909, not a bitmask.
Running state is therefore derived from pump speed (parameter 904) rather
than from status bits: speed > 0 means the pump is spinning.

Date: 2026-04-16
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from tic_connection import TICConnection


# ---------------------------------------------------------------------------
# Parameter IDs
# ---------------------------------------------------------------------------

PARAM_SPEED       = 904
PARAM_POWER       = 905
PARAM_CURRENT     = 906
PARAM_VOLTAGE     = 907
PARAM_TEMPERATURE = 908
PARAM_STATUS      = 909
PARAM_START_STOP  = 910


@dataclass
class PumpTelemetry:
    """All pump readings from a single poll."""
    speed_pct:   Optional[int]   = None   # % of full speed
    power_w:     Optional[float] = None   # Watts
    current_a:   Optional[float] = None   # Amperes
    voltage_v:   Optional[float] = None   # Volts
    temp_c:      Optional[float] = None   # °C
    state_raw:   Optional[int]   = None   # raw state enum from parameter 909
    errors:      dict = None

    def __post_init__(self):
        if self.errors is None:
            self.errors = {}

    @property
    def is_running(self) -> bool:
        """True if the pump is spinning — derived from speed, not status bits."""
        if self.speed_pct is not None:
            return self.speed_pct > 0
        return False

    @property
    def at_speed(self) -> bool:
        """True if the pump is at or very near full speed (≥ 95 %)."""
        if self.speed_pct is not None:
            return self.speed_pct >= 95
        return False

    @property
    def has_fault(self) -> bool:
        return False   # fault detection requires model-specific state decoding

    @property
    def status_str(self) -> str:
        if self.speed_pct is None:
            return "Unknown"
        if self.speed_pct == 0:
            return "Stopped"
        if self.at_speed:
            return "At Speed"
        return f"Running ({self.speed_pct} %)"

    def __str__(self) -> str:
        parts = [f"Status: {self.status_str}"]
        if self.speed_pct is not None:
            parts.append(f"Speed: {self.speed_pct}%")
        if self.power_w is not None:
            parts.append(f"Power: {self.power_w:.1f} W")
        if self.current_a is not None:
            parts.append(f"Current: {self.current_a:.2f} A")
        if self.voltage_v is not None:
            parts.append(f"Voltage: {self.voltage_v:.1f} V")
        if self.temp_c is not None:
            parts.append(f"Temp: {self.temp_c:.1f} °C")
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
        self._conn.write_param(PARAM_START_STOP, 1)   # raises IOError on TIC rejection
        return True

    def stop(self) -> bool:
        """Send the stop command to the turbo pump."""
        self._conn.write_param(PARAM_START_STOP, 0)   # raises IOError on TIC rejection
        return True

    def set_speed(self, percent: int) -> bool:
        """
        Set the pump normal-speed target.

        Args:
            percent: Target speed as a percentage of full speed (0–100).
                     0 resets the TIC to its default (full speed).

        Returns:
            True if acknowledged by TIC.
        """
        percent = max(0, min(100, int(percent)))
        ok = self._conn.write_param(PARAM_SPEED, percent)
        if ok:
            print(f"Pump speed setpoint set to {percent}%")
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
            (PARAM_SPEED,       "speed"),
            (PARAM_POWER,       "power"),
            (PARAM_CURRENT,     "current"),
            (PARAM_VOLTAGE,     "voltage"),
            (PARAM_TEMPERATURE, "temp"),
            (PARAM_STATUS,      "state"),
        ]

        for param_id, key in params:
            try:
                raw = self._conn.query_float(param_id)
                if key == "speed":
                    tel.speed_pct  = int(raw)
                elif key == "power":
                    tel.power_w    = raw
                elif key == "current":
                    tel.current_a  = raw
                elif key == "voltage":
                    tel.voltage_v  = raw
                elif key == "temp":
                    tel.temp_c     = raw
                elif key == "state":
                    tel.state_raw  = int(raw)
            except Exception as e:
                tel.errors[key] = str(e)

        return tel

    def is_running(self) -> Optional[bool]:
        """Return True if the pump is spinning (speed > 0), None on read error."""
        try:
            return int(self._conn.query_float(PARAM_SPEED)) > 0
        except Exception:
            return None

    def speed_pct(self) -> Optional[int]:
        """Return current pump speed in %, or None on error."""
        try:
            return int(self._conn.query_float(PARAM_SPEED))
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
