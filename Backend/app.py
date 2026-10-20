import json
import subprocess
import threading
import shutil
import sys
from pathlib import Path
from uuid import uuid4
from flask import Flask, jsonify, request, send_from_directory
from database import (database_is_available, fetch_events, persist_snapshot,
                      save_deadlock, save_event, create_session, ensure_schema_compatibility)

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "Frontend"
ENGINE_CANDIDATES = [ROOT / "engine" / "oscope_engine.exe", ROOT / "engine" / "oscope_engine"]
app = Flask(__name__, static_folder=None)
_lock = threading.RLock()

FEATURES = {
 "process_management": {"title":"Process management", "what":"A process is a running task with a PID, arrival time, CPU burst, remaining time, state and resource requests.", "how":"Launching a desktop tile creates a process and places it at the tail of the ready queue. A process moves through READY, RUNNING, BLOCKED and TERMINATED as the simulation advances.", "observe":"Watch the process table, state badge, remaining time and event log."},
 "scheduling": {"title":"FCFS CPU scheduling", "what":"First-Come, First-Served is a non-preemptive scheduling policy: ready processes are selected in arrival/queue order.", "how":"Each Advance tick dispatches the oldest eligible READY process if the CPU is idle, then executes one unit of its CPU burst. A process that cannot acquire a resource is blocked and the scheduler checks the next ready process.", "observe":"Inspect the CPU, ready queue, context-switch count and dispatch/completion events."},
 "synchronization": {"title":"Counting semaphore and resource locks", "what":"A counting semaphore represents a finite number of identical permits. The printer has two permits; the file lock has one.", "how":"A process requests its resource when it is dispatched. If a permit exists, it is acquired; otherwise the process blocks in FIFO order. When a holder finishes or is terminated, its permit is transferred to the first waiter before another process can claim it.", "observe":"Watch available permits, holders, waiting processes, and RESOURCE_ACQUIRED / PROCESS_BLOCKED / RESOURCE_RELEASED events."},
 "deadlock": {"title":"Deadlock detection and recovery", "what":"Deadlock is a set of processes permanently waiting on resources held by one another. The detector builds a wait-for graph and searches for a cycle.", "how":"The demo deliberately constructs a circular wait involving two processes and two resource types. Detection reports the involved PIDs and Coffman conditions. Recovery terminates a selected victim, releases its resources, wakes eligible waiters, and records the recovery.", "observe":"Open the Deadlock tab, check the four conditions, then use Recover deadlock and watch the resource state change."},
 "banker": {"title":"Banker's safety algorithm", "what":"Banker's algorithm tests whether a resource allocation is in a safe state, using each process's maximum claim, current allocation and available vector.", "how":"The C++ engine repeatedly finds a process whose remaining need can be met, simulates its completion and returns its resources. If all processes can finish, it returns a safe sequence; otherwise the state is unsafe.", "observe":"Use Run Banker demo to see the algorithm's safe/unsafe result and sequence."},
 "database": {"title":"MySQL persistence", "what":"MySQL stores session metadata, process snapshots, current resource allocations, event history and deadlock/recovery records.", "how":"After each state-changing action, OSCore upserts process state, stores the current allocation/waiting set and appends events. Each reset creates a new session so previous session history is retained.", "observe":"Check the DB indicator, then inspect the processes, resource_allocations, process_events and deadlock_events tables in MySQL Workbench."}
}

def initial_state(session_id=None):
    sid = session_id or str(uuid4())
    return {"session_id":sid,"next_pid":1001,"clock":0,"processes":[],"events":[],
      "resources":{"printer":{"capacity":2,"available":2,"holders":[]},"file_lock":{"capacity":1,"available":1,"holders":[]}},
      "deadlock":{"detected":False,"processes":[],"message":"No deadlock detected.","conditions":{}},
      "cpu":None,"ready_queue":[],"context_switches":0,
      "semaphore":{"name":"printer","initial":2,"value":2,"waiting":[]},"timeline":[]}

_state = initial_state()
if database_is_available(): ensure_schema_compatibility()
create_session(_state["session_id"])

