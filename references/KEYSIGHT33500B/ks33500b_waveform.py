"""
Keysight 33500B Waveform Generator - Waveform & Sweep Module

This module handles waveform configuration and frequency sweep control for
the Keysight 33500B series waveform generators. It provides:
  - Standard waveform setup (sine, square, ramp, pulse, noise, DC, arbitrary)
  - Individual parameter read/write
  - Frequency sweep configuration (start/stop freq, sweep time, spacing, etc.)
  - Burst mode configuration

Date: 2026-04-16
"""

from __future__ import annotations

from typing import Optional, TYPE_CHECKING
from enum import Enum

if TYPE_CHECKING:
    import numpy
    from ks33500b_arbitrarywf import ArbitraryWaveform


class WaveformType(Enum):
    """Supported waveform function types."""
    SINE      = "SINusoid"
    SQUARE    = "SQUare"
    RAMP      = "RAMP"
    PULSE     = "PULSe"
    NOISE     = "NOISe"
    DC        = "DC"
    ARBITRARY = "ARB"


class SweepSpacing(Enum):
    """Frequency sweep spacing modes."""
    LINEAR      = "LINear"
    LOGARITHMIC = "LOGarithmic"


class TriggerSource(Enum):
    """Trigger source options (sweep and burst)."""
    IMMEDIATE = "IMMediate"
    EXTERNAL  = "EXTernal"
    TIMER     = "TIMer"
    BUS       = "BUS"


class BurstMode(Enum):
    """Burst mode options."""
    TRIGGERED = "TRIGgered"
    GATED     = "GATed"
    INFINITY  = "INFinity"


