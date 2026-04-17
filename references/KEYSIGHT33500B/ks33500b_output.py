"""
Keysight 33500B Waveform Generator - Output Control Module

This module handles output configuration for the Keysight 33500B series
waveform generators. It provides methods to enable/disable outputs,
configure load impedance, polarity, and sync signal settings.

Date: 2026-04-16
"""

from typing import Optional
from enum import Enum


class OutputPolarity(Enum):
    """Output polarity options."""
    NORMAL = "NORMal"
    INVERTED = "INVerted"


class SyncPolarity(Enum):
    """Sync signal polarity options."""
    NORMAL = "NORMal"
    INVERTED = "INVerted"


class KS33500BOutput:
    """
    Handles output configuration for Keysight 33500B.

    This class provides methods to:
    - Enable / disable channel outputs
    - Configure load impedance (1 Ω – 10 kΩ or High-Z)
    - Set output polarity (normal / inverted)
    - Configure the sync output signal
    - Set trigger output slope
    """

    MIN_IMPEDANCE = 1      # 1 Ω
    MAX_IMPEDANCE = 10000  # 10 kΩ
    HIGH_Z = float('inf')

    def __init__(self, connection):
        """
        Initialize output controller.

        Args:
            connection: KS33500BConnection instance for communication.
        """
        self._conn = connection

    # =========================================================================
    # Output Enable / Disable
    # =========================================================================

    def enable(self, channel: int = 1) -> bool:
        """Enable the output for the specified channel."""
        return self._conn.write(f":OUTPut{channel} ON")

    def disable(self, channel: int = 1) -> bool:
        """Disable the output for the specified channel."""
        return self._conn.write(f":OUTPut{channel} OFF")

    def set_state(self, channel: int, enabled: bool) -> bool:
        """
        Set the output state.

        Args:
            channel: Output channel (1 or 2).
            enabled: True to enable, False to disable.
        """
        state = "ON" if enabled else "OFF"
        return self._conn.write(f":OUTPut{channel} {state}")

    def get_state(self, channel: int = 1) -> Optional[bool]:
        """
        Query the output state.

        Returns:
            True if enabled, False if disabled, None on query failure.
        """
        response = self._conn.query(f":OUTPut{channel}?")
        if response is None:
            return None
        return response.strip().upper() in ("1", "ON")

    def is_enabled(self, channel: int = 1) -> bool:
        """Return True if the channel output is enabled."""
        return self.get_state(channel) is True

    # =========================================================================
    # Load Impedance
    # =========================================================================

    def set_impedance(self, channel: int, impedance: float) -> bool:
        """
        Set the output load impedance.

        Args:
            channel: Output channel (1 or 2).
            impedance: Load in Ohms (1 to 10 000).

        Note:
            This setting affects how the displayed amplitude is scaled.
            Set it to match your actual load.
        """
        if impedance < self.MIN_IMPEDANCE or impedance > self.MAX_IMPEDANCE:
            print(f"Warning: Impedance should be between "
                  f"{self.MIN_IMPEDANCE} and {self.MAX_IMPEDANCE} Ω")
        return self._conn.write(f":OUTPut{channel}:LOAD {impedance}")

    def set_impedance_high_z(self, channel: int) -> bool:
        """Set the load impedance to High-Z (infinite)."""
        return self._conn.write(f":OUTPut{channel}:LOAD INFinity")

    def set_impedance_50_ohm(self, channel: int) -> bool:
        """Set the load impedance to 50 Ω."""
        return self.set_impedance(channel, 50)

    def get_impedance(self, channel: int = 1) -> Optional[float]:
        """
        Query the load impedance.

        Returns:
            Impedance in Ω, float('inf') for High-Z, None on failure.
        """
        response = self._conn.query(f":OUTPut{channel}:LOAD?")
        if response:
            try:
                value = float(response)
                if value > 1e30:
                    return float('inf')
                return value
            except ValueError:
                return None
        return None

    # =========================================================================
    # Output Polarity
    # =========================================================================

    def set_polarity(self, channel: int, polarity: OutputPolarity) -> bool:
        """
        Set the output polarity.

        Args:
            channel: Output channel (1 or 2).
            polarity: OutputPolarity.NORMAL or OutputPolarity.INVERTED.
        """
        return self._conn.write(f":OUTPut{channel}:POLarity {polarity.value}")

    def set_polarity_normal(self, channel: int) -> bool:
        """Set output polarity to normal."""
        return self.set_polarity(channel, OutputPolarity.NORMAL)

    def set_polarity_inverted(self, channel: int) -> bool:
        """Set output polarity to inverted."""
        return self.set_polarity(channel, OutputPolarity.INVERTED)

    def get_polarity(self, channel: int = 1) -> Optional[str]:
        """Query the output polarity. Returns 'NORM' or 'INV'."""
        return self._conn.query(f":OUTPut{channel}:POLarity?")

    # =========================================================================
    # Sync Output
    # =========================================================================

    def enable_sync(self, channel: int = 1) -> bool:
        """Enable the sync signal output."""
        return self._conn.write(f":OUTPut{channel}:SYNC ON")

    def disable_sync(self, channel: int = 1) -> bool:
        """Disable the sync signal output."""
        return self._conn.write(f":OUTPut{channel}:SYNC OFF")

    def get_sync_state(self, channel: int = 1) -> Optional[bool]:
        """Query whether the sync output is enabled."""
        response = self._conn.query(f":OUTPut{channel}:SYNC?")
        if response:
            return response.strip().upper() in ("1", "ON")
        return None

    def set_sync_polarity(self, channel: int,
                          polarity: SyncPolarity = SyncPolarity.NORMAL) -> bool:
        """
        Set the sync signal polarity.

        Args:
            channel: Output channel (1 or 2).
            polarity: SyncPolarity.NORMAL or SyncPolarity.INVERTED.
        """
        return self._conn.write(
            f":OUTPut{channel}:SYNC:POLarity {polarity.value}")

    # =========================================================================
    # Trigger Output
    # =========================================================================

    def enable_trigger_output(self, channel: int = 1) -> bool:
        """Enable the trigger output signal."""
        return self._conn.write(f":OUTPut{channel}:TRIGger ON")

    def disable_trigger_output(self, channel: int = 1) -> bool:
        """Disable the trigger output signal."""
        return self._conn.write(f":OUTPut{channel}:TRIGger OFF")

    def set_trigger_slope(self, channel: int, positive: bool = True) -> bool:
        """
        Set the trigger output edge.

        Args:
            channel: Output channel.
            positive: True for rising edge, False for falling edge.
        """
        slope = "POSitive" if positive else "NEGative"
        return self._conn.write(f":OUTPut{channel}:TRIGger:SLOPe {slope}")

    # =========================================================================
    # Convenience
    # =========================================================================

    def get_all_states(self) -> dict:
        """Return output states for both channels."""
        return {
            'ch1_enabled':   self.get_state(1),
            'ch2_enabled':   self.get_state(2),
            'ch1_impedance': self.get_impedance(1),
            'ch2_impedance': self.get_impedance(2),
            'ch1_polarity':  self.get_polarity(1),
            'ch2_polarity':  self.get_polarity(2),
        }


