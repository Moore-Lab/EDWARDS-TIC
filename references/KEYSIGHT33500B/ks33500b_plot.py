"""
Keysight 33500B Waveform Generator - Plot Module

This module provides waveform visualization for the 33500B controller GUI.
It can generate preview plots of standard waveforms and arbitrary waveform
data, as well as sweep frequency-vs-time diagrams.

Date: 2026-04-16
"""

import numpy as np
import matplotlib.pyplot as plt
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from typing import Optional, Tuple
import tkinter as tk


class WaveformPlotter:
    """
    Generates and displays waveform plots for the KS33500B GUI.

    Supports:
    - Standard waveforms: sine, square, pulse, ramp, noise, DC
    - Arbitrary waveform data (normalised ±1 arrays)
    - Frequency sweep diagram (frequency vs time)
    - Embedding in tkinter via FigureCanvasTkAgg
    """

    PLOT_POINTS = 1000
    CYCLES_TO_SHOW = 3

    def __init__(self):
        self.fig: Optional[Figure] = None
        self.ax = None
        self.canvas = None

    # =========================================================================
    # Waveform Generators (static)
    # =========================================================================

    @staticmethod
    def generate_sine(frequency: float, amplitude: float, offset: float,
                      phase: float, num_points: int = 1000,
                      num_cycles: int = 3) -> Tuple[np.ndarray, np.ndarray]:
        period = 1.0 / frequency
        t = np.linspace(0, num_cycles * period, num_points)
        phase_rad = np.deg2rad(phase)
        v = (amplitude / 2) * np.sin(2 * np.pi * frequency * t + phase_rad) + offset
        return t, v

    @staticmethod
    def generate_square(frequency: float, amplitude: float, offset: float,
                        phase: float, duty_cycle: float = 50.0,
                        num_points: int = 1000,
                        num_cycles: int = 3) -> Tuple[np.ndarray, np.ndarray]:
        from scipy import signal
        period = 1.0 / frequency
        t = np.linspace(0, num_cycles * period, num_points)
        phase_rad = np.deg2rad(phase)
        duty = duty_cycle / 100.0
        v = (amplitude / 2) * signal.square(
            2 * np.pi * frequency * t + phase_rad, duty=duty) + offset
        return t, v

    @staticmethod
    def generate_pulse(frequency: float, amplitude: float, offset: float,
                       phase: float, duty_cycle: float = 50.0,
                       rise_time: float = 0.0, fall_time: float = 0.0,
                       num_points: int = 1000,
                       num_cycles: int = 3) -> Tuple[np.ndarray, np.ndarray]:
        period = 1.0 / frequency
        t = np.linspace(0, num_cycles * period, num_points)
        duty = duty_cycle / 100.0
        pulse_width = period * duty
        pulse_start = (period - pulse_width) / 2.0
        pulse_end = pulse_start + pulse_width

        high_level = (amplitude / 2) + offset
        low_level = -(amplitude / 2) + offset

        v = np.full_like(t, low_level)
        for i, time_val in enumerate(t):
            cycle_pos = time_val % period
            if pulse_start <= cycle_pos < pulse_end:
                v[i] = high_level

        return t, v

    @staticmethod
    def generate_ramp(frequency: float, amplitude: float, offset: float,
                      phase: float, symmetry: float = 50.0,
                      num_points: int = 1000,
                      num_cycles: int = 3) -> Tuple[np.ndarray, np.ndarray]:
        from scipy import signal
        period = 1.0 / frequency
        t = np.linspace(0, num_cycles * period, num_points)
        phase_rad = np.deg2rad(phase)
        width = symmetry / 100.0
        v = (amplitude / 2) * signal.sawtooth(
            2 * np.pi * frequency * t + phase_rad, width=width) + offset
        return t, v

    @staticmethod
    def generate_noise(amplitude: float, offset: float,
                       num_points: int = 1000,
                       duration: float = 0.01) -> Tuple[np.ndarray, np.ndarray]:
        t = np.linspace(0, duration, num_points)
        v = (amplitude / 6) * np.random.randn(num_points) + offset
        return t, v

    @staticmethod
    def generate_dc(voltage: float,
                    duration: float = 0.01) -> Tuple[np.ndarray, np.ndarray]:
        t = np.array([0.0, duration])
        v = np.array([voltage, voltage])
        return t, v

    @staticmethod
    def generate_arbitrary(data: np.ndarray, frequency: float,
                           amplitude: float = 2.0, offset: float = 0.0,
                           num_cycles: int = 3) -> Tuple[np.ndarray, np.ndarray]:
        period = 1.0 / frequency
        v_normalized = np.tile(data, num_cycles)
        v = v_normalized * (amplitude / 2) + offset
        t = np.linspace(0, num_cycles * period, len(v))
        return t, v

    # =========================================================================
    # Sweep Preview Generator (static)
    # =========================================================================

    @staticmethod
    def generate_sweep_preview(
            start_freq: float, stop_freq: float, sweep_time: float,
            spacing: str = "linear",
            hold_start: float = 0.0, hold_stop: float = 0.0,
            return_time: float = 0.0,
            num_points: int = 500) -> Tuple[np.ndarray, np.ndarray]:
        """
        Generate a frequency-vs-time trace for the sweep visualisation.

        Args:
            start_freq: Start frequency in Hz.
            stop_freq:  Stop frequency in Hz.
            sweep_time: Sweep duration in seconds.
            spacing:    'linear' or 'logarithmic'.
            hold_start: Hold time at start frequency (s).
            hold_stop:  Hold time at stop frequency (s).
            return_time: Return sweep time (0 = no return).
            num_points: Number of time samples.

        Returns:
            (t, freq_hz) arrays.
        """
        total_time = hold_start + sweep_time + hold_stop + return_time
        if total_time <= 0:
            total_time = sweep_time if sweep_time > 0 else 1.0

        t_list, f_list = [], []

        # Hold at start
        if hold_start > 0:
            n = max(2, int(num_points * hold_start / total_time))
            t_seg = np.linspace(0, hold_start, n)
            t_list.append(t_seg)
            f_list.append(np.full(n, start_freq))

        t_offset = hold_start

        # Sweep
        n_sweep = max(2, int(num_points * sweep_time / total_time))
        t_seg = np.linspace(t_offset, t_offset + sweep_time, n_sweep)
        frac = (t_seg - t_offset) / sweep_time
        if spacing.lower() == "logarithmic" and start_freq > 0 and stop_freq > 0:
            f_seg = start_freq * (stop_freq / start_freq) ** frac
        else:
            f_seg = start_freq + (stop_freq - start_freq) * frac
        t_list.append(t_seg)
        f_list.append(f_seg)
        t_offset += sweep_time

        # Hold at stop
        if hold_stop > 0:
            n = max(2, int(num_points * hold_stop / total_time))
            t_seg = np.linspace(t_offset, t_offset + hold_stop, n)
            t_list.append(t_seg)
            f_list.append(np.full(n, stop_freq))
            t_offset += hold_stop

        # Return sweep
        if return_time > 0:
            n_ret = max(2, int(num_points * return_time / total_time))
            t_seg = np.linspace(t_offset, t_offset + return_time, n_ret)
            frac_ret = (t_seg - t_offset) / return_time
            if spacing.lower() == "logarithmic" and start_freq > 0 and stop_freq > 0:
                f_ret = stop_freq * (start_freq / stop_freq) ** frac_ret
            else:
                f_ret = stop_freq + (start_freq - stop_freq) * frac_ret
            t_list.append(t_seg)
            f_list.append(f_ret)

        t_all = np.concatenate(t_list)
        f_all = np.concatenate(f_list)
        return t_all, f_all

    # =========================================================================
    # Axis Formatters (static)
    # =========================================================================

    @staticmethod
    def format_time_axis(t: np.ndarray) -> Tuple[np.ndarray, str]:
        max_t = np.max(t)
        if max_t < 1e-6:
            return t * 1e9, "ns"
        elif max_t < 1e-3:
            return t * 1e6, "µs"
        elif max_t < 1:
            return t * 1e3, "ms"
        else:
            return t, "s"

    @staticmethod
    def format_frequency(frequency: float) -> str:
        if frequency >= 1e6:
            return f"{frequency / 1e6:.6g} MHz"
        elif frequency >= 1e3:
            return f"{frequency / 1e3:.6g} kHz"
        else:
            return f"{frequency:.6g} Hz"

    @staticmethod
    def format_freq_axis(freqs: np.ndarray) -> Tuple[np.ndarray, str]:
        max_f = np.max(freqs)
        if max_f >= 1e6:
            return freqs / 1e6, "MHz"
        elif max_f >= 1e3:
            return freqs / 1e3, "kHz"
        else:
            return freqs, "Hz"

    # =========================================================================
    # Figure Creation
    # =========================================================================

    def create_figure(self, figsize: Tuple[float, float] = (6, 3),
                      dpi: int = 100) -> Figure:
        self.fig = Figure(figsize=figsize, dpi=dpi)
        self.ax = self.fig.add_subplot(111)
        return self.fig

    # =========================================================================
    # Plot Methods
    # =========================================================================

    def plot_waveform(self, waveform_type: str,
                      frequency: float = 1000.0,
                      amplitude: float = 5.0,
                      offset: float = 0.0,
                      phase: float = 0.0,
                      duty_cycle: float = 50.0,
                      symmetry: float = 50.0,
                      arb_data: Optional[np.ndarray] = None,
                      channel: int = 1,
                      show_grid: bool = True,
                      show_annotations: bool = True) -> None:
        """
        Render a waveform preview onto self.ax.

        Args:
            waveform_type: 'Sine', 'Square', 'Pulse', 'Ramp', 'Noise',
                           'DC', or 'Arbitrary'.
            frequency:     Carrier frequency in Hz.
            amplitude:     Amplitude in Vpp.
            offset:        DC offset in V.
            phase:         Start phase in degrees.
            duty_cycle:    Duty cycle in % (Square / Pulse).
            symmetry:      Symmetry in % (Ramp).
            arb_data:      Normalised data array for Arbitrary mode.
            channel:       Channel number (affects plot colour).
            show_grid:     Whether to show grid lines.
            show_annotations: Whether to show parameter text box.
        """
        if self.ax is None:
            self.create_figure()

        self.ax.clear()
        wf_type = waveform_type.lower()

        if wf_type == "sine":
            t, v = self.generate_sine(frequency, amplitude, offset, phase)
        elif wf_type == "square":
            t, v = self.generate_square(frequency, amplitude, offset,
                                        phase, duty_cycle)
        elif wf_type == "pulse":
            t, v = self.generate_pulse(frequency, amplitude, offset,
                                       phase, duty_cycle)
        elif wf_type == "ramp":
            t, v = self.generate_ramp(frequency, amplitude, offset,
                                      phase, symmetry)
        elif wf_type == "noise":
            t, v = self.generate_noise(amplitude, offset)
        elif wf_type == "dc":
            t, v = self.generate_dc(offset)
        elif wf_type == "arbitrary" and arb_data is not None:
            t, v = self.generate_arbitrary(arb_data, frequency,
                                           amplitude, offset)
        else:
            t, v = self.generate_sine(frequency, amplitude, offset, phase)

        t_scaled, time_unit = self.format_time_axis(t)
        color = "#1f77b4" if channel == 1 else "#ff7f0e"
        self.ax.plot(t_scaled, v, color=color, linewidth=1.5)

        self.ax.set_xlabel(f"Time ({time_unit})")
        self.ax.set_ylabel("Voltage (V)")
        self.ax.set_title(f"Channel {channel}: {waveform_type}")

        v_min, v_max = np.min(v), np.max(v)
        margin = (v_max - v_min) * 0.1 if v_max != v_min else 0.5
        self.ax.set_ylim(v_min - margin, v_max + margin)

        if show_grid:
            self.ax.grid(True, linestyle='--', alpha=0.7)

        if show_annotations and wf_type not in ("noise", "dc"):
            ann = (f"f = {self.format_frequency(frequency)}\n"
                   f"Vpp = {amplitude:.3g} V\n"
                   f"Offset = {offset:.3g} V\n"
                   f"Phase = {phase:.1f}°")
            if wf_type in ("square", "pulse"):
                ann += f"\nDuty = {duty_cycle:.1f}%"
            elif wf_type == "ramp":
                ann += f"\nSymm = {symmetry:.1f}%"
            self.ax.text(0.98, 0.98, ann,
                         transform=self.ax.transAxes,
                         verticalalignment='top',
                         horizontalalignment='right',
                         fontsize=8,
                         bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.8))

        self.fig.tight_layout()

    def plot_sweep(self, start_freq: float, stop_freq: float,
                   sweep_time: float,
                   spacing: str = "linear",
                   hold_start: float = 0.0,
                   hold_stop: float = 0.0,
                   return_time: float = 0.0,
                   channel: int = 1,
                   show_grid: bool = True) -> None:
        """
        Render a frequency-vs-time sweep preview onto self.ax.

        Args:
            start_freq:  Start frequency in Hz.
            stop_freq:   Stop frequency in Hz.
            sweep_time:  Sweep duration in seconds.
            spacing:     'linear' or 'logarithmic'.
            hold_start:  Hold at start (s).
            hold_stop:   Hold at stop (s).
            return_time: Return sweep time (s). 0 = no return.
            channel:     Channel number (affects colour).
            show_grid:   Show grid lines.
        """
        if self.ax is None:
            self.create_figure()

        self.ax.clear()

        t, f = self.generate_sweep_preview(
            start_freq, stop_freq, sweep_time, spacing,
            hold_start, hold_stop, return_time)

        t_scaled, time_unit = self.format_time_axis(t)
        f_scaled, freq_unit = self.format_freq_axis(f)

        color = "#1f77b4" if channel == 1 else "#ff7f0e"
        self.ax.plot(t_scaled, f_scaled, color=color, linewidth=1.5)

        self.ax.set_xlabel(f"Time ({time_unit})")
        self.ax.set_ylabel(f"Frequency ({freq_unit})")
        self.ax.set_title(f"Channel {channel}: Frequency Sweep")

        if spacing.lower() == "logarithmic":
            try:
                self.ax.set_yscale("log")
            except Exception:
                pass

        f_min = min(start_freq, stop_freq)
        f_max = max(start_freq, stop_freq)
        margin = (f_max - f_min) * 0.05
        if spacing.lower() != "logarithmic":
            self.ax.set_ylim(
                (f_min - margin) / (1e3 if freq_unit == "kHz" else
                                    1e6 if freq_unit == "MHz" else 1),
                (f_max + margin) / (1e3 if freq_unit == "kHz" else
                                    1e6 if freq_unit == "MHz" else 1))

        ann = (f"Start = {self.format_frequency(start_freq)}\n"
               f"Stop  = {self.format_frequency(stop_freq)}\n"
               f"Time  = {sweep_time:.3g} s\n"
               f"Spacing = {spacing.capitalize()}")
        self.ax.text(0.98, 0.98, ann,
                     transform=self.ax.transAxes,
                     verticalalignment='top',
                     horizontalalignment='right',
                     fontsize=8,
                     bbox=dict(boxstyle='round', facecolor='lightyellow', alpha=0.8))

        if show_grid:
            self.ax.grid(True, linestyle='--', alpha=0.7)

        self.fig.tight_layout()

    # =========================================================================
    # tkinter Integration
    # =========================================================================

    def embed_in_tkinter(self, parent: tk.Widget) -> FigureCanvasTkAgg:
        """Embed the current figure in a tkinter widget."""
        if self.fig is None:
            self.create_figure()
        self.canvas = FigureCanvasTkAgg(self.fig, master=parent)
        self.canvas.draw()
        return self.canvas

    def update(self):
        """Redraw the canvas."""
        if self.canvas:
            self.canvas.draw()

    def save(self, filename: str, dpi: int = 150):
        """Save the current figure to a file."""
        if self.fig:
            self.fig.savefig(filename, dpi=dpi, bbox_inches='tight')


