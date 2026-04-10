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
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.gzip import GZipMiddleware
from starlette.middleware.sessions import SessionMiddleware
import hashlib
import hmac
import json
import os
import queue
import secrets
import shutil
import sqlite3
import threading
import time
import uuid
from typing import Optional

from pydantic import BaseModel

# Import our database functions
from database import UPLOADS_DIR, db_session, init_db, is_db_locked_error, run_write_transaction

# ---- Base Directory ----
# This ensures paths work correctly no matter where the server is started from
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SESSION_SECRET_KEY = os.getenv("SECRET_KEY", "zapshare-local-dev-secret-change-me")
SESSION_HTTPS_ONLY = os.getenv("SESSION_HTTPS_ONLY", "0") in {"1", "true", "True"}
SESSION_MAX_AGE_SECONDS = int(os.getenv("SESSION_MAX_AGE_SECONDS", "1209600"))
CHAT_PAGE_SIZE = 50
FILE_PREVIEW_PAGE_SIZE = 16
HISTORY_PAGE_SIZE = 40
STATIC_CACHE_MAX_AGE_SECONDS = 7 * 24 * 60 * 60
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".svg"}
SSE_HEARTBEAT_SECONDS = 20
SSE_QUEUE_MAXSIZE = 128
PASSWORD_HASH_SCHEME = "pbkdf2_sha256"
PASSWORD_HASH_ITERATIONS = int(os.getenv("PASSWORD_HASH_ITERATIONS", "310000"))
PASSWORD_SALT_BYTES = 16

# ---- App Setup ----
app = FastAPI(title="ZapShare")

# Secret key for session middleware (keeps users logged in)
app.add_middleware(
    SessionMiddleware,
    secret_key=SESSION_SECRET_KEY,
    max_age=SESSION_MAX_AGE_SECONDS,
    same_site="lax",
    https_only=SESSION_HTTPS_ONLY,
)
app.add_middleware(GZipMiddleware, minimum_size=700)

# Mount static files (CSS, JS) so the browser can load them
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")

# Setup Jinja2 templates (HTML files)
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))


@app.middleware("http")
async def cache_static_assets(request: Request, call_next):
    """Apply browser cache headers for static files to reduce repeat payloads."""
    response = await call_next(request)
    if request.url.path.startswith("/static/") and response.status_code == 200:
        if "Cache-Control" not in response.headers:
            response.headers["Cache-Control"] = (
                f"public, max-age={STATIC_CACHE_MAX_AGE_SECONDS}, immutable"
            )
    return response


# ---- Initialize Database on Startup ----
@app.on_event("startup")
def startup():
    """Called when the server starts. Creates database tables."""
    init_db()


# ---- Helper Functions ----

def hash_password(password: str) -> str:
    """Create a strong PBKDF2 password hash for new/updated credentials."""
    salt = secrets.token_hex(PASSWORD_SALT_BYTES)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        PASSWORD_HASH_ITERATIONS,
    ).hex()
    return f"{PASSWORD_HASH_SCHEME}${PASSWORD_HASH_ITERATIONS}${salt}${digest}"


def hash_password_legacy(password: str) -> str:
    """Legacy SHA-256 hash kept for backward-compatible login migration."""
    return hashlib.sha256(password.encode()).hexdigest()


def verify_password(password: str, stored_hash: str) -> bool:
    """Verify a password against modern PBKDF2 format or legacy SHA-256."""
    if stored_hash.startswith(f"{PASSWORD_HASH_SCHEME}$"):
        parts = stored_hash.split("$", 3)
        if len(parts) != 4:
            return False
        _, iterations_text, salt, expected = parts
        try:
            iterations = int(iterations_text)
        except ValueError:
            return False

        candidate = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt.encode("utf-8"),
            iterations,
        ).hex()
        return hmac.compare_digest(candidate, expected)

    return hmac.compare_digest(hash_password_legacy(password), stored_hash)


def needs_password_rehash(stored_hash: str) -> bool:
    return not stored_hash.startswith(f"{PASSWORD_HASH_SCHEME}$")


def get_current_user(request: Request):
    """
    Checks if a user is logged in by reading the session.
    Returns user_id if logged in, None otherwise.
    """
    return request.session.get("user_id")


def is_image_filename(filename: str) -> bool:
    ext = os.path.splitext(filename.lower())[1]
    return ext in IMAGE_EXTENSIONS


