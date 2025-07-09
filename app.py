from flask import Flask, render_template, request, redirect, session, jsonify, send_file, url_for
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
import difflib

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

def get_opportunities_from_chatgpt(city, custom_prompt=None):
    system_prompt = (
        "You are a helpful assistant for a volunteer opportunities platform. "
        "If the user prompt or any input contains inappropriate, offensive, unsafe, or non-family-friendly content, "
        "Never return or generate any inappropriate, offensive, or unsafe content."
    )
    if custom_prompt:
        prompt = custom_prompt
    else:
        prompt = f"""Generate 5 volunteer opportunities in {city}. For each opportunity, provide the following information in this exact format:\n\nOrganization Name: [Name]\nTitle: [Title]\nDescription: [Description]\nCity: [City]\nLocation: [Location]\nDuration: [Duration]\nVolunteers Needed: [Number]\nContact Info: [Contact Info]\nApply Link: [Apply Link]\n\nSeparate each opportunity with a blank line. Ensure that the Apply Link is a valid, real-world URL (e.g., https://example.com/apply). Make sure these opportunities are real and currently available."""
    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt}
            ]
        )
        return response["choices"][0]["message"]["content"]
    except Exception as e:
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
            # Always fallback to user_state if not present
            "state": re.search(r"State:\s*(.*?)(?:\n|$)", opp) or None,
            "location": re.search(r"Location:\s*(.*?)(?:\n|$)", opp),
            "duration": re.search(r"Duration:\s*(.*?)(?:\n|$)", opp),
            "volunteers_needed": re.search(r"Volunteers Needed:\s*(\d+)", opp),
            "contact_info": re.search(r"Contact Info:\s*(.*?)(?:\n|$)", opp),
            "apply_link": re.search(r"Apply Link:\s*(.*?)(?:\n|$)", opp)
        }
        state_value = fields["state"].group(1).strip() if fields["state"] and hasattr(fields["state"], 'group') else (user_state or "Unknown State")
        opportunity = {
            "organization_name": fields["organization_name"].group(1).strip() if fields["organization_name"] else "Unknown Organization",
            "title": fields["title"].group(1).strip() if fields["title"] else "Untitled Opportunity",
            "description": fields["description"].group(1).strip() if fields["description"] else "No description provided",
            "city": fields["city"].group(1).strip() if fields["city"] else "Unknown City",
            "state": state_value,
            "location": fields["location"].group(1).strip() if fields["location"] else "Unknown Location",
            "duration": fields["duration"].group(1).strip() if fields["duration"] else "Not specified",
            "volunteers_needed": int(fields["volunteers_needed"].group(1)) if fields["volunteers_needed"] else 1,
            "contact_info": fields["contact_info"].group(1).strip() if fields["contact_info"] else "No contact information provided",
            "apply_link": fields["apply_link"].group(1).strip() if fields["apply_link"] else None
        }
        parsed_opportunities.append(opportunity)
    return parsed_opportunities

# --- PATCH: Use OpenAI Moderation API for inappropriate content filtering ---
def check_inappropriate_openai(text):
    if not text or not isinstance(text, str) or len(text.strip()) < 3:
        return False
    try:
        result = openai.Moderation.create(input=text)
        flagged = result['results'][0]['flagged']
        return flagged
    except Exception as e:
        return False

def filter_generic_skills(skills):
    GENERIC = {"volunteering", "volunteer", "helping", "service", "work", "project", "team", "organization", "member", "event", "events", "community", "leadership", "student", "group", "support"}
    return [s for s in skills if s not in GENERIC and len(s) > 2]

