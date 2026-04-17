"""
Keysight 33500B Waveform Generator - Connection Module

This module handles VISA communication with the Keysight 33500B series
waveform generators (33511B, 33512B, 33521B, 33522B). It provides device
discovery over USB and LAN, connection management, and low-level SCPI
command communication.

Date: 2026-04-16
"""

import pyvisa
from typing import Optional, List, Tuple
import threading
import time


class KS33500BConnection:
    """
    Manages VISA connection to Keysight 33500B waveform generator.

    This class handles:
    - Device discovery (USB and LAN)
    - Connection establishment and teardown
    - Low-level SCPI command sending and querying
    - Error checking and status queries
    """

    # Keysight / Agilent USB Vendor ID
    KEYSIGHT_VID = "0x0957"
    # Known IDN substrings for 33500B series
    KEYSIGHT_IDS = ["Keysight Technologies", "Agilent Technologies"]
    KS33500B_MODELS = ["33511B", "33512B", "33521B", "33522B",
                       "33511A", "33512A", "33521A", "33522A",
                       "335"]  # broad fallback

    def __init__(self, resource_name: Optional[str] = None, timeout: int = 5000):
        """
        Initialize the connection object.

        Args:
            resource_name: VISA resource string, e.g.
                           'USB0::0x0957::0x2C07::MY57XXXXXX::INSTR'
                           'TCPIP0::192.168.1.100::inst0::INSTR'
                           If None, use discover_devices() and connect() later.
            timeout: Communication timeout in milliseconds (default: 5000 ms)
        """
        self._rm: Optional[pyvisa.ResourceManager] = None
        self._instrument: Optional[pyvisa.resources.Resource] = None
        self._resource_name: Optional[str] = resource_name
        self._timeout = timeout
        self._connected = False
        self._idn_string: Optional[str] = None

    # =========================================================================
    # Properties
    # =========================================================================

    @property
    def is_connected(self) -> bool:
        """Return True if connected to instrument."""
        return self._connected

    @property
    def idn(self) -> Optional[str]:
        """Return the instrument identification string."""
        return self._idn_string

    @property
    def resource_name(self) -> Optional[str]:
        """Return the current VISA resource name."""
        return self._resource_name

    # =========================================================================
    # Resource Manager
    # =========================================================================

    def _init_resource_manager(self, backend: str = '') -> None:
        """
        Initialize the VISA resource manager if not already initialized.

        Args:
            backend: VISA backend. '' = auto-detect, '@py' = pyvisa-py, '@ni' = NI-VISA.
        """
        if self._rm is None:
            try:
                self._rm = pyvisa.ResourceManager(backend)
                print(f"Using VISA backend: {self._rm.visalib}")
            except Exception as e:
                print(f"Error initializing ResourceManager with '{backend}': {e}")
                if backend != '@py':
                    try:
                        self._rm = pyvisa.ResourceManager('@py')
                        print(f"Fallback to pyvisa-py backend: {self._rm.visalib}")
                    except Exception as e2:
                        print(f"Fallback also failed: {e2}")
                        raise

    # =========================================================================
    # Discovery
    # =========================================================================

    def list_resources(self, query: str = '?*::INSTR') -> List[str]:
        """
        List available VISA resources without querying them.

        Args:
            query: VISA resource query pattern.
                   '?*::INSTR'     = all instruments
                   'USB?*::INSTR'  = USB only
                   'TCPIP?*::INSTR' = LAN only

        Returns:
            List of resource strings
        """
        self._init_resource_manager()
        try:
            resources = list(self._rm.list_resources(query))
            print(f"Found {len(resources)} VISA resource(s): {resources}")
            return resources
        except Exception as e:
            print(f"Error listing resources: {e}")
            return []

    def discover_devices(self, filter_keysight: bool = True,
                         query: str = '?*::INSTR') -> List[Tuple[str, str]]:
        """
        Discover available VISA instruments by querying each one.

        Args:
            filter_keysight: If True, only return Keysight/Agilent 33500B devices.
            query: VISA resource query pattern.

        Returns:
            List of tuples: (resource_name, idn_string)
        """
        self._init_resource_manager()
        devices = []

        try:
            resources = self._rm.list_resources(query)
            # Skip serial ports which can hang
            resources = [r for r in resources if not r.startswith('ASRL')]
            print(f"Scanning {len(resources)} resource(s)...")
        except Exception as e:
            print(f"Error listing resources: {e}")
            return devices

        for resource in resources:
            print(f"  Trying: {resource}...", end=" ")

            result = {"idn": None, "error": None, "instr": None}

            def query_device(res=resource):
                try:
                    instr = self._rm.open_resource(res)
                    result["instr"] = instr
                    instr.timeout = 2000
                    instr.read_termination = '\n'
                    instr.write_termination = '\n'
                    result["idn"] = instr.query("*IDN?").strip()
                except Exception as e:
                    result["error"] = e
                finally:
                    if result["instr"] is not None:
                        try:
                            result["instr"].close()
                        except Exception:
                            pass
                    result["instr"] = None

            thread = threading.Thread(target=query_device)
            thread.daemon = True
            thread.start()
            thread.join(timeout=3)

            if thread.is_alive():
                print("TIMEOUT (>3s) - skipping")
                continue

            if result["error"] is not None:
                print(f"ERROR: {result['error']} - skipping")
                continue

            idn = result["idn"]
            if idn is None:
                print("No response - skipping")
                continue

            print(f"OK - {idn[:50]}...")

            if filter_keysight:
                is_keysight = any(kid.upper() in idn.upper()
                                  for kid in self.KEYSIGHT_IDS)
                if is_keysight:
                    is_33500b = any(model in idn for model in self.KS33500B_MODELS)
                    if is_33500b:
                        devices.append((resource, idn))
                        print("   -> Keysight 33500B series found.")
            else:
                devices.append((resource, idn))

        return devices

    # =========================================================================
    # Connection
    # =========================================================================

    def connect(self, resource_name: Optional[str] = None) -> bool:
        """
        Connect to the instrument.

        Args:
            resource_name: VISA resource string. If None, uses the one from __init__.

        Returns:
            True if connection successful.
        """
        if resource_name:
            self._resource_name = resource_name

        if not self._resource_name:
            print("Error: No resource name specified")
            return False

        self._init_resource_manager()

        try:
            self._instrument = self._rm.open_resource(self._resource_name)
            self._instrument.timeout = self._timeout

            # Configure line termination
            self._instrument.read_termination = '\n'
            self._instrument.write_termination = '\n'

            # Clear any pending data
            try:
                self._instrument.clear()
            except Exception:
                pass

            # Query identification to verify connection
            self._idn_string = self.query("*IDN?")

            if self._idn_string:
                self._connected = True
                print(f"Connected to: {self._idn_string}")
                return True
            else:
                print("Error: No response from instrument")
                return False

        except Exception as e:
            print(f"Connection error: {e}")
            self._connected = False
            return False

    def disconnect(self) -> None:
        """Disconnect from the instrument."""
        if self._instrument:
            try:
                self._instrument.close()
            except Exception:
                pass
            self._instrument = None
        self._connected = False
        self._idn_string = None
        print("Disconnected from instrument")

    # =========================================================================
    # SCPI I/O
    # =========================================================================

    def write(self, command: str) -> bool:
        """
        Send a SCPI command to the instrument (no response expected).

        Args:
            command: SCPI command string.

        Returns:
            True if successful.
        """
        if not self._connected or not self._instrument:
            print("Error: Not connected to instrument")
            return False

        try:
            self._instrument.write(command)
            return True
        except Exception as e:
            print(f"Write error: {e}")
            return False

    def write_raw(self, data: bytes) -> bool:
        """
        Send raw bytes to the instrument (for binary data blocks).

        Args:
            data: Raw bytes to send.

        Returns:
            True if successful.
        """
        if not self._connected or not self._instrument:
            print("Error: Not connected to instrument")
            return False

        try:
            self._instrument.write_raw(data)
            return True
        except Exception as e:
            print(f"Write raw error: {e}")
            return False

    def query(self, command: str) -> Optional[str]:
        """
        Send a SCPI query and return the response.

        Args:
            command: SCPI query string (should end with '?').

        Returns:
            Response string, or None if error.
        """
        if not self._connected and self._instrument is None:
            print("Error: Not connected to instrument")
            return None

        try:
            response = self._instrument.query(command).strip()
            return response
        except Exception as e:
            print(f"Query error: {e}")
            return None

    # =========================================================================
    # IEEE 488.2 / SCPI Utility
    # =========================================================================

    def reset(self) -> bool:
        """Reset the instrument to factory defaults."""
        return self.write("*RST")

    def clear_status(self) -> bool:
        """Clear the instrument status registers."""
        return self.write("*CLS")

    def get_error(self) -> Optional[str]:
        """Query the instrument error queue."""
        return self.query(":SYSTem:ERRor?")

    def get_version(self) -> Optional[str]:
        """Query the instrument SCPI version."""
        return self.query(":SYSTem:VERSion?")

    def beep(self) -> bool:
        """Make the instrument beep."""
        return self.write(":SYSTem:BEEPer:IMMediate")

    def wait_for_operation_complete(self) -> bool:
        """Wait for all pending operations to complete."""
        response = self.query("*OPC?")
        return response == "1"

    # =========================================================================
    # Context Manager
    # =========================================================================

    def __enter__(self):
        """Context manager entry."""
        if self._resource_name and not self._connected:
            self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.disconnect()
        return False

    def close(self) -> None:
        """Close the connection and the resource manager."""
        self.disconnect()
        if self._rm:
            try:
                self._rm.close()
            except Exception:
                pass
            self._rm = None

    def __del__(self):
        """Destructor — silent cleanup."""
        if self._rm is not None:
            try:
                self.close()
            except Exception:
                pass


