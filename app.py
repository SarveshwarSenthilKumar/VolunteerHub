from flask import Flask, render_template, request, redirect, session, jsonify
from flask_session import Session
from datetime import datetime
import pytz
import openai
import os
import sqlite3
import json
from SarvAuth import * #Used for user authentication functions
from auth import auth_blueprint
import re

app = Flask(__name__)

app.config["SESSION_PERMANENT"] = True
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure OpenAI
openai.api_key = os.getenv('OPENAI_API_KEY')

autoRun = True #Change to True if you want to run the server automatically by running the app.py file
port = 5000 #Change to any port of your choice if you want to run the server automatically
authentication = True #Change to False if you want to disable user authentication

if authentication:
    app.register_blueprint(auth_blueprint, url_prefix='/auth')

#This route is the base route for the website which renders the index.html file
@app.route("/", methods=["GET", "POST"])
def index():
    if not authentication:
        return render_template("index.html")
    else:
        if not session.get("name"):
            return render_template("index.html", authentication=True)
        else:
            return render_template("/index.html")

def get_opportunities_from_chatgpt(city):
    prompt = f"""Generate 5 volunteer opportunities in {city}. For each opportunity, provide the following information in this exact format:

Organization Name: [Name]
Title: [Title]
Description: [Description]
City: [City]
Location: [Location]
Duration: [Duration]
Volunteers Needed: [Number]
Contact Info: [Contact Info]
Apply Link: [Apply Link]

Separate each opportunity with a blank line."""

    try:
        response = openai.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}]
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"Error getting opportunities from ChatGPT: {e}")
        return None

def extract_opportunity_info(text):
    # Split the text into individual opportunities
    opportunities = text.split('\n\n')
    parsed_opportunities = []
    for opp in opportunities:
        if not opp.strip():
            continue
        # Extract all fields using regex matching the prompt
        fields = {
            "organization_name": re.search(r"Organization Name:\s*(.*?)(?:\n|$)", opp),
            "title": re.search(r"Title:\s*(.*?)(?:\n|$)", opp),
            "description": re.search(r"Description:\s*(.*?)(?:\n|$)", opp),
            "city": re.search(r"City:\s*(.*?)(?:\n|$)", opp),
            "location": re.search(r"Location:\s*(.*?)(?:\n|$)", opp),
            "duration": re.search(r"Duration:\s*(.*?)(?:\n|$)", opp),
            "volunteers_needed": re.search(r"Volunteers Needed:\s*(\d+)", opp),
            "contact_info": re.search(r"Contact Info:\s*(.*?)(?:\n|$)", opp),
            "apply_link": re.search(r"Apply Link:\s*(.*?)(?:\n|$)", opp)
        }
        opportunity = {
            "organization_name": fields["organization_name"].group(1).strip() if fields["organization_name"] else "Unknown Organization",
            "title": fields["title"].group(1).strip() if fields["title"] else "Untitled Opportunity",
            "description": fields["description"].group(1).strip() if fields["description"] else "No description provided",
            "city": fields["city"].group(1).strip() if fields["city"] else "Unknown City",
            "location": fields["location"].group(1).strip() if fields["location"] else "Unknown Location",
            "duration": fields["duration"].group(1).strip() if fields["duration"] else "Not specified",
            "volunteers_needed": int(fields["volunteers_needed"].group(1)) if fields["volunteers_needed"] else 1,
            "contact_info": fields["contact_info"].group(1).strip() if fields["contact_info"] else "No contact information provided",
            "apply_link": fields["apply_link"].group(1).strip() if fields["apply_link"] else None
        }
        parsed_opportunities.append(opportunity)
    return parsed_opportunities

