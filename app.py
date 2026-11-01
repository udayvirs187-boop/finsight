import json
import os
import re
import secrets
import sqlite3
from datetime import datetime
from pathlib import Path

import yfinance as yf
from apscheduler.schedulers.background import BackgroundScheduler
from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    jsonify,
    send_from_directory,
    session,
)
from pywebpush import webpush, WebPushException
from werkzeug.security import generate_password_hash, check_password_hash

from market_data import get_stock_data


# --------------------------------------------------
# APP CONFIGURATION
# --------------------------------------------------

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY") or secrets.token_hex(32)
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"



DATABASE = Path(__file__).with_name("finsight.db")

PRIVATE_KEY = Path(
    os.environ.get(
        "VAPID_PRIVATE_KEY_PATH",
        str(Path(__file__).with_name("private_key.pem")),
    )
)

PUBLIC_KEY_FILE = Path(__file__).with_name("vapid_public_key.txt")

VAPID_CLAIMS = {
    "sub": (
        os.environ.get("VAPID_SUBJECT")
        or "mailto:udayvirs187@gmail.com"
    ).strip()
}


PUBLIC_KEY_FILE = Path(__file__).with_name("vapid_public_key.txt")

VAPID_CLAIMS = {
    "sub": os.environ.get(
        "VAPID_SUBJECT",
        "mailto:finsight@example.com",
    )
}


# --------------------------------------------------
# DATABASE
# --------------------------------------------------

