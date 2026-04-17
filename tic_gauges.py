"""
tic_gauges.py

Pressure gauge module for the Edwards TIC.

Reads Pirani (APGX) and wide-range (WRG) gauge pressures via the shared
TICConnection object.  All pressures are returned in mbar.

Parameter IDs
-------------
Verify these against your TIC manual (section "RS232 parameter list").
The TIC returns pressure values in Pascals; this module converts to mbar.

  913 — Gauge 1 / Wide-range gauge (WRG / Pirani+CCG)   input 1
  914 — Gauge 2 / Pirani-only gauge (APGX)               input 2

Date: 2026-04-16
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from tic_connection import TICConnection


# ---------------------------------------------------------------------------
# Parameter IDs — adjust to match your TIC wiring if different
# ---------------------------------------------------------------------------

PARAM_WRG  = 913   # Wide-range gauge  (input 1)
PARAM_APGX = 914   # Pirani APGX gauge (input 2)

# Pa → mbar conversion
_PA_TO_MBAR = 1.0 / 100.0


@dataclass
class GaugeReading:
    """Pressure reading from one gauge."""
    name:    str
    param:   int
    value_mbar: Optional[float] = None
    error:   Optional[str]      = None

    @property
    def ok(self) -> bool:
        return self.error is None and self.value_mbar is not None

    def __str__(self) -> str:
        if self.ok:
            return f"{self.name}: {self.value_mbar:.3e} mbar"
        return f"{self.name}: ERROR — {self.error}"


@dataclass
class GaugeStatus:
    """Combined reading from all gauges."""
    wrg:  GaugeReading = field(default_factory=lambda: GaugeReading("WRG",  PARAM_WRG))
    apgx: GaugeReading = field(default_factory=lambda: GaugeReading("APGX", PARAM_APGX))

    @property
    def all_ok(self) -> bool:
        return self.wrg.ok and self.apgx.ok

    def __str__(self) -> str:
        return f"{self.wrg}  |  {self.apgx}"


class TICGauges:
    """
    Reads pressure gauges from the Edwards TIC.

    Args:
        connection: Open TICConnection instance.

    Example:
        gauges = TICGauges(conn)
        status = gauges.read_all()
        print(status.wrg.value_mbar)
    """

    def __init__(self, connection: TICConnection):
        self._conn = connection

    # =========================================================================
    # Individual gauge reads
    # =========================================================================

    def read_wrg(self) -> GaugeReading:
        """Read the wide-range gauge (input 1). Returns value in mbar."""
        reading = GaugeReading("WRG", PARAM_WRG)
        try:
            pa = self._conn.query_float(PARAM_WRG)
            reading.value_mbar = pa * _PA_TO_MBAR
        except Exception as e:
            reading.error = str(e)
        return reading

    def read_apgx(self) -> GaugeReading:
        """Read the Pirani APGX gauge (input 2). Returns value in mbar."""
        reading = GaugeReading("APGX", PARAM_APGX)
        try:
            pa = self._conn.query_float(PARAM_APGX)
            reading.value_mbar = pa * _PA_TO_MBAR
        except Exception as e:
            reading.error = str(e)
        return reading

    # =========================================================================
    # Combined read
    # =========================================================================

    def read_all(self) -> GaugeStatus:
        """Read both gauges and return a GaugeStatus."""
        return GaugeStatus(
            wrg=self.read_wrg(),
            apgx=self.read_apgx(),
        )

    # =========================================================================
    # Convenience
    # =========================================================================

    def wrg_mbar(self) -> Optional[float]:
        """Return WRG pressure in mbar, or None on error."""
        r = self.read_wrg()
        return r.value_mbar if r.ok else None

    def apgx_mbar(self) -> Optional[float]:
        """Return APGX pressure in mbar, or None on error."""
        r = self.read_apgx()
        return r.value_mbar if r.ok else None


# =============================================================================
# Standalone test
# =============================================================================

if __name__ == "__main__":
    import sys
    port = sys.argv[1] if len(sys.argv) > 1 else "COM3"

    with TICConnection(port) as conn:
        gauges = TICGauges(conn)
        status = gauges.read_all()
        print(f"\nGauge readings:")
        print(f"  {status.wrg}")
        print(f"  {status.apgx}")
