# pip install textual psutil rich
import psutil
import os
import signal
import time
from datetime import timedelta
from rich.table import Table
from rich.text import Text
from rich.panel import Panel
from rich.columns import Columns
from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, Static
from textual.containers import Container

# Helper functions
def fmt_bytes(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} PB"

def fmt_uptime(seconds: float) -> str:
    return str(timedelta(seconds=int(seconds)))

def cpu_color(pct: float) -> str:
    if pct >= 80: return "bold red"
    if pct >= 50: return "yellow"
    return "green"

def mem_color(pct: float) -> str:
    if pct >= 80: return "bold red"
    if pct >= 50: return "yellow"
    return "cyan"

# System stats panel
class SystemPanel(Static):
    """Displays CPU, memory, disk, network, and uptime."""
    def update_stats(self):
        cpu_pcts = psutil.cpu_percent(percpu=True)
        mem = psutil.virtual_memory()
        swp = psutil.swap_memory()
        disk = psutil.disk_usage("/")
        net = psutil.net_io_counters()
        uptime = time.time() - psutil.boot_time()

        # CPU table
        cpu_table = Table.grid(padding=1)
        row = []
        for i, pct in enumerate(cpu_pcts):
            row.append(Text(f"CPU{i} {pct:.1f}%", style=cpu_color(pct)))
            if len(row) == 4:
                cpu_table.add_row(*row)
                row = []
        if row:
            cpu_table.add_row(*row)

        # Memory table
        mem_table = Table.grid(padding=1)
        mem_table.add_row("RAM ", f"{mem.percent:.1f}%", f"{fmt_bytes(mem.used)} / {fmt_bytes(mem.total)}")
        if swp.total:
            mem_table.add_row("Swap", f"{swp.percent:.1f}%", f"{fmt_bytes(swp.used)} / {fmt_bytes(swp.total)}")

        # Disk/Network/Uptime table
        info_table = Table.grid(padding=1)
        info_table.add_row("Disk", f"{disk.percent:.1f}%", f"{fmt_bytes(disk.used)} / {fmt_bytes(disk.total)}")
        info_table.add_row("Net ↑", fmt_bytes(net.bytes_sent), "sent")
        info_table.add_row("Net ↓", fmt_bytes(net.bytes_recv), "recv")
        info_table.add_row("Up  ", fmt_uptime(uptime), "")

        # Combine tables using Columns
        combined = Columns([cpu_table, mem_table, info_table], expand=True)
        panel = Panel(combined, title="System Stats")
        self.update(panel)

# Processes panel
class ProcessesPanel(Static):
    """Displays a scrollable list of processes."""
    sort_by = "cpu"
    selected_index = 0
    processes = []

    def refresh_processes(self):
        procs = []
        for p in psutil.process_iter(["pid","name","status","cpu_percent","memory_percent","num_threads","username"]):
            try:
                info = p.info
                info["memory_mb"] = p.memory_info().rss / 1024 / 1024
                procs.append(info)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

        key = self.sort_by
        if key == "cpu":
            procs.sort(key=lambda p: p.get("cpu_percent") or 0, reverse=True)
        elif key == "mem":
            procs.sort(key=lambda p: p.get("memory_percent") or 0, reverse=True)
        elif key == "pid":
            procs.sort(key=lambda p: p.get("pid") or 0)
        elif key == "name":
            procs.sort(key=lambda p: (p.get("name") or "").lower())

        self.processes = procs
        self.update_table()

    def update_table(self):
        table = Table(expand=True, title=f"Processes ({len(self.processes)})", show_header=True)
        table.add_column("PID", justify="right")
        table.add_column("Name", no_wrap=True)
        table.add_column("Status")
        table.add_column("CPU%", justify="right")
        table.add_column("MEM%", justify="right")
        table.add_column("RAM", justify="right")
        table.add_column("Threads", justify="right")
        table.add_column("User", no_wrap=True)

        for i, p in enumerate(self.processes[:100]):
            is_sel = i == self.selected_index
            style = "bold on #1e3a5f" if is_sel else ""
            table.add_row(
                str(p.get("pid")),
                p.get("name") or "?",
                p.get("status") or "",
                f"{p.get('cpu_percent',0):.1f}",
                f"{p.get('memory_percent',0):.1f}",
                fmt_bytes(p.get("memory_mb",0)*1024*1024),
                str(p.get("num_threads") or ""),
                (p.get("username") or "")[-14:],
                style=style
            )
        super().update(table)

    def move_selection(self, delta: int):
        self.selected_index = max(0, min(self.selected_index + delta, len(self.processes)-1))
        self.update_table()

    def get_selected_pid(self):
        if self.processes and 0 <= self.selected_index < len(self.processes):
            return self.processes[self.selected_index]["pid"]
        return None

# Main App
class TaskMonitorApp(App):
    BINDINGS = [
        ("q", "quit", "Quit"),
        ("k", "kill_process", "Kill process"),
        ("c", "sort_cpu", "Sort by CPU"),
        ("m", "sort_mem", "Sort by MEM"),
        ("p", "sort_pid", "Sort by PID"),
        ("n", "sort_name", "Sort by Name"),
        ("up", "move_up", "Move Up"),
        ("down", "move_down", "Move Down"),
    ]

    def compose(self) -> ComposeResult:
        yield Header()
        self.sys_panel = SystemPanel()
        self.proc_panel = ProcessesPanel()
        yield Container(self.sys_panel, self.proc_panel)
        yield Footer()

    def on_mount(self):
        self.set_interval(1, self.refresh_data)

    def refresh_data(self):
        self.sys_panel.update_stats()
        self.proc_panel.refresh_processes()

    def action_move_up(self):
        self.proc_panel.move_selection(-1)

    def action_move_down(self):
        self.proc_panel.move_selection(1)

    def action_sort_cpu(self):
        self.proc_panel.sort_by = "cpu"
        self.proc_panel.selected_index = 0
        self.proc_panel.refresh_processes()

    def action_sort_mem(self):
        self.proc_panel.sort_by = "mem"
        self.proc_panel.selected_index = 0
        self.proc_panel.refresh_processes()

    def action_sort_pid(self):
        self.proc_panel.sort_by = "pid"
        self.proc_panel.selected_index = 0
        self.proc_panel.refresh_processes()

    def action_sort_name(self):
        self.proc_panel.sort_by = "name"
        self.proc_panel.selected_index = 0
        self.proc_panel.refresh_processes()

    def action_kill_process(self):
        pid = self.proc_panel.get_selected_pid()
        if pid:
            try:
                os.kill(pid, signal.SIGTERM)
            except Exception:
                pass
            self.proc_panel.refresh_processes()

if __name__ == "__main__":
    TaskMonitorApp().run()