def sanitize_filename(filename: str) -> str:
    """Return a filesystem-safe filename while preserving the visible name."""
    base = os.path.basename(filename or "").strip()
    base = base.replace("\x00", "")
    if not base:
        return "upload.bin"

    safe_chars = []
    for char in base:
        if char.isalnum() or char in {".", "-", "_", " "}:
            safe_chars.append(char)
        else:
            safe_chars.append("_")

    cleaned = "".join(safe_chars).strip(" ._")
    return cleaned[:180] if cleaned else "upload.bin"


def build_upload_path(sender_id: int, receiver_id: int, original_filename: str) -> tuple[str, str]:
    """Create a unique, traversal-safe storage path for an uploaded file."""
    display_name = sanitize_filename(original_filename)
    storage_name = f"{sender_id}_{receiver_id}_{uuid.uuid4().hex}_{display_name}"
    file_path = os.path.abspath(os.path.join(UPLOADS_DIR, storage_name))

    uploads_root = os.path.abspath(UPLOADS_DIR) + os.sep
    if not file_path.startswith(uploads_root):
        raise ValueError("Invalid upload path")

    return display_name, file_path


def serialize_file_row(row) -> dict:
    item = dict(row)
    item["is_image"] = is_image_filename(item["filename"])
    return item


def can_access_file(file_record, user_id: int) -> bool:
    return bool(file_record) and (
        file_record["sender_id"] == user_id or file_record["receiver_id"] == user_id
    )


def serialize_message_row(row) -> dict:
    return dict(row)


def to_timeline_items(messages, files):
    timeline = []
    for msg in messages:
        timeline.append({"item_type": "msg", **serialize_message_row(msg)})
    for file_row in files:
        timeline.append({"item_type": "file", **serialize_file_row(file_row)})

    # SQLite timestamp string format sorts correctly lexicographically.
    timeline.sort(key=lambda item: (item["timestamp"], item["item_type"], item["id"]))
    return timeline


def get_chat_partner(db, receiver_id: int):
    return db.execute(
        "SELECT id, username FROM users WHERE id = ?", (receiver_id,)
    ).fetchone()


class RealtimeHub:
    """In-process SSE fan-out for conversation events and presence."""

    def __init__(self):
        self._lock = threading.RLock()
        self._subscribers: dict[tuple[int, int], set[queue.Queue[str]]] = {}
        self._user_connections: dict[int, int] = {}

    @staticmethod
    def _conversation_key(user_a: int, user_b: int) -> tuple[int, int]:
        return (user_a, user_b) if user_a < user_b else (user_b, user_a)

    @staticmethod
    def _sse_frame(event_type: str, payload: dict) -> str:
        data = json.dumps(payload, separators=(",", ":"))
        return f"event: {event_type}\ndata: {data}\n\n"

    def is_user_online(self, user_id: int) -> bool:
        with self._lock:
            return self._user_connections.get(user_id, 0) > 0

    def register(self, user_id: int, peer_id: int) -> tuple[tuple[int, int], queue.Queue[str], bool]:
        key = self._conversation_key(user_id, peer_id)
        client_queue: queue.Queue[str] = queue.Queue(maxsize=SSE_QUEUE_MAXSIZE)
        with self._lock:
            self._subscribers.setdefault(key, set()).add(client_queue)
            prev_count = self._user_connections.get(user_id, 0)
            self._user_connections[user_id] = prev_count + 1
        return key, client_queue, prev_count == 0

    def unregister(self, user_id: int, key: tuple[int, int], client_queue: queue.Queue[str]) -> bool:
        with self._lock:
            queues = self._subscribers.get(key)
            if queues and client_queue in queues:
                queues.remove(client_queue)
                if not queues:
                    self._subscribers.pop(key, None)

            prev_count = self._user_connections.get(user_id, 0)
            next_count = max(0, prev_count - 1)
            if next_count == 0:
                self._user_connections.pop(user_id, None)
            else:
                self._user_connections[user_id] = next_count
        return prev_count > 0 and next_count == 0

    def _emit(self, client_queue: queue.Queue[str], frame: str):
        try:
            client_queue.put_nowait(frame)
        except queue.Full:
            try:
                client_queue.get_nowait()
            except queue.Empty:
                pass
            try:
                client_queue.put_nowait(frame)
            except queue.Full:
                # Drop the frame for very slow clients to avoid blocking writes.
                pass

    def _fan_out(self, key: tuple[int, int], event_type: str, payload: dict):
        frame = self._sse_frame(event_type, payload)
        with self._lock:
            targets = list(self._subscribers.get(key, set()))
        for client_queue in targets:
            self._emit(client_queue, frame)

    def publish_conversation_event(self, user_a: int, user_b: int, event_type: str, payload: dict):
        self._fan_out(self._conversation_key(user_a, user_b), event_type, payload)

    def publish_presence(self, user_id: int, peer_id: int, online: bool):
        self.publish_conversation_event(
            user_id,
            peer_id,
            "presence",
            {
                "user_id": user_id,
                "online": online,
                "timestamp": int(time.time()),
            },
        )


