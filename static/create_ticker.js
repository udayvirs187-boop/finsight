
"use strict";

document.addEventListener("DOMContentLoaded", () => {
    const form = document.getElementById("createTickerForm");
    const tickerInput = document.getElementById("tickerInput");
    const addButton = document.getElementById("addTicker");
    const tickerList = document.getElementById("tickerList");
    const tickerCount = document.getElementById("tickerCount");
    const allTickersInput = document.getElementById("allTickers");
    const preview = document.getElementById("stockLookup");
    const createButton = document.getElementById("createViewButton");

    // Check that the expected HTML elements exist.
    if (
        !form ||
        !tickerInput ||
        !addButton ||
        !tickerList ||
        !tickerCount ||
        !allTickersInput ||
        !preview ||
        !createButton
    ) {
        console.error("Finsight: A required Create Ticker HTML element is missing.");
        return;
    }

    // Restore previously selected tickers after a form validation error.
    const tickers = Array.isArray(window.initialSelectedTickers)
        ? [...window.initialSelectedTickers]
        : [];

    let lookupInProgress = false;

    // Display a message in the stock lookup area.
    function showPreviewMessage(message) {
        preview.hidden = false;
        preview.replaceChildren();

        const text = document.createElement("div");
        text.className = "preview-message";
        text.textContent = message;

        preview.appendChild(text);
    }

    // Render the selected ticker chips.
    function renderTickers() {
        tickerList.replaceChildren();

        if (tickers.length === 0) {
            const empty = document.createElement("div");
            empty.className = "empty-list";
            empty.textContent = "No stocks added yet.";
            tickerList.appendChild(empty);
        }

        tickers.forEach((ticker) => {
            const chip = document.createElement("div");
            chip.className = "ticker-chip";

            const symbol = document.createElement("span");
            symbol.className = "ticker-symbol";
            symbol.textContent = ticker;

            const removeButton = document.createElement("button");
            removeButton.type = "button";
            removeButton.className = "remove-ticker";
            removeButton.textContent = "×";
            removeButton.setAttribute(
                "aria-label",
                `Remove ${ticker}`
            );

            removeButton.addEventListener("click", () => {
                const index = tickers.indexOf(ticker);

                if (index !== -1) {
                    tickers.splice(index, 1);
                }

                renderTickers();
                showPreviewMessage(`${ticker} removed from your view.`);
            });

            chip.append(symbol, removeButton);
            tickerList.appendChild(chip);
        });

        tickerCount.textContent =
            `${tickers.length} stock${tickers.length === 1 ? "" : "s"} added`;

        // Send the selected tickers to Flask when the form is submitted.
        allTickersInput.value = tickers.join(",");
    }

    // Display company information returned by the Flask API.
    function showStockPreview(stock) {
        preview.hidden = false;
        preview.replaceChildren();

        if (stock.logo_url) {
            const logo = document.createElement("img");
            logo.className = "stock-logo";
            logo.src = stock.logo_url;
            logo.alt = `${stock.company_name} logo`;
            logo.onerror = () => logo.remove();

            preview.appendChild(logo);
        }

        const textContainer = document.createElement("div");

        const companyName = document.createElement("div");
        companyName.className = "preview-name";
        companyName.textContent =
            `${stock.company_name} (${stock.ticker})`;

        const details = document.createElement("div");
        details.className = "preview-details";

        const information = [];

        if (stock.exchange) {
            information.push(stock.exchange);
        }

        if (stock.currency) {
            information.push(stock.currency);
        }

        if (
            stock.current_price !== null &&
            stock.current_price !== undefined
        ) {
            information.push(
                `Price: ${stock.currency || ""} ${stock.current_price}`.trim()
            );
        }

        details.textContent = information.length
            ? information.join(" · ")
            : "Company information retrieved.";

        textContainer.append(companyName, details);
        preview.appendChild(textContainer);
    }

    // Look up a ticker and add it only if the API confirms it exists.
    async function addTicker() {
        const symbol = tickerInput.value.trim().toUpperCase();

        if (!symbol) {
            tickerInput.focus();
            showPreviewMessage("Enter a stock ticker first.");
            return;
        }

        if (!/^[A-Z0-9.^=_-]+$/.test(symbol)) {
            showPreviewMessage(
                "Check the ticker format. For example: AAPL or VUAG.L."
            );
            return;
        }

        if (tickers.includes(symbol)) {
            showPreviewMessage(`${symbol} has already been added.`);
            return;
        }

        if (lookupInProgress) {
            return;
        }

        lookupInProgress = true;
        addButton.disabled = true;
        addButton.textContent = "Looking…";

        showPreviewMessage(
            `Looking up ${symbol} on Yahoo Finance…`
        );

        try {
            const response = await fetch(
                `/api/stock/${encodeURIComponent(symbol)}`,
                {
                    method: "GET",
                    headers: {
                        "Accept": "application/json"
                    }
                }
            );

            const result = await response.json();

            if (!response.ok || !result.success) {
                showPreviewMessage(
                    result.error || `Could not find ${symbol}.`
                );
                return;
            }

            const stock = result.stock;

            // Add the ticker only after a successful lookup.
            tickers.push(symbol);
            renderTickers();
            showStockPreview(stock);

            tickerInput.value = "";
            tickerInput.focus();

        } catch (error) {
            console.error("Stock lookup error:", error);

            showPreviewMessage(
                "Could not contact Finsight. Check that Flask is running and try again."
            );

        } finally {
            lookupInProgress = false;
            addButton.disabled = false;
            addButton.textContent = "+ Add";
        }
    }

    // Add a ticker when the button is clicked.
    addButton.addEventListener("click", addTicker);

    // Also allow Enter to add a ticker.
    tickerInput.addEventListener("keydown", (event) => {
        if (event.key === "Enter") {
            event.preventDefault();
            addTicker();
        }
    });

    // Validate the selected tickers before submitting the form.
    form.addEventListener("submit", (event) => {
        if (lookupInProgress) {
            event.preventDefault();
            showPreviewMessage(
                "Please wait for the stock lookup to finish."
            );
            return;
        }

        if (tickers.length === 0) {
            event.preventDefault();
            showPreviewMessage(
                "Please add at least one stock ticker."
            );
            tickerInput.focus();
            return;
        }

        // Make sure Flask receives every selected ticker.
        allTickersInput.value = tickers.join(",");

        createButton.disabled = true;
        createButton.textContent = "Creating view…";
    });

    // Render any tickers restored by Flask.
    renderTickers();
});
