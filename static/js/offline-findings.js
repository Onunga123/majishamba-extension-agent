(function () {
  "use strict";

  const DB_NAME = "kachieng-offline";
  const STORE_NAME = "pending-findings";
  const SYNC_URL = "/tasks/sync/findings/";
  let syncing = false;
  let submitting = false;

  function openDB() {
    return new Promise((resolve, reject) => {
      const request = indexedDB.open(DB_NAME, 1);

      request.onupgradeneeded = () => {
        const db = request.result;
        if (!db.objectStoreNames.contains(STORE_NAME)) {
          db.createObjectStore(STORE_NAME, { keyPath: "client_id" });
        }
      };

      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(request.error);
    });
  }

  async function storeRecord(record) {
    const db = await openDB();
    try {
      await new Promise((resolve, reject) => {
        const tx = db.transaction(STORE_NAME, "readwrite");
        tx.objectStore(STORE_NAME).put(record);
        tx.oncomplete = resolve;
        tx.onerror = () => reject(tx.error);
        tx.onabort = () => reject(tx.error);
      });
    } finally {
      db.close();
    }
  }

  async function getRecords() {
    const db = await openDB();
    try {
      return await new Promise((resolve, reject) => {
        const tx = db.transaction(STORE_NAME, "readonly");
        const request = tx.objectStore(STORE_NAME).getAll();
        request.onsuccess = () => resolve(request.result);
        request.onerror = () => reject(request.error);
      });
    } finally {
      db.close();
    }
  }

  async function removeRecord(clientId) {
    const db = await openDB();
    try {
      await new Promise((resolve, reject) => {
        const tx = db.transaction(STORE_NAME, "readwrite");
        tx.objectStore(STORE_NAME).delete(clientId);
        tx.oncomplete = resolve;
        tx.onerror = () => reject(tx.error);
        tx.onabort = () => reject(tx.error);
      });
    } finally {
      db.close();
    }
  }

  function makeId() {
    if (crypto.randomUUID) return crypto.randomUUID();

    return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, c => {
      const r = crypto.getRandomValues(new Uint8Array(1))[0] & 15;
      return (c === "x" ? r : (r & 3) | 8).toString(16);
    });
  }

  function showMessage(text, error) {
    let box = document.getElementById("offline-findings-status");

    if (!box) {
      box = document.createElement("div");
      box.id = "offline-findings-status";
      box.className = "rounded border p-3 text-sm mb-4";
      box.setAttribute("role", "status");
      box.setAttribute("aria-live", "polite");

      const form = document.querySelector('form[action*="/findings/"]');
      if (form) form.parentNode.insertBefore(box, form);
    }

    if (box) {
      box.textContent = text;
      box.style.borderColor = error ? "#b91c1c" : "#15803d";
    }
  }

  function readCookie(name) {
    const prefix = name + "=";
    const cookie = document.cookie.split(";").map(v => v.trim())
      .find(v => v.startsWith(prefix));
    return cookie ? decodeURIComponent(cookie.slice(prefix.length)) : "";
  }

  async function syncPending() {
    if (syncing || !navigator.onLine) return;
    syncing = true;

    try {
      const records = await getRecords();
      if (!records.length) return;

      const csrfToken = readCookie("csrftoken");
      if (!csrfToken) {
        showMessage(
          "Pending findings remain on this device. Sign in again when online to sync them.",
          true
        );
        return;
      }

      for (let i = 0; i < records.length; i += 20) {
        const batch = records.slice(i, i + 20);

        let response;
        try {
          response = await fetch(SYNC_URL, {
            method: "POST",
            credentials: "same-origin",
            headers: {
              "Content-Type": "application/json",
              "X-CSRFToken": csrfToken
            },
            body: JSON.stringify({ records: batch })
          });
        } catch (_) {
          showMessage(
            "Connection interrupted. Pending findings remain on this device.",
            true
          );
          return;
        }

        if (response.status === 403 || response.status === 401) {
          showMessage(
            "Sign-in or permission is required. Pending findings remain on this device.",
            true
          );
          return;
        }

        if (!response.ok) {
          showMessage(
            "Sync could not be confirmed. Pending findings remain on this device.",
            true
          );
          return;
        }

        const data = await response.json();

        for (const result of (data.results || [])) {
          if (result.status === "synced") {
            await removeRecord(result.client_id);
          }
        }

        const pending = await getRecords();
        if (pending.length) {
          showMessage(
            pending.length + " finding(s) still need attention or synchronisation.",
            true
          );
        } else {
          showMessage("All queued findings have been confirmed by the server.", false);
        }
      }
    } catch (error) {
      showMessage(
        "Could not access the local queue. Do not clear browser data; try again later.",
        true
      );
      console.error("Offline findings error:", error);
    } finally {
      syncing = false;
    }
  }

  async function initialise() {
    const form = document.querySelector('form[action*="/findings/"]');
    if (!form) return;

    window.addEventListener("online", syncPending);
    window.addEventListener("pageshow", syncPending);

    form.addEventListener("submit", async function (event) {
      // Always queue first, even when the browser reports online.

      event.preventDefault();

      if (!("indexedDB" in window)) {
        showMessage(
          "Offline storage is unavailable. Keep this page open and reconnect before submitting.",
          true
        );
        return;
      }

      if (submitting) return;
      submitting = true;

      const button = form.querySelector('button[type="submit"]');
      if (button) button.disabled = true;

      try {
        const formData = new FormData(form);
        const taskMatch = form.action.match(/\/tasks\/(\d+)\/findings\/?$/);

        if (!taskMatch) {
          throw new Error("Could not identify the task for this finding.");
        }

        const record = {
          client_id: makeId(),
          task_id: Number(taskMatch[1]),
          visit_date: formData.get("visit_date") || "",
          observations: formData.get("observations") || "",
          missing_information: formData.get("missing_information") || "",
          follow_up_notes: formData.get("follow_up_notes") || "",
          checklist: {
            onset_verified_locally: formData.get("onset_verified_locally") === "yes",
            pest_scouting_done: formData.get("pest_scouting_done") === "yes"
          },
          queued_at: new Date().toISOString()
        };

        if (!record.visit_date) {
          showMessage("Enter the visit date before saving offline.", true);
          return;
        }

        await storeRecord(record);
        form.reset();

        showMessage(
          "Saved on this device only. It has not reached the server yet. Keep this browser data until sync is confirmed.",
          false
        );
        if (navigator.onLine) syncPending();
      } catch (error) {
        showMessage(
          "Could not save this finding offline. Your form entries have been kept; please try again.",
          true
        );
        console.error("Offline save failed:", error);
      } finally {
        submitting = false;
        if (button) button.disabled = false;
      }
    });

    syncPending();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initialise);
  } else {
    initialise();
  }
})();
