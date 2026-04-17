"""
Keysight 33500B Waveform Generator - Arbitrary Waveform Module

This module provides tools for creating and managing arbitrary waveforms
for the Keysight 33500B series. It can generate waveform data (basic shapes
and frequency combs), compute optimal point counts, save/load CSV files,
and prepare data for upload to the instrument.

Hardware constants (33500B standard memory):
  Min points  :   8
  Max points  : 65 536
  Min rate    :   1 Sa/s
  Max rate    : 250 MSa/s
  Vertical res: 14 bits (DAC range 0–16 383)

Date: 2026-04-16
"""

import numpy as np
from math import gcd
from functools import reduce
from typing import Optional, List, Tuple, Dict
from pathlib import Path


# =============================================================================
# Hardware Constants
# =============================================================================

KS33500B_MIN_POINTS = 8
KS33500B_MAX_POINTS = 65536
KS33500B_MIN_RATE   = 1          # Sa/s
KS33500B_MAX_RATE   = 250e6      # 250 MSa/s
MIN_POINTS_PER_CYCLE = 10        # smoothness target


# =============================================================================
# Optimal-Point Calculators
# =============================================================================

def compute_optimal_points(frequency: float) -> int:
    """
    Compute the optimal number of waveform points for a given output frequency,
    maximising smoothness within the 33500B hardware limits.

    Formula:
        max_pts = floor(MAX_RATE / frequency)   → capped at MAX_POINTS
        min pts = 8

    Args:
        frequency: Desired output frequency in Hz.

    Returns:
        Optimal number of points (8 – 65 536).
    """
    if frequency <= 0:
        return KS33500B_MAX_POINTS
    max_pts = int(KS33500B_MAX_RATE / frequency)
    return max(KS33500B_MIN_POINTS, min(max_pts, KS33500B_MAX_POINTS))


def _approximate_gcd(freqs: np.ndarray, tol: float = 1e-3) -> float:
    """Compute approximate GCD of an array of frequencies."""
    min_f = np.min(freqs)
    # Work in units of the smallest frequency
    ratios = np.round(freqs / min_f).astype(int)
    g = reduce(gcd, ratios)
    return float(min_f / g) if g != 0 else float(min_f)


def compute_optimal_points_for_comb(
        frequencies: List[float]) -> Tuple[int, Dict]:
    """
    Compute the optimal point count for a frequency comb waveform.

    The buffer represents one period of the fundamental (GCD of all tones).
    The highest tone requires the most points for smooth rendering.

    Args:
        frequencies: List of comb tone frequencies in Hz.

    Returns:
        (num_points, info_dict)
        info_dict keys: fundamental, f_max, harmonics,
                        min_points_needed, max_points_available,
                        num_points, sample_rate, warning.
    """
    freqs = np.array(frequencies, dtype=float)
    if len(freqs) == 0:
        raise ValueError("No frequencies specified")
    if np.any(freqs <= 0):
        raise ValueError("All frequencies must be positive")

    fundamental = _approximate_gcd(freqs)
    f_max = float(np.max(freqs))
    harmonics = f_max / fundamental

    min_pts_needed = int(np.ceil(harmonics * MIN_POINTS_PER_CYCLE))
    max_pts_available = min(
        int(KS33500B_MAX_RATE / fundamental),
        KS33500B_MAX_POINTS)

    optimal = max(KS33500B_MIN_POINTS, max_pts_available)

    warning = None
    if min_pts_needed > KS33500B_MAX_POINTS:
        warning = (
            f"Frequency span too wide for smooth output.\n"
            f"The highest tone ({f_max:.4g} Hz) needs ~{min_pts_needed} points "
            f"within a {fundamental:.4g} Hz fundamental period,\n"
            f"but the 33500B maximum is {KS33500B_MAX_POINTS}."
        )
    elif optimal < min_pts_needed:
        warning = (
            f"Rate-limited: only {optimal} points achievable "
            f"(need {min_pts_needed} for smooth output)."
        )

    sample_rate = optimal * fundamental
    info = {
        'fundamental':         fundamental,
        'f_max':               f_max,
        'harmonics':           harmonics,
        'min_points_needed':   min_pts_needed,
        'max_points_available': max_pts_available,
        'num_points':          optimal,
        'sample_rate':         sample_rate,
        'warning':             warning,
    }
    return optimal, info


