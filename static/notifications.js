
"use strict";

// --------------------------------------------------
// FINSIGHT PUSH NOTIFICATIONS
// --------------------------------------------------

const FINSIGHT_SW_URL = "/service-worker.js";
const FINSIGHT_PUBLIC_KEY_URL = "/api/vapid-public-key";
const FINSIGHT_SUBSCRIBE_URL = "/api/push/subscribe";
const FINSIGHT_TEST_URL = "/api/push/test";

// --------------------------------------------------
// HELPERS
// --------------------------------------------------

function getViewId(providedViewId) {
    if (providedViewId !== undefined && providedViewId !== null) {
        const id = Number(providedViewId);
        if (Number.isInteger(id) && id > 0) return id;
    }

    const params = new URLSearchParams(window.location.search);
    const queryId = Number(params.get("id"));

    if (Number.isInteger(queryId) && queryId > 0) {
        return queryId;
    }

    const element = document.querySelector("[data-view-id]");
    if (element) {
        const id = Number(element.dataset.viewId);
        if (Number.isInteger(id) && id > 0) return id;
    }

    throw new Error(
        "Could not find the ticker view ID. Open a saved ticker view first."
    );
}

async function fetchJSON(url, options = {}) {
    const response = await fetch(url, {
        credentials: "same-origin",
        ...options
    });

    const text = await response.text();
    let data = {};

    try {
        data = text ? JSON.parse(text) : {};
    } catch {
        throw new Error(
            `The server returned an invalid response (${response.status}).`
        );
    }

    if (!response.ok) {
        throw new Error(
            data.error || data.message || `Request failed (${response.status}).`
        );
    }

    return data;
}

function urlBase64ToUint8Array(base64String) {
    const padding = "=".repeat((4 - base64String.length % 4) % 4);

    const base64 = (base64String + padding)
        .replace(/-/g, "+")
        .replace(/_/g, "/");

    const rawData = window.atob(base64);

    return Uint8Array.from(rawData, character =>
        character.charCodeAt(0)
    );
}

async function getServiceWorker() {
    if (!("serviceWorker" in navigator)) {
        throw new Error("This browser does not support service workers.");
    }

    if (!("PushManager" in window)) {
        throw new Error("This browser does not support push notifications.");
    }

    const registration = await navigator.serviceWorker.register(
        FINSIGHT_SW_URL
    );

    return await navigator.serviceWorker.ready || registration;
}

async function getPublicVapidKey() {
    const data = await fetchJSON(FINSIGHT_PUBLIC_KEY_URL);

    if (!data.publicKey) {
        throw new Error("The server did not provide a public VAPID key.");
    }

    return data.publicKey.trim();
}

// --------------------------------------------------
// ENABLE NOTIFICATIONS
// --------------------------------------------------

async function enableNotifications(providedViewId) {
    try {
        const viewId = getViewId(providedViewId);

        if (!("Notification" in window)) {
            throw new Error(
                "This browser does not support notifications."
            );
        }

        const permission = await Notification.requestPermission();

        if (permission !== "granted") {
            throw new Error(
                "Notification permission was not granted. Check your browser settings."
            );
        }

        const registration = await getServiceWorker();
        const publicKey = await getPublicVapidKey();
        const applicationServerKey = urlBase64ToUint8Array(publicKey);

        // Remove the existing browser subscription if it was created
        // with the old applicationServerKey.
        let subscription =
            await registration.pushManager.getSubscription();

        if (subscription) {
            const existingKey = subscription.options.applicationServerKey;

            let sameKey = false;

            if (existingKey) {
                const oldBytes = new Uint8Array(existingKey);

                sameKey =
                    oldBytes.length === applicationServerKey.length &&
                    oldBytes.every(
                        (byte, index) => byte === applicationServerKey[index]
                    );
            }

            if (!sameKey) {
                await subscription.unsubscribe();
                subscription = null;
            }
        }

        // Create a subscription using the currently deployed public key.
        if (!subscription) {
            subscription = await registration.pushManager.subscribe({
                userVisibleOnly: true,
                applicationServerKey
            });
        }

        // Store the new subscription on the server.
        const result = await fetchJSON(FINSIGHT_SUBSCRIBE_URL, {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify({
                view_id: viewId,
                subscription: subscription.toJSON()
            })
        });

        console.log("Finsight subscription saved:", result);

        alert(
            result.message ||
            "Notifications enabled successfully."
        );

        return true;

    } catch (error) {
        console.error("Enable notifications failed:", error);

        alert("Could not enable notifications: " + error.message);

        return false;
    }
}

// --------------------------------------------------
// SEND TEST NOTIFICATION
// --------------------------------------------------

async function sendTestNotification(providedViewId) {
    try {
        const viewId = getViewId(providedViewId);

        const result = await fetchJSON(FINSIGHT_TEST_URL, {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify({
                view_id: viewId
            })
        });

        console.log("Test notification result:", result);

        alert(
            result.message ||
            "The test notification was accepted by the push service."
        );

        return true;

    } catch (error) {
        console.error("Test notification failed:", error);

        alert("Could not send test notification: " + error.message);

        return false;
    }
}

// --------------------------------------------------
// OPTIONAL: UNSUBSCRIBE FROM NOTIFICATIONS
// --------------------------------------------------

async function disableNotifications() {
    try {
        const registration = await getServiceWorker();
        const subscription =
            await registration.pushManager.getSubscription();

        if (!subscription) {
            alert("There is no active browser subscription.");
            return true;
        }

        await subscription.unsubscribe();

        alert(
            "Browser notifications have been disabled. " +
            "The old server-side subscription may still exist."
        );

        return true;

    } catch (error) {
        console.error("Disable notifications failed:", error);

        alert("Could not disable notifications: " + error.message);

        return false;
    }
}

// Keep these functions accessible to existing HTML onclick handlers.
window.enableNotifications = enableNotifications;
window.sendTestNotification = sendTestNotification;
window.disableNotifications = disableNotifications;
