"""
main.py — Main Application File for ZapShare

This is the main file that runs the FastAPI web application.
It contains all the routes (pages) for:
    - Registration
    - Login / Logout
    - Dashboard (see all users)
    - Chat (send messages & files)
    - File download

Run with:  uvicorn main:app --reload
"""

# ---- Imports ----
from fastapi import FastAPI, Request, Form, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
import hashlib
import os
import shutil

# Import our database functions
from database import get_db, init_db

# ---- Base Directory ----
# This ensures paths work correctly no matter where the server is started from
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ---- App Setup ----
app = FastAPI(title="ZapShare")

# Secret key for session middleware (keeps users logged in)
app.add_middleware(SessionMiddleware, secret_key="zapshare-secret-key-2026")

# Mount static files (CSS, JS) so the browser can load them
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")

# Setup Jinja2 templates (HTML files)
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))


# ---- Initialize Database on Startup ----
@app.on_event("startup")
def startup():
    """Called when the server starts. Creates database tables."""
    init_db()


# ---- Helper Functions ----

def hash_password(password: str) -> str:
    """
    Hashes a password using SHA-256.
    This converts plain text password into a secure hash.
    Example: "hello" -> "2cf24dba5fb0a30e..."
    """
    return hashlib.sha256(password.encode()).hexdigest()


def get_current_user(request: Request):
    """
    Checks if a user is logged in by reading the session.
    Returns user_id if logged in, None otherwise.
    """
    return request.session.get("user_id")


# ============================================================
#                       ROUTES (PAGES)
# ============================================================


# ---- 1. HOME PAGE — Redirects to Login ----
@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    """Redirect to login page when user visits the site."""
    # If already logged in, go to dashboard
    if get_current_user(request):
        return RedirectResponse(url="/dashboard", status_code=302)
    return RedirectResponse(url="/login", status_code=302)


# ---- 2. REGISTER PAGE ----
@app.get("/register", response_class=HTMLResponse)
def register_page(request: Request):
    """Show the registration form."""
    return templates.TemplateResponse("register.html", {
        "request": request,
        "error": None
    })


@app.post("/register", response_class=HTMLResponse)
def register(request: Request, username: str = Form(...), password: str = Form(...)):
    """
    Handle registration form submission.
    - Check if username already exists
    - If not, save user with hashed password
    - Redirect to login page
    """
    db = get_db()

    # Check if username is already taken
    existing_user = db.execute(
        "SELECT id FROM users WHERE username = ?", (username,)
    ).fetchone()

    if existing_user:
        db.close()
        return templates.TemplateResponse("register.html", {
            "request": request,
            "error": "Username already exists! Please choose another."
        })

    # Hash the password and save the new user
    hashed_pw = hash_password(password)
    db.execute(
        "INSERT INTO users (username, password) VALUES (?, ?)",
        (username, hashed_pw)
    )
    db.commit()
    db.close()

    # Redirect to login page after successful registration
    return RedirectResponse(url="/login?registered=1", status_code=302)


# ---- 3. LOGIN PAGE ----
@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request, registered: int = 0):
    """Show the login form."""
    return templates.TemplateResponse("login.html", {
        "request": request,
        "error": None,
        "success": "Registration successful! Please login." if registered else None
    })


@app.post("/login", response_class=HTMLResponse)
def login(request: Request, username: str = Form(...), password: str = Form(...)):
    """
    Handle login form submission.
    - Verify username and password
    - Save user_id in session
    - Redirect to dashboard
    """
    db = get_db()

    # Find user by username
    user = db.execute(
        "SELECT * FROM users WHERE username = ?", (username,)
    ).fetchone()
    db.close()

    # Check if user exists and password matches
    if user is None or user["password"] != hash_password(password):
        return templates.TemplateResponse("login.html", {
            "request": request,
            "error": "Invalid username or password!",
            "success": None
        })

    # Save user info in session (this keeps them logged in)
    request.session["user_id"] = user["id"]
    request.session["username"] = user["username"]

    return RedirectResponse(url="/dashboard", status_code=302)