class KS33500BWaveform:
    """
    Handles waveform and sweep configuration for Keysight 33500B.

    Keysight 33500B series specifications:
      Frequency (sine/square): 1 µHz – 20 MHz (33511/12B) or 30 MHz (33521/22B)
      Frequency (ramp/pulse):  1 µHz – 200 kHz / 20 MHz
      Amplitude:               1 mVpp – 10 Vpp (50 Ω), 2 mVpp – 20 Vpp (High-Z)
      Arbitrary:               8 – 65 536 points, 1 Sa/s – 250 MSa/s
    """

    MAX_FREQ_SINE   = 30e6   # 30 MHz (33521/22B); 20 MHz for 33511/12B
    MIN_FREQ        = 1e-6   # 1 µHz
    MAX_AMPLITUDE   = 20.0   # 20 Vpp (High-Z)
    MIN_AMPLITUDE   = 1e-3   # 1 mVpp

    def __init__(self, connection):
        """
        Initialize waveform controller.

        Args:
            connection: KS33500BConnection instance.
        """
        self._conn = connection

    # =========================================================================
    # Quick Waveform Setup (APPLy)
    # =========================================================================

    def apply_sine(self, channel: int = 1, frequency: float = 1000.0,
                   amplitude: float = 5.0, offset: float = 0.0,
                   phase: float = 0.0) -> bool:
        """
        Configure sine wave output.

        Args:
            channel:   Output channel (1 or 2).
            frequency: Frequency in Hz.
            amplitude: Amplitude in Vpp.
            offset:    DC offset in V.
            phase:     Start phase in degrees.
        """
        cmd = (f":SOURce{channel}:APPLy:SINusoid "
               f"{frequency},{amplitude},{offset},{phase}")
        return self._conn.write(cmd)

    def apply_square(self, channel: int = 1, frequency: float = 1000.0,
                     amplitude: float = 5.0, offset: float = 0.0,
                     phase: float = 0.0) -> bool:
        """
        Configure square wave output (50 % duty cycle).

        Use set_square_duty_cycle() afterward to change the duty cycle.
        """
        cmd = (f":SOURce{channel}:APPLy:SQUare "
               f"{frequency},{amplitude},{offset},{phase}")
        return self._conn.write(cmd)

    def apply_ramp(self, channel: int = 1, frequency: float = 1000.0,
                   amplitude: float = 5.0, offset: float = 0.0,
                   phase: float = 0.0) -> bool:
        """
        Configure ramp / triangle wave output (50 % symmetry).

        Use set_ramp_symmetry() afterward to change symmetry.
        """
        cmd = (f":SOURce{channel}:APPLy:RAMP "
               f"{frequency},{amplitude},{offset},{phase}")
        return self._conn.write(cmd)

    def apply_pulse(self, channel: int = 1, frequency: float = 1000.0,
                    amplitude: float = 5.0, offset: float = 0.0,
                    phase: float = 0.0) -> bool:
        """Configure pulse wave output."""
        cmd = (f":SOURce{channel}:APPLy:PULSe "
               f"{frequency},{amplitude},{offset},{phase}")
        return self._conn.write(cmd)

    def apply_noise(self, channel: int = 1, amplitude: float = 5.0,
                    offset: float = 0.0) -> bool:
        """Configure Gaussian noise output."""
        cmd = f":SOURce{channel}:APPLy:NOISe DEFault,{amplitude},{offset}"
        return self._conn.write(cmd)

    def apply_dc(self, channel: int = 1, offset: float = 0.0) -> bool:
        """Configure DC voltage output."""
        cmd = f":SOURce{channel}:APPLy:DC DEFault,DEFault,{offset}"
        return self._conn.write(cmd)

    def apply_arbitrary(self, channel: int = 1, frequency: float = 1000.0,
                        amplitude: float = 5.0, offset: float = 0.0) -> bool:
        """
        Configure arbitrary waveform output using the currently selected arb.

        The waveform must have been uploaded and selected via
        upload_arbitrary_waveform() and select_arbitrary_waveform() first.
        """
        cmd = (f":SOURce{channel}:APPLy:ARBitrary "
               f"{frequency},{amplitude},{offset}")
        return self._conn.write(cmd)

    # =========================================================================
    # Individual Parameter Control
    # =========================================================================

    def set_function(self, channel: int, waveform: WaveformType) -> bool:
        """Set the waveform function type."""
        return self._conn.write(
            f":SOURce{channel}:FUNCtion {waveform.value}")

    def get_function(self, channel: int = 1) -> Optional[str]:
        """Query the current waveform function type."""
        return self._conn.query(f":SOURce{channel}:FUNCtion?")

    def set_frequency(self, channel: int, frequency: float) -> bool:
        """Set waveform frequency in Hz."""
        return self._conn.write(
            f":SOURce{channel}:FREQuency:FIXed {frequency}")

    def get_frequency(self, channel: int = 1) -> Optional[float]:
        """Query current frequency in Hz."""
        resp = self._conn.query(f":SOURce{channel}:FREQuency?")
        if resp:
            try:
                return float(resp)
            except ValueError:
                return None
        return None

    def set_amplitude(self, channel: int, amplitude: float) -> bool:
        """Set amplitude in Vpp."""
        return self._conn.write(f":SOURce{channel}:VOLTage {amplitude}")

    def get_amplitude(self, channel: int = 1) -> Optional[float]:
        """Query amplitude in Vpp."""
        resp = self._conn.query(f":SOURce{channel}:VOLTage?")
        if resp:
            try:
                return float(resp)
            except ValueError:
                return None
        return None

    def set_offset(self, channel: int, offset: float) -> bool:
        """Set DC offset in V."""
        return self._conn.write(f":SOURce{channel}:VOLTage:OFFSet {offset}")

    def get_offset(self, channel: int = 1) -> Optional[float]:
        """Query DC offset in V."""
        resp = self._conn.query(f":SOURce{channel}:VOLTage:OFFSet?")
        if resp:
            try:
                return float(resp)
            except ValueError:
                return None
        return None

    def set_phase(self, channel: int, phase: float) -> bool:
        """Set start phase in degrees (-360 to +360)."""
        return self._conn.write(f":SOURce{channel}:PHASe {phase}")

    def get_phase(self, channel: int = 1) -> Optional[float]:
        """Query phase in degrees."""
        resp = self._conn.query(f":SOURce{channel}:PHASe?")
        if resp:
            try:
                return float(resp)
            except ValueError:
                return None
        return None

    def set_high_level(self, channel: int, high: float) -> bool:
        """Set waveform high-level voltage in V."""
        return self._conn.write(f":SOURce{channel}:VOLTage:HIGH {high}")

    def set_low_level(self, channel: int, low: float) -> bool:
        """Set waveform low-level voltage in V."""
        return self._conn.write(f":SOURce{channel}:VOLTage:LOW {low}")

    # =========================================================================
    # Square Wave Specific
    # =========================================================================

    def set_square_duty_cycle(self, channel: int, duty_cycle: float) -> bool:
        """Set square wave duty cycle in percent (0.01 % to 99.99 %)."""
        return self._conn.write(
            f":SOURce{channel}:FUNCtion:SQUare:DCYCle {duty_cycle}")

    def get_square_duty_cycle(self, channel: int = 1) -> Optional[float]:
        """Query square wave duty cycle in percent."""
        resp = self._conn.query(
            f":SOURce{channel}:FUNCtion:SQUare:DCYCle?")
        if resp:
            try:
                return float(resp)
            except ValueError:
                return None
        return None

    # =========================================================================
    # Ramp Wave Specific
    # =========================================================================

    def set_ramp_symmetry(self, channel: int, symmetry: float) -> bool:
        """
        Set ramp symmetry in percent.
        0 % = falling ramp, 50 % = triangle, 100 % = rising ramp.
        """
        return self._conn.write(
            f":SOURce{channel}:FUNCtion:RAMP:SYMMetry {symmetry}")

    def get_ramp_symmetry(self, channel: int = 1) -> Optional[float]:
        """Query ramp symmetry in percent."""
        resp = self._conn.query(
            f":SOURce{channel}:FUNCtion:RAMP:SYMMetry?")
        if resp:
            try:
                return float(resp)
            except ValueError:
                return None
        return None

    # =========================================================================
    # Pulse Wave Specific
    # =========================================================================

    def set_pulse_duty_cycle(self, channel: int, duty_cycle: float) -> bool:
        """Set pulse duty cycle in percent."""
        return self._conn.write(
            f":SOURce{channel}:FUNCtion:PULSe:DCYCle {duty_cycle}")

    def get_pulse_duty_cycle(self, channel: int = 1) -> Optional[float]:
        """Query pulse duty cycle in percent."""
        resp = self._conn.query(
            f":SOURce{channel}:FUNCtion:PULSe:DCYCle?")
        if resp:
            try:
                return float(resp)
            except ValueError:
                return None
        return None

    def set_pulse_width(self, channel: int, width: float) -> bool:
        """Set pulse width in seconds."""
        return self._conn.write(
            f":SOURce{channel}:FUNCtion:PULSe:WIDTh {width}")

    def get_pulse_width(self, channel: int = 1) -> Optional[float]:
        """Query pulse width in seconds."""
        resp = self._conn.query(
            f":SOURce{channel}:FUNCtion:PULSe:WIDTh?")
        if resp:
            try:
                return float(resp)
            except ValueError:
                return None
        return None

    def set_pulse_leading_edge(self, channel: int, time: float) -> bool:
        """Set pulse leading-edge (rise) time in seconds."""
        return self._conn.write(
            f":SOURce{channel}:FUNCtion:PULSe:TRANsition:LEADing {time}")

    def set_pulse_trailing_edge(self, channel: int, time: float) -> bool:
        """Set pulse trailing-edge (fall) time in seconds."""
        return self._conn.write(
            f":SOURce{channel}:FUNCtion:PULSe:TRANsition:TRAiling {time}")

    # =========================================================================
    # Phase Sync
    # =========================================================================

    def sync_phases(self) -> bool:
        """Synchronise phases on both channels."""
        return self._conn.write(":PHASe:SYNChronize")

    def get_apply_settings(self, channel: int = 1) -> Optional[str]:
        """Query current waveform settings in APPLy format."""
        return self._conn.query(f":SOURce{channel}:APPLy?")

    # =========================================================================
    # Frequency Sweep
    # =========================================================================

    def configure_sweep(self, channel: int,
                        start_freq: float,
                        stop_freq: float,
                        sweep_time: float,
                        spacing: SweepSpacing = SweepSpacing.LINEAR,
                        return_time: float = 0.0,
                        hold_start: float = 0.0,
                        hold_stop: float = 0.0,
                        trigger: TriggerSource = TriggerSource.IMMEDIATE
                        ) -> bool:
        """
        Configure a frequency sweep on the specified channel.

        The carrier waveform type must be set beforehand with apply_sine()
        (or apply_square() / apply_ramp()) so the instrument has a waveform
        to sweep. Call sweep_on() to start the sweep after configuration.

        Args:
            channel:     Output channel (1 or 2).
            start_freq:  Sweep start frequency in Hz.
            stop_freq:   Sweep stop frequency in Hz.
            sweep_time:  Sweep duration in seconds.
            spacing:     SweepSpacing.LINEAR or SweepSpacing.LOGARITHMIC.
            return_time: Return-sweep duration in seconds. 0 = no return.
            hold_start:  Time to hold at start frequency before sweeping (s).
            hold_stop:   Time to hold at stop frequency after sweeping (s).
            trigger:     Trigger source for the sweep.

        Returns:
            True if all commands succeeded.
        """
        ok = True
        ok &= self._conn.write(
            f":SOURce{channel}:FREQuency:STARt {start_freq}")
        ok &= self._conn.write(
            f":SOURce{channel}:FREQuency:STOP {stop_freq}")
        ok &= self._conn.write(
            f":SOURce{channel}:SWEep:TIME {sweep_time}")
        ok &= self._conn.write(
            f":SOURce{channel}:SWEep:SPACing {spacing.value}")
        ok &= self._conn.write(
            f":SOURce{channel}:SWEep:RTIMe {return_time}")
        ok &= self._conn.write(
            f":SOURce{channel}:SWEep:HTIMe:STARt {hold_start}")
        ok &= self._conn.write(
            f":SOURce{channel}:SWEep:HTIMe:STOP {hold_stop}")
        ok &= self._conn.write(
            f":TRIGger{channel}:SOURce {trigger.value}")
        return ok

    def sweep_on(self, channel: int = 1) -> bool:
        """Enable frequency sweep mode on the channel."""
        return self._conn.write(f":SOURce{channel}:SWEep:STATe ON")

    def sweep_off(self, channel: int = 1) -> bool:
        """Disable frequency sweep mode on the channel."""
        return self._conn.write(f":SOURce{channel}:SWEep:STATe OFF")

    def get_sweep_state(self, channel: int = 1) -> Optional[bool]:
        """Return True if sweep is active, False if off, None on failure."""
        resp = self._conn.query(f":SOURce{channel}:SWEep:STATe?")
        if resp:
            return resp.strip().upper() in ("1", "ON")
        return None

    def set_sweep_start_freq(self, channel: int, freq: float) -> bool:
        """Set sweep start frequency in Hz."""
        return self._conn.write(f":SOURce{channel}:FREQuency:STARt {freq}")

    def get_sweep_start_freq(self, channel: int = 1) -> Optional[float]:
        """Query sweep start frequency in Hz."""
        resp = self._conn.query(f":SOURce{channel}:FREQuency:STARt?")
        if resp:
            try:
                return float(resp)
            except ValueError:
                return None
        return None

    def set_sweep_stop_freq(self, channel: int, freq: float) -> bool:
        """Set sweep stop frequency in Hz."""
        return self._conn.write(f":SOURce{channel}:FREQuency:STOP {freq}")

    def get_sweep_stop_freq(self, channel: int = 1) -> Optional[float]:
        """Query sweep stop frequency in Hz."""
        resp = self._conn.query(f":SOURce{channel}:FREQuency:STOP?")
        if resp:
            try:
                return float(resp)
            except ValueError:
                return None
        return None

    def set_sweep_time(self, channel: int, sweep_time: float) -> bool:
        """Set sweep time in seconds."""
        return self._conn.write(f":SOURce{channel}:SWEep:TIME {sweep_time}")

    def get_sweep_time(self, channel: int = 1) -> Optional[float]:
        """Query sweep time in seconds."""
        resp = self._conn.query(f":SOURce{channel}:SWEep:TIME?")
        if resp:
            try:
                return float(resp)
            except ValueError:
                return None
        return None

    def set_sweep_spacing(self, channel: int,
                          spacing: SweepSpacing) -> bool:
        """Set sweep spacing: LINEAR or LOGARITHMIC."""
        return self._conn.write(
            f":SOURce{channel}:SWEep:SPACing {spacing.value}")

    def set_sweep_return_time(self, channel: int, time: float) -> bool:
        """Set return-sweep time in seconds (0 = no return sweep)."""
        return self._conn.write(f":SOURce{channel}:SWEep:RTIMe {time}")

    def set_sweep_hold_start(self, channel: int, time: float) -> bool:
        """Set hold time at start frequency in seconds."""
        return self._conn.write(
            f":SOURce{channel}:SWEep:HTIMe:STARt {time}")

    def set_sweep_hold_stop(self, channel: int, time: float) -> bool:
        """Set hold time at stop frequency in seconds."""
        return self._conn.write(
            f":SOURce{channel}:SWEep:HTIMe:STOP {time}")

    def trigger_sweep(self, channel: int = 1) -> bool:
        """Send an immediate software trigger to start a sweep cycle."""
        return self._conn.write(f":TRIGger{channel}:IMMediate")

    def set_trigger_source(self, channel: int,
                           source: TriggerSource) -> bool:
        """Set the trigger source for sweep / burst."""
        return self._conn.write(
            f":TRIGger{channel}:SOURce {source.value}")

    # =========================================================================
    # Burst Mode
    # =========================================================================

    def configure_burst(self, channel: int,
                        n_cycles: int = 1,
                        mode: BurstMode = BurstMode.TRIGGERED,
                        trigger: TriggerSource = TriggerSource.IMMEDIATE,
                        phase: float = 0.0) -> bool:
        """
        Configure burst mode on the specified channel.

        Args:
            channel:  Output channel (1 or 2).
            n_cycles: Number of cycles per burst.
            mode:     BurstMode (TRIGGERED, GATED, INFINITY).
            trigger:  Trigger source.
            phase:    Burst start phase in degrees.

        Returns:
            True if all commands succeeded.
        """
        ok = True
        ok &= self._conn.write(
            f":SOURce{channel}:BURSt:MODe {mode.value}")
        ok &= self._conn.write(
            f":SOURce{channel}:BURSt:NCYCles {n_cycles}")
        ok &= self._conn.write(
            f":SOURce{channel}:BURSt:PHASe {phase}")
        ok &= self._conn.write(
            f":TRIGger{channel}:SOURce {trigger.value}")
        return ok

    def burst_on(self, channel: int = 1) -> bool:
        """Enable burst mode on the channel."""
        return self._conn.write(f":SOURce{channel}:BURSt:STATe ON")

    def burst_off(self, channel: int = 1) -> bool:
        """Disable burst mode on the channel."""
        return self._conn.write(f":SOURce{channel}:BURSt:STATe OFF")

    def get_burst_state(self, channel: int = 1) -> Optional[bool]:
        """Return True if burst mode is active."""
        resp = self._conn.query(f":SOURce{channel}:BURSt:STATe?")
        if resp:
            return resp.strip().upper() in ("1", "ON")
        return None

    # =========================================================================
    # Arbitrary Waveform Methods
    # =========================================================================

    def upload_arbitrary_waveform(self, channel: int, name: str,
                                   data: 'numpy.ndarray') -> bool:
        """
        Upload an arbitrary waveform to the instrument using ASCII format.

        The 33500B accepts comma-separated float values in the range
        -1.0 to +1.0 via the DATA:ARBitrary command.

        Up to 65 536 points per waveform (standard memory).
        The waveform is stored in volatile memory under the given name.

        Args:
            channel: Output channel (1 or 2).  Used only to set amplitude
                     context; the waveform catalog is shared.
            name:    Waveform name (alphanumeric, max 12 chars, e.g. "ARB1").
            data:    Array of normalised values in [-1, +1].

        Returns:
            True if upload succeeded.
        """
        import numpy as np
        import time

        n = len(data)
        if n < 8 or n > 65536:
            print(f"Error: Data length must be 8–65 536 points (got {n})")
            return False

        # Normalise to ±1
        max_abs = np.max(np.abs(data))
        if max_abs > 1.0:
            normalized = data / max_abs
        else:
            normalized = data.copy()

        # Clamp
        normalized = np.clip(normalized, -1.0, 1.0)

        print(f"Uploading {n} points to instrument as '{name}'...")

        # Build ASCII command
        values_str = ",".join(f"{v:.6f}" for v in normalized)
        cmd = f":SOURce{channel}:DATA:ARBitrary {name},{values_str}"

        if not self._conn.write(cmd):
            print("Error: Failed to send waveform data")
            return False

        # Wait proportional to data size
        time.sleep(max(0.2, n / 50000.0))

        # Check for errors
        err = self._conn.get_error()
        if err and not err.startswith("+0,") and not err.startswith("0,"):
            print(f"Warning: Instrument error after upload: {err}")

        print(f"Upload complete: '{name}' ({n} points)")
        return True

    def upload_arbitrary_waveform_binary(self, channel: int, name: str,
                                          data: 'numpy.ndarray') -> bool:
        """
        Upload an arbitrary waveform using binary IEEE 488.2 block format.

        This is faster than ASCII for large waveforms.  Data is converted to
        unsigned 14-bit DAC values (0–16 383) packed as 16-bit little-endian.

        Args:
            channel: Output channel (1 or 2).
            name:    Waveform name (e.g. "ARB1").
            data:    Array of normalised values in [-1, +1].

        Returns:
            True if upload succeeded.
        """
        import numpy as np
        import struct
        import time

        n = len(data)
        if n < 8 or n > 65536:
            print(f"Error: Data length must be 8–65 536 points (got {n})")
            return False

        # Normalise to ±1
        max_abs = np.max(np.abs(data))
        normalized = data / max_abs if max_abs > 1.0 else data.copy()
        normalized = np.clip(normalized, -1.0, 1.0)

        # Convert to unsigned 14-bit: -1 → 0, 0 → 8191, +1 → 16383
        dac = np.round((normalized + 1.0) / 2.0 * 16383).astype(np.uint16)
        dac = np.clip(dac, 0, 16383)

        binary_data = struct.pack(f'<{n}H', *dac)
        byte_count = len(binary_data)
        byte_count_str = str(byte_count)
        num_digits = len(byte_count_str)

        header = f":SOURce{channel}:DATA:ARBitrary:DAC {name},"
        block_hdr = f"#{num_digits}{byte_count_str}"
        cmd_bytes = (header.encode('ascii')
                     + block_hdr.encode('ascii')
                     + binary_data
                     + b'\n')

        print(f"Uploading {n} points (binary, {byte_count} bytes) as '{name}'...")

        if not self._conn.write_raw(cmd_bytes):
            print("Error: Failed to send binary waveform data")
            return False

        time.sleep(max(0.2, n / 100000.0))

        err = self._conn.get_error()
        if err and not err.startswith("+0,") and not err.startswith("0,"):
            print(f"Warning: Instrument error after upload: {err}")

        print(f"Binary upload complete: '{name}' ({n} points)")
        return True

    def upload_arbitrary_waveform_from_object(self, channel: int,
                                               waveform: 'ArbitraryWaveform',
                                               use_binary: bool = True) -> bool:
        """
        Upload an ArbitraryWaveform object to the instrument.

        Args:
            channel:    Output channel.
            waveform:   ArbitraryWaveform from ks33500b_arbitrarywf.
            use_binary: Use binary transfer (faster) when True.
        """
        if waveform.data is None:
            print("Error: Waveform has no data")
            return False

        name = waveform.name if waveform.name else "ARB1"
        if use_binary:
            return self.upload_arbitrary_waveform_binary(
                channel, name, waveform.data)
        return self.upload_arbitrary_waveform(channel, name, waveform.data)

    def select_arbitrary_waveform(self, channel: int, name: str) -> bool:
        """
        Select a previously uploaded arbitrary waveform for output.

        Args:
            channel: Output channel.
            name:    Waveform name as given during upload.
        """
        ok = self._conn.write(
            f':SOURce{channel}:FUNCtion:ARBitrary "{name}"')
        ok &= self._conn.write(f":SOURce{channel}:FUNCtion ARB")
        return ok

    def set_arb_sample_rate(self, channel: int, rate: float) -> bool:
        """
        Set the arbitrary waveform sample rate in Sa/s.

        Output frequency = sample_rate / num_points.

        Args:
            channel: Output channel.
            rate:    Sample rate in Sa/s (1 – 250 000 000).
        """
        return self._conn.write(
            f":SOURce{channel}:FUNCtion:ARBitrary:SRATe {rate}")

    def get_arb_sample_rate(self, channel: int = 1) -> Optional[float]:
        """Query the arbitrary waveform sample rate in Sa/s."""
        resp = self._conn.query(
            f":SOURce{channel}:FUNCtion:ARBitrary:SRATe?")
        if resp:
            try:
                return float(resp)
            except ValueError:
                return None
        return None

    def list_arbitrary_waveforms(self) -> Optional[str]:
        """List the arbitrary waveforms stored in instrument memory."""
        return self._conn.query(":SOURce1:DATA:VOLatile:CATalog?")

    def delete_arbitrary_waveform(self, name: str) -> bool:
        """Delete a stored arbitrary waveform by name."""
        return self._conn.write(f":SOURce1:DATA:DELete {name}")

    def delete_all_arbitrary_waveforms(self) -> bool:
        """Delete all user-defined arbitrary waveforms from volatile memory."""
        return self._conn.write(":SOURce1:DATA:DELete:ALL")