# PATCH: get_best_opportunities_with_label returns (results, randomized, fallback_label)
def get_best_opportunities_with_label(crsr, user_id, city, skills, base_query, base_params, skill_fields, min_results=1, debug_label=""):
    # If no skills, just show all matching opportunities (no skill filter)
    if not skills:
        query = base_query + " ORDER BY RANDOM()"
        crsr.execute(query, base_params)
        results = [dict(row) for row in crsr.fetchall()]
        results = [opp for opp in results if all(opp.get(field) for field in ["title", "organization_name", "description", "location", "apply_link"])]
        return results, True, "no-skills"
    attempts = []
    used_skills = [s for s in skills]
    attempts.append(("all", used_skills))
    filtered_skills = filter_generic_skills(used_skills)
    if filtered_skills and filtered_skills != used_skills:
        attempts.append(("filtered", filtered_skills))
    if len(filtered_skills) > 3:
        attempts.append(("top3", filtered_skills[:3]))
    attempts.append(("random", []))
    for label, skills_try in attempts:
        query = base_query
        params = list(base_params)
        if skills_try:
            skill_clauses = []
            skill_params = []
            for skill in skills_try:
                skill_clauses.append("(" + " OR ".join([f"LOWER({field}) LIKE ?" for field in skill_fields]) + ")")
                skill_params.extend([f"%{skill}%"] * len(skill_fields))
            query += " AND (" + " OR ".join(skill_clauses) + ")"
            params.extend(skill_params)
        query += " ORDER BY RANDOM()"
        crsr.execute(query, params)
        results = [dict(row) for row in crsr.fetchall()]
        results = [opp for opp in results if all(opp.get(field) for field in ["title", "organization_name", "description", "location", "apply_link"])]
        if len(results) >= min_results:
            return results, (label == "random"), label
    return results, True, "random"

@app.route("/swipe", methods=["GET"])
def swipe():
    if not session.get("name"):
        return redirect("/auth/login")
    user_connection = sqlite3.connect("users.db")
    user_connection.row_factory = sqlite3.Row
    user_crsr = user_connection.cursor()
    user_crsr.execute("SELECT id, city, state, skills FROM users WHERE username = ?", (session["name"],))
    user = user_crsr.fetchone()
    user_connection.close()
    if not user or not user["city"]:
        return redirect("/auth/login")
    used_skills = get_user_skills(user)
    if any(check_inappropriate_openai(skill) for skill in used_skills):
        return render_template("swipe.html", opportunities=[], randomized=False, error_message="Your skills/interests contain inappropriate or offensive language. Please update your profile.")
    connection = sqlite3.connect("opportunities.db")
    connection.row_factory = sqlite3.Row
    crsr = connection.cursor()
    # Use exact city match (case-insensitive)
    base_query = """
        SELECT o.* FROM opportunities o
        LEFT JOIN user_opportunities uo ON o.id = uo.opportunity_id AND uo.user_id = ?
        WHERE uo.id IS NULL AND LOWER(o.city) = LOWER(?)
    """
    base_params = [user["id"], user["city"]]
    skill_fields = ["o.title", "o.description", "o.organization_name"]
    opportunities, randomized, fallback_label = get_best_opportunities_with_label(crsr, user["id"], user["city"], used_skills, base_query, base_params, skill_fields, debug_label="swipe")
    connection.close()
    # If still empty, keep fetching from ChatGPT until we get at least one opportunity
    attempts = 0
    max_attempts = 3
    while not opportunities and attempts < max_attempts:
        chatgpt_prompt = f"Generate 5 volunteer opportunities in the city of '{user['city']}' related to the following skills: {', '.join(used_skills)}. For each opportunity, provide the following information in this exact format:\n\nOrganization Name: [Name]\nTitle: [Title]\nDescription: [Description]\nCity: [City]\nState: [State]\nLocation: [Location]\nDuration: [Duration]\nVolunteers Needed: [Number]\nContact Info: [Contact Info]\nApply Link: [Apply Link]\n\nSeparate each opportunity with a blank line. Ensure that the Apply Link is a valid, real-world URL (e.g., https://example.com/apply)."
        opportunities_text = get_opportunities_from_chatgpt(user["city"], custom_prompt=chatgpt_prompt)
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
            # Try again with fallback logic
            connection = sqlite3.connect("opportunities.db")
            connection.row_factory = sqlite3.Row
            crsr = connection.cursor()
            opportunities, randomized, fallback_label = get_best_opportunities_with_label(crsr, user["id"], user["city"], used_skills, base_query, base_params, skill_fields, debug_label=f"swipe-refetch-{attempts}")
            connection.close()
        attempts += 1
    rare_message = None
    if fallback_label == "random":
        rare_message = "That's quite a specialty, a rare one!"
    return render_template("swipe.html", opportunities=opportunities, randomized=randomized, rare_message=rare_message)

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