def check_frequency_feasibility(frequency: float) -> Tuple[bool, str]:
    """
    Check whether a given frequency is achievable as an arbitrary waveform.

    Returns:
        (feasible, message)
    """
    if frequency <= 0:
        return False, "Frequency must be positive."
    min_freq = KS33500B_MAX_RATE / KS33500B_MAX_POINTS  # ≈ 3 814 Hz crossover
    if frequency * KS33500B_MIN_POINTS > KS33500B_MAX_RATE:
        max_f = KS33500B_MAX_RATE / KS33500B_MIN_POINTS
        return False, (f"Frequency too high for arbitrary mode "
                       f"(max ≈ {max_f/1e6:.1f} MHz with {KS33500B_MIN_POINTS} pts).")
    n = compute_optimal_points(frequency)
    sr = frequency * n
    msg = (f"OK — {n} points, sample rate {sr/1e6:.3g} MSa/s "
           f"({n/MIN_POINTS_PER_CYCLE:.1f}× smoothness margin)")
    return True, msg


# =============================================================================
# ArbitraryWaveform Data Container
# =============================================================================

class ArbitraryWaveform:
    """
    Container for an arbitrary waveform: normalised ±1 data plus metadata.

    Attributes:
        name:       Instrument waveform name (e.g. "ARB1").  Max 12 chars.
        data:       numpy array of normalised values in [-1, +1], or None.
        frequency:  Intended output frequency in Hz (set by the generator).
        sample_rate: Computed sample rate in Sa/s.
        num_points: Number of waveform points.
        comb_info:  Dict with comb metadata (or None for single-tone shapes).
        description: Human-readable description string.
    """

    def __init__(self, name: str = "ARB1"):
        self.name: str = name[:12]
        self.data: Optional[np.ndarray] = None
        self.frequency: float = 1000.0
        self.sample_rate: float = 0.0
        self.num_points: int = 0
        self.comb_info: Optional[Dict] = None
        self.description: str = ""

    def save_csv(self, path: str) -> None:
        """Save waveform data to a CSV file (one value per line)."""
        if self.data is None:
            raise ValueError("No waveform data to save")
        np.savetxt(path, self.data, delimiter=",",
                   header=f"name={self.name},freq={self.frequency:.6g}",
                   comments="# ")
        print(f"Saved {len(self.data)} points to {path}")

    def load_csv(self, path: str) -> None:
        """Load waveform data from a CSV file."""
        raw = np.loadtxt(path, delimiter=",", comments="#")
        if raw.ndim > 1:
            raw = raw[:, 0]
        # Normalise
        max_abs = np.max(np.abs(raw))
        self.data = raw / max_abs if max_abs > 0 else raw
        self.num_points = len(self.data)
        # Try to read metadata from header
        try:
            with open(path) as f:
                line = f.readline().strip()
                if line.startswith("# name="):
                    parts = dict(p.split("=") for p in
                                 line.lstrip("# ").split(","))
                    self.name = parts.get("name", self.name)[:12]
                    self.frequency = float(parts.get("freq", self.frequency))
        except Exception:
            pass
        print(f"Loaded {self.num_points} points from {path}")

    def __repr__(self) -> str:
        pts = self.num_points if self.data is not None else 0
        return (f"ArbitraryWaveform(name='{self.name}', "
                f"points={pts}, freq={self.frequency:.4g} Hz)")


# =============================================================================
# WaveformGenerator Factory
# =============================================================================