# =============================================================================
# Module Test / Evaluation Mode
# =============================================================================
if __name__ == "__main__":
    from ks33500b_connection import KS33500BConnection

    print("=" * 60)
    print("KS33500B Waveform Module - Evaluation Mode")
    print("=" * 60)

    conn = KS33500BConnection()

    print("\nSearching for devices...")
    devices = conn.discover_devices()

    if not devices:
        print("No devices found.")
    else:
        resource = devices[0][0]
        print(f"Connecting to: {resource}")

        if conn.connect(resource):
            wf = KS33500BWaveform(conn)

            print("\n--- Current Settings ---")
            print(f"  CH1: {wf.get_apply_settings(1)}")

            print("\n--- Sine Wave (1 kHz, 2 Vpp, 0.5 V offset) ---")
            wf.apply_sine(1, 1000, 2.0, 0.5, 0)
            print(f"  Function:  {wf.get_function(1)}")
            print(f"  Frequency: {wf.get_frequency(1)} Hz")
            print(f"  Amplitude: {wf.get_amplitude(1)} Vpp")
            print(f"  Offset:    {wf.get_offset(1)} V")

            print("\n--- Sweep: 100 kHz → 700 kHz in 0.1 s ---")
            wf.configure_sweep(
                channel=1,
                start_freq=100e3,
                stop_freq=700e3,
                sweep_time=0.1,
                spacing=SweepSpacing.LINEAR,
                return_time=0.0,
                hold_start=0.0,
                hold_stop=0.0,
                trigger=TriggerSource.IMMEDIATE,
            )
            wf.sweep_on(1)
            print(f"  Sweep active: {wf.get_sweep_state(1)}")
            print(f"  Start freq:  {wf.get_sweep_start_freq(1)} Hz")
            print(f"  Stop freq:   {wf.get_sweep_stop_freq(1)} Hz")
            print(f"  Sweep time:  {wf.get_sweep_time(1)} s")

            print("\n--- Disabling sweep and resetting ---")
            wf.sweep_off(1)
            conn.reset()

    conn.close()
    print("\n" + "=" * 60)
    print("Evaluation complete.")
    print("=" * 60)
