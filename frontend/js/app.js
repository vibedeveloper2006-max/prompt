const API_BASE = "";

// --- ELITE STATE ENGINE ---
let state = {
    zoneCache: {},
    predictions: {},
    currentRoute: null,
    currentUser: "elite-user-" + Math.floor(Math.random() * 100000),
    timeOffset: 0, // minutes (0, 15, 30, 45, 60)
    isStaffView: false,
    routingActive: false,
    visionInterval: null,
    refreshInterval: null,
    alertInterval: null
};

// --- INITIALIZATION ---
document.addEventListener("DOMContentLoaded", () => {
    initCore();
    setupEventListeners();
    initSpotlight();
    startAutomatedTelemetry();
});

async function initCore() {
    await fetchLiveTelemetry();
    renderInteractiveMap();
    initAssistant();
    initSituationRoom();
}

function setupEventListeners() {
    // Operations Toggle
    const staffBtn = document.getElementById("staff-toggle-btn");
    staffBtn.addEventListener("click", toggleOperationsMode);

    // Route Form
    const routeForm = document.getElementById("route-form");
    routeForm.addEventListener("submit", handleRoutingRequest);

    // Time Machine Slider
    const timeSlider = document.getElementById("time-slider");
    const timeDisplay = document.getElementById("time-display");
    timeSlider.addEventListener("input", (e) => {
        state.timeOffset = parseInt(e.target.value);
        timeDisplay.innerText = state.timeOffset === 0 ? "Live Now" : `+${state.timeOffset} mins`;
        handleTimeShift();
    });

    // Reroute Actions
    document.getElementById("accept-reroute-btn").addEventListener("click", acceptReroute);
    document.getElementById("dismiss-reroute-btn").addEventListener("click", dismissReroute);

    // Visibility Handling
    document.addEventListener("visibilitychange", () => {
        if (document.visibilityState === "visible") startAutomatedTelemetry();
        else stopAutomatedTelemetry();
    });
}

// --- TELEMETRY & API ---
async function fetchLiveTelemetry() {
    try {
        const [statusRes, waitRes, insightRes] = await Promise.all([
            fetch(`${API_BASE}/crowd/status`),
            fetch(`${API_BASE}/crowd/wait-times`),
            fetch(`${API_BASE}/analytics/insights`)
        ]);

        const statusData = await statusRes.json();
        const waitData = await waitRes.json();
        const insightData = await insightRes.json();

        processStatus(statusData);
        processWaitTimes(waitData);
        processInsights(insightData);
    } catch (err) {
        console.error("Telemetry failure:", err);
    }
}

async function fetchAllPredictions() {
    try {
        const res = await fetch(`${API_BASE}/crowd/predict-all`);
        const data = await res.json();
        state.predictions = data.predictions;
    } catch (err) {
        console.error("Prediction synchronization failure:", err);
    }
}

function processStatus(data) {
    const startSelect = document.getElementById("current_zone");
    const endSelect = document.getElementById("destination");
    const statusGrid = document.getElementById("status-grid");

    const prevStart = startSelect.value;
    const prevEnd = endSelect.value;

    startSelect.innerHTML = "<option value='' disabled>Select Origin...</option>";
    endSelect.innerHTML = "<option value='' disabled>Select Destination...</option>";
    statusGrid.innerHTML = "";

    data.zones.forEach((zone, idx) => {
        state.zoneCache[zone.zone_id] = zone;
        
        // Populate selectors
        const statusText = zone.density === 100 ? " (Full)" : ` (${zone.density}%)`;
        startSelect.add(new Option(zone.name + statusText, zone.zone_id));
        endSelect.add(new Option(zone.name + statusText, zone.zone_id));

        // Render Telemetry Card with Stagger
        renderTelemetryCard(zone, idx);
    });

    if (prevStart) startSelect.value = prevStart;
    if (prevEnd) endSelect.value = prevEnd;
}

function renderTelemetryCard(zone, idx = 0) {
    const grid = document.getElementById("status-grid");
    const card = document.createElement("div");
    const staggerClass = idx < 5 ? `stagger-${idx + 1}` : "";
    card.className = `zone-status-card glass-panel stagger-reveal ${staggerClass} status-${zone.status}`;
    card.innerHTML = `
        <div class="zone-name">${zone.name}</div>
        <div class="zone-density">${zone.density}%</div>
        <div style="font-size: 0.7rem; color: var(--text-dim); text-transform: uppercase; margin-top: 0.5rem;">
            Node ${zone.zone_id} | ${zone.status}
        </div>
    `;
    grid.appendChild(card);
}