class WaveformGenerator:
    """
    Factory class that generates ArbitraryWaveform objects for common shapes.

    All methods return a fully populated ArbitraryWaveform with:
      - .data   : normalised numpy array in [-1, +1]
      - .frequency : intended output frequency
      - .sample_rate : computed sample rate
      - .num_points  : number of points
    """

    @staticmethod
    def sine(frequency: float, name: str = "ARB1") -> ArbitraryWaveform:
        """Generate a single sine period."""
        n = compute_optimal_points(frequency)
        t = np.linspace(0, 1, n, endpoint=False)
        data = np.sin(2 * np.pi * t)
        return WaveformGenerator._build(name, data, frequency, n,
                                        f"Sine at {frequency:.4g} Hz")

    @staticmethod
    def square(frequency: float, duty_cycle: float = 50.0,
               name: str = "ARB1") -> ArbitraryWaveform:
        """Generate a square wave with the given duty cycle."""
        n = compute_optimal_points(frequency)
        t = np.linspace(0, 1, n, endpoint=False)
        data = np.where(t < duty_cycle / 100.0, 1.0, -1.0)
        return WaveformGenerator._build(
            name, data, frequency, n,
            f"Square {duty_cycle:.0f}% DC at {frequency:.4g} Hz")

    @staticmethod
    def ramp(frequency: float, symmetry: float = 100.0,
             name: str = "ARB1") -> ArbitraryWaveform:
        """
        Generate a ramp wave.
        symmetry = 100 % → rising sawtooth, 0 % → falling sawtooth,
        50 % → triangle.
        """
        n = compute_optimal_points(frequency)
        t = np.linspace(0, 1, n, endpoint=False)
        sym = symmetry / 100.0
        data = np.where(
            t < sym,
            2.0 * t / sym - 1.0 if sym > 0 else -1.0,
            1.0 - 2.0 * (t - sym) / (1.0 - sym) if sym < 1.0 else 1.0
        )
        return WaveformGenerator._build(
            name, data, frequency, n,
            f"Ramp {symmetry:.0f}% sym at {frequency:.4g} Hz")

    @staticmethod
    def pulse(frequency: float, duty_cycle: float = 50.0,
              rise_frac: float = 0.01, fall_frac: float = 0.01,
              name: str = "ARB1") -> ArbitraryWaveform:
        """
        Generate a pulse with finite rise and fall times.

        Args:
            frequency:  Output frequency in Hz.
            duty_cycle: Pulse duty cycle in percent.
            rise_frac:  Rise time as fraction of period (0–1).
            fall_frac:  Fall time as fraction of period (0–1).
        """
        n = compute_optimal_points(frequency)
        t = np.linspace(0, 1, n, endpoint=False)
        duty = duty_cycle / 100.0
        data = np.full(n, -1.0)
        for i, ti in enumerate(t):
            if ti < rise_frac:
                data[i] = -1.0 + 2.0 * ti / rise_frac
            elif ti < duty - fall_frac:
                data[i] = 1.0
            elif ti < duty:
                data[i] = 1.0 - 2.0 * (ti - (duty - fall_frac)) / fall_frac
        return WaveformGenerator._build(
            name, data, frequency, n,
            f"Pulse {duty_cycle:.0f}% DC at {frequency:.4g} Hz")

    @staticmethod
    def gaussian(frequency: float, sigma: float = 0.15,
                 name: str = "ARB1") -> ArbitraryWaveform:
        """
        Generate a Gaussian pulse centred in the period.

        Args:
            frequency: Output frequency in Hz.
            sigma:     Standard deviation as fraction of period (default 0.15).
        """
        n = compute_optimal_points(frequency)
        t = np.linspace(0, 1, n, endpoint=False)
        data = np.exp(-0.5 * ((t - 0.5) / sigma) ** 2)
        data = data / np.max(data)
        data = 2.0 * data - 1.0
        return WaveformGenerator._build(
            name, data, frequency, n,
            f"Gaussian σ={sigma:.2f} at {frequency:.4g} Hz")

    @staticmethod
    def sinc(frequency: float, lobes: int = 4,
             name: str = "ARB1") -> ArbitraryWaveform:
        """
        Generate a sinc pulse.

        Args:
            frequency: Output frequency in Hz.
            lobes:     Number of lobes on each side of the main lobe.
        """
        n = compute_optimal_points(frequency)
        t = np.linspace(-lobes, lobes, n)
        data = np.sinc(t)
        return WaveformGenerator._build(
            name, data, frequency, n,
            f"Sinc {lobes} lobes at {frequency:.4g} Hz")

    @staticmethod
    def exponential(frequency: float, tau: float = 0.2,
                    decay: bool = True,
                    name: str = "ARB1") -> ArbitraryWaveform:
        """
        Generate an exponential rise or decay.

        Args:
            frequency: Output frequency in Hz.
            tau:       Time constant as fraction of period.
            decay:     True for decay, False for rise.
        """
        n = compute_optimal_points(frequency)
        t = np.linspace(0, 1, n, endpoint=False)
        data = np.exp(-t / tau) if decay else 1.0 - np.exp(-t / tau)
        data = 2.0 * data - 1.0
        return WaveformGenerator._build(
            name, data, frequency, n,
            f"Exp {'decay' if decay else 'rise'} τ={tau:.2f}")

    @staticmethod
    def frequency_comb(frequencies: List[float],
                       monte_carlo_iter: int = 1000,
                       name: str = "ARB1") -> ArbitraryWaveform:
        """
        Generate a frequency-comb waveform: sum of sinusoids with
        Monte Carlo phase optimisation for maximum RMS (flattest envelope).

        Args:
            frequencies:       List of tone frequencies in Hz.
            monte_carlo_iter:  Number of random-phase trials.
            name:              Instrument waveform name.

        Returns:
            ArbitraryWaveform with .comb_info metadata populated.
        """
        freqs = np.array(frequencies, dtype=float)
        if len(freqs) == 0:
            raise ValueError("At least one frequency required")

        n, info = compute_optimal_points_for_comb(list(freqs))
        fundamental = info['fundamental']

        t = np.linspace(0, 1.0 / fundamental, n, endpoint=False)

        best_data = None
        best_rms = -1.0

        for _ in range(monte_carlo_iter):
            phases = np.random.uniform(0, 2 * np.pi, len(freqs))
            waveform = np.zeros(n)
            for f, phi in zip(freqs, phases):
                waveform += np.sin(2 * np.pi * f * t + phi)
            rms = np.sqrt(np.mean(waveform ** 2))
            if rms > best_rms:
                best_rms = rms
                best_data = waveform.copy()

        # Normalise
        max_abs = np.max(np.abs(best_data))
        if max_abs > 0:
            best_data /= max_abs

        wf = ArbitraryWaveform(name)
        wf.data = best_data
        wf.frequency = fundamental
        wf.sample_rate = info['sample_rate']
        wf.num_points = n
        wf.comb_info = info
        wf.description = (
            f"Freq comb: {len(freqs)} tones, "
            f"f0={fundamental:.4g} Hz, "
            f"fmax={info['f_max']:.4g} Hz, "
            f"{n} pts, {monte_carlo_iter} MC trials")
        return wf

    # =========================================================================
    # Internal helper
    # =========================================================================

    @staticmethod
    def _build(name: str, data: np.ndarray, frequency: float,
               n: int, description: str) -> ArbitraryWaveform:
        # Normalise to ±1
        max_abs = np.max(np.abs(data))
        if max_abs > 0:
            data = data / max_abs
        wf = ArbitraryWaveform(name)
        wf.data = data
        wf.frequency = frequency
        wf.sample_rate = frequency * n
        wf.num_points = n
        wf.description = description
        return wf


