
function setupMenu() {
    const button = document.getElementById("addButton");
    const dropdown = document.getElementById("addDropdown");

    if (!button || !dropdown) return;

    button.addEventListener("click", () => {
        const open = dropdown.classList.toggle("open");
        button.setAttribute("aria-expanded", String(open));
    });

    document.addEventListener("click", event => {
        if (!event.target.closest(".add-wrap")) {
            dropdown.classList.remove("open");
            button.setAttribute("aria-expanded", "false");
        }
    });
}

function getTables() {
    try {
        return JSON.parse(localStorage.getItem("finsightTables") || "[]");
    } catch {
        return [];
    }
}

function saveTables(tables) {
    localStorage.setItem("finsightTables", JSON.stringify(tables));
}

function escapeHTML(value) {
    return String(value).replace(/[&<>"']/g, character => ({
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#39;"
    })[character]);
}

function renderTables() {
    const body = document.getElementById("tablesBody");
    if (!body) return;

    const defaults = [
        {
            id: "demo-tech",
            name: "Tech Watchlist",
            tickers: ["AAPL", "MSFT", "NVDA"],
            demo: true
        },
        {
            id: "demo-core",
            name: "Long-term Core",
            tickers: ["SPY", "VOO"],
            demo: true
        },
        {
            id: "demo-energy",
            name: "Energy Watchlist",
            tickers: ["XOM", "CVX"],
            demo: true
        }
    ];

    const saved = getTables();
    const tables = [...defaults, ...saved];
    const query = (document.getElementById("searchInput")?.value || "")
        .trim()
        .toLowerCase();

    body.innerHTML = tables
        .filter(table => {
            return (
                table.name.toLowerCase().includes(query) ||
                table.tickers.join(" ").toLowerCase().includes(query)
            );
        })
        .map(table => {
            const id = encodeURIComponent(table.id);
            const name = escapeHTML(table.name);
            const tickers = escapeHTML(table.tickers.join(" · "));

            return `
                <tr>
                    <td>
                        <a class="table-name-link"
                           href="table.html?id=${id}">
                           ${name}
                        </a>
                    </td>
                    <td>${tickers}</td>
                    <td>${table.demo ? "Demo data" : "Not generated"}</td>
                    <td>—</td>
                    <td>${table.demo ? "Demo" : "Not configured"}</td>
                </tr>`;
        }).join("");

    const empty = document.getElementById("emptyMessage");
    if (empty) {
        empty.style.display = body.children.length ? "none" : "block";
    }
}

function setupCreateTicker() {
    const form = document.getElementById("tickerForm");
    if (!form) return;

    const selected = new Set();
    const selectedList = document.getElementById("selectedList");
    const search = document.getElementById("tickerSearch");
    const results = document.getElementById("searchResults");
    const message = document.getElementById("message");

    results?.addEventListener("click", event => {
        const button = event.target.closest("[data-symbol]");
        if (!button) return;

        const symbol = button.dataset.symbol;

        if (selected.has(symbol)) {
            selected.delete(symbol);
        } else {
            selected.add(symbol);
        }

        renderSelected();
    });

    function renderSelected() {
        selectedList.innerHTML = [...selected].map(symbol => `
            <span class="chip">
                ${escapeHTML(symbol)}
                <button type="button" data-remove="${escapeHTML(symbol)}"
                    aria-label="Remove ${escapeHTML(symbol)}">×</button>
            </span>
        `).join("");

        results?.querySelectorAll("[data-symbol]").forEach(button => {
            button.textContent = selected.has(button.dataset.symbol)
                ? "✓ Added" : "+ Add";
        });
    }

    selectedList?.addEventListener("click", event => {
        const button = event.target.closest("[data-remove]");
        if (!button) return;

        selected.delete(button.dataset.remove);
        renderSelected();
    });

    function filterResults() {
        const query = (search?.value || "").trim().toLowerCase();

        results?.querySelectorAll(".result-row").forEach(row => {
            row.hidden = !row.textContent.toLowerCase().includes(query);
        });
    }

    search?.addEventListener("input", filterResults);
    document.getElementById("searchButton")
        ?.addEventListener("click", filterResults);

    form.addEventListener("submit", event => {
        event.preventDefault();

        const name = document.getElementById("tableName").value.trim();

        if (!name || selected.size === 0) {
            message.textContent = "Enter a table name and add at least one ticker.";
            return;
        }

        const table = {
            id: "table-" + Date.now(),
            name,
            tickers: [...selected],
            hourlyReports: document.getElementById("hourlyReports").checked,
            notifications: document.getElementById("notifications").checked
        };

        const tables = getTables();
        tables.push(table);

        try {
            saveTables(tables);
            window.location.href = "table.html?id=" + encodeURIComponent(table.id);
        } catch {
            message.textContent =
                "Could not save this table in your browser. Check browser storage settings.";
        }
    });
}

function renderTableDetail() {
    const title = document.getElementById("detailTitle");
    if (!title) return;

    const id = new URLSearchParams(window.location.search).get("id");
    const table = getTables().find(item => item.id === id);

    if (!table) {
        title.textContent = "Table not found";
        document.getElementById("detailMessage").textContent =
            "This table does not exist in your saved browser data. Go to My Tables and select a table.";
        return;
    }

    title.textContent = table.name;

    document.getElementById("detailTickers").innerHTML =
        table.tickers.map(symbol =>
            `<span class="chip">${escapeHTML(symbol)}</span>`
        ).join("");

    document.getElementById("detailMessage").textContent =
        "Your selected tickers are listed above. Live prices, technical indicators and hourly reports need to be connected to a market-data API and backend.";
}

document.addEventListener("DOMContentLoaded", () => {
    setupMenu();
    renderTables();
    setupCreateTicker();
    renderTableDetail();

    document.getElementById("searchInput")
        ?.addEventListener("input", renderTables);
});
