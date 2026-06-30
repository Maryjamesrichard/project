(function () {
  var config = window.healthAppConfig || {};
  if ("serviceWorker" in navigator && config.swUrl) {
    window.addEventListener("load", function () {
      navigator.serviceWorker.register(config.swUrl).catch(function () {});
    });
  }

  var promptEl = document.getElementById("installPrompt");
  var installBtn = document.getElementById("installHealthApp");
  var dismissBtn = document.getElementById("dismissInstallPrompt");
  var deferredPrompt = null;
  var dismissed = localStorage.getItem("healthAppInstallDismissed") === "1";
  var standalone = window.matchMedia("(display-mode: standalone)").matches || window.navigator.standalone;

  window.addEventListener("beforeinstallprompt", function (event) {
    if (dismissed || standalone || !promptEl) {
      return;
    }
    event.preventDefault();
    deferredPrompt = event;
    promptEl.classList.remove("d-none");
  });

  if (installBtn) {
    installBtn.addEventListener("click", function () {
      if (!deferredPrompt) {
        return;
      }
      deferredPrompt.prompt();
      deferredPrompt.userChoice.finally(function () {
        promptEl.classList.add("d-none");
        deferredPrompt = null;
      });
    });
  }

  if (dismissBtn) {
    dismissBtn.addEventListener("click", function () {
      localStorage.setItem("healthAppInstallDismissed", "1");
      dismissed = true;
      if (promptEl) {
        promptEl.classList.add("d-none");
      }
    });
  }
})();
