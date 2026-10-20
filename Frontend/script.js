const $ = (id) => document.getElementById(id);
let currentState = null;
let toastTimer = null;

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || `Request failed (${response.status})`);
  return data;
}

function showToast(message) {
  $("toast").textContent = message;
  $("toast").classList.remove("hidden");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => $("toast").classList.add("hidden"), 2800);
}

function statusBadge(state) {
  return `<span class="state ${state}">${state}</span>`;
}

function render(state) {
  currentState = state;
  $("clock").textContent = state.clock ?? 0;
  $("activeCount").textContent = state.active_count ?? 0;
  $("blockedCount").textContent = state.blocked_count ?? 0;
  $("completedCount").textContent = state.completed_count ?? 0;

  const running = (state.processes || []).find(p => p.state === "RUNNING");
  $("cpuProcess").textContent = running ? `PID ${running.pid}` : "Idle";
  $("cpuSub").textContent = running ? running.name : "Waiting for work";
  const queue = state.ready_queue || [];
  $("queueCount").textContent = queue.length;
  $("readyQueue").innerHTML = queue.length
    ? queue.map(pid => `<span class="queue-item">PID ${pid}</span>`).join("")
    : `<span class="muted">No processes queued</span>`;

  const processes = [...(state.processes || [])].reverse();
  $("processTable").innerHTML = processes.length ? processes.map(p => `
    <tr>
      <td>${p.pid}</td><td>${escapeHtml(p.name)}</td><td>${p.burst_time}</td>
      <td class="remaining-cell"><div class="remaining-label"><b>${p.remaining_time}</b><span>${p.progress ?? Math.round(100 * (p.burst_time - p.remaining_time) / Math.max(1,p.burst_time))}% complete</span></div><div class="process-time-bar"><span style="width:${Math.max(0,Math.min(100,p.progress ?? 0))}%"></span></div></td><td>${statusBadge(p.state)}</td>
    </tr>`).join("") : `<tr><td colspan="5" class="empty">No processes yet. Launch an action above.</td></tr>`;

  const resources = state.resources || {};
  $("resourceList").innerHTML = Object.entries(resources).map(([name, r]) => {
    const pct = r.capacity ? Math.round((r.available / r.capacity) * 100) : 0;
    return `<div class="resource"><div class="resource-top"><b>${escapeHtml(name.replace("_", " "))}</b><span>${r.available}/${r.capacity} available</span></div>
      <div class="bar"><span style="width:${pct}%"></span></div>
      <div class="muted" style="font-size:10px;margin-top:7px">Held by: ${(r.holders || []).length ? r.holders.map(x => `PID ${x}`).join(", ") : "nobody"}</div></div>`;
  }).join("");

  $("eventLog").innerHTML = (state.events || []).slice(0, 14).map(e => `
    <div class="event"><b>${escapeHtml(e.event_type || "EVENT")}${e.pid ? ` · PID ${e.pid}` : ""}</b>
    <small>${escapeHtml(e.description)} · T${e.time ?? ""}</small></div>`).join("") || `<span class="muted">Events will appear here.</span>`;

  const timeline = state.timeline || [];
  $("timeline").innerHTML = timeline.length ? timeline.slice(-24).map(t => `<span class="timeline-item ${t.pid ? "" : "idle"}">T${t.time}: ${t.pid ? `PID ${t.pid}` : "Idle"}</span>`).join("") : `<span class="muted">Advance the simulation to build a timeline.</span>`;

  const deadlock = state.deadlock || {};
  $("deadlockBanner").classList.toggle("hidden", !deadlock.detected);
  $("deadlockBanner").textContent = deadlock.detected ? `⚠ ${deadlock.message}` : "";
  renderDetails(state);
}

