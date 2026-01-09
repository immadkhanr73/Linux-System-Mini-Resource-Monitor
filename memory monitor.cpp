#include <iostream>
#include <fstream>
#include <string>
#include <unistd.h> // For sleep()

using namespace std;

void getMemoryUsage() {
    ifstream memInfo("/proc/meminfo"); // Open the file
    string line;
    long totalMem = 0;
    long freeMem = 0;

    if (memInfo.is_open()) {
        while (getline(memInfo, line)) {
            // Check for Total Memory
            if (line.find("MemTotal:") == 0) {
                string value = line.substr(line.find(":") + 1); // Get part after ":"
                value = value.substr(0, value.find("kB"));      // Remove "kB"
                totalMem = stol(value); // Convert string to number (long)
            }
            // Check for Available/Free Memory
            // Note: MemAvailable is often more accurate than MemFree for actual usability
            else if (line.find("MemAvailable:") == 0) {
                string value = line.substr(line.find(":") + 1);
                value = value.substr(0, value.find("kB"));
                freeMem = stol(value);
            }
        }
        memInfo.close();
    } else {
        cerr << "Unable to open /proc/meminfo" << endl;
        return;
    }

    // Calculation: Used = Total - Free
    long usedMem = totalMem - freeMem;

    // Display
    // Using \r to overwrite the same line for a "real-time" feel
    cout << "\rMemory Usage: " 
         << "Total: " << totalMem / 1024 << " MB | "
         << "Used: " << usedMem / 1024 << " MB | "
         << "Free: " << freeMem / 1024 << " MB      " << flush;
}

int main() {
    cout << "--- System Resource Monitor (Memory) ---" << endl;
    cout << "Press Ctrl+C to exit." << endl;

    while (true) {
        getMemoryUsage();
        sleep(1); // Update every 1 second
    }

    return 0;
}