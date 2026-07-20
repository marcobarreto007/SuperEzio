/* SuperEzio — Auth Module (JWT login/register) */
(function () {
  "use strict";

  const STORAGE_KEY_TOKEN = "sz_access_token";
  const STORAGE_KEY_REFRESH = "sz_refresh_token";
  const STORAGE_KEY_USER = "sz_user";
  const API = location.protocol === "file:" ? "http://127.0.0.1:8002" : "";

  // ── Token helpers ──

  function getToken() {
    return localStorage.getItem(STORAGE_KEY_TOKEN);
  }

  function getRefreshToken() {
    return localStorage.getItem(STORAGE_KEY_REFRESH);
  }

  function saveTokens(access, refresh) {
    localStorage.setItem(STORAGE_KEY_TOKEN, access);
    if (refresh) localStorage.setItem(STORAGE_KEY_REFRESH, refresh);
  }

  function clearTokens() {
    localStorage.removeItem(STORAGE_KEY_TOKEN);
    localStorage.removeItem(STORAGE_KEY_REFRESH);
    localStorage.removeItem(STORAGE_KEY_USER);
  }

  function isAuthenticated() {
    const token = getToken();
    if (!token) return false;
    try {
      const payload = JSON.parse(atob(token.split(".")[1]));
      const now = Math.floor(Date.now() / 1000);
      return payload.exp > now;
    } catch {
      return false;
    }
  }

  function getTokenExpiry() {
    const token = getToken();
    if (!token) return 0;
    try {
      const payload = JSON.parse(atob(token.split(".")[1]));
      return payload.exp || 0;
    } catch {
      return 0;
    }
  }

  // ── API calls ──

  async function login(username, password) {
    const r = await fetch(API + "/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password }),
    });
    if (!r.ok) {
      const data = await r.json().catch(() => ({}));
      throw new Error(data.detail || `Login failed (${r.status})`);
    }
    const data = await r.json();
    saveTokens(data.access_token, data.refresh_token);
    localStorage.setItem(STORAGE_KEY_USER, JSON.stringify({ username }));
    return data;
  }

  async function register(username, email, password) {
    const r = await fetch(API + "/auth/register", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, email, password }),
    });
    if (!r.ok) {
      const data = await r.json().catch(() => ({}));
      throw new Error(data.detail || `Registration failed (${r.status})`);
    }
    const data = await r.json();
    saveTokens(data.access_token, data.refresh_token);
    localStorage.setItem(STORAGE_KEY_USER, JSON.stringify({ username }));
    return data;
  }

  async function refreshToken() {
    const refresh = getRefreshToken();
    if (!refresh) return null;
    try {
      const r = await fetch(API + "/auth/refresh", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh_token: refresh }),
      });
      if (!r.ok) throw new Error("refresh failed");
      const data = await r.json();
      saveTokens(data.access_token, data.refresh_token || refresh);
      return data.access_token;
    } catch {
      return null;
    }
  }

  function logout() {
    clearTokens();
    showLogin();
  }

  // ── Modal UI ──

  let modalEl = null;
  let refreshInterval = null;

  const MODAL_HTML = `
    <div id="auth-modal-overlay" class="auth-overlay">
      <div class="auth-modal">
        <div class="auth-modal-header">
          <div class="auth-logo">
            <span class="auth-logo-mark">F51</span>
            <span class="auth-logo-text">SUPEREZIO</span>
          </div>
          <p class="auth-tagline">AI Financial Copilot</p>
        </div>

        <div class="auth-tabs">
          <button class="auth-tab auth-tab--active" data-auth-tab="login">Sign In</button>
          <button class="auth-tab" data-auth-tab="register">Create Account</button>
        </div>

        <!-- Login Form -->
        <form class="auth-form" id="auth-form-login">
          <div class="auth-field">
            <label for="auth-login-username">Username</label>
            <input id="auth-login-username" type="text" autocomplete="username" placeholder="Enter your username" required>
          </div>
          <div class="auth-field">
            <label for="auth-login-password">Password</label>
            <input id="auth-login-password" type="password" autocomplete="current-password" placeholder="Enter your password" required>
          </div>
          <div class="auth-error" id="auth-error-login"></div>
          <button class="auth-submit" type="submit">Sign In</button>
        </form>

        <!-- Register Form -->
        <form class="auth-form auth-form--hidden" id="auth-form-register">
          <div class="auth-field">
            <label for="auth-reg-username">Username</label>
            <input id="auth-reg-username" type="text" autocomplete="username" placeholder="Choose a username" required>
          </div>
          <div class="auth-field">
            <label for="auth-reg-email">Email</label>
            <input id="auth-reg-email" type="email" autocomplete="email" placeholder="your@email.com" required>
          </div>
          <div class="auth-field">
            <label for="auth-reg-password">Password</label>
            <input id="auth-reg-password" type="password" autocomplete="new-password" placeholder="Create a password (min 6 chars)" required minlength="6">
          </div>
          <div class="auth-error" id="auth-error-register"></div>
          <button class="auth-submit" type="submit">Create Account</button>
        </form>

        <div class="auth-footer">
          <span class="auth-footer-line"></span>
        </div>
      </div>
    </div>
  `;

  function injectModal() {
    if (document.getElementById("auth-modal-overlay")) return;
    const container = document.getElementById("auth-modal");
    if (!container) return;
    container.innerHTML = MODAL_HTML;
    modalEl = document.getElementById("auth-modal-overlay");
    bindEvents();
  }

  function bindEvents() {
    // Tab switching
    document.querySelectorAll("[data-auth-tab]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var tab = btn.dataset.authTab;
        document.querySelectorAll(".auth-tab").forEach(function (t) {
          t.classList.remove("auth-tab--active");
        });
        btn.classList.add("auth-tab--active");
        document.querySelectorAll(".auth-form").forEach(function (f) {
          f.classList.add("auth-form--hidden");
        });
        document.getElementById("auth-form-" + tab).classList.remove("auth-form--hidden");
        document.querySelectorAll(".auth-error").forEach(function (e) {
          e.textContent = "";
        });
      });
    });

    // Login submit
    var loginForm = document.getElementById("auth-form-login");
    if (loginForm) {
      loginForm.addEventListener("submit", async function (e) {
        e.preventDefault();
        var username = document.getElementById("auth-login-username").value.trim();
        var password = document.getElementById("auth-login-password").value;
        var errEl = document.getElementById("auth-error-login");
        errEl.textContent = "";
        var submitBtn = e.target.querySelector(".auth-submit");
        submitBtn.disabled = true;
        submitBtn.textContent = "Signing in...";
        try {
          await login(username, password);
          hideModal();
          window.dispatchEvent(new CustomEvent("auth:login"));
        } catch (err) {
          errEl.textContent = err.message;
        } finally {
          submitBtn.disabled = false;
          submitBtn.textContent = "Sign In";
        }
      });
    }

    // Register submit
    var regForm = document.getElementById("auth-form-register");
    if (regForm) {
      regForm.addEventListener("submit", async function (e) {
        e.preventDefault();
        var username = document.getElementById("auth-reg-username").value.trim();
        var email = document.getElementById("auth-reg-email").value.trim();
        var password = document.getElementById("auth-reg-password").value;
        var errEl = document.getElementById("auth-error-register");
        errEl.textContent = "";
        var submitBtn = e.target.querySelector(".auth-submit");
        submitBtn.disabled = true;
        submitBtn.textContent = "Creating...";
        try {
          await register(username, email, password);
          hideModal();
          window.dispatchEvent(new CustomEvent("auth:login"));
        } catch (err) {
          errEl.textContent = err.message;
        } finally {
          submitBtn.disabled = false;
          submitBtn.textContent = "Create Account";
        }
      });
    }
  }

  function showLogin() {
    injectModal();
    if (modalEl) modalEl.classList.add("auth-overlay--visible");
    // Switch to login tab
    var loginTab = document.querySelector('[data-auth-tab="login"]');
    if (loginTab) loginTab.click();
  }

  function hideModal() {
    if (modalEl) modalEl.classList.remove("auth-overlay--visible");
  }

  function startRefreshTimer() {
    stopRefreshTimer();
    refreshInterval = setInterval(async function () {
      if (!isAuthenticated()) return;
      var exp = getTokenExpiry();
      var now = Math.floor(Date.now() / 1000);
      // Refresh 5 minutes before expiry
      if (exp - now < 300) {
        var ok = await refreshToken();
        if (!ok) {
          clearTokens();
          showLogin();
        }
      }
    }, 60000); // Check every minute
  }

  function stopRefreshTimer() {
    if (refreshInterval) {
      clearInterval(refreshInterval);
      refreshInterval = null;
    }
  }

  // ── Init ──

  function init() {
    injectModal();

    if (isAuthenticated()) {
      startRefreshTimer();
      return;
    }

    // Try refresh once
    refreshToken().then(function (token) {
      if (token) {
        startRefreshTimer();
        return;
      }

      // Dev mode detection: call a real auth-gated endpoint to check if auth is required.
      // /health returns 200 even with JWT_SECRET set, so we use a protected route.
      fetch(API + "/cockpit/summary")
        .then(function (r) {
          if (r.ok) {
            // Dev mode — server accepts requests without auth
            console.log("SuperEzio: dev mode detected, skipping login");
            return;
          }
          // 401 or other — production mode, needs login
          clearTokens();
          showLogin();
        })
        .catch(function () {
          // Server unreachable — show login anyway
          clearTokens();
          showLogin();
        });
    });
  }

  // ── getValidToken: returns current token if valid (not expired), else null ──

  function getValidToken() {
    if (!isAuthenticated()) return null;
    return getToken();
  }

  // ── Public API ──

  window.SZ = window.SZ || {};
  window.SZ.auth = {
    login: login,
    register: register,
    logout: logout,
    getToken: getToken,
    getRefreshToken: getRefreshToken,
    refreshToken: refreshToken,
    isAuthenticated: isAuthenticated,
    getValidToken: getValidToken,
    clearTokens: clearTokens,
    showLogin: showLogin,
    hideModal: hideModal,
    init: init,
  };

  // Auto-init
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
