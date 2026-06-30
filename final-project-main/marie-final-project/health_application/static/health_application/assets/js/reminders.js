(function () {
  var config = window.healthAppConfig || {};
  if (!config.activeRemindersUrl) {
    return;
  }

  var reminders = new Map();
  var alertedKeys = new Set(JSON.parse(localStorage.getItem("healthReminderAlerted") || "[]"));
  var currentReminder = null;
  var audio = null;
  var audioContext = null;
  var alarmTimer = null;
  var modalInstance = null;
  var modalEl = document.getElementById("medicationReminderModal");
  var medicineEl = document.getElementById("reminderMedicineName");
  var doseEl = document.getElementById("reminderDoseText");
  var instructionsEl = document.getElementById("reminderInstructionsText");
  var stopBtn = document.getElementById("stopReminderAlarm");
  var takenBtn = document.getElementById("markReminderTaken");

  function rememberAlert(key) {
    alertedKeys.add(key);
    localStorage.setItem("healthReminderAlerted", JSON.stringify(Array.from(alertedKeys).slice(-100)));
  }

  function unlockAudio() {
    if (!audio) {
      audio = new Audio(config.alarmAudioUrl || "");
      audio.loop = true;
    }
    if (!audioContext && window.AudioContext) {
      audioContext = new AudioContext();
    }
    if (audioContext && audioContext.state === "suspended") {
      audioContext.resume();
    }
  }

  ["click", "touchstart", "keydown"].forEach(function (eventName) {
    window.addEventListener(eventName, unlockAudio, { once: true, passive: true });
  });

  function fallbackTone() {
    if (!audioContext) {
      return;
    }
    var oscillator = audioContext.createOscillator();
    var gain = audioContext.createGain();
    oscillator.frequency.value = 880;
    gain.gain.value = 0.2;
    oscillator.connect(gain);
    gain.connect(audioContext.destination);
    oscillator.start();
    setTimeout(function () {
      oscillator.stop();
    }, 700);
  }

  function playAlarm() {
    unlockAudio();
    var played = false;
    if (audio) {
      audio.currentTime = 0;
      audio.play().then(function () {
        played = true;
      }).catch(fallbackTone);
    } else {
      fallbackTone();
    }
    alarmTimer = setInterval(function () {
      if (!played) {
        fallbackTone();
      }
    }, 1500);
    setTimeout(stopAlarm, 45000);
  }

  function stopAlarm() {
    if (audio) {
      audio.pause();
      audio.currentTime = 0;
    }
    if (alarmTimer) {
      clearInterval(alarmTimer);
      alarmTimer = null;
    }
  }

  function formatCountdown(ms) {
    if (ms <= 0) {
      return config.i18n && config.i18n.timeToTake ? config.i18n.timeToTake : "Time to take your medicine";
    }
    var total = Math.floor(ms / 1000);
    var hours = String(Math.floor(total / 3600)).padStart(2, "0");
    var minutes = String(Math.floor((total % 3600) / 60)).padStart(2, "0");
    var seconds = String(total % 60).padStart(2, "0");
    var prefix = config.i18n && config.i18n.nextDoseIn ? config.i18n.nextDoseIn : "Next dose in";
    return prefix + " " + hours + ":" + minutes + ":" + seconds;
  }

  function showReminder(reminder) {
    currentReminder = reminder;
    if (medicineEl) {
      medicineEl.textContent = reminder.medicine_name;
    }
    if (doseEl) {
      doseEl.textContent = reminder.dosage;
    }
    if (instructionsEl) {
      instructionsEl.textContent = reminder.instructions || "";
    }
    if (window.Notification && Notification.permission === "default") {
      Notification.requestPermission();
    }
    if (window.Notification && Notification.permission === "granted") {
      new Notification(config.i18n.timeToTake || "Time to take your medicine", {
        body: reminder.medicine_name + " - " + reminder.dosage,
      });
    }
    if (modalEl && window.bootstrap) {
      modalInstance = modalInstance || new bootstrap.Modal(modalEl, { backdrop: "static", keyboard: false });
      modalInstance.show();
    } else if (modalEl) {
      modalEl.classList.add("show");
      modalEl.style.display = "block";
    }
    playAlarm();
  }

  function refreshCountdowns() {
    var now = Date.now();
    reminders.forEach(function (reminder) {
      if (!reminder.next_trigger_at) {
        return;
      }
      var trigger = new Date(reminder.next_trigger_at).getTime();
      var key = reminder.id + ":" + reminder.next_trigger_at;
      document.querySelectorAll('[data-reminder-id="' + reminder.id + '"]').forEach(function (el) {
        el.textContent = formatCountdown(trigger - now);
      });
      if (trigger <= now && !alertedKeys.has(key)) {
        rememberAlert(key);
        showReminder(reminder);
      }
    });
  }

  function loadReminders() {
    fetch(config.activeRemindersUrl, { credentials: "same-origin" })
      .then(function (response) {
        return response.json();
      })
      .then(function (data) {
        reminders.clear();
        (data.reminders || []).forEach(function (reminder) {
          reminders.set(reminder.id, reminder);
        });
        refreshCountdowns();
      })
      .catch(function () {});
  }

  if (stopBtn) {
    stopBtn.addEventListener("click", stopAlarm);
  }
  if (takenBtn) {
    takenBtn.addEventListener("click", function () {
      if (!currentReminder) {
        return;
      }
      stopAlarm();
      fetch(config.markTakenUrlTemplate.replace("/0/", "/" + currentReminder.id + "/"), {
        method: "POST",
        credentials: "same-origin",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": config.csrfToken || "",
        },
      }).then(function () {
        if (modalInstance) {
          modalInstance.hide();
        }
        currentReminder = null;
        loadReminders();
      });
    });
  }

  loadReminders();
  setInterval(loadReminders, 60000);
  setInterval(refreshCountdowns, 1000);
})();
