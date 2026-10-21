(() => {
  "use strict";

  const csrf = () =>
    document.querySelector('meta[name="csrf-token"]')?.content ||
    document.querySelector("[name=csrfmiddlewaretoken]")?.value ||
    "";

  document.body.addEventListener("htmx:configRequest", (event) => {
    event.detail.headers["X-CSRFToken"] = csrf();
  });

  document.body.addEventListener("htmx:afterSwap", (event) => {
    const target = event.detail.target;
    if (target?.matches?.(".cell-editor")) {
      const input = target.querySelector("input, select, textarea");
      if (input) {
        input.focus();
        if (input.select) input.select();
      }
    }
  });

  // Keep focus on inline editor when clicking into it.
  document.addEventListener("click", (event) => {
    const trigger = event.target.closest("[data-cell-edit]");
    if (trigger) trigger.classList.add("is-editing");
  });

  // Dismiss messages after a pause, unless they are errors.
  setTimeout(() => {
    document.querySelectorAll(".messages .message:not(.message-error)").forEach((el) => {
      el.style.transition = "opacity .4s";
      el.style.opacity = "0";
      setTimeout(() => el.remove(), 450);
    });
  }, 6500);

  window.NetMap = { csrf };
})();
