#ifndef OSCORE_DEADLOCK_H
#define OSCORE_DEADLOCK_H

#include <map>
#include <set>
#include <vector>

// A wait-for graph has an edge A -> B when A waits for a resource held by B.
std::vector<int> findDeadlockedProcesses(const std::map<int, std::set<int>>& graph);

#endif
