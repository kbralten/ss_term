import threading
import queue
import time
import sys
import re
from tkinter import Tk, Text, Button, END, Label, Entry, Scrollbar, StringVar, OptionMenu, Frame
import serial
import serial.tools.list_ports


def list_serial_ports():
    return [p.device for p in serial.tools.list_ports.comports()]


def parse_hex_bytes(s: str):
    # Accept formats like: "03 0A" or "0x03,0x0A" or "03,0A"
    s = s.replace(',', ' ').strip()
    parts = [p for p in s.split() if p]
    result = bytearray()
    for p in parts:
        p = p.strip()
        if p.startswith('0x') or p.startswith('0X'):
            v = int(p, 16)
        else:
            v = int(p, 16)
        result.append(v & 0xFF)
    return bytes(result)


class SerialTerminal:
    def __init__(self, root):
        self.root = root
        root.title('Simple Serial Terminal')

        top = Frame(root)
        top.pack(fill='x')

        Label(top, text='Port:').pack(side='left')
        self.port_var = StringVar(value='')
        self.port_menu = OptionMenu(top, self.port_var, *([''] + list_serial_ports()))
        self.port_menu.pack(side='left')

        self.refresh_btn = Button(top, text='Refresh', command=self.refresh_ports)
        self.refresh_btn.pack(side='left')

        self.connect_btn = Button(top, text='Connect', command=self.toggle_connect)
        self.connect_btn.pack(side='left')

        Label(top, text='EOL:').pack(side='left', padx=(10, 0))
        self.eol_var = StringVar(value='CRLF')
        OptionMenu(top, self.eol_var, 'CR', 'LF', 'CRLF').pack(side='left')

        Label(top, text='Baud:').pack(side='left', padx=(10, 0))
        self.baud_var = StringVar(value='115200')
        baud_rates = ['9600', '19200', '38400', '57600', '115200', '230400']
        OptionMenu(top, self.baud_var, *baud_rates).pack(side='left')

        self.log = Text(root, height=20, width=80, wrap='none')
        self.log.pack(fill='both', expand=True)
        self.log_scroll = Scrollbar(self.log, command=self.log.yview)
        self.log['yscrollcommand'] = self.log_scroll.set

        bottom = Frame(root)
        bottom.pack(fill='x')

        Label(bottom, text='Send Text:').pack(side='left')
        self.entry = Entry(bottom, width=40)
        self.entry.pack(side='left')
        self.send_btn = Button(bottom, text='Send', command=lambda: self.send_text(False))
        self.send_btn.pack(side='left')
        self.send_nl_btn = Button(bottom, text='Send with newline', command=lambda: self.send_text(True))
        self.send_nl_btn.pack(side='left')

        Label(bottom, text='Send Bytes (hex):').pack(side='left', padx=(10, 0))
        self.hex_entry = Entry(bottom, width=20)
        self.hex_entry.pack(side='left')
        self.send_bytes_btn = Button(bottom, text='Send Bytes', command=self.send_bytes)
        self.send_bytes_btn.pack(side='left')

        self.ser = None
        self.alive = False
        self.rx_queue = queue.Queue()
        self.root.after(100, self.process_rx)

    def refresh_ports(self):
        menu = self.port_menu['menu']
        menu.delete(0, 'end')
        ports = [''] + list_serial_ports()
        for p in ports:
            menu.add_command(label=p, command=lambda v=p: self.port_var.set(v))

    def toggle_connect(self):
        if self.ser:
            self.disconnect()
        else:
            self.connect()

    def connect(self):
        port = self.port_var.get()
        if not port:
            self.log.insert(END, 'No port selected\n')
            return
        try:
            try:
                baud = int(self.baud_var.get())
            except Exception:
                baud = 115200
            # Explicitly set 8N1 and no flow control (rtscts/xonxoff)
            self.ser = serial.Serial(port,
                                     baudrate=baud,
                                     timeout=0.1,
                                     bytesize=serial.EIGHTBITS,
                                     parity=serial.PARITY_NONE,
                                     stopbits=serial.STOPBITS_ONE,
                                     rtscts=False,
                                     xonxoff=False)
        except Exception as e:
            self.log.insert(END, f'Open failed: {e}\n')
            self.ser = None
            return
        self.alive = True
        self.connect_btn.config(text='Disconnect')
        self.log.insert(END, f'Connected to {port}\n')
        self.read_thread = threading.Thread(target=self.reader_thread, daemon=True)
        self.read_thread.start()

    def disconnect(self):
        self.alive = False
        if self.ser:
            try:
                self.ser.close()
            except Exception:
                pass
        self.ser = None
        self.connect_btn.config(text='Connect')
        self.log.insert(END, 'Disconnected\n')

    def parse_escaped_text(self, s: str) -> bytes:
        # Support escapes like: \n, \r, \t, \\\n+        # Hex escapes: \xHH or \0xHH (e.g. "DDS_WAVE\0xa5" or "\xA5")
        out = bytearray()
        i = 0
        L = len(s)
        while i < L:
            c = s[i]
            if c == '\\' and i + 1 < L:
                j = i + 1
                nxt = s[j]
                if nxt == 'n':
                    out.append(0x0A); i += 2; continue
                if nxt == 'r':
                    out.append(0x0D); i += 2; continue
                if nxt == 't':
                    out.append(0x09); i += 2; continue
                if nxt == '\\':
                    out.append(0x5C); i += 2; continue
                # hex forms: \xHH
                if nxt in ('x', 'X'):
                    # consume up to two hex digits after nxt
                    k = j + 1
                    hexstr = ''
                    while k < L and len(hexstr) < 2 and s[k].lower() in '0123456789abcdef':
                        hexstr += s[k]; k += 1
                    if hexstr:
                        out.append(int(hexstr, 16))
                        i = k
                        continue
                # hex form: \0xHH (user used \0xa5)
                if s[j:j+2].lower().startswith('0x'):
                    k = j + 2
                    hexstr = ''
                    while k < L and len(hexstr) < 2 and s[k].lower() in '0123456789abcdef':
                        hexstr += s[k]; k += 1
                    if hexstr:
                        out.append(int(hexstr, 16))
                        i = k
                        continue
                # no special escape recognized, take the character literally
                out.append(ord(nxt))
                i += 2
            else:
                out.append(ord(c))
                i += 1
        return bytes(out)

    def send_text(self, add_eol: bool = True):
        if not self.ser or not self.ser.is_open:
            self.log.insert(END, 'Not connected\n')
            return
        raw = self.entry.get()
        try:
            data_bytes = self.parse_escaped_text(raw)
        except Exception as e:
            self.log.insert(END, f'Parse failed: {e}\n')
            return
        if add_eol:
            eol = self.eol_var.get()
            if eol == 'CR':
                data_bytes = data_bytes + b'\r'
            elif eol == 'LF':
                data_bytes = data_bytes + b'\n'
            else:
                data_bytes = data_bytes + b'\r\n'
        try:
            self.ser.write(data_bytes)
            self.log.insert(END, f'Sent: {data_bytes!r}\n')
            # Clear the send text input after sending
            try:
                self.entry.delete(0, END)
            except Exception:
                pass
        except Exception as e:
            self.log.insert(END, f'Send failed: {e}\n')

    def send_bytes(self):
        if not self.ser or not self.ser.is_open:
            self.log.insert(END, 'Not connected\n')
            return
        text = self.hex_entry.get().strip()
        if not text:
            self.log.insert(END, 'No bytes to send\n')
            return
        try:
            b = parse_hex_bytes(text)
        except Exception as e:
            self.log.insert(END, f'Parse failed: {e}\n')
            return
        try:
            self.ser.write(b)
            self.log.insert(END, f'Sent bytes: {b}\n')
        except Exception as e:
            self.log.insert(END, f'Send failed: {e}\n')

    def reader_thread(self):
        buf = bytearray()
        while self.alive and self.ser and self.ser.is_open:
            try:
                n = self.ser.in_waiting
                if n:
                    data = self.ser.read(n)
                    if data:
                        self.rx_queue.put(data)
                else:
                    time.sleep(0.05)
            except Exception:
                time.sleep(0.1)

    def process_rx(self):
        try:
            while True:
                data = self.rx_queue.get_nowait()
                s = self.format_for_display(data)
                self.log.insert(END, s)
                self.log.see(END)
        except queue.Empty:
            pass
        self.root.after(100, self.process_rx)

    def format_for_display(self, data: bytes) -> str:
        # Convert bytes to a display string honoring EOL receive mode and showing non-printables inline
        mode = self.eol_var.get()
        out = []
        i = 0
        while i < len(data):
            b = data[i]
            # Handle CRLF mode specially
            if mode == 'CRLF' and b == 0x0D:
                # look ahead
                if i + 1 < len(data) and data[i + 1] == 0x0A:
                    out.append('\n')
                    i += 2
                    continue
                else:
                    out.append(f'<0x{b:02X}>')
                    i += 1
                    continue
            if mode == 'CR' and b == 0x0D:
                out.append('\n')
                i += 1
                continue
            if mode == 'LF' and b == 0x0A:
                out.append('\n')
                i += 1
                continue
            # Printable ASCII range
            if 0x20 <= b <= 0x7E:
                out.append(chr(b))
            else:
                out.append(f'<0x{b:02X}>')
            i += 1
        return ''.join(out)


def main():
    root = Tk()
    app = SerialTerminal(root)
    root.mainloop()


if __name__ == '__main__':
    main()
