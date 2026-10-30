
self.addEventListener("push", (event) => {
    let data = {
        title: "Finsight hourly report",
        body: "Your latest stock report is ready.",
        url: "/"
    };

    if (event.data) {
        try {
            data = { ...data, ...event.data.json() };
        } catch {
            data.body = event.data.text();
        }
    }

    event.waitUntil(
        self.registration.showNotification(data.title, {
            body: data.body,
            icon: "/static/finsight-logo.png",
            badge: "/static/finsight-logo.png",
            data: { url: data.url || "/" }
        })
    );
});

self.addEventListener("notificationclick", (event) => {
    event.notification.close();

    event.waitUntil(
        clients.openWindow(event.notification.data.url || "/")
    );
});