# PATCH: Improved event type extraction and fuzzy matching
EVENT_TYPE_ALIASES = {
    'conference': ['conference', 'conferences', 'conf', 'conf.', 'summit', 'symposium', 'forum'],
    'hackathon': ['hackathon', 'hackathons', 'hack', 'hackfest', 'codefest'],
    'contest': ['contest', 'contests', 'competition', 'competitions', 'comp', 'challenge', 'tournament'],
    'competition': ['competition', 'competitions', 'contest', 'contests', 'comp', 'challenge', 'tournament'],
    'meetup': ['meetup', 'meetups', 'meet-up', 'meet-ups', 'gathering', 'networking']
}
ALL_EVENT_ALIASES = set(a for v in EVENT_TYPE_ALIASES.values() for a in v)

def extract_event_types_from_text(text):
    found_types = set()
    text = text.lower()
    for etype, aliases in EVENT_TYPE_ALIASES.items():
        for alias in aliases:
            if alias in text:
                found_types.add(etype)
    # Fuzzy match for partials/typos
    words = text.split()
    for word in words:
        close = difflib.get_close_matches(word, ALL_EVENT_ALIASES, n=1, cutoff=0.75)
        if close:
            for etype, aliases in EVENT_TYPE_ALIASES.items():
                if close[0] in aliases:
                    found_types.add(etype)
    return list(found_types)

@app.route("/all-opportunities")
def all_opportunities():
    if not session.get("name"):
        return redirect("/auth/login")
    user_connection = sqlite3.connect("users.db")
    user_connection.row_factory = sqlite3.Row
    user_crsr = user_connection.cursor()
    user_crsr.execute("SELECT id, city, skills FROM users WHERE username = ?", (session.get("name"),))
    user = user_crsr.fetchone()
    user_connection.close()
    if not user or not user["city"]:
        return redirect("/auth/login")
    keyword = request.args.get("keyword", "").strip()
    include_types = [etype for etype in EVENT_TYPE_ALIASES if request.args.get(f'include_{etype}s')]
    extracted_types = extract_event_types_from_text(keyword) if keyword else []
    for etype in extracted_types:
        if etype not in include_types:
            include_types.append(etype)
    all_keywords = [e for e in include_types] + ([keyword] if keyword else [])
    used_skills = get_user_skills(user)
    flagged_skills = [skill for skill in used_skills if skill and len(skill.strip()) > 2 and check_inappropriate_openai(skill)]
    flagged_keywords = [kw for kw in all_keywords if kw and len(kw.strip()) > 2 and check_inappropriate_openai(kw)]
    if flagged_skills or flagged_keywords:
        return render_template("all_opportunities.html", opportunities=[], randomized=False, error_message="Your search contains inappropriate or offensive language. Please try again.")
    connection = sqlite3.connect("opportunities.db")
    connection.row_factory = sqlite3.Row
    crsr = connection.cursor()
    base_query = """
        SELECT o.* FROM opportunities o
        LEFT JOIN user_opportunities uo ON o.id = uo.opportunity_id AND uo.user_id = ?
        WHERE o.city LIKE ?
    """
    base_params = [user["id"], f"%{user['city']}%"]
    skill_fields = ["title", "description", "organization_name", "location"]
    event_only_mode = False
    if include_types and (not keyword or all(w in include_types for w in extract_event_types_from_text(keyword))):
        event_only_mode = True
    if event_only_mode:
        event_clauses = []
        event_params = []
        for etype in include_types:
            for alias in EVENT_TYPE_ALIASES[etype]:
                event_clauses.append("(" + " OR ".join([f"LOWER({field}) LIKE ?" for field in skill_fields]) + ")")
                event_params.extend([f"%{alias}%"] * len(skill_fields))
        if event_clauses:
            base_query += " AND (" + " OR ".join(event_clauses) + ")"
            base_params.extend(event_params)
        crsr.execute(base_query, base_params)
        opportunities = [dict(row) for row in crsr.fetchall()]
    else:
        combined_skills = used_skills + [kw.lower() for kw in all_keywords if kw]
        opportunities, randomized, fallback_label = get_best_opportunities_with_label(crsr, user["id"], user["city"], combined_skills, base_query, base_params, skill_fields, debug_label="all-opportunities")
    connection.close()
    # If no opportunities found and keyword is non-empty, use ChatGPT to generate plausible opportunities
    if not opportunities and keyword:
        chatgpt_prompt = f"""
Generate 5 real or plausible volunteer opportunities in {user['city']} for the keyword: '{keyword}'. For each opportunity, provide the following information in this exact format:

Organization Name: [Name]
Title: [Title]
Description: [Description]
City: [City]
State: [State]
Location: [Location]
Duration: [Duration]
Contact Info: [Contact Info]
Apply Link: [Apply Link]

Separate each opportunity with a blank line. Ensure that the Apply Link is a valid, real-world URL (e.g., https://example.com/apply)."""
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "system", "content": "You are a helpful assistant."}, {"role": "user", "content": chatgpt_prompt}],
            max_tokens=900,
            temperature=0.8
        )
        text = response['choices'][0]['message']['content']
        parsed_opportunities = extract_opportunity_info(text, user.get("state"))
        # Insert generated opportunities into the database
        connection = sqlite3.connect("opportunities.db")
        connection.row_factory = sqlite3.Row
        crsr = connection.cursor()
        for opp in parsed_opportunities:
            insert_opportunity_safely(crsr, opp)
        connection.commit()
        # Query again for the user
        crsr.execute(base_query, base_params)
        opportunities = [dict(row) for row in crsr.fetchall()]
        connection.close()
    rare_message = None
    if not event_only_mode and fallback_label == "random":
        rare_message = "That's quite a specialty, a rare one!"
    # After main query, if not event_only_mode and too few results, fill with random city/state opps
    MIN_OPPS = 10
    if not event_only_mode and len(opportunities) < MIN_OPPS:
        connection = sqlite3.connect("opportunities.db")
        connection.row_factory = sqlite3.Row
        crsr = connection.cursor()
        existing_ids = set(opp['id'] for opp in opportunities if 'id' in opp)
        user_state = user['state'] if 'state' in user.keys() else ''
        crsr.execute("SELECT * FROM opportunities WHERE city LIKE ? AND state LIKE ? ORDER BY RANDOM()", (f"%{user['city']}%", f"%{user_state}%"))
        for row in crsr.fetchall():
            if len(opportunities) >= MIN_OPPS:
                break
            if row['id'] not in existing_ids:
                opportunities.append(dict(row))
        connection.close()
    return render_template("all_opportunities.html", opportunities=opportunities, randomized=randomized, rare_message=rare_message, event_only_mode=event_only_mode)

