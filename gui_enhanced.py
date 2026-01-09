import sys
import ctypes
import os
from PyQt6.QtWidgets import (QApplication, QMainWindow, QLabel, QVBoxLayout, QHBoxLayout,
                             QWidget, QTableWidget, QTableWidgetItem, QHeaderView, QProgressBar, QFrame, QTabWidget, QGridLayout)
from PyQt6.QtCore import QTimer, Qt, QRectF
from PyQt6.QtGui import QPainter, QColor, QPen, QFont, QPalette
from collections import deque

# --- 1. LOAD C++ LIBRARY ---
lib_path = os.path.abspath("./libbackend.so")
c_lib = ctypes.CDLL(lib_path)

c_lib.get_uptime_seconds.restype = ctypes.c_double
c_lib.get_cpu_usage.restype = ctypes.c_double
c_lib.get_memory_usage.argtypes = [ctypes.POINTER(ctypes.c_long), ctypes.POINTER(ctypes.c_long)]
c_lib.get_process_cpu_usage.argtypes = [ctypes.c_int]
c_lib.get_process_cpu_usage.restype = ctypes.c_double
c_lib.get_process_memory_mb.argtypes = [ctypes.c_int]
c_lib.get_process_memory_mb.restype = ctypes.c_long
c_lib.get_load_averages.argtypes = [ctypes.POINTER(ctypes.c_double), ctypes.POINTER(ctypes.c_double), ctypes.POINTER(ctypes.c_double)]
c_lib.get_swap_usage.argtypes = [ctypes.POINTER(ctypes.c_long), ctypes.POINTER(ctypes.c_long)]
c_lib.get_memory_breakdown.argtypes = [ctypes.POINTER(ctypes.c_long), ctypes.POINTER(ctypes.c_long), ctypes.POINTER(ctypes.c_long)]
c_lib.get_iowait_percentage.restype = ctypes.c_double
c_lib.get_context_switches.restype = ctypes.c_longlong
c_lib.get_network_stats.argtypes = [ctypes.c_char_p, ctypes.POINTER(ctypes.c_longlong), ctypes.POINTER(ctypes.c_longlong), 
                                     ctypes.POINTER(ctypes.c_longlong), ctypes.POINTER(ctypes.c_longlong),
                                     ctypes.POINTER(ctypes.c_longlong), ctypes.POINTER(ctypes.c_longlong)]
c_lib.get_network_throughput.argtypes = [ctypes.c_char_p, ctypes.POINTER(ctypes.c_double), ctypes.POINTER(ctypes.c_double)]
c_lib.get_cpu_temperature.restype = ctypes.c_double
c_lib.get_file_descriptors.argtypes = [ctypes.POINTER(ctypes.c_long), ctypes.POINTER(ctypes.c_long)]
c_lib.get_process_fd_count.argtypes = [ctypes.c_int]
c_lib.get_process_fd_count.restype = ctypes.c_int
c_lib.get_battery_info.argtypes = [ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_double)]
c_lib.get_cpu_frequency.argtypes = [ctypes.c_int]
c_lib.get_cpu_frequency.restype = ctypes.c_double
c_lib.get_disk_io_rates.argtypes = [ctypes.c_char_p, ctypes.POINTER(ctypes.c_double), ctypes.POINTER(ctypes.c_double)]
c_lib.get_process_counts.argtypes = [ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int)]
c_lib.get_network_connections_count.restype = ctypes.c_int

# --- 2. PYTHON HELPER (Process List) ---
def get_process_list():
    """Reads /proc to get process list, sorted by Memory usage."""
    processes = []
    try:
        for pid in os.listdir('/proc'):
            if pid.isdigit():
                try:
                    with open(f'/proc/{pid}/status', 'r') as f:
                        name = "???"
                        state = "?"
                        memory = 0

                        for line in f:
                            if line.startswith("Name:"):
                                name = line.split(":")[1].strip()
                            elif line.startswith("State:"):
                                state = line.split(":")[1].strip().split()[0]
                            elif line.startswith("VmRSS:"):
                                mem_str = line.split(":")[1].strip().split()[0]
                                memory = int(mem_str) // 1024

                        if memory > 0:
                            processes.append((int(pid), name, state, memory))
                except (IOError, FileNotFoundError):
                    continue
    except Exception:
        pass

    processes.sort(key=lambda x: x[3], reverse=True)
    return processes[:50]