def _engine_path():
    preferred = ROOT / "engine" / ("oscope_engine.exe" if sys.platform == "win32" else "oscope_engine")
    if preferred.exists():
        return preferred

    compiler = shutil.which("g++") or shutil.which("clang++")
    if not compiler:
        return None
    output = preferred
    sources = [ROOT / "engine" / "engine_main.cpp", ROOT / "ProcessManagement" / "process_manager.cpp",
               ROOT / "ProcessManagement" / "scheduler.cpp", ROOT / "ProcessSynchronization" / "semaphore.cpp",
               ROOT / "DeadlockManagement" / "deadlock.cpp", ROOT / "BankersAlgorithm" / "banker.cpp"]
    try:
        built = subprocess.run([compiler, "-std=c++17", "-O2", *map(str, sources), "-o", str(output)],
                              capture_output=True, text=True, timeout=45, cwd=str(ROOT))
        if built.returncode == 0 and output.exists():
            return output
        print("C++ engine build failed:", built.stderr.strip())
    except (OSError, subprocess.TimeoutExpired) as exc:
        print("C++ engine build unavailable:", exc)
    return None

def _check_banker(available, allocation, maximum):
    """Validated Banker's safety check used for both the demo and user-supplied matrices."""
    if not isinstance(available, list) or not available:
        raise ValueError("available must be a non-empty list of resource counts")
    if not isinstance(allocation, list) or not allocation:
        raise ValueError("allocation must be a non-empty matrix")
    if not isinstance(maximum, list) or len(maximum) != len(allocation):
        raise ValueError("maximum must have the same number of process rows as allocation")
    width = len(available)
    vectors = [available] + allocation + maximum
    if any(not isinstance(row, list) or len(row) != width for row in vectors):
        raise ValueError("Every allocation and maximum row must match the available vector width")
    if any(type(value) is not int or value < 0 for row in vectors for value in row):
        raise ValueError("Resource counts must be non-negative integers")
    for i, row in enumerate(allocation):
        if any(maximum[i][j] < row[j] for j in range(width)):
            raise ValueError(f"Maximum claim for P{i} cannot be less than its current allocation")
    work = available[:]
    finished = [False] * len(allocation)
    sequence = []
    need = [[maximum[i][j] - allocation[i][j] for j in range(width)] for i in range(len(allocation))]
    while True:
        chosen = next((i for i in range(len(allocation)) if not finished[i]
                       and all(need[i][j] <= work[j] for j in range(width))), None)
        if chosen is None:
            break
        work = [work[j] + allocation[chosen][j] for j in range(width)]
        finished[chosen] = True
        sequence.append(f"P{chosen}")
    safe = all(finished)
    unfinished = [f"P{i}" for i, done in enumerate(finished) if not done]
    return {"ok": True, "algorithm": "Banker's Algorithm", "safe": safe,
            "safe_sequence": sequence if safe else [], "partial_sequence": sequence,
            "unfinished_processes": unfinished,
            "need_matrix": need,
            "message": ("System is in a SAFE state." if safe else
                        "System is in an UNSAFE state; no safe sequence includes every process.")}


def _banker_for_live_state():

    names = ["printer", "file_lock"]
    active = [p for p in _state["processes"] if p["state"] != "TERMINATED"]
    if not active:
        return {
            "ok": True,
            "algorithm": "Banker's Algorithm",
            "safe": True,
            "safe_sequence": [],
            "partial_sequence": [],
            "unfinished_processes": [],
            "need_matrix": [],
            "source": "live_simulation",
            "process_ids": [],
            "resource_names": names,
            "message": "No active processes to analyse. Reset or launch a workload first."
        }
    available = [int(_state["resources"][n]["available"]) for n in names]
    allocation, maximum = [], []
    for proc in active:
        alloc = [1 if proc["pid"] in _state["resources"][n]["holders"] else 0 for n in names]
        claim = alloc[:]
        requested = proc.get("waiting_for")
        configured = proc.get("resource")
        for resource_name in (requested, configured):
            if resource_name in names:
                claim[names.index(resource_name)] = 1
        allocation.append(alloc)
        maximum.append(claim)
    result = _check_banker(available, allocation, maximum)
    result["source"] = "live_simulation"
    result["process_ids"] = [p["pid"] for p in active]
    result["resource_names"] = names
    return result

