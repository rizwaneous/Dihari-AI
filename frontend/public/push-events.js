self.addEventListener("push", event => {
  if (!event.data) return;
  const { title, body, tag } = event.data.json();
  event.waitUntil(self.registration.showNotification(title, { body, tag, icon: "/icon-192.png" }));
});
self.addEventListener("notificationclick", event => {
  event.notification.close();
  event.waitUntil(self.clients.openWindow(self.location.origin + "/"));
});
