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
  window.loadPosts = function () {
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
  };

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
            ${p.enabled ? "checked" : ""}
            onchange="toggleRow(${idx}, this.checked)">
        </td>
        <td><span class="type-badge type-${p.type}">${escHtml(p.type_label)}</span></td>
        <td class="dt-cell">
          <div class="dt-date">${escHtml(p.post_date)}</div>
          <div class="dt-time">${escHtml(p.post_time)}</div>
        </td>
        <td class="dt-cell">
          <input type="time" class="form-control input-sm sm-time-input" value="${escHtml(p.post_time)}"
            onchange="allPosts[${idx}].post_time = this.value; syncTimeDisplay(${idx}, this.value);">
        </td>
        <td class="post-text-cell">
          <span class="post-text-view" onclick="startEdit(${idx}, this)" data-idx="${idx}">${escHtml(p.post_text)}</span>
          <textarea class="post-text-edit" data-idx="${idx}"
            onblur="finishEdit(${idx}, this)"
            onkeydown="if((event.metaKey||event.ctrlKey)&&event.key==='Enter') this.blur();"
          >${escHtml(p.post_text)}</textarea>
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
  window.startEdit = function (idx, span) {
    const ta = span.nextElementSibling;
    span.classList.add("editing");
    ta.classList.add("editing");
    ta.style.display = "block";
    ta.focus();
    ta.setSelectionRange(ta.value.length, ta.value.length);
  };

  window.finishEdit = function (idx, ta) {
    allPosts[idx].post_text = ta.value;
    const span = ta.previousElementSibling;
    span.textContent = ta.value;
    span.classList.remove("editing");
    ta.classList.remove("editing");
    ta.style.display = "none";
  };

  // ---- Toggle row ----
  window.toggleRow = function (idx, enabled) {
    allPosts[idx].enabled = enabled;
    const row = document.querySelector(`tr[data-idx="${idx}"]`);
    if (row) row.classList.toggle("row-disabled", !enabled);
    updateSelectedCount();
  };

  // ---- Select all / none ----
  window.selectAll = function (val) {
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
  };

  // ---- Filter ----
  window.filterPosts = function (type, btn) {
    activeFilter = type;
    document.querySelectorAll(".sm-filter-btn").forEach(b => b.classList.remove("active"));
    btn.classList.add("active");
    renderTable(allPosts, type);
  };

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
  window.exportCSV = function () {
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
  };

  // ---- Advanced settings toggle ----
  window.toggleAdv = function () {
    const body = document.getElementById("adv-body");
    const hdr  = document.getElementById("adv-toggle");
    if (body && hdr) {
      const open = body.classList.toggle("open");
      hdr.classList.toggle("open", open);
    }
  };

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

  // Auto-load on page ready
  document.addEventListener("DOMContentLoaded", loadPosts);
})();
