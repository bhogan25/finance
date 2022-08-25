import os

import datetime

from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd, stocksPresent, hasSpecialChar

# Configure application
app = Flask(__name__)

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use PostgreSQL database
# db = SQL("sqlite:///finance.db")
uri = os.getenv("DATABASE_URL")
if uri.startswith("postgres://"):
    uri = uri.replace("postgres://", "postgresql://")
db = SQL("postgres://zekjpczysdaabz:9d719487a8260d0f21b6dbfe13e6944e57a839261a744821b82fefc30345aa98@ec2-34-203-182-65.compute-1.amazonaws.com:5432/ddqdd4rcv163tf")

# Make sure API key is set
if not os.environ.get("API_KEY"):
    raise RuntimeError("API_KEY not set")


@app.after_request
def after_request(response):
    """Ensure responses aren't cached"""
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""

    # Construct list of dictoinaries containing stock information {Symbol: , Total Shares: , Price: , Market Value: , Total Cost: , Avg Position: }
    stocksOwnedByUserList = db.execute(
        "SELECT DISTINCT symbol AS 'Symbol', SUM(shares) AS 'Total_Shares' FROM purchases_1 WHERE users_id = ? GROUP BY Symbol", session['user_id'])
    net_value = 0.00

    if stocksPresent(stocksOwnedByUserList):
        for stock in stocksOwnedByUserList:
            stockQuote = lookup(stock['Symbol'])
            stock['Price'] = "{0:.2f}".format(stockQuote['price'])  # usd(stockQuote['price'])
            market_value = stockQuote['price'] * stock['Total_Shares']
            net_value += market_value
            stock['Market_Value'] = "{0:.2f}".format(market_value)  # edit made here

            cost = 0
            positionList = db.execute("SELECT shares, pps FROM purchases_1 WHERE users_id = ? AND symbol = ?",
                                      session['user_id'], stock['Symbol'])
            for position in positionList:
                cost += position['shares'] * position['pps']
            stock['Total_Cost'] = usd(cost)
            stock['Avg_Position'] = usd(cost / stock['Total_Shares'])

        # Display total cash value and net account value
        extractCash = db.execute("SELECT id, cash FROM users WHERE id = ?", session['user_id'])
        cash = float("{0:.2f}".format(extractCash[0]['cash']))
        net_value = usd(net_value + cash)
        cash = usd(cash)
        return render_template("originalindex.html", stocksOwnedByUserList=stocksOwnedByUserList, cash=cash, net_value=net_value)
    else:
        # If no purchases_1 table are found Display total cash value and net account value
        extractCash = db.execute("SELECT id, cash FROM users WHERE id = ?", session['user_id'])
        cash = float("{0:.2f}".format(extractCash[0]['cash']))
        return render_template("originalindex.html", cash=cash, net_value=net_value)


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""

    if request.method == "POST":

        # Check user input for errors
        if not lookup(request.form.get("symbol")):
            return apology("Could not find a stock for the symbol entered", 400)

        try:
            shares = round(int(request.form.get("shares")))
        except:
            return apology("Shares must be entered as whole, positive numbers", 400)

        if shares <= 0:
            return apology("Share value must be greater than 0", 400)

        stock = lookup(request.form.get("symbol"))
        rows = db.execute("SELECT cash FROM users WHERE id = ?", session["user_id"])
        cash = round(rows[0]["cash"], 2)
        cost = round(shares * float(stock["price"]), 2)

        if (cost > cash):
            return apology("You do not have enough cash to make this purchase", 400)

        # Record purchase in purchases_1 table and history_1 table
        current_time = datetime.datetime.now()
        db.execute("INSERT INTO purchases_1 (users_id, symbol, pps, shares, datetime) VALUES (?, ?, ?, ?, ?)",
                   session['user_id'], stock['symbol'], stock['price'], shares, current_time)
        db.execute("INSERT INTO history_1 (user_id, transaction_type, symbol, price, shares, datetime) VALUES (?, ?, ?, ?, ?, ?)",
                   session['user_id'], "Buy",  stock['symbol'], stock['price'], shares, current_time)

        # Update users cash balance in "users" db table
        db.execute("UPDATE users SET cash = ? WHERE id = ?", round(cash-cost, 2), session['user_id'])

        # Fetch cash balance after transaction
        rows = db.execute("SELECT cash FROM users WHERE id = ?", session['user_id'])
        balance = rows[0]["cash"]

        # Tells user what they bought, how much, for how much and their current balance

        return redirect("/")
        # return render_template("bought.html", name=stock["name"], shares=shares, pps=stock["price"], cost=cost, balance=balance)

    else:
        return render_template("buy.html")


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""
    history = db.execute(
        "SELECT transaction_type, symbol, price, shares, datetime FROM history_1 WHERE user_id = ?", session["user_id"])
    for column in history:
        column['price'] = usd(column['price'])

    return render_template("history.html", history=history)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = ?", request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""
    if request.method == "POST":

        stock = lookup(request.form.get("symbol"))

        # If lookup does not return error
        if not stock:
            # return render_template("noquote.html")
            return apology("Umm... excuse me, you didn't enter a stock sym")

        name = stock["name"]
        price = usd(stock["price"])
        symbol = stock["symbol"]

        return render_template("quoted.html", name=name, price=price, symbol=symbol)

    else:
        return render_template("quote.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""

    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("Must provide username to register", 400)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("Must provide password to register", 400)

        elif request.form.get("password") != request.form.get("confirmation"):
            return apology("Both passwords provided must be the same", 400)

        # Query finance.db to check for possible duplicate username
        elif db.execute("SELECT * FROM users WHERE username = ?", request.form.get("username")):
            return apology("The username you entered has already been taken, please pick a different username", 400)

        # Insert into database if valid username and password provided
        else:
            new_username = request.form.get("username")
            new_password = generate_password_hash(request.form.get("password"))

            db.execute("INSERT INTO users (username, hash) VALUES (?, ?)", new_username, new_password)

            # Redirect to login page
            return redirect("/")

    else:
        return render_template("register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""

    if request.method == "POST":

        # Grab data from purchases_1 table
        id = int(request.form.get("id"))
        positions = db.execute(
            "SELECT id, users_id, symbol, shares, pps, datetime FROM purchases_1 WHERE users_id = ?", session['user_id'])
        for position in positions:
            if int(position['id']) == id:

                # Verify user data is received from html page
                try:
                    shares_sell = request.form.get("shares")

                    if hasSpecialChar(shares_sell):
                        return apology("No special characters allowed", 400)
                    else:
                        shares_sell = int(float(shares_sell))

                except:
                    return apology("Shares must be entered as whole, positive numbers", 400)

                shares_current = int(position["shares"])  # request.form.get("shares_current")
                pps = round(float(position["pps"]), 2)  # request.form.get("pps")
                user_id = int(position["users_id"])  # request.form.get("users_id")
                symbol = position["symbol"]
                sesh = int(session["user_id"])

                if (not shares_sell) or (not shares_current) or (not id) or (not pps) or (not user_id):
                    return apology("Cannot sell 0 shares", 400)

                # Verify user data being accessed by sessioned user
                if not user_id == sesh:
                    return apology("Session user does not match data being requested", 400)

                new_total_shares = shares_current - shares_sell

                # Record transaction in history_1 table
                current_time = datetime.datetime.now()
                db.execute("INSERT INTO history_1 (user_id, transaction_type, symbol, price, shares, datetime) VALUES (?, ?, ?, ?, ?, ?)",
                               sesh, 'Sell', symbol, pps, shares_sell, current_time)

                if new_total_shares > 0:
                    # SELL STOCK - UPDATE new share total at requested price in purchases_1 table
                    db.execute("UPDATE purchases_1 SET shares = ? WHERE id = ?", new_total_shares, int(position['id']))
                elif new_total_shares == 0:
                    # SELL STOCK - DELETE position row in purchases_1 table
                    db.execute("DELETE FROM purchases_1 WHERE id = ?", int(position['id']))
                else:
                    return apology("Cannot sell more shares (or 0 shares) then owned of a perticular position", 400)

                # Update cash balance in users table
                extractCash = db.execute("SELECT id, cash FROM users WHERE id = ?", session['user_id'])
                cash = extractCash[0]['cash'] + round(shares_sell * pps, 2)

                db.execute("UPDATE users SET cash = ? WHERE id = ?", cash, session["user_id"])

                return redirect("/sell")

    else:
        # Construct list of dictoinaries containing stock information {Symbol: , Company: , Total Shares: , Price: , Market Value: , Total Cost: , Avg Position: }
        stocksOwnedByUserList = db.execute(
            "SELECT DISTINCT symbol AS 'Symbol', SUM(shares) AS 'Total_Shares' FROM purchases_1 WHERE users_id = ? GROUP BY Symbol", session['user_id'])
        net_value = 0
        sesh = session['user_id']

        if stocksPresent(stocksOwnedByUserList):
            for stock in stocksOwnedByUserList:
                stockQuote = lookup(stock['Symbol'])
                stock['Price'] = usd(stockQuote['price'])
                stock['Company'] = stockQuote['name']
                market_value = stockQuote['price'] * stock['Total_Shares']
                net_value += market_value
                stock['Market_Value'] = usd(market_value)

                cost = 0
                positionList = db.execute(
                    "SELECT symbol, shares, pps, datetime FROM purchases_1 WHERE users_id = ? AND symbol = ?", session['user_id'], stock['Symbol'])

                for position in positionList:
                    cost += position['shares'] * position['pps']
                stock['Total_Cost'] = usd(cost)
                stock['Avg_Position'] = usd(cost / stock['Total_Shares'])

            # Display total cash value and net account value
            extractCash = db.execute("SELECT id, cash FROM users WHERE id = ?", session['user_id'])
            cash = extractCash[0]['cash']
            net_value = usd(net_value + cash)
            cash = usd(cash)

            positions = db.execute(
                "SELECT id, users_id, symbol, shares, pps, datetime FROM purchases_1 WHERE users_id = ?", session['user_id'])
            for position in positions:
                position['pps'] = usd(position['pps'])

            return render_template("sell.html", stocksOwnedByUserList=stocksOwnedByUserList, positions=positions, cash=cash, net_value=net_value, sesh=sesh)
        else:
            # Display total cash value and net account value
            extractCash = db.execute("SELECT id, cash FROM users WHERE id = ?", session['user_id'])
            cash = round(float(extractCash[0]['cash']), 2)
            net_value = usd(net_value + cash)
            cash = usd(cash)
            return render_template("sell.html", cash=cash, net_value=net_value)