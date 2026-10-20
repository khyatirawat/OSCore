#ifndef OSCORE_SEMAPHORE_H
#define OSCORE_SEMAPHORE_H

#include <queue>
#include <string>

class CountingSemaphore {
public:
    explicit CountingSemaphore(int permits);
    bool wait(int pid);       // false means the process must block
    int signal();             // returns awakened PID, or -1 if nobody waits
    int value() const;
    std::queue<int> waitingQueue() const;
private:
    int permits_;
    std::queue<int> waiting_;
};

#endif