def _python_banker_fallback(payload=None):
    payload = payload or {}
    try:
        return _check_banker(payload.get("available", [3, 3, 2]),
                             payload.get("allocation", [[0,1,0],[2,0,0],[3,0,2],[2,1,1],[0,0,2]]),
                             payload.get("maximum", [[7,5,3],[3,2,2],[9,0,2],[2,2,2],[4,3,3]])), 200
    except (TypeError, ValueError) as exc:
        return {"ok": False, "error": str(exc)}, 400

def run_cpp_engine(payload):
    binary = _engine_path()
    if not binary:
        if payload.get("action") in ("banker_demo", "banker"):
            return _python_banker_fallback(payload)
        return {"ok":False,"error":"C++ engine unavailable: install a C++17 compiler (g++/MinGW) or rebuild the engine for this operating system."},503
    try:
        result = subprocess.run([str(binary)],input=json.dumps(payload),text=True,capture_output=True,timeout=8,cwd=str(ROOT))
        if result.returncode:
            if payload.get("action") in ("banker_demo", "banker"):
                return _python_banker_fallback(payload)
            return {"ok":False,"error":result.stderr.strip() or "C++ engine failed."},500
        data = json.loads(result.stdout)
        return data, (200 if data.get("ok",True) else 400)
    except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError) as exc:
        if payload.get("action") in ("banker_demo", "banker"):
            return _python_banker_fallback(payload)
        return {"ok":False,"error":str(exc)},500

def add_event(event_type, description, pid=None):
    event={"event_type":event_type,"description":description,"pid":pid,"time":_state["clock"]}
    _state["events"].insert(0,event); _state["events"]=_state["events"][:200]
    save_event(event_type,description,pid,_state["session_id"],_state["clock"])

def _find(pid): return next((p for p in _state["processes"] if p["pid"]==pid),None)

def _new_process(name, burst, resource=None):
    pid=_state["next_pid"]; _state["next_pid"]+=1
    p={"pid":pid,"name":name,"arrival_time":_state["clock"],"burst_time":burst,"remaining_time":burst,
       "state":"READY","resource":resource,"holds":[],"waiting_for":None,"progress":0}
    _state["processes"].append(p); _state["ready_queue"].append(pid)
    add_event("PROCESS_CREATED",f"{name} created (PID {pid}) and appended to the ready queue.",pid)
    return p

def _sync_semaphore():
    r=_state["resources"]["printer"]
    _state["semaphore"].update(value=r["available"],waiting=[p["pid"] for p in _state["processes"] if p["state"]=="BLOCKED" and p.get("waiting_for")=="printer"])

def _release_resource(p, resource_name):
    r=_state["resources"].get(resource_name)
    if not r: return
    if p["pid"] in r["holders"]:
        r["holders"].remove(p["pid"]); r["available"]=min(r["capacity"],r["available"]+1)
        if resource_name in p["holds"]: p["holds"].remove(resource_name)
        add_event("RESOURCE_RELEASED",f"PID {p['pid']} released {resource_name}.",p["pid"])
    waiter=next((q for q in _state["processes"] if q["state"]=="BLOCKED" and q.get("waiting_for")==resource_name),None)
    if waiter and r["available"]>0:
        r["available"]-=1; r["holders"].append(waiter["pid"]); waiter["holds"].append(resource_name)
        waiter["waiting_for"]=None; waiter["state"]="READY"
        if waiter["pid"] not in _state["ready_queue"]: _state["ready_queue"].append(waiter["pid"])
        add_event("RESOURCE_ACQUIRED",f"Permit handed to waiting PID {waiter['pid']} for {resource_name}.",waiter["pid"])
    _sync_semaphore()