def get_per_core_cpu_usage():
    """Returns list of CPU usage percentages for each core."""
    core_usages = []
    try:
        with open('/proc/stat', 'r') as f:
            for line in f:
                if line.startswith('cpu') and not line.startswith('cpu '):
                    parts = line.split()
                    if len(parts) >= 5:
                        user = int(parts[1])
                        nice = int(parts[2])
                        system = int(parts[3])
                        idle = int(parts[4])
                        iowait = int(parts[5]) if len(parts) > 5 else 0
                        
                        total = user + nice + system + idle + iowait
                        active = user + nice + system
                        
                        if total > 0:
                            usage = (active / total) * 100
                            core_usages.append(usage)
    except Exception:
        pass
    return core_usages

def get_disk_usage():
    """Returns disk usage percentage and used/total in GB for root partition."""
    try:
        import shutil
        total, used, free = shutil.disk_usage('/')
        total_gb = total // (1024**3)
        used_gb = used // (1024**3)
        percent = (used / total) * 100
        return percent, used_gb, total_gb
    except Exception:
        return 0, 0, 0

def get_network_interfaces():
    """Get list of network interfaces."""
    interfaces = []
    try:
        for iface in os.listdir('/sys/class/net'):
            if iface != 'lo':  # Skip loopback
                interfaces.append(iface)
    except:
        pass
    return interfaces

def get_disk_devices():
    """Get list of disk devices."""
    devices = []
    try:
        for device in os.listdir('/sys/block'):
            if not device.startswith('loop') and not device.startswith('ram'):
                devices.append(device)
    except:
        pass
    return devices

