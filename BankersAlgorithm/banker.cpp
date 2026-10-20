#include "banker.h"
#include <stdexcept>

BankerResult checkSafeState(
    const std::vector<int>& available,
    const std::vector<std::vector<int>>& allocation,
    const std::vector<std::vector<int>>& maximum
) {
    if (allocation.size() != maximum.size())
        throw std::invalid_argument("Allocation and maximum matrices must have same rows");
    for (std::size_t i = 0; i < allocation.size(); ++i) {
        if (allocation[i].size() != available.size() || maximum[i].size() != available.size())
            throw std::invalid_argument("Resource matrix columns must match available vector");
    }

    std::vector<int> work = available;
    std::vector<bool> finished(allocation.size(), false);
    std::vector<int> sequence;
    bool progressed = true;

    while (progressed) {
        progressed = false;
        for (std::size_t p = 0; p < allocation.size(); ++p) {
            if (finished[p]) continue;
            bool canFinish = true;
            for (std::size_t r = 0; r < available.size(); ++r) {
                int need = maximum[p][r] - allocation[p][r];
                if (need < 0) throw std::invalid_argument("Maximum cannot be less than allocation");
                if (need > work[r]) { canFinish = false; break; }
            }
            if (canFinish) {
                for (std::size_t r = 0; r < available.size(); ++r) work[r] += allocation[p][r];
                finished[p] = true;
                sequence.push_back(static_cast<int>(p));
                progressed = true;
            }
        }
    }

    bool safe = true;
    for (bool done : finished) if (!done) safe = false;
    return {safe, sequence};
}
