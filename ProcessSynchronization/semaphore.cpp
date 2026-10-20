#include "semaphore.h"
#include <stdexcept>

CountingSemaphore::CountingSemaphore(int permits) : permits_(permits) {
    if (permits < 0) throw std::invalid_argument("Semaphore permits cannot be negative");
}

bool CountingSemaphore::wait(int pid) {
    if (permits_ > 0) {
        --permits_;
        return true;
    }
    waiting_.push(pid);
    return false;
}

int CountingSemaphore::signal() {
    if (!waiting_.empty()) {
        int pid = waiting_.front();
        waiting_.pop();
        return pid;
    }
    ++permits_;
    return -1;
}

int CountingSemaphore::value() const { return permits_; }

std::queue<int> CountingSemaphore::waitingQueue() const { return waiting_; }