# =============================================================================
# Module Test / Evaluation Mode
# =============================================================================
if __name__ == "__main__":
    print("=" * 60)
    print("KS33500B Plot Module - Evaluation Mode")
    print("=" * 60)

    plotter = WaveformPlotter()
    plotter.create_figure(figsize=(10, 4))

    print("\nGenerating standard waveform plots...")

    plotter.plot_waveform("Sine", 1000, 5.0, 0, 0)
    plotter.save("test_sine.png")
    print("Saved test_sine.png")

    plotter.plot_waveform("Square", 1000, 5.0, 0, 0, duty_cycle=25)
    plotter.save("test_square.png")
    print("Saved test_square.png")

    plotter.plot_waveform("Ramp", 500, 3.0, 0, 0, symmetry=100)
    plotter.save("test_ramp.png")
    print("Saved test_ramp.png")

    print("\nGenerating sweep preview...")
    plotter.plot_sweep(100e3, 700e3, sweep_time=0.1,
                       spacing="linear", hold_start=0.01, hold_stop=0.01,
                       return_time=0.05)
    plotter.save("test_sweep.png")
    print("Saved test_sweep.png  (100 kHz → 700 kHz in 0.1 s)")

    print("\n" + "=" * 60)
    print("Evaluation complete.")
    print("=" * 60)
