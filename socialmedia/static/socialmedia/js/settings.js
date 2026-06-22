(function () {
  const configEl = document.getElementById("socialmedia-config");
  if (!configEl) return;
  const config = JSON.parse(configEl.textContent);

  const PREVIEW_URL = config.previewUrl;
  const EXPORT_URL  = config.exportUrl;
  const CSRF_TOKEN  = config.csrfToken;
  const TRANS_CLICK_TO_EDIT = config.transClickToEdit || "Click to edit · Ctrl+Enter to save";
  const TRANS_SELECT_AT_LEAST_ONE = config.transSelectAtLeastOne || "Please select at least one post to export.";

  let allPosts = [];   // full data from server
  let activeFilter = "all";

  // ---- Load posts from server ----
  function loadPosts() {
    const btn = document.getElementById("btn-regenerate");
    if (!btn) return;
    btn.disabled = true;
    btn.innerHTML = '<i class="fa fa-refresh"></i> Loading…';
    showSkeleton();

    fetch(PREVIEW_URL, { headers: { "X-Requested-With": "XMLHttpRequest" } })
      .then(r => r.json())
      .then(data => {
        allPosts = (data.posts || []).map(p => ({ ...p, enabled: true }));
        renderTable(allPosts, activeFilter);
        updateCounts();
      })
      .catch(err => {
        const tbody = document.getElementById("posts-tbody");
        if (tbody) {
          tbody.innerHTML =
            `<tr><td colspan="5"><div class="sm-empty"><i class="fa fa-exclamation-triangle"></i>
            Failed to load posts. ${err.message}</div></td></tr>`;
        }
      })
      .finally(() => {
        btn.disabled = false;
        btn.innerHTML = '<i class="fa fa-refresh"></i> Regenerate';
      });
  }

  // ---- Render table rows ----
  function renderTable(posts, filter) {
    const tbody = document.getElementById("posts-tbody");
    if (!tbody) return;
    const visible = filter === "all" ? posts : posts.filter(p => p.type === filter);

    if (!visible.length) {
      tbody.innerHTML = `<tr><td colspan="5"><div class="sm-empty">
        <i class="fa fa-share-alt"></i>
        <div>No posts found for this filter.</div>
        <small>Check that your event has the relevant data (CFP deadline, sessions, tickets).</small>
      </div></td></tr>`;
      updateSelectedCount();
      return;
    }

    tbody.innerHTML = visible.map((p, i) => {
      const idx = allPosts.indexOf(p);
      return `
      <tr data-idx="${idx}" data-type="${p.type}" class="${p.enabled ? "" : "row-disabled"}">
        <td>
          <input type="checkbox" class="row-chk" data-idx="${idx}"
            ${p.enabled ? "checked" : ""}>
        </td>
        <td><span class="type-badge type-${p.type}">${escHtml(p.type_label)}</span></td>
        <td class="dt-cell">
          <div class="dt-date">${escHtml(p.post_date)}</div>
          <div class="dt-time">${escHtml(p.post_time)}</div>
        </td>
        <td class="dt-cell">
          <input type="time" class="form-control input-sm sm-time-input" value="${escHtml(p.post_time)}">
        </td>
        <td class="post-text-cell">
          <span class="post-text-view" data-idx="${idx}">${escHtml(p.post_text)}</span>
          <textarea class="post-text-edit" data-idx="${idx}">${escHtml(p.post_text)}</textarea>
          <span class="edit-hint">${escHtml(TRANS_CLICK_TO_EDIT)}</span>
        </td>
      </tr>`;
    }).join("");

    updateSelectedCount();
  }

  function syncTimeDisplay(idx, val) {
    const view = document.querySelector(`.post-text-view[data-idx="${idx}"]`);
    if (view) {
      const row = view.closest("tr");
      const dtDate = row.querySelector(".dt-date");
      if (dtDate) {
        row.querySelector(".dt-time").textContent = val;
      }
    }
  }

  // ---- Inline editing ----
  function startEdit(idx, span) {
    const ta = span.nextElementSibling;
    span.classList.add("editing");
    ta.classList.add("editing");
    ta.style.display = "block";
    ta.focus();
    ta.setSelectionRange(ta.value.length, ta.value.length);
  }

  // Focusout / blur
  function finishEdit(idx, ta) {
    allPosts[idx].post_text = ta.value;
    const span = ta.previousElementSibling;
    span.textContent = ta.value;
    span.classList.remove("editing");
    ta.classList.remove("editing");
    ta.style.display = "none";
  }

  // ---- Toggle row ----
  function toggleRow(idx, enabled) {
    allPosts[idx].enabled = enabled;
    const row = document.querySelector(`tr[data-idx="${idx}"]`);
    if (row) row.classList.toggle("row-disabled", !enabled);
    updateSelectedCount();
  }

  // ---- Select all / none ----
  function selectAll(val) {
    allPosts.forEach((p, i) => { p.enabled = val; });
    document.querySelectorAll(".row-chk").forEach(chk => {
      const idx = parseInt(chk.dataset.idx);
      chk.checked = val;
      const row = chk.closest("tr");
      if (row) row.classList.toggle("row-disabled", !val);
    });
    const chkAll = document.getElementById("chk-all");
    if (chkAll) {
      chkAll.checked = val;
      chkAll.indeterminate = false;
    }
    updateSelectedCount();
  }

  // ---- Filter ----
  function filterPosts(type, btn) {
    activeFilter = type;
    document.querySelectorAll(".sm-filter-btn").forEach(b => b.classList.remove("active"));
    btn.classList.add("active");
    renderTable(allPosts, type);
  }

  // ---- Update counters ----
  function updateCounts() {
    const types = ["cfp", "speaker", "session", "ticket", "schedule"];
    const cntAll = document.getElementById("cnt-all");
    if (cntAll) cntAll.textContent = allPosts.length;
    types.forEach(t => {
      const el = document.getElementById(`cnt-${t}`);
      if (el) el.textContent = allPosts.filter(p => p.type === t).length;
    });
    updateSelectedCount();
  }

  function updateSelectedCount() {
    const n = allPosts.filter(p => p.enabled).length;
    const total = allPosts.length;
    const selCount = document.getElementById("selected-count");
    if (selCount) selCount.textContent = `${n} / ${total} selected`;
    
    const expCount = document.getElementById("export-count");
    if (expCount) expCount.textContent = `${n} post${n !== 1 ? "s" : ""} selected`;

    const allChk = document.getElementById("chk-all");
    if (allChk) {
      allChk.checked = n === total && total > 0;
      allChk.indeterminate = n > 0 && n < total;
    }
  }

  // ---- Export CSV ----
  function exportCSV() {
    const selected = allPosts.filter(p => p.enabled);
    if (!selected.length) {
      alert(TRANS_SELECT_AT_LEAST_ONE);
      return;
    }

    fetch(EXPORT_URL, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": CSRF_TOKEN,
        "X-Requested-With": "XMLHttpRequest",
      },
      body: JSON.stringify({ posts: allPosts }),
    })
      .then(r => {
        if (!r.ok) throw new Error("Export failed: " + r.status);
        return r.blob();
      })
      .then(blob => {
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = "socialmedia_posts.csv";
        document.body.appendChild(a);
        a.click();
        a.remove();
        URL.revokeObjectURL(url);
      })
      .catch(err => alert("Export error: " + err.message));
  }

  // ---- Advanced settings toggle ----
  function toggleAdv() {
    const body = document.getElementById("adv-body");
    const hdr  = document.getElementById("adv-toggle");
    if (body && hdr) {
      const open = body.classList.toggle("open");
      hdr.classList.toggle("open", open);
    }
  }

  // ---- Skeleton helper ----
  function showSkeleton() {
    const tbody = document.getElementById("posts-tbody");
    if (tbody) {
      tbody.innerHTML = `
        ${[...Array(5)].map(() => `<tr class="skeleton-row">
          <td><div class="skeleton-bar" style="width:16px;height:16px;border-radius:3px;"></div></td>
          <td><div class="skeleton-bar" style="width:60px;"></div></td>
          <td><div class="skeleton-bar" style="width:80px;"></div></td>
          <td><div class="skeleton-bar" style="width:50px;"></div></td>
          <td><div class="skeleton-bar"></div></td>
        </tr>`).join("")}`;
    }
  }

  function escHtml(str) {
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  // ---- Event Bindings ----
  function bindEvents() {
    const btnRegen = document.getElementById("btn-regenerate");
    if (btnRegen) btnRegen.addEventListener("click", loadPosts);

    const btnSaveRegen = document.getElementById("btn-save-regenerate");
    if (btnSaveRegen) btnSaveRegen.addEventListener("click", loadPosts);

    const filterPills = document.getElementById("filter-pills");
    if (filterPills) {
      filterPills.addEventListener("click", function (e) {
        const btn = e.target.closest(".sm-filter-btn");
        if (btn) {
          filterPosts(btn.dataset.type, btn);
        }
      });
    }

    const btnSelectAll = document.getElementById("btn-select-all");
    if (btnSelectAll) {
      btnSelectAll.addEventListener("click", () => selectAll(true));
    }

    const btnDeselectAll = document.getElementById("btn-deselect-all");
    if (btnDeselectAll) {
      btnDeselectAll.addEventListener("click", () => selectAll(false));
    }

    const chkAll = document.getElementById("chk-all");
    if (chkAll) {
      chkAll.addEventListener("change", function () {
        selectAll(this.checked);
      });
    }

    const btnExport = document.getElementById("btn-export");
    if (btnExport) {
      btnExport.addEventListener("click", exportCSV);
    }

    const advToggle = document.getElementById("adv-toggle");
    if (advToggle) {
      advToggle.addEventListener("click", toggleAdv);
    }

    // Attach tbody event delegation
    const tbody = document.getElementById("posts-tbody");
    if (tbody) {
      tbody.addEventListener("click", function (e) {
        if (e.target.classList.contains("post-text-view")) {
          const idx = parseInt(e.target.dataset.idx);
          startEdit(idx, e.target);
        }
      });

      tbody.addEventListener("change", function (e) {
        if (e.target.classList.contains("row-chk")) {
          const idx = parseInt(e.target.dataset.idx);
          toggleRow(idx, e.target.checked);
        } else if (e.target.classList.contains("sm-time-input")) {
          const row = e.target.closest("tr");
          const idx = parseInt(row.dataset.idx);
          allPosts[idx].post_time = e.target.value;
          syncTimeDisplay(idx, e.target.value);
        }
      });

      tbody.addEventListener("keydown", function (e) {
        if (e.target.classList.contains("post-text-edit")) {
          if ((e.metaKey || e.ctrlKey) && e.key === "Enter") {
            e.target.blur();
          }
        }
      });

      tbody.addEventListener("focusout", function (e) {
        if (e.target.classList.contains("post-text-edit")) {
          const idx = parseInt(e.target.dataset.idx);
          finishEdit(idx, e.target);
        }
      });
    }
  }

  // Auto-load and bind on page ready
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", () => {
      bindEvents();
      loadPosts();
    });
  } else {
    bindEvents();
    loadPosts();
  }
})();
