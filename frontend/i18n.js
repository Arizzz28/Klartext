// Translations. English texts are written in the code; if the person chose another language, every APPROVED translation replaces the
// matching English text on the screen (text, placeholders, tooltips). Texts without an approved translation stay English.
// Elements (and their children) marked translate="no" are never changed - that is how people's own messages stay untouched.
import { API_URL } from "./config.js";

const KEY = "chatisfying_lang", PACK = "chatisfying_langpack";
let texts = {};
export const currentLang = () => localStorage.getItem(KEY) || "en";
export const setLang = (code) => { if (code && code !== "en") localStorage.setItem(KEY, code); else { localStorage.removeItem(KEY); localStorage.removeItem(PACK); } };

const ATTRS = ["placeholder", "title", "aria-label", "alt"];
function tr(s) {
  const t = s.trim();
  const out = t && texts[t];
  return out ? s.replace(t, out) : s;
}
function skip(el) { return el.closest?.('[translate="no"], script, style, textarea, code'); }

function walk(root) {
  if (root.nodeType === 3) { if (!skip(root.parentElement)) { const n = tr(root.nodeValue); if (n !== root.nodeValue) root.nodeValue = n; } return; }
  if (root.nodeType !== 1 || skip(root)) return;
  for (const a of ATTRS) if (root.hasAttribute(a)) { const v = root.getAttribute(a), n = tr(v); if (n !== v) root.setAttribute(a, n); }
  for (const c of root.childNodes) walk(c);
}

export async function initI18n() {
  const lang = currentLang();
  document.documentElement.lang = lang;
  if (lang === "en") return;
  try { texts = JSON.parse(localStorage.getItem(PACK) || "{}").texts || {}; } catch { texts = {}; }
  const apply = () => { walk(document.body); };
  new MutationObserver((muts) => { for (const m of muts) { m.addedNodes.forEach((n) => walk(n)); if (m.type === "characterData") walk(m.target); } })
    .observe(document.body, { childList: true, subtree: true, characterData: true });
  apply();
  try {                                                       // refresh the pack in the background (used on the next page load)
    const r = await fetch(`${API_URL}/api/i18n/${lang}`);
    if (r.ok) {
      const pack = await r.json();
      const first = !Object.keys(texts).length;
      localStorage.setItem(PACK, JSON.stringify(pack));
      if (first) { texts = pack.texts; apply(); }
    }
  } catch { /* offline: the saved pack is used */ }
}