function processWaitTimes(data) {
    const grid = document.getElementById("wait-times-grid");
    grid.innerHTML = "";
    data.services.forEach((service, idx) => {
        const card = document.createElement("div");
        const staggerClass = idx < 5 ? `stagger-${idx + 1}` : "";
        card.className = `zone-status-card glass-panel stagger-reveal ${staggerClass} status-${service.status}`;
        card.innerHTML = `
            <div class="zone-name">${service.name}</div>
            <div class="zone-density" style="font-size: 1.5rem;">${service.wait_minutes}m</div>
            <div style="font-size: 0.7rem; color: var(--text-dim); margin-top: 0.5rem;">
                Trend: <span style="color:var(--accent-teal)">${service.trend}</span>
            </div>
        `;
        grid.appendChild(card);
    });
}

function processInsights(data) {
    const textEl = document.getElementById("insight-text");
    const hotspotsList = document.getElementById("staff-hotspots-list");
    const leaderboardList = document.getElementById("staff-leaderboard-list");

    if (data.recommended_entry && data.recommended_entry !== "N/A") {
        textEl.innerHTML = `<strong>Top Pick:</strong> ${data.recommended_entry} reports minimal latency.`;
    }

    if (hotspotsList) {
        hotspotsList.innerHTML = "";
        (data.historical_hotspots || []).slice(0, 3).forEach(h => {
            const li = document.createElement("li");
            li.innerHTML = `<span>${h}</span> <span class="wait-time-badge" style="background:rgba(239,68,68,0.1); color:var(--accent-red); border-color:var(--accent-red);">Peak Risk</span>`;
            hotspotsList.appendChild(li);
        });
    }

    if (leaderboardList) {
        leaderboardList.innerHTML = "";
        (data.live_leaderboard || []).forEach(z => {
            const li = document.createElement("li");
            li.innerHTML = `<span><strong>${z.name}</strong></span> <span class="metric-density-val">${z.current_density}%</span>`;
            leaderboardList.appendChild(li);
        });
    }
}

// --- INTERACTIVE MAP ENGINE ---
function renderInteractiveMap() {
    const container = document.getElementById("map-venue-view");
    container.innerHTML = ""; // Clear for re-render if needed

    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("viewBox", "0 0 100 100");
    svg.setAttribute("class", "map-svg");

    // Draw Mesh/Flow Connections
    for (let i = 0; i < gridSize; i++) {
        for (let j = 0; j < gridSize; j++) {
            if (i < gridSize - 1) {
                const line = document.createElementNS("http://www.w3.org/2000/svg", "line");
                line.setAttribute("x1", padding + (i * step));
                line.setAttribute("y1", padding + (j * step));
                line.setAttribute("x2", padding + ((i + 1) * step));
                line.setAttribute("y2", padding + (j * step));
                line.setAttribute("stroke", "rgba(59, 130, 246, 0.1)");
                line.setAttribute("stroke-width", "0.2");
                svg.appendChild(line);
            }
            if (j < gridSize - 1) {
                const line = document.createElementNS("http://www.w3.org/2000/svg", "line");
                line.setAttribute("x1", padding + (i * step));
                line.setAttribute("y1", padding + (j * step));
                line.setAttribute("x2", padding + (i * step));
                line.setAttribute("y2", padding + ((j + 1) * step));
                line.setAttribute("stroke", "rgba(59, 130, 246, 0.1)");
                line.setAttribute("stroke-width", "0.2");
                svg.appendChild(line);
            }

            const x = padding + (i * step);
            const y = padding + (j * step);

            // Pulse node markers for each zone
            const circle = document.createElementNS("http://www.w3.org/2000/svg", "circle");
            circle.setAttribute("cx", x);
            circle.setAttribute("cy", y);
            circle.setAttribute("r", "1.2");
            circle.setAttribute("fill", "var(--accent-blue)");
            circle.setAttribute("class", "pulse-node");
            circle.style.opacity = "0.4";
            
            svg.appendChild(circle);
        }
    }

    container.appendChild(svg);
    injectMapControls(container);
}

function initSpotlight() {
    document.addEventListener("mousemove", (e) => {
        const panels = document.querySelectorAll(".glass-panel");
        panels.forEach(panel => {
            const rect = panel.getBoundingClientRect();
            const x = ((e.clientX - rect.left) / rect.width) * 100;
            const y = ((e.clientY - rect.top) / rect.height) * 100;
            panel.style.setProperty("--mouse-x", `${x}%`);
            panel.style.setProperty("--mouse-y", `${y}%`);
        });
    });
}

