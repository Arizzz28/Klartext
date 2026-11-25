// Fills the operator details into the legal pages (terms.html, privacy.html, imprint.html and the consent dialog).
// Whatever the Owner has not entered is shown as a clearly marked gap - nothing is invented.
import { get } from "./api.js";

export async function fillLegal(root = document) {
  let info = null;
  try { info = await get("/api/legal"); } catch { /* server not reachable: the gaps stay marked */ }
  root.querySelectorAll("[data-op]").forEach((el) => {
    const value = info?.operator?.[el.dataset.op];
    if (value) { el.textContent = value; el.classList.remove("todo"); }
    else { el.textContent = `[NOCH NICHT AUSGEFÜLLT: ${el.dataset.label || el.dataset.op}]`; el.classList.add("todo"); }
  });
  root.querySelectorAll("[data-version]").forEach((el) => {
    const v = info?.[el.dataset.version];
    if (v) el.textContent = v;
  });
}

if (document.body?.dataset.page === "legal") fillLegal();
