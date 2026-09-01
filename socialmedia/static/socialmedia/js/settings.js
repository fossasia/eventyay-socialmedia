(function () {
  // ---- Config module ----
  const Config = (function () {
    const configEl = document.getElementById("socialmedia-config");
    let config = {};
    if (configEl && configEl.textContent) {
      try {
        config = JSON.parse(configEl.textContent);
      } catch (e) {
        console.warn("Failed to parse socialmedia-config JSON:", e);
      }
    }

    return {
      PREVIEW_URL: config.previewUrl || "",
      EXPORT_URL: config.exportUrl || "",
      UPDATE_URL: config.updateUrl || "",
      GENERATE_URL: config.generateUrl || "",
      BULK_ACTION_URL: config.bulkActionUrl || "",
      TEMPLATES_URL: config.templatesUrl || "",
      PUBLISH_NOW_URL: config.publishNowUrl || (config.updateUrl ? config.updateUrl.replace(/\/update\/?$/, "/publish-now/") : null),
      CSRF_TOKEN: config.csrfToken || (document.querySelector("input[name=csrfmiddlewaretoken]") ? document.querySelector("input[name=csrfmiddlewaretoken]").value : ""),
      TRANS_CLICK_TO_EDIT: config.transClickToEdit || "Click to edit · Ctrl+Enter to save",
      TRANS_SELECT_AT_LEAST_ONE: config.transSelectAtLeastOne || "Please select at least one post to export.",
    };
  })();

  // ---- Platform metadata ----
  const PLATFORM_META = {
    twitter: { label: "X / Twitter", iconClass: "fa fa-twitter", colorClass: "plat-twitter" },
    mastodon: { label: "Mastodon", iconClass: "fa fa-globe", colorClass: "plat-mastodon" },
    telegram: { label: "Telegram", iconClass: "fa fa-paper-plane", colorClass: "plat-telegram" },
    linkedin: { label: "LinkedIn", iconClass: "fa fa-linkedin", colorClass: "plat-linkedin" },
  };

  const PLATFORM_LIMITS = {
    twitter: 280,
    mastodon: 500,
    telegram: 4096,
    linkedin: 3000
  };


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
    let activeStatusFilter = "all";

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
        let list = posts;
        if (activeFilter === "excluded") {
          list = posts.filter(p => p.status === "excluded");
        } else {
          list = activeFilter === "all" ? posts : posts.filter(p => p.type === activeFilter);
          list = list.filter(p => p.status !== "excluded");
        }

        if (activeStatusFilter !== "all") {
          list = list.filter(p => p.status === activeStatusFilter);
        }
        return list;
      },
      getFilter() {
        return activeFilter;
      },
      setFilter(filter) {
        activeFilter = filter;
      },
      getStatusFilter() {
        return activeStatusFilter;
      },
      setStatusFilter(status) {
        activeStatusFilter = status;
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
        this.getFiltered().forEach(p => { p.enabled = enabled; });
      },
      applyBulkPreset(offsetDays) {
        let updatedCount = 0;
        let skippedCount = 0;

        this.getFiltered().forEach(p => {
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
        this.getFiltered().forEach(p => {
          if (!p.enabled) return;
          p.post_date = customDate;
          p.post_time = customTime;
          updatedCount++;
        });
        return { updatedCount };
      },
      applyBulkDefault() {
        let updatedCount = 0;
        this.getFiltered().forEach(p => {
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
        let limitExceededCount = 0;
        const todayStr = Helpers.getLocalTodayStr();

        this.getFiltered().forEach(p => {
          if (!p.enabled) return;
          if (p.post_date < todayStr) pastCount++;
          if (p.post_text.includes("{") || p.post_text.includes("}")) placeholderCount++;

          const limit = PLATFORM_LIMITS[p.platform] || null;
          if (limit && p.post_text.length > limit) limitExceededCount++;
        });

        return { pastCount, placeholderCount, limitExceededCount };
      }
    };
  })();

  // ---- API Client module ----
  const APIClient = {
    fetchPreview(force = false) {
      const url = force
        ? `${Config.PREVIEW_URL}${Config.PREVIEW_URL.includes("?") ? "&" : "?"}generate=true`
        : Config.PREVIEW_URL;
      return fetch(url, {
        headers: { "X-Requested-With": "XMLHttpRequest" }
      }).then(r => {
        if (!r.ok) throw new Error(`HTTP error ${r.status}`);
        return r.json();
      });
    },
    generatePosts() {
      if (!Config.GENERATE_URL) {
        return this.fetchPreview(true);
      }
      return fetch(Config.GENERATE_URL, {
        method: "POST",
        headers: {
          "X-CSRFToken": Config.CSRF_TOKEN,
          "X-Requested-With": "XMLHttpRequest",
        }
      }).then(r => {
        if (!r.ok) throw new Error(`Generate failed: ${r.status}`);
        return r.json();
      });
    },
    bulkAction(action, data) {
      if (!Config.BULK_ACTION_URL) return Promise.reject(new Error("Bulk action URL not configured"));
      return fetch(Config.BULK_ACTION_URL, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": Config.CSRF_TOKEN,
          "X-Requested-With": "XMLHttpRequest",
        },
        body: JSON.stringify({ action, ...data })
      }).then(r => {
        if (!r.ok) throw new Error(`Bulk action failed: ${r.status}`);
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
    exportCSV(posts, format) {
      return fetch(Config.EXPORT_URL, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": Config.CSRF_TOKEN,
          "X-Requested-With": "XMLHttpRequest",
        },
        body: JSON.stringify({ posts, format })
      }).then(r => {
        if (!r.ok) throw new Error(`Export failed: ${r.status}`);
        return r.blob();
      });
    }, savePostToDB(post, button = null) {
      if (!Config.UPDATE_URL || !post) return Promise.resolve();
      if (button) {
        button.disabled = true;
        UI.setWithIcon(button, "Saving…", "fa fa-spinner fa-spin");
      }
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
          post_type: post.type,
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
          post.is_saved = true;
          post.last_saved_date = post.post_date;
          post.last_saved_time = post.post_time;
          if (res.post_status) {
            post.status = res.post_status;
            post.error_message = "";
          }

          // Unconditionally refresh row state so Save button disappears and status badge updates
          UI.updateRow(post.id);

          if (res.scheduled_at) {
            UI.showToast(`Schedule saved (${res.scheduled_at}). Status updated to Scheduled!`, "success");
          }
          return res;
        })
        .catch(err => {
          console.error("Failed to save post to DB:", err);
          UI.showToast("Failed to save schedule update: " + err.message, "warning");
          if (button) {
            button.disabled = false;
            UI.setWithIcon(button, "Save Schedule", "fa fa-check");
          }
        });
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
          post_type: post.type,
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
    },

    publishPostNow(dbId, postId) {
      if (!Config.PUBLISH_NOW_URL) return Promise.reject(new Error("Publish URL not configured"));
      return fetch(Config.PUBLISH_NOW_URL, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": Config.CSRF_TOKEN,
          "X-Requested-With": "XMLHttpRequest",
        },
        body: JSON.stringify({ db_id: dbId, post_id: postId })
      }).then(async r => {
        const text = await r.text();
        let data = {};
        try {
          data = JSON.parse(text);
        } catch (e) {
          if (!r.ok) {
            throw new Error(`Server returned HTTP ${r.status}`);
          }
        }
        if (!r.ok) {
          throw new Error(data.message || data.error || `HTTP error ${r.status}`);
        }
        return data;
      });
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
        toast.classList.add("toast-fade-out");
        setTimeout(() => toast.remove(), 500);
      }, 5000);
    },

    showSkeleton() {
      const tbody = document.getElementById("posts-tbody");
      if (!tbody) return;
      tbody.textContent = "";

      for (let i = 0; i < 5; i++) {
        const tr = document.createElement("tr");
        const tdChk = document.createElement("td");
        const bChk = document.createElement("div");
        bChk.className = "skeleton-bar skeleton-col-check";
        tdChk.appendChild(bChk);
        tr.appendChild(tdChk);

        const tdType = document.createElement("td");
        const bType = document.createElement("div");
        bType.className = "skeleton-bar skeleton-col-type";
        tdType.appendChild(bType);
        tr.appendChild(tdType);

        // Platform column skeleton
        const tdPlat = document.createElement("td");
        const bPlat = document.createElement("div");
        bPlat.className = "skeleton-bar skeleton-col-platform";
        tdPlat.appendChild(bPlat);
        tr.appendChild(tdPlat);

        const tdSched = document.createElement("td");
        const bSched = document.createElement("div");
        bSched.className = "skeleton-bar skeleton-col-date";
        tdSched.appendChild(bSched);
        tr.appendChild(tdSched);

        const tdInput = document.createElement("td");
        const bInput = document.createElement("div");
        bInput.className = "skeleton-bar skeleton-col-postdate";
        tdInput.appendChild(bInput);
        tr.appendChild(tdInput);

        const tdText = document.createElement("td");
        const bText = document.createElement("div");
        bText.className = "skeleton-bar skeleton-col-content";
        tdText.appendChild(bText);
        tr.appendChild(tdText);

        const tdActions = document.createElement("td");
        const bActions = document.createElement("div");
        bActions.className = "skeleton-bar skeleton-col-actions";
        tdActions.appendChild(bActions);
        tr.appendChild(tdActions);

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

      // Platform & Account column (Issue #61)
      const tdPlat = document.createElement("td");
      tdPlat.className = "platform-account-cell";
      if (p.platform) {
        const meta = PLATFORM_META[p.platform];
        const platSpan = document.createElement("span");
        platSpan.className = `platform-badge ${meta ? meta.colorClass : ""}`;
        if (meta && meta.iconClass) {
          const icon = document.createElement("i");
          icon.className = meta.iconClass;
          platSpan.appendChild(icon);
          platSpan.appendChild(document.createTextNode(" " + (meta.label || p.platform_label || p.platform)));
        } else {
          platSpan.textContent = p.platform_label || p.platform;
        }
        tdPlat.appendChild(platSpan);

        if (p.account_handle) {
          const handleDiv = document.createElement("div");
          handleDiv.className = "plat-account-handle";
          const hIcon = document.createElement("i");
          hIcon.className = "fa fa-user-circle-o";
          handleDiv.appendChild(hIcon);
          const handleText = p.account_handle.startsWith("@") ? p.account_handle : `@${p.account_handle}`;
          handleDiv.appendChild(document.createTextNode(" " + handleText));
          tdPlat.appendChild(handleDiv);
        } else if (p.account_status === "disconnected" || !p.account_handle) {
          const missingDiv = document.createElement("div");
          missingDiv.className = "plat-account-missing text-warning";
          missingDiv.title = "No active account connected for this platform";
          const wIcon = document.createElement("i");
          wIcon.className = "fa fa-exclamation-triangle";
          missingDiv.appendChild(wIcon);
          missingDiv.appendChild(document.createTextNode(" Not connected"));
          tdPlat.appendChild(missingDiv);
        }
      } else {
        const naSpan = document.createElement("span");
        naSpan.className = "platform-badge plat-generic";
        naSpan.textContent = "Generic";
        tdPlat.appendChild(naSpan);
      }

      // Add status badge
      const statusDiv = document.createElement("div");
      statusDiv.className = "status-badge-wrap";

      const statusVal = p.status || "draft";
      const statusBadge = document.createElement("span");
      statusBadge.className = `status-badge status-${statusVal}`;

      let statusLabel = statusVal.charAt(0).toUpperCase() + statusVal.slice(1);

      if (statusVal === "failed" && p.error_message) {
        statusBadge.title = p.error_message;
        statusBadge.classList.add("has-error");

        const errIcon = document.createElement("i");
        errIcon.className = "fa fa-exclamation-circle status-error-icon";
        statusBadge.appendChild(document.createTextNode(statusLabel + " "));
        statusBadge.appendChild(errIcon);
      } else {
        statusBadge.textContent = statusLabel;
      }

      statusDiv.appendChild(statusBadge);
      tdPlat.appendChild(statusDiv);

      tr.appendChild(tdPlat);

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

      const isUnsaved = p.is_saved === false;

      if (isDateModified || isTimeModified || isUnsaved) {
        const mod = document.createElement("div");
        mod.className = "is-modified-label";
        mod.textContent = isUnsaved ? "Unsaved changes" : "Modified";
        wrap.appendChild(mod);

        if (isUnsaved) {
          const saveTime = document.createElement("button");
          saveTime.className = "btn-save-time";
          saveTime.dataset.postId = p.id;
          saveTime.type = "button";
          saveTime.title = "Save schedule time to database";
          this.setWithIcon(saveTime, "Save Schedule", "fa fa-check");
          wrap.appendChild(saveTime);
        }

        if (isDateModified || isTimeModified) {
          const revTime = document.createElement("button");
          revTime.className = "btn-revert-time";
          revTime.dataset.postId = p.id;
          revTime.type = "button";
          revTime.title = "Revert to default timing";
          this.setWithIcon(revTime, "", "fa fa-undo");
          wrap.appendChild(revTime);
        }
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
      viewSpan.title = "Click to edit text";
      viewSpan.textContent = p.post_text;
      tdContent.appendChild(viewSpan);

      const limit = PLATFORM_LIMITS[p.platform] || null;
      const exceedsLimit = limit && p.post_text.length > limit;

      const editArea = document.createElement("textarea");
      editArea.className = `post-text-edit${hasPlaceholder ? ' has-warning' : ''}${exceedsLimit ? ' has-error' : ''}`;
      editArea.dataset.postId = p.id;
      editArea.value = p.post_text;
      editArea.rows = 3;
      tdContent.appendChild(editArea);

      const cWrap = document.createElement("div");
      cWrap.className = "char-count-wrap";
      const charSpan = document.createElement("span");
      const numSpan = document.createElement("span");
      numSpan.className = `char-count${exceedsLimit ? ' has-warning' : ''}`;
      if (limit) {
        numSpan.textContent = `${p.post_text.length} / ${limit}`;
      } else {
        numSpan.textContent = p.post_text.length;
      }
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

      if (p.speaker_social_links && p.speaker_social_links.length > 0) {
        const linksDiv = document.createElement("div");
        linksDiv.className = "speaker-social-links-row";

        p.speaker_social_links.forEach((link) => {
          if (!link.url) return;
          const a = document.createElement("a");
          a.href = link.url;
          a.target = "_blank";
          a.rel = "noopener noreferrer";
          a.className = "speaker-social-pill";

          const icon = document.createElement("i");
          const net = (link.network || "globe").toLowerCase();
          if (net === "twitter" || net === "x") icon.className = "fa fa-twitter";
          else if (net === "linkedin") icon.className = "fa fa-linkedin";
          else if (net === "github") icon.className = "fa fa-github";
          else if (net === "telegram") icon.className = "fa fa-telegram";
          else if (net === "instagram") icon.className = "fa fa-instagram";
          else icon.className = "fa fa-globe";

          a.appendChild(icon);
          a.appendChild(document.createTextNode(link.handle || link.network));
          linksDiv.appendChild(a);
        });
        tdContent.appendChild(linksDiv);
      }

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
        const prevBtn = document.createElement("button");
        prevBtn.className = "btn-preview-post";
        prevBtn.dataset.postId = p.id;
        prevBtn.type = "button";
        prevBtn.title = "Preview post live card";
        this.setWithIcon(prevBtn, "", "fa fa-eye");
        tdActions.appendChild(prevBtn);

        if (p.status !== "published" && p.status !== "exported") {
          const pubBtn = document.createElement("button");
          pubBtn.className = "btn-publish-now";
          pubBtn.dataset.postId = p.id;
          pubBtn.dataset.dbId = p.db_id || "";
          pubBtn.type = "button";
          pubBtn.title = p.status === "failed" ? "Retry publishing" : "Publish now";
          this.setWithIcon(pubBtn, "", "fa fa-paper-plane");
          tdActions.appendChild(pubBtn);
        }

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
      const emptyStateEl = document.getElementById("sm-empty-setup-state");
      const mainContentEl = document.getElementById("sm-posts-main-content");
      const allPosts = PostState.getAll();

      if (allPosts.length === 0 && emptyStateEl && mainContentEl) {
        emptyStateEl.style.display = "block";
        mainContentEl.style.display = "none";
        return;
      } else if (emptyStateEl && mainContentEl) {
        emptyStateEl.style.display = "none";
        mainContentEl.style.display = "block";
      }

      const tbody = document.getElementById("posts-tbody");
      if (!tbody) return;
      tbody.textContent = "";

      const visible = PostState.getFiltered();

      if (!visible.length) {
        const tr = document.createElement("tr");
        const td = document.createElement("td");
        td.colSpan = 7;

        const emptyDiv = document.createElement("div");
        emptyDiv.className = "sm-empty";

        const icon = document.createElement("i");
        icon.className = "fa fa-share-alt";
        emptyDiv.appendChild(icon);

        const heading = document.createElement("div");
        heading.textContent = "No posts found for the selected filters.";
        emptyDiv.appendChild(heading);

        const desc = document.createElement("small");
        desc.textContent = "Try switching the content type or status filter above.";
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

    openPreviewModal(post) {
      const container = document.getElementById("sm-card-preview-container");
      if (!container || !post) return;
      container.textContent = "";

      const platformKey = post.platform || "generic";
      const meta = PLATFORM_META[platformKey] || { label: "Generic Post", iconClass: "fa fa-share-alt", colorClass: "plat-generic" };
      const limit = PLATFORM_LIMITS[platformKey] || null;

      const previewBox = document.createElement("div");
      previewBox.className = "sm-card-preview";

      // Header
      const header = document.createElement("div");
      header.className = "sm-preview-header";

      const avatar = document.createElement("div");
      avatar.className = "sm-preview-avatar";
      const icon = document.createElement("i");
      icon.className = meta.iconClass || "fa fa-user";
      avatar.appendChild(icon);
      header.appendChild(avatar);

      const authorBox = document.createElement("div");
      const nameDiv = document.createElement("div");
      nameDiv.className = "sm-preview-author";
      nameDiv.textContent = post.event_name || "Event Official";
      const handleDiv = document.createElement("div");
      handleDiv.className = "sm-preview-handle";
      handleDiv.textContent = `@eventyay_${platformKey}`;
      authorBox.appendChild(nameDiv);
      authorBox.appendChild(handleDiv);
      header.appendChild(authorBox);

      const tag = document.createElement("span");
      tag.className = `sm-preview-platform-tag platform-badge ${meta.colorClass || ''}`;
      tag.textContent = meta.label;
      header.appendChild(tag);

      previewBox.appendChild(header);

      // Body Text
      const textDiv = document.createElement("div");
      textDiv.className = "sm-preview-text";
      textDiv.textContent = post.post_text;
      previewBox.appendChild(textDiv);

      // Media Attachment (if media_url exists)
      if (post.media_url) {
        const mediaBox = document.createElement("div");
        mediaBox.className = "sm-preview-media";
        const mediaImg = document.createElement("img");
        mediaImg.src = post.media_url;
        mediaImg.alt = "Post Media Attachment";
        mediaBox.appendChild(mediaImg);
        previewBox.appendChild(mediaBox);
      }

      // Speaker Social Links Section (if present)
      if (post.speaker_social_links && post.speaker_social_links.length > 0) {
        const socialBox = document.createElement("div");
        socialBox.className = "sm-preview-speaker-socials";

        const label = document.createElement("span");
        label.className = "sm-speaker-social-label";
        label.textContent = "Speaker Profiles:";
        socialBox.appendChild(label);

        post.speaker_social_links.forEach((link) => {
          if (!link.url) return;
          const a = document.createElement("a");
          a.href = link.url;
          a.target = "_blank";
          a.rel = "noopener noreferrer";
          a.className = "sm-speaker-social-link btn btn-xs btn-default";

          const icon = document.createElement("i");
          const net = (link.network || "globe").toLowerCase();
          if (net === "twitter" || net === "x") icon.className = "fa fa-twitter";
          else if (net === "linkedin") icon.className = "fa fa-linkedin";
          else if (net === "github") icon.className = "fa fa-github";
          else if (net === "telegram") icon.className = "fa fa-telegram";
          else if (net === "instagram") icon.className = "fa fa-instagram";
          else icon.className = "fa fa-globe";

          a.appendChild(icon);
          a.appendChild(document.createTextNode(link.handle || link.network));
          socialBox.appendChild(a);
        });

        previewBox.appendChild(socialBox);
      }

      // Footer / Char Counter
      const footer = document.createElement("div");
      footer.className = "sm-preview-footer";

      const timeSpan = document.createElement("span");
      timeSpan.textContent = `Scheduled: ${post.post_date} at ${post.post_time}`;
      footer.appendChild(timeSpan);

      const charSpan = document.createElement("span");
      const exceeds = limit && post.post_text.length > limit;
      charSpan.className = exceeds ? "char-count over-limit" : "char-count";
      charSpan.textContent = limit ? `${post.post_text.length} / ${limit} chars` : `${post.post_text.length} chars`;
      footer.appendChild(charSpan);

      previewBox.appendChild(footer);
      container.appendChild(previewBox);

      // Bind modal publish now button
      const modalPubBtn = document.getElementById("btn-modal-publish-now");
      const modalEl = document.getElementById("sm-preview-modal");
      
      const hideModal = () => {
        const $jq = window.$ || window.jQuery;
        if ($jq && typeof $jq.fn.modal === "function") {
          $jq("#sm-preview-modal").modal("hide");
        } else if (modalEl) {
          modalEl.style.display = "none";
          modalEl.classList.remove("in");
        }
      };

      if (modalPubBtn) {
        if (post.db_id && post.status !== "published" && post.status !== "exported") {
          modalPubBtn.style.display = "inline-block";
          modalPubBtn.onclick = () => {
            hideModal();
            AppController.publishPostNow(post.id, post.db_id, null);
          };
        } else {
          modalPubBtn.style.display = "none";
        }
      }

      const $jq = window.$ || window.jQuery;
      if ($jq && typeof $jq.fn.modal === "function") {
        $jq("#sm-preview-modal").modal("show");
      } else if (modalEl) {
        modalEl.style.display = "block";
        modalEl.classList.add("in");
      }
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

      // Status badges counts (Issue #66)
      const currentType = PostState.getFilter();
      const relevantPosts = currentType === "all"
        ? activePosts
        : (currentType === "excluded" ? excludedPosts : activePosts.filter(p => p.type === currentType));

      const cntStatusAll = document.getElementById("cnt-status-all");
      if (cntStatusAll) cntStatusAll.textContent = relevantPosts.length;

      const statuses = ["scheduled", "published", "failed", "draft"];
      statuses.forEach(st => {
        const el = document.getElementById(`cnt-status-${st}`);
        if (el) el.textContent = relevantPosts.filter(p => p.status === st).length;
      });

      // Update bulk button disabled states
      const selected = PostState.getFiltered().filter(p => p.enabled);
      const btnDiscard = document.getElementById("btn-bulk-discard");
      if (btnDiscard) {
        btnDiscard.disabled = selected.length === 0;
      }
      const failedCount = relevantPosts.filter(p => p.status === "failed").length;
      const btnRetry = document.getElementById("btn-bulk-retry");
      if (btnRetry) {
        btnRetry.disabled = failedCount === 0;
      }

      this.updateSelectedCount();
    },

    updateSelectedCount() {
      const posts = PostState.getFiltered();
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

      const btnDiscard = document.getElementById("btn-bulk-discard");
      if (btnDiscard) {
        btnDiscard.disabled = n === 0;
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

    renderValidationAlert(pastCount, placeholderCount, limitExceededCount) {
      const alertContainer = document.getElementById("validation-alert-container");
      if (!alertContainer) return;

      if (pastCount > 0 || placeholderCount > 0 || limitExceededCount > 0) {
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
        if (limitExceededCount > 0) {
          parts.push(`${limitExceededCount} post(s) exceeding platform character limits`);
        }

        alertDiv.appendChild(document.createTextNode(parts.join(", ") + ". Review highlighted rows before exporting."));
        alertContainer.textContent = "";
        alertContainer.appendChild(alertDiv);
        alertContainer.classList.remove("hidden");
      } else {
        alertContainer.classList.add("hidden");
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
          post_time: post.original_post_time,
          is_saved: false
        });
        this.updateRow(id);
        AppController.triggerValidation();
        APIClient.savePostToDB(post);
        this.showToast("Reverted post timing to default.", "success");
      }
    },

    ensureScheduleControls(id) {
      const row = document.querySelector(`tr[data-post-id="${id}"]`);
      if (!row) return;
      const wrap = row.querySelector(".post-schedule-cell-wrap");
      if (!wrap) return;

      const post = PostState.get(id);
      if (!post) return;

      const isDateModified = post.post_date !== post.original_post_date;
      const isTimeModified = post.post_time !== post.original_post_time;
      const isUnsaved = post.is_saved === false;

      let modLabel = wrap.querySelector(".is-modified-label");
      let saveBtn = wrap.querySelector(".btn-save-time");
      let revBtn = wrap.querySelector(".btn-revert-time");

      if (isDateModified || isTimeModified || isUnsaved) {
        if (!modLabel) {
          modLabel = document.createElement("div");
          modLabel.className = "is-modified-label";
          wrap.appendChild(modLabel);
        }
        modLabel.textContent = isUnsaved ? "Unsaved changes" : "Modified";

        if (isUnsaved) {
          if (!saveBtn) {
            saveBtn = document.createElement("button");
            saveBtn.className = "btn-save-time";
            saveBtn.dataset.postId = id;
            saveBtn.type = "button";
            saveBtn.title = "Save schedule time to database";
            this.setWithIcon(saveBtn, "Save Schedule", "fa fa-check");
            if (revBtn) {
              wrap.insertBefore(saveBtn, revBtn);
            } else {
              wrap.appendChild(saveBtn);
            }
          }
        } else {
          if (saveBtn) saveBtn.remove();
        }

        if (isDateModified || isTimeModified) {
          if (!revBtn) {
            revBtn = document.createElement("button");
            revBtn.className = "btn-revert-time";
            revBtn.dataset.postId = id;
            revBtn.type = "button";
            revBtn.title = "Revert to default timing";
            this.setWithIcon(revBtn, "", "fa fa-undo");
            wrap.appendChild(revBtn);
          }
        } else {
          if (revBtn) revBtn.remove();
        }
      } else {
        if (modLabel) modLabel.remove();
        if (saveBtn) saveBtn.remove();
        if (revBtn) revBtn.remove();
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
      initTemplatesPage();
      if (Config.PREVIEW_URL) {
        this.loadInitialData();
      }
    },

    loadInitialData(force = false) {
      const btn = document.getElementById("btn-regenerate");
      if (btn) {
        btn.disabled = true;
        UI.setWithIcon(btn, "Loading…", "fa fa-refresh fa-spin");
      }
      UI.showSkeleton();

      APIClient.fetchPreview(force)
        .then(data => {
          const incoming = data.posts || [];
          const hasGenerated = data.has_generated_posts !== false;

          const emptyStateEl = document.getElementById("sm-empty-setup-state");
          const mainContentEl = document.getElementById("sm-posts-main-content");

          if (!hasGenerated || (incoming.length === 0 && !force)) {
            PostState.init([]);
            if (emptyStateEl && mainContentEl) {
              emptyStateEl.style.display = "block";
              mainContentEl.style.display = "none";
            }
            UI.updateCounts();
            return;
          }

          if (emptyStateEl && mainContentEl) {
            emptyStateEl.style.display = "none";
            mainContentEl.style.display = "block";
          }

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
            td.colSpan = 7;

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

    generatePosts() {
      const btn = document.getElementById("btn-initial-generate") || document.getElementById("btn-regenerate");
      if (btn) {
        btn.disabled = true;
        UI.setWithIcon(btn, "Generating…", "fa fa-spinner fa-spin");
      }
      APIClient.generatePosts()
        .then(res => {
          UI.showToast(res.message || "Posts generated successfully!", "success");
          this.loadInitialData(true);
        })
        .catch(err => {
          UI.showToast("Post generation failed: " + err.message, "warning");
        })
        .finally(() => {
          if (btn) {
            btn.disabled = false;
            if (btn.id === "btn-initial-generate") {
              UI.setWithIcon(btn, "Generate Posts", "fa fa-magic");
            } else {
              UI.setWithIcon(btn, "Regenerate", "fa fa-refresh");
            }
          }
        });
    },

    bulkDiscard() {
      const selected = PostState.getFiltered().filter(p => p.enabled && p.status !== "excluded");
      if (!selected.length) {
        UI.showToast("Please select at least one post to discard.", "warning");
        return;
      }

      const dbIds = selected.map(p => p.db_id).filter(Boolean);
      const postIds = selected.map(p => p.id);

      APIClient.bulkAction("discard", { db_ids: dbIds, post_ids: postIds })
        .then(res => {
          if (res.success) {
            const previousStates = selected.map(p => ({ post: p, oldStatus: p.status }));
            selected.forEach(p => {
              p.status = "excluded";
              p.enabled = false;
            });
            UI.renderTable(PostState.getAll(), PostState.getFilter());
            UI.updateCounts();
            UI.showToast(
              `Discarded ${res.count || selected.length} post(s).`,
              "success",
              () => {
                previousStates.forEach(({ post, oldStatus }) => {
                  post.status = oldStatus;
                  APIClient.updatePostStatus(post, oldStatus);
                });
                UI.renderTable(PostState.getAll(), PostState.getFilter());
                UI.updateCounts();
                UI.showToast("Discard undone.", "success");
              }
            );
          } else {
            UI.showToast("Failed to discard posts: " + (res.error || "Unknown error"), "warning");
          }
        })
        .catch(err => {
          console.error("Bulk discard failed:", err);
          UI.showToast("Bulk discard error: " + err.message, "warning");
        });
    },

    bulkRetry(provider = null) {
      let failedPosts = PostState.getFiltered().filter(p => p.status === "failed");
      if (provider) {
        failedPosts = failedPosts.filter(p => p.platform === provider || (p.id && String(p.id).endsWith(`_${provider}`)));
      }
      if (!failedPosts.length) {
        UI.showToast(provider ? `No failed posts found on ${provider}.` : "No failed posts found in current view.", "info");
        return;
      }

      const dbIds = failedPosts.map(p => p.db_id).filter(Boolean);
      const postIds = failedPosts.map(p => p.id);

      APIClient.bulkAction("retry", { provider, db_ids: dbIds, post_ids: postIds })
        .then(res => {
          if (res.success) {
            failedPosts.forEach(p => {
              p.status = "scheduled";
              p.error_message = "";
            });
            UI.renderTable(PostState.getAll(), PostState.getFilter());
            UI.updateCounts();
            UI.showToast(`Re-queued ${res.count || failedPosts.length} failed post(s).`, "success");
          } else {
            UI.showToast("Failed to retry posts: " + (res.error || "Unknown error"), "warning");
          }
        })
        .catch(err => {
          console.error("Bulk retry failed:", err);
          UI.showToast("Bulk retry error: " + err.message, "warning");
        });
    },

    triggerValidation() {
      const { pastCount, placeholderCount, limitExceededCount } = PostState.validate();
      UI.renderValidationAlert(pastCount, placeholderCount, limitExceededCount);
    },

    saveAndRegenerate(e) {
      e.preventDefault();
      const btn = document.getElementById("btn-save-regenerate");
      if (!btn) return;
      btn.disabled = true;
      UI.setWithIcon(btn, "Saving…", "fa fa-refresh fa-spin");

      const form = btn.closest("form");
      const formData = new FormData(form);

      APIClient.saveSettings(formData)
        .then(() => {
          UI.showToast("Settings saved successfully.", "success");
          this.loadInitialData(true);
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

      const presetSelect = document.getElementById("export-preset-select");
      const exportFormat = presetSelect ? presetSelect.value : "generic";

      APIClient.exportCSV(enabledVisiblePosts, exportFormat)
        .then(blob => {
          const url = URL.createObjectURL(blob);
          const a = document.createElement("a");
          a.href = url;
          a.download = `socialmedia_posts_${exportFormat}.csv`;
          document.body.appendChild(a);
          a.click();
          a.remove();
          URL.revokeObjectURL(url);

          UI.showToast(`Successfully exported ${enabledVisiblePosts.length} post(s).`, "success");
        })
        .catch(err => UI.showToast(`Export error: ${err.message}`, "warning"));
    },

    publishPostNow(postId, dbId, button) {
      if (button) {
        button.disabled = true;
        button.title = "Publishing...";
        const icon = button.querySelector("i");
        if (icon) {
          icon.className = "fa fa-spinner fa-spin";
        }
      }

      APIClient.publishPostNow(dbId, postId)
        .then(res => {
          UI.showToast(res.message || "Post published successfully!", "success");
          PostState.update(postId, {
            status: res.status || "published",
            error_message: ""
          });
          UI.renderTable(PostState.getAll(), PostState.getFilter());
          UI.updateCounts();
        })
        .catch(err => {
          UI.showToast(`Publishing failed: ${err.message}`, "warning");
          PostState.update(postId, {
            status: "failed",
            error_message: err.message
          });
          UI.renderTable(PostState.getAll(), PostState.getFilter());
          UI.updateCounts();
        })
        .finally(() => {
          if (button) {
            button.disabled = false;
            button.title = "Publish now";
            const icon = button.querySelector("i");
            if (icon) {
              icon.className = "fa fa-paper-plane";
            }
          }
        });
    },

    bindEvents() {
      const btnRegen = document.getElementById("btn-regenerate");
      if (btnRegen) btnRegen.addEventListener("click", () => this.generatePosts());

      const btnInitGen = document.getElementById("btn-initial-generate");
      if (btnInitGen) btnInitGen.addEventListener("click", () => this.generatePosts());

      const filterPills = document.getElementById("filter-pills");
      if (filterPills) {
        filterPills.addEventListener("click", (e) => {
          const btn = e.target.closest(".sm-filter-btn");
          if (btn) {
            PostState.setFilter(btn.dataset.type);
            document.querySelectorAll(".sm-filter-btn").forEach(b => b.classList.remove("active"));
            btn.classList.add("active");
            UI.renderTable(PostState.getAll(), PostState.getFilter());
            UI.updateCounts();
            this.triggerValidation();
          }
        });
      }

      const statusPills = document.getElementById("status-filter-pills");
      if (statusPills) {
        statusPills.addEventListener("click", (e) => {
          const btn = e.target.closest(".sm-status-btn");
          if (btn) {
            PostState.setStatusFilter(btn.dataset.status);
            document.querySelectorAll(".sm-status-btn").forEach(b => b.classList.remove("active"));
            btn.classList.add("active");
            UI.renderTable(PostState.getAll(), PostState.getFilter());
            UI.updateCounts();
            this.triggerValidation();
          }
        });
      }

      const btnBulkDiscard = document.getElementById("btn-bulk-discard");
      if (btnBulkDiscard) {
        btnBulkDiscard.addEventListener("click", () => this.bulkDiscard());
      }

      const btnBulkRetry = document.getElementById("btn-bulk-retry");
      if (btnBulkRetry) {
        btnBulkRetry.addEventListener("click", () => this.bulkRetry());
      }

      document.querySelectorAll(".retry-platform-link").forEach(link => {
        link.addEventListener("click", (e) => {
          e.preventDefault();
          const plat = link.dataset.platform || null;
          this.bulkRetry(plat);
        });
      });

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
          customInputs.style.display = this.value === "custom" ? "inline-flex" : "none";
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
          } else if (e.target.closest(".btn-save-time")) {
            const btn = e.target.closest(".btn-save-time");
            const post = PostState.get(postId);
            if (post) {
              APIClient.savePostToDB(post, btn);
            }
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
          } else if (e.target.closest(".btn-preview-post")) {
            const post = PostState.get(postId);
            if (post) {
              UI.openPreviewModal(post);
            }
          } else if (e.target.closest(".btn-publish-now")) {
            const btn = e.target.closest(".btn-publish-now");
            const dbId = btn.dataset.dbId;
            this.publishPostNow(postId, dbId, btn);
          }
        });

        tbody.addEventListener("change", (e) => {
          const postId = e.target.dataset.postId;
          if (!postId) return;

          if (e.target.classList.contains("row-chk")) {
            UI.toggleRow(postId, e.target.checked);
          } else if (e.target.classList.contains("sm-date-input")) {
            PostState.update(postId, { post_date: e.target.value, is_saved: false });
            e.target.classList.add("is-modified");
            UI.ensureScheduleControls(postId);
            this.triggerValidation();
          } else if (e.target.classList.contains("sm-time-input")) {
            PostState.update(postId, { post_time: e.target.value, is_saved: false });
            e.target.classList.add("is-modified");
            UI.ensureScheduleControls(postId);
            this.triggerValidation();
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
              if (countSpan) {
                const post = PostState.get(postId);
                const limit = PLATFORM_LIMITS[post.platform] || null;
                if (limit) {
                  countSpan.textContent = `${e.target.value.length} / ${limit}`;
                  if (e.target.value.length > limit) {
                    countSpan.classList.add("has-warning");
                    e.target.classList.add("has-error");
                  } else {
                    countSpan.classList.remove("has-warning");
                    e.target.classList.remove("has-error");
                  }
                } else {
                  countSpan.textContent = e.target.value.length;
                }
              }
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
    }
  };

  // Track last focused input for token chip insertion
  let lastFocusedInput = null;
  document.addEventListener("focusin", (e) => {
    if (e.target && (e.target.tagName === "INPUT" || e.target.tagName === "TEXTAREA")) {
      lastFocusedInput = e.target;
    }
  });

  // ---- Token & Preset UI Helpers ----
  function insertToken(chip) {
    const targetId = chip.dataset.target;
    const token = chip.textContent.trim();
    let input = lastFocusedInput;
    if (!input || !document.body.contains(input)) {
      input = targetId ? document.getElementById(targetId) : null;
    }
    if (!input && targetId) {
      input = document.getElementById(targetId);
    }
    if (!input) {
      const parentCard = chip.closest(".template-group, .adv-group, .custom-templates-panel");
      if (parentCard) {
        input = parentCard.querySelector("textarea, input[type='text']");
      }
    }
    if (!input) return;

    const value = input.value || "";
    let startPos = typeof input.selectionStart === "number" ? input.selectionStart : value.length;
    let endPos = typeof input.selectionEnd === "number" ? input.selectionEnd : value.length;
    if (startPos < 0) startPos = value.length;
    if (endPos < 0) endPos = value.length;

    input.value = value.substring(0, startPos) + token + value.substring(endPos);

    input.focus();
    try {
      input.selectionStart = startPos + token.length;
      input.selectionEnd = startPos + token.length;
    } catch (err) {
      if (!(err instanceof DOMException)) {
        console.warn("Failed to set input selection position:", err);
      }
    }

    input.dispatchEvent(new Event("input", { bubbles: true }));
    input.dispatchEvent(new Event("change", { bubbles: true }));
  }

  function handlePresetClick(btn) {
    const container = btn.closest(".presets-container");
    if (!container) return;

    const targetId = container.dataset.target;
    const val = parseInt(btn.dataset.val, 10);
    const input = document.getElementById(targetId);
    if (!input || isNaN(val)) return;

    let offsets = (input.value || "")
      .split(",")
      .map(x => parseInt(x.trim(), 10))
      .filter(x => !isNaN(x));

    const idx = offsets.indexOf(val);
    if (idx > -1) {
      offsets.splice(idx, 1);
    } else {
      offsets.push(val);
    }

    offsets.sort((a, b) => b - a);
    input.value = offsets.join(", ");

    input.dispatchEvent(new Event("input", { bubbles: true }));
    input.dispatchEvent(new Event("change", { bubbles: true }));
  }

  // Document-level event delegation for token chips & preset buttons (single listener)
  document.addEventListener("click", (e) => {
    const chip = e.target.closest(".token-chip");
    if (chip) {
      e.preventDefault();
      insertToken(chip);
      return;
    }
    const presetBtn = e.target.closest(".presets-container .preset-btn");
    if (presetBtn) {
      e.preventDefault();
      handlePresetClick(presetBtn);
      return;
    }
  });


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

    // Platform toggle: show/hide per-platform template fields
    const platformKeys = ["twitter", "mastodon", "telegram", "linkedin"];
    platformKeys.forEach(platform => {
      const checkbox = document.getElementById(`id_socialmedia_${platform}_enabled`);
      const tplBlock = document.getElementById(`plat-tpls-${platform}`);
      if (!checkbox || !tplBlock) return;

      const syncVisibility = () => {
        tplBlock.classList.toggle("hidden", !checkbox.checked);
      };
      syncVisibility();
      checkbox.addEventListener("change", syncVisibility);
    });
  }

  function initTemplatesPage() {
    // Accordion toggle
    document.querySelectorAll(".toggle-custom-tpl-btn").forEach(btn => {
      btn.addEventListener("click", function () {
        const targetSelector = this.dataset.target;
        const panel = document.querySelector(targetSelector);
        if (panel) {
          panel.classList.toggle("active");
        }
      });
    });

    // Copy to other platforms
    document.querySelectorAll(".btn-copy-plat").forEach(btn => {
      btn.addEventListener("click", function () {
        const srcId = this.dataset.src;
        const srcInput = document.getElementById(srcId);
        if (!srcInput) return;
        const text = srcInput.value;

        const panel = this.closest(".custom-templates-panel");
        if (panel) {
          panel.querySelectorAll("textarea").forEach(ta => {
            if (ta !== srcInput) {
              ta.value = text;
              const evt = document.createEvent("HTMLEvents");
              evt.initEvent("input", true, true);
              ta.dispatchEvent(evt);
            }
          });
          UI.showToast("Copied template copy to other platforms.", "info");
        }
      });
    });

    // Reset to default
    document.querySelectorAll(".reset-default-btn").forEach(btn => {
      btn.addEventListener("click", function () {
        const type = this.dataset.type;
        const panel = document.getElementById(`custom-tpls-${type}`);
        if (panel) {
          panel.querySelectorAll("textarea").forEach(ta => {
            ta.value = "";
            const evt = document.createEvent("HTMLEvents");
            evt.initEvent("input", true, true);
            ta.dispatchEvent(evt);
          });
          UI.showToast("Reset templates to system default.", "info");
        }
      });
    });

    // Realtime character count bars
    document.querySelectorAll(".char-count-bar").forEach(bar => {
      const targetId = bar.dataset.target;
      const limit = parseInt(bar.dataset.limit, 10);
      const input = document.getElementById(targetId);
      if (!input || isNaN(limit)) return;

      const updateBar = () => {
        const len = input.value.length;
        bar.textContent = `${len} / ${limit} chars`;
        if (len > limit) {
          bar.classList.add("has-error");
        } else {
          bar.classList.remove("has-error");
        }
      };
      input.addEventListener("input", updateBar);
      updateBar();
    });

    // Custom Waves Dynamic Handler
    const serializeCustomWaves = (type) => {
      const container = document.getElementById(`custom-waves-list-${type}`);
      const hiddenInput = document.getElementById(`id_socialmedia_${type}_custom_waves`);
      if (!container || !hiddenInput) return;

      const waves = [];
      container.querySelectorAll(".wave-card-custom").forEach(card => {
        const enabled = card.querySelector(".custom-wave-enable")?.checked ?? true;
        const label = card.querySelector(".custom-wave-label")?.value?.trim() || "Custom Wave";
        const offset = parseInt(card.querySelector(".custom-wave-offset")?.value, 10);
        const template = card.querySelector(".custom-wave-template")?.value || "";
        if (!isNaN(offset)) {
          waves.push({
            id: card.dataset.waveId || `wave_${Date.now()}_${Math.random().toString(36).substr(2, 4)}`,
            label: label,
            offset: offset,
            enabled: enabled,
            template: template
          });
        }
      });
      hiddenInput.value = JSON.stringify(waves);
    };

    document.querySelectorAll(".btn-add-custom-wave").forEach(btn => {
      btn.addEventListener("click", function () {
        const type = this.dataset.type;
        const unitLabel = this.dataset.unit || "Days before milestone:";
        const container = document.getElementById(`custom-waves-list-${type}`);
        if (!container) return;

        const waveId = `wave_custom_${Date.now()}`;
        const newCard = document.createElement("div");
        newCard.className = "wave-card wave-card-custom";
        newCard.dataset.waveId = waveId;
        newCard.innerHTML = `
          <div class="wave-card-header">
            <div class="wave-toggle-wrap">
              <input type="checkbox" class="custom-wave-enable" checked>
              <span class="wave-badge wave-custom-badge"><i class="fa fa-sparkles"></i> Custom Wave:</span>
              <input type="text" class="form-control input-sm custom-wave-label" value="Custom Wave" placeholder="e.g. Early Call" style="width: 150px; display: inline-block; height: 26px; padding: 2px 6px;">
            </div>
            <div class="wave-offset-wrap">
              <span class="wave-offset-label">${unitLabel}</span>
              <input type="number" class="form-control input-sm custom-wave-offset" value="15" style="width: 70px; height: 28px; text-align: center;">
              <button type="button" class="btn btn-danger btn-xs btn-remove-wave" title="Remove this wave">
                <i class="fa fa-trash"></i>
              </button>
            </div>
          </div>
          <div class="wave-card-body">
            <div class="wave-custom-input">
              <label class="small text-muted">Custom Wave Copy:</label>
              <textarea class="form-control custom-wave-template" rows="2" placeholder="Write custom copy for this wave..."></textarea>
            </div>
          </div>
        `;
        container.appendChild(newCard);
        serializeCustomWaves(type);
      });
    });

    document.addEventListener("click", function (e) {
      const rmBtn = e.target.closest(".btn-remove-wave");
      if (rmBtn) {
        const card = rmBtn.closest(".wave-card-custom");
        const container = card?.closest(".custom-waves-list");
        if (card && container) {
          const type = container.id.replace("custom-waves-list-", "");
          card.remove();
          serializeCustomWaves(type);
        }
      }
    });

    document.addEventListener("input", function (e) {
      const customCard = e.target.closest(".wave-card-custom");
      if (customCard) {
        const container = customCard.closest(".custom-waves-list");
        if (container) {
          const type = container.id.replace("custom-waves-list-", "");
          serializeCustomWaves(type);
        }
      }
    });

    document.addEventListener("change", function (e) {
      const customCard = e.target.closest(".wave-card-custom");
      if (customCard) {
        const container = customCard.closest(".custom-waves-list");
        if (container) {
          const type = container.id.replace("custom-waves-list-", "");
          serializeCustomWaves(type);
        }
      }
    });

    // Form submission serialization
    const form = document.querySelector(".sm-templates-form");
    if (form) {
      form.addEventListener("submit", () => {
        ["cfp", "speaker", "session", "ticket", "schedule"].forEach(t => serializeCustomWaves(t));
      });
    }

    ["cfp", "speaker", "session", "ticket", "schedule"].forEach(t => serializeCustomWaves(t));
  }


  // Run on load
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", () => AppController.init());
  } else {
    AppController.init();
  }
})();