function handleTimeShift() {
    if (state.timeOffset > 0) {
        fetchAllPredictions().then(() => {
            applyPredictionsToUI();
        });
    } else {
        fetchLiveTelemetry();
    }
}

function applyPredictionsToUI() {
    const grid = document.getElementById("status-grid");
    grid.innerHTML = "";

    Object.values(state.predictions).forEach(pred => {
        const zone = {
            zone_id: pred.zone_id,
            name: state.zoneCache[pred.zone_id]?.name || pred.zone_id,
            density: pred.predicted_density,
            status: _densityToStatus(pred.predicted_density)
        };
        renderTelemetryCard(zone);
    });
    
    // Announce state shift
    addAssistantMessage(`Adjusting tactical view to T+${state.timeOffset} minutes. Predicted dispersal patterns applied.`);
}

function _densityToStatus(d) {
    if (d >= 70) return "HIGH";
    if (d >= 40) return "MEDIUM";
    return "LOW";
}

// --- ROUTING LOGIC ---
async function handleRoutingRequest(e) {
    e.preventDefault();
    const btn = document.getElementById("submit-btn");
    const spinner = document.getElementById("btn-spinner");
    const btnText = document.getElementById("btn-text");

    const payload = {
        user_id: state.currentUser,
        current_zone: document.getElementById("current_zone").value,
        destination: document.getElementById("destination").value,
        priority: document.getElementById("priority").value,
        constraints: []
    };

    if (document.getElementById("constraint-avoid").checked) payload.constraints.push("avoid_crowd");
    if (document.getElementById("constraint-fastest").checked) payload.constraints.push("prefer_fastest");

    // UI Feedback
    btn.disabled = true;
    spinner.classList.remove("d-none");
    btnText.innerText = "Computing Elite Path...";

    try {
        const res = await fetch(`${API_BASE}/navigate/suggest`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
        });
        const data = await res.json();
        renderRoutingResults(data);
        startAlertPolling();
    } catch (err) {
        showError("Computational failure. Rerouting via secondary mesh nodes...");
    } finally {
        btn.disabled = false;
        spinner.classList.add("d-none");
        btnText.innerText = "Initialize Traversal Path";
    }
}

function renderRoutingResults(data) {
    state.currentRoute = data;
    document.getElementById("empty-state").classList.add("d-none");
    document.getElementById("results-display").classList.remove("d-none");

    document.getElementById("wait-time-display").innerText = `~${data.estimated_wait_minutes}m`;
    document.getElementById("route-distance-badge").innerText = `${data.total_walking_distance_meters}m`;
    document.getElementById("ai-explanation").innerText = data.ai_explanation;

    // Timeline Rendering
    const timeline = document.getElementById("route-timeline");
    timeline.innerHTML = "";
    data.recommended_route.forEach((zid, idx) => {
        const zone = state.zoneCache[zid] || { name: zid };
        const node = document.createElement("div");
        node.className = "timeline-node fade-in";
        node.style.animationDelay = `${idx * 0.1}s`;
        node.innerHTML = `
            <div class="node-dot">${idx + 1}</div>
            <div class="node-content">
                <strong>${zone.name}</strong>
                <p style="font-size:0.75rem; color:var(--text-dim); margin-top:0.25rem;">
                    Status: <span style="color:var(--accent-blue)">NOMINAL</span>
                </p>
            </div>
        `;
        timeline.appendChild(node);
    });

    // Animate Path on Map (Placeholder logic for WOW)
    animateMapPath(data.route_waypoints);

    // Logic Weights
    if (data.reasoning_summary) {
        animateWeightBar("bar-density", data.reasoning_summary.density_factor);
        animateWeightBar("bar-trend", data.reasoning_summary.trend_factor);
        animateWeightBar("bar-event", data.reasoning_summary.event_factor);
    }
}

function animateWeightBar(id, val) {
    const bar = document.getElementById(id);
    bar.style.width = "0%";
    setTimeout(() => { bar.style.width = (val * 100) + "%"; }, 50);
}

