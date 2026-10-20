#ifndef OSCORE_SCHEDULER_H
#define OSCORE_SCHEDULER_H

#include "process_manager.h"
#include <vector>

std::vector<int> fcfsOrder(const std::vector<Process>& processes);

#endif