@app.route("/opportunities", methods=["GET"])
def search_opportunities():
    if not session.get("name"):
        return redirect("/auth/login")
    keyword = request.args.get("keyword", "").strip()
    city = request.args.get("city", "").strip()
    user_connection = sqlite3.connect("users.db")
    user_connection.row_factory = sqlite3.Row
    user_crsr = user_connection.cursor()
    user_crsr.execute("SELECT id, city, skills, state FROM users WHERE username = ?", (session.get("name"),))
    user = user_crsr.fetchone()
    user_connection.close()
    if not user:
        return redirect("/auth/login")
    search_city = city if city else user["city"]
    event_types = list(EVENT_TYPE_ALIASES.keys())
    include_types = [etype for etype in event_types if request.args.get(f'include_{etype}s')]
    extracted_types = extract_event_types_from_text(keyword) if keyword else []
    for etype in extracted_types:
        if etype not in include_types:
            include_types.append(etype)
    all_keywords = [e for e in include_types] + ([keyword] if keyword else [])
    used_skills = get_user_skills(user)
    MAX_SKILLS = 5
    if len(used_skills) > MAX_SKILLS:
        used_skills = used_skills[:MAX_SKILLS]
    flagged_skills = [skill for skill in used_skills if skill and len(skill.strip()) > 2 and check_inappropriate_openai(skill)]
    flagged_keywords = [kw for kw in all_keywords if kw and len(kw.strip()) > 2 and check_inappropriate_openai(kw)]
    if flagged_skills or flagged_keywords:
        return render_template("opportunities.html", opportunities=[], randomized=False, error_message="Your search contains inappropriate or offensive language. Please try again.")
    connection = sqlite3.connect("opportunities.db")
    connection.row_factory = sqlite3.Row
    crsr = connection.cursor()
    base_query = "SELECT * FROM opportunities WHERE 1=1"
    base_params = []
    if search_city:
        base_query += " AND LOWER(city) LIKE ?"
        base_params.append(f"%{search_city.lower()}%")
    skill_fields = ["title", "description", "organization_name", "location"]
    # Determine if this is an event-only search
    event_only_mode = False
    if include_types and (not keyword or all(w in include_types for w in extract_event_types_from_text(keyword))):
        event_only_mode = True
    if event_only_mode:
        event_clauses = []
        event_params = []
        for etype in include_types:
            for alias in EVENT_TYPE_ALIASES[etype]:
                event_clauses.append("(" + " OR ".join([f"LOWER({field}) LIKE ?" for field in skill_fields]) + ")")
                event_params.extend([f"%{alias}%"] * len(skill_fields))
        if event_clauses:
            base_query += " AND (" + " OR ".join(event_clauses) + ")"
            base_params.extend(event_params)
        crsr.execute(base_query, base_params)
        opportunities = [dict(row) for row in crsr.fetchall()]
    else:
        combined_skills = used_skills + [kw.lower() for kw in all_keywords if kw]
        opportunities, randomized, fallback_label = get_best_opportunities_with_label(crsr, user["id"], search_city, combined_skills, base_query, base_params, skill_fields, debug_label="opportunities")
    connection.close()
    # If still empty, use ChatGPT to generate events (not just volunteer opps) for event types
    if event_only_mode and not opportunities and include_types:
        keyword_part = f". Every event must be directly about '{keyword}' and the keyword must appear as a whole word in the event's title or description." if keyword else ""
        chatgpt_prompt = f"Generate 5 real or plausible events (not just volunteer opportunities) in {search_city} for the following types: {', '.join(include_types)}{keyword_part} For each event, provide the following information in this exact format:\n\nOrganization Name: [Name]\nTitle: [Title]\nDescription: [Description]\nCity: [City]\nState: [State]\nLocation: [Location]\nDuration: [Duration]\nContact Info: [Contact Info]\nApply Link: [Apply Link]\n\nSeparate each event with a blank line. Ensure that the Apply Link is a valid, real-world URL (e.g., https://example.com/apply)."
        opportunities_text = get_opportunities_from_chatgpt(search_city, custom_prompt=chatgpt_prompt)
        if opportunities_text:
            parsed_opportunities = extract_opportunity_info(opportunities_text, user.get("state"))
            if keyword:
                keyword_lc = keyword.lower()
                before_count = len(parsed_opportunities)
                def keyword_in_text(text):
                    return bool(re.search(rf"\\b{re.escape(keyword_lc)}\\b", text.lower()))
                parsed_opportunities = [opp for opp in parsed_opportunities if keyword_in_text(opp.get('title', '')) or keyword_in_text(opp.get('description', ''))]
            connection = sqlite3.connect("opportunities.db")
            connection.row_factory = sqlite3.Row
            crsr = connection.cursor()
            inserted_count = 0
            for opp in parsed_opportunities:
                if insert_opportunity_safely(crsr, opp):
                    inserted_count += 1
            connection.commit()
            connection.close()
            # Try again with event-only query
            connection = sqlite3.connect("opportunities.db")
            connection.row_factory = sqlite3.Row
            crsr = connection.cursor()
            base_query2 = "SELECT * FROM opportunities WHERE 1=1"
            base_params2 = []
            if search_city:
                base_query2 += " AND LOWER(city) LIKE ?"
                base_params2.append(f"%{search_city.lower()}%")
            event_clauses = []
            event_params = []
            for etype in include_types:
                for alias in EVENT_TYPE_ALIASES[etype]:
                    event_clauses.append("(" + " OR ".join([f"LOWER({field}) LIKE ?" for field in skill_fields]) + ")")
                    event_params.extend([f"%{alias}%"] * len(skill_fields))
            if event_clauses:
                base_query2 += " AND (" + " OR ".join(event_clauses) + ")"
                base_params2.extend(event_params)
            if keyword:
                base_query2 += " AND (" + " OR ".join([f"LOWER({field}) LIKE ?" for field in skill_fields]) + ")"
                base_params2.extend([f"%{keyword.lower()}%"] * len(skill_fields))
            crsr.execute(base_query2, base_params2)
            opportunities = [dict(row) for row in crsr.fetchall()]
            connection.close()
            randomized = False
            # If still no results, show a user-friendly message
            if not opportunities:
                return render_template("opportunities.html", opportunities=[], randomized=False, rare_message=None, event_only_mode=event_only_mode, error_message="No events found for your search. Try a different keyword or event type.")
    rare_message = None
    if not event_only_mode and fallback_label == "random":
        rare_message = "That's quite a specialty, a rare one!"
    return render_template("opportunities.html", opportunities=opportunities, randomized=randomized, rare_message=rare_message, event_only_mode=event_only_mode)

