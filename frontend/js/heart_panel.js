(function () {
  "use strict";

  function escapeHtml(value) {
    return String(value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function formatCell(value) {
    if (value === null || value === undefined) {
      return "";
    }
    return escapeHtml(value);
  }

  function rankingUrl() {
    var panel = document.getElementById("heart-panel");
    return (panel && panel.getAttribute("data-ranking-url")) || "/api/heart/ranking";
  }

  function setStatus(message, isError) {
    var statusEl = document.getElementById("heart-status");
    if (!statusEl) {
      return;
    }
    statusEl.textContent = message;
    statusEl.className = isError ? "heart-status heart-status--error" : "heart-status";
  }

  function renderRows(body) {
    var tbody = document.getElementById("heart-tbody");
    var emptyEl = document.getElementById("heart-empty");
    var tableEl = document.getElementById("heart-table");
    if (!tbody || !emptyEl || !tableEl) {
      return;
    }

    var rows = Array.isArray(body.rows) ? body.rows : [];
    if (rows.length === 0) {
      tbody.innerHTML = "";
      emptyEl.hidden = false;
      tableEl.hidden = true;
      var emptyParts = ["sem movimentos (livro vazio)"];
      if (body.path_id) {
        emptyParts.push("path_id: " + body.path_id);
      }
      if (body.path_status) {
        emptyParts.push("path_status: " + body.path_status);
      }
      emptyEl.textContent = emptyParts.join(" — ");
      setStatus("", false);
      return;
    }

    emptyEl.hidden = true;
    tableEl.hidden = false;
    tbody.innerHTML = rows
      .map(function (row) {
        var pathId = row.path_id != null ? row.path_id : body.path_id;
        var pathStatus = row.path_status != null ? row.path_status : body.path_status;
        return (
          "<tr>" +
          "<td>" + formatCell(row.symbol) + "</td>" +
          "<td>" + formatCell(row.session_date) + "</td>" +
          "<td>" + formatCell(row.gross_ret) + "</td>" +
          "<td>" + formatCell(pathId) + "</td>" +
          "<td>" + formatCell(pathStatus) + "</td>" +
          "</tr>"
        );
      })
      .join("");
    setStatus("rows: " + rows.length, false);
  }

  async function loadRanking() {
    setStatus("A carregar…", false);

    try {
      var response = await fetch(rankingUrl());
      if (!response.ok) {
        var errorText = await response.text();
        var message = "HTTP " + response.status;
        if (errorText) {
          message += ": " + errorText;
        }
        setStatus(message, true);
        return;
      }

      var body = await response.json();
      renderRows(body);
    } catch (err) {
      setStatus(String(err), true);
    }
  }

  document.addEventListener("DOMContentLoaded", loadRanking);
})();
