#include "scheduler.h"
#include <algorithm>
#include <numeric>

std::vector<int> fcfsOrder(const std::vector<Process>& processes) {
    std::vector<int> order;
    for (int i = 0; i < static_cast<int>(processes.size()); ++i) {
        if (processes[i].state != ProcessState::Terminated)
            order.push_back(i);
    }
    std::stable_sort(order.begin(), order.end(), [&processes](int a, int b) {
        if (processes[a].arrivalTime != processes[b].arrivalTime)
            return processes[a].arrivalTime < processes[b].arrivalTime;
        return processes[a].pid < processes[b].pid;
    });
    return order;
}