def _acquire_for_dispatch(p):
    name=p.get("resource")
    if not name or name in p["holds"]: return True
    r=_state["resources"][name]
    if r["available"]>0:
        r["available"]-=1; r["holders"].append(p["pid"]); p["holds"].append(name)
        add_event("RESOURCE_ACQUIRED",f"PID {p['pid']} acquired {name} on dispatch.",p["pid"]); _sync_semaphore(); return True
    p["state"]="BLOCKED"; p["waiting_for"]=name
    add_event("PROCESS_BLOCKED",f"PID {p['pid']} blocked: all {name} permits are in use.",p["pid"]); _sync_semaphore(); return False

def _detect_deadlock():
    graph={}
    for p in _state["processes"]:
        if p["state"]=="BLOCKED" and p.get("waiting_for"):
            holders=_state["resources"][p["waiting_for"]]["holders"]
            graph[p["pid"]]=[h for h in holders if h!=p["pid"]]
    visited=set(); active=[]; cycles=[]
    def dfs(node):
        if node in active:
            cycle=active[active.index(node):]
            if cycle and cycle not in cycles: cycles.append(cycle[:])
            return
        if node in visited: return
        active.append(node)
        for nxt in graph.get(node,[]): dfs(nxt)
        active.pop(); visited.add(node)
    for node in graph: dfs(node)
    return cycles[0] if cycles else []

def _schedule_tick():
    _state["clock"]+=1
    for waiter in _state["processes"]:
        if waiter["state"] != "BLOCKED" or not waiter.get("waiting_for"):
            continue
        resource_name = waiter["waiting_for"]
        resource = _state["resources"].get(resource_name)
        if resource and resource["available"] > 0:
            resource["available"] -= 1
            if waiter["pid"] not in resource["holders"]:
                resource["holders"].append(waiter["pid"])
            if resource_name not in waiter["holds"]:
                waiter["holds"].append(resource_name)
            waiter["waiting_for"] = None
            waiter["state"] = "READY"
            if waiter["pid"] not in _state["ready_queue"]:
                _state["ready_queue"].append(waiter["pid"])
            add_event("RESOURCE_ACQUIRED", f"PID {waiter['pid']} resumed and acquired {resource_name}.", waiter["pid"])
    queued = []
    for pid in _state["ready_queue"]:
        candidate = _find(pid)
        if candidate and candidate["state"] == "READY" and pid not in queued:
            queued.append(pid)
    for candidate in _state["processes"]:
        if candidate["state"] == "READY" and candidate["pid"] not in queued:
            queued.append(candidate["pid"])
    _state["ready_queue"] = queued
    _sync_semaphore()
    running=_find(_state["cpu"]) if _state["cpu"] else None
    if running and running["state"]!="RUNNING": running=None
    if running is None:
        _state["cpu"]=None
        while _state["ready_queue"]:
            pid=_state["ready_queue"].pop(0); candidate=_find(pid)
            if not candidate or candidate["state"]!="READY": continue
            if not _acquire_for_dispatch(candidate): continue
            candidate["state"]="RUNNING"; running=candidate; _state["cpu"]=pid
            add_event("CPU_DISPATCH",f"FCFS dispatched {candidate['name']} to the CPU.",pid); break
    if running:
        running["remaining_time"]=max(0,running["remaining_time"]-1)
        running["progress"]=round(100*(running["burst_time"]-running["remaining_time"])/running["burst_time"])
        _state["timeline"].append({"time":_state["clock"],"pid":running["pid"],"name":running["name"]})
        _state["timeline"]=_state["timeline"][-100:]
        if running["remaining_time"]==0:
            running["state"]="TERMINATED"
            for resource_name in list(running["holds"]): _release_resource(running,resource_name)
            add_event("PROCESS_TERMINATED",f"{running['name']} completed its CPU burst.",running["pid"])
            _state["cpu"]=None; _state["context_switches"]+=1
    else:
        _state["timeline"].append({"time":_state["clock"],"pid":None,"name":"Idle"})
        _state["timeline"]=_state["timeline"][-100:]
    cycle=_detect_deadlock()
    if cycle:
        _state["deadlock"]={"detected":True,"processes":cycle,"message":"Wait-for graph contains a cycle: "+" → ".join(map(str,cycle+[cycle[0]])),"conditions":{"mutual_exclusion":True,"hold_and_wait":True,"no_preemption":True,"circular_wait":True}}

