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

  // ---- Helper for date calculation ----
  function addDays(dateStr, days) {
    const parts = dateStr.split('-');
    const date = new Date(Date.UTC(parseInt(parts[0]), parseInt(parts[1]) - 1, parseInt(parts[2])));
    date.setUTCDate(date.getUTCDate() + days);
    return date.toISOString().split('T')[0];
  }

  // ---- Toast notifications ----
  function showToast(msg, type = "success") {
    const toast = document.createElement("div");
    toast.className = `alert alert-${type === "success" ? "success" : "warning"}`;
    toast.style.position = "fixed";
    toast.style.top = "20px";
    toast.style.right = "20px";
    toast.style.zIndex = "9999";
    toast.style.boxShadow = "0 4px 12px rgba(0,0,0,0.15)";
    toast.style.padding = "12px 20px";
    toast.style.margin = "0";
    toast.innerHTML = `<i class="fa ${type === "success" ? "fa-check-circle" : "fa-warning"}"></i> ${msg}`;
    document.body.appendChild(toast);
    setTimeout(() => {
      toast.style.opacity = "0";
      toast.style.transition = "opacity 0.5s ease";
      setTimeout(() => toast.remove(), 500);
    }, 3000);
  }

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
        const incoming = data.posts || [];
        const oldMap = {};
        allPosts.forEach(p => {
          if (p.id) {
            oldMap[p.id] = p;
          }
        });
        
        allPosts = incoming.map(p => {
          const old = oldMap[p.id];
          if (old) {
            return {
              ...p,
              post_text: old.post_text !== old.default_text ? old.post_text : p.post_text,
              post_date: old.post_date !== old.original_post_date ? old.post_date : p.post_date,
              post_time: old.post_time !== old.original_post_time ? old.post_time : p.post_time,
              enabled: old.enabled
            };
          }
          return { ...p, enabled: true };
        });

        renderTable(allPosts, activeFilter);
        updateCounts();
        validateAllPosts();
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

    const todayStr = new Date().toISOString().split('T')[0];

    tbody.innerHTML = visible.map((p, i) => {
      const idx = allPosts.indexOf(p);
      const safeType = escHtml(p.type);
      const isDateModified = p.post_date !== p.original_post_date;
      const isTimeModified = p.post_time !== p.original_post_time;
      const isTextModified = p.post_text !== p.default_text;

      const hasPlaceholder = p.post_text.includes("{") || p.post_text.includes("}");
      const isPast = p.post_date < todayStr;

      const dateClass = isDateModified ? "is-modified" : "";
      const timeClass = isTimeModified ? "is-modified" : "";
      const textClass = isTextModified ? "is-modified" : "";

      const refHtml = p.reference_date ? `<div class="dt-ref-date"><i class="fa fa-info-circle"></i> Ref: ${escHtml(p.reference_date)}</div>` : "";
      const dateWarn = isPast ? `<div class="validation-warning-badge"><i class="fa fa-exclamation-triangle"></i> Scheduled in past</div>` : "";
      const textWarn = hasPlaceholder ? `<div class="validation-warning-badge"><i class="fa fa-exclamation-triangle"></i> Unresolved placeholders</div>` : "";

      const revertBtn = isTextModified ? `<button class="btn-revert-text" data-idx="${idx}" type="button"><i class="fa fa-undo"></i> Revert to default</button>` : "";
      const charCount = p.post_text.length;
      return `
      <tr data-idx="${idx}" data-type="${safeType}" class="${p.enabled ? "" : "row-disabled"}">
        <td>
          <input type="checkbox" class="row-chk" data-idx="${idx}"
            ${p.enabled ? "checked" : ""}>
        </td>
        <td>
          <span class="type-badge type-${safeType}">${escHtml(p.type_label)}</span>
        </td>
        <td>
          <input type="date" class="form-control input-sm sm-date-input ${dateClass}" data-idx="${idx}" value="${escHtml(p.post_date)}">
          ${isDateModified ? '<div class="is-modified-label">Modified</div>' : ''}
          ${refHtml}
          ${dateWarn}
        </td>
        <td>
          <input type="time" class="form-control input-sm sm-time-input ${timeClass}" data-idx="${idx}" value="${escHtml(p.post_time)}">
          ${isTimeModified ? '<div class="is-modified-label">Modified</div>' : ''}
        </td>
        <td class="post-text-cell">
          <span class="post-text-view ${textClass}" data-idx="${idx}" tabindex="0">${escHtml(p.post_text)}</span>
          <textarea class="post-text-edit ${hasPlaceholder ? 'has-warning' : ''}" data-idx="${idx}">${escHtml(p.post_text)}</textarea>
          <div class="char-count-wrap" style="font-size: 11px; color: #888; margin-top: 4px; display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap;">
            <span><span class="char-count">${charCount}</span> characters</span>
            ${revertBtn}
          </div>
          ${textWarn}
        </td>
      </tr>`;
    }).join("");

    updateSelectedCount();
  }

  // ---- Inline editing ----
  function startEdit(idx, span) {
    const cell = span.closest(".post-text-cell");
    if (!cell) return;
    const ta = cell.querySelector(".post-text-edit");
    span.classList.add("editing");
    if (ta) {
      ta.classList.add("editing");
      ta.style.display = "block";
      ta.focus();
      ta.setSelectionRange(ta.value.length, ta.value.length);
    }
  }

  // Focusout / blur
  function finishEdit(idx, ta) {
    allPosts[idx].post_text = ta.value;
    renderTable(allPosts, activeFilter);
    validateAllPosts();
  }

  // Revert to template
  function revertPostText(idx) {
    const post = allPosts[idx];
    if (post && post.default_text !== undefined) {
      post.post_text = post.default_text;
      renderTable(allPosts, activeFilter);
      validateAllPosts();
      showToast("Reverted post text to template default.", "success");
    }
  }

  // ---- Toggle row ----
  function toggleRow(idx, enabled) {
    allPosts[idx].enabled = enabled;
    const row = document.querySelector(`tr[data-idx="${idx}"]`);
    if (row) row.classList.toggle("row-disabled", !enabled);
    updateSelectedCount();
    validateAllPosts();
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
    validateAllPosts();
  }

  // ---- Filter ----
  function filterPosts(type, btn) {
    activeFilter = type;
    document.querySelectorAll(".sm-filter-btn").forEach(b => b.classList.remove("active"));
    btn.classList.add("active");
    renderTable(allPosts, type);
    validateAllPosts();
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

  // ---- Validation checks ----
  function validateAllPosts() {
    let pastCount = 0;
    let placeholderCount = 0;
    const todayStr = new Date().toISOString().split('T')[0];

    allPosts.forEach(p => {
      if (!p.enabled) return;
      if (p.post_date < todayStr) {
        pastCount++;
      }
      if (p.post_text.includes("{") || p.post_text.includes("}")) {
        placeholderCount++;
      }
    });

    const alertContainer = document.getElementById("validation-alert-container");
    if (!alertContainer) return;

    if (pastCount > 0 || placeholderCount > 0) {
      let html = `<div class="alert alert-warning" style="margin-bottom: 12px;">`;
      html += `<strong>Warning:</strong> `;
      const parts = [];
      if (pastCount > 0) {
        parts.push(`${pastCount} active post(s) scheduled in the past`);
      }
      if (placeholderCount > 0) {
        parts.push(`${placeholderCount} post(s) with unresolved placeholders (e.g. {tag})`);
      }
      html += parts.join(" and ") + `. Review highlighted rows before exporting.`;
      html += `</div>`;
      alertContainer.innerHTML = html;
      alertContainer.style.display = "block";
    } else {
      alertContainer.style.display = "none";
      alertContainer.innerHTML = "";
    }
  }

  // ---- Apply bulk scheduling ----
  function applyBulkSchedule() {
    const preset = document.getElementById("bulk-schedule-preset").value;
    if (!preset) {
      alert("Please select a schedule preset first.");
      return;
    }

    const selected = allPosts.filter(p => p.enabled);
    if (!selected.length) {
      alert("Please select at least one post row to apply scheduling.");
      return;
    }

    let updatedCount = 0;
    let skippedCount = 0;

    if (preset === "custom") {
      const customDate = document.getElementById("bulk-schedule-custom-date").value;
      const customTime = document.getElementById("bulk-schedule-custom-time").value;
      if (!customDate || !customTime) {
        alert("Please select both a custom date and time.");
        return;
      }
      selected.forEach(p => {
        p.post_date = customDate;
        p.post_time = customTime;
        updatedCount++;
      });
    } else {
      const offsetDays = parseInt(preset);
      selected.forEach(p => {
        if (p.reference_date) {
          p.post_date = addDays(p.reference_date, offsetDays);
          updatedCount++;
        } else {
          skippedCount++;
        }
      });
    }

    renderTable(allPosts, activeFilter);
    validateAllPosts();

    let msg = `Applied preset to ${updatedCount} post(s).`;
    if (skippedCount > 0) {
      msg += ` (${skippedCount} post(s) skipped due to missing reference dates).`;
    }
    showToast(msg, "success");
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

        showToast(`Successfully exported ${selected.length} post(s).`, "success");
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
          <td><div class="skeleton-bar" style="width:130px;"></div></td>
          <td><div class="skeleton-bar" style="width:100px;"></div></td>
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

  // ---- Save settings & regenerate preview ----
  function saveAndRegenerate(e) {
    e.preventDefault();
    const btn = document.getElementById("btn-save-regenerate");
    if (!btn) return;
    btn.disabled = true;
    btn.innerHTML = '<i class="fa fa-refresh"></i> Saving…';

    const form = btn.closest("form");
    const formData = new FormData(form);

    fetch("", {
      method: "POST",
      headers: {
        "X-CSRFToken": CSRF_TOKEN,
        "X-Requested-With": "XMLHttpRequest",
      },
      body: formData
    })
      .then(r => {
        if (!r.ok) throw new Error("Save failed");
        // If not redirected, form was invalid (returned 200 same template with errors)
        if (!r.redirected) {
          throw new Error("Form validation failed");
        }
        return r.text();
      })
      .then(() => {
        showToast("Settings saved successfully.", "success");
        loadPosts();
      })
      .catch(err => {
        // Fallback: submit normally so user can see validation error highlights
        form.submit();
      })
      .finally(() => {
        btn.disabled = false;
        btn.innerHTML = '<i class="fa fa-refresh"></i> Save & Regenerate Preview';
      });
  }

  // ---- Event Bindings ----
  function bindEvents() {
    const btnRegen = document.getElementById("btn-regenerate");
    if (btnRegen) btnRegen.addEventListener("click", loadPosts);

    const btnSaveRegen = document.getElementById("btn-save-regenerate");
    if (btnSaveRegen) btnSaveRegen.addEventListener("click", saveAndRegenerate);

    const filterPills = document.getElementById("filter-pills");
    if (filterPills) {
      filterPills.addEventListener("click", function (e) {
        const btn = e.target.closest(".sm-filter-btn");
        if (btn) {
          filterPosts(btn.dataset.type, btn);
        }
      });
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

    // Bulk scheduling preset change & apply bindings
    const presetSel = document.getElementById("bulk-schedule-preset");
    const customInputs = document.getElementById("bulk-schedule-custom-inputs");
    if (presetSel && customInputs) {
      presetSel.addEventListener("change", function () {
        if (this.value === "custom") {
          customInputs.style.display = "flex";
        } else {
          customInputs.style.display = "none";
        }
      });
    }

    const btnApplySchedule = document.getElementById("btn-apply-schedule");
    if (btnApplySchedule) {
      btnApplySchedule.addEventListener("click", applyBulkSchedule);
    }

    // Attach tbody event delegation
    const tbody = document.getElementById("posts-tbody");
    if (tbody) {
      tbody.addEventListener("click", function (e) {
        if (e.target.classList.contains("post-text-view")) {
          const idx = parseInt(e.target.dataset.idx);
          startEdit(idx, e.target);
        } else if (e.target.closest(".btn-revert-text")) {
          const btn = e.target.closest(".btn-revert-text");
          const idx = parseInt(btn.dataset.idx);
          revertPostText(idx);
        }
      });

      tbody.addEventListener("change", function (e) {
        if (e.target.classList.contains("row-chk")) {
          const idx = parseInt(e.target.dataset.idx);
          toggleRow(idx, e.target.checked);
        } else if (e.target.classList.contains("sm-date-input")) {
          const idx = parseInt(e.target.dataset.idx);
          allPosts[idx].post_date = e.target.value;
          renderTable(allPosts, activeFilter);
          validateAllPosts();
        } else if (e.target.classList.contains("sm-time-input")) {
          const idx = parseInt(e.target.dataset.idx);
          allPosts[idx].post_time = e.target.value;
          renderTable(allPosts, activeFilter);
          validateAllPosts();
        }
      });

      tbody.addEventListener("input", function (e) {
        if (e.target.classList.contains("post-text-edit")) {
          const idx = parseInt(e.target.dataset.idx);
          allPosts[idx].post_text = e.target.value;
          
          const cell = e.target.closest(".post-text-cell");
          if (cell) {
            const countSpan = cell.querySelector(".char-count");
            if (countSpan) {
              countSpan.textContent = e.target.value.length;
            }
          }
        }
      });

      tbody.addEventListener("keydown", function (e) {
        if (e.target.classList.contains("post-text-view")) {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            const idx = parseInt(e.target.dataset.idx);
            startEdit(idx, e.target);
          }
        } else if (e.target.classList.contains("post-text-edit")) {
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
