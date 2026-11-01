
"use strict";

// ==================================================
// FINSIGHT PUSH NOTIFICATIONS
// ==================================================

const FINSIGHT_SW_URL = "/service-worker.js";
const FINSIGHT_PUBLIC_KEY_URL = "/api/vapid-public-key";
const FINSIGHT_SUBSCRIBE_URL = "/api/push/subscribe";
const FINSIGHT_TEST_URL = "/api/push/test";

// ==================================================
// HELPERS
// ==================================================

function getViewId(providedViewId) {
    if (providedViewId !== undefined && providedViewId !== null) {
        const id = Number(providedViewId);

        if (Number.isInteger(id) && id > 0) {
            return id;
        }
    }

    const params = new URLSearchParams(window.location.search);
    const queryId = Number(params.get("id"));

    if (Number.isInteger(queryId) && queryId > 0) {
        return queryId;
    }

    const element = document.querySelector("[data-view-id]");

    if (element) {
        const id = Number(element.dataset.viewId);

        if (Number.isInteger(id) && id > 0) {
            return id;
        }
    }

    throw new Error(
        "Ticker view ID not found. Open a saved ticker view first."
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
            `Invalid server response (${response.status}).`
        );
    }

    if (!response.ok) {
        throw new Error(
            data.error ||
            data.message ||
            `Request failed (${response.status}).`
        );
    }

    return data;
}

function urlBase64ToUint8Array(base64String) {
    const padding = "=".repeat(
        (4 - base64String.length % 4) % 4
    );

    const base64 = (base64String + padding)
        .replace(/-/g, "+")
        .replace(/_/g, "/");

    const rawData = window.atob(base64);

    return Uint8Array.from(
        rawData,
        character => character.charCodeAt(0)
    );
}

async function getServiceWorker() {
    if (!("serviceWorker" in navigator)) {
        throw new Error(
            "This browser does not support service workers."
        );
    }

    if (!("PushManager" in window)) {
        throw new Error(
            "This browser does not support push notifications."
        );
    }

    const registration = await navigator.serviceWorker.register(
        FINSIGHT_SW_URL
    );

    return await navigator.serviceWorker.ready || registration;
}

async function getPublicVapidKey() {
    const data = await fetchJSON(FINSIGHT_PUBLIC_KEY_URL);

    if (!data.publicKey) {
        throw new Error(
            "The server did not provide a public VAPID key."
        );
    }

    return data.publicKey.trim();
}

function showError(action, error) {
    console.error(`Finsight ${action} failed:`, error);

    alert(
        `${action} failed: ` +
        (error.message || "An unexpected error occurred.")
    );
}

// ==================================================
// ENABLE NOTIFICATIONS
// ==================================================

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
                "Notification permission was not granted. " +
                "Check your browser site settings."
            );
        }

        const registration = await getServiceWorker();
        const publicKey = await getPublicVapidKey();

        const applicationServerKey =
            urlBase64ToUint8Array(publicKey);

        let subscription =
            await registration.pushManager.getSubscription();

        // Remove the old subscription if it uses a different key.
        if (subscription) {
            const existingKey =
                subscription.options.applicationServerKey;

            let sameKey = false;

            if (existingKey) {
                const oldBytes = new Uint8Array(existingKey);

                sameKey =
                    oldBytes.length === applicationServerKey.length &&
                    oldBytes.every(
                        (byte, index) =>
                            byte === applicationServerKey[index]
                    );
            }

            if (!sameKey) {
                await subscription.unsubscribe();
                subscription = null;
            }
        }

        // Create a subscription with the current public key.
        if (!subscription) {
            subscription =
                await registration.pushManager.subscribe({
                    userVisibleOnly: true,
                    applicationServerKey
                });
        }

        // Save the subscription for this ticker view.
        const result = await fetchJSON(
            FINSIGHT_SUBSCRIBE_URL,
            {
                method: "POST",
                headers: {
                    "Content-Type": "application/json"
                },
                body: JSON.stringify({
                    view_id: viewId,
                    subscription: subscription.toJSON()
                })
            }
        );

        console.log("Finsight subscription saved:", result);

        alert(
            result.message ||
            "Notifications enabled successfully."
        );

        return true;

    } catch (error) {
        showError("Enable notifications", error);
        return false;
    }
}

// ==================================================
// SEND TEST NOTIFICATION
// ==================================================

async function sendTestNotification(providedViewId) {
    try {
        const viewId = getViewId(providedViewId);

        const result = await fetchJSON(
            FINSIGHT_TEST_URL,
            {
                method: "POST",
                headers: {
                    "Content-Type": "application/json"
                },
                body: JSON.stringify({
                    view_id: viewId
                })
            }
        );

        console.log("Finsight test notification result:", result);

        alert(
            result.message ||
            "The test notification request was accepted."
        );

        return true;

    } catch (error) {
        showError("Test notification", error);
        return false;
    }
}

// ==================================================
// DISABLE NOTIFICATIONS
// ==================================================

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
            "The server-side subscription may still exist."
        );

        return true;

    } catch (error) {
        showError("Disable notifications", error);
        return false;
    }
}

// ==================================================
// BUTTON WIRING
// ==================================================

function bindNotificationButton(selectors, action) {
    const buttons = document.querySelectorAll(selectors);

    buttons.forEach(button => {
        // Prevent duplicate event handlers.
        if (
            button.dataset.finsightNotificationBound === "true"
        ) {
            return;
        }

        button.dataset.finsightNotificationBound = "true";

        button.addEventListener("click", async event => {
            event.preventDefault();

            if (button.disabled) {
                return;
            }

            button.disabled = true;

            try {
                const viewId =
                    button.dataset.viewId ||
                    document.querySelector("[data-view-id]")
                        ?.dataset.viewId;

                await action(viewId);

            } catch (error) {
                showError("Notification action", error);

            } finally {
                button.disabled = false;
            }
        });
    });
}

function initialiseNotificationButtons() {
    // Matches the actual attributes in your view_table.html.
    bindNotificationButton(
        [
            "#enable-notifications",
            "#enableNotifications",
            "#enableNotificationsBtn",
            "#enable-notifications-btn",
            "[data-action='enable-notifications']",
            "[data-enable-push]"
        ].join(","),
        enableNotifications
    );

    bindNotificationButton(
        [
            "#test-notification",
            "#testNotification",
            "#testNotificationBtn",
            "#test-notification-btn",
            "[data-action='test-notification']",
            "[data-test-push]"
        ].join(","),
        sendTestNotification
    );

    bindNotificationButton(
        [
            "#disable-notifications",
            "#disableNotifications",
            "[data-action='disable-notifications']"
        ].join(","),
        disableNotifications
    );

    console.log("Finsight notification buttons initialised.");

    console.log(
        "Enable button found:",
        document.querySelectorAll("[data-enable-push]").length
    );

    console.log(
        "Test button found:",
        document.querySelectorAll("[data-test-push]").length
    );
}

// ==================================================
// GLOBAL FUNCTIONS
// ==================================================

// Preserve compatibility with existing HTML onclick handlers.
window.enableNotifications = enableNotifications;
window.sendTestNotification = sendTestNotification;
window.disableNotifications = disableNotifications;

// Initialise after the HTML has loaded.
if (document.readyState === "loading") {
    document.addEventListener(
        "DOMContentLoaded",
        initialiseNotificationButtons
    );
} else {
    initialiseNotificationButtons();
}