# ---- 4. LOGOUT ----
@app.get("/logout")
def logout(request: Request):
    """Clear session and redirect to login page."""
    request.session.clear()
    return RedirectResponse(url="/login", status_code=302)


# ---- 5. DASHBOARD PAGE ----
@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request):
    """
    Show the dashboard with a list of all registered users.
    The logged-in user can click on any user to start chatting.
    """
    user_id = get_current_user(request)
    if not user_id:
        return RedirectResponse(url="/login", status_code=302)

    db = get_db()

    # Get all users EXCEPT the currently logged-in user
    users = db.execute(
        "SELECT id, username FROM users WHERE id != ?", (user_id,)
    ).fetchall()
    db.close()

    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "username": request.session.get("username"),
        "users": users
    })


# ---- 6. CHAT PAGE ----
@app.get("/chat/{receiver_id}", response_class=HTMLResponse)
def chat_page(request: Request, receiver_id: int):
    """
    Show the chat page between the logged-in user and another user.
    Displays previous messages and files, with forms to send new ones.
    """
    user_id = get_current_user(request)
    if not user_id:
        return RedirectResponse(url="/login", status_code=302)

    db = get_db()

    # Get the receiver's info
    receiver = db.execute(
        "SELECT id, username FROM users WHERE id = ?", (receiver_id,)
    ).fetchone()

    if not receiver:
        db.close()
        return RedirectResponse(url="/dashboard", status_code=302)

    # Get all users for the sidebar (excluding self)
    users = db.execute(
        "SELECT id, username FROM users WHERE id != ?", (user_id,)
    ).fetchall()

    # Get all messages between these two users (in both directions)
    messages = db.execute("""
        SELECT m.*, u.username as sender_name
        FROM messages m
        JOIN users u ON m.sender_id = u.id
        WHERE (m.sender_id = ? AND m.receiver_id = ?)
           OR (m.sender_id = ? AND m.receiver_id = ?)
        ORDER BY m.timestamp ASC
    """, (user_id, receiver_id, receiver_id, user_id)).fetchall()

    # Get all files shared between these two users
    files = db.execute("""
        SELECT f.*, u.username as sender_name
        FROM files f
        JOIN users u ON f.sender_id = u.id
        WHERE (f.sender_id = ? AND f.receiver_id = ?)
           OR (f.sender_id = ? AND f.receiver_id = ?)
        ORDER BY f.timestamp ASC
    """, (user_id, receiver_id, receiver_id, user_id)).fetchall()

    db.close()

    return templates.TemplateResponse("chat.html", {
        "request": request,
        "username": request.session.get("username"),
        "user_id": user_id,
        "receiver": receiver,
        "users": users,
        "messages": messages,
        "files": files
    })


# ---- 7. SEND MESSAGE (form-based, redirects back) ----
@app.post("/send_message")
def send_message(
    request: Request,
    receiver_id: int = Form(...),
    content: str = Form(...)
):
    """Save a new text message to the database."""
    user_id = get_current_user(request)
    if not user_id:
        return RedirectResponse(url="/login", status_code=302)

    db = get_db()
    db.execute(
        "INSERT INTO messages (sender_id, receiver_id, content) VALUES (?, ?, ?)",
        (user_id, receiver_id, content)
    )
    db.commit()
    db.close()

    # Redirect back to the chat page
    return RedirectResponse(url=f"/chat/{receiver_id}", status_code=302)


# ---- 7b. SEND MESSAGE (JSON API — used by auto-refresh JS) ----
@app.post("/api/send")
async def api_send_message(request: Request):
    """
    Accepts a JSON POST with {receiver_id, content}.
    Saves the message and returns it as JSON.
    Used by the frontend fetch() call so page doesn't reload on send.
    """
    user_id = get_current_user(request)
    if not user_id:
        return JSONResponse({"error": "not logged in"}, status_code=401)

    data = await request.json()
    receiver_id = data.get("receiver_id")
    content = data.get("content", "").strip()

    if not content or not receiver_id:
        return JSONResponse({"error": "missing fields"}, status_code=400)

    db = get_db()
    cursor = db.execute(
        "INSERT INTO messages (sender_id, receiver_id, content) VALUES (?, ?, ?)",
        (user_id, receiver_id, content)
    )
    msg_id = cursor.lastrowid
    db.commit()

    # Fetch back the saved message with timestamp and sender name
    msg = db.execute("""
        SELECT m.id, m.content, m.timestamp, m.sender_id, u.username as sender_name
        FROM messages m
        JOIN users u ON m.sender_id = u.id
        WHERE m.id = ?
    """, (msg_id,)).fetchone()
    db.close()

    return dict(msg)


