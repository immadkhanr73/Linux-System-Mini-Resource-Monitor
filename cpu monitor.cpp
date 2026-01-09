#include <iostream>
#include <fstream>
#include <string>
#include <vector>
#include <sstream>
#include <unistd.h> // For sleep()

using namespace std;

// Structure to hold the snapshot of CPU data
struct CpuStats {
    long long user, nice, system, idle, iowait, irq, softirq, steal;
};

// Function to read /proc/stat and parse values
CpuStats getCpuData() {
    ifstream file("/proc/stat");
    string line;
    CpuStats stats = {0};

    if (file.is_open()) {
        getline(file, line); // We only need the first line (aggregate cpu)
        string label;
        
        // Use stringstream to parse the line easily
        istringstream ss(line);
        
        // The first part is text "cpu", we skip it
        ss >> label >> stats.user >> stats.nice >> stats.system >> stats.idle 
           >> stats.iowait >> stats.irq >> stats.softirq >> stats.steal;
        
        file.close();
    } else {
        cerr << "Error opening /proc/stat" << endl;
    }
    return stats;
}

int main() {
    cout << "--- System Resource Monitor (CPU) ---" << endl;
    cout << "Press Ctrl+C to exit." << endl;

    // 1. Take initial snapshot
    CpuStats prev = getCpuData();

    while (true) {
        // 2. Wait for 1 second (to let time pass)
        sleep(1);

        // 3. Take second snapshot
        CpuStats curr = getCpuData();

        // 4. Calculate the differences (Deltas)
        long long prevIdle = prev.idle + prev.iowait;
        long long currIdle = curr.idle + curr.iowait;

        long long prevNonIdle = prev.user + prev.nice + prev.system + prev.irq + prev.softirq + prev.steal;
        long long currNonIdle = curr.user + curr.nice + curr.system + curr.irq + curr.softirq + curr.steal;

        long long prevTotal = prevIdle + prevNonIdle;
        long long currTotal = currIdle + currNonIdle;

        long long totalDelta = currTotal - prevTotal;
        long long idleDelta = currIdle - prevIdle;

        // 5. Calculate Percentage
        // Avoid division by zero
        double percentage = 0.0;
        if (totalDelta > 0) {
             percentage = (double)(totalDelta - idleDelta) / totalDelta * 100.0;
        }

        // 6. Display
        cout << "\rCPU Usage: " << percentage << "%     " << flush;

        // 7. Update 'prev' for the next loop iteration
        prev = curr;
    }

    return 0;
}