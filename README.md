# Simple Serial Terminal Emulator

A minimal Python + Tkinter serial terminal emulator with two key features:

- Choose line ending used for sending and receiving: `CR`, `LF`, or `CRLF`.
- Send arbitrary bytes (hex input like `03` or `0x03`) and display non-printable bytes inline as `<0x03>`.

Requirements
- Python 3.8+
- Install dependencies:

```powershell
python -m pip install -r requirements.txt
```

Run

```powershell
python main.py
```

Usage
- Select a serial port and press Connect.
- Choose the `EOL` send/receive mode from the dropdown (`CR`, `LF`, `CRLF`).
- Type text and press Send — the chosen EOL will be appended and transmitted.
- To send raw bytes, enter hex bytes in the "Send Bytes (hex)" field (e.g. `03 0A` or `0x03,0x0A`) and press "Send Bytes".
- Incoming bytes are shown in the log; printable ASCII characters are shown directly; non-printable bytes are shown as `<0xNN>`.
 - Type text into `Send Text` and click `Send` (no newline) or `Send with newline` (append EOL per selection).
 - You can include raw bytes inline using escapes. Examples:
	 - `DDS_WAVE\\0xa5` sends ASCII `DDS_WAVE` followed by byte `0xA5`.
	 - `value\\x0A` sends a raw `0x0A` byte.
	 - `hello\\n` sends a newline byte (same as selecting `LF` and using `Send with newline`).
 - Choose a `Baud` rate from the dropdown (default `115200`).
 - The connection defaults to 8N1 (8 data bits, no parity, 1 stop bit) and no flow control (RTS/CTS and XON/XOFF disabled).
