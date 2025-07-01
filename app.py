from flask import Flask, render_template, request, redirect, session, jsonify, send_file
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
import requests
import time
import io
from SarvAuth import checkUserPassword
from werkzeug.utils import secure_filename
import pdfplumber

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
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}]
        )
        return response["choices"][0]["message"]["content"]
    except Exception as e:
        print(f"Error getting opportunities from ChatGPT: {e}")
        return None

def extract_opportunity_info(text, user_state=None):
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
            "state": re.search(r"State:\s*(.*?)(?:\n|$)", opp),
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
            "state": fields["state"].group(1).strip() if fields["state"] else (user_state or "Unknown State"),
            "location": fields["location"].group(1).strip() if fields["location"] else "Unknown Location",
            "duration": fields["duration"].group(1).strip() if fields["duration"] else "Not specified",
            "volunteers_needed": int(fields["volunteers_needed"].group(1)) if fields["volunteers_needed"] else 1,
            "contact_info": fields["contact_info"].group(1).strip() if fields["contact_info"] else "No contact information provided",
            "apply_link": fields["apply_link"].group(1).strip() if fields["apply_link"] else None
        }
        parsed_opportunities.append(opportunity)
    return parsed_opportunities

@app.route("/swipe", methods=["GET"])
def swipe():
    print(session.get("name"))
    if not session.get("name"):
        return redirect("/auth/login")

    # Get user id, city, and skills
    user_connection = sqlite3.connect("users.db")
    user_connection.row_factory = sqlite3.Row
    user_crsr = user_connection.cursor()
    user_crsr.execute("SELECT id, city, state, skills FROM users WHERE username = ?", (session["name"],))
    user = user_crsr.fetchone()
    user_connection.close()

    print(user)

    if not user or not user["city"]:
        return redirect("/auth/login")

    max_retries = 3
    retries = 0
    opportunities = []
    used_skills = get_user_skills(user)
    while retries < max_retries:
        connection = sqlite3.connect("opportunities.db")
        connection.row_factory = sqlite3.Row
        crsr = connection.cursor()
        if used_skills:
            # Personalized: prioritize matches by skills
            skill_clauses = []
            skill_params = []
            for skill in used_skills:
                skill_clauses.append("(LOWER(o.title) LIKE ? OR LOWER(o.description) LIKE ? OR LOWER(o.organization_name) LIKE ?)")
                skill_params.extend([f"%{skill}%"] * 3)
            skill_query = " AND (" + " OR ".join(skill_clauses) + ")" if skill_clauses else ""
            crsr.execute(f"""
                SELECT o.* FROM opportunities o
                LEFT JOIN user_opportunities uo ON o.id = uo.opportunity_id AND uo.user_id = ?
                WHERE uo.id IS NULL AND o.city LIKE ? {skill_query}
                ORDER BY RANDOM()
            """, [user["id"], f"%{user['city']}%"] + skill_params)
        else:
            # No skills: randomize
            crsr.execute("""
                SELECT o.* FROM opportunities o
                LEFT JOIN user_opportunities uo ON o.id = uo.opportunity_id AND uo.user_id = ?
                WHERE uo.id IS NULL AND o.city LIKE ?
                ORDER BY RANDOM()
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
            parsed_opportunities = extract_opportunity_info(opportunities_text, user["state"])
            connection = sqlite3.connect("opportunities.db")
            connection.row_factory = sqlite3.Row
            crsr = connection.cursor()
            inserted_count = 0
            for opp in parsed_opportunities:
                if insert_opportunity_safely(crsr, opp):
                    inserted_count += 1
            connection.commit()
            connection.close()
            print(f"Inserted {inserted_count} new opportunities for {user['city']}")
        retries += 1
    # PATCH: If no skills, set a flag for UI
    randomized = not used_skills
    return render_template("swipe.html", opportunities=opportunities, randomized=randomized)

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

    # Get user id, city, and skills
    user_connection = sqlite3.connect("users.db")
    user_connection.row_factory = sqlite3.Row
    user_crsr = user_connection.cursor()
    user_crsr.execute("SELECT id, city, skills FROM users WHERE username = ?", (session.get("name"),))
    user = user_crsr.fetchone()
    user_connection.close()

    if not user or not user["city"]:
        return redirect("/auth/login")

    # Get search/filter params
    keyword = request.args.get("keyword", "").strip()
    include_types = []
    if request.args.get('include_conferences'): include_types.append('conference')
    if request.args.get('include_hackathons'): include_types.append('hackathon')
    if request.args.get('include_contests'): include_types.append('contest')
    if request.args.get('include_competitions'): include_types.append('competition')
    if request.args.get('include_meetups'): include_types.append('meetup')
    all_keywords = [keyword] if keyword else []
    all_keywords += include_types

    used_skills = get_user_skills(user)
    connection = sqlite3.connect("opportunities.db")
    connection.row_factory = sqlite3.Row
    crsr = connection.cursor()
    query = """
        SELECT o.* FROM opportunities o
        LEFT JOIN user_opportunities uo ON o.id = uo.opportunity_id AND uo.user_id = ?
        WHERE o.city LIKE ?
    """
    params = [user["id"], f"%{user['city']}%"]
    if all_keywords:
        keyword_clauses = []
        keyword_params = []
        for kw in all_keywords:
            if kw:
                keyword_clauses.append("(LOWER(title) LIKE ? OR LOWER(description) LIKE ? OR LOWER(organization_name) LIKE ? OR LOWER(location) LIKE ?)")
                keyword_params.extend([f"%{kw.lower()}%"] * 4)
        if keyword_clauses:
            query += " AND (" + " OR ".join(keyword_clauses) + ")"
            params.extend(keyword_params)
    if used_skills:
        skill_clauses = []
        skill_params = []
        for skill in used_skills:
            skill_clauses.append("(LOWER(title) LIKE ? OR LOWER(description) LIKE ? OR LOWER(organization_name) LIKE ?)")
            skill_params.extend([f"%{skill}%"] * 3)
        if skill_clauses:
            query += " AND (" + " OR ".join(skill_clauses) + ")"
            params.extend(skill_params)
        query += " ORDER BY RANDOM()"
    else:
        query += " ORDER BY RANDOM()"
    crsr.execute(query, params)
    opportunities = [dict(row) for row in crsr.fetchall()]
    connection.close()
    randomized = not used_skills
    return render_template("all_opportunities.html", opportunities=opportunities, randomized=randomized)

@app.route("/opportunities", methods=["GET"])
def search_opportunities():
    if not session.get("name"):
        return redirect("/auth/login")

    keyword = request.args.get("keyword", "").strip()
    city = request.args.get("city", "").strip()

    # Get user id, city, and skills if not provided
    user_connection = sqlite3.connect("users.db")
    user_connection.row_factory = sqlite3.Row
    user_crsr = user_connection.cursor()
    user_crsr.execute("SELECT id, city, skills FROM users WHERE username = ?", (session.get("name"),))
    user = user_crsr.fetchone()
    user_connection.close()

    if not user:
        return redirect("/auth/login")

    search_city = city if city else user["city"]

    # After reading keyword and city:
    include_types = []
    if request.args.get('include_conferences'): include_types.append('conference')
    if request.args.get('include_hackathons'): include_types.append('hackathon')
    if request.args.get('include_contests'): include_types.append('contest')
    if request.args.get('include_competitions'): include_types.append('competition')
    if request.args.get('include_meetups'): include_types.append('meetup')

    # Combine keyword and event types for search
    all_keywords = [keyword] if keyword else []
    all_keywords += include_types

    used_skills = get_user_skills(user)
    connection = sqlite3.connect("opportunities.db")
    connection.row_factory = sqlite3.Row
    crsr = connection.cursor()
    query = "SELECT * FROM opportunities WHERE 1=1"
    params = []
    if search_city:
        query += " AND LOWER(city) LIKE ?"
        params.append(f"%{search_city.lower()}%")
    if all_keywords:
        keyword_clauses = []
        keyword_params = []
        for kw in all_keywords:
            if kw:
                keyword_clauses.append("(LOWER(title) LIKE ? OR LOWER(description) LIKE ? OR LOWER(organization_name) LIKE ? OR LOWER(location) LIKE ?)")
                keyword_params.extend([f"%{kw.lower()}%"] * 4)
        if keyword_clauses:
            query += " AND (" + " OR ".join(keyword_clauses) + ")"
            params.extend(keyword_params)
    if used_skills:
        skill_clauses = []
        skill_params = []
        for skill in used_skills:
            skill_clauses.append("(LOWER(title) LIKE ? OR LOWER(description) LIKE ? OR LOWER(organization_name) LIKE ?)")
            skill_params.extend([f"%{skill}%"] * 3)
        if skill_clauses:
            query += " AND (" + " OR ".join(skill_clauses) + ")"
            params.extend(skill_params)
        query += " ORDER BY RANDOM()"
    else:
        query += " ORDER BY RANDOM()"
    crsr.execute(query, params)
    opportunities = [dict(row) for row in crsr.fetchall()]
    connection.close()
    randomized = not used_skills
    return render_template("opportunities.html", opportunities=opportunities, randomized=randomized)

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
        parsed_opportunities = extract_opportunity_info(opportunities_text, user["state"])
        connection = sqlite3.connect("opportunities.db")
        connection.row_factory = sqlite3.Row
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
    if not opportunity or not all(opportunity.get(field) for field in ["title", "organization_name", "description", "location", "apply_link", "state"]):
        return False
    
    # Check for duplicates
    if is_duplicate_opportunity(crsr, opportunity):
        return False
    
    # Insert the opportunity
    crsr.execute("""
        INSERT INTO opportunities 
        (organization_name, title, description, location, city, state, contact_info, apply_link, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        opportunity["organization_name"].strip(),
        opportunity["title"].strip(),
        opportunity["description"].strip(),
        opportunity["location"].strip(),
        opportunity["city"].strip(),
        opportunity["state"].strip() if opportunity.get("state") else "Unknown State",
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
            saved_opportunities TEXT DEFAULT '[]',
            is_admin INTEGER DEFAULT 0,
            skills TEXT DEFAULT ''
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

def is_valid_url(url):
    try:
        if not url.startswith('http://') and not url.startswith('https://'):
            url = 'https://' + url
        resp = requests.head(url, allow_redirects=True, timeout=5)
        return resp.status_code in (200, 301, 302, 307, 308, 403)
    except Exception:
        return False

def geocode_address(address):
    """Geocode an address using Nominatim and return (lat, lng) or (None, None) if not found."""
    try:
        url = f"https://nominatim.openstreetmap.org/search"
        params = {"q": address, "format": "json", "limit": 1}
        headers = {"User-Agent": "VolunteerHub/1.0 (contact@volunteerhub.com)"}
        resp = requests.get(url, params=params, headers=headers, timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            if data:
                return float(data[0]["lat"]), float(data[0]["lon"])
    except Exception as e:
        print(f"Geocoding error for '{address}': {e}")
    return None, None

@app.route("/map", methods=["GET"])
def map_view():
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

    # Get search/filter params
    keyword = request.args.get("keyword", "").strip()
    include_types = []
    if request.args.get('include_conferences'): include_types.append('conference')
    if request.args.get('include_hackathons'): include_types.append('hackathon')
    if request.args.get('include_contests'): include_types.append('contest')
    if request.args.get('include_competitions'): include_types.append('competition')
    if request.args.get('include_meetups'): include_types.append('meetup')
    all_keywords = [keyword] if keyword else []
    all_keywords += include_types

    # Query all opportunities in user's city, with filtering
    connection = sqlite3.connect("opportunities.db")
    connection.row_factory = sqlite3.Row
    crsr = connection.cursor()
    query = "SELECT * FROM opportunities WHERE LOWER(city) LIKE ?"
    params = [f"%{user['city'].lower()}%"]
    if all_keywords:
        keyword_clauses = []
        keyword_params = []
        for kw in all_keywords:
            if kw:
                keyword_clauses.append("(LOWER(title) LIKE ? OR LOWER(description) LIKE ? OR LOWER(organization_name) LIKE ? OR LOWER(location) LIKE ?)")
                keyword_params.extend([f"%{kw.lower()}%"] * 4)
        if keyword_clauses:
            query += " AND (" + " OR ".join(keyword_clauses) + ")"
            params.extend(keyword_params)
    query += " ORDER BY created_at DESC"
    crsr.execute(query, params)
    opportunities = [dict(row) for row in crsr.fetchall()]
    connection.close()

    # Geocode addresses using Google Maps API, do NOT update DB
    GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY")
    def geocode_address_google(address):
        try:
            url = "https://maps.googleapis.com/maps/api/geocode/json"
            params = {"address": address, "key": GOOGLE_MAPS_API_KEY}
            resp = requests.get(url, params=params, timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("status") == "OK" and data["results"]:
                    loc = data["results"][0]["geometry"]["location"]
                    return float(loc["lat"]), float(loc["lng"])
        except Exception as e:
            print(f"Google Maps geocoding error for '{address}': {e}")
        return None, None

    map_opps = []
    for opp in opportunities:
        address = f"{opp.get('location', '')}, {opp.get('city', '')}"
        lat, lng = geocode_address_google(address)
        if lat and lng:
            map_opps.append({
                "title": opp["title"],
                "organization_name": opp["organization_name"],
                "description": opp["description"],
                "apply_link": opp["apply_link"],
                "lat": lat,
                "lng": lng
            })
    return render_template("map.html", opportunities=map_opps)

@app.route("/_admin_dashboard", methods=["GET", "POST"])
def admin_dashboard():
    if not session.get("name"):
        return redirect("/auth/login")
    # Check if user is admin in DB
    user_connection = sqlite3.connect("users.db")
    user_connection.row_factory = sqlite3.Row
    user_crsr = user_connection.cursor()
    user_crsr.execute("SELECT is_admin FROM users WHERE username = ?", (session.get("name"),))
    user = user_crsr.fetchone()
    if not user or not user["is_admin"]:
        user_connection.close()
        return "Access denied", 403

    # Handle admin promotion (persistent)
    message = None
    if request.method == "POST":
        promote_username = request.form.get("promote_username", "").strip()
        if promote_username:
            user_crsr.execute("SELECT * FROM users WHERE username = ?", (promote_username,))
            promote_user = user_crsr.fetchone()
            if promote_user:
                user_crsr.execute("UPDATE users SET is_admin = 1 WHERE username = ?", (promote_username,))
                user_connection.commit()
                message = f"User '{promote_username}' is now an admin."
            else:
                message = f"User '{promote_username}' not found."
    # Get stats
    user_crsr.execute("SELECT COUNT(*) FROM users")
    total_users = user_crsr.fetchone()[0]
    user_crsr.execute("SELECT COUNT(*) FROM users WHERE is_admin = 1")
    total_admins = user_crsr.fetchone()[0]
    user_connection.close()
    opp_connection = sqlite3.connect("opportunities.db")
    opp_crsr = opp_connection.cursor()
    opp_crsr.execute("SELECT COUNT(*) FROM opportunities")
    total_opps = opp_crsr.fetchone()[0]
    opp_connection.close()
    return render_template("admin_dashboard.html", total_users=total_users, total_admins=total_admins, total_opps=total_opps, message=message)

@app.route("/profile", methods=["GET", "POST"])
def profile():
    if not session.get("name"):
        return redirect("/auth/login")
    message = None
    user_connection = sqlite3.connect("users.db")
    user_connection.row_factory = sqlite3.Row
    user_crsr = user_connection.cursor()
    # Ensure birthday column exists
    try:
        user_crsr.execute("ALTER TABLE users ADD COLUMN birthday TEXT")
    except Exception:
        pass
    # Fetch user info
    user_crsr.execute("SELECT * FROM users WHERE username = ?", (session.get("name"),))
    user = user_crsr.fetchone()
    if not user:
        user_connection.close()
        return redirect("/auth/login")
    # Handle info/resume/skills update
    if request.method == "POST":
        # Info update
        name = request.form.get("name", user["name"])
        email = request.form.get("email", user["emailaddress"])
        city = request.form.get("city", user["city"])
        state = request.form.get("state", user["state"])
        birthday = request.form.get("birthday", user["birthday"] if "birthday" in user.keys() else None)
        password = request.form.get("password", None)
        skills = request.form.get("skills", user["skills"] if "skills" in user.keys() else "")
        update_fields = []
        update_values = []
        if name != user["name"]:
            update_fields.append("name = ?")
            update_values.append(name)
        if email != user["emailaddress"]:
            update_fields.append("emailaddress = ?")
            update_values.append(email)
        if city != user["city"]:
            update_fields.append("city = ?")
            update_values.append(city)
        if state != user["state"]:
            update_fields.append("state = ?")
            update_values.append(state)
        if birthday and (not user["birthday"] or birthday != user["birthday"]):
            update_fields.append("birthday = ?")
            update_values.append(birthday)
        if password and password != user["password"]:
            valid = checkUserPassword(user["username"], password)
            if not (isinstance(valid, list) and valid[0] is True):
                message = valid[1] if isinstance(valid, tuple) or isinstance(valid, list) and len(valid) > 1 else "Password does not meet requirements."
            else:
                update_fields.append("password = ?")
                update_values.append(password)
        if skills != (user["skills"] if "skills" in user.keys() else ""):
            update_fields.append("skills = ?")
            update_values.append(skills)
        # Resume upload and skill extraction
        if "resume" in request.files:
            file = request.files["resume"]
            if file and file.filename.lower().endswith(".pdf"):
                resume_data = file.read()
                if resume_data:
                    update_fields.append("resume = ?")
                    update_values.append(resume_data)
                    # Extract skills from resume using LLM
                    try:
                        import pdfplumber
                        import openai
                        import io
                        file_stream = io.BytesIO(resume_data)
                        with pdfplumber.open(file_stream) as pdf:
                            text = ''.join(page.extract_text() or '' for page in pdf.pages)
                        if text:
                            prompt = f"""
Given the following resume text, extract a concise, comma-separated list of the most relevant skills, areas of expertise, and interests for matching to volunteer opportunities. Only output the list, no extra text.

Resume:
{text}
"""
                            response = openai.ChatCompletion.create(
                                model="gpt-3.5-turbo",
                                messages=[{"role": "user", "content": prompt}]
                            )
                            skills_str = response["choices"][0]["message"]["content"].strip()
                            if skills_str:
                                update_fields.append("skills = ?")
                                update_values.append(skills_str)
                                skills = skills_str
                    except Exception as e:
                        print(f"Failed to extract skills from resume: {e}")
            elif file and file.filename:
                message = "Only PDF files are allowed."
        if update_fields and (not message or message == "Profile updated successfully."):
            update_values.append(session.get("name"))
            user_crsr.execute(f"UPDATE users SET {', '.join(update_fields)} WHERE username = ?", update_values)
            user_connection.commit()
            if not message:
                message = "Profile updated successfully."
        elif not message:
            message = "No changes made."
        # Re-fetch user after update
        user_crsr.execute("SELECT * FROM users WHERE username = ?", (session.get("name"),))
        user = user_crsr.fetchone()
    has_resume = user["resume"] is not None
    user_connection.close()
    return render_template("profile.html", user=user, has_resume=has_resume, message=message)

@app.route("/profile/resume")
def download_resume():
    if not session.get("name"):
        return redirect("/auth/login")
    user_connection = sqlite3.connect("users.db")
    user_connection.row_factory = sqlite3.Row
    user_crsr = user_connection.cursor()
    user_crsr.execute("SELECT resume FROM users WHERE username = ?", (session.get("name"),))
    user = user_crsr.fetchone()
    user_connection.close()
    if user and user["resume"]:
        return send_file(io.BytesIO(user["resume"]), mimetype="application/pdf", as_attachment=True, download_name="resume.pdf")
    return "No resume found.", 404

@app.route("/resume-match", methods=["GET", "POST"])
def resume_match():
    if not session.get("name"):
        return redirect("/auth/login")
    message = None
    matched_opportunities = []
    extracted_skills = []
    if request.method == "POST":
        if "resume" not in request.files:
            message = "No file part."
        else:
            file = request.files["resume"]
            if file.filename == "":
                message = "No selected file."
            elif not file.filename.lower().endswith(".pdf"):
                message = "Only PDF files are allowed."
            else:
                # Extract text from PDF using pdfplumber
                try:
                    file.seek(0)
                    with pdfplumber.open(file) as pdf:
                        text = ''.join(page.extract_text() or '' for page in pdf.pages)
                except Exception as e:
                    message = f"Failed to read PDF: {e}"
                    text = ""
                if text:
                    # Use LLM to extract skills/keywords
                    prompt = f"""
Given the following resume text, extract a concise, comma-separated list of the most relevant skills, areas of expertise, and interests for matching to volunteer opportunities. Only output the list, no extra text.

Resume:
{text}
"""
                    try:
                        response = openai.ChatCompletion.create(
                            model="gpt-3.5-turbo",
                            messages=[{"role": "user", "content": prompt}]
                        )
                        skills_str = response["choices"][0]["message"]["content"].strip()
                        extracted_skills = [s.strip() for s in skills_str.split(",") if s.strip()]
                    except Exception as e:
                        message = f"Failed to extract skills: {e}"
                        extracted_skills = []
                # Query opportunities DB for matches using the search logic
                if extracted_skills:
                    connection = sqlite3.connect("opportunities.db")
                    connection.row_factory = sqlite3.Row
                    crsr = connection.cursor()
                    # Build a query to match any of the skills in title, description, or organization_name
                    clauses = []
                    params = []
                    for skill in extracted_skills:
                        clauses.append("(LOWER(title) LIKE ? OR LOWER(description) LIKE ? OR LOWER(organization_name) LIKE ?)")
                        params.extend([f"%{skill.lower()}%"] * 3)
                    query = "SELECT * FROM opportunities"
                    if clauses:
                        query += " WHERE " + " OR ".join(clauses)
                    query += " ORDER BY created_at DESC LIMIT 20"
                    crsr.execute(query, params)
                    matched_opportunities = [dict(row) for row in crsr.fetchall()]
                    connection.close()
                    if not matched_opportunities:
                        # If no DB matches, ask ChatGPT for real, verifiable opportunities for these skills
                        chat_prompt = f"""
Given the following skills and interests: {', '.join(extracted_skills)}, generate 5 real, verifiable, and currently available volunteer opportunities from reputable organizations. For each, provide:

Organization Name: [Name]
Title: [Title]
Description: [Description]
City: [City]
State: [State]
Location: [Location]
Duration: [Duration]
Volunteers Needed: [Number]
Contact Info: [Contact Info]
Apply Link: [Apply Link]

Only include real opportunities with working links. Separate each opportunity with a blank line.
"""
                        try:
                            response = openai.ChatCompletion.create(
                                model="gpt-3.5-turbo",
                                messages=[{"role": "user", "content": chat_prompt}]
                            )
                            opp_text = response["choices"][0]["message"]["content"].strip()
                            # Use the extract_opportunity_info function to parse
                            matched_opportunities = extract_opportunity_info(opp_text)
                            if not matched_opportunities:
                                message = "No matching opportunities found for your resume, even from ChatGPT."
                        except Exception as e:
                            message = f"No matching opportunities found for your resume, and failed to fetch from ChatGPT: {e}"
    return render_template("resume_match.html", message=message, matched_opportunities=matched_opportunities, extracted_skills=extracted_skills)

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

# --- PATCH: Helper to get user skills as list ---
def get_user_skills(user):
    # Accepts either a dict or sqlite3.Row
    if isinstance(user, dict):
        skills_str = user.get("skills", "")
    else:
        # sqlite3.Row supports key access
        skills_str = user["skills"] if "skills" in user.keys() else ""
    if not skills_str:
        return []
    return [s.strip().lower() for s in skills_str.split(",") if s.strip()]
