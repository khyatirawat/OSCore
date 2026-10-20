#include "../ProcessManagement/process_manager.h"
#include "../ProcessManagement/scheduler.h"
#include "../ProcessSynchronization/semaphore.h"
#include "../DeadlockManagement/deadlock.h"
#include "../BankersAlgorithm/banker.h"

#include <iostream>
#include <map>
#include <set>
#include <string>
#include <vector>
#include <algorithm>

int main() {
    std::string input;
    std::getline(std::cin, input);
    if (input.find("banker_demo") != std::string::npos) {
        auto result = checkSafeState(
            {3, 3, 2},
            {{0, 1, 0}, {2, 0, 0}, {3, 0, 2}, {2, 1, 1}, {0, 0, 2}},
            {{7, 5, 3}, {3, 2, 2}, {9, 0, 2}, {2, 2, 2}, {4, 3, 3}}
        );
        std::cout << "{\"ok\":true,\"algorithm\":\"Banker's Algorithm\",\"safe\":"
                  << (result.safe ? "true" : "false") << ",\"safe_sequence\":[";
        for (std::size_t i = 0; i < result.safeSequence.size(); ++i) {
            if (i) std::cout << ",";
            std::cout << "\"P" << result.safeSequence[i] << "\"";
        }
        std::cout << "],\"message\":\"Safe-state check completed.\"}";
        return 0;
    }

    if (input.find("deadlock_demo") != std::string::npos) {
        std::map<int, std::set<int>> graph{{1001, {1002}}, {1002, {1001}}};
        auto deadlocked = findDeadlockedProcesses(graph);
        std::cout << "{\"ok\":true,\"algorithm\":\"Wait-for graph cycle detection\",\"deadlock_detected\":"
                  << (!deadlocked.empty() ? "true" : "false") << ",\"processes\":[";
        for (std::size_t i = 0; i < deadlocked.size(); ++i) {
            if (i) std::cout << ",";
            std::cout << deadlocked[i];
        }
        std::cout << "],\"message\":\"Cycle detection demo completed.\"}";
        return 0;
    }

    CountingSemaphore printer(2);
    bool p1 = printer.wait(1001);
    bool p2 = printer.wait(1002);
    bool p3 = printer.wait(1003);
    int awakened = printer.signal();
    std::cout << "{\"ok\":true,\"demo\":\"counting_semaphore\","
              << "\"p1_acquired\":" << (p1 ? "true" : "false") << ","
              << "\"p2_acquired\":" << (p2 ? "true" : "false") << ","
              << "\"p3_acquired\":" << (p3 ? "true" : "false") << ","
              << "\"awakened_pid\":" << awakened << ","
              << "\"semaphore_value\":" << printer.value() << "}";
    return 0;
}
