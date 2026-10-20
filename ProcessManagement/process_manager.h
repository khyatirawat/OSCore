#ifndef OSCORE_PROCESS_MANAGER_H
#define OSCORE_PROCESS_MANAGER_H

#include <string>
#include <vector>

enum class ProcessState { New, Ready, Running, Blocked, Terminated };

struct Process {
    int pid{};
    std::string name;
    int arrivalTime{};
    int burstTime{};
    int remainingTime{};
    ProcessState state{ProcessState::New};
};

std::string stateToString(ProcessState state);
Process createProcess(int pid, const std::string& name, int arrivalTime, int burstTime);

#endif
