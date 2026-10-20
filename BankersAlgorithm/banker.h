#ifndef OSCORE_BANKER_H
#define OSCORE_BANKER_H

#include <vector>

struct BankerResult {
    bool safe;
    std::vector<int> safeSequence;
};

BankerResult checkSafeState(
    const std::vector<int>& available,
    const std::vector<std::vector<int>>& allocation,
    const std::vector<std::vector<int>>& maximum
);

#endif