# =============================================================================
# Module Test / Evaluation Mode
# =============================================================================
if __name__ == "__main__":
    print("=" * 60)
    print("KS33500B Connection Module - Evaluation Mode")
    print("=" * 60)

    conn = KS33500BConnection()

    # Step 1: List available VISA resources (no query)
    print("\n--- Listing VISA Resources ---")
    conn.list_resources()

    # Step 2: Discover Keysight 33500B devices
    print("\n--- Discovering Keysight 33500B Devices ---")
    devices = conn.discover_devices()

    if devices:
        resource, idn = devices[0]
        print(f"\nFound: {idn}")
        print(f"Resource: {resource}")

        if conn.connect(resource):
            print(f"\nConnection successful!")
            print(f"IDN: {conn.idn}")

            time.sleep(0.2)

            print("\n--- Testing Basic Queries ---")
            opc = conn.query("*OPC?")
            print(f"Operation Complete (*OPC?): {opc}")

            error = conn.get_error()
            print(f"Error Status: {error}")

            version = conn.get_version()
            print(f"SCPI Version: {version}")

            print("\n--- Testing Beep ---")
            if conn.beep():
                print("Beep command sent!")
                time.sleep(0.5)

        conn.close()
    else:
        print("\nNo Keysight 33500B devices found.")
        print("Check USB connection and NI-VISA / pyvisa-py installation.")

    print("\n" + "=" * 60)
    print("Evaluation complete.")
    print("=" * 60)
