import asyncio
import logging

_LOGGER = logging.getLogger(__name__)


class OreiMatrixClient:
    """Async client for controlling Orei HDMI Matrix via Telnet."""

    def __init__(self, host, port=23):
        self._host = host
        self._port = port
        self._reader = None
        self._writer = None
        self._lock = asyncio.Lock()

    # -----------------------
    # Connection management
    # -----------------------

    async def connect(self):
        """Establish a TCP connection to the matrix."""
        self._reader, self._writer = await asyncio.wait_for(
            asyncio.open_connection(self._host, self._port),
            timeout=5.0,
        )
        _LOGGER.debug("Connected to Orei Matrix at %s:%s", self._host, self._port)

    async def disconnect(self):
        """Close the connection."""
        if not self._writer:
            return

        self._writer.close()
        try:
            await self._writer.wait_closed()
        except Exception:
            pass  # Best effort cleanup
        finally:
            self._reader = None
            self._writer = None
            _LOGGER.debug("Disconnected from Orei Matrix")

    async def _ensure_connected(self):
        """Reconnect if needed."""
        if not self._writer or self._writer.is_closing():
            await self.connect()

    # -----------------------
    # Core command handling
    # -----------------------

    async def _send_command_multiple(self, cmd: str) -> list[str]:
        async with self._lock:
            await self._ensure_connected()
            return await self._send_and_parse(cmd)

    async def _send_and_parse(self, cmd: str) -> list[str]:
        """Send command and parse response."""
        try:
            chunks = await self._send_and_read(cmd)
        except Exception as e:
            _LOGGER.warning("Telnet command failed (%s), reconnecting...", e)
            await self.disconnect()
            raise

        if not chunks:
            _LOGGER.warning("No response received for command: %s", cmd)
            return []

        return self._parse_response(cmd, chunks)

    async def _send_and_read(self, cmd: str) -> bytearray:
        """Send command and read raw response."""
        if not self._writer or not self._reader:
            raise RuntimeError("Not connected to matrix")

        _LOGGER.debug("Sending command: %s", cmd)
        self._writer.write((cmd + "\r\n").encode("ascii"))
        await self._writer.drain()

        # Read response until idle
        chunks = bytearray()
        try:
            while True:
                data = await asyncio.wait_for(self._reader.read(1024), timeout=0.3)
                if not data:
                    break
                chunks.extend(data)
        except TimeoutError:
            pass

        return chunks

    def _parse_response(self, cmd: str, chunks: bytearray) -> list[str]:
        """Parse raw response bytes into cleaned lines."""
        # --- Clean and parse ---
        filtered = bytes(b for b in chunks if b < 0x80)
        text = filtered.decode("ascii", errors="ignore").strip()

        # Split into lines, remove empty and banner/prompt lines
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        _LOGGER.debug("Parsed lines for cmd '%s': %s", cmd, lines)

        # Remove echoed command and banner
        cleaned = []
        for line in lines:
            # Skip command echo (exact match), banners, and prompts
            if (
                line == cmd
                or line == cmd.rstrip("!")
                or line.startswith(("********", "FW Version"))
                or line == ">"
                or "Welcome" in line
            ):
                _LOGGER.debug("Skipping line: %s", line)
                continue
            cleaned.append(line.strip(">"))

        _LOGGER.debug("Cleaned response for cmd '%s': %s", cmd, cleaned)
        return cleaned

    async def _send_command(self, cmd: str) -> str:
        cleaned = await self._send_command_multiple(cmd)
        response = cleaned[-1] if cleaned else ""
        _LOGGER.debug("Cleaned response: %s", response)
        return response

    # -----------------------
    # Matrix control commands
    # -----------------------

    async def get_type(self) -> str:
        """Return matrix model type."""
        type_str = await self._send_command("r type!")
        # If we got the command back or something weird, return a default
        if not type_str or "type" in type_str.lower() or len(type_str) < 3:
            _LOGGER.warning("Invalid type response: '%s', using default", type_str)
            return "HDMI Matrix"
        return type_str

    async def get_status(self) -> dict:
        """Get full device status including input/output counts."""
        lines = await self._send_command_multiple("r status!")

        status: dict = {
            "power": False,
            "input_count": 0,
            "output_count": 0,
            "inputs": {},
            "outputs": {},
            "routing": {},
        }

        for line in lines:
            line_lower = line.lower()

            # Parse power
            if "power on" in line_lower:
                status["power"] = True

            # Count inputs: "hdmi input 1: sync"
            if "hdmi input" in line_lower and ":" in line:
                parts = line_lower.split(":")
                try:
                    input_num = int(parts[0].split()[-1])
                except (ValueError, IndexError):
                    continue

                input_count: int = status["input_count"]  # type: ignore[assignment]
                status["input_count"] = max(input_count, input_num)
                state = parts[1].strip()
                is_connected = "disconnect" not in state
                inputs_dict: dict = status["inputs"]  # type: ignore[assignment]
                inputs_dict[input_num] = {"connected": is_connected}

            # Count outputs: "hdmi output 1: disconnect" or "hdbt output 1"
            is_output = "hdmi output" in line_lower or "hdbt output" in line_lower
            if is_output and ":" in line:
                parts = line_lower.split(":")
                try:
                    output_num = int(parts[0].split()[-1])
                except (ValueError, IndexError):
                    continue

                output_count: int = status["output_count"]  # type: ignore[assignment]
                status["output_count"] = max(output_count, output_num)
                state = parts[1].strip()
                is_connected = "disconnect" not in state
                outputs_dict: dict = status["outputs"]  # type: ignore[assignment]
                outputs_dict[output_num] = {"connected": is_connected}

            # Parse routing: "input 1 -> output 1"
            routing_check = (
                "->" in line_lower and "input" in line_lower and "output" in line_lower
            )
            if routing_check:
                parts = line_lower.replace("->", " ").split()
                try:
                    input_idx = parts.index("input") + 1
                    output_idx = parts.index("output") + 1
                except (ValueError, IndexError):
                    continue

                try:
                    input_num = int(parts[input_idx])
                    output_num = int(parts[output_idx])
                except (ValueError, IndexError):
                    continue

                routing_dict: dict = status["routing"]  # type: ignore[assignment]
                routing_dict[output_num] = input_num

        _LOGGER.debug("Parsed status: %s", status)
        return status

    async def get_power(self) -> bool:
        """Return True if matrix power is ON."""
        res = await self._send_command("r power!")
        return "on" in res.lower()

    async def set_power(self, state: bool):
        """Turn matrix power ON or OFF."""
        cmd = f"s power {1 if state else 0}!"
        await self._send_command(cmd)

    async def get_output_source(self, output_id: int):
        """Get the current input assigned to a given output."""
        res = await self._send_command(f"r av out {output_id}!")
        _LOGGER.debug("Parsing output source response: %s", res)

        res = res.lower().replace("->", " -> ").replace(":", " ")
        parts = res.split()
        input_id = None

        try:
            for i, token in enumerate(parts):
                if token in ("input", "in") and i + 1 < len(parts):
                    input_id = int(parts[i + 1])
        except ValueError:
            _LOGGER.warning("Could not parse integers from response: %s", res)
            return None

        return input_id

    async def get_output_sources(self):
        """Get the current input assigned to a given output."""
        results = await self._send_command_multiple("r av out 0!")
        response = {}

        for res in results:
            res = res.lower().replace("->", " -> ").replace(":", " ")
            parts = res.split()
            output_id = None
            input_id = None

            try:
                for i, token in enumerate(parts):
                    if token in ("output", "out") and i + 1 < len(parts):
                        output_id = int(parts[i + 1])
                    if token in ("input", "in") and i + 1 < len(parts):
                        input_id = int(parts[i + 1])
                response[output_id] = input_id
            except ValueError:
                _LOGGER.warning("Could not parse integers from response: %s", res)
                return None
        return response

    async def get_in_link(self, input_id: int):
        """Get the input state."""
        res = await self._send_command(f"r link in {input_id}!")
        return "disconnect" not in res.lower()

    async def get_in_links(self):
        """Get the input state."""
        results = await self._send_command_multiple("r link in 0!")
        response = {}

        for res in results:
            res = res.lower().replace(":", " ")
            parts = res.split()
            input_id = None

            try:
                for i, token in enumerate(parts):
                    if token in ("input", "in") and i + 1 < len(parts):
                        input_id = int(parts[i + 1])
                response[input_id] = "disconnect" not in res
            except ValueError:
                _LOGGER.warning("Could not parse integers from response: %s", res)
                return None
        return response

    async def get_out_link(self, output_id: int):
        """Get the output state."""
        res = await self._send_command(f"r link out {output_id}!")
        return "disconnect" not in res.lower()

    async def get_out_links(self):
        """Get the input state."""
        results = await self._send_command_multiple("r link out 0!")
        response = {}

        for res in results:
            res = res.lower().replace(":", " ")
            parts = res.split()
            output_id = None

            try:
                for i, token in enumerate(parts):
                    if token in ("output", "out") and i + 1 < len(parts):
                        output_id = int(parts[i + 1])
                response[output_id] = "disconnect" not in res
            except ValueError:
                _LOGGER.warning("Could not parse integers from response: %s", res)
                return None
        return response

    async def set_cec_in(self, input_id: int, command: str):
        """Send a CEC command to the input."""
        await self._send_command(f"s cec in {input_id} {command}!")

    async def set_cec_out(self, output_id: int, command: str):
        """Send a CEC command to both HDMI and HDBaseT outputs."""
        # Send to HDMI output
        await self._send_command(f"s cec hdmi out {output_id} {command}!")
        # Send to HDBaseT output
        await self._send_command(f"s cec hdbt out {output_id} {command}!")

    async def set_output_active(self, output_id: int):
        """Set the output to active source (tells TV to switch to this input)."""
        # Send active command to both HDMI and HDBaseT
        await self._send_command(f"s cec hdmi out {output_id} active!")
        await self._send_command(f"s cec hdbt out {output_id} active!")

    async def set_output_source(self, input_id: int, output_id: int):
        """Assign an input to an output."""
        await self._send_command(f"s in {input_id} av out {output_id}!")