def get_db_connection():
    connection = sqlite3.connect(DATABASE)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def initialise_database():
    with get_db_connection() as connection:
        connection.execute("""
            CREATE TABLE IF NOT EXISTS ticker_views (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                tickers TEXT NOT NULL,
                hourly_reports INTEGER NOT NULL DEFAULT 0,
                notifications INTEGER NOT NULL DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        connection.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL COLLATE NOCASE UNIQUE,
                email TEXT NOT NULL COLLATE NOCASE UNIQUE,
                password_hash TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        connection.execute("""
            CREATE TABLE IF NOT EXISTS stocks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticker TEXT NOT NULL UNIQUE,
                company_name TEXT NOT NULL,
                exchange TEXT,
                currency TEXT,
                logo_url TEXT,
                current_price REAL,
                price_change REAL,
                price_change_percent REAL,
                rsi REAL,
                macd REAL,
                macd_signal REAL,
                relative_volume REAL,
                last_updated TEXT,
                saved_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        existing_columns = {
            row["name"]
            for row in connection.execute(
                "PRAGMA table_info(stocks)"
            ).fetchall()
        }

        optional_columns = {
            "logo_url": "TEXT",
            "current_price": "REAL",
            "price_change": "REAL",
            "price_change_percent": "REAL",
            "rsi": "REAL",
            "macd": "REAL",
            "macd_signal": "REAL",
            "relative_volume": "REAL",
            "last_updated": "TEXT",
            "saved_at": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
        }

        for column, definition in optional_columns.items():
            if column not in existing_columns:
                connection.execute(
                    f"ALTER TABLE stocks ADD COLUMN {column} {definition}"
                )

        connection.execute("""
            CREATE TABLE IF NOT EXISTS push_subscriptions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                view_id INTEGER NOT NULL,
                endpoint TEXT NOT NULL,
                subscription_json TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(view_id, endpoint),
                FOREIGN KEY(view_id)
                    REFERENCES ticker_views(id)
                    ON DELETE CASCADE
            )
        """)

        subscription_columns = {
            row["name"]
            for row in connection.execute(
                "PRAGMA table_info(push_subscriptions)"
            ).fetchall()
        }

        if "view_id" in subscription_columns:
            indexes = connection.execute(
                "PRAGMA index_list(push_subscriptions)"
            ).fetchall()

            endpoint_is_unique = False

            for index in indexes:
                if not index["unique"]:
                    continue

                index_columns = connection.execute(
                    f"PRAGMA index_info('{index['name']}')"
                ).fetchall()

                names = [item["name"] for item in index_columns]

                if names == ["endpoint"]:
                    endpoint_is_unique = True
                    break

            if endpoint_is_unique:
                connection.execute("""
                    ALTER TABLE push_subscriptions
                    RENAME TO push_subscriptions_old
                """)

                connection.execute("""
                    CREATE TABLE push_subscriptions (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        view_id INTEGER NOT NULL,
                        endpoint TEXT NOT NULL,
                        subscription_json TEXT NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE(view_id, endpoint),
                        FOREIGN KEY(view_id)
                            REFERENCES ticker_views(id)
                            ON DELETE CASCADE
                    )
                """)

                connection.execute("""
                    INSERT OR IGNORE INTO push_subscriptions (
                        view_id, endpoint, subscription_json, created_at
                    )
                    SELECT view_id, endpoint, subscription_json, created_at
                    FROM push_subscriptions_old
                """)

                connection.execute(
                    "DROP TABLE push_subscriptions_old"
                )


# --------------------------------------------------
# STOCK METADATA
# --------------------------------------------------

def get_stock_metadata(symbol):
    symbol = symbol.strip().upper()

    if not symbol:
        raise ValueError("Enter a ticker symbol.")

    ticker = yf.Ticker(symbol)

    try:
        history = ticker.history(period="5d", interval="1d")
    except Exception as error:
        raise ValueError(
            f"Yahoo Finance could not retrieve price history for {symbol}."
        ) from error

    if history.empty or "Close" not in history.columns:
        raise ValueError(
            f"No market data found for {symbol}. "
            "Check the ticker symbol or try again later."
        )

    history_close = history["Close"].dropna()

    if history_close.empty:
        raise ValueError(f"No usable prices were found for {symbol}.")

    info = {}

    try:
        info = ticker.get_info() or {}
    except Exception:
        app.logger.warning(
            "Company metadata unavailable for %s; using fallback.",
            symbol,
        )

    company_name = (
        info.get("longName")
        or info.get("shortName")
        or symbol
    )

    current_price = (
        info.get("regularMarketPrice")
        or info.get("currentPrice")
        or float(history_close.iloc[-1])
    )

    return {
        "ticker": symbol,
        "company_name": company_name,
        "exchange": (
            info.get("fullExchangeName")
            or info.get("exchange")
        ),
        "currency": info.get("currency"),
        "logo_url": (
            info.get("logo_url")
            or info.get("logoUrl")
        ),
        "current_price": current_price,
    }


def save_stock(metadata, indicators=None):
    indicators = indicators or {}

    with get_db_connection() as connection:
        connection.execute("""
            INSERT INTO stocks (
                ticker, company_name, exchange, currency, logo_url,
                current_price, price_change, price_change_percent,
                rsi, macd, macd_signal, relative_volume, last_updated
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(ticker) DO UPDATE SET
                company_name = excluded.company_name,
                exchange = excluded.exchange,
                currency = excluded.currency,
                logo_url = excluded.logo_url,
                current_price = COALESCE(
                    excluded.current_price, stocks.current_price
                ),
                price_change = COALESCE(
                    excluded.price_change, stocks.price_change
                ),
                price_change_percent = COALESCE(
                    excluded.price_change_percent,
                    stocks.price_change_percent
                ),
                rsi = COALESCE(excluded.rsi, stocks.rsi),
                macd = COALESCE(excluded.macd, stocks.macd),
                macd_signal = COALESCE(
                    excluded.macd_signal, stocks.macd_signal
                ),
                relative_volume = COALESCE(
                    excluded.relative_volume, stocks.relative_volume
                ),
                last_updated = COALESCE(
                    excluded.last_updated, stocks.last_updated
                )
        """, (
            metadata["ticker"],
            metadata["company_name"],
            metadata.get("exchange"),
            metadata.get("currency"),
            metadata.get("logo_url"),
            metadata.get("current_price"),
            indicators.get("price_change"),
            indicators.get("price_change_percent"),
            indicators.get("rsi"),
            indicators.get("macd"),
            indicators.get("macd_signal"),
            indicators.get("relative_volume"),
            indicators.get("last_updated"),
        ))


# --------------------------------------------------
# STOCK DATA HELPERS
# --------------------------------------------------

def get_stock_results(symbols):
    results = []

    for symbol in symbols:
        try:
            stock = get_stock_data(symbol)
            results.append({
                "symbol": symbol,
                "data": stock,
                "error": None,
            })
        except Exception as error:
            app.logger.exception(
                "Could not retrieve market data for %s", symbol
            )
            results.append({
                "symbol": symbol,
                "data": None,
                "error": str(error),
            })

    return results


# --------------------------------------------------
# TICKER VIEW DATABASE HELPERS
# --------------------------------------------------

def get_all_views():
    """Return saved views and remove views without tickers."""
    with get_db_connection() as connection:
        rows = connection.execute("""
            SELECT *
            FROM ticker_views
            ORDER BY id DESC
        """).fetchall()

        views = []
        empty_view_ids = []

        for row in rows:
            view = dict(row)

            try:
                tickers = json.loads(view["tickers"])
                if not isinstance(tickers, list):
                    tickers = []
            except (json.JSONDecodeError, TypeError):
                tickers = []

            view["tickers"] = tickers

            if not tickers:
                empty_view_ids.append(view["id"])
            else:
                views.append(view)

        if empty_view_ids:
            connection.executemany(
                "DELETE FROM ticker_views WHERE id = ?",
                [(view_id,) for view_id in empty_view_ids],
            )

    return views


def get_view(view_id):
    with get_db_connection() as connection:
        row = connection.execute("""
            SELECT *
            FROM ticker_views
            WHERE id = ?
        """, (view_id,)).fetchone()

    if row is None:
        return None

    view = dict(row)

    try:
        tickers = json.loads(view["tickers"])
        if not isinstance(tickers, list):
            tickers = []
    except (json.JSONDecodeError, TypeError):
        tickers = []

    view["tickers"] = tickers
    return view


# --------------------------------------------------
# STOCK LOOKUP API
# --------------------------------------------------

@app.route("/api/stock/<path:symbol>")
def stock_lookup(symbol):
    try:
        metadata = get_stock_metadata(symbol)

        return jsonify({
            "success": True,
            "stock": metadata,
        })

    except ValueError as error:
        return jsonify({
            "success": False,
            "error": str(error),
        }), 400

    except Exception:
        app.logger.exception(
            "Stock lookup failed for %s", symbol
        )

        return jsonify({
            "success": False,
            "error": "The stock lookup failed. Please try again.",
        }), 502


# --------------------------------------------------
# DASHBOARD
# --------------------------------------------------

@app.route("/")
@app.route("/index.html")
def index():
    views = get_all_views()

    symbols = list(dict.fromkeys(
        symbol
        for view in views
        for symbol in view["tickers"]
    ))

    stocks = get_stock_results(symbols)

    return render_template(
        "index.html",
        views=views,
        stocks=stocks,
    )


# --------------------------------------------------
# ALL SAVED TICKER VIEWS
# --------------------------------------------------

@app.route("/my_tables.html")
def my_tables():
    return render_template(
        "my_tables.html",
        views=get_all_views(),
    )


# --------------------------------------------------
# CREATE A TICKER VIEW
# --------------------------------------------------

@app.route("/create_ticker.html", methods=["GET", "POST"])
def create_ticker():
    if request.method == "GET":
        return render_template(
            "create_ticker.html",
            error=None,
            form_name="",
            selected_tickers=[],
            hourly_reports_checked=False,
        )

    name = request.form.get("name", "").strip()
    tickers_raw = request.form.get("tickers", "")

    tickers = list(dict.fromkeys(
        ticker.strip().upper()
        for ticker in tickers_raw.split(",")
        if ticker.strip()
    ))

    hourly_reports = (
        1 if request.form.get("hourly_reports") == "yes" else 0
    )

    form_values = {
        "form_name": name,
        "selected_tickers": tickers,
        "hourly_reports_checked": bool(hourly_reports),
    }

    if not name:
        return render_template(
            "create_ticker.html",
            error="Please enter a name for your ticker view.",
            **form_values,
        )

    if not tickers:
        return render_template(
            "create_ticker.html",
            error="Please add at least one stock ticker.",
            **form_values,
        )

    try:
        for symbol in tickers:
            indicators = get_stock_data(symbol)
            metadata = get_stock_metadata(symbol)
            save_stock(metadata, indicators)

        with get_db_connection() as connection:
            connection.execute("""
                INSERT INTO ticker_views (name, tickers, hourly_reports)
                VALUES (?, ?, ?)
            """, (name, json.dumps(tickers), hourly_reports))

    except ValueError as error:
        app.logger.warning(
            "Ticker view validation failed: %s", error
        )

        return render_template(
            "create_ticker.html",
            error=str(error),
            **form_values,
        )

    except Exception:
        app.logger.exception("Failed to save ticker view")

        return render_template(
            "create_ticker.html",
            error=(
                "Finsight couldn't retrieve or save the stock information. "
                "Please try again."
            ),
            **form_values,
        )

    flash(f'"{name}" was created successfully.', "success")
    return redirect(url_for("my_tables"))


# --------------------------------------------------
# OPEN A SAVED TICKER VIEW
# --------------------------------------------------

@app.route("/table.html")
def view_table():
    view_id = request.args.get("id", type=int)

    if view_id is None:
        flash("Please select a ticker view.", "error")
        return redirect(url_for("my_tables"))

    view = get_view(view_id)

    if view is None:
        flash("That ticker view could not be found.", "error")
        return redirect(url_for("my_tables"))

    if not view["tickers"]:
        with get_db_connection() as connection:
            connection.execute(
                "DELETE FROM ticker_views WHERE id = ?",
                (view_id,),
            )

        flash("That empty ticker view has been removed.", "error")
        return redirect(url_for("my_tables"))

    stocks = get_stock_results(view["tickers"])

    return render_template(
        "table.html",
        view=view,
        stocks=stocks,
        error=None,
    )


# --------------------------------------------------
# REMOVE A TICKER FROM A SAVED VIEW
# --------------------------------------------------

@app.route("/table/<int:view_id>/delete/<symbol>", methods=["POST"])
def delete_ticker_from_view(view_id, symbol):
    view = get_view(view_id)

    if view is None:
        flash("That ticker view could not be found.", "error")
        return redirect(url_for("my_tables"))

    symbol = symbol.strip().upper()
    tickers = view["tickers"]

    if symbol not in tickers:
        flash(f"{symbol} was not in that ticker view.", "error")
        return redirect(url_for("view_table", id=view_id))

    tickers.remove(symbol)

    with get_db_connection() as connection:
        if not tickers:
            connection.execute(
                "DELETE FROM ticker_views WHERE id = ?",
                (view_id,),
            )
            connection.execute(
                "DELETE FROM push_subscriptions WHERE view_id = ?",
                (view_id,),
            )
            flash(
                f"{view['name']} was deleted because it had no tickers left.",
                "success",
            )
        else:
            connection.execute("""
                UPDATE ticker_views
                SET tickers = ?
                WHERE id = ?
            """, (json.dumps(tickers), view_id))

            flash(
                f"{symbol} was removed from {view['name']}.",
                "success",
            )

    return redirect(url_for("my_tables"))


# --------------------------------------------------
# STOCK DETAIL PAGE
# --------------------------------------------------

@app.route("/stock/<symbol>")
def stock_detail(symbol):
    symbol = symbol.strip().upper()

    try:
        stock = get_stock_data(symbol)

        return render_template(
            "stock_detail.html",
            stock=stock,
            error=None,
        )

    except Exception:
        app.logger.exception(
            "Could not load stock detail for %s", symbol
        )

        return render_template(
            "stock_detail.html",
            stock=None,
            error=(
                f"Market data for {symbol} could not be loaded. "
                "Check the ticker symbol and try again."
            ),
        )


# --------------------------------------------------
# LOGIN AND SIGNUP
# --------------------------------------------------

@app.route("/login.html", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        if not email or not password:
            flash("Enter your email address and password.", "error")
            return render_template("login.html")

        with get_db_connection() as connection:
            user = connection.execute(
                """
                SELECT id, username, email, password_hash
                FROM users
                WHERE email = ? COLLATE NOCASE
                """,
                (email,),
            ).fetchone()

        if (
            user is None
            or not check_password_hash(user["password_hash"], password)
        ):
            flash("Email or password is incorrect.", "error")
            return render_template("login.html")

        session.clear()
        session["user_id"] = user["id"]
        session["username"] = user["username"]

        flash(f"Welcome back, {user['username']}!", "success")
        return redirect(url_for("index"))

    if session.get("user_id"):
        return redirect(url_for("index"))

    return render_template("login.html")


@app.route("/signup.html", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")

        if not username or not email or not password or not confirm_password:
            flash("Complete every field to create your account.", "error")
            return render_template("signup.html")

        if not re.fullmatch(r"[A-Za-z0-9_.-]{3,30}", username):
            flash(
                "Username must be 3–30 characters and use only letters, "
                "numbers, dots, underscores or hyphens.",
                "error",
            )
            return render_template("signup.html")

        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
            flash("Enter a valid email address.", "error")
            return render_template("signup.html")

        if len(password) < 8:
            flash(
                "Your password must be at least 8 characters long.",
                "error",
            )
            return render_template("signup.html")

        if password != confirm_password:
            flash("The passwords do not match.", "error")
            return render_template("signup.html")

        password_hash = generate_password_hash(password)

        try:
            with get_db_connection() as connection:
                cursor = connection.execute(
                    """
                    INSERT INTO users (username, email, password_hash)
                    VALUES (?, ?, ?)
                    """,
                    (username, email, password_hash),
                )
                user_id = cursor.lastrowid

        except sqlite3.IntegrityError:
            flash(
                "That username or email is already registered. "
                "Try signing in or use different details.",
                "error",
            )
            return render_template("signup.html")

        session.clear()
        session["user_id"] = user_id
        session["username"] = username

        flash("Your Finsight account has been created.", "success")
        return redirect(url_for("index"))

    if session.get("user_id"):
        return redirect(url_for("index"))

    return render_template("signup.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("You have been signed out.", "success")
    return redirect(url_for("index"))


# --------------------------------------------------
# WEB PUSH NOTIFICATIONS
# --------------------------------------------------

def get_vapid_public_key():
    if not PUBLIC_KEY_FILE.exists():
        raise RuntimeError("vapid_public_key.txt is missing.")

    return PUBLIC_KEY_FILE.read_text(encoding="utf-8").strip()


def send_push(subscription, title, body, url="/"):
    """Send a browser push notification."""
    if not PRIVATE_KEY.exists():
        app.logger.error("VAPID private key is missing.")
        return False

    payload = json.dumps({
        "title": title,
        "body": body,
        "url": url,
    })

    try:
        webpush(
            subscription_info=subscription,
            data=payload,
            vapid_private_key=str(PRIVATE_KEY),
            vapid_claims=VAPID_CLAIMS,
        )
        return True

    except WebPushException as error:
        app.logger.warning("Push delivery failed: %s", error)

        response = getattr(error, "response", None)

        if response is not None and response.status_code in (404, 410):
            with get_db_connection() as connection:
                connection.execute(
                    "DELETE FROM push_subscriptions WHERE endpoint = ?",
                    (subscription.get("endpoint"),),
                )

        return False

    except Exception:
        app.logger.exception("Unexpected push notification error")
        return False


@app.route("/service-worker.js")
def service_worker():
    return send_from_directory(
        app.root_path,
        "service-worker.js",
        mimetype="application/javascript",
    )


@app.route("/api/vapid-public-key")
def vapid_public_key():
    try:
        return jsonify({"publicKey": get_vapid_public_key()})

    except Exception:
        app.logger.exception("Could not load VAPID public key")
        return jsonify({
            "error": "Push notifications are not configured."
        }), 500


@app.route("/api/push/subscribe", methods=["POST"])
def subscribe_to_push():
    data = request.get_json(silent=True) or {}
    subscription = data.get("subscription")
    view_id = data.get("view_id")

    if not isinstance(subscription, dict):
        return jsonify({
            "error": "A browser subscription is required."
        }), 400

    endpoint = subscription.get("endpoint")

    if not isinstance(endpoint, str) or not endpoint.startswith("https://"):
        return jsonify({"error": "The push endpoint is invalid."}), 400

    try:
        view_id = int(view_id)
    except (TypeError, ValueError):
        return jsonify({"error": "Choose a valid ticker view."}), 400

    view = get_view(view_id)

    if view is None:
        return jsonify({"error": "Ticker view not found."}), 404

    with get_db_connection() as connection:
        connection.execute("""
            INSERT INTO push_subscriptions (
                view_id, endpoint, subscription_json
            )
            VALUES (?, ?, ?)
            ON CONFLICT(view_id, endpoint) DO UPDATE SET
                subscription_json = excluded.subscription_json
        """, (view_id, endpoint, json.dumps(subscription)))

    return jsonify({
        "success": True,
        "message": "Notifications enabled.",
    })


@app.route("/api/push/test", methods=["POST"])
def test_push():
    data = request.get_json(silent=True) or {}

    try:
        view_id = int(data.get("view_id"))
    except (TypeError, ValueError):
        return jsonify({"error": "Choose a valid ticker view."}), 400

    view = get_view(view_id)

    if view is None:
        return jsonify({"error": "Ticker view not found."}), 404

    with get_db_connection() as connection:
        rows = connection.execute("""
            SELECT endpoint, subscription_json
            FROM push_subscriptions
            WHERE view_id = ?
        """, (view_id,)).fetchall()

    if not rows:
        return jsonify({
            "error": "Enable notifications for this view first."
        }), 400

    delivered = 0

    for row in rows:
        subscription = json.loads(row["subscription_json"])

        if send_push(
            subscription,
            "Finsight test notification",
            f"Notifications are working for {view['name']}.",
            "/",
        ):
            delivered += 1

    if delivered:
        return jsonify({
            "success": True,
            "message": (
                f"Push service accepted {delivered} notification(s)."
            ),
        })

    return jsonify({
        "error": (
            "The push service did not accept the notification. "
            "Check the application logs for details."
        )
    }), 502


# --------------------------------------------------
# HOURLY REPORT GENERATOR
# --------------------------------------------------

def generate_hourly_reports():
    """Generate reports and notify browsers subscribed to enabled views."""
    app.logger.info("Starting scheduled Finsight hourly reports.")

    views = get_all_views()

    for view in views:
        if not view["hourly_reports"]:
            continue

        tickers = view["tickers"]

        if not tickers:
            continue

        report_lines = [
            "=" * 55,
            f"FINSIGHT HOURLY REPORT: {view['name']}",
            f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "=" * 55,
            "",
        ]

        for symbol in tickers:
            try:
                stock = get_stock_data(symbol)

                report_lines.append(
                    f"{symbol} — {stock['currency']} {stock['price']}"
                )
                report_lines.append(
                    f"Price change: {stock['price_change_percent']}%"
                )
                report_lines.append(f"RSI: {stock['rsi']}")
                report_lines.append(f"MACD: {stock['macd']}")
                report_lines.append(
                    f"MACD signal: {stock['macd_signal']}"
                )
                report_lines.append(
                    f"Relative volume: {stock['relative_volume']}"
                )
                report_lines.append(
                    f"Latest data: {stock['last_updated']}"
                )
                report_lines.append("")

                try:
                    metadata = get_stock_metadata(symbol)
                    save_stock(metadata, stock)
                except Exception:
                    app.logger.exception(
                        "Could not update saved metadata for %s", symbol
                    )

            except Exception:
                app.logger.exception(
                    "Hourly report failed for ticker %s", symbol
                )
                report_lines.append(
                    f"{symbol}: Market data could not be retrieved."
                )
                report_lines.append("")

        report = "\n".join(report_lines)
        app.logger.info("\n%s", report)

        with get_db_connection() as connection:
            subscriptions = connection.execute("""
                SELECT endpoint, subscription_json
                FROM push_subscriptions
                WHERE view_id = ?
            """, (view["id"],)).fetchall()

        for row in subscriptions:
            subscription = json.loads(row["subscription_json"])

            send_push(
                subscription,
                f"Finsight report: {view['name']}",
                f"Your hourly report is ready for {len(tickers)} ticker(s).",
                url=f"/table.html?id={view['id']}",
            )

    app.logger.info("Finished scheduled Finsight hourly reports.")


# --------------------------------------------------
# SCHEDULER
# --------------------------------------------------

scheduler = BackgroundScheduler(daemon=True)

scheduler.add_job(
    generate_hourly_reports,
    trigger="interval",
    hours=1,
    id="finsight_hourly_reports",
    replace_existing=True,
    max_instances=1,
    coalesce=True,
)


# --------------------------------------------------
# START THE APP
# --------------------------------------------------

initialise_database()

if __name__ == "__main__":
    if not scheduler.running:
        scheduler.start()

    app.logger.info("Finsight is running.")
    app.logger.info(
        "Hourly reports run every hour while the app is running."
    )

    app.run(debug=True, use_reloader=False)
