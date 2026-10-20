#include "deadlock.h"
#include <algorithm>
#include <functional>

std::vector<int> findDeadlockedProcesses(const std::map<int, std::set<int>>& graph) {
    std::map<int, int> color; // 0 = unseen, 1 = visiting, 2 = done
    std::set<int> involved;
    std::vector<int> stack;

    std::function<void(int)> dfs = [&](int node) {
        color[node] = 1;
        stack.push_back(node);
        auto it = graph.find(node);
        if (it != graph.end()) {
            for (int next : it->second) {
                if (color[next] == 0) {
                    dfs(next);
                } else if (color[next] == 1) {
                    auto pos = std::find(stack.begin(), stack.end(), next);
                    if (pos != stack.end())
                        for (; pos != stack.end(); ++pos) involved.insert(*pos);
                }
            }
        }
        stack.pop_back();
        color[node] = 2;
    };

    for (const auto& entry : graph)
        if (color[entry.first] == 0) dfs(entry.first);

    return std::vector<int>(involved.begin(), involved.end());
}
