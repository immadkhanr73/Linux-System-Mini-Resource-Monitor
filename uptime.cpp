#include <iostream>
#include <fstream>
#include <string>
#include <sstream>
#include <iomanip> // For setfill and setw

using namespace std;

string formatUptime(long total_seconds) {
    if (total_seconds <= 0) return "0 seconds";

    // Convert total seconds into days, hours, minutes, and seconds
    long days = total_seconds / (60 * 60 * 24);
    long remaining_seconds = total_seconds % (60 * 60 * 24);
    
    long hours = remaining_seconds / (60 * 60);
    remaining_seconds %= (60 * 60);
    
    long minutes = remaining_seconds / 60;
    long seconds = remaining_seconds % 60;

    // Use stringstream to build the final formatted string
    stringstream ss;
    
    if (days > 0) {
        ss << days << " days, ";
    }
    
    // Use setw and setfill for HH:MM:SS formatting (e.g., 05:08:12)
    ss << setfill('0') << setw(2) << hours << ":"
       << setfill('0') << setw(2) << minutes << ":"
       << setfill('0') << setw(2) << seconds;

    return ss.str();
}


void getSystemUptime() {
    ifstream file("/proc/uptime");
    string line;
    double uptime_seconds;

    if (file.is_open()) {
        getline(file, line); // Read the line (e.g., "123456.78 98765.43")
        
        // Use stringstream to extract the first number (uptime_seconds)
        istringstream ss(line);
        ss >> uptime_seconds;

        file.close();
    } else {
        cerr << "Unable to open /proc/uptime" << endl;
        return;
    }

    // Convert the double (with fractions) to a long integer (whole seconds)
    long total_seconds = (long)uptime_seconds;

    // Display the result
    cout << "System Uptime: " << formatUptime(total_seconds) << endl;
}

int main() {
    cout << "--- System Resource Monitor (Uptime) ---" << endl;
    getSystemUptime();
    return 0;
}