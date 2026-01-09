#include <iostream>
#include <fstream>
#include <string>
#include <vector>
#include <dirent.h> // REQUIRED for reading directories
#include <ctype.h>  // For isdigit()
#include <iomanip>  // For formatting columns (setw)

using namespace std;

// Structure to hold process info
struct ProcessInfo {
    string pid;
    string name;
    string state;
    string memory;
};

// Helper: Check if a directory name is just numbers (i.e., it is a PID)
bool isPidFolder(const string& name) {
    for (char c : name) {
        if (!isdigit(c)) return false;
    }
    return true;
}

// Helper: Read a specific /proc/[pid]/status file
ProcessInfo getProcessDetails(string pid) {
    ProcessInfo p;
    p.pid = pid;
    
    // Default values if we can't read them
    p.name = "???"; 
    p.state = "?";
    p.memory = "0 kB";

    string path = "/proc/" + pid + "/status";
    ifstream file(path);
    string line;

    if (file.is_open()) {
        while (getline(file, line)) {
            // Find Name
            if (line.find("Name:") == 0) {
                p.name = line.substr(line.find(":") + 1);
                // Remove leading whitespace
                size_t first = p.name.find_first_not_of(" \t");
                if (first != string::npos) p.name = p.name.substr(first);
            }
            // Find State
            else if (line.find("State:") == 0) {
                p.state = line.substr(line.find(":") + 1);
                size_t first = p.state.find_first_not_of(" \t");
                if (first != string::npos) p.state = p.state.substr(first);
            }
            // Find Memory (VmRSS is the actual physical memory used)
            else if (line.find("VmRSS:") == 0) {
                p.memory = line.substr(line.find(":") + 1);
                size_t first = p.memory.find_first_not_of(" \t");
                if (first != string::npos) p.memory = p.memory.substr(first);
            }
        }
        file.close();
    }
    return p;
}

int main() {
    cout << "--- System Resource Monitor (Processes) ---" << endl;
    
    // 1. Open the /proc directory
    DIR* procDir = opendir("/proc");
    struct dirent* entry;

    if (procDir == NULL) {
        cerr << "Error: Could not open /proc directory." << endl;
        return 1;
    }

    // Header formatting
    cout << left << setw(10) << "PID" 
         << left << setw(25) << "NAME" 
         << left << setw(15) << "STATE" 
         << left << setw(15) << "MEMORY" << endl;
    cout << "------------------------------------------------------------" << endl;

    // 2. Iterate through every item in /proc
    while ((entry = readdir(procDir)) != NULL) {
        string dirName = entry->d_name;

        // 3. Filter: We only want directories that are Numbers (PIDs)
        if (isPidFolder(dirName)) {
            ProcessInfo p = getProcessDetails(dirName);
            
            // 4. Display the row
            cout << left << setw(10) << p.pid 
                 << left << setw(25) << p.name.substr(0, 24) // Truncate long names 
                 << left << setw(15) << p.state 
                 << left << setw(15) << p.memory << endl;
        }
    }

    closedir(procDir);
    return 0;
}