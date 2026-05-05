"""
tic_connection.py

Low-level RS-232 connection layer for the Edwards TIC (Turbo Instrument Controller).

Protocol
--------
  Query      : ?V<id>\r
  Query resp : =V<id> <value>[;<extra>...]\r  (success)
               *V<id> <code>\r                (error)
  Write      : !C<id> <value>\r
  Write resp : *C<id> 0\r                    (success, code 0)
               *C<id> <code>\r               (error, non-zero code)

Values are returned in SI units (Pa for pressure).  Callers are responsible
for unit conversion.

Date: 2026-04-16
"""

from __future__ import annotations

import re
import threading
import time
from typing import Optional

try:
    import serial
    SERIAL_AVAILABLE = True
except ImportError:
    SERIAL_AVAILABLE = False


class TICConnection:
    """
    Manages a single RS-232 session with the Edwards TIC.

    Typical use:
        conn = TICConnection("COM3")
        conn.connect()
        value = conn.query(913)   # read parameter 913
        conn.write_param(910, 1)  # start turbo pump
        conn.disconnect()

    Context manager:
        with TICConnection("COM3") as conn:
            value = conn.query(914)
    """

    DEFAULT_BAUDRATE  = 9600
    DEFAULT_TIMEOUT   = 2.0   # seconds

    def __init__(self, port: str = "COM3", baudrate: int = DEFAULT_BAUDRATE,
                 timeout: float = DEFAULT_TIMEOUT):
        self._port     = port
        self._baudrate = baudrate
        self._timeout  = timeout
        self._ser: Optional[serial.Serial] = None
        self._lock = threading.Lock()   # serialise concurrent poll / command threads
        self._last_cmd_t: float = 0.0   # monotonic time of last completed command
        self._min_gap_s:  float = 0.05  # 50 ms — TIC needs time between commands

    # =========================================================================
    # Properties
    # =========================================================================

    @property
    def is_connected(self) -> bool:
        return self._ser is not None and self._ser.is_open

    @property
    def port(self) -> str:
        return self._port

    @property
    def baudrate(self) -> int:
        return self._baudrate

    # =========================================================================
    # Connection management
    # =========================================================================

    def connect(self, port: Optional[str] = None,
                baudrate: Optional[int] = None) -> bool:
        """
        Open the serial port.

        Args:
            port:     Override the port set at construction time.
            baudrate: Override the baud rate set at construction time.

        Returns:
            True if the port opened successfully.
        """
        if not SERIAL_AVAILABLE:
            raise RuntimeError("pyserial not installed — run: pip install pyserial")

        if port:
            self._port = port
        if baudrate:
            self._baudrate = baudrate

        if self.is_connected:
            return True

        try:
            self._ser = serial.Serial(
                self._port,
                baudrate=self._baudrate,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=self._timeout,
            )
            print(f"Connected to Edwards TIC on {self._port} at {self._baudrate} baud")
            return True
        except serial.SerialException as e:
            print(f"Connection error: {e}")
            self._ser = None
            return False

    def disconnect(self) -> None:
        """Close the serial port."""
        if self._ser and self._ser.is_open:
            self._ser.close()
        self._ser = None
        print("Disconnected from Edwards TIC")

    # =========================================================================
    # Raw I/O
    # =========================================================================

    def _send(self, command: str) -> str:
        """
        Send a command string and return the raw response line.

        Raises:
            RuntimeError: if not connected
            IOError:      if no response received
        """
        with self._lock:
            if not self.is_connected:
                raise RuntimeError("Not connected to TIC")

            # Edwards TIC needs a minimum gap between successive RS-232 commands.
            # Without this, a write fired immediately after a read is rejected (*V... 2).
            gap = self._min_gap_s - (time.monotonic() - self._last_cmd_t)
            if gap > 0:
                time.sleep(gap)

            self._ser.reset_input_buffer()
            self._ser.write(command.encode("ascii"))
            raw = self._ser.read_until(b"\r").decode("ascii", errors="replace").strip()
            self._last_cmd_t = time.monotonic()

            if command.startswith("!"):
                print(f"[TIC] WRITE  sent={command.strip()!r}  raw={raw!r}", flush=True)

            if not raw:
                raise IOError(f"No response to command {command!r} — check cable and port")

            return raw

    @staticmethod
    def _parse_response(raw: str, param_id: int) -> str:
        """
        Parse a TIC query response (=V) and return the first value field.

        Raises:
            IOError: on TIC error response or unrecognised format
        """
        if raw.startswith("*"):
            raise IOError(f"TIC error for parameter {param_id}: {raw!r}")

        match = re.match(r"=V\d+\s+([\S]+)", raw)
        if not match:
            raise IOError(f"Unexpected TIC response for parameter {param_id}: {raw!r}")

        return match.group(1).split(";")[0]

    @staticmethod
    def _parse_command_response(raw: str, param_id: int) -> None:
        """
        Parse a TIC command response (*C<id> <code>) where code 0 means success.

        Raises:
            IOError: on non-zero error code or unrecognised format
        """
        match = re.match(r"\*C\d+\s+(\d+)", raw)
        if not match:
            raise IOError(f"Unexpected TIC command response for {param_id}: {raw!r}")
        code = int(match.group(1))
        if code != 0:
            raise IOError(f"TIC command error {code} for parameter {param_id}: {raw!r}")

    # =========================================================================
    # Public query / write
    # =========================================================================

    def query(self, param_id: int) -> str:
        """
        Send a ?V<id> query and return the first value field as a string.

        Args:
            param_id: TIC parameter number (e.g. 913 for WRG pressure).

        Returns:
            String representation of the first value field.

        Raises:
            RuntimeError, IOError, serial.SerialException
        """
        raw = self._send(f"?V{param_id}\r")
        return self._parse_response(raw, param_id)

    def query_float(self, param_id: int) -> float:
        """Convenience wrapper — returns query result as float."""
        return float(self.query(param_id))

    def query_int(self, param_id: int) -> int:
        """Convenience wrapper — returns query result as int."""
        return int(self.query(param_id))

    def write_param(self, param_id: int, value) -> bool:
        """
        Send a !C<id> <value> command to set a TIC parameter.

        Args:
            param_id: TIC parameter number (e.g. 910 to start/stop pump).
            value:    Value to write (converted to string).

        Returns:
            True if the TIC acknowledged the command.
        """
        raw = self._send(f"!C{param_id} {value}\r")
        try:
            self._parse_command_response(raw, param_id)
            return True
        except IOError as e:
            print(f"Write error: {e}")
            return False

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

    with TICConnection(port) as conn:
        print(f"\nRaw query for parameter 913: {conn.query(913)}")
        print(f"Raw query for parameter 914: {conn.query(914)}")