# ---- 7c. POLL MESSAGES (JSON API — used for auto-refresh) ----
@app.get("/api/messages/{receiver_id}")
def api_get_messages(
    request: Request,
    receiver_id: int,
    after_msg: int = 0,
    after_file: int = 0
):
    """
    Returns new messages and files as JSON.
    'after_msg' and 'after_file' are the last IDs the client already has.
    The client calls this every 2 seconds to get new content.
    """
    user_id = get_current_user(request)
    if not user_id:
        return JSONResponse({"error": "not logged in"}, status_code=401)

    db = get_db()

    # Get new messages with ID greater than what the client already has
    messages = db.execute("""
        SELECT m.id, m.content, m.timestamp, m.sender_id, u.username as sender_name
        FROM messages m
        JOIN users u ON m.sender_id = u.id
        WHERE ((m.sender_id = ? AND m.receiver_id = ?)
           OR  (m.sender_id = ? AND m.receiver_id = ?))
          AND m.id > ?
        ORDER BY m.timestamp ASC
    """, (user_id, receiver_id, receiver_id, user_id, after_msg)).fetchall()

    # Get new files with ID greater than what the client already has
    files = db.execute("""
        SELECT f.id, f.filename, f.timestamp, f.sender_id, u.username as sender_name
        FROM files f
        JOIN users u ON f.sender_id = u.id
        WHERE ((f.sender_id = ? AND f.receiver_id = ?)
           OR  (f.sender_id = ? AND f.receiver_id = ?))
          AND f.id > ?
        ORDER BY f.timestamp ASC
    """, (user_id, receiver_id, receiver_id, user_id, after_file)).fetchall()

    db.close()

    return {
        "messages": [dict(m) for m in messages],
        "files": [dict(f) for f in files],
        "user_id": user_id
    }


# ---- 8. UPLOAD FILE ----
@app.post("/upload")
async def upload_file(
    request: Request,
    receiver_id: int = Form(...),
    file: UploadFile = File(...)
):
    """
    Handle file upload.
    - Save the file to the uploads/ folder
    - Store file info in the database
    """
    user_id = get_current_user(request)
    if not user_id:
        return RedirectResponse(url="/login", status_code=302)

    # Create a unique filename to avoid conflicts
    # Format: senderID_receiverID_originalname
    safe_filename = f"{user_id}_{receiver_id}_{file.filename}"
    file_path = os.path.join(BASE_DIR, "uploads", safe_filename)

    # Save the file to disk
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    # Save file metadata to database
    db = get_db()
    db.execute(
        "INSERT INTO files (sender_id, receiver_id, filename, filepath) VALUES (?, ?, ?, ?)",
        (user_id, receiver_id, file.filename, file_path)
    )
    db.commit()
    db.close()

    # Redirect back to chat page
    return RedirectResponse(url=f"/chat/{receiver_id}", status_code=302)


# ---- 9. DOWNLOAD FILE ----
@app.get("/download/{file_id}")
def download_file(request: Request, file_id: int):
    """
    Download a shared file by its ID.
    Uses FileResponse to send the file to the browser.
    """
    user_id = get_current_user(request)
    if not user_id:
        return RedirectResponse(url="/login", status_code=302)

    db = get_db()
    file_record = db.execute(
        "SELECT * FROM files WHERE id = ?", (file_id,)
    ).fetchone()
    db.close()

    if not file_record:
        return RedirectResponse(url="/dashboard", status_code=302)

    # Send the file for download
    return FileResponse(
        path=file_record["filepath"],
        filename=file_record["filename"],
        media_type="application/octet-stream"
    )