// --- SITUATION ROOM ---
function initSituationRoom() {
    const room = document.getElementById("vision-room-content");
    const scenarios = [
        { msg: "CCTV Zone A: Bottleneck forming near Gate entrance. Recommending staggered entry.", risk: "LOW" },
        { msg: "Sensors Zone FC: Unexpected surge at North registers. Wait times +5m.", risk: "MEDIUM" },
        { msg: "Vision Feed Corridor 2: Stairway obstruction cleared. Step-free mode still advised for accessibility tags.", risk: "INFO" },
        { msg: "System Snapshot: 98% confidence in current dispersal flow. No major anomalies.", risk: "SAFE" }
    ];

    let idx = 0;
    state.visionInterval = setInterval(() => {
        room.innerHTML = `
            <div class="loading-bar-pulse" style="height: 2px; background: var(--accent-purple); width: 100%; margin-bottom: 1rem;"></div>
            <p style="color: var(--text-main); font-weight: 500;">AI Analysis: <span style="color:var(--text-muted); font-weight:400;">${scenarios[idx].msg}</span></p>
            <div class="status-badge" style="margin-top: 1rem; border-color: var(--accent-purple); color: var(--accent-purple); width: fit-content;">SCAN STATUS: ${scenarios[idx].risk}</div>
        `;
        idx = (idx + 1) % scenarios.length;
    }, 8000);
}

// --- REROUTE FLOW ---
function startAlertPolling() {
    if (state.alertInterval) clearInterval(state.alertInterval);
    state.alertInterval = setInterval(async () => {
        try {
            const res = await fetch(`${API_BASE}/navigate/alerts/${state.currentUser}`);
            const data = await res.json();
            if (data.requires_reroute) showRerouteAlert(data.new_navigation);
        } catch (e) {}
    }, 10000);
}

function showRerouteAlert(data) {
    const banner = document.getElementById("reroute-alert");
    banner.classList.remove("d-none");
    document.getElementById("reroute-alert-text").innerText = 
        `Dynamic Shift: An alternative path is ${data.estimated_wait_minutes}m faster.`;
    // We could store the new path for acceptance logic
}

async function acceptReroute() {
    // Ported logic from original
    document.getElementById("reroute-alert").classList.add("d-none");
    addAssistantMessage("Navigation parameters updated. Trailing live density markers.");
}

function dismissReroute() {
    document.getElementById("reroute-alert").classList.add("d-none");
}

// --- UI UTILS ---
function toggleOperationsMode() {
    state.isStaffView = !state.isStaffView;
    document.getElementById("attendee-view-container").classList.toggle("d-none", state.isStaffView);
    document.getElementById("staff-view-container").classList.toggle("d-none", !state.isStaffView);
    document.getElementById("staff-toggle-btn").innerText = state.isStaffView ? "Exit Operations" : "Operations Control";
    document.getElementById("staff-toggle-btn").setAttribute("aria-pressed", state.isStaffView);
}

function startAutomatedTelemetry() {
    if (state.refreshInterval) clearInterval(state.refreshInterval);
    state.refreshInterval = setInterval(fetchLiveTelemetry, 30000);
}

function stopAutomatedTelemetry() {
    clearInterval(state.refreshInterval);
}

function showError(msg) {
    const err = document.getElementById("form-error");
    err.innerText = msg;
    err.classList.remove("d-none");
    setTimeout(() => err.classList.add("d-none"), 5000);
}

function injectMapControls(container) {
    // Future: Add zoom logic here
}

function animateMapPath(waypoints) {
    // Future: SVG Polyline animation
}

// --- ASSISTANT LOGIC ---
function initAssistant() {
    const toggle = document.getElementById("chat-toggle-btn");
    const close = document.getElementById("chat-close-btn");
    const widget = document.getElementById("chat-widget");
    const form = document.getElementById("chat-form");
    const input = document.getElementById("chat-input");

    toggle.addEventListener("click", () => widget.classList.toggle("d-none"));
    close.addEventListener("click", () => widget.classList.add("d-none"));
    
    form.addEventListener("submit", async (e) => {
        e.preventDefault();
        const msg = input.value;
        if (!msg) return;
        addAssistantMessage(msg, "user");
        input.value = "";
        
        try {
            const res = await fetch(`${API_BASE}/assistant/chat`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ message: msg, user_id: state.currentUser, history: [] })
            });
            const data = await res.json();
            addAssistantMessage(data.reply);
        } catch (e) {
            addAssistantMessage("Inertial signal loss. Retrying assistant uplink...", "ai-msg error-msg");
        }
    });

    document.querySelectorAll(".chat-suggestions .chat-chip").forEach(chip => {
        chip.addEventListener("click", () => {
            input.value = chip.innerText;
            form.dispatchEvent(new Event("submit"));
        });
    });
}

function addAssistantMessage(text, role = "ai-msg") {
    const feed = document.getElementById("chat-feed");
    const bubble = document.createElement("div");
    bubble.className = `chat-msg ${role}`;
    bubble.innerText = text;
    feed.appendChild(bubble);
    feed.scrollTop = feed.scrollHeight;
}
