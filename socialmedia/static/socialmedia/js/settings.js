(function () {
  // ---- Config module ----
  const Config = (function () {
    const configEl = document.getElementById("socialmedia-config");
    if (!configEl) return null;
    const config = JSON.parse(configEl.textContent);

    return {
      PREVIEW_URL: config.previewUrl,
      EXPORT_URL: config.exportUrl,
      UPDATE_URL: config.updateUrl,
      CSRF_TOKEN: config.csrfToken,
      TRANS_CLICK_TO_EDIT: config.transClickToEdit || "Click to edit · Ctrl+Enter to save",
      TRANS_SELECT_AT_LEAST_ONE: config.transSelectAtLeastOne || "Please select at least one post to export.",
    };
  })();

  if (!Config) return;

  // ---- Helper functions ----
  const Helpers = {
    addDays(dateStr, days) {
      const parts = dateStr.split('-');
      const date = new Date(Date.UTC(parseInt(parts[0]), parseInt(parts[1]) - 1, parseInt(parts[2])));
      date.setUTCDate(date.getUTCDate() + days);
      return date.toISOString().split('T')[0];
    },
    getLocalTodayStr() {
      const now = new Date();
      return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}`;
    }
  };

  // ---- State Store module ----
  const PostState = (function () {
    let posts = [];
    let activeFilter = "all";

    return {
      init(incomingPosts) {
        posts = incomingPosts;
      },
      get(id) {
        return posts.find(p => p.id == id) || null;
      },
      getAll() {
        return posts;
      },
      getFiltered() {
        if (activeFilter === "excluded") {
          return posts.filter(p => p.status === "excluded");
        }
        const list = activeFilter === "all" ? posts : posts.filter(p => p.type === activeFilter);
        return list.filter(p => p.status !== "excluded");
      },
      getFilter() {
        return activeFilter;
      },
      setFilter(filter) {
        activeFilter = filter;
      },
      update(id, updates) {
        const post = this.get(id);
        if (post) {
          Object.assign(post, updates);
        }
        return post;
      },
      toggle(id, enabled) {
        return this.update(id, { enabled });
      },
      selectAll(enabled) {
        posts.forEach(p => { p.enabled = enabled; });
      },
      applyBulkPreset(offsetDays) {
        let updatedCount = 0;
        let skippedCount = 0;

        posts.forEach(p => {
          if (!p.enabled) return;
          if (p.reference_date) {
            p.post_date = Helpers.addDays(p.reference_date, offsetDays);
            updatedCount++;
          } else {
            skippedCount++;
          }
        });

        return { updatedCount, skippedCount };
      },
      applyBulkCustom(customDate, customTime) {
        let updatedCount = 0;
        posts.forEach(p => {
          if (!p.enabled) return;
          p.post_date = customDate;
          p.post_time = customTime;
          updatedCount++;
        });
        return { updatedCount };
      },
      applyBulkDefault() {
        let updatedCount = 0;
        posts.forEach(p => {
          if (!p.enabled) return;
          p.post_date = p.original_post_date;
          p.post_time = p.original_post_time;
          updatedCount++;
        });
        return { updatedCount };
      },
      validate() {
        let pastCount = 0;
        let placeholderCount = 0;
        const todayStr = Helpers.getLocalTodayStr();

        posts.forEach(p => {
          if (!p.enabled) return;
          if (p.post_date < todayStr) pastCount++;
          if (p.post_text.includes("{") || p.post_text.includes("}")) placeholderCount++;
        });

        return { pastCount, placeholderCount };
      }
    };
  })();

  // ---- API Client module ----
  const APIClient = {
    fetchPreview() {
      return fetch(Config.PREVIEW_URL, {
        headers: { "X-Requested-With": "XMLHttpRequest" }
      }).then(r => {
        if (!r.ok) throw new Error(`HTTP error ${r.status}`);
        return r.json();
      });
    },
    saveSettings(formData) {
      return fetch("", {
        method: "POST",
        headers: {
          "X-CSRFToken": Config.CSRF_TOKEN,
          "X-Requested-With": "XMLHttpRequest",
        },
        body: formData
      }).then(r => {
        if (!r.ok) throw new Error("Save failed");
        if (!r.redirected) throw new Error("Form validation failed");
        return r.text();
      });
    },
    exportCSV(posts) {
      return fetch(Config.EXPORT_URL, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": Config.CSRF_TOKEN,
          "X-Requested-With": "XMLHttpRequest",
        },
        body: JSON.stringify({ posts })
      }).then(r => {
        if (!r.ok) throw new Error(`Export failed: ${r.status}`);
        return r.blob();
      });
    },
    savePostToDB(post) {
      if (!Config.UPDATE_URL || !post) return Promise.resolve();
      const isPinned = (post.post_text !== post.default_text) ||
                       (post.post_date !== post.original_post_date) ||
                       (post.post_time !== post.original_post_time);
      return fetch(Config.UPDATE_URL, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": Config.CSRF_TOKEN,
          "X-Requested-With": "XMLHttpRequest",
        },
        body: JSON.stringify({
          id: post.id,
          db_id: post.db_id,
          post_text: post.post_text,
          post_date: post.post_date,
          post_time: post.post_time,
          is_pinned: isPinned
        }),
      })
        .then(r => {
          if (!r.ok) throw new Error("Save to DB failed");
          return r.json();
        })
        .then(res => {
          if (res.db_id) post.db_id = res.db_id;
          post.is_pinned = res.is_pinned;
          return res;
        })
        .catch(err => console.error("Failed to save post to DB:", err));
    },
    updatePostStatus(post, status) {
      if (!Config.UPDATE_URL || !post) return Promise.resolve();
      return fetch(Config.UPDATE_URL, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": Config.CSRF_TOKEN,
          "X-Requested-With": "XMLHttpRequest",
        },
        body: JSON.stringify({
          id: post.id,
          db_id: post.db_id,
          status: status
        }),
      })
        .then(r => {
          if (!r.ok) throw new Error("Status update failed");
          return r.json();
        })
        .then(res => {
          if (res.db_id) post.db_id = res.db_id;
          if (res.is_pinned) post.is_pinned = true;
          return res;
        })
        .catch(err => console.error("Failed to update post status:", err));
    }
  };

  // ---- UI module ----
  const UI = {
    setWithIcon(el, text, iconClass) {
      if (!el) return;
      el.textContent = "";
      if (iconClass) {
        const icon = document.createElement("i");
        icon.className = iconClass;
        el.appendChild(icon);
        el.appendChild(document.createTextNode(" " + text));
      } else {
        el.appendChild(document.createTextNode(text));
      }
    },

    showToast(msg, type = "success", onUndo = null) {
      const toast = document.createElement("div");
      toast.className = `sm-toast sm-toast-${type}`;

      const icon = document.createElement("i");
      icon.className = `fa ${type === "success" ? "fa-check-circle" : "fa-warning"}`;
      toast.appendChild(icon);
      toast.appendChild(document.createTextNode(msg));

      if (onUndo) {
        const undoBtn = document.createElement("button");
        undoBtn.className = "sm-toast-undo";
        undoBtn.type = "button";
        undoBtn.textContent = "Undo";
        undoBtn.addEventListener("click", () => {
          onUndo();
          toast.remove();
        });
        toast.appendChild(undoBtn);
      }

      document.body.appendChild(toast);
      setTimeout(() => {
        if (toast.parentNode) {
          toast.style.transition = "opacity 0.5s ease";
          toast.style.opacity = "0";
          setTimeout(() => {
            if (toast.parentNode) toast.remove();
          }, 500);
        }
      }, 5000);
    },

    showSkeleton() {
      const tbody = document.getElementById("posts-tbody");
      if (!tbody) return;
      tbody.textContent = "";

      for (let i = 0; i < 5; i++) {
        const tr = document.createElement("tr");
        tr.className = "skeleton-row";

        const tdChk = document.createElement("td");
        const bChk = document.createElement("div");
        bChk.className = "skeleton-bar";
        bChk.style.width = "16px";
        bChk.style.height = "16px";
        bChk.style.borderRadius = "3px";
        tdChk.appendChild(bChk);
        tr.appendChild(tdChk);

        const tdType = document.createElement("td");
        const bType = document.createElement("div");
        bType.className = "skeleton-bar";
        bType.style.width = "60px";
        tdType.appendChild(bType);
        tr.appendChild(tdType);

        const tdSched = document.createElement("td");
        const bSched = document.createElement("div");
        bSched.className = "skeleton-bar";
        bSched.style.width = "110px";
        tdSched.appendChild(bSched);
        tr.appendChild(tdSched);

        const tdInput = document.createElement("td");
        const bInput = document.createElement("div");
        bInput.className = "skeleton-bar";
        bInput.style.width = "125px";
        tdInput.appendChild(bInput);
        tr.appendChild(tdInput);

        const tdText = document.createElement("td");
        const bText = document.createElement("div");
        bText.className = "skeleton-bar";
        tdText.appendChild(bText);
        tr.appendChild(tdText);

        tbody.appendChild(tr);
      }
    },

    createPostRow(p, todayStr) {
      const isDateModified = p.post_date !== p.original_post_date;
      const isTimeModified = p.post_time !== p.original_post_time;
      const isTextModified = p.post_text !== p.default_text;

      const hasPlaceholder = p.post_text.includes("{") || p.post_text.includes("}");
      const isPast = p.post_date < todayStr;

      const tr = document.createElement("tr");
      tr.dataset.postId = p.id;
      tr.dataset.type = p.type;
      tr.className = p.enabled ? "" : "row-disabled";

      const tdChk = document.createElement("td");
      const chk = document.createElement("input");
      chk.type = "checkbox";
      chk.className = "row-chk";
      chk.dataset.postId = p.id;
      chk.checked = p.enabled;
      tdChk.appendChild(chk);
      tr.appendChild(tdChk);

      const tdType = document.createElement("td");
      const typeSpan = document.createElement("span");
      typeSpan.className = `type-badge type-${p.type}`;
      typeSpan.textContent = p.type_label;
      tdType.appendChild(typeSpan);
      tr.appendChild(tdType);

      const tdSched = document.createElement("td");
      tdSched.className = "event-schedule-cell";
      if (p.is_schedule_associated) {
        if (p.event_schedule_display === "Unscheduled") {
          const spanUn = document.createElement("span");
          spanUn.className = "sched-badge sched-unscheduled";
          this.setWithIcon(spanUn, "Unscheduled", "fa fa-clock-o");
          tdSched.appendChild(spanUn);
        } else if (p.event_schedule_display) {
          const parts = p.event_schedule_display.split(" ");
          if (parts.length >= 3) {
            const dateStr = parts.slice(0, 3).join(" ");
            const timeStr = parts.slice(3).join(" ");

            const box = document.createElement("div");
            box.className = "sched-box sched-active";

            const dRow = document.createElement("div");
            dRow.className = "sched-date-row";
            this.setWithIcon(dRow, dateStr, "fa fa-calendar");

            const tRow = document.createElement("div");
            tRow.className = "sched-time-row";
            this.setWithIcon(tRow, timeStr, "fa fa-clock-o");

            box.appendChild(dRow);
            box.appendChild(tRow);
            tdSched.appendChild(box);
          } else {
            const spanAct = document.createElement("span");
            spanAct.className = "sched-badge sched-active";
            this.setWithIcon(spanAct, p.event_schedule_display, "fa fa-calendar");
            tdSched.appendChild(spanAct);
          }
        }
      } else {
        const spanNa = document.createElement("span");
        spanNa.className = "sched-badge sched-na";
        spanNa.textContent = "N/A";
        tdSched.appendChild(spanNa);
      }
      tr.appendChild(tdSched);

      const tdPostSched = document.createElement("td");
      const wrap = document.createElement("div");
      wrap.className = "post-schedule-cell-wrap";

      const dateIn = document.createElement("input");
      dateIn.type = "date";
      dateIn.className = `form-control input-sm sm-date-input${isDateModified ? ' is-modified' : ''}`;
      dateIn.dataset.postId = p.id;
      dateIn.value = p.post_date;
      wrap.appendChild(dateIn);

      const timeIn = document.createElement("input");
      timeIn.type = "time";
      timeIn.className = `form-control input-sm sm-time-input${isTimeModified ? ' is-modified' : ''}`;
      timeIn.dataset.postId = p.id;
      timeIn.value = p.post_time;
      wrap.appendChild(timeIn);

      if (isDateModified || isTimeModified) {
        const mod = document.createElement("div");
        mod.className = "is-modified-label";
        mod.textContent = "Modified";
        wrap.appendChild(mod);

        const revTime = document.createElement("button");
        revTime.className = "btn-revert-time";
        revTime.dataset.postId = p.id;
        revTime.type = "button";
        revTime.title = "Revert to default timing";
        this.setWithIcon(revTime, "", "fa fa-undo");
        wrap.appendChild(revTime);
      }

      if (isPast) {
        const warn = document.createElement("div");
        warn.className = "validation-warning-badge";
        this.setWithIcon(warn, "Scheduled in past", "fa fa-exclamation-triangle");
        wrap.appendChild(warn);
      }
      tdPostSched.appendChild(wrap);
      tr.appendChild(tdPostSched);

      const tdContent = document.createElement("td");
      tdContent.className = "post-text-cell";

      const viewSpan = document.createElement("span");
      viewSpan.className = `post-text-view${isTextModified ? ' is-modified' : ''}`;
      viewSpan.dataset.postId = p.id;
      viewSpan.tabIndex = 0;
      viewSpan.textContent = p.post_text;
      tdContent.appendChild(viewSpan);

      const editArea = document.createElement("textarea");
      editArea.className = `post-text-edit${hasPlaceholder ? ' has-warning' : ''}`;
      editArea.dataset.postId = p.id;
      editArea.value = p.post_text;
      
      const cWrap = document.createElement("div");
      cWrap.className = "char-count-wrap";
      const charSpan = document.createElement("span");
      const numSpan = document.createElement("span");
      numSpan.className = "char-count";
      numSpan.textContent = p.post_text.length;
      charSpan.appendChild(numSpan);
      charSpan.appendChild(document.createTextNode(" characters"));
      cWrap.appendChild(charSpan);

      if (isTextModified) {
        const revertBtn = document.createElement("button");
        revertBtn.className = "btn-revert-text";
        revertBtn.dataset.postId = p.id;
        revertBtn.type = "button";
        this.setWithIcon(revertBtn, "Revert to default", "fa fa-undo");
        cWrap.appendChild(revertBtn);
      }
      tdContent.appendChild(cWrap);

      if (hasPlaceholder) {
        const warn = document.createElement("div");
        warn.className = "validation-warning-badge";
        this.setWithIcon(warn, "Unresolved placeholders", "fa fa-exclamation-triangle");
        tdContent.appendChild(warn);
      }

      tdContent.appendChild(editArea);
      tr.appendChild(tdContent);

      const tdActions = document.createElement("td");
      if (p.status === "excluded") {
        const restoreBtn = document.createElement("button");
        restoreBtn.className = "btn-restore-post";
        restoreBtn.dataset.postId = p.id;
        restoreBtn.type = "button";
        restoreBtn.title = "Restore post to preview";
        this.setWithIcon(restoreBtn, "", "fa fa-undo");
        tdActions.appendChild(restoreBtn);
      } else {
        const delBtn = document.createElement("button");
        delBtn.className = "btn-delete-post";
        delBtn.dataset.postId = p.id;
        delBtn.type = "button";
        delBtn.title = "Remove post from preview";
        this.setWithIcon(delBtn, "", "fa fa-trash");
        tdActions.appendChild(delBtn);
      }
      tr.appendChild(tdActions);

      return tr;
    },

    renderTable(posts, filter) {
      const tbody = document.getElementById("posts-tbody");
      if (!tbody) return;
      tbody.textContent = "";

      let visible;
      if (filter === "excluded") {
        visible = posts.filter(p => p.status === "excluded");
      } else {
        visible = filter === "all" ? posts : posts.filter(p => p.type === filter);
        visible = visible.filter(p => p.status !== "excluded");
      }

      if (!visible.length) {
        const tr = document.createElement("tr");
        const td = document.createElement("td");
        td.colSpan = 6;

        const emptyDiv = document.createElement("div");
        emptyDiv.className = "sm-empty";
        
        const icon = document.createElement("i");
        icon.className = "fa fa-share-alt";
        emptyDiv.appendChild(icon);

        const heading = document.createElement("div");
        heading.textContent = "No posts found for this filter.";
        emptyDiv.appendChild(heading);

        const desc = document.createElement("small");
        desc.textContent = "Check that your event has the relevant data (CFP deadline, sessions, tickets).";
        emptyDiv.appendChild(desc);

        td.appendChild(emptyDiv);
        tr.appendChild(td);
        tbody.appendChild(tr);

        this.updateSelectedCount();
        return;
      }

      const todayStr = Helpers.getLocalTodayStr();
      const fragment = document.createDocumentFragment();
      visible.forEach(p => {
        fragment.appendChild(this.createPostRow(p, todayStr));
      });
      tbody.appendChild(fragment);

      this.updateSelectedCount();
    },

     updateCounts() {
      const allPosts = PostState.getAll();
      const activePosts = allPosts.filter(p => p.status !== "excluded");
      const excludedPosts = allPosts.filter(p => p.status === "excluded");

      const cntAll = document.getElementById("cnt-all");
      if (cntAll) cntAll.textContent = activePosts.length;

      const types = ["cfp", "speaker", "session", "ticket", "schedule"];
      types.forEach(t => {
        const el = document.getElementById(`cnt-${t}`);
        if (el) el.textContent = activePosts.filter(p => p.type === t).length;
      });

      const cntExcluded = document.getElementById("cnt-excluded");
      if (cntExcluded) cntExcluded.textContent = excludedPosts.length;

      this.updateSelectedCount();
    },

    updateSelectedCount() {
      const posts = PostState.getAll();
      const n = posts.filter(p => p.enabled).length;
      const total = posts.length;

      const selCount = document.getElementById("selected-count");
      if (selCount) selCount.textContent = `${n} / ${total} selected`;

      const expCount = document.getElementById("export-count");
      if (expCount) expCount.textContent = `${n} post${n !== 1 ? "s" : ""} selected`;

      const allChk = document.getElementById("chk-all");
      if (allChk) {
        allChk.checked = n === total && total > 0;
        allChk.indeterminate = n > 0 && n < total;
      }
    },

    updateRow(id) {
      const post = PostState.get(id);
      if (!post) return;

      const row = document.querySelector(`tr[data-post-id="${id}"]`);
      if (!row) return;

      const todayStr = Helpers.getLocalTodayStr();
      const newRow = this.createPostRow(post, todayStr);
      row.replaceWith(newRow);

      this.updateSelectedCount();
    },

    renderValidationAlert(pastCount, placeholderCount) {
      const alertContainer = document.getElementById("validation-alert-container");
      if (!alertContainer) return;

      if (pastCount > 0 || placeholderCount > 0) {
        const alertDiv = document.createElement("div");
        alertDiv.className = "alert alert-warning sm-validation-alert";

        const strong = document.createElement("strong");
        strong.textContent = "Warning: ";
        alertDiv.appendChild(strong);

        const parts = [];
        if (pastCount > 0) {
          parts.push(`${pastCount} active post(s) scheduled in the past`);
        }
        if (placeholderCount > 0) {
          parts.push(`${placeholderCount} post(s) with unresolved placeholders (e.g. {tag})`);
        }

        alertDiv.appendChild(document.createTextNode(parts.join(" and ") + ". Review highlighted rows before exporting."));
        alertContainer.textContent = "";
        alertContainer.appendChild(alertDiv);
        alertContainer.style.display = "block";
      } else {
        alertContainer.style.display = "none";
        alertContainer.textContent = "";
      }
    },

    startEdit(id) {
      const row = document.querySelector(`tr[data-post-id="${id}"]`);
      if (!row) return;

      const viewSpan = row.querySelector(".post-text-view");
      const editArea = row.querySelector(".post-text-edit");
      if (viewSpan && editArea) {
        viewSpan.classList.add("editing");
        editArea.classList.add("editing");
        editArea.style.display = "block";
        editArea.focus();
        editArea.setSelectionRange(editArea.value.length, editArea.value.length);
      }
    },

    finishEdit(id, value) {
      PostState.update(id, { post_text: value });
      this.updateRow(id);
      AppController.triggerValidation();
    },

    revertPostText(id) {
      const post = PostState.get(id);
      if (post && post.default_text !== undefined) {
        PostState.update(id, { post_text: post.default_text });
        this.updateRow(id);
        AppController.triggerValidation();
        APIClient.savePostToDB(post);
        this.showToast("Reverted post text to template default.", "success");
      }
    },

    revertPostTime(id) {
      const post = PostState.get(id);
      if (post) {
        PostState.update(id, {
          post_date: post.original_post_date,
          post_time: post.original_post_time
        });
        this.updateRow(id);
        AppController.triggerValidation();
        APIClient.savePostToDB(post);
        this.showToast("Reverted post timing to default.", "success");
      }
    },

    toggleRow(id, enabled) {
      PostState.toggle(id, enabled);
      const row = document.querySelector(`tr[data-post-id="${id}"]`);
      if (row) {
        row.classList.toggle("row-disabled", !enabled);
      }
      this.updateSelectedCount();
      AppController.triggerValidation();
    },

    toggleAdv() {
      const body = document.getElementById("adv-body");
      const hdr = document.getElementById("adv-toggle");
      if (body && hdr) {
        const open = body.classList.toggle("open");
        hdr.classList.toggle("open", open);
      }
    }
  };

  // ---- App Controller module (Orchestration) ----
  const AppController = {
    init() {
      this.bindEvents();
      initHelperUIs();
      this.loadInitialData();
    },

    loadInitialData() {
      const btn = document.getElementById("btn-regenerate");
      if (btn) {
        btn.disabled = true;
        UI.setWithIcon(btn, "Loading…", "fa fa-refresh");
      }
      UI.showSkeleton();

      APIClient.fetchPreview()
        .then(data => {
          const incoming = data.posts || [];
          const oldMap = {};
          PostState.getAll().forEach(p => {
            if (p.id) oldMap[p.id] = p;
          });

          const posts = incoming.map(p => {
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

          PostState.init(posts);
          UI.renderTable(PostState.getAll(), PostState.getFilter());
          UI.updateCounts();
          this.triggerValidation();
        })
        .catch(err => {
          const tbody = document.getElementById("posts-tbody");
          if (tbody) {
            tbody.textContent = "";
            const tr = document.createElement("tr");
            const td = document.createElement("td");
            td.colSpan = 6;

            const emptyDiv = document.createElement("div");
            emptyDiv.className = "sm-empty";
            
            const icon = document.createElement("i");
            icon.className = "fa fa-exclamation-triangle";
            emptyDiv.appendChild(icon);
            emptyDiv.appendChild(document.createTextNode(" Failed to load posts. " + err.message));

            td.appendChild(emptyDiv);
            tr.appendChild(td);
            tbody.appendChild(tr);
          }
        })
        .finally(() => {
          if (btn) {
            btn.disabled = false;
            UI.setWithIcon(btn, "Regenerate", "fa fa-refresh");
          }
        });
    },

    triggerValidation() {
      const { pastCount, placeholderCount } = PostState.validate();
      UI.renderValidationAlert(pastCount, placeholderCount);
    },

    saveAndRegenerate(e) {
      e.preventDefault();
      const btn = document.getElementById("btn-save-regenerate");
      if (!btn) return;
      btn.disabled = true;
      UI.setWithIcon(btn, "Saving…", "fa fa-refresh");

      const form = btn.closest("form");
      const formData = new FormData(form);

      APIClient.saveSettings(formData)
        .then(() => {
          UI.showToast("Settings saved successfully.", "success");
          this.loadInitialData();
        })
        .catch(() => {
          form.submit();
        })
        .finally(() => {
          btn.disabled = false;
          UI.setWithIcon(btn, "Save & Regenerate Preview", "fa fa-refresh");
        });
    },

    applyBulkSchedule() {
      const preset = document.getElementById("bulk-schedule-preset").value;
      if (!preset) {
        UI.showToast("Please select a schedule preset first.", "warning");
        return;
      }

      const enabledPosts = PostState.getAll().filter(p => p.enabled);
      if (!enabledPosts.length) {
        UI.showToast("Please select at least one post row to apply scheduling.", "warning");
        return;
      }

      let res;
      if (preset === "default") {
        res = PostState.applyBulkDefault();
      } else if (preset === "custom") {
        const customDate = document.getElementById("bulk-schedule-custom-date").value;
        const customTime = document.getElementById("bulk-schedule-custom-time").value;
        if (!customDate || !customTime) {
          UI.showToast("Please select both a custom date and time.", "warning");
          return;
        }
        res = PostState.applyBulkCustom(customDate, customTime);
      } else {
        const offsetDays = parseInt(preset);
        res = PostState.applyBulkPreset(offsetDays);
      }

      UI.renderTable(PostState.getAll(), PostState.getFilter());
      this.triggerValidation();

      enabledPosts.forEach(p => {
        if (preset === "default" || preset === "custom" || p.reference_date) {
          APIClient.savePostToDB(p);
        }
      });

      let msg = preset === "default"
        ? `Reverted ${res.updatedCount || 0} post(s) to default timing.`
        : `Applied preset to ${res.updatedCount || 0} post(s).`;
      if (res.skippedCount > 0) {
        msg += ` (${res.skippedCount} post(s) skipped due to missing reference dates).`;
      }
      UI.showToast(msg, "success");
    },

    exportCSV() {
      const visiblePosts = PostState.getFiltered().filter(p => p.status !== "excluded");
      const enabledVisiblePosts = visiblePosts.filter(p => p.enabled);
      if (!enabledVisiblePosts.length) {
        UI.showToast(Config.TRANS_SELECT_AT_LEAST_ONE, "warning");
        return;
      }

      APIClient.exportCSV(visiblePosts)
        .then(blob => {
          const url = URL.createObjectURL(blob);
          const a = document.createElement("a");
          a.href = url;
          a.download = "socialmedia_posts.csv";
          document.body.appendChild(a);
          a.click();
          a.remove();
          URL.revokeObjectURL(url);

          UI.showToast(`Successfully exported ${enabledVisiblePosts.length} post(s).`, "success");
        })
        .catch(err => UI.showToast(`Export error: ${err.message}`, "warning"));
    },

    bindEvents() {
      const btnRegen = document.getElementById("btn-regenerate");
      if (btnRegen) btnRegen.addEventListener("click", () => this.loadInitialData());

      const btnSaveRegen = document.getElementById("btn-save-regenerate");
      if (btnSaveRegen) btnSaveRegen.addEventListener("click", (e) => this.saveAndRegenerate(e));

      const filterPills = document.getElementById("filter-pills");
      if (filterPills) {
        filterPills.addEventListener("click", (e) => {
          const btn = e.target.closest(".sm-filter-btn");
          if (btn) {
            PostState.setFilter(btn.dataset.type);
            document.querySelectorAll(".sm-filter-btn").forEach(b => b.classList.remove("active"));
            btn.classList.add("active");
            UI.renderTable(PostState.getAll(), PostState.getFilter());
            this.triggerValidation();
          }
        });
      }

      const chkAll = document.getElementById("chk-all");
      if (chkAll) {
        chkAll.addEventListener("change", (e) => {
          const checked = e.target.checked;
          PostState.selectAll(checked);

          document.querySelectorAll(".row-chk").forEach(chk => {
            chk.checked = checked;
            const row = chk.closest("tr");
            if (row) row.classList.toggle("row-disabled", !checked);
          });

          UI.updateSelectedCount();
          this.triggerValidation();
        });
      }

      const btnExport = document.getElementById("btn-export");
      if (btnExport) btnExport.addEventListener("click", () => this.exportCSV());

      const advToggle = document.getElementById("adv-toggle");
      if (advToggle) advToggle.addEventListener("click", () => UI.toggleAdv());

      const presetSel = document.getElementById("bulk-schedule-preset");
      const customInputs = document.getElementById("bulk-schedule-custom-inputs");
      if (presetSel && customInputs) {
        presetSel.addEventListener("change", function () {
          customInputs.style.display = this.value === "custom" ? "flex" : "none";
        });
      }

      const btnApplySchedule = document.getElementById("btn-apply-schedule");
      if (btnApplySchedule) btnApplySchedule.addEventListener("click", () => this.applyBulkSchedule());

      const tbody = document.getElementById("posts-tbody");
      if (tbody) {
        tbody.addEventListener("click", (e) => {
          const tr = e.target.closest("[data-post-id]");
          if (!tr) return;
          const postId = tr.dataset.postId;

          if (e.target.classList.contains("post-text-view")) {
            UI.startEdit(postId);
          } else if (e.target.closest(".btn-revert-text")) {
            UI.revertPostText(postId);
          } else if (e.target.closest(".btn-revert-time")) {
            UI.revertPostTime(postId);
          } else if (e.target.closest(".btn-delete-post")) {
            const post = PostState.get(postId);
            if (post) {
              const previousStatus = post.status;
              PostState.update(postId, { status: "excluded" });
              tr.remove();
              UI.updateSelectedCount();
              UI.updateCounts();

              APIClient.updatePostStatus(post, "excluded");

              UI.showToast("Post removed from preview.", "success", () => {
                PostState.update(postId, { status: previousStatus });
                APIClient.updatePostStatus(post, previousStatus);
                UI.renderTable(PostState.getAll(), PostState.getFilter());
                UI.updateCounts();
              });
            }
          } else if (e.target.closest(".btn-restore-post")) {
            const post = PostState.get(postId);
            if (post) {
              PostState.update(postId, { status: "scheduled" });
              tr.remove();
              UI.updateSelectedCount();
              UI.updateCounts();

              APIClient.updatePostStatus(post, "scheduled");
              UI.showToast("Post restored to preview.", "success");
            }
          }
        });

        tbody.addEventListener("change", (e) => {
          const postId = e.target.dataset.postId;
          if (!postId) return;

          if (e.target.classList.contains("row-chk")) {
            UI.toggleRow(postId, e.target.checked);
          } else if (e.target.classList.contains("sm-date-input")) {
            PostState.update(postId, { post_date: e.target.value });
            UI.updateRow(postId);
            this.triggerValidation();
            APIClient.savePostToDB(PostState.get(postId));
          } else if (e.target.classList.contains("sm-time-input")) {
            PostState.update(postId, { post_time: e.target.value });
            UI.updateRow(postId);
            this.triggerValidation();
            APIClient.savePostToDB(PostState.get(postId));
          }
        });

        tbody.addEventListener("input", (e) => {
          const postId = e.target.dataset.postId;
          if (!postId) return;

          if (e.target.classList.contains("post-text-edit")) {
            PostState.update(postId, { post_text: e.target.value });
            const row = e.target.closest("tr");
            if (row) {
              const countSpan = row.querySelector(".char-count");
              if (countSpan) countSpan.textContent = e.target.value.length;
            }
          }
        });

        tbody.addEventListener("keydown", (e) => {
          const postId = e.target.dataset.postId;
          if (!postId) return;

          if (e.target.classList.contains("post-text-view")) {
            if (e.key === "Enter" || e.key === " ") {
              e.preventDefault();
              UI.startEdit(postId);
            }
          } else if (e.target.classList.contains("post-text-edit")) {
            if ((e.metaKey || e.ctrlKey) && e.key === "Enter") {
              e.target.blur();
            }
          }
        });

        tbody.addEventListener("focusout", (e) => {
          const postId = e.target.dataset.postId;
          if (!postId) return;

          if (e.target.classList.contains("post-text-edit")) {
            UI.finishEdit(postId, e.target.value);
            APIClient.savePostToDB(PostState.get(postId));
          }
        });
      }

      // Preset buttons clicks
      document.querySelectorAll(".presets-container .preset-btn").forEach(btn => {
        btn.addEventListener("click", function () {
          handlePresetClick(this);
        });
      });

      // Token chips clicks
      document.querySelectorAll(".token-chip").forEach(chip => {
        chip.addEventListener("click", function () {
          insertToken(this);
        });
      });
    }
  };

  // ---- Token & Preset UI Helpers ----
  function insertToken(chip) {
    const targetId = chip.dataset.target;
    const token = chip.textContent;
    const input = document.getElementById(targetId);
    if (!input) return;

    const startPos = input.selectionStart;
    const endPos = input.selectionEnd;
    const value = input.value;

    input.value = value.substring(0, startPos) + token + value.substring(endPos);
    
    input.focus();
    input.selectionStart = startPos + token.length;
    input.selectionEnd = startPos + token.length;

    // Trigger input/change event
    const evt = document.createEvent("HTMLEvents");
    evt.initEvent("input", true, true);
    input.dispatchEvent(evt);
  }

  function handlePresetClick(btn) {
    const container = btn.closest(".presets-container");
    if (!container) return;

    const targetId = container.dataset.target;
    const val = parseInt(btn.dataset.val);
    const input = document.getElementById(targetId);
    if (!input || isNaN(val)) return;

    let offsets = input.value
      .split(",")
      .map(x => parseInt(x.trim()))
      .filter(x => !isNaN(x));

    const idx = offsets.indexOf(val);
    if (idx > -1) {
      offsets.splice(idx, 1);
    } else {
      offsets.push(val);
    }

    offsets.sort((a, b) => b - a);
    input.value = offsets.join(", ");

    const evt = document.createEvent("HTMLEvents");
    evt.initEvent("change", true, true);
    input.dispatchEvent(evt);
  }

  function updatePresetsUI(container, currentOffsets) {
    container.querySelectorAll(".preset-btn").forEach(btn => {
      const val = parseInt(btn.dataset.val);
      if (currentOffsets.includes(val)) {
        btn.classList.add("btn-primary");
        btn.classList.remove("btn-default");
      } else {
        btn.classList.add("btn-default");
        btn.classList.remove("btn-primary");
      }
    });

    const preview = container.querySelector(".live-offsets-preview");
    if (preview) {
      preview.textContent = "";
      if (currentOffsets.length > 0) {
        const unit = container.dataset.unit || "days";
        preview.appendChild(document.createTextNode("Active: "));
        currentOffsets.forEach((x, idx) => {
          const span = document.createElement("span");
          span.className = "label label-info";
          span.textContent = x + unit;
          preview.appendChild(span);
          if (idx < currentOffsets.length - 1) {
            preview.appendChild(document.createTextNode(" "));
          }
        });
      } else {
        const em = document.createElement("em");
        em.textContent = "No offsets set";
        preview.appendChild(em);
      }
    }
  }

  function initHelperUIs() {
    document.querySelectorAll(".presets-container").forEach(container => {
      const targetId = container.dataset.target;
      const input = document.getElementById(targetId);
      if (input) {
        const updateFn = () => {
          const offsets = input.value
            .split(",")
            .map(x => parseInt(x.trim()))
            .filter(x => !isNaN(x));
          updatePresetsUI(container, offsets);
        };
        input.addEventListener("input", updateFn);
        input.addEventListener("change", updateFn);
        updateFn();
      }
    });
  }
  // Run on load
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", () => AppController.init());
  } else {
    AppController.init();
  }
})();