@app.route("/fetch_opportunities_background", methods=["POST"])
def fetch_opportunities_background():
    if not session.get("name"):
        return jsonify({"error": "Not logged in"}), 401

    # Get user city and state
    user_connection = sqlite3.connect("users.db")
    user_connection.row_factory = sqlite3.Row
    user_crsr = user_connection.cursor()
    user_crsr.execute("SELECT city, state FROM users WHERE username = ?", (session["name"],))
    user = user_crsr.fetchone()
    user_connection.close()

    if not user or not user["city"]:
        return jsonify({"error": "No city found for user"}), 400

    # Get keyword from request (if present)
    data = request.get_json(silent=True)
    if not data:
        data = {}
    keyword = data.get("keyword", None)

    # Fetch new opportunities from ChatGPT
    if keyword:
        chatgpt_prompt = f"""Generate 5 volunteer opportunities in {user['city']} related to '{keyword}'. For each opportunity, provide the following information in this exact format:\n\nOrganization Name: [Name]\nTitle: [Title]\nDescription: [Description]\nCity: [City]\nLocation: [Location]\nDuration: [Duration]\nVolunteers Needed: [Number]\nContact Info: [Contact Info]\nApply Link: [Apply Link]\n\nSeparate each opportunity with a blank line. Ensure that the Apply Link is a valid, real-world URL (e.g., https://example.com/apply)."""
        opportunities_text = get_opportunities_from_chatgpt(user["city"], custom_prompt=chatgpt_prompt)
    else:
        opportunities_text = get_opportunities_from_chatgpt(user["city"])
    user_state = user["state"] if "state" in user.keys() else None
    if opportunities_text:
        parsed_opportunities = extract_opportunity_info(opportunities_text, user_state)
        connection = sqlite3.connect("opportunities.db")
        connection.row_factory = sqlite3.Row
        crsr = connection.cursor()
        inserted_count = 0
        for opp in parsed_opportunities:
            if insert_opportunity_safely(crsr, opp):
                inserted_count += 1
        connection.commit()
        connection.close()
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
            phone TEXT,
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
        pass
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
            pass
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
    if request.method == "POST" and "promote_username" in request.form:
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

    # User search logic
    search_query = request.args.get("search", "").strip()
    if search_query:
        user_crsr.execute("SELECT id, username, emailAddress, name, city, state, phone, dateJoined, saved_opportunities, is_admin, skills, birthday FROM users WHERE username LIKE ? ORDER BY id DESC", (f"%{search_query}%",))
    else:
        user_crsr.execute("SELECT id, username, emailAddress, name, city, state, phone, dateJoined, saved_opportunities, is_admin, skills, birthday FROM users ORDER BY id DESC")
    users = [dict(row) for row in user_crsr.fetchall()]

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
    return render_template("admin_dashboard.html", total_users=total_users, total_admins=total_admins, total_opps=total_opps, message=message, users=users, search_query=search_query)

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
        phone = request.form.get("phone", user["phone"])
        birthday = request.form.get("birthday", user["birthday"] if "birthday" in user.keys() else None)
        password = request.form.get("password", None)
        skills = request.form.get("skills", user["skills"] if "skills" in user.keys() else "")
        # Age validation
        if birthday:
            try:
                dob = datetime.strptime(birthday, '%Y-%m-%d')
                today = datetime.now()
                age = (today - dob).days // 365
                if age < 6:
                    message = "You must be at least 6 years old."
            except Exception:
                message = "Invalid birthday."
        # Phone validation (simple international/US number check)
        phone_pattern = r'^(\+\d{1,3}[- ]?)?\d{10}$'
        if phone and not re.match(phone_pattern, phone):
            message = "Please enter a valid phone number (10 digits, with optional country code)."
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
        if phone != user["phone"]:
            update_fields.append("phone = ?")
            update_values.append(phone)
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
                        pass
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
                            messages=[
                                {"role": "system", "content": SYSTEM_PROMPT},
                                {"role": "user", "content": prompt}
                            ]
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
                                messages=[
                                    {"role": "system", "content": SYSTEM_PROMPT},
                                    {"role": "user", "content": chat_prompt}
                                ]
                            )
                            opp_text = response["choices"][0]["message"]["content"].strip()
                            # Use the extract_opportunity_info function to parse
                            matched_opportunities = extract_opportunity_info(opp_text)
                            if not matched_opportunities:
                                message = "No matching opportunities found for your resume, even from ChatGPT."
                        except Exception as e:
                            message = f"No matching opportunities found for your resume, and failed to fetch from ChatGPT: {e}"
    return render_template("resume_match.html", message=message, matched_opportunities=matched_opportunities, extracted_skills=extracted_skills)

