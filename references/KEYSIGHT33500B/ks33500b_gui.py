"""
Keysight 33500B Waveform Generator - GUI Application

Full tkinter GUI for the Keysight 33500B series waveform generators.
Features:
  - USB / LAN device discovery and connection
  - Dual-channel control tabs
  - Waveform types: Sine, Square, Pulse, Ramp, Noise, DC, Arbitrary
  - Frequency Sweep mode with live frequency-vs-time preview
  - Burst mode
  - Arbitrary waveform generation (shapes + frequency comb)
  - Live waveform preview (matplotlib)
  - Run modes: Continuous, N Cycles, Duration
  - Load impedance toggle (High-Z / 50 Ω)
  - Status bar

Date: 2026-04-16
"""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from typing import Optional, List, Tuple
import threading
import time
import numpy as np

from ks33500b_controller import KS33500BController
from ks33500b_plot import WaveformPlotter
from ks33500b_arbitrarywf import (
    ArbitraryWaveform, WaveformGenerator,
    compute_optimal_points, compute_optimal_points_for_comb,
    check_frequency_feasibility, KS33500B_MAX_POINTS,
)


# =============================================================================
# Connection Frame
# =============================================================================

class ConnectionFrame(ttk.LabelFrame):
    """Top-bar frame for VISA connection controls."""

    def __init__(self, parent, on_connect, on_disconnect):
        super().__init__(parent, text="Connection", padding=10)
        self.on_connect    = on_connect
        self.on_disconnect = on_disconnect
        self.devices: List[Tuple[str, str]] = []
        self._build()

    def _build(self):
        # Mode radio buttons
        self.mode_var = tk.StringVar(value="scan")
        ttk.Radiobutton(self, text="Scan for devices",
                        variable=self.mode_var, value="scan",
                        command=self._on_mode).grid(
            row=0, column=0, sticky="w", padx=5)
        ttk.Radiobutton(self, text="Manual VISA address",
                        variable=self.mode_var, value="manual",
                        command=self._on_mode).grid(
            row=0, column=1, sticky="w", padx=5)

        # Scan frame
        self.scan_frame = ttk.Frame(self)
        self.scan_frame.grid(row=1, column=0, columnspan=5,
                             sticky="ew", pady=5)
        ttk.Label(self.scan_frame, text="Device:").pack(
            side="left", padx=(0, 5))
        self.device_combo = ttk.Combobox(
            self.scan_frame, width=55, state="readonly")
        self.device_combo.pack(side="left", padx=5)
        self.scan_btn = ttk.Button(
            self.scan_frame, text="Scan", command=self._scan)
        self.scan_btn.pack(side="left", padx=5)

        # Manual frame (hidden by default)
        self.manual_frame = ttk.Frame(self)
        ttk.Label(self.manual_frame, text="VISA Address:").pack(
            side="left", padx=(0, 5))
        self.manual_entry = ttk.Entry(self.manual_frame, width=45)
        self.manual_entry.pack(side="left", padx=5)
        self.manual_entry.insert(0, "USB0::0x0957::0x2C07::MYXXXXXXXX::INSTR")

        # Connect / Disconnect / Status
        btn_frame = ttk.Frame(self)
        btn_frame.grid(row=2, column=0, columnspan=5, sticky="ew", pady=5)
        self.connect_btn = ttk.Button(
            btn_frame, text="Connect", command=self._connect)
        self.connect_btn.pack(side="left", padx=5)
        self.disconnect_btn = ttk.Button(
            btn_frame, text="Disconnect", command=self._disconnect,
            state="disabled")
        self.disconnect_btn.pack(side="left", padx=5)
        self.status_label = ttk.Label(
            btn_frame, text="Not connected", foreground="red")
        self.status_label.pack(side="left", padx=20)
        self.columnconfigure(0, weight=1)

    def _on_mode(self):
        if self.mode_var.get() == "scan":
            self.manual_frame.grid_remove()
            self.scan_frame.grid(row=1, column=0, columnspan=5,
                                 sticky="ew", pady=5)
        else:
            self.scan_frame.grid_remove()
            self.manual_frame.grid(row=1, column=0, columnspan=5,
                                   sticky="ew", pady=5)

    def _scan(self):
        self.scan_btn.config(state="disabled")
        self.status_label.config(text="Scanning...", foreground="orange")
        self.update()

        def do_scan():
            from ks33500b_connection import KS33500BConnection
            conn = KS33500BConnection()
            self.devices = conn.discover_devices()
            conn.close()
            self.after(0, self._scan_done)

        threading.Thread(target=do_scan, daemon=True).start()

    def _scan_done(self):
        self.scan_btn.config(state="normal")
        if self.devices:
            self.device_combo['values'] = [
                f"{idn}  ({res})" for res, idn in self.devices]
            self.device_combo.current(0)
            self.status_label.config(
                text=f"Found {len(self.devices)} device(s)",
                foreground="green")
        else:
            self.device_combo['values'] = []
            self.device_combo.set("")
            self.status_label.config(text="No devices found",
                                     foreground="red")

    def _connect(self):
        if self.mode_var.get() == "scan":
            if not self.devices:
                messagebox.showwarning("No Device",
                                       "Please scan for devices first.")
                return
            idx = self.device_combo.current()
            if idx < 0:
                messagebox.showwarning("No Device",
                                       "Please select a device.")
                return
            resource = self.devices[idx][0]
        else:
            resource = self.manual_entry.get().strip()
            if not resource:
                messagebox.showwarning("No Address",
                                       "Please enter a VISA address.")
                return

        self.status_label.config(text="Connecting...", foreground="orange")
        self.update()

        if self.on_connect(resource):
            self.connect_btn.config(state="disabled")
            self.disconnect_btn.config(state="normal")
            self.scan_btn.config(state="disabled")
            self.device_combo.config(state="disabled")
            self.manual_entry.config(state="disabled")
            self.status_label.config(text="Connected", foreground="green")
        else:
            self.status_label.config(text="Connection failed",
                                     foreground="red")

    def _disconnect(self):
        self.on_disconnect()
        self.connect_btn.config(state="normal")
        self.disconnect_btn.config(state="disabled")
        self.scan_btn.config(state="normal")
        self.device_combo.config(state="readonly")
        self.manual_entry.config(state="normal")
        self.status_label.config(text="Disconnected", foreground="red")


# =============================================================================
# Arbitrary Waveform Generator Dialog
# =============================================================================

