#include <iostream>
#include <fstream>
#include <string>
#include <sstream>
#include <vector>
#include <unistd.h>
#include <map>
#include <dirent.h>

using namespace std;

extern "C" {

    // --- STRUCTS ---
    struct CpuStats {
        long long user, nice, system, idle, iowait, irq, softirq, steal;
    };

    struct ProcStats {
        long long utime;
        long long stime;
        long long rss;
    };

    struct NetworkStats {
        long long rx_bytes;
        long long tx_bytes;
        long long rx_packets;
        long long tx_packets;
        long long rx_errors;
        long long tx_errors;
    };

    struct DiskIOStats {
        long long read_bytes;
        long long write_bytes;
    };

    // Static variables to hold state between updates
    static CpuStats prev_cpu_stats = {0};
    static map<int, long long> prev_proc_times;
    static map<string, NetworkStats> prev_net_stats;
    static map<string, DiskIOStats> prev_disk_stats;

    // --- FUNCTION 1: UPTIME ---
    double get_uptime_seconds() {
        ifstream file("/proc/uptime");
        double uptime_seconds = 0.0;
        if (file.is_open()) {
            string line;
            getline(file, line);
            istringstream ss(line);
            ss >> uptime_seconds;
            file.close();
        }
        return uptime_seconds;
    }

    // --- FUNCTION 2: MEMORY ---
    void get_memory_usage(long* total_k, long* free_k) {
        ifstream memInfo("/proc/meminfo");
        string line;
        *total_k = 0;
        *free_k = 0;

        if (memInfo.is_open()) {
            while (getline(memInfo, line)) {
                if (line.find("MemTotal:") == 0) {
                    string val = line.substr(line.find(":") + 1);
                    val = val.substr(0, val.find("kB"));
                    *total_k = stol(val);
                }
                else if (line.find("MemAvailable:") == 0) {
                    string val = line.substr(line.find(":") + 1);
                    val = val.substr(0, val.find("kB"));
                    *free_k = stol(val);
                }
            }
            memInfo.close();
        }
    }

    // --- FUNCTION 3: TOTAL CPU USAGE ---
    double get_cpu_usage() {
        ifstream file("/proc/stat");
        CpuStats curr = {0};

        if (file.is_open()) {
            string line, label;
            getline(file, line);
            istringstream ss(line);
            ss >> label >> curr.user >> curr.nice >> curr.system >> curr.idle
               >> curr.iowait >> curr.irq >> curr.softirq >> curr.steal;
            file.close();
        }

        if (prev_cpu_stats.user == 0 && prev_cpu_stats.idle == 0) {
            prev_cpu_stats = curr;
            return 0.0;
        }

        long long prevIdle = prev_cpu_stats.idle + prev_cpu_stats.iowait;
        long long currIdle = curr.idle + curr.iowait;

        long long prevNonIdle = prev_cpu_stats.user + prev_cpu_stats.nice + prev_cpu_stats.system + prev_cpu_stats.irq + prev_cpu_stats.softirq + prev_cpu_stats.steal;
        long long currNonIdle = curr.user + curr.nice + curr.system + curr.irq + curr.softirq + curr.steal;

        long long totalDelta = (currIdle + currNonIdle) - (prevIdle + prevNonIdle);
        long long idleDelta = currIdle - prevIdle;

        double percentage = 0.0;
        if (totalDelta > 0) {
             percentage = (double)(totalDelta - idleDelta) / totalDelta * 100.0;
        }

        prev_cpu_stats = curr;
        return percentage;
    }

    // --- FUNCTION 4: PER-PROCESS CPU USAGE ---
    double get_process_cpu_usage(int pid) {
        ifstream f("/proc/" + to_string(pid) + "/stat");
        if (!f.is_open()) return 0.0;

        string tmp;
        long long utime, stime;
        
        // Skip to fields 14 and 15 (utime and stime)
        for (int i = 0; i < 13; i++) f >> tmp;
        f >> utime >> stime;
        f.close();

        long long total = utime + stime;
        
        // Get previous time for this process
        long long prev_time = 0;
        if (prev_proc_times.find(pid) != prev_proc_times.end()) {
            prev_time = prev_proc_times[pid];
        }
        
        // Calculate delta
        long long delta = total - prev_time;
        
        // Store current time for next iteration
        prev_proc_times[pid] = total;
        
        // Convert to percentage (delta is in jiffies, divide by time period in jiffies)
        // Assuming 1 second update interval and using sysconf to get clock ticks per second
        long hz = sysconf(_SC_CLK_TCK);
        if (hz <= 0) hz = 100; // fallback
        
        double percentage = (double)delta / hz * 100.0;
        
        // Cap at reasonable value (some processes might spike)
        if (percentage > 100.0) percentage = 100.0;
        if (percentage < 0.0) percentage = 0.0;
        
        return percentage;
    }

    // --- FUNCTION 5: PER-PROCESS MEMORY ---
    long get_process_memory_mb(int pid) {
        ifstream f("/proc/" + to_string(pid) + "/status");
        string line;
        while (getline(f, line)) {
            if (line.find("VmRSS:") == 0) {
                string val = line.substr(line.find(":") + 1);
                val = val.substr(0, val.find("kB"));
                long kb = stol(val);
                return kb / 1024;
            }
        }
        return 0;
    }

    // --- FUNCTION 6: LOAD AVERAGES ---
    void get_load_averages(double* load1, double* load5, double* load15) {
        ifstream file("/proc/loadavg");
        if (file.is_open()) {
            file >> *load1 >> *load5 >> *load15;
            file.close();
        } else {
            *load1 = *load5 = *load15 = 0.0;
        }
    }

    // --- FUNCTION 7: SWAP USAGE ---
    void get_swap_usage(long* total_k, long* free_k) {
        ifstream memInfo("/proc/meminfo");
        string line;
        *total_k = 0;
        *free_k = 0;

        if (memInfo.is_open()) {
            while (getline(memInfo, line)) {
                if (line.find("SwapTotal:") == 0) {
                    string val = line.substr(line.find(":") + 1);
                    val = val.substr(0, val.find("kB"));
                    *total_k = stol(val);
                }
                else if (line.find("SwapFree:") == 0) {
                    string val = line.substr(line.find(":") + 1);
                    val = val.substr(0, val.find("kB"));
                    *free_k = stol(val);
                }
            }
            memInfo.close();
        }
    }

    // --- FUNCTION 8: MEMORY BREAKDOWN ---
    void get_memory_breakdown(long* cached_k, long* buffers_k, long* shared_k) {
        ifstream memInfo("/proc/meminfo");
        string line;
        *cached_k = 0;
        *buffers_k = 0;
        *shared_k = 0;

        if (memInfo.is_open()) {
            while (getline(memInfo, line)) {
                if (line.find("Cached:") == 0) {
                    string val = line.substr(line.find(":") + 1);
                    val = val.substr(0, val.find("kB"));
                    *cached_k = stol(val);
                }
                else if (line.find("Buffers:") == 0) {
                    string val = line.substr(line.find(":") + 1);
                    val = val.substr(0, val.find("kB"));
                    *buffers_k = stol(val);
                }
                else if (line.find("Shmem:") == 0) {
                    string val = line.substr(line.find(":") + 1);
                    val = val.substr(0, val.find("kB"));
                    *shared_k = stol(val);
                }
            }
            memInfo.close();
        }
    }

    // --- FUNCTION 9: IO WAIT PERCENTAGE ---
    double get_iowait_percentage() {
        ifstream file("/proc/stat");
        CpuStats curr = {0};

        if (file.is_open()) {
            string line, label;
            getline(file, line);
            istringstream ss(line);
            ss >> label >> curr.user >> curr.nice >> curr.system >> curr.idle
               >> curr.iowait >> curr.irq >> curr.softirq >> curr.steal;
            file.close();
        }

        long long total = curr.user + curr.nice + curr.system + curr.idle + curr.iowait + curr.irq + curr.softirq + curr.steal;
        
        if (total > 0) {
            return (double)curr.iowait / total * 100.0;
        }
        return 0.0;
    }

    // --- FUNCTION 10: CONTEXT SWITCHES ---
    long long get_context_switches() {
        ifstream file("/proc/stat");
        string line;
        
        if (file.is_open()) {
            while (getline(file, line)) {
                if (line.find("ctxt") == 0) {
                    istringstream ss(line);
                    string label;
                    long long ctxt;
                    ss >> label >> ctxt;
                    file.close();
                    return ctxt;
                }
            }
            file.close();
        }
        return 0;
    }

    // --- FUNCTION 11: NETWORK STATS ---
    void get_network_stats(const char* interface, long long* rx_bytes, long long* tx_bytes, 
                          long long* rx_packets, long long* tx_packets,
                          long long* rx_errors, long long* tx_errors) {
        string path = "/sys/class/net/" + string(interface) + "/statistics/";
        
        ifstream rx_b(path + "rx_bytes");
        ifstream tx_b(path + "tx_bytes");
        ifstream rx_p(path + "rx_packets");
        ifstream tx_p(path + "tx_packets");
        ifstream rx_e(path + "rx_errors");
        ifstream tx_e(path + "tx_errors");
        
        if (rx_b.is_open()) rx_b >> *rx_bytes;
        if (tx_b.is_open()) tx_b >> *tx_bytes;
        if (rx_p.is_open()) rx_p >> *rx_packets;
        if (tx_p.is_open()) tx_p >> *tx_packets;
        if (rx_e.is_open()) rx_e >> *rx_errors;
        if (tx_e.is_open()) tx_e >> *tx_errors;
    }

    // --- FUNCTION 12: NETWORK THROUGHPUT ---
    void get_network_throughput(const char* interface, double* rx_mbps, double* tx_mbps) {
        long long rx_bytes = 0, tx_bytes = 0, rx_packets = 0, tx_packets = 0, rx_errors = 0, tx_errors = 0;
        get_network_stats(interface, &rx_bytes, &tx_bytes, &rx_packets, &tx_packets, &rx_errors, &tx_errors);
        
        NetworkStats curr = {rx_bytes, tx_bytes, rx_packets, tx_packets, rx_errors, tx_errors};
        string iface(interface);
        
        if (prev_net_stats.find(iface) != prev_net_stats.end()) {
            NetworkStats& prev = prev_net_stats[iface];
            long long rx_delta = curr.rx_bytes - prev.rx_bytes;
            long long tx_delta = curr.tx_bytes - prev.tx_bytes;
            
            // Convert to Mbps (bytes per second * 8 / 1,000,000)
            *rx_mbps = (rx_delta * 8.0) / 1000000.0;
            *tx_mbps = (tx_delta * 8.0) / 1000000.0;
        } else {
            *rx_mbps = 0.0;
            *tx_mbps = 0.0;
        }
        
        prev_net_stats[iface] = curr;
    }

    // --- FUNCTION 13: CPU TEMPERATURE ---
    double get_cpu_temperature() {
        // Try different thermal zones
        for (int i = 0; i < 10; i++) {
            string path = "/sys/class/thermal/thermal_zone" + to_string(i) + "/temp";
            ifstream file(path);
            if (file.is_open()) {
                long temp_millidegrees;
                file >> temp_millidegrees;
                file.close();
                return temp_millidegrees / 1000.0; // Convert to Celsius
            }
        }
        return -1.0; // Not available
    }

    // --- FUNCTION 14: SYSTEM FILE DESCRIPTORS ---
    void get_file_descriptors(long* allocated, long* max_fd) {
        ifstream file("/proc/sys/fs/file-nr");
        if (file.is_open()) {
            long unused;
            file >> *allocated >> unused >> *max_fd;
            file.close();
        } else {
            *allocated = 0;
            *max_fd = 0;
        }
    }

    // --- FUNCTION 15: PER-PROCESS FILE DESCRIPTORS ---
    int get_process_fd_count(int pid) {
        string path = "/proc/" + to_string(pid) + "/fd";
        DIR* dir = opendir(path.c_str());
        if (!dir) return 0;
        
        int count = 0;
        struct dirent* entry;
        while ((entry = readdir(dir)) != nullptr) {
            if (entry->d_name[0] != '.') {
                count++;
            }
        }
        closedir(dir);
        return count;
    }

    // --- FUNCTION 16: BATTERY INFO ---
    void get_battery_info(int* percentage, int* is_charging, double* charge_rate) {
        *percentage = -1;
        *is_charging = 0;
        *charge_rate = 0.0;
        
        // Try BAT0 and BAT1
        for (int i = 0; i < 2; i++) {
            string base_path = "/sys/class/power_supply/BAT" + to_string(i) + "/";
            
            ifstream capacity_file(base_path + "capacity");
            if (capacity_file.is_open()) {
                capacity_file >> *percentage;
                capacity_file.close();
                
                ifstream status_file(base_path + "status");
                if (status_file.is_open()) {
                    string status;
                    status_file >> status;
                    *is_charging = (status == "Charging") ? 1 : 0;
                    status_file.close();
                }
                
                ifstream power_file(base_path + "power_now");
                if (power_file.is_open()) {
                    long power_microwatts;
                    power_file >> power_microwatts;
                    *charge_rate = power_microwatts / 1000000.0; // Convert to watts
                    power_file.close();
                }
                
                break;
            }
        }
    }

    // --- FUNCTION 17: CPU FREQUENCY ---
    double get_cpu_frequency(int core) {
        string path = "/sys/devices/system/cpu/cpu" + to_string(core) + "/cpufreq/scaling_cur_freq";
        ifstream file(path);
        if (file.is_open()) {
            long freq_khz;
            file >> freq_khz;
            file.close();
            return freq_khz / 1000.0; // Convert to MHz
        }
        return -1.0;
    }

    // --- FUNCTION 18: DISK IO RATES ---
    void get_disk_io_rates(const char* disk, double* read_mbps, double* write_mbps) {
        string path = "/sys/block/" + string(disk) + "/stat";
        ifstream file(path);
        
        if (file.is_open()) {
            long long reads, reads_merged, sectors_read, time_reading;
            long long writes, writes_merged, sectors_written, time_writing;
            
            file >> reads >> reads_merged >> sectors_read >> time_reading
                 >> writes >> writes_merged >> sectors_written >> time_writing;
            file.close();
            
            // Sectors are typically 512 bytes
            long long read_bytes = sectors_read * 512;
            long long write_bytes = sectors_written * 512;
            
            DiskIOStats curr = {read_bytes, write_bytes};
            string disk_name(disk);
            
            if (prev_disk_stats.find(disk_name) != prev_disk_stats.end()) {
                DiskIOStats& prev = prev_disk_stats[disk_name];
                long long read_delta = curr.read_bytes - prev.read_bytes;
                long long write_delta = curr.write_bytes - prev.write_bytes;
                
                // Convert to MB/s
                *read_mbps = read_delta / (1024.0 * 1024.0);
                *write_mbps = write_delta / (1024.0 * 1024.0);
            } else {
                *read_mbps = 0.0;
                *write_mbps = 0.0;
            }
            
            prev_disk_stats[disk_name] = curr;
        } else {
            *read_mbps = 0.0;
            *write_mbps = 0.0;
        }
    }

    // --- FUNCTION 19: PROCESS COUNTS BY STATE ---
    void get_process_counts(int* running, int* sleeping, int* stopped, int* zombie) {
        *running = 0;
        *sleeping = 0;
        *stopped = 0;
        *zombie = 0;
        
        DIR* dir = opendir("/proc");
        if (!dir) return;
        
        struct dirent* entry;
        while ((entry = readdir(dir)) != nullptr) {
            if (entry->d_type == DT_DIR) {
                string name = entry->d_name;
                if (name.find_first_not_of("0123456789") == string::npos) {
                    // It's a PID directory
                    string stat_path = "/proc/" + name + "/stat";
                    ifstream file(stat_path);
                    if (file.is_open()) {
                        string line;
                        getline(file, line);
                        
                        // Find the state character (it's after the command name in parentheses)
                        size_t last_paren = line.rfind(')');
                        if (last_paren != string::npos && last_paren + 2 < line.length()) {
                            char state = line[last_paren + 2];
                            switch (state) {
                                case 'R': (*running)++; break;
                                case 'S': case 'D': case 'I': (*sleeping)++; break;
                                case 'T': (*stopped)++; break;
                                case 'Z': (*zombie)++; break;
                            }
                        }
                        file.close();
                    }
                }
            }
        }
        closedir(dir);
    }

    // --- FUNCTION 20: NETWORK CONNECTIONS COUNT ---
    int get_network_connections_count() {
        int count = 0;
        
        // Count TCP connections
        ifstream tcp_file("/proc/net/tcp");
        if (tcp_file.is_open()) {
            string line;
            getline(tcp_file, line); // Skip header
            while (getline(tcp_file, line)) {
                count++;
            }
            tcp_file.close();
        }
        
        // Count TCP6 connections
        ifstream tcp6_file("/proc/net/tcp6");
        if (tcp6_file.is_open()) {
            string line;
            getline(tcp6_file, line); // Skip header
            while (getline(tcp6_file, line)) {
                count++;
            }
            tcp6_file.close();
        }
        
        return count;
    }
}