# =============================================================================
# Module Test / Evaluation Mode
# =============================================================================
if __name__ == "__main__":
    print("=" * 60)
    print("KS33500B Arbitrary Waveform Module - Evaluation Mode")
    print("=" * 60)

    print("\n--- Single-frequency shapes ---")
    for label, wf in [
        ("Sine 1 kHz",    WaveformGenerator.sine(1000)),
        ("Square 50%",    WaveformGenerator.square(1000, 50)),
        ("Square 25%",    WaveformGenerator.square(1000, 25)),
        ("Ramp rising",   WaveformGenerator.ramp(1000, 100)),
        ("Triangle",      WaveformGenerator.ramp(1000, 50)),
        ("Gaussian",      WaveformGenerator.gaussian(1000)),
        ("Sinc 4 lobes",  WaveformGenerator.sinc(1000)),
    ]:
        ok, msg = check_frequency_feasibility(wf.frequency)
        print(f"  {label:<20} {wf.num_points:>6} pts  {wf.sample_rate/1e6:.3g} MSa/s  | {msg}")

    print("\n--- Frequency comb (100 Hz – 1 kHz, step 100 Hz) ---")
    comb_freqs = [100 * k for k in range(1, 11)]
    comb = WaveformGenerator.frequency_comb(comb_freqs, monte_carlo_iter=500)
    print(f"  {comb.description}")
    if comb.comb_info.get('warning'):
        print(f"  WARNING: {comb.comb_info['warning']}")

    print("\n--- Optimal points vs frequency ---")
    for f in [1, 100, 1e3, 10e3, 100e3, 1e6, 10e6, 30e6]:
        n = compute_optimal_points(f)
        sr = f * n
        print(f"  {f:>10.0f} Hz  →  {n:>6} pts, {sr/1e6:.3g} MSa/s")

    print("\n" + "=" * 60)
    print("Evaluation complete.")
    print("=" * 60)
