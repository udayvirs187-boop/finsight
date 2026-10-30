
async function enableNotifications(viewId) {
    if (!("serviceWorker" in navigator) || !("PushManager" in window)) {
        alert("Your browser does not support push notifications.");
        return;
    }

    if (!("Notification" in window)) {
        alert("Notifications are not supported by this browser.");
        return;
    }

    try {
        const permission = await Notification.requestPermission();

        if (permission !== "granted") {
            alert("Notifications were not allowed. Check your browser site settings.");
            return;
        }

        const workerResponse = await fetch("/service-worker.js");

        if (!workerResponse.ok) {
            throw new Error("Service worker file missing: " + workerResponse.status);
        }

        const registration = await navigator.serviceWorker.register(
            "/service-worker.js"
        );

        await navigator.serviceWorker.ready;

        const keyResponse = await fetch("/api/vapid-public-key");

        if (!keyResponse.ok) {
            throw new Error("Could not load notification key: " + keyResponse.status);
        }

        const { publicKey } = await keyResponse.json();

        if (!publicKey) {
            throw new Error("VAPID public key is missing.");
        }

        const subscription = await registration.pushManager.subscribe({
            userVisibleOnly: true,
            applicationServerKey: urlBase64ToUint8Array(publicKey)
        });

        const response = await fetch("/api/push/subscribe", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                view_id: Number(viewId),
                subscription: subscription
            })
        });

        const result = await response.json();

        if (!response.ok) {
            throw new Error(result.error || "Could not save subscription.");
        }

        alert("Notifications enabled for this ticker view!");
    } catch (error) {
        console.error("Enable notifications failed:", error);
        alert("Could not enable notifications: " + error.message);
    }
}

async function sendTestNotification(viewId) {
    try {
        const response = await fetch("/api/push/test", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ view_id: Number(viewId) })
        });

        const result = await response.json();

        if (!response.ok) {
            throw new Error(result.error || "Test notification failed.");
        }

        alert(result.message || "Test notification sent.");
    } catch (error) {
        console.error("Test notification failed:", error);
        alert("Could not send test notification: " + error.message);
    }
}

function urlBase64ToUint8Array(base64String) {
    const padding = "=".repeat((4 - base64String.length % 4) % 4);
    const base64 = (base64String + padding)
        .replace(/-/g, "+")
        .replace(/_/g, "/");

    const rawData = window.atob(base64);
    return Uint8Array.from(rawData, character => character.charCodeAt(0));
}

document.addEventListener("DOMContentLoaded", () => {
    document.querySelectorAll("[data-enable-push]").forEach(button => {
        button.addEventListener("click", () => {
            enableNotifications(button.dataset.viewId);
        });
    });

    document.querySelectorAll("[data-test-push]").forEach(button => {
        button.addEventListener("click", () => {
            sendTestNotification(button.dataset.viewId);
        });
    });
});
