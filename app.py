from flask import Flask, render_template, request, redirect, session, jsonify
from flask_session import Session
from datetime import datetime, timedelta
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
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(days=30)  # Set session lifetime to 30 days
Session(app)

# Configure OpenAI
openai.api_key = os.getenv('OPENAI_API_KEY')

autoRun = True #Change to True if you want to run the server automatically by running the app.py file
port = 5000 #Change to any port of your choice if you want to run the server automatically
authentication = True #Change to False if you want to disable user authentication

if authentication:
    app.register_blueprint(auth_blueprint, url_prefix='/auth')

@app.before_request
def make_session_permanent():
    session.permanent = True

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

Separate each opportunity with a blank line. Ensure that the Apply Link is a valid, real-world URL (e.g., https://example.com/apply)."""

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

@app.route("/opportunities")
def opportunities():
    if not session.get("name"):
        return redirect("/auth/login")

    # Get user city
    user_connection = sqlite3.connect("users.db")
    user_connection.row_factory = sqlite3.Row
    user_crsr = user_connection.cursor()
    user_crsr.execute("SELECT city FROM users WHERE username = ?", (session["name"],))
    user = user_crsr.fetchone()
    user_connection.close()
    if not user or not user["city"]:
        return redirect("/auth/login")

    # Redirect to /swipe if user is logged in and has a city
    return redirect("/swipe")

@app.route("/swipe", methods=["GET"])
def swipe():
    print(session.get("name"))
    if not session.get("name"):
        return redirect("/auth/login")

    # Get user id and city
    user_connection = sqlite3.connect("users.db")
    user_connection.row_factory = sqlite3.Row
    user_crsr = user_connection.cursor()
    user_crsr.execute("SELECT id, city FROM users WHERE username = ?", (session["name"],))
    user = user_crsr.fetchone()
    user_connection.close()

    max_retries = 3
    retries = 0
    opportunities = []
    while retries < max_retries:
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
        # Filter out opportunities with missing/empty required fields
        opportunities = [opp for opp in opportunities if all(opp.get(field) for field in ["title", "organization_name", "description", "location", "apply_link"])]
        if opportunities:
            break
        # If none, fetch and store new ones
        opportunities_text = get_opportunities_from_chatgpt(user["city"])
        if opportunities_text:
            parsed_opportunities = extract_opportunity_info(opportunities_text)
            connection = sqlite3.connect("opportunities.db")
            crsr = connection.cursor()
            inserted_count = 0
            for opp in parsed_opportunities:
                if insert_opportunity_safely(crsr, opp):
                    inserted_count += 1
            connection.commit()
            connection.close()
            print(f"Inserted {inserted_count} new opportunities for {user['city']}")
            # Fetch the newly added opportunities
            connection = sqlite3.connect("opportunities.db")
            connection.row_factory = sqlite3.Row
            crsr = connection.cursor()
            crsr.execute("""
                SELECT o.* FROM opportunities o
                LEFT JOIN user_opportunities uo ON o.id = uo.opportunity_id AND uo.user_id = ?
                WHERE o.city LIKE ?
                ORDER BY o.created_at DESC
            """, (user["id"], f"%{user['city']}%"))
            opportunities = [dict(row) for row in crsr.fetchall()]
            connection.close()
        retries += 1
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

@app.route("/saved", methods=["GET"])
def saved():
    if not session.get("name"):
        return redirect("/auth/login")

    # Get user id
    user_connection = sqlite3.connect("users.db")
    user_connection.row_factory = sqlite3.Row
    user_crsr = user_connection.cursor()
    user_crsr.execute("SELECT id, saved_opportunities FROM users WHERE username = ?", (session["name"],))
    user = user_crsr.fetchone()
    user_connection.close()
    if not user:
        return redirect("/auth/login")

    # Get saved opportunities
    saved_opportunities = json.loads(user["saved_opportunities"])
    connection = sqlite3.connect("opportunities.db")
    connection.row_factory = sqlite3.Row
    crsr = connection.cursor()
    crsr.execute("SELECT * FROM opportunities WHERE id IN ({})".format(",".join("?" * len(saved_opportunities))), saved_opportunities)
    opportunities = [dict(row) for row in crsr.fetchall()]
    connection.close()

    return render_template("saved.html", opportunities=opportunities)

@app.route("/auth/logout")
def logout():
    # Clear the session
    session.clear()
    # Redirect to the home page
    return redirect("/")

@app.route("/all-opportunities")
def all_opportunities():
    if not session.get("name"):
        return redirect("/auth/login")

    # Get user id and city
    user_connection = sqlite3.connect("users.db")
    user_connection.row_factory = sqlite3.Row
    user_crsr = user_connection.cursor()
    user_crsr.execute("SELECT id, city FROM users WHERE username = ?", (session.get("name"),))
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
        WHERE o.city LIKE ?
        ORDER BY o.created_at DESC
    """, (user["id"], f"%{user['city']}%"))
    opportunities = [dict(row) for row in crsr.fetchall()]
    connection.close()

    # If no opportunities are found, fetch and store new ones
    if not opportunities:
        opportunities_text = get_opportunities_from_chatgpt(user["city"])
        if opportunities_text:
            parsed_opportunities = extract_opportunity_info(opportunities_text)
            connection = sqlite3.connect("opportunities.db")
            crsr = connection.cursor()
            inserted_count = 0
            for opp in parsed_opportunities:
                if insert_opportunity_safely(crsr, opp):
                    inserted_count += 1
            connection.commit()
            connection.close()
            print(f"Inserted {inserted_count} new opportunities for {user['city']}")
            # Fetch the newly added opportunities
            connection = sqlite3.connect("opportunities.db")
            connection.row_factory = sqlite3.Row
            crsr = connection.cursor()
            crsr.execute("""
                SELECT o.* FROM opportunities o
                LEFT JOIN user_opportunities uo ON o.id = uo.opportunity_id AND uo.user_id = ?
                WHERE o.city LIKE ?
                ORDER BY o.created_at DESC
            """, (user["id"], f"%{user['city']}%"))
            opportunities = [dict(row) for row in crsr.fetchall()]
            connection.close()

    return render_template("all_opportunities.html", opportunities=opportunities)

@app.route("/opportunities", methods=["GET"])
def search_opportunities():
    if not session.get("name"):
        return redirect("/auth/login")

    keyword = request.args.get("keyword", "").strip()
    city = request.args.get("city", "").strip()

    # Get user id and city if not provided
    user_connection = sqlite3.connect("users.db")
    user_connection.row_factory = sqlite3.Row
    user_crsr = user_connection.cursor()
    user_crsr.execute("SELECT id, city FROM users WHERE username = ?", (session.get("name"),))
    user = user_crsr.fetchone()
    user_connection.close()

    if not user:
        return redirect("/auth/login")

    search_city = city if city else user["city"]

    # Search in the database first
    connection = sqlite3.connect("opportunities.db")
    connection.row_factory = sqlite3.Row
    crsr = connection.cursor()
    query = "SELECT * FROM opportunities WHERE 1=1"
    params = []
    if search_city:
        query += " AND city LIKE ?"
        params.append(f"%{search_city}%")
    if keyword:
        query += " AND (title LIKE ? OR description LIKE ? OR organization_name LIKE ? OR location LIKE ?)"
        params.extend([f"%{keyword}%"] * 4)
    query += " ORDER BY created_at DESC"
    crsr.execute(query, params)
    opportunities = [dict(row) for row in crsr.fetchall()]
    connection.close()

    # If no results, fetch from ChatGPT
    if not opportunities and search_city:
        def get_opportunities_from_chatgpt_with_keyword(city, keyword):
            prompt = f"""Generate 5 volunteer opportunities in {city} that match the keyword '{keyword}'. For each opportunity, provide the following information in this exact format:\n\nOrganization Name: [Name]\nTitle: [Title]\nDescription: [Description]\nCity: [City]\nLocation: [Location]\nDuration: [Duration]\nVolunteers Needed: [Number]\nContact Info: [Contact Info]\nApply Link: [Apply Link]\n\nSeparate each opportunity with a blank line. Ensure that the Apply Link is a valid, real-world URL (e.g., https://example.com/apply)."""
            try:
                response = openai.chat.completions.create(
                    model="gpt-3.5-turbo",
                    messages=[{"role": "user", "content": prompt}]
                )
                return response.choices[0].message.content
            except Exception as e:
                print(f"Error getting opportunities from ChatGPT: {e}")
                return None
        
        opportunities_text = get_opportunities_from_chatgpt_with_keyword(search_city, keyword)
        if opportunities_text:
            parsed_opportunities = extract_opportunity_info(opportunities_text)
            connection = sqlite3.connect("opportunities.db")
            crsr = connection.cursor()
            inserted_count = 0
            for opp in parsed_opportunities:
                if insert_opportunity_safely(crsr, opp):
                    inserted_count += 1
            connection.commit()
            print(f"Inserted {inserted_count} new opportunities for {search_city} with keyword '{keyword}'")
            # Fetch again after inserting
            query = "SELECT * FROM opportunities WHERE 1=1"
            params = []
            if search_city:
                query += " AND city LIKE ?"
                params.append(f"%{search_city}%")
            if keyword:
                query += " AND (title LIKE ? OR description LIKE ? OR organization_name LIKE ? OR location LIKE ?)"
                params.extend([f"%{keyword}%"] * 4)
            query += " ORDER BY created_at DESC"
            crsr.execute(query, params)
            opportunities = [dict(row) for row in crsr.fetchall()]
            connection.close()

    return render_template("opportunities.html", opportunities=opportunities)

@app.route("/fetch_opportunities_background", methods=["POST"])
def fetch_opportunities_background():
    if not session.get("name"):
        return jsonify({"error": "Not logged in"}), 401

    # Get user city
    user_connection = sqlite3.connect("users.db")
    user_connection.row_factory = sqlite3.Row
    user_crsr = user_connection.cursor()
    user_crsr.execute("SELECT city FROM users WHERE username = ?", (session["name"],))
    user = user_crsr.fetchone()
    user_connection.close()

    if not user or not user["city"]:
        return jsonify({"error": "No city found for user"}), 400

    # Fetch new opportunities from ChatGPT
    opportunities_text = get_opportunities_from_chatgpt(user["city"])
    if opportunities_text:
        parsed_opportunities = extract_opportunity_info(opportunities_text)
        connection = sqlite3.connect("opportunities.db")
        crsr = connection.cursor()
        inserted_count = 0
        for opp in parsed_opportunities:
            if insert_opportunity_safely(crsr, opp):
                inserted_count += 1
        connection.commit()
        connection.close()
        print(f"Background: Inserted {inserted_count} new opportunities for {user['city']}")
        return jsonify({"success": True, "inserted_count": inserted_count})
    else:
        return jsonify({"success": False, "error": "Failed to fetch from ChatGPT"})

@app.route("/removesaved", methods=["POST"])
def remove_saved():
    if not session.get("name"):
        return jsonify({"error": "Not logged in"}), 401
    
    data = request.get_json()
    if not data or not data.get("opportunity_id"):
        return jsonify({"error": "Missing opportunity_id"}), 400
    
    opportunity_id = data.get("opportunity_id")
    
    # Get user and their saved opportunities
    user_connection = sqlite3.connect("users.db")
    user_connection.row_factory = sqlite3.Row
    user_crsr = user_connection.cursor()
    user_crsr.execute("SELECT id, saved_opportunities FROM users WHERE username = ?", (session["name"],))
    user = user_crsr.fetchone()
    
    if not user:
        user_connection.close()
        return jsonify({"error": "User not found"}), 404
    
    # Remove the opportunity from saved list
    saved_opportunities = json.loads(user["saved_opportunities"] or "[]")
    if str(opportunity_id) in saved_opportunities:
        saved_opportunities.remove(str(opportunity_id))
        user_crsr.execute("UPDATE users SET saved_opportunities = ? WHERE id = ?", (json.dumps(saved_opportunities), user["id"]))
        user_connection.commit()
        user_connection.close()
        return jsonify({"success": True})
    else:
        user_connection.close()
        return jsonify({"error": "Opportunity not found in saved list"}), 404

def normalize_text(text):
    """Normalize text for duplicate checking by converting to lowercase and trimming whitespace"""
    if not text:
        return ""
    return text.lower().strip()

def is_duplicate_opportunity(crsr, opportunity):
    """Check if an opportunity is a duplicate based on normalized fields"""
    if not opportunity:
        return False
    
    # Normalize the fields for comparison
    org_name = normalize_text(opportunity.get("organization_name", ""))
    title = normalize_text(opportunity.get("title", ""))
    apply_link = normalize_text(opportunity.get("apply_link", ""))
    
    # Check for exact matches first (most strict)
    if org_name and title:
        crsr.execute("""
            SELECT id FROM opportunities 
            WHERE LOWER(TRIM(organization_name)) = ? AND LOWER(TRIM(title)) = ?
        """, (org_name, title))
        if crsr.fetchone():
            return True
    
    # Check for similar organization name and title (fuzzy matching)
    if org_name and title:
        # Check if organization name and title are very similar (allowing for minor variations)
        crsr.execute("""
            SELECT id, organization_name, title FROM opportunities 
            WHERE LOWER(TRIM(organization_name)) LIKE ? AND LOWER(TRIM(title)) LIKE ?
        """, (f"%{org_name}%", f"%{title}%"))
        existing = crsr.fetchall()
        for row in existing:
            existing_org = normalize_text(row[1])
            existing_title = normalize_text(row[2])
            # If both org name and title are very similar (>80% match), consider it a duplicate
            if (existing_org in org_name or org_name in existing_org) and (existing_title in title or title in existing_title):
                return True
    
    # Check for duplicate apply links (if available)
    if apply_link:
        crsr.execute("""
            SELECT id FROM opportunities 
            WHERE LOWER(TRIM(apply_link)) = ?
        """, (apply_link,))
        if crsr.fetchone():
            return True
    
    return False

def insert_opportunity_safely(crsr, opportunity):
    """Safely insert an opportunity, checking for duplicates first"""
    if not opportunity or not all(opportunity.get(field) for field in ["title", "organization_name", "description", "location", "apply_link"]):
        return False
    
    # Check for duplicates
    if is_duplicate_opportunity(crsr, opportunity):
        return False
    
    # Insert the opportunity
    crsr.execute("""
        INSERT INTO opportunities 
        (organization_name, title, description, location, city, contact_info, apply_link, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        opportunity["organization_name"].strip(),
        opportunity["title"].strip(),
        opportunity["description"].strip(),
        opportunity["location"].strip(),
        opportunity["city"].strip(),
        opportunity["contact_info"].strip(),
        opportunity["apply_link"].strip(),
        datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ))
    return True

def init_db():
    # Initialize users database
    user_connection = sqlite3.connect("users.db")
    user_crsr = user_connection.cursor()
    
    # Create users table with extended schema if it doesn't exist
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
    
    # Create opportunities table with apply_link field if it doesn't exist
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
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(organization_name, title, apply_link)
        )
    """)
    
    # Add unique constraint if it doesn't exist (for existing databases)
    try:
        opp_crsr.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_opportunity_unique 
            ON opportunities(organization_name, title, apply_link)
        """)
    except:
        pass  # Index might already exist
    
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

def cleanup_duplicates():
    """Clean up existing duplicates in the opportunities database"""
    connection = sqlite3.connect("opportunities.db")
    crsr = connection.cursor()
    
    # Get all opportunities
    crsr.execute("SELECT id, organization_name, title, apply_link FROM opportunities ORDER BY created_at")
    all_opportunities = crsr.fetchall()
    
    seen_combinations = set()
    duplicates_to_remove = []
    
    for opp_id, org_name, title, apply_link in all_opportunities:
        # Normalize the fields
        org_name_norm = normalize_text(org_name)
        title_norm = normalize_text(title)
        apply_link_norm = normalize_text(apply_link)
        
        # Create a unique key for this opportunity
        key = (org_name_norm, title_norm, apply_link_norm)
        
        if key in seen_combinations:
            # This is a duplicate, mark for removal
            duplicates_to_remove.append(opp_id)
        else:
            seen_combinations.add(key)
    
    # Remove duplicates (keep the first occurrence)
    if duplicates_to_remove:
        crsr.execute("DELETE FROM opportunities WHERE id IN ({})".format(
            ",".join("?" * len(duplicates_to_remove))
        ), duplicates_to_remove)
        connection.commit()
        print(f"Removed {len(duplicates_to_remove)} duplicate opportunities")
    
    connection.close()
    return len(duplicates_to_remove)

@app.route("/cleanup-duplicates", methods=["POST"])
def cleanup_duplicates_route():
    if not session.get("name"):
        return jsonify({"error": "Not logged in"}), 401
    
    try:
        removed_count = cleanup_duplicates()
        return jsonify({"success": True, "removed_count": removed_count})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

# Initialize database tables if they don't exist
init_db()

# Clean up any existing duplicates
try:
    cleanup_duplicates()
except Exception as e:
    print(f"Error during duplicate cleanup: {e}")

if autoRun:
    if __name__ == '__main__':
        app.run(debug=True, port=port)