@app.route('/generate-ai-email', methods=['POST'])
def generate_ai_email():
    try:
        data = request.get_json()
        opportunity = data.get('opportunity', {})
        user_name = session.get('name', None)
        user_real_name = None
        user_skills = None
        if user_name:
            user_connection = sqlite3.connect('users.db')
            user_connection.row_factory = sqlite3.Row
            user_crsr = user_connection.cursor()
            user_crsr.execute('SELECT name, skills FROM users WHERE username = ?', (user_name,))
            user_row = user_crsr.fetchone()
            user_connection.close()
            if user_row:
                if user_row['name']:
                    user_real_name = user_row['name']
                if user_row['skills']:
                    user_skills = user_row['skills']
        signature = user_real_name or user_name or 'VolunteerHub User'
        skills_text = f"\nRelevant skills/experiences: {user_skills}" if user_skills else ""
        prompt = f"""
You are an assistant helping a volunteer write a professional, friendly, and human-sounding email to express interest in a volunteer opportunity.

Here is the opportunity information:
Title: {opportunity.get('title', '')}
Organization: {opportunity.get('organization_name', '')}
Description: {opportunity.get('description', '')}
Location: {opportunity.get('city', '')}, {opportunity.get('location', '')}
{skills_text}

Write a complete, detailed, and persuasive email with:
- A greeting (e.g., Dear [Organization] or Hello)
- A body expressing genuine interest, mentioning relevant skills/enthusiasm, and asking about next steps
- A polite closing and a single, professional signature using this name: {signature}
- Do NOT use any placeholders, brackets, or boilerplate like [Your Name] or [Organization]—fill in all information fully and naturally.
- Make the email more detailed, authentic, and persuasive than a generic template.
- Do NOT include any section labels like 'Body:', 'Closing:', or 'Signature:' in the output. Just write the email as it would be sent.
"""
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "system", "content": "You are a helpful assistant."}, {"role": "user", "content": prompt}],
            max_tokens=400,
            temperature=0.85
        )
        text = response['choices'][0]['message']['content']
        return jsonify({'email': text})
    except Exception as e:
        return jsonify({'error': f'Failed to generate email: {str(e)}'}), 500

