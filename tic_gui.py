"""
tic_gui.py

Tkinter GUI for the Edwards TIC (Turbo Instrument Controller).

Features:
  - COM port connection panel with manual entry and port scan
  - Live pressure gauge display (auto-refresh, configurable interval)
  - Pressure history strip-chart (matplotlib)
  - Turbo pump control: start/stop, speed setpoint, live telemetry
  - Status bar

Date: 2026-04-16
"""

from __future__ import annotations

import threading
import time
from collections import deque
from typing import Optional

import tkinter as tk
from tkinter import ttk, messagebox

import matplotlib
matplotlib.use("TkAgg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import numpy as np

from tic_controller import TICController


# =============================================================================
# Helpers
# =============================================================================

def _fmt_pressure(mbar: Optional[float]) -> str:
    """Format a pressure value for display."""
    if mbar is None:
        return "---"
    if mbar <= 0:
        return "< range"
    return f"{mbar:.3e} mbar"


def _pressure_color(mbar: Optional[float]) -> str:
    """Return a foreground color appropriate for the pressure value."""
    if mbar is None:
        return "gray"
    if mbar > 1e-2:
        return "red"
    if mbar > 1e-5:
        return "orange"
    return "green"


# =============================================================================
# Connection Frame
# =============================================================================

class ConnectionFrame(ttk.LabelFrame):
    """Top panel: COM port entry, scan, connect/disconnect."""

    def __init__(self, parent, on_connect, on_disconnect):
        super().__init__(parent, text="Connection", padding=10)
        self.on_connect    = on_connect
        self.on_disconnect = on_disconnect
        self._build()

    def _build(self):
        # Port row
        ttk.Label(self, text="COM Port:").grid(
            row=0, column=0, sticky="e", padx=5, pady=4)
        self.port_var = tk.StringVar(value="COM3")
        self.port_entry = ttk.Entry(self, textvariable=self.port_var, width=10)
        self.port_entry.grid(row=0, column=1, sticky="w", padx=5, pady=4)

        self.scan_btn = ttk.Button(self, text="Scan Ports", command=self._scan)
        self.scan_btn.grid(row=0, column=2, padx=5, pady=4)

        # Baud rate
        ttk.Label(self, text="Baud Rate:").grid(
            row=0, column=3, sticky="e", padx=(15, 5), pady=4)
        self.baud_var = tk.StringVar(value="9600")
        ttk.Combobox(self, textvariable=self.baud_var,
                     values=["9600", "19200", "38400", "57600", "115200"],
                     width=9, state="readonly").grid(
            row=0, column=4, sticky="w", padx=5, pady=4)

        # Connect / Disconnect / Status
        self.connect_btn = ttk.Button(
            self, text="Connect", command=self._connect)
        self.connect_btn.grid(row=0, column=5, padx=8, pady=4)

        self.disconnect_btn = ttk.Button(
            self, text="Disconnect", command=self._disconnect, state="disabled")
        self.disconnect_btn.grid(row=0, column=6, padx=5, pady=4)

        self.status_lbl = ttk.Label(self, text="Not connected", foreground="red")
        self.status_lbl.grid(row=0, column=7, padx=15, pady=4, sticky="w")

    def _scan(self):
        """Scan for available COM ports and populate the entry."""
        self.scan_btn.config(state="disabled")
        self.status_lbl.config(text="Scanning...", foreground="orange")
        self.update()

        def do_scan():
            try:
                import serial.tools.list_ports
                ports = [p.device for p in serial.tools.list_ports.comports()]
            except Exception:
                ports = []
            self.after(0, lambda: self._scan_done(ports))

        threading.Thread(target=do_scan, daemon=True).start()

    def _scan_done(self, ports):
        self.scan_btn.config(state="normal")
        if ports:
            self.port_var.set(ports[0])
            self.status_lbl.config(
                text=f"Found: {', '.join(ports)}", foreground="blue")
        else:
            self.status_lbl.config(text="No COM ports found", foreground="red")

    def _connect(self):
        port = self.port_var.get().strip()
        if not port:
            messagebox.showwarning("No Port", "Enter a COM port first.")
            return
        self.status_lbl.config(text="Connecting...", foreground="orange")
        self.update()
        if self.on_connect(port, int(self.baud_var.get())):
            self.connect_btn.config(state="disabled")
            self.disconnect_btn.config(state="normal")
            self.port_entry.config(state="disabled")
            self.scan_btn.config(state="disabled")
            self.status_lbl.config(
                text=f"Connected ({port})", foreground="green")
        else:
            self.status_lbl.config(text="Connection failed", foreground="red")

    def _disconnect(self):
        self.on_disconnect()
        self.connect_btn.config(state="normal")
        self.disconnect_btn.config(state="disabled")
        self.port_entry.config(state="normal")
        self.scan_btn.config(state="normal")
        self.status_lbl.config(text="Disconnected", foreground="red")


# =============================================================================
# Gauge Panel
# =============================================================================

HISTORY_LEN = 300   # number of data points kept for the strip chart


class GaugePanel(ttk.LabelFrame):
    """
    Displays live pressure readings and a scrolling history plot.
    """

    def __init__(self, parent, controller_getter):
        super().__init__(parent, text="Pressure Gauges", padding=10)
        self.get_controller = controller_getter

        self._history_t:    deque = deque(maxlen=HISTORY_LEN)
        self._history_wrg:  deque = deque(maxlen=HISTORY_LEN)
        self._history_apgx: deque = deque(maxlen=HISTORY_LEN)
        self._t0 = time.monotonic()

        self._auto_refresh = False
        self._refresh_job  = None

        self._build()

    def _build(self):
        top = ttk.Frame(self)
        top.grid(row=0, column=0, sticky="ew")
        self.columnconfigure(0, weight=1)

        # WRG display
        ttk.Label(top, text="WRG (Gauge 1):", font=("TkDefaultFont", 10, "bold")).grid(
            row=0, column=0, sticky="w", padx=8, pady=4)
        self.wrg_var = tk.StringVar(value="---")
        self.wrg_lbl = ttk.Label(top, textvariable=self.wrg_var,
                                  font=("Courier", 14, "bold"), foreground="gray")
        self.wrg_lbl.grid(row=0, column=1, sticky="w", padx=8, pady=4)

        # APGX display
        ttk.Label(top, text="APGX (Gauge 2):", font=("TkDefaultFont", 10, "bold")).grid(
            row=1, column=0, sticky="w", padx=8, pady=4)
        self.apgx_var = tk.StringVar(value="---")
        self.apgx_lbl = ttk.Label(top, textvariable=self.apgx_var,
                                   font=("Courier", 14, "bold"), foreground="gray")
        self.apgx_lbl.grid(row=1, column=1, sticky="w", padx=8, pady=4)

        # Controls row
        ctrl = ttk.Frame(top)
        ctrl.grid(row=0, column=2, rowspan=2, sticky="e", padx=10)

        ttk.Button(ctrl, text="Read Now", command=self._read_once).pack(
            side="left", padx=4)

        self.auto_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(ctrl, text="Auto-refresh", variable=self.auto_var,
                         command=self._toggle_auto).pack(side="left", padx=4)

        ttk.Label(ctrl, text="Interval (s):").pack(side="left", padx=(8, 2))
        self.interval_var = tk.StringVar(value="2")
        ttk.Spinbox(ctrl, textvariable=self.interval_var,
                    from_=1, to=60, width=5).pack(side="left", padx=4)

        ttk.Button(ctrl, text="Clear History",
                   command=self._clear_history).pack(side="left", padx=8)

        # Matplotlib strip chart
        self.fig, self.ax = plt.subplots(figsize=(7, 2.5), dpi=90)
        self.fig.patch.set_facecolor("#f0f0f0")
        self.ax.set_facecolor("#f8f8f8")
        self.ax.set_xlabel("Time (s)")
        self.ax.set_ylabel("Pressure (mbar)")
        self.ax.set_yscale("log")
        self.ax.grid(True, which="both", linestyle="--", alpha=0.5)
        self._line_wrg,  = self.ax.plot([], [], "b-o", ms=3, label="WRG")
        self._line_apgx, = self.ax.plot([], [], "r-s", ms=3, label="APGX")
        self.ax.legend(loc="upper left", fontsize=8)
        self.fig.tight_layout()

        canvas = FigureCanvasTkAgg(self.fig, master=self)
        canvas.get_tk_widget().grid(row=1, column=0, sticky="nsew", padx=5, pady=5)
        self._canvas = canvas
        self.rowconfigure(1, weight=1)

    # =========================================================================
    # Reading logic
    # =========================================================================

    def _read_once(self):
        ctl = self.get_controller()
        if not ctl or not ctl.is_connected:
            messagebox.showwarning("Not Connected",
                                   "Connect to the TIC first.")
            return
        threading.Thread(target=self._do_read, daemon=True).start()

    def _do_read(self):
        ctl = self.get_controller()
        if not ctl:
            return
        try:
            gs = ctl.read_gauges()
            self.after(0, lambda: self._update_display(gs))
        except Exception as e:
            self.after(0, lambda: self._show_error(str(e)))

    def _update_display(self, gs):
        # WRG
        wrg_val = gs.wrg.value_mbar
        self.wrg_var.set(_fmt_pressure(wrg_val))
        self.wrg_lbl.config(foreground=_pressure_color(wrg_val))

        # APGX
        apgx_val = gs.apgx.value_mbar
        self.apgx_var.set(_fmt_pressure(apgx_val))
        self.apgx_lbl.config(foreground=_pressure_color(apgx_val))

        # History
        t = time.monotonic() - self._t0
        self._history_t.append(t)
        self._history_wrg.append(wrg_val if (wrg_val and wrg_val > 0) else None)
        self._history_apgx.append(apgx_val if (apgx_val and apgx_val > 0) else None)
        self._redraw_chart()

    def _show_error(self, msg):
        self.wrg_var.set("ERROR")
        self.wrg_lbl.config(foreground="red")
        self.apgx_var.set("ERROR")
        self.apgx_lbl.config(foreground="red")

    def _redraw_chart(self):
        t_arr    = np.array(self._history_t, dtype=float)
        wrg_arr  = np.array([v if v else np.nan for v in self._history_wrg])
        apgx_arr = np.array([v if v else np.nan for v in self._history_apgx])

        self._line_wrg.set_data(t_arr, wrg_arr)
        self._line_apgx.set_data(t_arr, apgx_arr)

        valid = np.concatenate([wrg_arr[~np.isnan(wrg_arr)],
                                 apgx_arr[~np.isnan(apgx_arr)]])
        if len(valid) > 0:
            ymin = max(valid.min() * 0.1, 1e-12)
            ymax = valid.max() * 10
            self.ax.set_ylim(ymin, ymax)

        if len(t_arr) > 1:
            self.ax.set_xlim(t_arr[0], max(t_arr[-1], t_arr[0] + 10))

        self._canvas.draw_idle()

    def _clear_history(self):
        self._history_t.clear()
        self._history_wrg.clear()
        self._history_apgx.clear()
        self._t0 = time.monotonic()
        self._line_wrg.set_data([], [])
        self._line_apgx.set_data([], [])
        self._canvas.draw_idle()

    # =========================================================================
    # Auto-refresh
    # =========================================================================

    def _toggle_auto(self):
        if self.auto_var.get():
            self._auto_refresh = True
            self._schedule_next()
        else:
            self._auto_refresh = False
            if self._refresh_job:
                self.after_cancel(self._refresh_job)
                self._refresh_job = None

    def _schedule_next(self):
        if not self._auto_refresh:
            return
        try:
            interval_ms = int(float(self.interval_var.get()) * 1000)
        except ValueError:
            interval_ms = 2000
        self._refresh_job = self.after(interval_ms, self._auto_tick)

    def _auto_tick(self):
        ctl = self.get_controller()
        if ctl and ctl.is_connected:
            threading.Thread(target=self._do_read, daemon=True).start()
        self._schedule_next()

    def stop_auto(self):
        """Stop any running auto-refresh (called on disconnect/close)."""
        self._auto_refresh = False
        self.auto_var.set(False)
        if self._refresh_job:
            self.after_cancel(self._refresh_job)
            self._refresh_job = None


# =============================================================================
# Pump Panel
# =============================================================================

class PumpPanel(ttk.LabelFrame):
    """Turbo pump control: start/stop, speed setpoint, live telemetry."""

    def __init__(self, parent, controller_getter):
        super().__init__(parent, text="Turbo Pump", padding=10)
        self.get_controller = controller_getter
        self._poll_job  = None
        self._polling   = False
        self._build()

    def _build(self):
        # ---- Control column ----
        ctrl = ttk.LabelFrame(self, text="Controls", padding=8)
        ctrl.grid(row=0, column=0, sticky="ns", padx=(0, 10))

        # Start / Stop buttons
        btn_row = ttk.Frame(ctrl)
        btn_row.grid(row=0, column=0, columnspan=2, pady=6)

        self.start_btn = ttk.Button(btn_row, text="START Pump",
                                     command=self._start_pump, width=14)
        self.start_btn.pack(side="left", padx=6)
        self.stop_btn  = ttk.Button(btn_row, text="STOP Pump",
                                     command=self._stop_pump, width=14)
        self.stop_btn.pack(side="left", padx=6)

        # Speed setpoint
        spd_frm = ttk.LabelFrame(ctrl, text="Speed Setpoint", padding=6)
        spd_frm.grid(row=1, column=0, columnspan=2, sticky="ew", pady=6)

        self.speed_var = tk.IntVar(value=100)
        self.speed_scale = ttk.Scale(spd_frm, from_=0, to=100,
                                      variable=self.speed_var,
                                      orient="horizontal", length=180,
                                      command=self._on_scale)
        self.speed_scale.grid(row=0, column=0, padx=5, pady=4)
        self.speed_disp = tk.StringVar(value="100%")
        ttk.Label(spd_frm, textvariable=self.speed_disp, width=5).grid(
            row=0, column=1, padx=5)

        ttk.Button(spd_frm, text="Set Speed",
                   command=self._set_speed).grid(
            row=1, column=0, columnspan=2, pady=4)

        # Poll controls
        poll_frm = ttk.LabelFrame(ctrl, text="Telemetry Poll", padding=6)
        poll_frm.grid(row=2, column=0, columnspan=2, sticky="ew", pady=6)

        ttk.Button(poll_frm, text="Read Now",
                   command=self._read_once).grid(row=0, column=0, padx=5, pady=4)

        self.poll_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(poll_frm, text="Auto-poll",
                         variable=self.poll_var,
                         command=self._toggle_poll).grid(row=0, column=1, padx=5)

        ttk.Label(poll_frm, text="Interval (s):").grid(row=1, column=0, sticky="e", padx=5)
        self.poll_interval_var = tk.StringVar(value="2")
        ttk.Spinbox(poll_frm, textvariable=self.poll_interval_var,
                    from_=1, to=60, width=6).grid(row=1, column=1, sticky="w", padx=5)

        # ---- Telemetry column ----
        tel = ttk.LabelFrame(self, text="Telemetry", padding=8)
        tel.grid(row=0, column=1, sticky="nsew")
        self.columnconfigure(1, weight=1)

        fields = [
            ("Status",      "status_var",   "Unknown"),
            ("Speed",       "speed_rd_var",  "---"),
            ("Power",       "power_var",    "---"),
            ("Current",     "current_var",  "---"),
            ("Voltage",     "voltage_var",  "---"),
            ("Temperature", "temp_var",     "---"),
        ]
        self._tel_vars = {}
        for i, (label, attr, default) in enumerate(fields):
            ttk.Label(tel, text=f"{label}:", font=("TkDefaultFont", 10, "bold")).grid(
                row=i, column=0, sticky="e", padx=8, pady=4)
            var = tk.StringVar(value=default)
            setattr(self, attr, var)
            self._tel_vars[attr] = var
            lbl = ttk.Label(tel, textvariable=var,
                            font=("Courier", 11), width=18)
            lbl.grid(row=i, column=1, sticky="w", padx=8, pady=4)
            if attr == "status_var":
                self._status_lbl = lbl

        # Status LED
        self.led_canvas = tk.Canvas(tel, width=20, height=20)
        self.led_canvas.grid(row=0, column=2, padx=8)
        self._set_led(False)

    # =========================================================================
    # Pump commands
    # =========================================================================

    def _start_pump(self):
        ctl = self.get_controller()
        if not ctl or not ctl.is_connected:
            messagebox.showwarning("Not Connected", "Connect to the TIC first.")
            return
        if not messagebox.askyesno("Confirm", "Start the turbo pump?"):
            return
        threading.Thread(target=ctl.start_pump, daemon=True).start()

    def _stop_pump(self):
        ctl = self.get_controller()
        if not ctl or not ctl.is_connected:
            messagebox.showwarning("Not Connected", "Connect to the TIC first.")
            return
        if not messagebox.askyesno("Confirm", "Stop the turbo pump?"):
            return
        threading.Thread(target=ctl.stop_pump, daemon=True).start()

    def _on_scale(self, _=None):
        self.speed_disp.set(f"{int(self.speed_var.get())}%")

    def _set_speed(self):
        ctl = self.get_controller()
        if not ctl or not ctl.is_connected:
            messagebox.showwarning("Not Connected", "Connect to the TIC first.")
            return
        pct = int(self.speed_var.get())
        threading.Thread(target=lambda: ctl.set_pump_speed(pct),
                         daemon=True).start()

    # =========================================================================
    # Telemetry display
    # =========================================================================

    def _read_once(self):
        ctl = self.get_controller()
        if not ctl or not ctl.is_connected:
            messagebox.showwarning("Not Connected", "Connect to the TIC first.")
            return
        threading.Thread(target=self._do_read, daemon=True).start()

    def _do_read(self):
        ctl = self.get_controller()
        if not ctl:
            return
        try:
            tel = ctl.read_pump()
            self.after(0, lambda: self._update_display(tel))
        except Exception as e:
            self.after(0, lambda: self._show_error(str(e)))

    def _update_display(self, tel):
        self.status_var.set(tel.status_str)
        color = "green" if tel.is_running else ("red" if tel.has_fault else "gray")
        self._status_lbl.config(foreground=color)
        self._set_led(tel.is_running)

        self.speed_rd_var.set(f"{tel.speed_pct}%" if tel.speed_pct is not None else "---")
        self.power_var.set(f"{tel.power_w:.1f} W" if tel.power_w is not None else "---")
        self.current_var.set(f"{tel.current_a:.2f} A" if tel.current_a is not None else "---")
        self.voltage_var.set(f"{tel.voltage_v:.1f} V" if tel.voltage_v is not None else "---")
        self.temp_var.set(f"{tel.temp_c:.1f} °C" if tel.temp_c is not None else "---")

    def _show_error(self, msg):
        self.status_var.set("READ ERROR")
        self._status_lbl.config(foreground="red")
        self._set_led(False)

    def _set_led(self, on: bool):
        self.led_canvas.delete("all")
        color = "#00cc00" if on else "#444444"
        self.led_canvas.create_oval(2, 2, 18, 18, fill=color, outline="black")

    # =========================================================================
    # Auto-poll
    # =========================================================================

    def _toggle_poll(self):
        if self.poll_var.get():
            self._polling = True
            self._schedule_next()
        else:
            self._polling = False
            if self._poll_job:
                self.after_cancel(self._poll_job)
                self._poll_job = None

    def _schedule_next(self):
        if not self._polling:
            return
        try:
            interval_ms = int(float(self.poll_interval_var.get()) * 1000)
        except ValueError:
            interval_ms = 2000
        self._poll_job = self.after(interval_ms, self._poll_tick)

    def _poll_tick(self):
        ctl = self.get_controller()
        if ctl and ctl.is_connected:
            threading.Thread(target=self._do_read, daemon=True).start()
        self._schedule_next()

    def stop_poll(self):
        """Stop any running auto-poll (called on disconnect/close)."""
        self._polling = False
        self.poll_var.set(False)
        if self._poll_job:
            self.after_cancel(self._poll_job)
            self._poll_job = None


# =============================================================================
# Main Application
# =============================================================================

class TICApp(tk.Tk):
    """Main application window for the Edwards TIC controller."""

    def __init__(self):
        super().__init__()
        self.title("Edwards TIC Controller")
        self.minsize(900, 680)
        self.controller: Optional[TICController] = None
        self._build()

    def _build(self):
        # Connection frame
        self.conn_frame = ConnectionFrame(
            self, self._on_connect, self._on_disconnect)
        self.conn_frame.pack(fill="x", padx=10, pady=6)

        # Notebook: Gauges | Pump
        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=10, pady=4)

        self.gauge_panel = GaugePanel(nb, self._get_controller)
        nb.add(self.gauge_panel, text="  Pressure Gauges  ")

        self.pump_panel = PumpPanel(nb, self._get_controller)
        nb.add(self.pump_panel, text="  Turbo Pump  ")

        # Status bar
        self.status_var = tk.StringVar(value="Ready — not connected")
        ttk.Label(self, textvariable=self.status_var,
                  relief="sunken", anchor="w").pack(
            fill="x", side="bottom", padx=2, pady=2)

        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # =========================================================================
    # Controller access
    # =========================================================================

    def _get_controller(self) -> Optional[TICController]:
        return self.controller

    # =========================================================================
    # Connection callbacks
    # =========================================================================

    def _on_connect(self, port: str, baudrate: int) -> bool:
        self.controller = TICController(port, baudrate)
        if self.controller.connect():
            self.status_var.set(f"Connected to Edwards TIC on {port}")
            return True
        self.controller = None
        self.status_var.set("Connection failed — check port and cable")
        return False

    def _on_disconnect(self):
        self.gauge_panel.stop_auto()
        self.pump_panel.stop_poll()
        if self.controller:
            self.controller.disconnect()
            self.controller = None
        self.status_var.set("Disconnected")

    # =========================================================================
    # Close
    # =========================================================================

    def _on_close(self):
        self.gauge_panel.stop_auto()
        self.pump_panel.stop_poll()
        if self.controller and self.controller.is_connected:
            self.controller.disconnect()
        plt.close("all")
        self.destroy()


# =============================================================================
# Entry point
# =============================================================================

def main():
    app = TICApp()
    app.mainloop()


if __name__ == "__main__":
    main()
