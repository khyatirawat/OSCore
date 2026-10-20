# OSCore — Inside the System

OSCore is an interactive operating-systems simulator with an HTML/CSS/JS dashboard, a Flask API, C++ algorithm demos, and MySQL persistence. It is an educational simulation, not a real operating-system process controller.

## Components
- **Process management:** PIDs, process states, burst/remaining time, ready queue and event history.
- **FCFS scheduling:** one simulated CPU tick per Advance action; oldest eligible ready process is dispatched first.
- **Synchronization:** counting semaphore behavior for a two-permit printer and a single-permit file lock; FIFO waiting and resource hand-off.
- **Deadlock:** a controlled circular-wait scenario, wait-for graph cycle detector, Coffman condition explanation and victim-based recovery.
- **Banker's algorithm:** C++ safe-state demo with the standard five-process example.
- **Database:** session records, process snapshots, current held/waiting allocations, event history, resource state and deadlock/recovery history.
- **Feature guide:** in the dashboard, select any concept to read what it is, how this simulator models it, and what to observe.

## Requirements
- Python 3.10+
- MySQL 8.x (or compatible)
- A C++17 compiler (g++/MinGW recommended)

## Setup (Windows PowerShell)
Run commands from the extracted `OSCore` project folder.

1. Create your local database config:
   ```powershell
   Copy-Item .env.example .env
   ```
   Edit `.env` and enter your MySQL username/password.
2. In MySQL Workbench, open and execute `database/schema.sql`. If you already created the older OSCore schema, the backend attempts a small idempotent compatibility migration on startup.
3. Install Python packages:
   ```powershell
   python -m pip install -r Backend/requirements.txt
   ```
4. Compile the C++ algorithm engine:
   ```powershell
   g++ -std=c++17 -O2 -Wall -Wextra engine/engine_main.cpp ProcessManagement/process_manager.cpp ProcessManagement/scheduler.cpp ProcessSynchronization/semaphore.cpp DeadlockManagement/deadlock.cpp BankersAlgorithm/banker.cpp -o engine/oscope_engine.exe
   ```
5. Start Flask:
   ```powershell
   python Backend/app.py
   ```
6. Open `http://127.0.0.1:5000` in your browser.

### macOS/Linux
Use `cp Backend/.env.example Backend/.env`, the same pip command, and compile with the same g++ command but output to `-o engine/oscope_engine` (no `.exe`). Start with `python3 Backend/app.py`.

## How to use
- Launch a desktop tile to create a process; press **Advance simulation** to execute one CPU tick at a time. Use **Run mock simulation** to create a sample workload and watch it advance automatically tick by tick.
- Launch several print tasks to see semaphore contention and blocked processes.
- Select **Demonstrate deadlock**, inspect the Deadlock tab, then select **Recover deadlock**.
- Select **Run Banker's safety demo** to run the C++ safety algorithm.
- Use **System details** and the **What is each feature doing?** guide for explanations.
- Reset creates a fresh session. Earlier sessions remain in the database.

## API
- `GET /api/health` — API, MySQL and compiled-engine status.
- `GET /api/state` — current simulation snapshot.
- `GET /api/features` — feature explanations for the guide.
- `GET /api/events?limit=100&session_id=...` — persisted event history.
- `GET /api/history/processes?session_id=...` — persisted process records.
- `POST /api/actions` — actions such as `open_website`, `print_document`, `copy_files`, `print_another`, `generate_tasks`, `tick`, `demonstrate_deadlock`, `recover_deadlock`, `banker_demo`, and `reset`.

## Database tables
`simulation_sessions`, `processes`, `resources`, `resource_allocations`, `process_events`, and `deadlock_events`.

## Notes / limitations
The dashboard simulation is authoritative in the Flask process; scheduling, resource hand-off and wait-for graph logic are implemented in the Flask simulation so the UI can update each tick. The backend selects a C++ executable for the current operating system and attempts to compile the engine from source when a C++17 compiler is available. If the Banker's demo cannot run through C++, it uses a Python safety-algorithm fallback so the feature does not fail merely because a platform-specific executable is missing. Restarting Flask starts a new in-memory session; saved history remains in MySQL, but a running simulation is not restored from a previous session. If MySQL is unavailable, the UI can still run in offline/demo mode, but data will not be persisted. This is intended for coursework and demonstrations.
