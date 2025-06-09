from flask import Flask, render_template, request, redirect, session, jsonify, Blueprint
from flask_session import Session
from datetime import datetime
import pytz
import sqlite3
from SarvAuth import * #Used for user authentication functions

auth_blueprint = Blueprint('auth', __name__)

@auth_blueprint.route("/login", methods=["GET", "POST"])
def login():
        if session.get("name"):
            return redirect("/")
        if request.method == "GET":
            return render_template("/auth/login.html")
        else:
            username = request.form.get("username").strip().lower()
            password = request.form.get("password").strip()

            password = hash(password)

            connection = sqlite3.connect("users.db")
            connection.row_factory = sqlite3.Row
            crsr = connection.cursor()
            crsr.execute("SELECT * FROM users WHERE username = ?", (username,))
            users = crsr.fetchall()
            connection.close()

            if len(users) == 0:
                return render_template("/auth/login.html", error="No account has been found with this username!")
            user = users[0]
            if user["password"] == password:
                session["name"] = username
                return redirect("/")

            return render_template("/auth/login.html", error="You have entered an incorrect password! Please try again!")
    
@auth_blueprint.route("/signup", methods=["GET", "POST"])
def signup():
    if session.get("name"):
        return redirect("/")
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        email = request.form.get("email")
        city = request.form.get("city")
        state = request.form.get("state")
        name = request.form.get("name")
        dateJoined = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        if not username or not password or not email or not city or not state or not name:
            print(username, password, email, city, state, name)
            return render_template("signup.html", error="All fields are required")

        connection = sqlite3.connect("users.db")
        crsr = connection.cursor()
        crsr.execute("SELECT * FROM users WHERE username = ?", (username,))
        if crsr.fetchone():
            connection.close()
            return render_template("signup.html", error="Username already exists")

        crsr.execute("SELECT * FROM users WHERE email = ?", (email,))
        if crsr.fetchone():
            connection.close()
            return render_template("signup.html", error="Email already exists")

        try:
            crsr.execute("""
                INSERT INTO users (username, password, email, city, state, name, dateJoined, saved_opportunities)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (username, password, email, city, state, name, dateJoined, '[]'))
            connection.commit()
            connection.close()
            session["name"] = username
            return redirect("/")
        except Exception as e:
            connection.close()
            return render_template("signup.html", error=f"Error creating user: {e}")

    return render_template("signup.html")
    
@auth_blueprint.route("/logout")
def logout():
    session["name"] = None
    return redirect("/")
