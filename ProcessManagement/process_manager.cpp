#include "process_manager.h"

std::string stateToString(ProcessState state) {
    switch (state) {
        case ProcessState::New: return "NEW";
        case ProcessState::Ready: return "READY";
        case ProcessState::Running: return "RUNNING";
        case ProcessState::Blocked: return "BLOCKED";
        case ProcessState::Terminated: return "TERMINATED";
    }
    return "UNKNOWN";
}

Process createProcess(int pid, const std::string& name, int arrivalTime, int burstTime) {
    Process p;
    p.pid = pid;
    p.name = name;
    p.arrivalTime = arrivalTime;
    p.burstTime = burstTime;
    p.remainingTime = burstTime;
    p.state = ProcessState::Ready;
    return p;
}
