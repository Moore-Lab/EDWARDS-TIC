"""
tic_controller.py

Unified controller facade for the Edwards TIC.

Combines connection management, gauge reading, and pump control into a single
easy-to-use interface.  Prefer this class for scripts and higher-level code;
use the individual modules directly only when you need fine-grained access.

Date: 2026-04-16
"""

from __future__ import annotations

from typing import Optional

from tic_connection import TICConnection
from tic_gauges import TICGauges, GaugeStatus
from tic_pump import TICPump, PumpTelemetry


class TICController:
    """
    Unified interface to the Edwards TIC.

    Combines:
    - Connection management  (connect, disconnect)
    - Pressure gauges        (read_gauges, wrg_mbar, apgx_mbar)
    - Turbo pump             (start, stop, read_pump, is_pump_running)

    Example:
        tic = TICController("COM3")
        if tic.connect():
            gs = tic.read_gauges()
            print(f"WRG: {gs.wrg.value_mbar:.3e} mbar")
            tic.start_pump()
tel = tic.read_pump()
            print(tel)
            tic.stop_pump()
            tic.disconnect()

    Context manager:
        with TICController("COM3") as tic:
            print(tic.wrg_mbar())
    """

    def __init__(self, port: str = "COM3", baudrate: int = 9600,
                 timeout: float = 2.0):
        self._connection = TICConnection(port, baudrate, timeout)
        self._gauges: Optional[TICGauges] = None
        self._pump:   Optional[TICPump]   = None

    # =========================================================================
    # Properties
    # =========================================================================

    @property
    def is_connected(self) -> bool:
        return self._connection.is_connected

    @property
    def connection(self) -> TICConnection:
        return self._connection

    @property
    def gauges(self) -> Optional[TICGauges]:
        return self._gauges

    @property
    def pump(self) -> Optional[TICPump]:
        return self._pump

    @property
    def port(self) -> str:
        return self._connection.port

    # =========================================================================
    # Connection
    # =========================================================================

    def connect(self, port: Optional[str] = None,
                baudrate: Optional[int] = None) -> bool:
        """
        Open the serial connection to the TIC.

        Returns:
            True if connected successfully.
        """
        if self._connection.connect(port, baudrate):
            self._gauges = TICGauges(self._connection)
            self._pump   = TICPump(self._connection)
            return True
        return False

    def disconnect(self) -> None:
        """Close the serial connection."""
        self._connection.disconnect()
        self._gauges = None
        self._pump   = None

    # =========================================================================
    # Gauge interface
    # =========================================================================

    def read_gauges(self) -> GaugeStatus:
        """Read both pressure gauges and return a GaugeStatus."""
        if not self._gauges:
            raise RuntimeError("Not connected")
        return self._gauges.read_all()

    def wrg_mbar(self) -> Optional[float]:
        """Return wide-range gauge pressure in mbar, or None on error."""
        if not self._gauges:
            return None
        return self._gauges.wrg_mbar()

    def apgx_mbar(self) -> Optional[float]:
        """Return Pirani APGX gauge pressure in mbar, or None on error."""
        if not self._gauges:
            return None
        return self._gauges.apgx_mbar()

    # =========================================================================
    # Pump interface
    # =========================================================================

    def start_pump(self) -> bool:
        """Send the start command to the turbo pump."""
        if not self._pump:
            raise RuntimeError("Not connected")
        return self._pump.start()

    def stop_pump(self) -> bool:
        """Send the stop command to the turbo pump."""
        if not self._pump:
            raise RuntimeError("Not connected")
        return self._pump.stop()

    def read_pump(self) -> PumpTelemetry:
        """Poll all pump telemetry and return a PumpTelemetry object."""
        if not self._pump:
            raise RuntimeError("Not connected")
        return self._pump.read_telemetry()

    def is_pump_running(self) -> Optional[bool]:
        """Return True if the pump is spinning, None if the read fails."""
        if not self._pump:
            return None
        return self._pump.is_running()

    def pump_speed_pct(self) -> Optional[int]:
        """Return current pump speed in %, or None on error."""
        if not self._pump:
            return None
        return self._pump.speed_pct()

    # =========================================================================
    # Combined status
    # =========================================================================

    def get_status(self) -> dict:
        """Return a dict with complete instrument status."""
        status = {"connected": self.is_connected, "port": self.port}
        if self.is_connected:
            gs  = self.read_gauges()
            tel = self.read_pump()
            status["gauges"] = {
                "wrg_mbar":  gs.wrg.value_mbar,
                "apgx_mbar": gs.apgx.value_mbar,
                "wrg_error":  gs.wrg.error,
                "apgx_error": gs.apgx.error,
            }
            status["pump"] = {
                "running":    tel.is_running,
                "at_speed":   tel.at_speed,
                "status_str": tel.status_str,
                "speed_pct":  tel.speed_pct,
                "power_w":    tel.power_w,
                "errors":     tel.errors,
            }
        return status

    def print_status(self) -> None:
        """Print formatted instrument status."""
        s = self.get_status()
        print("\n" + "=" * 50)
        print("Edwards TIC Status")
        print("=" * 50)
        print(f"Connected : {s['connected']}  ({s['port']})")
        if s["connected"]:
            g = s["gauges"]
            print(f"\n--- Pressure Gauges ---")
            if g["wrg_mbar"] is not None:
                print(f"  WRG  : {g['wrg_mbar']:.3e} mbar")
            else:
                print(f"  WRG  : ERROR — {g['wrg_error']}")
            if g["apgx_mbar"] is not None:
                print(f"  APGX : {g['apgx_mbar']:.3e} mbar")
            else:
                print(f"  APGX : ERROR — {g['apgx_error']}")

            p = s["pump"]
            print(f"\n--- Turbo Pump ---")
            print(f"  Status  : {p['status_str']}")
            if p["speed_pct"] is not None:
                print(f"  Speed   : {p['speed_pct']}%")
            if p["power_w"] is not None:
                print(f"  Power   : {p['power_w']:.1f} W")
            if p["errors"]:
                print(f"  Errors  : {p['errors']}")
        print("=" * 50)

    # =========================================================================
    # Context manager
    # =========================================================================

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.disconnect()
        return False


# =============================================================================
# Standalone test
# =============================================================================

if __name__ == "__main__":
    import sys
    port = sys.argv[1] if len(sys.argv) > 1 else "COM3"

    tic = TICController(port)

    print(f"Connecting to Edwards TIC on {port}...")
    if tic.connect():
        tic.print_status()
        tic.disconnect()
    else:
        print("Connection failed — check port and cable.")
