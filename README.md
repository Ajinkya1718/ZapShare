# ZapShare -- Simple Chat and File Sharing Web App

A beginner-friendly web-based chat application built with Python, FastAPI, and SQLite.

## Features

- User Registration and Login
- Dashboard to see all registered users
- Chat with text messages
- File sharing (upload and download)
- Dark / Light mode toggle

## Tech Stack

- Backend: Python 3.10+, FastAPI, Uvicorn
- Database: SQLite (via sqlite3 module)
- Frontend: HTML, CSS, JavaScript (Jinja2 templates)
- Auth: Session-based login with SHA-256 password hashing

## Project Structure

    ZapShare/
     app/
        main.py           # All routes and app logic
        database.py       # SQLite database setup
        requirements.txt  # Python dependencies
        templates/        # HTML pages
           login.html
           register.html
           dashboard.html
           chat.html
        static/           # CSS and JS
           style.css
           script.js
        uploads/          # Uploaded files
     render.yaml           # Render deployment config
     README.md

## How to Run Locally

1. Install dependencies:
       pip install -r app/requirements.txt

2. Start the server:
       cd app
       uvicorn main:app --reload

3. Open browser: http://127.0.0.1:8000

## Deploy on Render

1. Push this repo to GitHub
2. Go to https://render.com and connect your repo
3. Use these settings:
       Build Command:  pip install -r app/requirements.txt
       Start Command:  cd app && uvicorn main:app --host 0.0.0.0 --port $PORT

Or simply click New > Blueprint and Render will auto-detect render.yaml.

## Routes

| Route              | Method   | Description              |
|--------------------|----------|--------------------------|
| /register          | GET/POST | User registration        |
| /login             | GET/POST | User login               |
| /logout            | GET      | Logout and clear session |
| /dashboard         | GET      | View all users           |
| /chat/{user_id}    | GET      | Chat with a user         |
| /send_message      | POST     | Send a text message      |
| /upload            | POST     | Upload a file            |
| /download/{file_id}| GET      | Download a shared file   |