function renderDetails(state) {
  const processes = state.processes || [];
  $("processDetails").innerHTML = processes.length ? processes.slice().reverse().map(p =>
    `<div class="detail-item"><strong>PID ${p.pid} · ${escapeHtml(p.name)}</strong><span>State: ${p.state} · Arrival: ${p.arrival_time} · Burst: ${p.burst_time} · Remaining: ${p.remaining_time}</span><span>Holds: ${(p.holds || []).join(", ") || "none"} · Waiting for: ${p.waiting_for || "nothing"}</span></div>`
  ).join("") : `<div class="detail-item"><strong>No processes yet</strong><span>Launch an action to inspect its process details.</span></div>`;

  $("schedulingDetails").innerHTML = `
    <div class="detail-item"><strong>Scheduling algorithm</strong><span>First-Come, First-Served (FCFS)</span></div>
    <div class="detail-item"><strong>CPU process</strong><span>${state.cpu ? `PID ${state.cpu}` : "CPU is idle"}</span></div>
    <div class="detail-item"><strong>Ready queue order</strong><span>${(state.ready_queue || []).map(pid => `PID ${pid}`).join(" → ") || "Empty"}</span></div>
    <div class="detail-item"><strong>Context switches</strong><span>${state.context_switches ?? 0}</span></div>`;

  const deadlock = state.deadlock || {};
  $("deadlockDetails").innerHTML = `
    <div class="detail-item"><strong>${deadlock.detected ? "DEADLOCK DETECTED" : "No deadlock detected"}</strong><span>${escapeHtml(deadlock.message || "")}</span></div>
    <div class="detail-item"><strong>Involved processes</strong><span>${(deadlock.processes || []).map(pid => `PID ${pid}`).join(", ") || "None"}</span></div>`;
  const c = deadlock.conditions || {};
  const labels = [
    ["mutual_exclusion", "Mutual exclusion"],
    ["hold_and_wait", "Hold and wait"],
    ["no_preemption", "No preemption"],
    ["circular_wait", "Circular wait"]
  ];
  $("conditions").innerHTML = labels.map(([key, label]) =>
    `<div class="detail-item condition"><span class="${c[key] ? "check" : "cross"}">${c[key] ? "✓" : "○"}</span><div><strong>${label}</strong><span>${c[key] ? "Present in current demo" : "Not currently established"}</span></div></div>`
  ).join("");

  const sem = state.semaphore || {};
  $("syncDetails").innerHTML = `
    <div class="detail-item"><strong>Printer semaphore</strong><span>Initial count: ${sem.initial ?? 2}</span><span>Available permits: ${state.resources?.printer?.available ?? sem.value ?? 0}</span></div>
    <div class="detail-item"><strong>Processes holding printer</strong><span>${(state.resources?.printer?.holders || []).map(pid => `PID ${pid}`).join(", ") || "None"}</span></div>
    <div class="detail-item"><strong>Waiting processes</strong><span>${(sem.waiting || []).map(pid => `PID ${pid}`).join(", ") || "None recorded"}</span></div>
    <div class="detail-item"><strong>Operations</strong><span>wait() requests a permit; signal() releases it.</span></div>`;
}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, ch => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
  })[ch]);
}

async function refresh() {
  try {
    const [state, health] = await Promise.all([api("/api/state"), api("/api/health")]);
    render(state);
    $("apiStatus").textContent = `API online · DB ${health.database}`;
    $("apiStatus").style.color = health.database === "connected" ? "var(--green)" : "var(--yellow)";
  } catch (error) {
    $("apiStatus").textContent = "Backend unavailable";
    $("apiStatus").style.color = "var(--red)";
  }
}

let simulationRunning = false;
async function runMockSimulation() {
  if (simulationRunning) return;
  simulationRunning = true;
  const button = document.querySelector('[data-action="run_mock_simulation"]');
  if (button) { button.disabled = true; button.textContent = "⏸ Simulation running…"; }
  try {
    let state = await api("/api/actions", {method:"POST", body:JSON.stringify({action:"run_mock_simulation"})});
    render(state);
    showToast("Mock workload created. Watch each process's remaining time decrease.");
    let safety = 0;
    while (safety++ < 80) {
      const active = (state.processes || []).some(p => p.state !== "TERMINATED");
      if (!active || state.deadlock?.detected) break;
      await new Promise(resolve => setTimeout(resolve, 650));
      state = await api("/api/actions", {method:"POST", body:JSON.stringify({action:"tick"})});
      render(state);
    }
    showToast(state.deadlock?.detected ? "Simulation paused: deadlock detected. Use Recover deadlock." : "Mock simulation finished.");
  } catch (error) { showToast(error.message); }
  finally {
    simulationRunning = false;
    if (button) { button.disabled = false; button.textContent = "▶ Run mock simulation"; }
  }
}