realtime_hub = RealtimeHub()


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
    def _tx(conn):
        # Check if username is already taken
        existing_user = conn.execute(
            "SELECT id FROM users WHERE username = ?", (username,)
        ).fetchone()
        if existing_user:
            return {"ok": False, "reason": "exists"}

        # Hash the password and save the new user
        hashed_pw = hash_password(password)
        conn.execute(
            "INSERT INTO users (username, password) VALUES (?, ?)",
            (username, hashed_pw)
        )
        return {"ok": True}

    result = run_write_transaction(_tx)
    if not result.get("ok"):
        return templates.TemplateResponse("register.html", {
            "request": request,
            "error": "Username already exists! Please choose another."
        })

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
    with db_session() as db:
        # Find user by username
        user = db.execute(
            "SELECT * FROM users WHERE username = ?", (username,)
        ).fetchone()

    # Check if user exists and password matches
    if user is None or not verify_password(password, user["password"]):
        return templates.TemplateResponse("login.html", {
            "request": request,
            "error": "Invalid username or password!",
            "success": None
        })

    if needs_password_rehash(user["password"]):
        # One-time transparent upgrade from legacy hashes after successful login.
        try:
            run_write_transaction(
                lambda conn: conn.execute(
                    "UPDATE users SET password = ? WHERE id = ?",
                    (hash_password(password), user["id"]),
                )
            )
        except Exception:
            # Keep login successful even if hash upgrade cannot be persisted.
            pass

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

    with db_session() as db:
        # Get all users EXCEPT the currently logged-in user
        users = db.execute(
            "SELECT id, username FROM users WHERE id != ?", (user_id,)
        ).fetchall()

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

    with db_session() as db:
        # Get the receiver's info
        receiver = get_chat_partner(db, receiver_id)

        if not receiver:
            return RedirectResponse(url="/dashboard", status_code=302)

        # Get all users for the sidebar (excluding self)
        users = db.execute(
            "SELECT id, username FROM users WHERE id != ?", (user_id,)
        ).fetchall()

        # Load only recent messages for faster initial render.
        messages = db.execute("""
        SELECT m.*, u.username as sender_name
        FROM messages m
        JOIN users u ON m.sender_id = u.id
        WHERE (m.sender_id = ? AND m.receiver_id = ?)
           OR (m.sender_id = ? AND m.receiver_id = ?)
        ORDER BY m.id DESC
        LIMIT ?
    """, (user_id, receiver_id, receiver_id, user_id, CHAT_PAGE_SIZE)).fetchall()
        messages = list(reversed(messages))

        # Load recent files only to keep first render fast.
        files = db.execute("""
        SELECT f.*, u.username as sender_name
        FROM files f
        JOIN users u ON f.sender_id = u.id
        WHERE (f.sender_id = ? AND f.receiver_id = ?)
           OR (f.sender_id = ? AND f.receiver_id = ?)
        ORDER BY f.id DESC
        LIMIT ?
    """, (user_id, receiver_id, receiver_id, user_id, FILE_PREVIEW_PAGE_SIZE)).fetchall()
        files = list(reversed(files))

        oldest_msg_id = messages[0]["id"] if messages else 0
        has_more_messages = False
        if oldest_msg_id:
            has_more_messages = db.execute("""
            SELECT 1
            FROM messages
            WHERE ((sender_id = ? AND receiver_id = ?)
               OR  (sender_id = ? AND receiver_id = ?))
              AND id < ?
            LIMIT 1
        """, (user_id, receiver_id, receiver_id, user_id, oldest_msg_id)).fetchone() is not None

        timeline = to_timeline_items(messages, files)


    return templates.TemplateResponse("chat.html", {
        "request": request,
        "username": request.session.get("username"),
        "user_id": user_id,
        "receiver": receiver,
        "users": users,
        "messages": messages,
        "files": files,
        "timeline": timeline,
        "has_more_messages": has_more_messages,
        "oldest_msg_id": oldest_msg_id
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

    if receiver_id == user_id:
        return HTMLResponse("Invalid receiver.", status_code=400)

    with db_session() as db:
        receiver = get_chat_partner(db, receiver_id)
    if not receiver:
        return HTMLResponse("Receiver not found.", status_code=404)

    def _tx(conn):
        cursor = conn.execute(
            "INSERT INTO messages (sender_id, receiver_id, content) VALUES (?, ?, ?)",
            (user_id, receiver_id, content),
        )
        msg_id = cursor.lastrowid
        msg = conn.execute(
            """
            SELECT m.id, m.content, m.timestamp, m.sender_id, u.username as sender_name
            FROM messages m
            JOIN users u ON m.sender_id = u.id
            WHERE m.id = ?
            """,
            (msg_id,),
        ).fetchone()
        return dict(msg)

    try:
        msg = run_write_transaction(_tx)
        realtime_hub.publish_conversation_event(user_id, receiver_id, "message", msg)
    except sqlite3.OperationalError as exc:
        if is_db_locked_error(exc):
            return HTMLResponse("Database busy, please retry.", status_code=503)
        raise

    # Redirect back to the chat page
    return RedirectResponse(url=f"/chat/{receiver_id}", status_code=302)


# ---- 7b. SEND MESSAGE (JSON API — used by auto-refresh JS) ----
class SendMessagePayload(BaseModel):
    receiver_id: Optional[int] = None
    content: Optional[str] = None


@app.post("/api/send")
def api_send_message(payload: SendMessagePayload, request: Request):
    """
    Accepts a JSON POST with {receiver_id, content}.
    Saves the message and returns it as JSON.
    Used by the frontend fetch() call so page doesn't reload on send.
    """
    user_id = get_current_user(request)
    if not user_id:
        return JSONResponse({"error": "not logged in"}, status_code=401)

    receiver_id = payload.receiver_id
    content = (payload.content or "").strip()

    if not content or not receiver_id:
        return JSONResponse({"error": "missing fields"}, status_code=400)

    if receiver_id == user_id:
        return JSONResponse({"error": "invalid receiver"}, status_code=400)

    with db_session() as db:
        receiver = get_chat_partner(db, receiver_id)
    if not receiver:
        return JSONResponse({"error": "receiver not found"}, status_code=404)

    def _tx(conn):
        cursor = conn.execute(
            "INSERT INTO messages (sender_id, receiver_id, content) VALUES (?, ?, ?)",
            (user_id, receiver_id, content),
        )
        msg_id = cursor.lastrowid

        # Fetch back the saved message with timestamp and sender name
        msg = conn.execute("""
            SELECT m.id, m.content, m.timestamp, m.sender_id, u.username as sender_name
            FROM messages m
            JOIN users u ON m.sender_id = u.id
            WHERE m.id = ?
        """, (msg_id,)).fetchone()

        return dict(msg)

    try:
        msg = run_write_transaction(_tx)
        realtime_hub.publish_conversation_event(user_id, receiver_id, "message", msg)
        return msg
    except sqlite3.OperationalError as exc:
        if is_db_locked_error(exc):
            return JSONResponse({"error": "db busy"}, status_code=503)
        raise


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

    if receiver_id == user_id:
        return JSONResponse({"error": "invalid receiver"}, status_code=400)

    with db_session() as db:
        receiver = get_chat_partner(db, receiver_id)
    if not receiver:
        return JSONResponse({"error": "receiver not found"}, status_code=404)

    with db_session() as db:
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

    return {
        "messages": [serialize_message_row(m) for m in messages],
        "files": [serialize_file_row(f) for f in files],
        "user_id": user_id
    }


@app.get("/api/messages/{receiver_id}/history")
def api_get_messages_history(
    request: Request,
    receiver_id: int,
    before_msg: int,
    limit: int = HISTORY_PAGE_SIZE
):
    """
    Loads older message history in pages.
    This keeps initial chat render light while still allowing deep scrollback.
    """
    user_id = get_current_user(request)
    if not user_id:
        return JSONResponse({"error": "not logged in"}, status_code=401)

    if receiver_id == user_id:
        return JSONResponse({"error": "invalid receiver"}, status_code=400)

    with db_session() as db:
        receiver = get_chat_partner(db, receiver_id)
    if not receiver:
        return JSONResponse({"error": "receiver not found"}, status_code=404)

    if before_msg <= 0:
        return JSONResponse({"error": "invalid cursor"}, status_code=400)

    page_size = max(10, min(limit, 100))

    with db_session() as db:
        older = db.execute("""
        SELECT m.id, m.content, m.timestamp, m.sender_id, u.username as sender_name
        FROM messages m
        JOIN users u ON m.sender_id = u.id
        WHERE ((m.sender_id = ? AND m.receiver_id = ?)
           OR  (m.sender_id = ? AND m.receiver_id = ?))
          AND m.id < ?
        ORDER BY m.id DESC
        LIMIT ?
    """, (user_id, receiver_id, receiver_id, user_id, before_msg, page_size)).fetchall()

        older = list(reversed(older))
        oldest_loaded = older[0]["id"] if older else before_msg

        has_more = False
        if older:
            has_more = db.execute("""
            SELECT 1
            FROM messages
            WHERE ((sender_id = ? AND receiver_id = ?)
               OR  (sender_id = ? AND receiver_id = ?))
              AND id < ?
            LIMIT 1
        """, (user_id, receiver_id, receiver_id, user_id, oldest_loaded)).fetchone() is not None

    return {
        "messages": [serialize_message_row(m) for m in older],
        "has_more": has_more,
        "next_before_msg": oldest_loaded
    }


@app.get("/api/events/{receiver_id}")
def api_events(request: Request, receiver_id: int):
    """Stream realtime message/file/presence updates for the active conversation."""
    user_id = get_current_user(request)
    if not user_id:
        return JSONResponse({"error": "not logged in"}, status_code=401)

    if receiver_id == user_id:
        return JSONResponse({"error": "invalid receiver"}, status_code=400)

    with db_session() as db:
        receiver = get_chat_partner(db, receiver_id)
    if not receiver:
        return JSONResponse({"error": "receiver not found"}, status_code=404)

    convo_key, client_queue, became_online = realtime_hub.register(user_id, receiver_id)
    if became_online:
        realtime_hub.publish_presence(user_id, receiver_id, online=True)

    def event_stream():
        try:
            snapshot = {
                "peer_user_id": receiver_id,
                "peer_online": realtime_hub.is_user_online(receiver_id),
                "timestamp": int(time.time()),
            }
            yield RealtimeHub._sse_frame("presence_snapshot", snapshot)

            while True:
                try:
                    frame = client_queue.get(timeout=SSE_HEARTBEAT_SECONDS)
                    yield frame
                except queue.Empty:
                    yield RealtimeHub._sse_frame(
                        "heartbeat", {"timestamp": int(time.time())}
                    )
        finally:
            became_offline = realtime_hub.unregister(user_id, convo_key, client_queue)
            if became_offline:
                realtime_hub.publish_presence(user_id, receiver_id, online=False)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ---- 8. UPLOAD FILE ----
@app.post("/upload")
def upload_file(
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

    if receiver_id == user_id:
        return HTMLResponse("Invalid receiver.", status_code=400)

    with db_session() as db:
        receiver = get_chat_partner(db, receiver_id)
    if not receiver:
        return HTMLResponse("Receiver not found.", status_code=404)

    try:
        display_filename, file_path = build_upload_path(user_id, receiver_id, file.filename)
    except ValueError:
        return HTMLResponse("Invalid file name.", status_code=400)

    # Save the file to disk
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    # Save file metadata to database
    def _tx(conn):
        cursor = conn.execute(
            "INSERT INTO files (sender_id, receiver_id, filename, filepath) VALUES (?, ?, ?, ?)",
            (user_id, receiver_id, display_filename, file_path),
        )
        file_id = cursor.lastrowid
        file_row = conn.execute(
            """
            SELECT f.id, f.filename, f.timestamp, f.sender_id, u.username as sender_name
            FROM files f
            JOIN users u ON f.sender_id = u.id
            WHERE f.id = ?
            """,
            (file_id,),
        ).fetchone()
        return serialize_file_row(file_row)

    try:
        file_event = run_write_transaction(_tx)
        realtime_hub.publish_conversation_event(user_id, receiver_id, "file", file_event)
    except sqlite3.OperationalError as exc:
        # If DB write fails after the file is saved, clean up the orphaned file.
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
        except Exception:
            pass
        if is_db_locked_error(exc):
            return HTMLResponse("Database busy, please retry.", status_code=503)
        raise
    except Exception:
        # Keep filesystem and DB in sync even on non-SQLite write failures.
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
        except Exception:
            pass
        raise

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

    with db_session() as db:
        file_record = db.execute(
            "SELECT * FROM files WHERE id = ?", (file_id,)
        ).fetchone()

    if not can_access_file(file_record, user_id):
        return JSONResponse({"error": "not found"}, status_code=404)

    file_path = os.path.abspath(file_record["filepath"])
    uploads_root = os.path.abspath(UPLOADS_DIR) + os.sep
    if not file_path.startswith(uploads_root) or not os.path.exists(file_path):
        return JSONResponse({"error": "not found"}, status_code=404)

    # Send the file for download
    return FileResponse(
        path=file_path,
        filename=file_record["filename"],
        media_type="application/octet-stream"
    )