def _snapshot():
    active=[p for p in _state["processes"] if p["state"]!="TERMINATED"]
    return {**_state,"processes":[dict(p) for p in _state["processes"]],"events":list(_state["events"]),
      "active_count":len(active),"blocked_count":sum(p["state"]=="BLOCKED" for p in active),
      "completed_count":sum(p["state"]=="TERMINATED" for p in _state["processes"]),
      "ready_queue":[pid for pid in _state["ready_queue"] if (p:=_find(pid)) and p["state"]=="READY"]}

def _persist():
    _sync_semaphore(); persist_snapshot(_state)

@app.get("/")
def index(): return send_from_directory(FRONTEND,"index.html")
@app.get("/<path:path>")
def frontend_files(path):
    candidate=FRONTEND/path
    if candidate.is_file(): return send_from_directory(FRONTEND,path)
    return jsonify({"error":"Not found"}),404
@app.get("/api/health")
def health():
    return jsonify({"api":"ok","database":"connected" if database_is_available() else "unavailable","engine":"compiled" if _engine_path() else "not compiled","session_id":_state["session_id"]})
@app.get("/api/state")
def state():
    with _lock: return jsonify(_snapshot())
@app.get("/api/features")
def features(): return jsonify(FEATURES)
@app.get("/api/events")
def events():
    session=request.args.get("session_id") or _state["session_id"]
    return jsonify(fetch_events(limit=min(500,max(1,request.args.get("limit",100,type=int))),session_id=session))
@app.get("/api/history/processes")
def process_history():
    from database import fetch_session_processes
    sid=request.args.get("session_id") or _state["session_id"]
    return jsonify(fetch_session_processes(sid))

