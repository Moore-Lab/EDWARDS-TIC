"""
Keysight 33500B Waveform Generator - Main Controller Module

This module provides a unified interface to control the Keysight 33500B series
waveform generators. It combines connection, waveform, and output control into
a single easy-to-use facade class.

Date: 2026-04-16
"""

from typing import Optional, List, Tuple

from ks33500b_connection import KS33500BConnection
from ks33500b_waveform import (KS33500BWaveform, WaveformType,
                                SweepSpacing, TriggerSource, BurstMode)
from ks33500b_output import KS33500BOutput, OutputPolarity


class KS33500BController:
    """
    Unified controller for Keysight 33500B waveform generator.

    Combines:
    - Connection management  (connect, disconnect, discover)
    - Waveform configuration (sine, square, pulse, ramp, noise, DC, arb)
    - Frequency sweep        (configure_sweep, sweep_on, sweep_off)
    - Burst mode             (configure_burst, burst_on, burst_off)
    - Output control         (enable, disable, impedance, polarity)

    Example:
        ks = KS33500BController()
        if ks.auto_connect():
            ks.setup_sine(1, frequency=1000, amplitude=2.0)
            ks.output_on(1)
            # ... do work ...
            ks.output_off(1)
            ks.disconnect()

    Context manager:
        with KS33500BController() as ks:
            if ks.is_connected:
                ks.setup_sine(1, frequency=1e6, amplitude=1.0)
                ks.output_on(1)
    """

    def __init__(self, resource_name: Optional[str] = None,
                 timeout: int = 5000):
        """
        Initialise the 33500B controller.

        Args:
            resource_name: VISA resource string (optional).
            timeout:       Communication timeout in ms.
        """
        self._connection = KS33500BConnection(resource_name, timeout)
        self._waveform: Optional[KS33500BWaveform] = None
        self._output:   Optional[KS33500BOutput]   = None

    # =========================================================================
    # Properties
    # =========================================================================

    @property
    def is_connected(self) -> bool:
        return self._connection.is_connected

    @property
    def idn(self) -> Optional[str]:
        return self._connection.idn

    @property
    def connection(self) -> KS33500BConnection:
        return self._connection

    @property
    def waveform(self) -> Optional[KS33500BWaveform]:
        return self._waveform

    @property
    def output(self) -> Optional[KS33500BOutput]:
        return self._output

    # =========================================================================
    # Connection Management
    # =========================================================================

    def discover_devices(self) -> List[Tuple[str, str]]:
        """Discover available Keysight 33500B devices."""
        return self._connection.discover_devices()

    def connect(self, resource_name: Optional[str] = None) -> bool:
        """
        Connect to an instrument.

        Args:
            resource_name: VISA resource string. If None, uses the one
                           passed to __init__ (or the first discovered device).
        """
        if self._connection.connect(resource_name):
            self._waveform = KS33500BWaveform(self._connection)
            self._output   = KS33500BOutput(self._connection)
            return True
        return False

    def auto_connect(self) -> bool:
        """Auto-discover and connect to the first available 33500B."""
        devices = self.discover_devices()
        if devices:
            resource, idn = devices[0]
            print(f"Auto-connecting to: {idn}")
            return self.connect(resource)
        print("No Keysight 33500B devices found.")
        return False

    def disconnect(self) -> None:
        """Disconnect from the instrument."""
        self._connection.disconnect()
        self._waveform = None
        self._output   = None

    def reset(self) -> bool:
        """Reset the instrument to factory defaults (*RST)."""
        return self._connection.reset()

    def beep(self) -> bool:
        """Make the instrument beep."""
        return self._connection.beep()

    # =========================================================================
    # Quick Waveform Setup
    # =========================================================================

    def setup_sine(self, channel: int = 1, frequency: float = 1000.0,
                   amplitude: float = 5.0, offset: float = 0.0,
                   phase: float = 0.0) -> bool:
        """
        Configure a sine wave.

        Args:
            channel:   Output channel (1 or 2).
            frequency: Frequency in Hz.
            amplitude: Amplitude in Vpp.
            offset:    DC offset in V.
            phase:     Start phase in degrees.
        """
        if self._waveform:
            return self._waveform.apply_sine(
                channel, frequency, amplitude, offset, phase)
        return False

    def setup_square(self, channel: int = 1, frequency: float = 1000.0,
                     amplitude: float = 5.0, offset: float = 0.0,
                     phase: float = 0.0,
                     duty_cycle: Optional[float] = None) -> bool:
        """
        Configure a square wave.

        Args:
            duty_cycle: Optional duty cycle in percent (default: 50 %).
        """
        if self._waveform:
            ok = self._waveform.apply_square(
                channel, frequency, amplitude, offset, phase)
            if ok and duty_cycle is not None:
                self._waveform.set_square_duty_cycle(channel, duty_cycle)
            return ok
        return False

    def setup_ramp(self, channel: int = 1, frequency: float = 1000.0,
                   amplitude: float = 5.0, offset: float = 0.0,
                   phase: float = 0.0,
                   symmetry: Optional[float] = None) -> bool:
        """
        Configure a ramp wave.

        Args:
            symmetry: Optional symmetry in percent
                      (0 = falling, 50 = triangle, 100 = rising).
        """
        if self._waveform:
            ok = self._waveform.apply_ramp(
                channel, frequency, amplitude, offset, phase)
            if ok and symmetry is not None:
                self._waveform.set_ramp_symmetry(channel, symmetry)
            return ok
        return False

    def setup_pulse(self, channel: int = 1, frequency: float = 1000.0,
                    amplitude: float = 5.0, offset: float = 0.0,
                    phase: float = 0.0,
                    duty_cycle: Optional[float] = None,
                    width: Optional[float] = None,
                    rise_time: Optional[float] = None,
                    fall_time: Optional[float] = None) -> bool:
        """
        Configure a pulse wave.

        Args:
            duty_cycle: Optional duty cycle in percent.
            width:      Optional pulse width in seconds.
            rise_time:  Optional rise time in seconds.
            fall_time:  Optional fall time in seconds.
        """
        if self._waveform:
            ok = self._waveform.apply_pulse(
                channel, frequency, amplitude, offset, phase)
            if ok:
                if duty_cycle is not None:
                    self._waveform.set_pulse_duty_cycle(channel, duty_cycle)
                if width is not None:
                    self._waveform.set_pulse_width(channel, width)
                if rise_time is not None:
                    self._waveform.set_pulse_leading_edge(channel, rise_time)
                if fall_time is not None:
                    self._waveform.set_pulse_trailing_edge(channel, fall_time)
            return ok
        return False

    def setup_noise(self, channel: int = 1, amplitude: float = 5.0,
                    offset: float = 0.0) -> bool:
        """Configure Gaussian noise output."""
        if self._waveform:
            return self._waveform.apply_noise(channel, amplitude, offset)
        return False

    def setup_dc(self, channel: int = 1, voltage: float = 0.0) -> bool:
        """Configure DC voltage output."""
        if self._waveform:
            return self._waveform.apply_dc(channel, voltage)
        return False

    # =========================================================================
    # Frequency Sweep
    # =========================================================================

    def setup_sweep(self, channel: int = 1,
                    start_freq: float = 100e3,
                    stop_freq: float = 700e3,
                    sweep_time: float = 0.1,
                    waveform: str = "sine",
                    amplitude: float = 5.0,
                    offset: float = 0.0,
                    spacing: str = "linear",
                    return_time: float = 0.0,
                    hold_start: float = 0.0,
                    hold_stop: float = 0.0,
                    trigger: str = "immediate") -> bool:
        """
        Configure and arm a frequency sweep.

        This method:
          1. Sets up the carrier waveform (sine/square/ramp).
          2. Configures all sweep parameters.
          3. Enables sweep mode (sweep_on).
          4. Turns output ON.

        Call output_on() separately if you want manual control.

        Args:
            channel:     Output channel (1 or 2).
            start_freq:  Start frequency in Hz.
            stop_freq:   Stop frequency in Hz.
            sweep_time:  Sweep duration in seconds.
            waveform:    Carrier waveform: 'sine', 'square', or 'ramp'.
            amplitude:   Carrier amplitude in Vpp.
            offset:      Carrier DC offset in V.
            spacing:     'linear' or 'logarithmic'.
            return_time: Return sweep time in seconds (0 = no return).
            hold_start:  Hold time at start frequency in seconds.
            hold_stop:   Hold time at stop frequency in seconds.
            trigger:     'immediate', 'external', 'timer', or 'bus'.

        Returns:
            True if all commands succeeded.
        """
        if not self._waveform:
            return False

        # Map string args to enums
        spacing_map = {
            "linear":      SweepSpacing.LINEAR,
            "logarithmic": SweepSpacing.LOGARITHMIC,
            "log":         SweepSpacing.LOGARITHMIC,
        }
        trigger_map = {
            "immediate": TriggerSource.IMMEDIATE,
            "imm":       TriggerSource.IMMEDIATE,
            "external":  TriggerSource.EXTERNAL,
            "ext":       TriggerSource.EXTERNAL,
            "timer":     TriggerSource.TIMER,
            "bus":       TriggerSource.BUS,
        }
        sp_enum = spacing_map.get(spacing.lower(), SweepSpacing.LINEAR)
        tr_enum = trigger_map.get(trigger.lower(), TriggerSource.IMMEDIATE)

        # 1. Set carrier waveform using a mid-range frequency
        mid_freq = (start_freq + stop_freq) / 2.0
        wf_lower = waveform.lower()
        if wf_lower == "square":
            ok = self._waveform.apply_square(channel, mid_freq, amplitude, offset)
        elif wf_lower == "ramp":
            ok = self._waveform.apply_ramp(channel, mid_freq, amplitude, offset)
        else:
            ok = self._waveform.apply_sine(channel, mid_freq, amplitude, offset)

        if not ok:
            return False

        # 2. Configure sweep parameters
        ok &= self._waveform.configure_sweep(
            channel=channel,
            start_freq=start_freq,
            stop_freq=stop_freq,
            sweep_time=sweep_time,
            spacing=sp_enum,
            return_time=return_time,
            hold_start=hold_start,
            hold_stop=hold_stop,
            trigger=tr_enum,
        )

        # 3. Enable sweep mode
        ok &= self._waveform.sweep_on(channel)
        return ok

    def sweep_on(self, channel: int = 1) -> bool:
        """Enable sweep mode on the channel."""
        if self._waveform:
            return self._waveform.sweep_on(channel)
        return False

    def sweep_off(self, channel: int = 1) -> bool:
        """Disable sweep mode on the channel."""
        if self._waveform:
            return self._waveform.sweep_off(channel)
        return False

    # =========================================================================
    # Burst Mode
    # =========================================================================

    def setup_burst(self, channel: int = 1,
                    n_cycles: int = 1,
                    mode: str = "triggered",
                    trigger: str = "immediate",
                    phase: float = 0.0) -> bool:
        """
        Configure burst mode and enable it.

        Args:
            channel:   Output channel.
            n_cycles:  Cycles per burst.
            mode:      'triggered', 'gated', or 'infinity'.
            trigger:   'immediate', 'external', 'timer', or 'bus'.
            phase:     Burst start phase in degrees.
        """
        if not self._waveform:
            return False

        mode_map = {
            "triggered": BurstMode.TRIGGERED,
            "gated":     BurstMode.GATED,
            "infinity":  BurstMode.INFINITY,
        }
        trigger_map = {
            "immediate": TriggerSource.IMMEDIATE,
            "external":  TriggerSource.EXTERNAL,
            "timer":     TriggerSource.TIMER,
            "bus":       TriggerSource.BUS,
        }
        bm = mode_map.get(mode.lower(), BurstMode.TRIGGERED)
        tr = trigger_map.get(trigger.lower(), TriggerSource.IMMEDIATE)

        ok = self._waveform.configure_burst(channel, n_cycles, bm, tr, phase)
        ok &= self._waveform.burst_on(channel)
        return ok

    def burst_on(self, channel: int = 1) -> bool:
        """Enable burst mode on the channel."""
        if self._waveform:
            return self._waveform.burst_on(channel)
        return False

    def burst_off(self, channel: int = 1) -> bool:
        """Disable burst mode on the channel."""
        if self._waveform:
            return self._waveform.burst_off(channel)
        return False

    # =========================================================================
    # Output Control
    # =========================================================================

    def output_on(self, channel: int = 1) -> bool:
        """Enable output for the specified channel."""
        if self._output:
            return self._output.enable(channel)
        return False

    def output_off(self, channel: int = 1) -> bool:
        """Disable output for the specified channel."""
        if self._output:
            return self._output.disable(channel)
        return False

    def all_outputs_on(self) -> bool:
        """Enable outputs on both channels."""
        if self._output:
            return self._output.enable(1) and self._output.enable(2)
        return False

    def all_outputs_off(self) -> bool:
        """Disable outputs on both channels."""
        if self._output:
            return self._output.disable(1) and self._output.disable(2)
        return False

    def set_load_50_ohm(self, channel: int = 1) -> bool:
        """Set load impedance to 50 Ω."""
        if self._output:
            return self._output.set_impedance_50_ohm(channel)
        return False

    def set_load_high_z(self, channel: int = 1) -> bool:
        """Set load impedance to High-Z."""
        if self._output:
            return self._output.set_impedance_high_z(channel)
        return False

    # =========================================================================
    # Parameter Query
    # =========================================================================

    def get_frequency(self, channel: int = 1) -> Optional[float]:
        """Get current frequency in Hz."""
        if self._waveform:
            return self._waveform.get_frequency(channel)
        return None

    def get_amplitude(self, channel: int = 1) -> Optional[float]:
        """Get current amplitude in Vpp."""
        if self._waveform:
            return self._waveform.get_amplitude(channel)
        return None

    def get_offset(self, channel: int = 1) -> Optional[float]:
        """Get current DC offset in V."""
        if self._waveform:
            return self._waveform.get_offset(channel)
        return None

    def get_waveform_type(self, channel: int = 1) -> Optional[str]:
        """Get current waveform type string."""
        if self._waveform:
            return self._waveform.get_function(channel)
        return None

    def is_output_on(self, channel: int = 1) -> bool:
        """Check if the channel output is enabled."""
        if self._output:
            return self._output.is_enabled(channel)
        return False

    # =========================================================================
    # Parameter Set
    # =========================================================================

    def set_frequency(self, channel: int, frequency: float) -> bool:
        """Set frequency in Hz."""
        if self._waveform:
            return self._waveform.set_frequency(channel, frequency)
        return False

    def set_amplitude(self, channel: int, amplitude: float) -> bool:
        """Set amplitude in Vpp."""
        if self._waveform:
            return self._waveform.set_amplitude(channel, amplitude)
        return False

    def set_offset(self, channel: int, offset: float) -> bool:
        """Set DC offset in V."""
        if self._waveform:
            return self._waveform.set_offset(channel, offset)
        return False

    def set_phase(self, channel: int, phase: float) -> bool:
        """Set phase in degrees."""
        if self._waveform:
            return self._waveform.set_phase(channel, phase)
        return False

    # =========================================================================
    # Status
    # =========================================================================

    def get_status(self) -> dict:
        """Return a dict with comprehensive instrument status."""
        status = {
            'connected': self.is_connected,
            'idn':       self.idn,
        }
        if self.is_connected:
            status['channels'] = {}
            for ch in [1, 2]:
                ch_info = {
                    'output_enabled': self.is_output_on(ch),
                    'waveform':       self.get_waveform_type(ch),
                    'frequency':      self.get_frequency(ch),
                    'amplitude':      self.get_amplitude(ch),
                    'offset':         self.get_offset(ch),
                }
                if self._output:
                    ch_info['impedance'] = self._output.get_impedance(ch)
                    ch_info['polarity']  = self._output.get_polarity(ch)
                if self._waveform:
                    ch_info['sweep_on']  = self._waveform.get_sweep_state(ch)
                    ch_info['burst_on']  = self._waveform.get_burst_state(ch)
                status['channels'][ch] = ch_info
        return status

    def print_status(self) -> None:
        """Print formatted instrument status."""
        s = self.get_status()
        print("\n" + "=" * 50)
        print("Keysight 33500B Status")
        print("=" * 50)
        print(f"Connected : {s['connected']}")
        if s['connected']:
            print(f"IDN       : {s['idn']}")
            for ch in [1, 2]:
                cs = s['channels'][ch]
                print(f"\n--- Channel {ch} ---")
                print(f"  Output  : {'ON' if cs['output_enabled'] else 'OFF'}")
                print(f"  Waveform: {cs['waveform']}")
                print(f"  Freq    : {cs['frequency']} Hz")
                print(f"  Amp     : {cs['amplitude']} Vpp")
                print(f"  Offset  : {cs['offset']} V")
                imp = cs.get('impedance')
                if imp is not None:
                    print(f"  Load    : {'High-Z' if imp == float('inf') else f'{imp} Ω'}")
                if cs.get('polarity'):
                    print(f"  Polarity: {cs['polarity']}")
                if cs.get('sweep_on'):
                    print(f"  Sweep   : ON")
                if cs.get('burst_on'):
                    print(f"  Burst   : ON")
        print("=" * 50)

    # =========================================================================
    # Context Manager
    # =========================================================================

    def __enter__(self):
        if not self.is_connected:
            self.auto_connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.disconnect()
        return False