document.querySelectorAll("[data-action]").forEach(button => {
  button.addEventListener("click", async () => {
    const action = button.dataset.action;
    if (action === "run_mock_simulation") { await runMockSimulation(); return; }
    if (simulationRunning && action !== "reset") { showToast("Wait for the current mock simulation to finish, or reset it."); return; }
    try {
      let state = await api("/api/actions", {
        method: "POST",
        body: JSON.stringify({ action })
      });
      if (state.error) throw new Error(state.error);
      if (state.ok === false && state.error) throw new Error(state.error);
      if (state.algorithm || state.demo === "counting_semaphore") {
        $("bankerResult").textContent = JSON.stringify(state, null, 2);
        showToast(state.message || `${state.algorithm || "Semaphore demo"} completed`);
        await refresh();
        return;
      }
      render(state);
      if (action === "reset") $("bankerResult").textContent = "";
      if (action === "recover_deadlock") {
        let recoveryTicks = 0;
        while (recoveryTicks++ < 40 && (state.processes || []).some(p => p.state !== "TERMINATED") && !state.deadlock?.detected) {
          await new Promise(resolve => setTimeout(resolve, 650));
          state = await api("/api/actions", {method:"POST", body:JSON.stringify({action:"tick"})});
          render(state);
          const unfinished = (state.processes || []).filter(p => p.state !== "TERMINATED");
          const runnable = unfinished.some(p => p.state === "READY" || p.state === "RUNNING");
          if (unfinished.length && !runnable && !state.deadlock?.detected) {
            showToast("Recovery completed, but no process is runnable. Check resource ownership in the event log.");
            break;
          }
        }
        if (!(state.processes || []).some(p => p.state !== "TERMINATED")) {
          showToast("Deadlock recovered. Remaining processes completed execution.");
        } else if (state.deadlock?.detected) {
          showToast("A deadlock is still detected. Review the deadlock panel.");
        } else if (recoveryTicks >= 40) {
          showToast("Recovery started, but the simulation reached its tick limit.");
        }
      } else {
        showToast(action === "reset" ? "New simulation session started." : "Simulation updated.");
      }
    } catch (error) {
      showToast(error.message);
    }
  });
});

$("detailsToggle").addEventListener("click", () => $("detailsPanel").classList.add("open"));
$("closeDetails").addEventListener("click", () => $("detailsPanel").classList.remove("open"));
document.querySelectorAll("[data-tab]").forEach(tab => {
  tab.addEventListener("click", () => {
    document.querySelectorAll("[data-tab]").forEach(x => x.classList.toggle("active", x === tab));
    document.querySelectorAll(".tab-content").forEach(x => x.classList.toggle("hidden", x.id !== tab.dataset.tab));
  });
});

async function loadFeatureGuide() {
  try {
    const features = await api("/api/features");
    function selectFeature(key) {
      const f = features[key]; if (!f) return;
      document.querySelectorAll("[data-feature]").forEach(b => b.classList.toggle("active", b.dataset.feature === key));
      $("featureWhat").textContent = f.what;
      $("featureHow").textContent = f.how;
      $("featureObserve").textContent = f.observe;
    }
    document.querySelectorAll("[data-feature]").forEach(b => b.addEventListener("click", () => selectFeature(b.dataset.feature)));
    selectFeature("process_management");
  } catch (_) { $("featureWhat").textContent = "Feature explanations are unavailable until the backend is running."; }
}

$("runBanker").addEventListener("click", async () => {
  try {
    const result = await api("/api/actions", {method:"POST", body:JSON.stringify({action:"banker_demo"})});
    const resultLabel = result.error ? "ERROR" : (result.process_ids?.length === 0 ? "NO ACTIVE PROCESSES" : (result.safe ? "SAFE STATE" : "UNSAFE STATE"));
    const sequenceLabel = result.safe ? "Safe sequence" : "Partial sequence";
    const sequence = result.safe ? (result.safe_sequence || []) : (result.partial_sequence || []);
    $("bankerResult").textContent = `${result.algorithm || "Banker’s algorithm"}\nResult: ${resultLabel}\n${sequenceLabel}: ${sequence.join(" → ") || "none"}\n${result.message || ""}`;
    showToast("Banker’s safety check completed.");
  } catch (error) { $("bankerResult").textContent = error.message; showToast(error.message); }
});

loadFeatureGuide();
refresh();
setInterval(refresh, 2500);