@app.post("/api/actions")
def actions():
    global _state
    body=request.get_json(silent=True) or {}; action=body.get("action","")
    with _lock:
        if action=="reset":
            old_sid=_state["session_id"]; _state=initial_state(); create_session(_state["session_id"])
            add_event("SIMULATION_RESET",f"New simulation session created; previous session {old_sid} remains in database.")
        elif action in ("open_website","print_document","copy_files","print_another"):
            choices={"open_website":("Open Website",3,None),"print_document":("Print Document",4,"printer"),"copy_files":("Copy Files",3,"file_lock"),"print_another":("Print Another Document",5,"printer")}
            name,burst,res=choices[action]; _new_process(name,burst,res); _schedule_tick()
        elif action in ("generate_tasks", "run_mock_simulation"):
            for name,burst,res in [("Open Website",3,None),("Print Document",4,"printer"),("Copy Files",3,"file_lock"),("Print Another Document",5,"printer")]:
                _new_process(name,burst,res)
        elif action=="tick": _schedule_tick()
        elif action=="demonstrate_deadlock":
            _state["processes"]=[p for p in _state["processes"] if p["state"]=="TERMINATED"]
            _state["ready_queue"]=[]; _state["cpu"]=None
            _state["resources"]={"printer":{"capacity":1,"available":0,"holders":[]},"file_lock":{"capacity":1,"available":0,"holders":[]}}
            p1=_new_process("Deadlock Process P1",4,"printer"); p2=_new_process("Deadlock Process P2",4,"file_lock")
            p1["state"]="BLOCKED"; p1["holds"]=["file_lock"]; p1["waiting_for"]="printer"
            p2["state"]="BLOCKED"; p2["holds"]=["printer"]; p2["waiting_for"]="file_lock"
            _state["resources"]["file_lock"]["holders"]=[p1["pid"]]; _state["resources"]["printer"]["holders"]=[p2["pid"]]
            _state["ready_queue"]=[]
            cycle = _detect_deadlock()
            _state["deadlock"]={"detected":bool(cycle),"processes":cycle,"message":(f"Wait-for graph cycle detected: {' → '.join(map(str,cycle + cycle[:1]))}." if cycle else "No cycle found in wait-for graph."),"conditions":{"mutual_exclusion":True,"hold_and_wait":True,"no_preemption":True,"circular_wait":bool(cycle)}}
            _sync_semaphore(); add_event("DEADLOCK_DETECTED",_state["deadlock"]["message"]); save_deadlock(_state["session_id"],True,[p1["pid"],p2["pid"]])
        elif action=="recover_deadlock":
            if not _state["deadlock"].get("detected"):
                return jsonify({"error":"No deadlock to recover from."}),400

            victims=list(_state["deadlock"].get("processes",[]))
            victim=victims[-1] if victims else None
            victim_process=_find(victim) if victim is not None else None

            _state["cpu"]=None
            if victim_process:
                victim_process["state"]="TERMINATED"
                victim_process["remaining_time"]=0
                victim_process["progress"]=100
                victim_process["waiting_for"]=None
                for rname in list(victim_process["holds"]):
                    _release_resource(victim_process,rname)
                add_event("DEADLOCK_RECOVERY",f"Recovery terminated victim PID {victim} and released held resources.",victim)

            for q in _state["processes"]:
                if q["state"] == "TERMINATED":
                    continue
                q["waiting_for"] = None
                if q["state"] == "BLOCKED":
                    q["state"] = "READY"
                    add_event("PROCESS_UNBLOCKED", f"PID {q['pid']} unblocked by deadlock recovery.", q["pid"])

            for resource_name, rr in _state["resources"].items():
                rr["holders"] = [q["pid"] for q in _state["processes"]
                                  if q["state"] != "TERMINATED" and resource_name in q.get("holds", [])]
                rr["holders"] = list(dict.fromkeys(rr["holders"]))

            ready=[]
            for pid in _state["ready_queue"]:
                q=_find(pid)
                if q and q["state"]=="READY" and pid not in ready:
                    ready.append(pid)
            for q in _state["processes"]:
                if q["state"]=="READY" and q["pid"] not in ready:
                    ready.append(q["pid"])
            _state["ready_queue"] = ready

            printer = _state["resources"]["printer"]
            printer["capacity"] = 2
            printer["available"] = max(0, printer["capacity"] - len(printer["holders"]))
            file_lock = _state["resources"]["file_lock"]
            file_lock["capacity"] = 1
            file_lock["available"] = max(0, file_lock["capacity"] - len(file_lock["holders"]))
            for q in _state["processes"]:
                if q["state"] == "BLOCKED":
                    q["state"] = "READY"
                if q["state"] != "TERMINATED":
                    q["waiting_for"] = None
                    if q["state"] == "READY" and q["pid"] not in _state["ready_queue"]:
                        _state["ready_queue"].append(q["pid"])
            _state["deadlock"]={"detected":False,"processes":[],"message":f"Deadlock resolved by terminating victim PID {victim}; runnable processes have been restored to the ready queue.","conditions":{}}
            _sync_semaphore()
            save_deadlock(_state["session_id"],False,victims,f"Terminated PID {victim}")
            add_event("SCHEDULER_RESUMED","Scheduler resumed after deadlock recovery.")
            _schedule_tick()
        elif action=="banker_demo":
            try:
                result = _banker_for_live_state()
                status = 200
            except (TypeError, ValueError) as exc:
                result, status = {"ok": False, "error": str(exc)}, 400
            if status==200:
                add_event("BANKER_DEMO",f"Banker's algorithm checked live simulation state: {result.get('message','completed')}.")
            _persist(); return jsonify(result),status
        elif action=="run_banker":
            payload={"action":"banker", "available":body.get("available",[3,3,2]),
                     "allocation":body.get("allocation",[[0,1,0],[2,0,0],[3,0,2],[2,1,1],[0,0,2]]),
                     "maximum":body.get("maximum",[[7,5,3],[3,2,2],[9,0,2],[2,2,2],[4,3,3]])}
            result,status=_python_banker_fallback(payload)
            add_event("BANKER_ANALYSIS",f"Banker's safety analysis: {result.get('message', result.get('error','failed'))}")
            _persist(); return jsonify(result),status
        else: return jsonify({"error":f"Unknown action: {action}"}),400
        _persist()
        return jsonify(_snapshot())

if __name__=="__main__": app.run(host="127.0.0.1",port=5000,debug=False)