# =============================================================================
# Module Test / Evaluation Mode
# =============================================================================
if __name__ == "__main__":
    import time

    print("=" * 60)
    print("KS33500B Controller - Evaluation Mode")
    print("=" * 60)

    ks = KS33500BController()

    print("\nSearching for devices...")
    devices = ks.discover_devices()

    if not devices:
        print("No devices found. Check connection.")
    else:
        resource = devices[0][0]
        print(f"Connecting to: {resource}")

        if ks.connect(resource):
            print("\n--- Initial Status ---")
            ks.print_status()

            # Sine wave test
            print("\n--- Sine wave: 1 kHz, 2 Vpp ---")
            ks.setup_sine(1, frequency=1000, amplitude=2.0)
            ks.output_on(1)
            time.sleep(1)
            ks.output_off(1)

            # Sweep test
            print("\n--- Sweep: 100 kHz → 700 kHz in 0.1 s ---")
            ks.setup_sweep(
                channel=1,
                start_freq=100e3,
                stop_freq=700e3,
                sweep_time=0.1,
                waveform="sine",
                amplitude=2.0,
                spacing="linear",
            )
            ks.output_on(1)
            time.sleep(2)
            ks.sweep_off(1)
            ks.output_off(1)

            print("\n--- Final Status ---")
            ks.print_status()

            ks.reset()

    ks.connection.close()
    print("\n" + "=" * 60)
    print("Evaluation complete.")
    print("=" * 60)
