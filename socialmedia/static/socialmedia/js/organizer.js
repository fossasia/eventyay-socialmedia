(function () {
  "use strict";

  // ---- Config module ----
  var Config = (function () {
    var configEl = document.getElementById("socialmedia-organizer-config");
    if (!configEl) return {};
    try {
      return JSON.parse(configEl.textContent);
    } catch (e) {
      return {};
    }
  })();

  // ---- Test connection module ----
  function initTestConnection() {
    var btn = document.getElementById("test-connection-btn");
    if (!btn || !Config.testUrl) return;

    btn.addEventListener("click", function () {
      var resultDiv = document.getElementById("test-connection-result");
      btn.disabled = true;
      btn.innerHTML = '<i class="fa fa-spinner fa-spin"></i> ' + (Config.transTesting || "Testing...");
      if (resultDiv) resultDiv.style.display = "none";

      var xhr = new XMLHttpRequest();
      xhr.open("POST", Config.testUrl);
      if (Config.csrfToken) {
        xhr.setRequestHeader("X-CSRFToken", Config.csrfToken);
      }
      xhr.setRequestHeader("Content-Type", "application/json");

      xhr.onload = function () {
        var data;
        try {
          data = JSON.parse(xhr.responseText);
        } catch (e) {
          data = { success: false, message: Config.transServerError || "An unexpected server error occurred." };
        }
        if (resultDiv) {
          resultDiv.style.display = "block";
          if (xhr.status === 200 && data.success) {
            resultDiv.innerHTML = '<div class="alert alert-success"><i class="fa fa-check-circle"></i> ' + data.message + "</div>";
          } else {
            resultDiv.innerHTML = '<div class="alert alert-danger"><i class="fa fa-times-circle"></i> ' + data.message + "</div>";
          }
        }
        btn.disabled = false;
        btn.innerHTML = '<i class="fa fa-plug"></i> ' + (Config.transTestConnection || "Test Connection");
      };

      xhr.onerror = function () {
        if (resultDiv) {
          resultDiv.style.display = "block";
          resultDiv.innerHTML = '<div class="alert alert-danger"><i class="fa fa-times-circle"></i> ' + (Config.transNetworkError || "Network error. Please try again.") + "</div>";
        }
        btn.disabled = false;
        btn.innerHTML = '<i class="fa fa-plug"></i> ' + (Config.transTestConnection || "Test Connection");
      };

      xhr.send(JSON.stringify({}));
    });
  }

  // ---- Interactive OAuth URL builder module ----
  function initOAuthUrlBuilder() {
    var clientIdInput = document.getElementById("id_client_id");
    var instructionItems = document.querySelectorAll(".sm-setup-instructions-item");

    instructionItems.forEach(function (item) {
      var text = item.textContent || item.innerText;
      if (text.indexOf("https://www.linkedin.com/oauth/v2/authorization") !== -1 || text.indexOf("YOUR_CLIENT_ID") !== -1) {
        var box = document.createElement("div");
        box.className = "sm-oauth-url-box";

        var hint = document.createElement("div");
        hint.style.fontSize = "12px";
        hint.style.marginBottom = "6px";
        hint.style.color = "#555";
        hint.textContent = Config.transAuthPasteHint || "Paste your Client ID in the form above to generate your custom link:";

        var codeEl = document.createElement("code");
        codeEl.className = "sm-oauth-url-text";

        var orgScopeLabel = document.createElement("label");
        orgScopeLabel.style.fontSize = "12px";
        orgScopeLabel.style.fontWeight = "normal";
        orgScopeLabel.style.display = "block";
        orgScopeLabel.style.marginBottom = "8px";
        orgScopeLabel.style.cursor = "pointer";

        var orgScopeCheckbox = document.createElement("input");
        orgScopeCheckbox.type = "checkbox";
        orgScopeCheckbox.style.marginRight = "6px";

        orgScopeLabel.appendChild(orgScopeCheckbox);
        orgScopeLabel.appendChild(document.createTextNode(" " + (Config.transCompanyScopeOption || "Include Company Page scope (w_organization_social) - only if approved on your app")));

        var actions = document.createElement("div");
        actions.className = "sm-oauth-url-actions";

        var copyBtn = document.createElement("button");
        copyBtn.type = "button";
        copyBtn.className = "btn btn-default btn-xs";
        copyBtn.innerHTML = '<i class="fa fa-copy"></i> ' + (Config.transCopyUrl || "Copy URL");

        var openBtn = document.createElement("a");
        openBtn.target = "_blank";
        openBtn.rel = "noopener noreferrer";
        openBtn.className = "btn btn-primary btn-xs";
        openBtn.innerHTML = '<i class="fa fa-external-link"></i> ' + (Config.transOpenAuth || "Open Authorization Page");

        actions.appendChild(copyBtn);
        actions.appendChild(openBtn);
        box.appendChild(hint);
        box.appendChild(codeEl);
        box.appendChild(orgScopeLabel);
        box.appendChild(actions);

        function updateUrl() {
          var val = clientIdInput ? clientIdInput.value.trim() : "";
          var resolvedId = val || "YOUR_CLIENT_ID";
          var scopes = "w_member_social%20openid%20profile";
          if (orgScopeCheckbox.checked) {
            scopes += "%20w_organization_social";
          }
          var fullUrl = "https://www.linkedin.com/oauth/v2/authorization?response_type=code&client_id=" +
            encodeURIComponent(resolvedId) +
            "&redirect_uri=https://localhost&scope=" +
            scopes;
          codeEl.textContent = fullUrl;

          if (val) {
            openBtn.href = fullUrl;
            openBtn.classList.remove("disabled");
            openBtn.removeAttribute("aria-disabled");
            hint.textContent = Config.transAuthReady || "Your custom authorization link is ready:";
          } else {
            openBtn.href = "#";
            openBtn.classList.add("disabled");
            openBtn.setAttribute("aria-disabled", "true");
            hint.textContent = Config.transAuthPasteHint || "Paste your Client ID in the form above to generate your custom link:";
          }
        }

        orgScopeCheckbox.addEventListener("change", updateUrl);

        copyBtn.addEventListener("click", function () {
          var textToCopy = codeEl.textContent;
          var onCopied = function () {
            copyBtn.innerHTML = '<i class="fa fa-check text-success"></i> ' + (Config.transCopied || "Copied!");
            setTimeout(function () {
              copyBtn.innerHTML = '<i class="fa fa-copy"></i> ' + (Config.transCopyUrl || "Copy URL");
            }, 2000);
          };

          if (navigator.clipboard && navigator.clipboard.writeText) {
            navigator.clipboard.writeText(textToCopy).then(onCopied);
          } else {
            var textarea = document.createElement("textarea");
            textarea.value = textToCopy;
            document.body.appendChild(textarea);
            textarea.select();
            document.execCommand("copy");
            document.body.removeChild(textarea);
            onCopied();
          }
        });

        if (clientIdInput) {
          clientIdInput.addEventListener("input", updateUrl);
          clientIdInput.addEventListener("change", updateUrl);
        }

        item.innerHTML = "6. " + (Config.transAuthStepTitle || "Authorize your LinkedIn account using this link:");
        item.appendChild(box);
        updateUrl();
      }
    });
  }

  // Initialize on DOM ready
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () {
      initTestConnection();
      initOAuthUrlBuilder();
    });
  } else {
    initTestConnection();
    initOAuthUrlBuilder();
  }
})();
