# VolunteerHub

VolunteerHub is a modern Flask web application that helps users discover, match with, and manage volunteer opportunities. It features personalized search, resume-based AI matching, interactive maps, user profiles, and an executive admin dashboard—all with a beautiful, user-friendly interface.

## Features

- **User Authentication**: Secure signup, login, and session management.
- **Opportunity Search & Filtering**: Find opportunities by keyword, event type, and city. Filter by conferences, hackathons, contests, competitions, and meetups.
- **Resume-Based AI Matching**: Upload your resume (PDF) and get matched to real opportunities using OpenAI GPT.
- **Interactive Map**: Visualize opportunities in your city with a modern, dark-mode map (Google Maps geocoding).
- **Profile Management**: Update your info, upload/view your resume, and manage your saved opportunities.
- **Admin Dashboard**: Executive dashboard for managing users and viewing stats. Promote users to admin.
- **Saved & Swipe**: Like, save, and swipe through opportunities. Remove saved items easily.
- **Robust Backend**: All data stored in SQLite databases with schema checks and duplicate cleanup utilities.
- **Modern UI**: Responsive, accessible, and visually appealing design throughout.

## Setup Instructions

### Prerequisites
- Python 3.10 or newer recommended
- [pip](https://pip.pypa.io/en/stable/)
- (Recommended) [virtualenv](https://virtualenv.pypa.io/en/latest/)

### 1. Clone the Repository
```sh
git clone https://github.com/yourusername/VolunteerHub.git
cd VolunteerHub
```

### 2. Create and Activate a Virtual Environment
```sh
python -m venv .venv
# On Windows:
.venv\Scripts\activate
# On Mac/Linux:
source .venv/bin/activate
```

### 3. Install Dependencies
```sh
pip install -r requirements.txt
```

### 4. Set Up API Keys
Create a `.env` file in the project root with your API keys:
```
OPENAI_API_KEY=your-openai-api-key
GOOGLE_MAPS_API_KEY=your-google-maps-api-key
ENCRYPTION_KEY=your-secret-key
```

### 5. Initialize the Databases
```sh
python createOpportunitiesDatabase.py
```

### 6. Run the App
```sh
python app.py
```
Visit [http://localhost:5000](http://localhost:5000) in your browser.

## Usage
- **Sign up** and log in to access all features.
- **Find Opportunities**: Use the search, swipe, or map features to discover events.
- **Resume Match**: Go to `/resume-match` or use the homepage button to upload your resume and get AI-powered matches.
- **Profile**: Update your info and manage your resume at `/profile`.
- **Admin Dashboard**: If you are an admin, access `/ _admin_dashboard` for user and opportunity management.

## Contributing
Pull requests are welcome! For major changes, please open an issue first to discuss what you would like to change.

## Support
If you encounter bugs or have questions, please open an issue or contact the maintainer.

---
**VolunteerHub** — Empowering communities, one opportunity at a time.

