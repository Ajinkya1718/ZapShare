/* ==========================================================
   script.js — ZapShare Frontend Logic
   1. Theme toggle (dark/light mode)
   2. Send message via fetch() so page doesn't reload
   3. Auto-refresh polling every 2 seconds for new messages
   ========================================================== */

/* ---- 1. THEME TOGGLE ---- */
function toggleTheme() {
    const html = document.documentElement;
    const btn  = document.getElementById('themeToggle');
    const isDark = html.getAttribute('data-theme') === 'dark';
    if (isDark) {
        html.removeAttribute('data-theme');
        if (btn) btn.textContent = '🌙';
        localStorage.setItem('zapTheme', 'light');
    } else {
        html.setAttribute('data-theme', 'dark');
        if (btn) btn.textContent = '☀️';
        localStorage.setItem('zapTheme', 'dark');
    }
}

// Apply saved theme on every page load
(function applyTheme() {
    const saved = localStorage.getItem('zapTheme');
    const btn   = document.getElementById('themeToggle');
    if (saved === 'dark') {
        document.documentElement.setAttribute('data-theme', 'dark');
        if (btn) btn.textContent = '☀️';
    }
})();


/* ---- 2. SEND MESSAGE (no page reload) ---- */

// Scroll messages area to the very bottom
function scrollDown() {
    const area = document.getElementById('messagesArea');
    if (area) area.scrollTop = area.scrollHeight;
}

// Build a message bubble DOM element from a message object
function buildMsgBubble(msg, currentUid) {
    const isSent = (msg.sender_id === currentUid);
    const div = document.createElement('div');
    div.className = 'bubble ' + (isSent ? 'sent' : 'recv');
    div.dataset.id   = msg.id;
    div.dataset.type = 'msg';

    let inner = '';
    if (!isSent) {
        inner += `<div class="bubble-sender">${escHtml(msg.sender_name)}</div>`;
    }
    inner += `<span class="bubble-text">${escHtml(msg.content)}</span>`;
    inner += `<span class="bubble-time">${msg.timestamp.substring(11,16)}</span>`;
    div.innerHTML = inner;
    return div;
}

// Build a file bubble DOM element from a file object
function buildFileBubble(file, currentUid) {
    const isSent = (file.sender_id === currentUid);
    const div = document.createElement('div');
    div.className = 'bubble file-bubble ' + (isSent ? 'sent' : 'recv');
    div.dataset.id   = file.id;
    div.dataset.type = 'file';

    let inner = `<span class="file-icon">📎</span><div class="file-info">`;
    if (!isSent) {
        inner += `<div class="bubble-sender">${escHtml(file.sender_name)}</div>`;
    }
    inner += `<div class="file-name">
                <a href="/download/${file.id}" class="file-link">${escHtml(file.filename)}</a>
              </div>`;
    inner += `<div class="file-size">${file.timestamp.substring(11,16)}</div>`;
    inner += `</div>`;
    div.innerHTML = inner;
    return div;
}

// Escape HTML to prevent XSS
function escHtml(str) {
    return String(str)
        .replace(/&/g,'&amp;')
        .replace(/</g,'&lt;')
        .replace(/>/g,'&gt;')
        .replace(/"/g,'&quot;');
}

// Wire up the send button and Enter key — only runs on the chat page
(function setupSend() {
    const input   = document.getElementById('msgInput');
    const sendBtn = document.getElementById('sendBtn');
    const indicator = document.getElementById('sendingIndicator');
    const area    = document.getElementById('messagesArea');

    if (!input || !sendBtn || !area) return; // not on chat page

    function doSend() {
        const content = input.value.trim();
        if (!content) return;

        // Show "sending..." indicator
        if (indicator) indicator.style.display = 'inline';
        sendBtn.disabled = true;

        fetch('/api/send', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ receiver_id: RECEIVER_ID, content: content })
        })
        .then(r => r.json())
        .then(msg => {
            if (msg.error) { alert('Could not send: ' + msg.error); return; }
            // Add the sent bubble immediately (no need to wait for poll)
            const bubble = buildMsgBubble(msg, CURRENT_UID);
            area.appendChild(bubble);
            // Update tracker so poll doesn't add it again
            if (msg.id > lastMsgId) lastMsgId = msg.id;
            input.value = '';
            scrollDown();
        })
        .catch(() => alert('Network error — please try again.'))
        .finally(() => {
            if (indicator) indicator.style.display = 'none';
            sendBtn.disabled = false;
            input.focus();
        });
    }

    // Click send button
    sendBtn.addEventListener('click', doSend);

    // Press Enter to send (Shift+Enter = new line)
    input.addEventListener('keydown', function(e) {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            doSend();
        }
    });

    // Scroll to bottom on first load
    scrollDown();
})();


/* ---- 3. AUTO-REFRESH POLLING ---- */
(function startPolling() {
    const area = document.getElementById('messagesArea');
    if (!area) return; // only run on chat page

    const pollStatus = document.getElementById('pollStatus');

    function poll() {
        fetch(`/api/messages/${RECEIVER_ID}?after_msg=${lastMsgId}&after_file=${lastFileId}`)
            .then(r => {
                if (!r.ok) throw new Error('Not OK');
                return r.json();
            })
            .then(data => {
                let updated = false;

                // Append new text messages
                if (data.messages && data.messages.length > 0) {
                    data.messages.forEach(msg => {
                        // Only add if not already in DOM (could be our own sent message)
                        if (!area.querySelector(`[data-id="${msg.id}"][data-type="msg"]`)) {
                            area.appendChild(buildMsgBubble(msg, CURRENT_UID));
                        }
                        if (msg.id > lastMsgId) lastMsgId = msg.id;
                    });
                    updated = true;
                }

                // Append new file messages
                if (data.files && data.files.length > 0) {
                    data.files.forEach(file => {
                        if (!area.querySelector(`[data-id="${file.id}"][data-type="file"]`)) {
                            area.appendChild(buildFileBubble(file, CURRENT_UID));
                        }
                        if (file.id > lastFileId) lastFileId = file.id;
                    });
                    updated = true;
                }

                if (updated) scrollDown();
                if (pollStatus) pollStatus.textContent = 'Live • updates every 2s';
            })
            .catch(() => {
                // Show a subtle offline indicator but keep retrying
                if (pollStatus) pollStatus.textContent = 'Reconnecting…';
            });
    }

    // Poll immediately once, then every 2 seconds
    poll();
    setInterval(poll, 2000);
})();


/* ---- 4. FILE LABEL UPDATE ---- */
function updateFileLabel(input) {
    const label = document.getElementById('fileLabel');
    if (!label) return;
    if (input.files && input.files[0]) {
        label.textContent = '📎 ' + input.files[0].name;
    } else {
        label.textContent = '📎 Choose file to share…';
    }
}