class ArbGeneratorDialog(tk.Toplevel):
    """Modal dialog for generating arbitrary waveforms."""

    SHAPES = ["sine", "square", "ramp", "pulse", "gaussian",
              "sinc", "exponential", "frequency_comb"]

    def __init__(self, parent, on_generated):
        super().__init__(parent)
        self.title("Arbitrary Waveform Generator")
        self.resizable(False, False)
        self.on_generated = on_generated
        self.result: Optional[ArbitraryWaveform] = None
        self._build()
        self.grab_set()

    def _build(self):
        frm = ttk.Frame(self, padding=10)
        frm.pack(fill="both", expand=True)

        # Shape selection
        ttk.Label(frm, text="Shape:").grid(row=0, column=0, sticky="e", padx=5, pady=4)
        self.shape_var = tk.StringVar(value="sine")
        shape_combo = ttk.Combobox(frm, textvariable=self.shape_var,
                                   values=self.SHAPES, width=20, state="readonly")
        shape_combo.grid(row=0, column=1, columnspan=2, sticky="w", padx=5, pady=4)
        shape_combo.bind("<<ComboboxSelected>>", self._on_shape)

        # Frequency
        ttk.Label(frm, text="Frequency:").grid(
            row=1, column=0, sticky="e", padx=5, pady=4)
        self.freq_var = tk.StringVar(value="1000")
        self.freq_entry = ttk.Entry(frm, textvariable=self.freq_var, width=15)
        self.freq_entry.grid(row=1, column=1, sticky="w", padx=5, pady=4)
        self.freq_unit_var = tk.StringVar(value="Hz")
        ttk.Combobox(frm, textvariable=self.freq_unit_var,
                     values=["Hz", "kHz", "MHz"], width=6,
                     state="readonly").grid(row=1, column=2, sticky="w", padx=5, pady=4)

        # Extra parameters frame
        self.extra_frm = ttk.LabelFrame(frm, text="Options", padding=5)
        self.extra_frm.grid(row=2, column=0, columnspan=3, sticky="ew",
                            padx=5, pady=5)

        # Duty Cycle (square / pulse)
        self.duty_lbl = ttk.Label(self.extra_frm, text="Duty Cycle:")
        self.duty_lbl.grid(row=0, column=0, sticky="e", padx=5, pady=3)
        self.duty_var = tk.StringVar(value="50")
        self.duty_entry = ttk.Entry(self.extra_frm, textvariable=self.duty_var, width=10)
        self.duty_entry.grid(row=0, column=1, sticky="w", padx=5, pady=3)
        ttk.Label(self.extra_frm, text="%").grid(row=0, column=2, sticky="w")

        # Symmetry (ramp)
        self.symm_lbl = ttk.Label(self.extra_frm, text="Symmetry:")
        self.symm_lbl.grid(row=1, column=0, sticky="e", padx=5, pady=3)
        self.symm_var = tk.StringVar(value="100")
        self.symm_entry = ttk.Entry(self.extra_frm, textvariable=self.symm_var, width=10)
        self.symm_entry.grid(row=1, column=1, sticky="w", padx=5, pady=3)
        ttk.Label(self.extra_frm, text="% (0=fall, 50=tri, 100=rise)").grid(
            row=1, column=2, sticky="w")

        # Comb frequencies
        self.comb_lbl = ttk.Label(self.extra_frm, text="Comb freqs (Hz):")
        self.comb_lbl.grid(row=2, column=0, sticky="e", padx=5, pady=3)
        self.comb_var = tk.StringVar(value="100:100:1000")
        self.comb_entry = ttk.Entry(self.extra_frm, textvariable=self.comb_var, width=30)
        self.comb_entry.grid(row=2, column=1, columnspan=2, sticky="w", padx=5, pady=3)
        ttk.Label(self.extra_frm, text="(start:step:stop  or  f1,f2,…)",
                  font=("TkDefaultFont", 8),
                  foreground="gray").grid(row=3, column=1, columnspan=2,
                                          sticky="w", padx=5)

        # Monte Carlo iterations
        self.mc_lbl = ttk.Label(self.extra_frm, text="MC iterations:")
        self.mc_lbl.grid(row=4, column=0, sticky="e", padx=5, pady=3)
        self.mc_var = tk.StringVar(value="1000")
        ttk.Entry(self.extra_frm, textvariable=self.mc_var, width=10).grid(
            row=4, column=1, sticky="w", padx=5, pady=3)

        # Waveform name
        ttk.Label(frm, text="Name:").grid(row=3, column=0, sticky="e", padx=5, pady=4)
        self.name_var = tk.StringVar(value="ARB1")
        ttk.Entry(frm, textvariable=self.name_var, width=15).grid(
            row=3, column=1, sticky="w", padx=5, pady=4)
        ttk.Label(frm, text="(max 12 chars)", foreground="gray",
                  font=("TkDefaultFont", 8)).grid(row=3, column=2, sticky="w")

        # Info label
        self.info_var = tk.StringVar(value="")
        ttk.Label(frm, textvariable=self.info_var, foreground="blue",
                  wraplength=380, justify="left").grid(
            row=4, column=0, columnspan=3, sticky="w", padx=5, pady=5)

        # Buttons
        btn_frm = ttk.Frame(frm)
        btn_frm.grid(row=5, column=0, columnspan=3, sticky="e", pady=5)
        ttk.Button(btn_frm, text="Generate",
                   command=self._generate).pack(side="left", padx=5)
        ttk.Button(btn_frm, text="Cancel",
                   command=self.destroy).pack(side="left", padx=5)

        self._on_shape()

    def _on_shape(self, *_):
        shape = self.shape_var.get()
        is_comb = shape == "frequency_comb"

        for w in [self.duty_lbl, self.duty_entry]:
            w.grid() if shape in ("square", "pulse") else w.grid_remove()
        for w in [self.symm_lbl, self.symm_entry]:
            w.grid() if shape == "ramp" else w.grid_remove()
        for w in [self.comb_lbl, self.comb_entry, self.mc_lbl]:
            w.grid() if is_comb else w.grid_remove()

        self.freq_entry.config(state="disabled" if is_comb else "normal")

    def _parse_comb_freqs(self) -> List[float]:
        txt = self.comb_var.get().strip()
        if ":" in txt:
            parts = txt.split(":")
            if len(parts) == 3:
                start, step, stop = float(parts[0]), float(parts[1]), float(parts[2])
                return list(np.arange(start, stop + step * 0.5, step))
        return [float(x.strip()) for x in txt.split(",") if x.strip()]

    def _get_freq_hz(self) -> float:
        v = float(self.freq_var.get())
        unit = self.freq_unit_var.get()
        if unit == "kHz":
            v *= 1e3
        elif unit == "MHz":
            v *= 1e6
        return v

    def _generate(self):
        shape = self.shape_var.get()
        name  = self.name_var.get()[:12] or "ARB1"

        try:
            if shape == "frequency_comb":
                freqs = self._parse_comb_freqs()
                if not freqs:
                    raise ValueError("No frequencies entered")
                mc = int(self.mc_var.get())
                wf = WaveformGenerator.frequency_comb(freqs, mc, name)
                info = wf.comb_info
                msg = (f"{wf.num_points} pts, "
                       f"f0={info['fundamental']:.4g} Hz, "
                       f"SR={info['sample_rate']/1e6:.3g} MSa/s")
                if info.get('warning'):
                    msg += f"\n⚠ {info['warning']}"
                self.info_var.set(msg)
            else:
                freq = self._get_freq_hz()
                ok, feasibility_msg = check_frequency_feasibility(freq)
                if not ok:
                    raise ValueError(feasibility_msg)
                if shape == "sine":
                    wf = WaveformGenerator.sine(freq, name)
                elif shape == "square":
                    duty = float(self.duty_var.get())
                    wf = WaveformGenerator.square(freq, duty, name)
                elif shape == "ramp":
                    symm = float(self.symm_var.get())
                    wf = WaveformGenerator.ramp(freq, symm, name)
                elif shape == "pulse":
                    duty = float(self.duty_var.get())
                    wf = WaveformGenerator.pulse(freq, duty, name=name)
                elif shape == "gaussian":
                    wf = WaveformGenerator.gaussian(freq, name=name)
                elif shape == "sinc":
                    wf = WaveformGenerator.sinc(freq, name=name)
                elif shape == "exponential":
                    wf = WaveformGenerator.exponential(freq, name=name)
                else:
                    wf = WaveformGenerator.sine(freq, name)

                self.info_var.set(
                    f"{wf.num_points} pts, "
                    f"SR={wf.sample_rate/1e6:.3g} MSa/s  |  {feasibility_msg}")

            self.result = wf
            self.on_generated(wf)
            self.destroy()

        except Exception as e:
            messagebox.showerror("Generation Error", str(e), parent=self)