# --- 3. CUSTOM WIDGET: MEMORY GAUGE ---
class MemoryGauge(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.value = 0
        self.used_mb = 0
        self.total_mb = 0
        self.setMinimumSize(300, 300)

    def set_data(self, used, total):
        self.used_mb = used
        self.total_mb = total
        if total > 0:
            self.value = (used / total) * 100
        else:
            self.value = 0
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        width = self.width()
        height = self.height()
        size = min(width, height) - 20
        rect = QRectF((width - size) / 2, (height - size) / 2, size, size)

        # Color Logic (Blue -> Orange)
        if self.value < 75:
            bar_color = QColor("#2979FF") # Blue
        else:
            bar_color = QColor("#FF6D00") # Orange

        # Background Arc
        pen_bg = QPen(QColor(40, 44, 52), 12, cap=Qt.PenCapStyle.RoundCap)
        painter.setPen(pen_bg)
        painter.drawArc(rect, -225 * 16, -270 * 16)

        # Active Arc
        pen_active = QPen(bar_color, 12, cap=Qt.PenCapStyle.RoundCap)
        painter.setPen(pen_active)
        span_angle = -(self.value / 100) * 270
        painter.drawArc(rect, -225 * 16, int(span_angle * 16))

        # Text
        painter.setPen(QColor("#ffffff"))

        # Percentage
        painter.setFont(QFont("Segoe UI", 24, QFont.Weight.Bold))
        rect_pct = QRectF(rect)
        rect_pct.moveBottom(rect.center().y() - 5)
        painter.drawText(rect_pct, Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignHCenter, f"{int(self.value)}%")

        # MB Used / Total
        painter.setFont(QFont("Segoe UI", 16))
        rect_used = QRectF(rect)
        rect_used.moveTop(rect.center().y() + 5)
        painter.drawText(rect_used, Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter, f"{int(self.used_mb)} / {int(self.total_mb)} MB")

# --- 4. MAIN WINDOW ---
class ProfessionalMonitor(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Linux System Resource Monitor")
        self.resize(1200, 800)
        self.setup_theme()

        # Network history for graphs
        self.network_history = {}
        self.prev_context_switches = 0

        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        layout = QVBoxLayout(main_widget)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        # --- HEADER ---
        self.lbl_main_title = QLabel("Linux System Resource Monitor")
        self.lbl_main_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_main_title.setStyleSheet("font-size: 30px; font-weight: bold; color: white; margin-bottom: 5px;")
        layout.addWidget(self.lbl_main_title)

        # --- TAB WIDGET ---
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet("""
            QTabWidget::pane {
                border: 2px solid #21252b;
                background-color: #282c34;
                border-radius: 5px;
            }
            QTabBar::tab {
                background-color: #21252b;
                color: #abb2bf;
                padding: 10px 20px;
                margin-right: 2px;
                border-top-left-radius: 5px;
                border-top-right-radius: 5px;
                font-size: 16px;
                font-weight: bold;
            }
            QTabBar::tab:selected {
                background-color: #2979FF;
                color: white;
            }
            QTabBar::tab:hover {
                background-color: #2c313a;
            }
        """)

        # --- TAB 1: SYSTEM OVERVIEW ---
        self.create_system_tab()
        
        # --- TAB 2: PROCESSES ---
        self.create_process_tab()

        # --- TAB 3: NETWORK ---
        self.create_network_tab()

        # --- TAB 4: SYSTEM INFO ---
        self.create_system_info_tab()

        layout.addWidget(self.tabs)

        # --- TIMER ---
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_system_stats)
        self.timer.start(1000)

    def create_system_tab(self):
        system_tab = QWidget()
        system_layout = QVBoxLayout(system_tab)
        system_layout.setContentsMargins(10, 10, 10, 10)
        system_layout.setSpacing(15)

        # --- SECTION A: DASHBOARD ---
        dashboard_layout = QHBoxLayout()

        self.mem_gauge = MemoryGauge()

        info_panel = QWidget()
        info_layout = QVBoxLayout(info_panel)

        self.lbl_cpu_title = QLabel("CPU Usage")
        self.lbl_cpu_title.setStyleSheet("font-size: 20px; color: #aaaaaa;")

        self.cpu_bar = QProgressBar()
        self.cpu_bar.setTextVisible(True)
        self.cpu_bar.setStyleSheet("""
            QProgressBar {
                border: 2px solid #444;
                font-size: 16px;
                font-weight: bold;
                border-radius: 5px;
                text-align: center;
                background-color: #282c34;
                color: white;
                height: 25px;
            }
            QProgressBar::chunk {
                background-color: #2979FF;
                border-radius: 3px;
            }
        """)

        self.lbl_uptime = QLabel("Uptime: Calculating...")
        self.lbl_uptime.setStyleSheet("font-size: 20px; font-weight: bold; color: white; margin-top: 10px;")

        self.lbl_temp = QLabel("CPU Temp: N/A")
        self.lbl_temp.setStyleSheet("font-size: 18px; color: #abb2bf; margin-top: 5px;")

        self.lbl_load = QLabel("Load Avg: N/A")
        self.lbl_load.setStyleSheet("font-size: 18px; color: #abb2bf; margin-top: 5px;")

        self.lbl_iowait = QLabel("I/O Wait: N/A")
        self.lbl_iowait.setStyleSheet("font-size: 18px; color: #abb2bf; margin-top: 5px;")

        info_layout.addWidget(self.lbl_cpu_title)
        info_layout.addWidget(self.cpu_bar)
        info_layout.addWidget(self.lbl_uptime)
        info_layout.addWidget(self.lbl_temp)
        info_layout.addWidget(self.lbl_load)
        info_layout.addWidget(self.lbl_iowait)
        info_layout.addStretch()

        dashboard_layout.addWidget(self.mem_gauge)
        dashboard_layout.addWidget(info_panel)
        dashboard_layout.setStretch(1, 2)

        dash_frame = QFrame()
        dash_frame.setLayout(dashboard_layout)
        dash_frame.setStyleSheet("background-color: #21252b; border-radius: 10px; padding: 10px;")
        system_layout.addWidget(dash_frame)

        # --- SECTION B: PER-CORE CPU USAGE ---
        self.lbl_core_title = QLabel("Per-Core CPU Usage")
        self.lbl_core_title.setStyleSheet("font-size: 20px; font-weight: bold; color: #abb2bf; margin-top: 10px;")
        system_layout.addWidget(self.lbl_core_title)

        self.core_bars_layout = QVBoxLayout()
        self.core_bars = []
        
        cores_frame = QFrame()
        cores_frame.setLayout(self.core_bars_layout)
        cores_frame.setStyleSheet("background-color: #21252b; border-radius: 10px; padding: 10px;")
        system_layout.addWidget(cores_frame)

        # --- SECTION C: DISK USAGE ---
        self.lbl_disk_title = QLabel("Disk Usage")
        self.lbl_disk_title.setStyleSheet("font-size: 20px; color: #aaaaaa; margin-top: 10px;")
        system_layout.addWidget(self.lbl_disk_title)

        self.disk_bar = QProgressBar()
        self.disk_bar.setTextVisible(True)
        self.disk_bar.setStyleSheet("""
            QProgressBar {
                border: 2px solid #444;
                font-size: 16px;
                font-weight: bold;
                border-radius: 5px;
                text-align: center;
                background-color: #282c34;
                color: white;
                height: 25px;
            }
            QProgressBar::chunk {
                background-color: #2979FF;
                border-radius: 3px;
            }
        """)

        disk_frame = QFrame()
        disk_layout = QVBoxLayout(disk_frame)
        disk_layout.addWidget(self.disk_bar)
        disk_frame.setStyleSheet("background-color: #21252b; border-radius: 10px; padding: 10px;")
        system_layout.addWidget(disk_frame)

        # --- SECTION D: SWAP USAGE ---
        self.lbl_swap_title = QLabel("Swap Usage")
        self.lbl_swap_title.setStyleSheet("font-size: 20px; color: #aaaaaa; margin-top: 10px;")
        system_layout.addWidget(self.lbl_swap_title)

        self.swap_bar = QProgressBar()
        self.swap_bar.setTextVisible(True)
        self.swap_bar.setStyleSheet("""
            QProgressBar {
                border: 2px solid #444;
                font-size: 16px;
                font-weight: bold;
                border-radius: 5px;
                text-align: center;
                background-color: #282c34;
                color: white;
                height: 25px;
            }
            QProgressBar::chunk {
                background-color: #2979FF;
                border-radius: 3px;
            }
        """)

        swap_frame = QFrame()
        swap_layout = QVBoxLayout(swap_frame)
        swap_layout.addWidget(self.swap_bar)
        swap_frame.setStyleSheet("background-color: #21252b; border-radius: 10px; padding: 10px;")
        system_layout.addWidget(swap_frame)

        system_layout.addStretch()

        self.tabs.addTab(system_tab, "System Overview")

    def create_process_tab(self):
        proc_tab = QWidget()
        proc_layout = QVBoxLayout(proc_tab)
        proc_layout.setContentsMargins(10, 10, 10, 10)
        proc_layout.setSpacing(10)

        self.lbl_proc_title = QLabel("Top Processes (Sorted by Memory)")
        self.lbl_proc_title.setStyleSheet("font-size: 25px; font-weight: bold; color: #abb2bf;")
        proc_layout.addWidget(self.lbl_proc_title)

        self.table = QTableWidget()
        font = QFont()
        font.setPointSize(16)
        self.table.setFont(font)
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels(["PID", "Name", "State", "Memory (MB)", "CPU %", "Disk I/O", "FDs"])
        header_font = QFont()
        header_font.setPointSize(18)
        header_font.setBold(True)
        self.table.horizontalHeader().setFont(header_font)
        self.table.verticalHeader().setVisible(False)
        self.table.setShowGrid(True)
        self.table.setAlternatingRowColors(True)

        self.table.setStyleSheet("""
            QTableWidget {
                background-color: #282c34;
                alternate-background-color: #2c313a;
                color: #abb2bf;
                border: none;
                gridline-color: #3e4451;
            }
            QHeaderView::section {
                background-color: #21252b;
                color: white;
                padding: 5px;
                border: none;
                font-weight: bold;
            }
            QTableWidget::item {
                padding: 5px;
            }
            QTableWidget::item:selected {
                background-color: #3d4554;
                color: white;
            }
        """)

        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.ResizeToContents)

        proc_layout.addWidget(self.table)

        self.tabs.addTab(proc_tab, "Processes")

    def create_network_tab(self):
        network_tab = QWidget()
        network_layout = QVBoxLayout(network_tab)
        network_layout.setContentsMargins(10, 10, 10, 10)
        network_layout.setSpacing(15)

        self.lbl_network_title = QLabel("Network Statistics")
        self.lbl_network_title.setStyleSheet("font-size: 25px; font-weight: bold; color: #abb2bf;")
        network_layout.addWidget(self.lbl_network_title)

        # Network interfaces
        self.network_interfaces = get_network_interfaces()
        self.network_labels = {}

        for iface in self.network_interfaces:
            iface_frame = QFrame()
            iface_layout = QVBoxLayout(iface_frame)
            iface_frame.setStyleSheet("background-color: #21252b; border-radius: 10px; padding: 10px; margin-bottom: 10px;")

            iface_title = QLabel(f"Interface: {iface}")
            iface_title.setStyleSheet("font-size: 20px; font-weight: bold; color: #2979FF;")
            iface_layout.addWidget(iface_title)

            throughput_label = QLabel(f"Throughput: ↓ 0.00 Mbps | ↑ 0.00 Mbps")
            throughput_label.setStyleSheet("font-size: 16px; color: #abb2bf;")
            iface_layout.addWidget(throughput_label)

            stats_label = QLabel(f"Packets: RX 0 | TX 0 | Errors: RX 0 | TX 0")
            stats_label.setStyleSheet("font-size: 14px; color: #aaaaaa;")
            iface_layout.addWidget(stats_label)

            self.network_labels[iface] = {
                'throughput': throughput_label,
                'stats': stats_label
            }

            network_layout.addWidget(iface_frame)

        # Network connections count
        self.lbl_connections = QLabel("Active Network Connections: 0")
        self.lbl_connections.setStyleSheet("font-size: 18px; font-weight: bold; color: #abb2bf; margin-top: 10px;")
        network_layout.addWidget(self.lbl_connections)

        network_layout.addStretch()

        self.tabs.addTab(network_tab, "Network")

    def create_system_info_tab(self):
        info_tab = QWidget()
        info_layout = QVBoxLayout(info_tab)
        info_layout.setContentsMargins(10, 10, 10, 10)
        info_layout.setSpacing(15)

        self.lbl_sysinfo_title = QLabel("System Information")
        self.lbl_sysinfo_title.setStyleSheet("font-size: 25px; font-weight: bold; color: #abb2bf;")
        info_layout.addWidget(self.lbl_sysinfo_title)

        # Memory Breakdown
        mem_frame = QFrame()
        mem_layout = QVBoxLayout(mem_frame)
        mem_frame.setStyleSheet("background-color: #21252b; border-radius: 10px; padding: 15px; margin-bottom: 10px;")

        mem_title = QLabel("Memory Breakdown")
        mem_title.setStyleSheet("font-size: 20px; font-weight: bold; color: #2979FF;")
        mem_layout.addWidget(mem_title)

        self.lbl_cached = QLabel("Cached: N/A")
        self.lbl_cached.setStyleSheet("font-size: 16px; color: #abb2bf;")
        mem_layout.addWidget(self.lbl_cached)

        self.lbl_buffers = QLabel("Buffers: N/A")
        self.lbl_buffers.setStyleSheet("font-size: 16px; color: #abb2bf;")
        mem_layout.addWidget(self.lbl_buffers)

        self.lbl_shared = QLabel("Shared: N/A")
        self.lbl_shared.setStyleSheet("font-size: 16px; color: #abb2bf;")
        mem_layout.addWidget(self.lbl_shared)

        info_layout.addWidget(mem_frame)

        # CPU Frequency
        freq_frame = QFrame()
        freq_layout = QVBoxLayout(freq_frame)
        freq_frame.setStyleSheet("background-color: #21252b; border-radius: 10px; padding: 15px; margin-bottom: 10px;")

        freq_title = QLabel("CPU Frequencies")
        freq_title.setStyleSheet("font-size: 20px; font-weight: bold; color: #2979FF;")
        freq_layout.addWidget(freq_title)

        self.lbl_frequencies = QLabel("Loading...")
        self.lbl_frequencies.setStyleSheet("font-size: 16px; color: #abb2bf;")
        freq_layout.addWidget(self.lbl_frequencies)

        info_layout.addWidget(freq_frame)

        # System Stats
        sys_frame = QFrame()
        sys_layout = QVBoxLayout(sys_frame)
        sys_frame.setStyleSheet("background-color: #21252b; border-radius: 10px; padding: 15px; margin-bottom: 10px;")

        sys_title = QLabel("System Statistics")
        sys_title.setStyleSheet("font-size: 20px; font-weight: bold; color: #2979FF;")
        sys_layout.addWidget(sys_title)

        self.lbl_context_switches = QLabel("Context Switches: N/A")
        self.lbl_context_switches.setStyleSheet("font-size: 16px; color: #abb2bf;")
        sys_layout.addWidget(self.lbl_context_switches)

        self.lbl_file_descriptors = QLabel("File Descriptors: N/A")
        self.lbl_file_descriptors.setStyleSheet("font-size: 16px; color: #abb2bf;")
        sys_layout.addWidget(self.lbl_file_descriptors)

        self.lbl_process_counts = QLabel("Processes: N/A")
        self.lbl_process_counts.setStyleSheet("font-size: 16px; color: #abb2bf;")
        sys_layout.addWidget(self.lbl_process_counts)

        info_layout.addWidget(sys_frame)

        # Disk I/O
        disk_io_frame = QFrame()
        disk_io_layout = QVBoxLayout(disk_io_frame)
        disk_io_frame.setStyleSheet("background-color: #21252b; border-radius: 10px; padding: 15px; margin-bottom: 10px;")

        disk_io_title = QLabel("Disk I/O Rates")
        disk_io_title.setStyleSheet("font-size: 20px; font-weight: bold; color: #2979FF;")
        disk_io_layout.addWidget(disk_io_title)

        self.disk_devices = get_disk_devices()
        self.lbl_disk_io = {}

        for device in self.disk_devices:
            lbl = QLabel(f"{device}: Read 0.00 MB/s | Write 0.00 MB/s")
            lbl.setStyleSheet("font-size: 16px; color: #abb2bf;")
            disk_io_layout.addWidget(lbl)
            self.lbl_disk_io[device] = lbl

        info_layout.addWidget(disk_io_frame)

        # Battery (if available)
        battery_frame = QFrame()
        battery_layout = QVBoxLayout(battery_frame)
        battery_frame.setStyleSheet("background-color: #21252b; border-radius: 10px; padding: 15px; margin-bottom: 10px;")

        battery_title = QLabel("Battery Information")
        battery_title.setStyleSheet("font-size: 20px; font-weight: bold; color: #2979FF;")
        battery_layout.addWidget(battery_title)

        self.lbl_battery = QLabel("Battery: N/A")
        self.lbl_battery.setStyleSheet("font-size: 16px; color: #abb2bf;")
        battery_layout.addWidget(self.lbl_battery)

        info_layout.addWidget(battery_frame)

        info_layout.addStretch()

        self.tabs.addTab(info_tab, "System Info")

    def setup_theme(self):
        palette = QPalette()
        palette.setColor(QPalette.ColorRole.Window, QColor(40, 44, 52))
        palette.setColor(QPalette.ColorRole.WindowText, Qt.GlobalColor.white)
        self.setPalette(palette)

    def update_system_stats(self):
        # Uptime
        sec = c_lib.get_uptime_seconds()
        m, s = divmod(sec, 60)
        h, m = divmod(m, 60)
        self.lbl_uptime.setText(f"System Uptime: {int(h)}h {int(m)}m {int(s)}s")

        # CPU
        cpu = c_lib.get_cpu_usage()
        self.cpu_bar.setValue(int(cpu))
        if cpu > 75:
             self.cpu_bar.setStyleSheet(self.cpu_bar.styleSheet().replace("#2979FF", "#FF6D00"))
        else:
             self.cpu_bar.setStyleSheet(self.cpu_bar.styleSheet().replace("#FF6D00", "#2979FF"))

        # CPU Temperature
        temp = c_lib.get_cpu_temperature()
        if temp > 0:
            temp_color = "#FF6D00" if temp > 70 else "#2979FF"
            self.lbl_temp.setText(f"CPU Temp: {temp:.1f}°C")
            self.lbl_temp.setStyleSheet(f"font-size: 18px; color: {temp_color}; margin-top: 5px;")
        else:
            self.lbl_temp.setText("CPU Temp: N/A")

        # Load Averages
        load1 = ctypes.c_double()
        load5 = ctypes.c_double()
        load15 = ctypes.c_double()
        c_lib.get_load_averages(ctypes.byref(load1), ctypes.byref(load5), ctypes.byref(load15))
        self.lbl_load.setText(f"Load Avg: {load1.value:.2f}, {load5.value:.2f}, {load15.value:.2f}")

        # I/O Wait
        iowait = c_lib.get_iowait_percentage()
        self.lbl_iowait.setText(f"I/O Wait: {iowait:.2f}%")

        # Memory Gauge
        total = ctypes.c_long()
        free = ctypes.c_long()
        c_lib.get_memory_usage(ctypes.byref(total), ctypes.byref(free))
        total_mb = total.value // 1024
        used_mb = total_mb - (free.value // 1024)
        self.mem_gauge.set_data(used_mb, total_mb)

        # Per-Core CPU Usage
        self.update_per_core_cpu()

        # Disk Usage
        disk_percent, disk_used, disk_total = get_disk_usage()
        self.disk_bar.setValue(int(disk_percent))
        self.disk_bar.setFormat(f"{disk_percent:.1f}% ({disk_used} GB / {disk_total} GB)")
        if disk_percent > 75:
            self.disk_bar.setStyleSheet(self.disk_bar.styleSheet().replace("#2979FF", "#FF6D00"))
        else:
            self.disk_bar.setStyleSheet(self.disk_bar.styleSheet().replace("#FF6D00", "#2979FF"))

        # Swap Usage
        swap_total = ctypes.c_long()
        swap_free = ctypes.c_long()
        c_lib.get_swap_usage(ctypes.byref(swap_total), ctypes.byref(swap_free))
        if swap_total.value > 0:
            swap_used_mb = (swap_total.value - swap_free.value) // 1024
            swap_total_mb = swap_total.value // 1024
            swap_percent = ((swap_total.value - swap_free.value) / swap_total.value) * 100
            self.swap_bar.setValue(int(swap_percent))
            self.swap_bar.setFormat(f"{swap_percent:.1f}% ({swap_used_mb} MB / {swap_total_mb} MB)")
            if swap_percent > 75:
                self.swap_bar.setStyleSheet(self.swap_bar.styleSheet().replace("#2979FF", "#FF6D00"))
            else:
                self.swap_bar.setStyleSheet(self.swap_bar.styleSheet().replace("#FF6D00", "#2979FF"))
        else:
            self.swap_bar.setValue(0)
            self.swap_bar.setFormat("No Swap Available")

        # Process Table
        self.update_process_table()

        # Network Stats
        self.update_network_stats()

        # System Info
        self.update_system_info()

    def update_per_core_cpu(self):
        core_usages = get_per_core_cpu_usage()
        
        # Create bars if they don't exist
        while len(self.core_bars) < len(core_usages):
            core_num = len(self.core_bars)
            
            core_container = QWidget()
            core_layout = QHBoxLayout(core_container)
            core_layout.setContentsMargins(0, 0, 0, 0)
            
            core_label = QLabel(f"Core {core_num}:")
            core_label.setStyleSheet("font-size: 14px; color: #abb2bf; min-width: 70px;")
            
            core_bar = QProgressBar()
            core_bar.setTextVisible(True)
            core_bar.setStyleSheet("""
                QProgressBar {
                    border: 2px solid #444;
                    font-size: 14px;
                    font-weight: bold;
                    border-radius: 5px;
                    text-align: center;
                    background-color: #282c34;
                    color: white;
                    height: 20px;
                }
                QProgressBar::chunk {
                    background-color: #2979FF;
                    border-radius: 3px;
                }
            """)
            
            core_layout.addWidget(core_label)
            core_layout.addWidget(core_bar)
            
            self.core_bars_layout.addWidget(core_container)
            self.core_bars.append((core_bar, core_container))
        
        # Update bar values
        for i, usage in enumerate(core_usages):
            if i < len(self.core_bars):
                bar, _ = self.core_bars[i]
                bar.setValue(int(usage))
                if usage > 75:
                    bar.setStyleSheet(bar.styleSheet().replace("#2979FF", "#FF6D00"))
                else:
                    bar.setStyleSheet(bar.styleSheet().replace("#FF6D00", "#2979FF"))

    def update_process_table(self):
        if self.table.verticalScrollBar().isSliderDown():
            return

        processes = get_process_list()
        self.table.setRowCount(len(processes))

        for row, (pid, name, state, mem) in enumerate(processes):
            self.table.setItem(row, 0, QTableWidgetItem(str(pid)))
            self.table.setItem(row, 1, QTableWidgetItem(name))

            item_state = QTableWidgetItem(state)
            item_state.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 2, item_state)

            item_mem = QTableWidgetItem(f"{mem} MB")
            item_mem.setTextAlignment(Qt.AlignmentFlag.AlignRight)
            self.table.setItem(row, 3, item_mem)

            # Per-process CPU usage
            cpu_usage = c_lib.get_process_cpu_usage(pid)
            item_cpu = QTableWidgetItem(f"{cpu_usage:.1f}%")
            item_cpu.setTextAlignment(Qt.AlignmentFlag.AlignRight)
            self.table.setItem(row, 4, item_cpu)

            # Disk I/O (read from /proc/[pid]/io if available)
            disk_io = self.get_process_disk_io(pid)
            item_io = QTableWidgetItem(disk_io)
            item_io.setTextAlignment(Qt.AlignmentFlag.AlignRight)
            self.table.setItem(row, 5, item_io)

            # File descriptors
            fd_count = c_lib.get_process_fd_count(pid)
            item_fd = QTableWidgetItem(str(fd_count))
            item_fd.setTextAlignment(Qt.AlignmentFlag.AlignRight)
            self.table.setItem(row, 6, item_fd)

    def get_process_disk_io(self, pid):
        """Get disk I/O information for a process."""
        try:
            with open(f'/proc/{pid}/io', 'r') as f:
                read_bytes = 0
                write_bytes = 0
                for line in f:
                    if line.startswith('read_bytes:'):
                        read_bytes = int(line.split(':')[1].strip())
                    elif line.startswith('write_bytes:'):
                        write_bytes = int(line.split(':')[1].strip())
                
                total_mb = (read_bytes + write_bytes) / (1024 * 1024)
                if total_mb > 1024:
                    return f"{total_mb/1024:.1f} GB"
                elif total_mb > 1:
                    return f"{total_mb:.1f} MB"
                else:
                    return f"{total_mb*1024:.0f} KB"
        except (IOError, PermissionError, FileNotFoundError):
            return "N/A"

    def update_network_stats(self):
        # Update throughput for each interface
        for iface in self.network_interfaces:
            rx_mbps = ctypes.c_double()
            tx_mbps = ctypes.c_double()
            c_lib.get_network_throughput(iface.encode('utf-8'), ctypes.byref(rx_mbps), ctypes.byref(tx_mbps))
            
            self.network_labels[iface]['throughput'].setText(
                f"Throughput: ↓ {rx_mbps.value:.2f} Mbps | ↑ {tx_mbps.value:.2f} Mbps"
            )

            # Get packet stats
            rx_bytes = ctypes.c_longlong()
            tx_bytes = ctypes.c_longlong()
            rx_packets = ctypes.c_longlong()
            tx_packets = ctypes.c_longlong()
            rx_errors = ctypes.c_longlong()
            tx_errors = ctypes.c_longlong()
            
            c_lib.get_network_stats(iface.encode('utf-8'), 
                                   ctypes.byref(rx_bytes), ctypes.byref(tx_bytes),
                                   ctypes.byref(rx_packets), ctypes.byref(tx_packets),
                                   ctypes.byref(rx_errors), ctypes.byref(tx_errors))
            
            self.network_labels[iface]['stats'].setText(
                f"Packets: RX {rx_packets.value} | TX {tx_packets.value} | Errors: RX {rx_errors.value} | TX {tx_errors.value}"
            )

        # Network connections count
        connections = c_lib.get_network_connections_count()
        self.lbl_connections.setText(f"Active Network Connections: {connections}")

    def update_system_info(self):
        # Memory Breakdown
        cached = ctypes.c_long()
        buffers = ctypes.c_long()
        shared = ctypes.c_long()
        c_lib.get_memory_breakdown(ctypes.byref(cached), ctypes.byref(buffers), ctypes.byref(shared))
        
        self.lbl_cached.setText(f"Cached: {cached.value // 1024} MB")
        self.lbl_buffers.setText(f"Buffers: {buffers.value // 1024} MB")
        self.lbl_shared.setText(f"Shared: {shared.value // 1024} MB")

        # CPU Frequencies
        core_count = len(get_per_core_cpu_usage())
        freq_text = ""
        for i in range(core_count):
            freq = c_lib.get_cpu_frequency(i)
            if freq > 0:
                freq_text += f"Core {i}: {freq:.0f} MHz\n"
        
        if freq_text:
            self.lbl_frequencies.setText(freq_text.strip())
        else:
            self.lbl_frequencies.setText("Frequency information not available")

        # Context Switches
        current_ctxt = c_lib.get_context_switches()
        if self.prev_context_switches > 0:
            ctxt_per_sec = current_ctxt - self.prev_context_switches
            self.lbl_context_switches.setText(f"Context Switches: {ctxt_per_sec:,}/sec (Total: {current_ctxt:,})")
        else:
            self.lbl_context_switches.setText(f"Context Switches: {current_ctxt:,}")
        self.prev_context_switches = current_ctxt

        # File Descriptors
        allocated = ctypes.c_long()
        max_fd = ctypes.c_long()
        c_lib.get_file_descriptors(ctypes.byref(allocated), ctypes.byref(max_fd))
        if max_fd.value > 0:
            fd_percent = (allocated.value / max_fd.value) * 100
            self.lbl_file_descriptors.setText(f"File Descriptors: {allocated.value:,} / {max_fd.value:,} ({fd_percent:.1f}%)")
        else:
            self.lbl_file_descriptors.setText(f"File Descriptors: {allocated.value:,}")

        # Process Counts
        running = ctypes.c_int()
        sleeping = ctypes.c_int()
        stopped = ctypes.c_int()
        zombie = ctypes.c_int()
        c_lib.get_process_counts(ctypes.byref(running), ctypes.byref(sleeping), 
                                ctypes.byref(stopped), ctypes.byref(zombie))
        total = running.value + sleeping.value + stopped.value + zombie.value
        self.lbl_process_counts.setText(
            f"Processes: Total {total} | Running {running.value} | Sleeping {sleeping.value} | Stopped {stopped.value} | Zombie {zombie.value}"
        )

        # Disk I/O Rates
        for device in self.disk_devices:
            read_mbps = ctypes.c_double()
            write_mbps = ctypes.c_double()
            c_lib.get_disk_io_rates(device.encode('utf-8'), ctypes.byref(read_mbps), ctypes.byref(write_mbps))
            self.lbl_disk_io[device].setText(f"{device}: Read {read_mbps.value:.2f} MB/s | Write {write_mbps.value:.2f} MB/s")

        # Battery Info
        percentage = ctypes.c_int()
        is_charging = ctypes.c_int()
        charge_rate = ctypes.c_double()
        c_lib.get_battery_info(ctypes.byref(percentage), ctypes.byref(is_charging), ctypes.byref(charge_rate))
        
        if percentage.value >= 0:
            status = "Charging" if is_charging.value else "Discharging"
            self.lbl_battery.setText(f"Battery: {percentage.value}% ({status}) | Power: {charge_rate.value:.2f}W")
        else:
            self.lbl_battery.setText("Battery: Not Available")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = ProfessionalMonitor()
    window.show()
    sys.exit(app.exec())