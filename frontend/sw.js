// Service worker: shows push messages even when the app is closed.
self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (e) => e.waitUntil(self.clients.claim()));

self.addEventListener("push", (event) => {
  let data = {};
  try { data = event.data ? event.data.json() : {}; } catch { data = { title: "Chatisfying", body: "New message" }; }
  event.waitUntil(self.registration.showNotification(data.title || "Chatisfying", {
    body: data.body || "New message",
    icon: "assets/images/logo.svg",
    tag: data.url || "chatisfying",          // several messages from one chat replace each other
    data: { url: data.url || "#/chats" },
  }));
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const target = self.registration.scope + (event.notification.data?.url || "");
  event.waitUntil(self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((list) => {
    const open = list.find((c) => c.url.startsWith(self.registration.scope));
    if (open) return open.focus().then(() => open.navigate(target));
    return self.clients.openWindow(target);
  }));
});
