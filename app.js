/**
 * Frontend logic for MediBuddy Weather-Advisory Assistant
 */

document.addEventListener("DOMContentLoaded", () => {
  // Session State
  let sessionId = "session-" + Math.random().toString(36).substring(2, 8);
  const sessionIdLabel = document.getElementById("sessionIdLabel");
  if (sessionIdLabel) sessionIdLabel.textContent = sessionId;

  // DOM Elements
  const chatForm = document.getElementById("chatForm");
  const userInput = document.getElementById("userInput");
  const sendBtn = document.getElementById("sendBtn");
  const chatMessages = document.getElementById("chatMessages");
  const simulateFailToggle = document.getElementById("simulateFailToggle");
  const resetSessionBtn = document.getElementById("resetSessionBtn");

  // Drawer Elements
  const viewSopsBtn = document.getElementById("viewSopsBtn");
  const closeDrawerBtn = document.getElementById("closeDrawerBtn");
  const sopDrawer = document.getElementById("sopDrawer");
  const drawerOverlay = document.getElementById("drawerOverlay");
  const sopListContainer = document.getElementById("sopListContainer");
  const sopCountBadge = document.getElementById("sopCountBadge");
  const drawerRuleCount = document.getElementById("drawerRuleCount");
  const addSopForm = document.getElementById("addSopForm");

  // Tab switching
  const tabBtns = document.querySelectorAll(".tab-btn");
  tabBtns.forEach((btn) => {
    btn.addEventListener("click", () => {
      tabBtns.forEach((b) => b.classList.remove("active"));
      document.querySelectorAll(".tab-pane").forEach((p) => p.classList.remove("active"));
      btn.classList.add("active");
      const targetId = btn.getAttribute("data-tab");
      document.getElementById(targetId)?.classList.add("active");
    });
  });

  // Suggestion chips
  document.querySelectorAll(".chip").forEach((chip) => {
    chip.addEventListener("click", () => {
      const prompt = chip.getAttribute("data-prompt");
      if (prompt) {
        userInput.value = prompt;
        chatForm.dispatchEvent(new Event("submit", { cancelable: true }));
      }
    });
  });

  // Open & Close Drawer
  function openDrawer() {
    sopDrawer.classList.add("open");
    drawerOverlay.classList.add("open");
    loadSOPList();
  }

  function closeDrawer() {
    sopDrawer.classList.remove("open");
    drawerOverlay.classList.remove("open");
  }

  viewSopsBtn?.addEventListener("click", openDrawer);
  closeDrawerBtn?.addEventListener("click", closeDrawer);
  drawerOverlay?.addEventListener("click", closeDrawer);

  // Load SOPs from Backend
  async function loadSOPList() {
    try {
      const res = await fetch("/api/sops");
      if (!res.ok) throw new Error("Failed to load SOP rules");
      const data = await res.json();
      const count = data.count || data.rules.length;

      if (sopCountBadge) sopCountBadge.textContent = count;
      if (drawerRuleCount) drawerRuleCount.textContent = count;

      if (!data.rules || data.rules.length === 0) {
        sopListContainer.innerHTML = `<p class="loading-text">No rules configured.</p>`;
        return;
      }

      sopListContainer.innerHTML = data.rules
        .map((r) => {
          const sev = (r.severity || "advisory").toLowerCase();
          return `
          <div class="sop-item-card">
            <div class="sop-item-header">
              <span class="sop-item-id">${escapeHtml(r.id)}</span>
              <span class="pill-badge ${sev}">${escapeHtml(r.severity)}</span>
            </div>
            <div class="sop-item-name">${escapeHtml(r.name)}</div>
            <div style="font-size: 0.75rem; color: #64748b;">Category: ${escapeHtml(r.category)}</div>
            <div class="sop-item-guidance">${escapeHtml(r.guidance || "")}</div>
          </div>
        `;
        })
        .join("");
    } catch (err) {
      sopListContainer.innerHTML = `<p style="color: red;">Error: ${escapeHtml(err.message)}</p>`;
    }
  }

  // Handle Adding New SOP Live (Live Review Test Requirement)
  addSopForm?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const id = document.getElementById("newSopId").value.trim();
    const name = document.getElementById("newSopName").value.trim();
    const category = document.getElementById("newSopCategory").value;
    const severity = document.getElementById("newSopSeverity").value;
    const activitiesRaw = document.getElementById("newSopActivities").value;
    const field = document.getElementById("newCondField").value;
    const op = document.getElementById("newCondOp").value;
    const val = parseFloat(document.getElementById("newCondVal").value);
    const guidance = document.getElementById("newSopGuidance").value.trim();

    const target_activities = activitiesRaw
      .split(",")
      .map((a) => a.trim().toLowerCase())
      .filter((a) => a.length > 0);

    const payload = {
      id,
      name,
      category,
      severity,
      target_activities,
      condition_type: "numeric",
      conditions: {
        logic: "and",
        rules: [{ field, operator: op, value: val }],
      },
      guidance,
      action: "caution",
    };

    try {
      const res = await fetch("/api/sops", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const respData = await res.json();
      if (!res.ok) throw new Error(respData.detail || "Failed to add SOP");

      alert(`Success! Policy ${id} was added to sops.yaml and is now active.`);
      addSopForm.reset();
      // Switch back to list tab and reload
      document.querySelector('[data-tab="listTab"]')?.click();
      loadSOPList();
    } catch (err) {
      alert(`Could not add rule: ${err.message}`);
    }
  });

  // Handle Reset Session
  resetSessionBtn?.addEventListener("click", async () => {
    try {
      await fetch(`/api/reset?session_id=${encodeURIComponent(sessionId)}`, { method: "POST" });
      sessionId = "session-" + Math.random().toString(36).substring(2, 8);
      if (sessionIdLabel) sessionIdLabel.textContent = sessionId;

      chatMessages.innerHTML = `
        <div class="message-row assistant">
          <div class="avatar-icon">MB</div>
          <div class="message-card">
            <div class="card-header">
              <span class="card-title">Session Reset Complete</span>
              <span class="pill-badge info">Fresh Thread</span>
            </div>
            <div class="card-body">
              <p>Conversational memory has been cleared. You can now start a fresh query context!</p>
            </div>
          </div>
        </div>
      `;
    } catch (err) {
      console.error(err);
    }
  });

  // Handle Chat Submit
  chatForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const query = userInput.value.trim();
    if (!query) return;

    const simulateFail = simulateFailToggle.checked;

    // Append User Message
    appendUserMessage(query);
    userInput.value = "";
    userInput.disabled = true;
    sendBtn.disabled = true;

    // Append Typing Indicator
    const typingId = appendTypingIndicator();
    scrollToBottom();

    try {
      const resp = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          query,
          session_id: sessionId,
          simulate_api_failure: simulateFail,
        }),
      });

      removeMessage(typingId);

      if (!resp.ok) {
        const errData = await resp.json().catch(() => ({}));
        throw new Error(errData.detail || `Server error (HTTP ${resp.status})`);
      }

      const data = await resp.json();
      appendAssistantResponse(data);
    } catch (err) {
      removeMessage(typingId);
      appendErrorMessage(err.message);
    } finally {
      userInput.disabled = false;
      sendBtn.disabled = false;
      userInput.focus();
      scrollToBottom();
    }
  });

  function appendUserMessage(text) {
    const row = document.createElement("div");
    row.className = "message-row user";
    row.innerHTML = `
      <div class="avatar-icon">You</div>
      <div class="message-card">
        <p>${escapeHtml(text)}</p>
      </div>
    `;
    chatMessages.appendChild(row);
  }

  function appendTypingIndicator() {
    const id = "typing-" + Date.now();
    const row = document.createElement("div");
    row.id = id;
    row.className = "message-row assistant";
    row.innerHTML = `
      <div class="avatar-icon">MB</div>
      <div class="message-card" style="padding: 12px 18px;">
        <span style="font-size: 0.85rem; color: #64748b;">LangGraph evaluating weather telemetry and binding SOPs...</span>
      </div>
    `;
    chatMessages.appendChild(row);
    return id;
  }

  function removeMessage(id) {
    const el = document.getElementById(id);
    if (el) el.remove();
  }

  function appendAssistantResponse(data) {
    const row = document.createElement("div");
    row.className = "message-row assistant";

    const primary = data.primary_sop;
    const secondaries = data.secondary_sops || [];
    const weather = data.weather_telemetry;
    const locMeta = data.location_meta;
    const trace = data.traceability || {};

    let statusPill = `<span class="pill-badge none">No SOP Guidance</span>`;
    let sevClass = "none";

    if (primary) {
      const sev = (primary.severity || "advisory").toLowerCase();
      sevClass = sev;
      statusPill = `<span class="pill-badge ${sev}">${escapeHtml(primary.severity)}</span>`;
    } else if (data.error_type === "API_ERROR") {
      statusPill = `<span class="pill-badge critical">API Failure</span>`;
    } else if (data.error_type === "LOCATION_NOT_FOUND") {
      statusPill = `<span class="pill-badge warning">Location Unresolved</span>`;
    }

    const cityDisplay = locMeta?.name
      ? `${locMeta.name}${locMeta.country ? ", " + locMeta.country : ""}`
      : data.extracted_location || "Target Area";

    let primaryCardHtml = "";
    if (primary) {
      const guidance = primary.evaluated_guidance || primary.guidance || "";
      primaryCardHtml = `
        <div class="policy-citation-block ${sevClass}">
          <strong>Primary Policy Applied: [${escapeHtml(primary.id)}] ${escapeHtml(primary.name)}</strong>
          <p style="margin-top: 4px;">${escapeHtml(guidance)}</p>
        </div>
      `;
    }

    let secondaryHtml = "";
    if (secondaries.length > 0) {
      secondaryHtml = `
        <div style="margin: 8px 0; font-size: 0.84rem;">
          <strong style="color: #475569;">Co-Applicable Policies Triggered:</strong>
          <ul style="margin-left: 18px; margin-top: 4px;">
            ${secondaries
              .map(
                (s) => `
              <li><strong>[${escapeHtml(s.id)}] (${escapeHtml(s.severity)}) - ${escapeHtml(s.name)}</strong>:
                ${escapeHtml(s.evaluated_guidance || s.guidance || "")}
              </li>`
              )
              .join("")}
          </ul>
        </div>
      `;
    }

    let telemetryHtml = "";
    if (weather) {
      telemetryHtml = `
        <div class="telemetry-box">
          <div class="telemetry-header">
            <span>Verified Open-Meteo Telemetry</span>
            <span>Coord: ${weather.latitude?.toFixed(2)}°, ${weather.longitude?.toFixed(2)}°</span>
          </div>
          <div class="telemetry-grid">
            <div class="telemetry-tile">
              <span class="telemetry-label">Condition</span>
              <span class="telemetry-val">${escapeHtml(weather.weather_description || "N/A")}</span>
            </div>
            <div class="telemetry-tile">
              <span class="telemetry-label">Temperature</span>
              <span class="telemetry-val">${weather.temperature_2m}°C (feels ${weather.apparent_temperature}°C)</span>
            </div>
            <div class="telemetry-tile">
              <span class="telemetry-label">Wind / Gusts</span>
              <span class="telemetry-val">${weather.wind_speed_10m} / ${weather.wind_gusts_10m} km/h</span>
            </div>
            <div class="telemetry-tile">
              <span class="telemetry-label">Rain / Precip</span>
              <span class="telemetry-val">${weather.precipitation} mm</span>
            </div>
            <div class="telemetry-tile">
              <span class="telemetry-label">UV Index</span>
              <span class="telemetry-val">${weather.uv_index}</span>
            </div>
          </div>
        </div>
      `;
    }

    // Format raw response markdown-ish to paragraphs if no primary card
    let rawTextHtml = "";
    if (!primary) {
      rawTextHtml = `<div style="white-space: pre-line; font-size: 0.92rem;">${escapeHtml(data.response)}</div>`;
    }

    row.innerHTML = `
      <div class="avatar-icon">MB</div>
      <div class="message-card">
        <div class="card-header">
          <div>
            <span class="card-title">${escapeHtml(cityDisplay)}</span>
            <span style="font-size: 0.78rem; color: #64748b; margin-left: 8px;">Activity: ${escapeHtml(data.extracted_activity || "General")}</span>
          </div>
          ${statusPill}
        </div>
        <div class="card-body">
          ${primaryCardHtml}
          ${secondaryHtml}
          ${rawTextHtml}
          ${telemetryHtml}
        </div>
      </div>
    `;

    chatMessages.appendChild(row);
  }

  function appendErrorMessage(msg) {
    const row = document.createElement("div");
    row.className = "message-row assistant";
    row.innerHTML = `
      <div class="avatar-icon" style="background: #ef4444;">!</div>
      <div class="message-card" style="border-color: #fecaca; background: #fff5f5;">
        <div class="card-header">
          <span class="card-title" style="color: #b91c1c;">Request Error</span>
          <span class="pill-badge critical">System Failure</span>
        </div>
        <p style="color: #991b1b; font-size: 0.9rem;">${escapeHtml(msg)}</p>
      </div>
    `;
    chatMessages.appendChild(row);
  }

  function scrollToBottom() {
    chatMessages.scrollTop = chatMessages.scrollHeight;
  }

  function escapeHtml(str) {
    if (typeof str !== "string") return str ?? "";
    return str
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }

  // Initial load of SOP count
  loadSOPList();
});
