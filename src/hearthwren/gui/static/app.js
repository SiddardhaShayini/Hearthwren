/**
 * Hearthwren Desktop UI — Client Logic
 * Clean, lightweight, dependency-free vanilla JavaScript.
 */

document.addEventListener("DOMContentLoaded", () => {
  // Navigation tabs
  const navItems = document.querySelectorAll(".nav-item");
  const viewPanels = document.querySelectorAll(".view-panel");

  navItems.forEach((item) => {
    item.addEventListener("click", () => {
      const targetId = item.getAttribute("data-view");
      navItems.forEach((n) => n.classList.remove("active"));
      viewPanels.forEach((p) => p.classList.remove("active"));
      item.classList.add("active");
      const targetPanel = document.getElementById(targetId);
      if (targetPanel) targetPanel.classList.add("active");

      // Load specific data on view switch
      if (targetId === "view-diff") loadDiff();
      if (targetId === "view-memory") loadMemory();
      if (targetId === "view-doctor") loadDoctor();
    });
  });

  // Modal controls
  const repoModal = document.getElementById("repo-modal");
  const btnOpenRepoModal = document.getElementById("btn-open-repo-modal");
  const btnCloseRepoModal = document.getElementById("btn-close-repo-modal");
  const btnCancelRepo = document.getElementById("btn-cancel-repo");
  const btnApplyRepo = document.getElementById("btn-apply-repo");
  const modalRepoInput = document.getElementById("modal-repo-input");

  let currentBrowseParent = null;

  async function loadBrowseDirectory(targetDir) {
    const drivesContainer = document.getElementById("browse-drives-container");
    const subdirsContainer = document.getElementById("browse-subdirs-container");
    if (!subdirsContainer) return;

    subdirsContainer.innerHTML = '<span style="font-size: 12px; color: var(--text-dim);">Loading directories...</span>';

    try {
      const url = targetDir ? `/api/browse?dir=${encodeURIComponent(targetDir)}` : "/api/browse";
      const res = await fetch(url);
      if (!res.ok) return;
      const data = await res.json();

      modalRepoInput.value = data.current;
      currentBrowseParent = data.parent;

      // Update parent button state
      const btnParent = document.getElementById("btn-browse-parent");
      if (btnParent) {
        btnParent.disabled = !data.parent;
      }

      // Render Drives
      if (drivesContainer && data.drives && data.drives.length > 0) {
        drivesContainer.innerHTML = "";
        data.drives.forEach(drive => {
          const btn = document.createElement("button");
          btn.className = "drive-chip";
          btn.textContent = `💾 ${drive}`;
          btn.addEventListener("click", () => loadBrowseDirectory(drive));
          drivesContainer.appendChild(btn);
        });
      }

      // Render Subdirectories
      subdirsContainer.innerHTML = "";
      if (data.subdirectories && data.subdirectories.length > 0) {
        data.subdirectories.forEach(sub => {
          const chip = document.createElement("div");
          chip.className = "folder-chip";
          chip.innerHTML = `<span>📁</span> <span>${sub}</span>`;
          chip.addEventListener("click", () => {
            const sep = data.current.endsWith("\\") || data.current.endsWith("/") ? "" : "\\";
            const nextPath = `${data.current}${sep}${sub}`;
            loadBrowseDirectory(nextPath);
          });
          subdirsContainer.appendChild(chip);
        });
      } else {
        subdirsContainer.innerHTML = '<span style="font-size: 12px; color: var(--text-dim); padding: 4px 0;">(No subdirectories found)</span>';
      }
    } catch (err) {
      subdirsContainer.innerHTML = `<span style="font-size: 12px; color: var(--danger);">Error loading directory: ${err.message}</span>`;
    }
  }

  function openModal() {
    repoModal.classList.add("open");
    modalRepoInput.focus();
    loadBrowseDirectory(modalRepoInput.value.trim());
  }

  function closeModal() {
    repoModal.classList.remove("open");
  }

  btnOpenRepoModal.addEventListener("click", openModal);
  btnCloseRepoModal.addEventListener("click", closeModal);
  btnCancelRepo.addEventListener("click", closeModal);

  // Up to parent button
  const btnBrowseParent = document.getElementById("btn-browse-parent");
  if (btnBrowseParent) {
    btnBrowseParent.addEventListener("click", () => {
      if (currentBrowseParent) {
        loadBrowseDirectory(currentBrowseParent);
      }
    });
  }

  // Native Browse Dialog Button
  const btnNativeBrowse = document.getElementById("btn-native-browse");
  if (btnNativeBrowse) {
    btnNativeBrowse.addEventListener("click", async () => {
      btnNativeBrowse.textContent = "⏳ Browsing...";
      btnNativeBrowse.disabled = true;
      try {
        const res = await fetch("/api/browse-dialog", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ current: modalRepoInput.value.trim() }),
        });
        const data = await res.json();
        if (data.success && data.path) {
          modalRepoInput.value = data.path;
          loadBrowseDirectory(data.path);
        }
      } catch (err) {
        console.warn("Browse dialog error:", err);
      } finally {
        btnNativeBrowse.textContent = "📂 Browse...";
        btnNativeBrowse.disabled = false;
      }
    });
  }

  btnApplyRepo.addEventListener("click", async () => {
    const newPath = modalRepoInput.value.trim();
    if (!newPath) return;
    try {
      const res = await fetch("/api/set-repo", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ path: newPath }),
      });
      const data = await res.json();
      if (data.success) {
        closeModal();
        pollStatus();
        alert(`Switched workspace repository to:\n${data.workspace}`);
      } else {
        alert(`Error: ${data.error}`);
      }
    } catch (err) {
      alert(`Failed to set repository: ${err.message}`);
    }
  });

  // Real-time Status Polling
  async function pollStatus() {
    try {
      const res = await fetch("/api/status");
      if (!res.ok) return;
      const data = await res.json();

      // Update Header
      document.getElementById("header-repo-name").textContent = data.workspace_name || "Repository";
      modalRepoInput.value = data.workspace;

      const gitText = data.git.is_repo ? `${data.git.branch} (${data.git.clean ? 'Clean' : 'Modified'})` : 'No Git';
      document.getElementById("git-branch-text").textContent = gitText;

      const availGb = data.resources.available_ram_gb;
      const totalGb = data.resources.total_system_ram_gb;
      document.getElementById("ram-free-text").textContent = `${availGb.toFixed(1)} GB free`;

      const usedPct = Math.max(5, Math.min(100, ((totalGb - availGb) / totalGb) * 100));
      const fillBar = document.getElementById("ram-meter-bar");
      fillBar.style.width = `${usedPct}%`;

      if (availGb < 1.5) {
        fillBar.style.backgroundColor = "var(--danger)";
      } else if (availGb < 3.0) {
        fillBar.style.backgroundColor = "var(--warning)";
      } else {
        fillBar.style.backgroundColor = "var(--success-text)";
      }
    } catch (err) {
      console.warn("Status poll error:", err);
    }
  }

  // Poll status on load and periodically
  pollStatus();
  setInterval(pollStatus, 4000);

  // Agent Output Helper
  const agentLog = document.getElementById("agent-output-log");
  function appendAgentLog(msg, title = "") {
    const timestamp = new Date().toLocaleTimeString();
    let entry = `[${timestamp}] `;
    if (title) entry += `=== ${title} ===\n`;
    entry += `${msg}\n\n`;
    agentLog.textContent = entry + agentLog.textContent;
  }

  document.getElementById("btn-clear-log").addEventListener("click", () => {
    agentLog.textContent = "";
  });

  // 1. Run Task
  document.getElementById("btn-run-task").addEventListener("click", async () => {
    const input = document.getElementById("task-input");
    const task = input.value.trim();
    if (!task) return;

    appendAgentLog(`Initiating task: "${task}"...`, "Run Task");
    try {
      const res = await fetch("/api/run", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ task, multi_phase: false }),
      });
      const data = await res.json();
      if (data.success) {
        let details = `Plan:\n${data.plan}\n\nActions Taken:\n${(data.actions_taken || []).map(a => '  + ' + a).join('\n')}`;
        if (data.file_created) {
          details += `\n\n📄 File Created: ${data.file_created}`;
        }
        if (data.recovery_proposal) {
          details += `\n\nRecovery Guidance:\n${data.recovery_proposal}`;
        }
        appendAgentLog(details, "Task Complete");
        pollStatus();
      } else {
        appendAgentLog(`Error: ${data.error || 'Task aborted'}`, "Task Failed");
      }
    } catch (err) {
      appendAgentLog(`Request error: ${err.message}`, "Error");
    }
  });

  // 2. Run 5-Phase Pipeline
  document.getElementById("btn-run-multiphase").addEventListener("click", async () => {
    const input = document.getElementById("task-input");
    const task = input.value.trim();
    if (!task) return;

    appendAgentLog(`Starting 5-Phase Pipeline for: "${task}"...\n(Understand -> Test Spec -> Implement -> Review -> Report)`, "5-Phase Pipeline");
    try {
      const res = await fetch("/api/run", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ task, multi_phase: true }),
      });
      const data = await res.json();
      if (data.success) {
        let text = "";
        data.phases.forEach(p => {
          text += `[Phase ${p.phase}]: ${p.success ? 'PASS' : 'FAIL'}\n${p.summary}\n\n`;
        });
        appendAgentLog(text, "5-Phase Pipeline Succeeded");
        pollStatus();
      } else {
        appendAgentLog(`Pipeline error: ${data.final_report}`, "Pipeline Failed");
      }
    } catch (err) {
      appendAgentLog(`Error: ${err.message}`, "Pipeline Error");
    }
  });

  // 3. Guidance Query
  document.getElementById("btn-guide-query").addEventListener("click", async () => {
    const input = document.getElementById("task-input");
    const query = input.value.trim();
    if (!query) return;

    appendAgentLog(`Querying guidance for: "${query}"...`, "Guidance");
    try {
      const res = await fetch("/api/guide", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query }),
      });
      const data = await res.json();
      appendAgentLog(data.guidance || "No guidance returned.", "Guidance Report");
    } catch (err) {
      appendAgentLog(`Error: ${err.message}`, "Guidance Error");
    }
  });

  // 4. Plan Mode
  const planLog = document.getElementById("plan-output-log");
  document.getElementById("btn-create-plan").addEventListener("click", async () => {
    const input = document.getElementById("plan-input");
    const task = input.value.trim();
    if (!task) return;

    planLog.textContent = `Analyzing architecture and generating ordered plan for: "${task}"...`;
    try {
      const res = await fetch("/api/plan", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ task }),
      });
      const data = await res.json();
      planLog.textContent = data.plan || data.error || "No plan generated.";
    } catch (err) {
      planLog.textContent = `Error: ${err.message}`;
    }
  });

  // 5. Code & Symbol Search
  async function performSearch(symbolsOnly = false) {
    const query = document.getElementById("search-input").value.trim();
    const container = document.getElementById("search-results-container");
    if (!query) return;

    container.innerHTML = `<div style="padding: 10px; color: var(--text-dim);">Searching index for '${query}'...</div>`;
    try {
      const res = await fetch(`/api/search?q=${encodeURIComponent(query)}&symbol=${symbolsOnly ? 1 : 0}`);
      const data = await res.json();

      let html = "";
      if (data.symbols && data.symbols.length > 0) {
        html += `<div style="font-weight: 600; font-size: 13px; color: var(--accent); margin: 8px 0;">Matching Symbols (${data.symbols.length}):</div>`;
        data.symbols.forEach(s => {
          html += `
            <div style="background-color: var(--code-bg); padding: 8px 12px; border-radius: 6px; margin-bottom: 6px; border: 1px solid var(--border-subtle); font-family: var(--font-mono); font-size: 12px;">
              <span class="badge badge-pass" style="margin-right: 6px;">${s.kind}</span>
              <strong style="color: var(--success-text);">${s.name}</strong>
              <span style="color: var(--text-dim); margin-left: 8px;">${s.path}:${s.line}</span>
            </div>`;
        });
      }

      if (data.matches && data.matches.length > 0) {
        html += `<div style="font-weight: 600; font-size: 13px; color: var(--accent); margin: 12px 0 8px 0;">Full-Text Content Matches (${data.matches.length}):</div>`;
        data.matches.forEach(m => {
          const highlighted = m.snippet.replace(/<b>/g, '<span style="color: #f2cc60; font-weight: bold;">').replace(/<\/b>/g, '</span>');
          html += `
            <div style="background-color: var(--code-bg); padding: 10px; border-radius: 6px; margin-bottom: 8px; border: 1px solid var(--border-subtle); font-size: 12px;">
              <div style="color: var(--accent); font-weight: 600; font-family: var(--font-mono); margin-bottom: 4px;">${m.path}</div>
              <div style="font-family: var(--font-mono); color: var(--text-secondary); white-space: pre-wrap;">${highlighted}</div>
            </div>`;
        });
      }

      if (!html) {
        html = `<div style="padding: 12px; color: var(--text-dim);">No symbols or text matches found for '${query}'.</div>`;
      }
      container.innerHTML = html;
    } catch (err) {
      container.innerHTML = `<div style="color: var(--danger-text); padding: 10px;">Search error: ${err.message}</div>`;
    }
  }

  document.getElementById("btn-search-all").addEventListener("click", () => performSearch(false));
  document.getElementById("btn-search-symbols").addEventListener("click", () => performSearch(true));

  document.getElementById("btn-reindex").addEventListener("click", async () => {
    const container = document.getElementById("search-results-container");
    container.innerHTML = `<div style="padding: 10px; color: var(--text-dim);">Rebuilding SQLite FTS index...</div>`;
    try {
      const res = await fetch("/api/index", { method: "POST" });
      const data = await res.json();
      container.innerHTML = `<div style="color: var(--success-text); padding: 10px;">Successfully indexed ${data.indexed_files} source files into index.db.</div>`;
    } catch (err) {
      container.innerHTML = `<div style="color: var(--danger-text); padding: 10px;">Reindex failed: ${err.message}</div>`;
    }
  });

  // 6. Diff & Git
  async function loadDiff() {
    const viewer = document.getElementById("diff-output-viewer");
    viewer.textContent = "Loading git diff...";
    try {
      const res = await fetch("/api/diff");
      const data = await res.json();
      if (!data.is_repo) {
        viewer.textContent = "Current workspace is not a Git repository.";
        return;
      }
      const fullDiff = (data.staged ? `=== STAGED CHANGES ===\n${data.staged}\n\n` : '') +
                       (data.unstaged ? `=== UNSTAGED CHANGES ===\n${data.unstaged}` : '');
      viewer.textContent = fullDiff.trim() || "No changes detected in working tree (clean).";
    } catch (err) {
      viewer.textContent = `Failed to load diff: ${err.message}`;
    }
  }

  document.getElementById("btn-refresh-diff").addEventListener("click", loadDiff);

  document.getElementById("btn-commit-diff").addEventListener("click", async () => {
    const msg = document.getElementById("commit-msg-input").value.trim();
    if (!msg) {
      alert("Please enter a commit message.");
      return;
    }
    if (!confirm(`Are you sure you want to stage and commit with message:\n"${msg}"?`)) return;

    try {
      const res = await fetch("/api/commit", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: msg }),
      });
      const data = await res.json();
      if (data.success) {
        alert("Commit created successfully!");
        document.getElementById("commit-msg-input").value = "";
        loadDiff();
        pollStatus();
      } else {
        alert(`Commit failed: ${data.stderr || data.error}`);
      }
    } catch (err) {
      alert(`Error committing: ${err.message}`);
    }
  });

  document.getElementById("btn-push-diff").addEventListener("click", async () => {
    if (!confirm("Are you sure you want to push commits to the remote repository?")) return;
    try {
      const res = await fetch("/api/push", { method: "POST" });
      const data = await res.json();
      if (data.success) {
        alert("Pushed successfully to remote repository!");
        loadDiff();
        pollStatus();
      } else {
        alert(`Push failed: ${data.stderr || data.error}`);
      }
    } catch (err) {
      alert(`Push error: ${err.message}`);
    }
  });

  // 7. Memory View
  async function loadMemory() {
    const container = document.getElementById("memory-sections-container");
    container.innerHTML = "<div style='color: var(--text-dim);'>Reading AGENT_MEMORY.md...</div>";
    try {
      const res = await fetch("/api/memory");
      const data = await res.json();
      if (!data.exists) {
        container.innerHTML = "<div style='color: var(--warning);'>AGENT_MEMORY.md is missing. Run 'hwren init' to create it.</div>";
        return;
      }
      let html = "";
      if (data.stale && data.stale.length > 0) {
        html += `<div style="background-color: rgba(210, 153, 34, 0.15); border: 1px solid var(--warning); padding: 10px; border-radius: 6px; margin-bottom: 14px;">
                   <strong style="color: var(--warning);">Stale File References Detected:</strong>
                   <ul style="margin-left: 20px; font-size: 12px; margin-top: 6px; color: var(--text-primary);">
                     ${data.stale.map(s => `<li>${s}</li>`).join('')}
                   </ul>
                 </div>`;
      }
      Object.entries(data.sections).forEach(([title, content]) => {
        html += `
          <div style="background-color: var(--bg-card-hover); padding: 12px; border-radius: 6px; margin-bottom: 10px; border: 1px solid var(--border-subtle);">
            <div style="font-weight: 600; color: var(--accent); margin-bottom: 6px;">## ${title}</div>
            <div style="font-size: 12px; color: var(--text-secondary); white-space: pre-wrap; font-family: var(--font-mono); max-height: 150px; overflow-y: auto;">${content}</div>
          </div>`;
      });
      container.innerHTML = html;
    } catch (err) {
      container.innerHTML = `<div style="color: var(--danger-text);">Error loading memory: ${err.message}</div>`;
    }
  }

  document.getElementById("btn-refresh-memory").addEventListener("click", loadMemory);

  // 8. Doctor View
  async function loadDoctor() {
    const tbody = document.getElementById("doctor-table-body");
    tbody.innerHTML = "<tr><td colspan='3' style='text-align: center; color: var(--text-dim);'>Running diagnostic checks...</td></tr>";
    try {
      const res = await fetch("/api/doctor");
      const data = await res.json();
      let html = "";
      data.checks.forEach(c => {
        const badgeClass = c.status === "PASS" ? "badge-pass" : (c.status === "WARN" ? "badge-warn" : "badge-fail");
        html += `
          <tr>
            <td><strong>${c.name}</strong></td>
            <td><span class="badge ${badgeClass}">[${c.status}]</span></td>
            <td style="color: var(--text-secondary);">${c.value}</td>
          </tr>`;
      });
      tbody.innerHTML = html;
    } catch (err) {
      tbody.innerHTML = `<tr><td colspan='3' style='color: var(--danger-text);'>Failed to run doctor: ${err.message}</td></tr>`;
    }
  }

  document.getElementById("btn-refresh-doctor").addEventListener("click", loadDoctor);
});