@app.route("/opportunities", methods=["GET"])
def opportunities():
    if not session.get("name"):
        return redirect("/auth/login")

    # Get user info
    user_connection = sqlite3.connect("users.db")
    user_connection.row_factory = sqlite3.Row
    user_crsr = user_connection.cursor()
    user_crsr.execute("SELECT city FROM users WHERE username = ?", (session["name"],))
    user = user_crsr.fetchone()
    user_connection.close()

    if not user or not user["city"]:
        return redirect("/")

    # Get search parameters
    keyword = request.args.get("keyword", "").strip()
    city = request.args.get("city", user["city"]).strip()

    # Fetch and store new opportunities from ChatGPT if not already present
    try:
        opportunities_text = get_opportunities_from_chatgpt(city)
        if opportunities_text:
            parsed_opportunities = extract_opportunity_info(opportunities_text)
            connection = sqlite3.connect("opportunities.db")
            crsr = connection.cursor()
            for opp in parsed_opportunities:
                crsr.execute("""
                    SELECT id FROM opportunities 
                    WHERE organization_name = ? AND title = ? AND description = ?
                """, (opp["organization_name"], opp["title"], opp["description"]))
                if not crsr.fetchone():
                    crsr.execute("""
                        INSERT INTO opportunities 
                        (organization_name, title, description, location, city, contact_info, apply_link, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        opp["organization_name"],
                        opp["title"],
                        opp["description"],
                        opp["location"],
                        opp["city"],
                        opp["contact_info"],
                        opp["apply_link"],
                        datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    ))
            connection.commit()
            connection.close()
    except Exception as e:
        print(f"Error fetching or storing opportunities: {e}")

    # Now search the database for matching opportunities
    connection = sqlite3.connect("opportunities.db")
    connection.row_factory = sqlite3.Row
    crsr = connection.cursor()
    query = "SELECT * FROM opportunities WHERE 1=1"
    params = []
    if keyword:
        query += " AND (organization_name LIKE ? OR title LIKE ? OR description LIKE ?)"
        params.extend([f"%{keyword}%", f"%{keyword}%", f"%{keyword}%"])
    if city:
        query += " AND city LIKE ?"
        params.append(f"%{city}%")
    query += " ORDER BY created_at DESC"
    crsr.execute(query, params)
    opportunities = [dict(row) for row in crsr.fetchall()]
    connection.close()

    return render_template("opportunities.html", opportunities=opportunities)

@app.route("/swipe", methods=["GET"])
def swipe():
    if not session.get("name"):
        return redirect("/auth/login")

    # Get user id and city
    user_connection = sqlite3.connect("users.db")
    user_connection.row_factory = sqlite3.Row
    user_crsr = user_connection.cursor()
    user_crsr.execute("SELECT id, city FROM users WHERE username = ?", (session["name"],))
    user = user_crsr.fetchone()
    user_connection.close()
    if not user or not user["city"]:
        return redirect("/auth/login")

    # Get all unswiped opportunities for this user
    connection = sqlite3.connect("opportunities.db")
    connection.row_factory = sqlite3.Row
    crsr = connection.cursor()
    crsr.execute("""
        SELECT o.* FROM opportunities o
        LEFT JOIN user_opportunities uo ON o.id = uo.opportunity_id AND uo.user_id = ?
        WHERE uo.id IS NULL AND o.city LIKE ?
        ORDER BY o.created_at DESC
    """, (user["id"], f"%{user['city']}%"))
    opportunities = [dict(row) for row in crsr.fetchall()]
    connection.close()

    return render_template("swipe.html", opportunities=opportunities)

@app.route("/swipe_action", methods=["POST"])
def swipe_action():
    if not session.get("name"):
        return jsonify({"error": "Not logged in"}), 401
    
    opportunity_id = request.json.get("opportunity_id")
    action = request.json.get("action")  # "like", "dislike", or "save"
    
    if not opportunity_id or not action:
        return jsonify({"error": "Missing parameters"}), 400
    
    # Get user id from users.db
    user_connection = sqlite3.connect("users.db")
    user_connection.row_factory = sqlite3.Row
    user_crsr = user_connection.cursor()
    user_crsr.execute("SELECT id, saved_opportunities FROM users WHERE username = ?", (session["name"],))
    user = user_crsr.fetchone()
    
    if action == "save":
        # Update saved opportunities in users table
        saved_opps = json.loads(user['saved_opportunities'] or '[]')
        if opportunity_id not in saved_opps:
            saved_opps.append(opportunity_id)
            user_crsr.execute("""
                UPDATE users 
                SET saved_opportunities = ? 
                WHERE username = ?
            """, (json.dumps(saved_opps), session["name"]))
            user_connection.commit()
    else:
        # Record the swipe in opportunities.db
        opp_connection = sqlite3.connect("opportunities.db")
        opp_crsr = opp_connection.cursor()
        opp_crsr.execute("""
            INSERT INTO user_opportunities (user_id, opportunity_id, status, created_at)
            VALUES (?, ?, ?, ?)
        """, (user['id'], opportunity_id, action, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        opp_connection.commit()
        opp_connection.close()
    
    user_connection.close()
    return jsonify({"success": True})

@app.route("/saved")
def saved_opportunities():
    if not session.get("name"):
        return redirect("/auth/login")
    # Get user's saved opportunities
    user_connection = sqlite3.connect("users.db")
    user_connection.row_factory = sqlite3.Row
    user_crsr = user_connection.cursor()
    user_crsr.execute("SELECT id, saved_opportunities FROM users WHERE username = ?", (session["name"],))
    user = user_crsr.fetchone()
    if not user:
        return redirect("/auth/login")
    # Parse saved opportunities
    saved_opps = json.loads(user['saved_opportunities'] or '[]')
    if not saved_opps:
        return render_template("saved.html", opportunities=[])
    # Get the full opportunity details
    opp_connection = sqlite3.connect("opportunities.db")
    opp_connection.row_factory = sqlite3.Row
    opp_crsr = opp_connection.cursor()
    placeholders = ','.join('?' * len(saved_opps))
    opp_crsr.execute(f"""
        SELECT * FROM opportunities 
        WHERE id IN ({placeholders})
        ORDER BY created_at DESC
    """, saved_opps)
    opportunities = [dict(row) for row in opp_crsr.fetchall()]
    # Add a default image_url if not present
    for opp in opportunities:
        if 'image_url' not in opp or not opp['image_url']:
            opp['image_url'] = '/static/default.jpg'
    opp_connection.close()
    user_connection.close()
    return render_template("saved.html", opportunities=opportunities)

@app.route("/auth/logout")
def logout():
    # Clear the session
    session.clear()
    # Redirect to the home page
    return redirect("/")

def init_db():
    # Initialize users database
    user_connection = sqlite3.connect("users.db")
    user_crsr = user_connection.cursor()
    
    # Drop existing users table if it exists
    user_crsr.execute("DROP TABLE IF EXISTS users")
    
    # Create users table with extended schema
    user_crsr.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            emailaddress TEXT UNIQUE NOT NULL,
            name TEXT,
            dateJoined TEXT,
            city TEXT,
            state TEXT,
            saved_opportunities TEXT DEFAULT '[]'
        )
    """)
    user_connection.commit()
    user_connection.close()

    # Initialize opportunities database
    opp_connection = sqlite3.connect("opportunities.db")
    opp_crsr = opp_connection.cursor()
    
    # Drop existing opportunities table if it exists
    opp_crsr.execute("DROP TABLE IF EXISTS opportunities")
    
    # Create opportunities table with apply_link field
    opp_crsr.execute("""
        CREATE TABLE IF NOT EXISTS opportunities (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            organization_name TEXT NOT NULL,
            title TEXT NOT NULL,
            description TEXT NOT NULL,
            city TEXT NOT NULL,
            location TEXT NOT NULL,
            duration TEXT,
            volunteers_needed INTEGER,
            contact_info TEXT,
            apply_link TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    opp_crsr.execute("""
        CREATE TABLE IF NOT EXISTS user_opportunities (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            opportunity_id INTEGER NOT NULL,
            status TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id),
            FOREIGN KEY (opportunity_id) REFERENCES opportunities (id)
        )
    """)
    opp_connection.commit()
    opp_connection.close()

# Call init_db when the app starts
init_db()

if autoRun:
    if __name__ == '__main__':
        app.run(debug=True, port=port)