@app.route('/ai-email')
def ai_email():
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
    if saved_opportunities:
        crsr.execute("SELECT * FROM opportunities WHERE id IN ({})".format(",".join(["?"]*len(saved_opportunities))), saved_opportunities)
        opportunities = [dict(row) for row in crsr.fetchall()]
    else:
        opportunities = []
    connection.close()
    return render_template("ai_email.html", opportunities=opportunities)

@app.route('/admin/add-opportunity', methods=['GET', 'POST'])
def admin_add_opportunity():
    if not session.get('name'):
        return redirect('/auth/login')
    # Check if user is admin
    user_connection = sqlite3.connect('users.db')
    user_connection.row_factory = sqlite3.Row
    user_crsr = user_connection.cursor()
    user_crsr.execute('SELECT is_admin FROM users WHERE username = ?', (session.get('name'),))
    user = user_crsr.fetchone()
    if not user or not user['is_admin']:
        user_connection.close()
        return 'Access denied', 403
    user_connection.close()
    message = None
    if request.method == 'POST':
        try:
            data = {
                'organization_name': request.form.get('organization_name'),
                'title': request.form.get('title'),
                'description': request.form.get('description'),
                'location': request.form.get('location'),
                'city': request.form.get('city'),
                'state': request.form.get('state'),
                'duration': request.form.get('duration'),
                'volunteers_needed': request.form.get('volunteers_needed'),
                'contact_info': request.form.get('contact_info'),
                'apply_link': request.form.get('apply_link'),
                'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'latitude': request.form.get('latitude'),
                'longitude': request.form.get('longitude'),
            }
            if not all([data['organization_name'], data['title'], data['description'], data['location'], data['city'], data['state'], data['contact_info'], data['apply_link']]):
                message = 'Please fill in all required fields.'
            else:
                conn = sqlite3.connect('opportunities.db')
                crsr = conn.cursor()
                crsr.execute('''
                    INSERT INTO opportunities (
                        organization_name, title, description, location, city, state, duration, volunteers_needed, contact_info, apply_link, created_at, latitude, longitude
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    data['organization_name'], data['title'], data['description'], data['location'], data['city'], data['state'], data['duration'], data['volunteers_needed'], data['contact_info'], data['apply_link'], data['created_at'], data['latitude'], data['longitude']
                ))
                conn.commit()
                conn.close()
                message = 'Opportunity added successfully!'
        except Exception as e:
            message = f'Error: {str(e)}'
    return render_template('admin_add_opportunity.html', message=message)

@app.route('/admin/opportunities', methods=['GET', 'POST'])
def admin_opportunities():
    if not session.get('name'):
        return redirect('/auth/login')
    # Check if user is admin
    user_connection = sqlite3.connect('users.db')
    user_connection.row_factory = sqlite3.Row
    user_crsr = user_connection.cursor()
    user_crsr.execute('SELECT is_admin FROM users WHERE username = ?', (session.get('name'),))
    user = user_crsr.fetchone()
    if not user or not user['is_admin']:
        user_connection.close()
        return 'Access denied', 403
    user_connection.close()
    message = request.args.get('message')
    search = request.args.get('search', '').strip()
    selected_city = request.args.get('city', '').strip()
    selected_organization = request.args.get('organization', '').strip()
    page = int(request.args.get('page', 1))
    per_page = 50
    offset = (page - 1) * per_page
    conn = sqlite3.connect('opportunities.db')
    conn.row_factory = sqlite3.Row
    crsr = conn.cursor()
    # Get unique cities and organizations for filters
    crsr.execute('SELECT DISTINCT city FROM opportunities ORDER BY city ASC')
    cities = [row['city'] for row in crsr.fetchall() if row['city']]
    crsr.execute('SELECT DISTINCT organization_name FROM opportunities ORDER BY organization_name ASC')
    organizations = [row['organization_name'] for row in crsr.fetchall() if row['organization_name']]
    # Build filter query
    filters = []
    params = []
    if search:
        filters.append('(title LIKE ? OR organization_name LIKE ? OR city LIKE ?)')
        params.extend([f'%{search}%', f'%{search}%', f'%{search}%'])
    if selected_city:
        filters.append('city = ?')
        params.append(selected_city)
    if selected_organization:
        filters.append('organization_name = ?')
        params.append(selected_organization)
    where_clause = 'WHERE ' + ' AND '.join(filters) if filters else ''
    # Count total
    crsr.execute(f'SELECT COUNT(*) FROM opportunities {where_clause}', params)
    total = crsr.fetchone()[0]
    # Fetch paged results
    crsr.execute(f'SELECT * FROM opportunities {where_clause} ORDER BY created_at DESC LIMIT ? OFFSET ?', params + [per_page, offset])
    opportunities = [dict(row) for row in crsr.fetchall()]
    conn.close()
    total_pages = (total + per_page - 1) // per_page
    return render_template('admin_opportunities.html', opportunities=opportunities, search=search, message=message, page=page, total_pages=total_pages, cities=cities, organizations=organizations, selected_city=selected_city, selected_organization=selected_organization)

@app.route('/admin/delete-opportunity/<int:opp_id>', methods=['POST'])
def admin_delete_opportunity(opp_id):
    if not session.get('name'):
        return redirect('/auth/login')
    # Check if user is admin
    user_connection = sqlite3.connect('users.db')
    user_connection.row_factory = sqlite3.Row
    user_crsr = user_connection.cursor()
    user_crsr.execute('SELECT is_admin FROM users WHERE username = ?', (session.get('name'),))
    user = user_crsr.fetchone()
    if not user or not user['is_admin']:
        user_connection.close()
        return 'Access denied', 403
    user_connection.close()
    conn = sqlite3.connect('opportunities.db')
    crsr = conn.cursor()
    crsr.execute('DELETE FROM opportunities WHERE id = ?', (opp_id,))
    conn.commit()
    conn.close()
    return redirect(url_for('admin_opportunities', message='Opportunity deleted.'))

# Initialize database tables if they don't exist
init_db()

# Clean up any existing duplicates
try:
    cleanup_duplicates()
except Exception as e:
    pass

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

# PATCH: Add system prompt for inappropriate content to resume skill extraction and resume-match
SYSTEM_PROMPT = (
    "You are a helpful assistant for a volunteer opportunities platform. "
    "If the user prompt or any input contains inappropriate, offensive, unsafe, or non-family-friendly content, "
    "refuse to generate results and respond with an error message indicating the input is inappropriate. "
    "Never return or generate any inappropriate, offensive, or unsafe content."
)
