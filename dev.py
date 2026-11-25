"""Manage this workspace's Odoo and PostgreSQL development processes."""

import argparse
from pathlib import Path
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request

import psutil


PROJECT = Path(__file__).resolve().parent
RUNTIME = PROJECT.parents[1] / "work" / "odoo19-env"
SOURCE = RUNTIME / "odoo"
CONFIG = PROJECT / "local" / "odoo.conf"
PG_BIN = Path("/opt/homebrew/opt/postgresql@16/bin")
PG_DATA = RUNTIME / "postgres-data"
PID_FILE = RUNTIME / "odoo.pid"
URL = "http://127.0.0.1:8069"


def pg_ctl(*args, check=True):
    result = subprocess.run(
        [str(PG_BIN / "pg_ctl"), "-D", str(PG_DATA), *args],
        capture_output=True, text=True,
    )
    if check and result.returncode:
        raise RuntimeError(result.stdout + result.stderr)
    return result


def postgres_running():
    result = pg_ctl("status", check=False)
    if result.returncode not in (0, 3):
        raise RuntimeError(result.stdout + result.stderr)
    return result.returncode == 0


def odoo_process():
    if not PID_FILE.exists():
        return None
    pid = int(PID_FILE.read_text().strip())
    try:
        process = psutil.Process(pid)
        if not process.is_running() or process.status() == psutil.STATUS_ZOMBIE:
            return None
        command = process.cmdline()
    except psutil.NoSuchProcess:
        return None
    if str(SOURCE / "odoo-bin") not in command or str(CONFIG) not in command:
        raise RuntimeError(f"PID {pid} does not belong to this Odoo instance; no action taken.")
    return process


def port_busy(port):
    with socket.socket() as sock:
        sock.settimeout(0.5)
        return sock.connect_ex(("127.0.0.1", port)) == 0


def http_ready():
    try:
        with urllib.request.urlopen(URL + "/web/login?db=equipment_dev", timeout=2) as response:
            return response.status == 200
    except (OSError, urllib.error.URLError):
        return False


def start_postgres():
    if not postgres_running():
        if port_busy(5432):
            raise RuntimeError("Port 5432 is occupied by another service.")
        pg_ctl("-l", str(RUNTIME / "logs" / "postgres.log"), "-w", "-t", "30", "start")


def start():
    start_postgres()
    process = odoo_process()
    if process is None:
        if port_busy(8069):
            raise RuntimeError("Port 8069 is occupied by another service.")
        with (RUNTIME / "logs" / "odoo-console.log").open("a") as console:
            child = subprocess.Popen(
                [sys.executable, str(SOURCE / "odoo-bin"), "-c", str(CONFIG)],
                cwd=SOURCE, stdin=subprocess.DEVNULL, stdout=console,
                stderr=subprocess.STDOUT, start_new_session=True,
            )
        process = psutil.Process(child.pid)
    for _ in range(90):
        if not process.is_running() or process.status() == psutil.STATUS_ZOMBIE:
            raise RuntimeError(f"Odoo exited; inspect {RUNTIME / 'logs'}.")
        if http_ready():
            print(f"Odoo is ready: {URL}/web/login?db=equipment_dev")
            print(f"Login details: {PROJECT / 'local' / 'access.txt'}")
            return
        time.sleep(1)
    raise RuntimeError(f"Odoo startup timed out; inspect {RUNTIME / 'logs'}.")


def stop_odoo():
    process = odoo_process()
    if process is not None:
        process.terminate()
        try:
            process.wait(timeout=30)
        except psutil.TimeoutExpired as error:
            raise RuntimeError("Odoo has not stopped; PostgreSQL was left running.") from error


def stop():
    stop_odoo()
    if postgres_running():
        pg_ctl("-m", "fast", "-w", "-t", "30", "stop")
    print("This project's Odoo and PostgreSQL are stopped. Database files are preserved.")


def upgrade():
    start_postgres()
    stop_odoo()
    log_path = RUNTIME / "logs" / "upgrade.log"
    result = subprocess.run([
        sys.executable, str(SOURCE / "odoo-bin"), "-c", str(CONFIG),
        "-d", "equipment_dev", "-u", "equipment_borrowing",
        "--no-http", "--stop-after-init",
        "--pidfile", str(RUNTIME / "odoo-upgrade.pid"),
        "--logfile", str(log_path),
    ], capture_output=True, text=True, stdin=subprocess.DEVNULL)
    if result.returncode:
        raise RuntimeError(f"Module upgrade failed; inspect {log_path}.\n{result.stdout}{result.stderr}")
    print("Module equipment_borrowing upgraded.")
    start()


def status():
    print(f"Python: {sys.version.split()[0]}")
    print(subprocess.check_output([str(PG_BIN / "postgres"), "--version"], text=True).strip())
    print("PostgreSQL: " + ("running" if postgres_running() else "stopped"))
    process = odoo_process()
    print("Odoo: " + (f"running (PID {process.pid})" if process is not None else "stopped"))
    print("Login page: " + ("HTTP 200" if http_ready() else "unavailable"))
    print(f"Custom addons: {PROJECT / 'addons'}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["start", "stop", "restart", "status", "upgrade"], default="status", nargs="?")
    action = parser.parse_args().action
    if action == "restart":
        stop()
        start()
    else:
        {"start": start, "stop": stop, "status": status, "upgrade": upgrade}[action]()


if __name__ == "__main__":
    try:
        main()
    except (OSError, RuntimeError, ValueError, psutil.Error) as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