# =============================================================================
# Module Test / Evaluation Mode
# =============================================================================
if __name__ == "__main__":
    from ks33500b_connection import KS33500BConnection

    print("=" * 60)
    print("KS33500B Output Module - Evaluation Mode")
    print("=" * 60)

    conn = KS33500BConnection()

    print("\nSearching for devices...")
    devices = conn.discover_devices()

    if not devices:
        print("No devices found. Check USB / LAN connection.")
    else:
        resource = devices[0][0]
        print(f"Connecting to: {resource}")

        if conn.connect(resource):
            out = KS33500BOutput(conn)

            print("\n--- Current Output States ---")
            for key, val in out.get_all_states().items():
                print(f"  {key}: {val}")

            print("\n--- Enable / Disable CH1 ---")
            out.enable(1)
            print(f"  CH1 enabled: {out.is_enabled(1)}")
            out.disable(1)
            print(f"  CH1 enabled: {out.is_enabled(1)}")

            print("\n--- Impedance ---")
            out.set_impedance_50_ohm(1)
            print(f"  CH1 load: {out.get_impedance(1)} Ω")
            out.set_impedance_high_z(1)
            imp = out.get_impedance(1)
            print(f"  CH1 load: {'High-Z' if imp == float('inf') else imp}")

            print("\n--- Polarity ---")
            out.set_polarity_inverted(1)
            print(f"  CH1 polarity: {out.get_polarity(1)}")
            out.set_polarity_normal(1)
            print(f"  CH1 polarity: {out.get_polarity(1)}")

    conn.close()
    print("\n" + "=" * 60)
    print("Evaluation complete.")
    print("=" * 60)
