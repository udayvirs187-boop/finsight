
"use strict";

/*
 * Finsight — app.js
 * The Flask backend is responsible for storing ticker views.
 * This file does not create demo views or use localStorage.
 */

document.addEventListener("DOMContentLoaded", () => {
    initialiseDeleteConfirmations();
    initialiseTickerForm();
    initialiseSearch();
    initialiseNavigation();
});

/*
 * Confirm before deleting a ticker or ticker view.
 */
function initialiseDeleteConfirmations() {
    document.querySelectorAll("[data-confirm-delete]").forEach((element) => {
        element.addEventListener("click", (event) => {
            const message =
                element.dataset.confirmDelete ||
                "Are you sure you want to delete this?";

            if (!window.confirm(message)) {
                event.preventDefault();
            }
        });
    });

    document.querySelectorAll("form[data-confirm-delete]").forEach((form) => {
        form.addEventListener("submit", (event) => {
            const message =
                form.dataset.confirmDelete ||
                "Are you sure you want to delete this?";

            if (!window.confirm(message)) {
                event.preventDefault();
            }
        });
    });
}

/*
 * Basic client-side checks for ticker creation forms.
 * Flask must still validate ticker symbols on the server.
 */
function initialiseTickerForm() {
    const forms = document.querySelectorAll(
        'form[data-ticker-form], form#ticker-form'
    );

    forms.forEach((form) => {
        form.addEventListener("submit", (event) => {
            const tickerInputs = form.querySelectorAll(
                'input[name="tickers"], input[name="ticker"], ' +
                'input[name="symbols"]'
            );

            if (tickerInputs.length === 0) {
                return;
            }

            const hasTicker = Array.from(tickerInputs).some((input) => {
                return input.value.trim().length > 0;
            });

            if (!hasTicker) {
                event.preventDefault();

                const message = form.querySelector("[data-form-error]");

                if (message) {
                    message.textContent =
                        "Enter at least one stock ticker.";
                    message.hidden = false;
                } else {
                    window.alert("Enter at least one stock ticker.");
                }

                tickerInputs[0].focus();
            }
        });
    });
}

/*
 * Optional filtering for lists of ticker views.
 * Add data-view-search to a search input and data-view-item
 * to each view card or row in the HTML.
 */
function initialiseSearch() {
    const searchInputs = document.querySelectorAll("[data-view-search]");

    searchInputs.forEach((input) => {
        input.addEventListener("input", () => {
            const query = input.value.trim().toLowerCase();

            document.querySelectorAll("[data-view-item]").forEach((item) => {
                const text = item.textContent.toLowerCase();
                item.hidden = !text.includes(query);
            });
        });
    });
}

/*
 * Optional dropdown/navigation buttons.
 * Add data-menu-toggle to a button and data-menu to its menu.
 */
function initialiseNavigation() {
    document.querySelectorAll("[data-menu-toggle]").forEach((button) => {
        button.addEventListener("click", () => {
            const menuName = button.dataset.menuToggle;
            const menu = document.querySelector(
                `[data-menu="${CSS.escape(menuName)}"]`
            );

            if (!menu) {
                return;
            }

            const isOpen = button.getAttribute("aria-expanded") === "true";

            button.setAttribute("aria-expanded", String(!isOpen));
            menu.hidden = isOpen;
        });
    });
}
