(() => {
  const key = "cuentas-claras-theme";
  const choices = ["system", "light", "dark"];
  const system = window.matchMedia("(prefers-color-scheme: dark)");
  let preference = "system";
  let button;
  try {
    const saved = window.localStorage.getItem(key);
    if (choices.includes(saved)) preference = saved;
  } catch (error) {
    console.warn("No se pudo recuperar la preferencia de tema:", error);
  }

  function applyTheme() {
    document.documentElement.dataset.theme = preference === "system"
      ? system.matches ? "dark" : "light"
      : preference;
    if (button) {
      const label = document.documentElement.dataset.theme === "dark"
        ? "Activar modo claro" : "Activar modo oscuro";
      button.setAttribute("aria-label", label);
      button.setAttribute("title", label);
    }
  }
  applyTheme();
  system.addEventListener("change", applyTheme);

  document.addEventListener("DOMContentLoaded", () => {
    button = document.querySelector("[data-theme-toggle]");
    const status = document.querySelector("[data-theme-status]");
    if (!button) return;
    applyTheme();
    button.addEventListener("click", () => {
      preference = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
      applyTheme();
      try {
        window.localStorage.setItem(key, preference);
        status.textContent = "Apariencia actualizada.";
      } catch (error) {
        console.warn("No se pudo guardar la preferencia de tema:", error);
        status.textContent = "Apariencia actualizada, pero no se pudo guardar la preferencia en este navegador.";
      }
    });
    window.addEventListener("storage", (event) => {
      if (event.key !== key && event.key !== null) return;
      preference = choices.includes(event.newValue) ? event.newValue : "system";
      applyTheme();
    });
  });
})();
