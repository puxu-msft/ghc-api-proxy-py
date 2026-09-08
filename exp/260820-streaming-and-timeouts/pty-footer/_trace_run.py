import fcntl, os, pty, select, struct, subprocess, sys, termios
import pyte
COLS, ROWS = 100, 30
master, slave = pty.openpty()
fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", ROWS, COLS, 0, 0))
env = {**os.environ, "TERM": "xterm-256color", "COLUMNS": str(COLS), "LINES": str(ROWS), "PYTHONPATH": "src"}
p = subprocess.Popen([sys.executable, sys.argv[1]], stdin=slave, stdout=slave, stderr=slave, env=env, close_fds=True)
os.close(slave)
chunks = []
while True:
    r, _, _ = select.select([master], [], [], 30.0)
    if not r: break
    try: data = os.read(master, 65536)
    except OSError: break
    if not data: break
    chunks.append(data)
os.close(master)
print("exit:", p.wait(timeout=30), file=sys.stderr)
screen = pyte.HistoryScreen(COLS, ROWS, history=4000)
pyte.ByteStream(screen).feed(b"".join(chunks))
hist = ["".join(row[c].data for c in sorted(row)) for row in screen.history.top]
print("=========== SCROLLBACK ===========")
for line in hist: print(repr(line.rstrip()))
print("=========== SCREEN ===========")
for i, line in enumerate(screen.display): print(f"{i:02d}|{line.rstrip()}")
