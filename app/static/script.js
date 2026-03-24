/* ==========================================================
   script.js — ZapShare Frontend Logic
   1. Theme toggle (dark/light mode)
   2. Send message via fetch() so page doesn't reload
    3. Auto-refresh polling for new messages with backoff
    4. Mobile sidebar toggle support on chat page
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


/* ---- 1b. MOBILE CHAT LAYOUT ---- */
(function setupMobileLayout() {
    const layout = document.querySelector('.app-layout');
    const openBtn = document.getElementById('mobileUsersBtn');
    const area = document.getElementById('messagesArea');
    if (!layout || !openBtn || !area) return;

    openBtn.addEventListener('click', () => {
        layout.classList.remove('chat-open');
    });

    // Keep chat panel focused after sending from mobile keyboard.
    const input = document.getElementById('msgInput');
    if (input) {
        input.addEventListener('focus', () => {
            layout.classList.add('chat-open');
        });
    }
})();


/* ---- 2. SEND MESSAGE (no page reload) ---- */

// Scroll messages area to the very bottom
function scrollDown() {
    const area = document.getElementById('messagesArea');
    if (area) area.scrollTop = area.scrollHeight;
}

function isNearBottom(area) {
    const threshold = 110;
    return (area.scrollHeight - area.scrollTop - area.clientHeight) < threshold;
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

        let inner = `<div class="file-info">`;
    if (!isSent) {
        inner += `<div class="bubble-sender">${escHtml(file.sender_name)}</div>`;
    }

        if (file.is_image) {
                inner += `<a href="/download/${file.id}" class="file-preview-link" target="_blank" rel="noopener noreferrer">
                                        <img
                                            src="/download/${file.id}"
                                            alt="${escHtml(file.filename)}"
                                            class="file-preview-image"
                                            loading="lazy"
                                            decoding="async"
                                        >
                                    </a>`;
        } else {
                inner += `<div class="file-card-head">
                                        <span class="file-icon">📎</span>
                                        <div class="file-name">
                                                <a href="/download/${file.id}" class="file-link">${escHtml(file.filename)}</a>
                                        </div>
                                    </div>`;
        }
        if (file.is_image) {
                inner += `<div class="file-meta">
                                        <a href="/download/${file.id}" class="file-link" target="_blank" rel="noopener noreferrer">Open full image</a>
                                    </div>`;
        } else {
                inner += `<div class="file-meta">Tap to download</div>`;
        }
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


/* ---- 2b. MESSAGE HISTORY PAGINATION ---- */
(function setupHistoryPagination() {
    const area = document.getElementById('messagesArea');
    const loadBtn = document.getElementById('loadOlderBtn');
    const loadWrap = document.getElementById('loadOlderWrap');
    if (!area || !loadBtn || !loadWrap || typeof beforeMsgId === 'undefined') return;

    if (!HAS_MORE_MESSAGES) {
        loadWrap.classList.add('is-hidden');
        return;
    }

    let loading = false;

    function setLoadState(text, disabled) {
        loadBtn.textContent = text;
        loadBtn.disabled = disabled;
    }

    function prependMessages(messages) {
        if (!messages || messages.length === 0) return;

        // Preserve viewport position while prepending older messages.
        const prevHeight = area.scrollHeight;
        const anchor = loadWrap.nextElementSibling;

        const frag = document.createDocumentFragment();
        messages.forEach(msg => {
            if (!area.querySelector(`[data-id="${msg.id}"][data-type="msg"]`)) {
                frag.appendChild(buildMsgBubble(msg, CURRENT_UID));
            }
        });

        if (anchor) {
            area.insertBefore(frag, anchor);
        } else {
            area.appendChild(frag);
        }

        const nextHeight = area.scrollHeight;
        area.scrollTop += (nextHeight - prevHeight);
    }

    loadBtn.addEventListener('click', () => {
        if (loading || beforeMsgId <= 0) return;

        loading = true;
        setLoadState('Loading...', true);

        fetch(`/api/messages/${RECEIVER_ID}/history?before_msg=${beforeMsgId}`)
            .then(r => {
                if (!r.ok) throw new Error('history failed');
                return r.json();
            })
            .then(data => {
                prependMessages(data.messages || []);
                beforeMsgId = data.next_before_msg || beforeMsgId;

                if (!data.has_more) {
                    loadWrap.classList.add('is-hidden');
                } else {
                    setLoadState('Load older messages', false);
                }
            })
            .catch(() => {
                setLoadState('Retry loading older', false);
            })
            .finally(() => {
                loading = false;
            });
    });
})();


/* ---- 3. AUTO-REFRESH POLLING ---- */
(function startPolling() {
    const area = document.getElementById('messagesArea');
    if (!area) return; // only run on chat page

    const pollStatus = document.getElementById('pollStatus');
    const seen = new Set();
    let inFlight = false;
    let pollDelay = 2000;
    let timer = null;

    function scheduleNext(delay) {
        if (timer) clearTimeout(timer);
        timer = setTimeout(poll, delay);
    }

    function poll() {
        if (inFlight) {
            scheduleNext(pollDelay);
            return;
        }
        if (document.hidden) {
            // Reduce background work when tab isn't visible.
            scheduleNext(8000);
            return;
        }

        inFlight = true;
        fetch(`/api/messages/${RECEIVER_ID}?after_msg=${lastMsgId}&after_file=${lastFileId}`)
            .then(r => {
                if (!r.ok) throw new Error('Not OK');
                return r.json();
            })
            .then(data => {
                let updated = false;
                const shouldStickToBottom = isNearBottom(area);

                // Append new text messages
                if (data.messages && data.messages.length > 0) {
                    data.messages.forEach(msg => {
                        const key = `msg-${msg.id}`;
                        // Only add if not already in DOM (could be our own sent message)
                        if (!seen.has(key) && !area.querySelector(`[data-id="${msg.id}"][data-type="msg"]`)) {
                            area.appendChild(buildMsgBubble(msg, CURRENT_UID));
                            seen.add(key);
                        }
                        if (msg.id > lastMsgId) lastMsgId = msg.id;
                    });
                    updated = true;
                }

                // Append new file messages
                if (data.files && data.files.length > 0) {
                    data.files.forEach(file => {
                        const key = `file-${file.id}`;
                        if (!seen.has(key) && !area.querySelector(`[data-id="${file.id}"][data-type="file"]`)) {
                            area.appendChild(buildFileBubble(file, CURRENT_UID));
                            seen.add(key);
                        }
                        if (file.id > lastFileId) lastFileId = file.id;
                    });
                    updated = true;
                }

                if (updated && shouldStickToBottom) scrollDown();
                pollDelay = 2000;
                if (pollStatus) pollStatus.textContent = 'Live • synced';
            })
            .catch(() => {
                // Show a subtle offline indicator but keep retrying
                pollDelay = Math.min(pollDelay * 1.8, 12000);
                if (pollStatus) pollStatus.textContent = 'Reconnecting...';
            })
            .finally(() => {
                inFlight = false;
                scheduleNext(pollDelay);
            });
    }

    // Seed seen IDs from server-rendered DOM to avoid repeated querySelector churn.
    area.querySelectorAll('[data-id][data-type]').forEach(node => {
        seen.add(`${node.dataset.type}-${node.dataset.id}`);
    });

    // Poll immediately, then continue with adaptive delay.
    poll();

    document.addEventListener('visibilitychange', () => {
        if (!document.hidden) {
            pollDelay = 1200;
            poll();
        }
    });
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