# =============================================================================
# Channel Frame
# =============================================================================

class ChannelFrame(ttk.LabelFrame):
    """Per-channel control panel (waveform, sweep, burst, output)."""

    WAVEFORMS  = ["Sine", "Square", "Pulse", "Ramp", "Noise", "DC", "Arbitrary"]
    SWEEP_WFS  = ["Sine", "Square", "Ramp"]
    MODES      = ["Standard", "Sweep", "Burst"]

    def __init__(self, parent, channel: int, controller_getter):
        super().__init__(parent, text=f"Channel {channel}", padding=10)
        self.channel        = channel
        self.get_controller = controller_getter
        self.arb_waveform: Optional[ArbitraryWaveform] = None
        self.plotter        = WaveformPlotter()
        self._output_off_job = None
        self._update_scheduled = False

        self._build()
        self._set_defaults()

    # =========================================================================
    # UI Construction
    # =========================================================================

    def _build(self):
        paned = ttk.PanedWindow(self, orient="horizontal")
        paned.pack(fill="both", expand=True)

        ctrl_frm = ttk.Frame(paned)
        paned.add(ctrl_frm, weight=1)

        plot_frm = ttk.LabelFrame(paned, text="Preview", padding=5)
        paned.add(plot_frm, weight=1)

        # --- Output row ---
        out_row = ttk.Frame(ctrl_frm)
        out_row.grid(row=0, column=0, columnspan=4, sticky="ew", pady=4)

        self.output_var = tk.BooleanVar(value=False)
        self.output_btn = ttk.Checkbutton(
            out_row, text="Output ON", variable=self.output_var,
            command=self._toggle_output)
        self.output_btn.pack(side="left", padx=5)

        self.led = tk.Canvas(out_row, width=20, height=20)
        self.led.pack(side="left", padx=5)
        self._set_led(False)

        ttk.Label(out_row, text="  Run:").pack(side="left", padx=(10, 3))
        self.run_var = tk.StringVar(value="Continuous")
        self.run_combo = ttk.Combobox(
            out_row, textvariable=self.run_var,
            values=["Continuous", "N Cycles", "Duration"],
            width=12, state="readonly")
        self.run_combo.pack(side="left", padx=3)
        self.run_combo.bind("<<ComboboxSelected>>", self._on_run_mode)

        self.cycles_frm = ttk.Frame(out_row)
        ttk.Label(self.cycles_frm, text="N:").pack(side="left")
        self.cycles_var = tk.StringVar(value="100")
        ttk.Entry(self.cycles_frm, textvariable=self.cycles_var, width=7).pack(
            side="left", padx=2)

        self.dur_frm = ttk.Frame(out_row)
        ttk.Label(self.dur_frm, text="T:").pack(side="left")
        self.dur_var = tk.StringVar(value="10")
        ttk.Entry(self.dur_frm, textvariable=self.dur_var, width=7).pack(
            side="left", padx=2)
        self.dur_unit_var = tk.StringVar(value="s")
        ttk.Combobox(self.dur_frm, textvariable=self.dur_unit_var,
                     values=["s", "min", "hour"], width=5,
                     state="readonly").pack(side="left", padx=2)

        # --- Mode selection (Standard / Sweep / Burst) ---
        mode_frm = ttk.LabelFrame(ctrl_frm, text="Mode", padding=5)
        mode_frm.grid(row=1, column=0, columnspan=4, sticky="ew", pady=4)

        self.mode_var = tk.StringVar(value="Standard")
        for m in self.MODES:
            ttk.Radiobutton(mode_frm, text=m, variable=self.mode_var,
                            value=m, command=self._on_mode).pack(
                side="left", padx=12)

        # --- Standard waveform panel ---
        self.std_panel = ttk.Frame(ctrl_frm)
        self.std_panel.grid(row=2, column=0, columnspan=4, sticky="ew")
        self._build_standard_panel(self.std_panel)

        # --- Sweep panel ---
        self.sweep_panel = ttk.Frame(ctrl_frm)
        self.sweep_panel.grid(row=2, column=0, columnspan=4, sticky="ew")
        self._build_sweep_panel(self.sweep_panel)

        # --- Burst panel ---
        self.burst_panel = ttk.Frame(ctrl_frm)
        self.burst_panel.grid(row=2, column=0, columnspan=4, sticky="ew")
        self._build_burst_panel(self.burst_panel)

        # --- Load impedance + Apply ---
        bottom_row = ttk.Frame(ctrl_frm)
        bottom_row.grid(row=3, column=0, columnspan=4, sticky="ew", pady=5)

        load_frm = ttk.LabelFrame(bottom_row, text="Load", padding=4)
        load_frm.pack(side="left", padx=5)
        self.load_var = tk.StringVar(value="HighZ")
        ttk.Radiobutton(load_frm, text="High-Z", variable=self.load_var,
                        value="HighZ", command=self._on_load).pack(
            side="left", padx=8)
        ttk.Radiobutton(load_frm, text="50 Ω", variable=self.load_var,
                        value="50", command=self._on_load).pack(
            side="left", padx=8)

        btn_row = ttk.Frame(bottom_row)
        btn_row.pack(side="right", padx=5)
        ttk.Button(btn_row, text="Refresh",
                   command=self._refresh).pack(side="left", padx=4)
        ttk.Button(btn_row, text="Apply Settings",
                   command=self._apply).pack(side="left", padx=4)

        # --- Plot ---
        self.plotter.create_figure(figsize=(4, 3), dpi=80)
        canvas = self.plotter.embed_in_tkinter(plot_frm)
        canvas.get_tk_widget().pack(fill="both", expand=True)
        self._update_plot()

    def _build_standard_panel(self, parent):
        # Waveform selection
        wf_frm = ttk.LabelFrame(parent, text="Waveform", padding=5)
        wf_frm.grid(row=0, column=0, columnspan=4, sticky="ew", pady=4)
        self.wf_var = tk.StringVar(value="Sine")
        for i, wf in enumerate(self.WAVEFORMS):
            ttk.Radiobutton(wf_frm, text=wf, variable=self.wf_var,
                            value=wf, command=self._on_wf).grid(
                row=i // 4, column=i % 4, padx=8, pady=2, sticky="w")

        # Parameters
        param_frm = ttk.LabelFrame(parent, text="Parameters", padding=5)
        param_frm.grid(row=1, column=0, columnspan=4, sticky="ew", pady=4)

        def lbl(text, row):
            ttk.Label(param_frm, text=text).grid(
                row=row, column=0, sticky="e", padx=5, pady=3)

        lbl("Frequency:", 0)
        self.freq_var = tk.StringVar(value="1000")
        self.freq_entry = ttk.Entry(param_frm, textvariable=self.freq_var, width=14)
        self.freq_entry.grid(row=0, column=1, padx=5, pady=3)
        self.freq_unit_var = tk.StringVar(value="Hz")
        ttk.Combobox(param_frm, textvariable=self.freq_unit_var,
                     values=["Hz", "kHz", "MHz"], width=6,
                     state="readonly").grid(row=0, column=2, padx=5, pady=3)
        self.freq_hint = ttk.Label(
            param_frm, text="(e.g. 1/0.1 = 10 Hz)",
            font=("TkDefaultFont", 8), foreground="gray")
        self.freq_hint.grid(row=0, column=3, sticky="w", padx=5)

        lbl("Amplitude:", 1)
        self.amp_var = tk.StringVar(value="5.0")
        ttk.Entry(param_frm, textvariable=self.amp_var, width=14).grid(
            row=1, column=1, padx=5, pady=3)
        ttk.Label(param_frm, text="Vpp").grid(row=1, column=2, sticky="w")

        lbl("Offset:", 2)
        self.offset_var = tk.StringVar(value="0.0")
        ttk.Entry(param_frm, textvariable=self.offset_var, width=14).grid(
            row=2, column=1, padx=5, pady=3)
        ttk.Label(param_frm, text="V").grid(row=2, column=2, sticky="w")

        lbl("Phase:", 3)
        self.phase_var = tk.StringVar(value="0.0")
        self.phase_entry = ttk.Entry(param_frm, textvariable=self.phase_var, width=14)
        self.phase_entry.grid(row=3, column=1, padx=5, pady=3)
        ttk.Label(param_frm, text="°").grid(row=3, column=2, sticky="w")

        # Waveform-specific options
        extra_frm = ttk.LabelFrame(parent, text="Waveform Options", padding=5)
        extra_frm.grid(row=2, column=0, columnspan=4, sticky="ew", pady=4)

        self.duty_lbl  = ttk.Label(extra_frm, text="Duty Cycle:")
        self.duty_lbl.grid(row=0, column=0, sticky="e", padx=5, pady=3)
        self.duty_var  = tk.StringVar(value="50")
        self.duty_entry = ttk.Entry(extra_frm, textvariable=self.duty_var, width=10)
        self.duty_entry.grid(row=0, column=1, padx=5, pady=3)
        ttk.Label(extra_frm, text="%").grid(row=0, column=2, sticky="w")

        # Pulse width row
        self.pw_frm = ttk.Frame(extra_frm)
        self.pw_frm.grid(row=1, column=0, columnspan=6, sticky="ew", pady=3)
        ttk.Label(self.pw_frm, text="Pulse Width:").grid(
            row=0, column=0, sticky="e", padx=5)
        self.pw_var  = tk.StringVar(value="100")
        ttk.Entry(self.pw_frm, textvariable=self.pw_var, width=10).grid(
            row=0, column=1, padx=5)
        self.pw_unit_var = tk.StringVar(value="µs")
        ttk.Combobox(self.pw_frm, textvariable=self.pw_unit_var,
                     values=["ns", "µs", "ms", "s"], width=5,
                     state="readonly").grid(row=0, column=2, padx=5)
        ttk.Label(self.pw_frm, text="Period:").grid(
            row=0, column=3, padx=(12, 5))
        self.period_disp = tk.StringVar(value="1.000 ms")
        ttk.Label(self.pw_frm, textvariable=self.period_disp, width=12).grid(
            row=0, column=4)
        ttk.Label(self.pw_frm, text="Duty:").grid(row=0, column=5, padx=(10, 2))
        self.calc_duty = tk.StringVar(value="10.0%")
        ttk.Label(self.pw_frm, textvariable=self.calc_duty, width=7).grid(
            row=0, column=6)
        self.pw_frm.grid_remove()

        self.symm_lbl  = ttk.Label(extra_frm, text="Symmetry:")
        self.symm_lbl.grid(row=0, column=3, sticky="e", padx=5, pady=3)
        self.symm_var  = tk.StringVar(value="50")
        self.symm_entry = ttk.Entry(extra_frm, textvariable=self.symm_var, width=10)
        self.symm_entry.grid(row=0, column=4, padx=5, pady=3)
        ttk.Label(extra_frm, text="%").grid(row=0, column=5, sticky="w")

        # Arbitrary waveform panel
        self.arb_frm = ttk.LabelFrame(parent, text="Arbitrary Waveform", padding=5)
        self.arb_frm.grid(row=3, column=0, columnspan=4, sticky="ew", pady=4)
        self.arb_name_var = tk.StringVar(value="No waveform loaded")
        ttk.Label(self.arb_frm, textvariable=self.arb_name_var).grid(
            row=0, column=0, columnspan=2, sticky="w", padx=5)
        ttk.Button(self.arb_frm, text="Load CSV…",
                   command=self._load_arb_csv).grid(row=0, column=2, padx=4)
        ttk.Button(self.arb_frm, text="Generate…",
                   command=self._generate_arb).grid(row=0, column=3, padx=4)
        ttk.Button(self.arb_frm, text="Save CSV…",
                   command=self._save_arb_csv).grid(row=0, column=4, padx=4)
        ttk.Button(self.arb_frm, text="Upload",
                   command=self._upload_arb).grid(row=0, column=5, padx=4)
        self.arb_info_var = tk.StringVar(value="")
        ttk.Label(self.arb_frm, textvariable=self.arb_info_var,
                  foreground="blue", font=("TkDefaultFont", 8)).grid(
            row=1, column=0, columnspan=6, sticky="w", padx=5)

    def _build_sweep_panel(self, parent):
        """Build the frequency sweep configuration panel."""
        frm = ttk.LabelFrame(parent, text="Frequency Sweep", padding=8)
        frm.pack(fill="x", pady=4)

        def row(label, r):
            ttk.Label(frm, text=label).grid(row=r, column=0, sticky="e",
                                            padx=5, pady=4)

        # Carrier waveform
        row("Waveform:", 0)
        self.sweep_wf_var = tk.StringVar(value="Sine")
        ttk.Combobox(frm, textvariable=self.sweep_wf_var,
                     values=self.SWEEP_WFS, width=10,
                     state="readonly").grid(row=0, column=1, sticky="w", padx=5)

        # Start frequency
        row("Start Freq:", 1)
        self.sw_start_var = tk.StringVar(value="100")
        ttk.Entry(frm, textvariable=self.sw_start_var, width=12).grid(
            row=1, column=1, padx=5, pady=4)
        self.sw_start_unit = tk.StringVar(value="kHz")
        ttk.Combobox(frm, textvariable=self.sw_start_unit,
                     values=["Hz", "kHz", "MHz"], width=6,
                     state="readonly").grid(row=1, column=2, padx=4)

        # Stop frequency
        row("Stop Freq:", 2)
        self.sw_stop_var = tk.StringVar(value="700")
        ttk.Entry(frm, textvariable=self.sw_stop_var, width=12).grid(
            row=2, column=1, padx=5, pady=4)
        self.sw_stop_unit = tk.StringVar(value="kHz")
        ttk.Combobox(frm, textvariable=self.sw_stop_unit,
                     values=["Hz", "kHz", "MHz"], width=6,
                     state="readonly").grid(row=2, column=2, padx=4)

        # Sweep time
        row("Sweep Time:", 3)
        self.sw_time_var = tk.StringVar(value="0.1")
        ttk.Entry(frm, textvariable=self.sw_time_var, width=12).grid(
            row=3, column=1, padx=5, pady=4)
        ttk.Label(frm, text="s").grid(row=3, column=2, sticky="w")

        # Spacing
        row("Spacing:", 4)
        self.sw_spacing_var = tk.StringVar(value="Linear")
        ttk.Combobox(frm, textvariable=self.sw_spacing_var,
                     values=["Linear", "Logarithmic"], width=12,
                     state="readonly").grid(row=4, column=1, sticky="w", padx=5)

        # Amplitude
        row("Amplitude:", 5)
        self.sw_amp_var = tk.StringVar(value="5.0")
        ttk.Entry(frm, textvariable=self.sw_amp_var, width=12).grid(
            row=5, column=1, padx=5, pady=4)
        ttk.Label(frm, text="Vpp").grid(row=5, column=2, sticky="w")

        # Return time
        row("Return Time:", 6)
        self.sw_rtime_var = tk.StringVar(value="0")
        ttk.Entry(frm, textvariable=self.sw_rtime_var, width=12).grid(
            row=6, column=1, padx=5, pady=4)
        ttk.Label(frm, text="s  (0 = no return)").grid(
            row=6, column=2, sticky="w")

        # Hold times
        row("Hold Start:", 7)
        self.sw_hstart_var = tk.StringVar(value="0")
        ttk.Entry(frm, textvariable=self.sw_hstart_var, width=12).grid(
            row=7, column=1, padx=5, pady=4)
        ttk.Label(frm, text="s").grid(row=7, column=2, sticky="w")

        row("Hold Stop:", 8)
        self.sw_hstop_var = tk.StringVar(value="0")
        ttk.Entry(frm, textvariable=self.sw_hstop_var, width=12).grid(
            row=8, column=1, padx=5, pady=4)
        ttk.Label(frm, text="s").grid(row=8, column=2, sticky="w")

        # Trigger
        row("Trigger:", 9)
        self.sw_trig_var = tk.StringVar(value="Immediate")
        ttk.Combobox(frm, textvariable=self.sw_trig_var,
                     values=["Immediate", "External", "Timer", "Bus"],
                     width=12, state="readonly").grid(
            row=9, column=1, sticky="w", padx=5)

        # Bind live preview updates
        for var in (self.sw_start_var, self.sw_start_unit,
                    self.sw_stop_var, self.sw_stop_unit,
                    self.sw_time_var, self.sw_spacing_var,
                    self.sw_rtime_var, self.sw_hstart_var, self.sw_hstop_var):
            var.trace_add("write", self._schedule_plot)

    def _build_burst_panel(self, parent):
        """Build the burst mode configuration panel."""
        frm = ttk.LabelFrame(parent, text="Burst Mode", padding=8)
        frm.pack(fill="x", pady=4)

        def row(label, r):
            ttk.Label(frm, text=label).grid(row=r, column=0, sticky="e",
                                            padx=5, pady=4)

        row("Cycles:", 0)
        self.burst_n_var = tk.StringVar(value="1")
        ttk.Entry(frm, textvariable=self.burst_n_var, width=10).grid(
            row=0, column=1, sticky="w", padx=5)

        row("Mode:", 1)
        self.burst_mode_var = tk.StringVar(value="Triggered")
        ttk.Combobox(frm, textvariable=self.burst_mode_var,
                     values=["Triggered", "Gated", "Infinity"],
                     width=12, state="readonly").grid(
            row=1, column=1, sticky="w", padx=5)

        row("Trigger:", 2)
        self.burst_trig_var = tk.StringVar(value="Immediate")
        ttk.Combobox(frm, textvariable=self.burst_trig_var,
                     values=["Immediate", "External", "Timer", "Bus"],
                     width=12, state="readonly").grid(
            row=2, column=1, sticky="w", padx=5)

        row("Phase:", 3)
        self.burst_phase_var = tk.StringVar(value="0")
        ttk.Entry(frm, textvariable=self.burst_phase_var, width=10).grid(
            row=3, column=1, sticky="w", padx=5)
        ttk.Label(frm, text="°").grid(row=3, column=2, sticky="w")

        ttk.Label(frm,
                  text="(Configure carrier waveform in Standard mode first)",
                  foreground="gray", font=("TkDefaultFont", 8)).grid(
            row=4, column=0, columnspan=3, pady=4)

    # =========================================================================
    # Defaults & Traces
    # =========================================================================

    def _set_defaults(self):
        self._on_mode()
        self._on_wf()

        for var in (self.freq_var, self.freq_unit_var, self.amp_var,
                    self.offset_var, self.phase_var,
                    self.duty_var, self.symm_var,
                    self.pw_var, self.pw_unit_var):
            var.trace_add("write", self._schedule_plot)

        for var in (self.freq_var, self.freq_unit_var,
                    self.pw_var, self.pw_unit_var):
            var.trace_add("write", self._update_pw_display)

    # =========================================================================
    # Mode / Waveform Switching
    # =========================================================================

    def _on_mode(self):
        mode = self.mode_var.get()
        self.std_panel.grid_remove()
        self.sweep_panel.grid_remove()
        self.burst_panel.grid_remove()

        if mode == "Standard":
            self.std_panel.grid()
        elif mode == "Sweep":
            self.sweep_panel.grid()
        elif mode == "Burst":
            self.burst_panel.grid()

        self._update_plot()

    def _on_wf(self):
        wf = self.wf_var.get()
        is_arb = (wf == "Arbitrary")
        no_freq = wf in ("Noise", "DC")
        is_arb_with_comb = (is_arb and self.arb_waveform is not None
                            and hasattr(self.arb_waveform, 'comb_info')
                            and self.arb_waveform.comb_info)

        freq_dis = no_freq or is_arb_with_comb
        self.freq_entry.config(state="disabled" if freq_dis else "normal")
        self.phase_entry.config(state="disabled" if no_freq else "normal")

        # Duty / symmetry visibility
        if wf == "Square":
            self.duty_lbl.grid(); self.duty_entry.grid()
            self.duty_entry.config(state="normal")
            self.pw_frm.grid_remove()
        elif wf == "Pulse":
            self.duty_lbl.grid_remove(); self.duty_entry.grid_remove()
            self.pw_frm.grid()
            self._update_pw_display()
        else:
            self.duty_lbl.grid(); self.duty_entry.grid()
            self.duty_entry.config(state="disabled")
            self.pw_frm.grid_remove()

        self.symm_entry.config(state="normal" if wf == "Ramp" else "disabled")

        if is_arb:
            self.arb_frm.grid()
            if is_arb_with_comb:
                f0 = self.arb_waveform.comb_info['fundamental']
                self.freq_hint.config(
                    text=f"(comb f₀: {f0:.4g} Hz)", foreground="blue")
            elif self.arb_waveform is not None:
                self.freq_hint.config(
                    text="(set by arb dialog)", foreground="blue")
            else:
                self.freq_hint.config(
                    text="(generate or load a waveform first)",
                    foreground="gray")
        else:
            self.arb_frm.grid_remove()
            self.freq_hint.config(text="(e.g. 1/0.1 = 10 Hz)",
                                  foreground="gray")

        self._update_plot()

    def _on_run_mode(self, *_):
        mode = self.run_var.get()
        self.cycles_frm.pack_forget()
        self.dur_frm.pack_forget()
        if mode == "N Cycles":
            self.cycles_frm.pack(side="left", padx=4)
        elif mode == "Duration":
            self.dur_frm.pack(side="left", padx=4)

    def _on_load(self):
        ctl = self.get_controller()
        if not ctl or not ctl.is_connected:
            return
        if self.load_var.get() == "50":
            ctl.set_load_50_ohm(self.channel)
        else:
            ctl.set_load_high_z(self.channel)

    # =========================================================================
    # Plot
    # =========================================================================

    def _schedule_plot(self, *_):
        if not self._update_scheduled:
            self._update_scheduled = True
            self.after(120, self._do_plot)

    def _do_plot(self):
        self._update_scheduled = False
        self._update_plot()

    def _update_plot(self):
        mode = self.mode_var.get()

        if mode == "Sweep":
            try:
                start = self._freq_hz(self.sw_start_var.get(),
                                      self.sw_start_unit.get())
                stop  = self._freq_hz(self.sw_stop_var.get(),
                                      self.sw_stop_unit.get())
                st    = float(self.sw_time_var.get())
                sp    = self.sw_spacing_var.get().lower()
                rt    = float(self.sw_rtime_var.get() or "0")
                hs    = float(self.sw_hstart_var.get() or "0")
                he    = float(self.sw_hstop_var.get() or "0")
                self.plotter.plot_sweep(start, stop, st, sp, hs, he, rt,
                                        channel=self.channel)
                self.plotter.update()
            except Exception:
                pass
            return

        if mode == "Burst":
            # Show the carrier waveform in standard mode
            pass  # fall through to standard plot

        try:
            wf   = self.wf_var.get()
            freq = self._get_freq_hz()
            amp  = float(self.amp_var.get())
            off  = float(self.offset_var.get())
            ph   = float(self.phase_var.get())
            duty = float(self.duty_var.get())
            symm = float(self.symm_var.get())

            arb_data = (self.arb_waveform.data
                        if self.arb_waveform is not None else None)

            self.plotter.plot_waveform(
                wf, freq, amp, off, ph, duty, symm,
                arb_data=arb_data, channel=self.channel)
            self.plotter.update()
        except Exception:
            pass

    # =========================================================================
    # Helpers
    # =========================================================================

    @staticmethod
    def _freq_hz(value_str: str, unit: str) -> float:
        v = float(value_str)
        if unit == "kHz":
            v *= 1e3
        elif unit == "MHz":
            v *= 1e6
        return v

    def _get_freq_hz(self) -> float:
        try:
            txt = self.freq_var.get().strip()
            allowed = set('0123456789.+-*/() eE')
            if all(c in allowed for c in txt):
                v = eval(txt, {"__builtins__": {}}, {})
            else:
                v = float(txt)
            unit = self.freq_unit_var.get()
            if unit == "kHz":
                v *= 1e3
            elif unit == "MHz":
                v *= 1e6
            return float(v)
        except Exception:
            return 1000.0

    def _get_pw_seconds(self) -> float:
        try:
            w = float(self.pw_var.get())
            mult = {"ns": 1e-9, "µs": 1e-6, "ms": 1e-3, "s": 1}
            return w * mult.get(self.pw_unit_var.get(), 1e-6)
        except Exception:
            return 100e-6

    def _update_pw_display(self, *_):
        try:
            freq = self._get_freq_hz()
            if freq <= 0:
                return
            period = 1.0 / freq
            if period >= 1:
                self.period_disp.set(f"{period:.3f} s")
            elif period >= 1e-3:
                self.period_disp.set(f"{period*1e3:.3f} ms")
            elif period >= 1e-6:
                self.period_disp.set(f"{period*1e6:.3f} µs")
            else:
                self.period_disp.set(f"{period*1e9:.3f} ns")

            w_s = self._get_pw_seconds()
            duty = (w_s / period) * 100
            self.calc_duty.set(f"{duty:.1f}%" if duty <= 100 else ">100%!")
        except Exception:
            pass

    def _set_led(self, on: bool):
        self.led.delete("all")
        color = "#00dd00" if on else "#444444"
        self.led.create_oval(2, 2, 18, 18, fill=color, outline="black")

    # =========================================================================
    # Output Toggle
    # =========================================================================

    def _toggle_output(self):
        ctl = self.get_controller()
        if not ctl or not ctl.is_connected:
            self.output_var.set(False)
            self._set_led(False)
            return

        if self.output_var.get():
            run = self.run_var.get()
            ok = ctl.output_on(self.channel)
            if ok:
                self._set_led(True)
                if run == "N Cycles":
                    try:
                        n = int(self.cycles_var.get())
                        freq = self._get_freq_hz()
                        self._schedule_off(n / freq)
                    except Exception:
                        pass
                elif run == "Duration":
                    try:
                        t = float(self.dur_var.get())
                        mult = {"s": 1, "min": 60, "hour": 3600}
                        t_s = t * mult.get(self.dur_unit_var.get(), 1)
                        self._schedule_off(t_s)
                    except Exception:
                        pass
            else:
                self.output_var.set(False)
                self._set_led(False)
        else:
            if self._output_off_job:
                self.after_cancel(self._output_off_job)
                self._output_off_job = None
            ctl.output_off(self.channel)
            self._set_led(False)

    def _schedule_off(self, seconds: float):
        if self._output_off_job:
            self.after_cancel(self._output_off_job)
        self._output_off_job = self.after(
            int(seconds * 1000), self._auto_off)

    def _auto_off(self):
        self._output_off_job = None
        ctl = self.get_controller()
        if ctl and ctl.is_connected:
            ctl.output_off(self.channel)
        self.output_var.set(False)
        self._set_led(False)

    # =========================================================================
    # Apply Settings
    # =========================================================================

    def _apply(self):
        ctl = self.get_controller()
        if not ctl or not ctl.is_connected:
            messagebox.showwarning("Not Connected",
                                   "Please connect to a device first.")
            return

        mode = self.mode_var.get()

        try:
            if mode == "Standard":
                self._apply_standard(ctl)
            elif mode == "Sweep":
                self._apply_sweep(ctl)
            elif mode == "Burst":
                self._apply_burst(ctl)
        except Exception as e:
            messagebox.showerror("Apply Error", str(e))

    def _apply_standard(self, ctl):
        wf    = self.wf_var.get()
        freq  = self._get_freq_hz()
        amp   = float(self.amp_var.get())
        off   = float(self.offset_var.get())
        ph    = float(self.phase_var.get())
        duty  = float(self.duty_var.get())
        symm  = float(self.symm_var.get())

        ok = False
        if wf == "Sine":
            ok = ctl.setup_sine(self.channel, freq, amp, off, ph)
        elif wf == "Square":
            ok = ctl.setup_square(self.channel, freq, amp, off, ph, duty)
        elif wf == "Pulse":
            ok = ctl.setup_pulse(
                self.channel, freq, amp, off, ph,
                width=self._get_pw_seconds())
        elif wf == "Ramp":
            ok = ctl.setup_ramp(self.channel, freq, amp, off, ph, symm)
        elif wf == "Noise":
            ok = ctl.setup_noise(self.channel, amp, off)
        elif wf == "DC":
            ok = ctl.setup_dc(self.channel, off)
        elif wf == "Arbitrary":
            if self.arb_waveform is None:
                messagebox.showwarning("No Waveform",
                                       "Load or generate a waveform first.")
                return
            name = self.arb_waveform.name
            if not ctl.waveform.upload_arbitrary_waveform_from_object(
                    self.channel, self.arb_waveform):
                messagebox.showerror("Upload Failed",
                                     "Arbitrary waveform upload failed.")
                return
            time.sleep(0.3)
            ctl.waveform.select_arbitrary_waveform(self.channel, name)
            if hasattr(self.arb_waveform, 'comb_info') and self.arb_waveform.comb_info:
                arb_freq = self.arb_waveform.comb_info['fundamental']
            else:
                arb_freq = freq
            sr = arb_freq * len(self.arb_waveform.data)
            ctl.waveform.set_arb_sample_rate(self.channel, sr)
            ctl.set_amplitude(self.channel, amp)
            ctl.set_offset(self.channel, off)
            ok = True

        if not ok:
            messagebox.showerror("Command Failed",
                                 "One or more commands failed.")
        else:
            self._update_plot()

    def _apply_sweep(self, ctl):
        start    = self._freq_hz(self.sw_start_var.get(), self.sw_start_unit.get())
        stop     = self._freq_hz(self.sw_stop_var.get(), self.sw_stop_unit.get())
        sw_time  = float(self.sw_time_var.get())
        amp      = float(self.sw_amp_var.get())
        spacing  = self.sw_spacing_var.get().lower()
        ret_time = float(self.sw_rtime_var.get() or "0")
        h_start  = float(self.sw_hstart_var.get() or "0")
        h_stop   = float(self.sw_hstop_var.get() or "0")
        wf       = self.sweep_wf_var.get().lower()
        trig     = self.sw_trig_var.get().lower()

        ok = ctl.setup_sweep(
            channel=self.channel,
            start_freq=start,
            stop_freq=stop,
            sweep_time=sw_time,
            waveform=wf,
            amplitude=amp,
            spacing=spacing,
            return_time=ret_time,
            hold_start=h_start,
            hold_stop=h_stop,
            trigger=trig,
        )
        if not ok:
            messagebox.showerror("Sweep Error", "Failed to configure sweep.")
        else:
            self._update_plot()

    def _apply_burst(self, ctl):
        n     = int(self.burst_n_var.get())
        mode  = self.burst_mode_var.get().lower()
        trig  = self.burst_trig_var.get().lower()
        phase = float(self.burst_phase_var.get())

        ok = ctl.setup_burst(self.channel, n, mode, trig, phase)
        if not ok:
            messagebox.showerror("Burst Error", "Failed to configure burst.")

    # =========================================================================
    # Refresh
    # =========================================================================

    def _refresh(self):
        ctl = self.get_controller()
        if not ctl or not ctl.is_connected:
            return
        # Read back and update UI fields
        freq = ctl.get_frequency(self.channel)
        amp  = ctl.get_amplitude(self.channel)
        off  = ctl.get_offset(self.channel)
        out  = ctl.is_output_on(self.channel)

        if freq is not None:
            self.freq_var.set(f"{freq:.6g}")
            self.freq_unit_var.set("Hz")
        if amp  is not None:
            self.amp_var.set(f"{amp:.4g}")
        if off  is not None:
            self.offset_var.set(f"{off:.4g}")
        self.output_var.set(out)
        self._set_led(out)
        self._update_plot()

    # =========================================================================
    # Arbitrary Waveform Callbacks
    # =========================================================================

    def _load_arb_csv(self):
        path = filedialog.askopenfilename(
            title="Load CSV waveform",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")])
        if not path:
            return
        wf = ArbitraryWaveform()
        try:
            wf.load_csv(path)
        except Exception as e:
            messagebox.showerror("Load Error", str(e))
            return
        self.arb_waveform = wf
        self.arb_name_var.set(f"{wf.name}  ({wf.num_points} pts)")
        self.arb_info_var.set(f"Loaded from {path}")
        self.wf_var.set("Arbitrary")
        self._on_wf()

    def _generate_arb(self):
        def on_generated(wf: ArbitraryWaveform):
            self.arb_waveform = wf
            self.arb_name_var.set(f"{wf.name}  ({wf.num_points} pts)")
            self.arb_info_var.set(wf.description)
            self.wf_var.set("Arbitrary")
            if wf.comb_info:
                self.freq_var.set(f"{wf.comb_info['fundamental']:.6g}")
                self.freq_unit_var.set("Hz")
            else:
                self.freq_var.set(f"{wf.frequency:.6g}")
                self.freq_unit_var.set("Hz")
            self._on_wf()

        ArbGeneratorDialog(self, on_generated)

    def _save_arb_csv(self):
        if self.arb_waveform is None:
            messagebox.showwarning("No Waveform", "No waveform to save.")
            return
        path = filedialog.asksaveasfilename(
            title="Save CSV waveform",
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")])
        if not path:
            return
        try:
            self.arb_waveform.save_csv(path)
        except Exception as e:
            messagebox.showerror("Save Error", str(e))

    def _upload_arb(self):
        ctl = self.get_controller()
        if not ctl or not ctl.is_connected:
            messagebox.showwarning("Not Connected",
                                   "Please connect to a device first.")
            return
        if self.arb_waveform is None:
            messagebox.showwarning("No Waveform",
                                   "Load or generate a waveform first.")
            return
        if not ctl.waveform.upload_arbitrary_waveform_from_object(
                self.channel, self.arb_waveform):
            messagebox.showerror("Upload Failed",
                                 "Waveform upload failed.")
            return
        name = self.arb_waveform.name
        ctl.waveform.select_arbitrary_waveform(self.channel, name)
        messagebox.showinfo("Upload Complete",
                            f"Waveform '{name}' uploaded successfully.")


# =============================================================================
# Presets Panel
# =============================================================================

class PresetsPanel(ttk.LabelFrame):
    """Quick-access preset buttons."""

    def __init__(self, parent, controller_getter):
        super().__init__(parent, text="Quick Presets", padding=8)
        self.get_controller = controller_getter
        self._build()

    def _build(self):
        presets = [
            ("1 kHz Sine 1 Vpp",  self._p_1khz_sine),
            ("10 kHz Sine 5 Vpp", self._p_10khz_sine),
            ("DC 3.3 V",          self._p_dc_3v3),
            ("Reset",             self._p_reset),
        ]
        for i, (label, cmd) in enumerate(presets):
            ttk.Button(self, text=label, command=cmd, width=18).grid(
                row=0, column=i, padx=6, pady=4)

    def _p_1khz_sine(self):
        ctl = self.get_controller()
        if ctl and ctl.is_connected:
            ctl.setup_sine(1, 1000, 1.0, 0)

    def _p_10khz_sine(self):
        ctl = self.get_controller()
        if ctl and ctl.is_connected:
            ctl.setup_sine(1, 10000, 5.0, 0)

    def _p_dc_3v3(self):
        ctl = self.get_controller()
        if ctl and ctl.is_connected:
            ctl.setup_dc(1, 3.3)

    def _p_reset(self):
        ctl = self.get_controller()
        if ctl and ctl.is_connected:
            ctl.reset()


# =============================================================================
# Main Application
# =============================================================================

class KS33500BApp(tk.Tk):
    """Main application window."""

    def __init__(self):
        super().__init__()
        self.title("Keysight 33500B Waveform Generator Controller")
        self.minsize(960, 720)
        self.controller: Optional[KS33500BController] = None
        self._build()

    def _build(self):
        # Connection frame
        conn_frm = ConnectionFrame(self, self._on_connect, self._on_disconnect)
        conn_frm.pack(fill="x", padx=10, pady=6)

        # Channel notebook
        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=10, pady=4)

        self.ch1 = ChannelFrame(nb, 1, self._get_controller)
        self.ch2 = ChannelFrame(nb, 2, self._get_controller)
        nb.add(self.ch1, text=" Channel 1 ")
        nb.add(self.ch2, text=" Channel 2 ")

        # Presets
        PresetsPanel(self, self._get_controller).pack(
            fill="x", padx=10, pady=4)

        # Status bar
        self.status_var = tk.StringVar(value="Ready — not connected")
        ttk.Label(self, textvariable=self.status_var,
                  relief="sunken", anchor="w").pack(
            fill="x", side="bottom", padx=2, pady=2)

        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _get_controller(self) -> Optional[KS33500BController]:
        return self.controller

    def _on_connect(self, resource: str) -> bool:
        self.controller = KS33500BController()
        if self.controller.connect(resource):
            self.status_var.set(f"Connected: {self.controller.idn}")
            return True
        self.controller = None
        self.status_var.set("Connection failed")
        return False

    def _on_disconnect(self):
        if self.controller:
            self.controller.disconnect()
            self.controller = None
        self.status_var.set("Disconnected")

    def _on_close(self):
        if self.controller and self.controller.is_connected:
            self.controller.all_outputs_off()
            self.controller.disconnect()
        self.destroy()


# =============================================================================
# Entry Point
# =============================================================================

def main():
    app = KS33500BApp()
    app.mainloop()


if __name__ == "__main__":
    main()
