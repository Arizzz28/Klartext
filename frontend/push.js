// Web push in the browser: asks for permission, registers the service worker and tells the server where to send.
import { get, post } from "./api.js";

export const pushSupported = () => "serviceWorker" in navigator && "PushManager" in window && "Notification" in window;

export function needsHomeScreen() {
  const ios = /iPad|iPhone|iPod/.test(navigator.userAgent) || (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);
  const standalone = window.navigator.standalone === true || window.matchMedia?.("(display-mode: standalone)").matches;
  return ios && !standalone;
}

function keyToBytes(base64url) {
  const pad = "=".repeat((4 - (base64url.length % 4)) % 4);
  const raw = atob((base64url + pad).replace(/-/g, "+").replace(/_/g, "/"));
  return Uint8Array.from(raw, (c) => c.charCodeAt(0));
}

export async function pushState() {
  if (!pushSupported()) return needsHomeScreen() ? "needs-home-screen" : "unsupported";
  if (Notification.permission === "denied") return "denied";
  try {
    const reg = await navigator.serviceWorker.getRegistration();
    const sub = reg && (await reg.pushManager.getSubscription());
    return sub ? "on" : "off";
  } catch { return "off"; }
}

export async function enablePush() {
  if (!pushSupported()) throw new Error(needsHomeScreen()
    ? "On an iPad or iPhone, first add Chatisfying to your Home Screen (Share button → “Add to Home Screen”) and open it from there."
    : "This browser does not support push messages.");
  const info = await get("/api/push/key");
  if (!info.enabled) throw new Error("Push messages are not set up on the server yet (the Owner has to add the VAPID keys).");
  const permission = await Notification.requestPermission();
  if (permission !== "granted") throw new Error("Notifications were not allowed. You can change this in your device settings.");
  const reg = await navigator.serviceWorker.register("sw.js");
  await navigator.serviceWorker.ready;
  let sub = await reg.pushManager.getSubscription();
  if (!sub) sub = await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: keyToBytes(info.public_key) });
  await post("/api/push/subscribe", sub.toJSON());
}

export async function disablePush() {
  const reg = await navigator.serviceWorker.getRegistration();
  const sub = reg && (await reg.pushManager.getSubscription());
  if (sub) {
    try { await post("/api/push/unsubscribe", { endpoint: sub.endpoint }); } catch { /* the server forgets it later anyway */ }
    await sub.unsubscribe();
  }
}
