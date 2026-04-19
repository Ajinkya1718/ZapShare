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


/* ---- 1c. ATTACHMENT SUBMENU ---- */
(function setupAttachmentMenu() {
    const wrap = document.getElementById('composerWrap');
    const attachBtn = document.getElementById('attachBtn');
    const menu = document.getElementById('attachMenu');
    const pickMediaBtn = document.getElementById('pickMediaBtn');
    const pickDocBtn = document.getElementById('pickDocBtn');
    const fileInput = document.getElementById('fileUploadInput');
    const fileForm = document.getElementById('fileForm');

    if (!wrap || !attachBtn || !menu || !pickMediaBtn || !pickDocBtn || !fileInput || !fileForm) return;

    function closeMenu() {
        menu.classList.remove('open');
        menu.setAttribute('aria-hidden', 'true');
        attachBtn.setAttribute('aria-expanded', 'false');
    }

    function openMenu() {
        menu.classList.add('open');
        menu.setAttribute('aria-hidden', 'false');
        attachBtn.setAttribute('aria-expanded', 'true');
    }

    attachBtn.addEventListener('click', () => {
        if (menu.classList.contains('open')) {
            closeMenu();
        } else {
            openMenu();
        }
    });

    pickMediaBtn.addEventListener('click', () => {
        closeMenu();
        fileInput.setAttribute('accept', 'image/*,video/*');
        fileInput.value = '';
        fileInput.click();
    });

    pickDocBtn.addEventListener('click', () => {
        closeMenu();
        fileInput.setAttribute('accept', '.pdf,.doc,.docx,.xls,.xlsx,.ppt,.pptx,.txt,.csv,.zip,.rar,.7z,.json,.xml');
        fileInput.value = '';
        fileInput.click();
    });

    fileInput.addEventListener('change', () => {
        if (fileInput.files && fileInput.files[0]) {
            fileForm.submit();
        }
    });

    document.addEventListener('click', (event) => {
        if (!wrap.contains(event.target)) {
            closeMenu();
        }
    });

    document.addEventListener('keydown', (event) => {
        if (event.key === 'Escape') {
            closeMenu();
        }
    });
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

function parseEventData(evt) {
    try {
        return JSON.parse(evt.data);
    } catch (_) {
        return null;
    }
}

function setupGlobalPresenceSync() {
    const rows = Array.from(document.querySelectorAll('.sidebar-users .user-row[data-user-id]'));
    if (rows.length === 0) return;

    const dynamicRows = new Map();
    rows.forEach(row => {
        if (row.dataset.presenceMode === 'dynamic') {
            dynamicRows.set(String(row.dataset.userId), row);
        }
    });

    let presenceSource = null;
    let presenceTimer = null;
    let presenceReconnectTimer = null;
    let presenceFailures = 0;
    let presencePollDelay = 8000;
    let presenceInFlight = false;

    function getStatusNode(row) {
        return row ? row.querySelector('.user-row-sub') : null;
    }

    function setRowStatus(row, isOnline) {
        if (!row || row.dataset.presenceMode === 'fixed') return;
        const statusNode = getStatusNode(row);
        if (!statusNode) return;
        const base = row.dataset.presenceBase || 'Click to chat';
        statusNode.textContent = isOnline ? 'Online' : base;
        row.dataset.presenceState = isOnline ? 'online' : 'offline';
    }

    function applySnapshot(snapshot) {
        const onlineIds = new Set((snapshot && snapshot.online_user_ids) || []);
        dynamicRows.forEach((row, userId) => {
            setRowStatus(row, onlineIds.has(Number(userId)));
        });
    }

    function applyPresence(payload) {
        if (!payload || typeof payload.user_id === 'undefined') return;
        const row = dynamicRows.get(String(payload.user_id));
        if (!row) return;
        setRowStatus(row, !!payload.online);
    }

    function stopPresencePolling() {
        if (presenceTimer) {
            clearTimeout(presenceTimer);
            presenceTimer = null;
        }
    }

    function clearPresenceReconnectTimer() {
        if (presenceReconnectTimer) {
            clearTimeout(presenceReconnectTimer);
            presenceReconnectTimer = null;
        }
    }

    function schedulePresencePoll(delay) {
        stopPresencePolling();
        presenceTimer = setTimeout(pollPresenceOnce, delay);
    }

    function pollPresenceOnce() {
        if (presenceInFlight) {
            schedulePresencePoll(presencePollDelay);
            return;
        }

        if (document.hidden) {
            schedulePresencePoll(20000);
            return;
        }

        presenceInFlight = true;
        fetch('/api/presence/online', {
            method: 'GET',
            headers: { 'X-Requested-With': 'XMLHttpRequest' },
            credentials: 'same-origin'
        })
            .then(res => {
                if (!res.ok) throw new Error('presence poll failed');
                return res.json();
            })
            .then(applySnapshot)
            .catch(() => {
                presencePollDelay = Math.min(presencePollDelay * 1.6, 20000);
            })
            .finally(() => {
                presenceInFlight = false;
                schedulePresencePoll(presencePollDelay);
            });
    }

    function startPresencePollingFallback() {
        stopPresenceStream();
        presencePollDelay = 2000;
        pollPresenceOnce();
    }

    function clearPresenceSource() {
        if (presenceSource) {
            presenceSource.close();
            presenceSource = null;
        }
    }

    function schedulePresenceReconnect() {
        clearPresenceReconnectTimer();
        const delay = Math.min(1000 * (2 ** Math.min(presenceFailures, 5)), 15000);
        presenceReconnectTimer = setTimeout(connectPresenceStream, delay);
    }

    function stopPresenceStream() {
        clearPresenceReconnectTimer();
        clearPresenceSource();
        stopPresencePolling();
    }

    function connectPresenceStream() {
        clearPresenceReconnectTimer();
        clearPresenceSource();

        const stream = new EventSource('/api/presence/events');
        presenceSource = stream;

        stream.addEventListener('open', () => {
            if (presenceSource !== stream) return;
            presenceFailures = 0;
            stopPresencePolling();
        });

        stream.addEventListener('presence_snapshot', evt => {
            if (presenceSource !== stream) return;
            const payload = parseEventData(evt);
            if (!payload) return;
            applySnapshot(payload);
        });

        stream.addEventListener('presence', evt => {
            if (presenceSource !== stream) return;
            const payload = parseEventData(evt);
            if (!payload) return;
            applyPresence(payload);
        });

        stream.onerror = () => {
            if (presenceSource !== stream) return;
            stream.close();
            presenceSource = null;
            presenceFailures += 1;

            if (presenceFailures >= 3) {
                startPresencePollingFallback();
                return;
            }

            schedulePresenceReconnect();
        };
    }

    applySnapshot({ online_user_ids: [] });
    connectPresenceStream();

    document.addEventListener('visibilitychange', () => {
        if (!document.hidden && !presenceSource) {
            pollPresenceOnce();
        }
    });

    window.addEventListener('beforeunload', () => {
        stopPresenceStream();
    });
}

setupGlobalPresenceSync();

// Wire up the send button and Enter key — only runs on the chat page
(function setupSend() {
    const input   = document.getElementById('msgInput');
    const sendBtn = document.getElementById('sendBtn');
    const indicator = document.getElementById('sendingIndicator');
    const area    = document.getElementById('messagesArea');

    if (!input || !sendBtn || !area) return; // not on chat page

    function updateActionIcon() {
        const hasText = input.value.trim().length > 0;
        if (hasText) {
            sendBtn.setAttribute('title', 'Send');
            sendBtn.setAttribute('aria-label', 'Send message');
            sendBtn.dataset.mode = 'send';
        } else {
            sendBtn.setAttribute('title', 'Voice message');
            sendBtn.setAttribute('aria-label', 'Voice message');
            sendBtn.dataset.mode = 'mic';
        }
    }

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
            input.value = '';
        })
        .catch(() => alert('Network error — please try again.'))
        .finally(() => {
            if (indicator) indicator.style.display = 'none';
            sendBtn.disabled = false;
            input.focus();
        });
    }

    // Click send button
    sendBtn.addEventListener('click', () => {
        if (sendBtn.dataset.mode === 'send') {
            doSend();
        }
    });

    input.addEventListener('input', updateActionIcon);

    // Press Enter to send (Shift+Enter = new line)
    input.addEventListener('keydown', function(e) {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            doSend();
        }
    });

    // Scroll to bottom on first load
    scrollDown();
    updateActionIcon();
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


/* ---- 3. REALTIME SYNC (SSE FIRST + POLLING FALLBACK) ---- */
(function startRealtimeSync() {
    const area = document.getElementById('messagesArea');
    if (!area) return; // only run on chat page

    const pollStatus = document.getElementById('pollStatus');
    const seen = new Set();
    let inFlight = false;
    let pollDelay = 2000;
    let pollTimer = null;
    let reconnectTimer = null;
    let sse = null;
    let sseFailures = 0;
    let peerOnline = null;
    let connectionState = 'CONNECTING';

    function setState(nextState) {
        connectionState = nextState;
        renderStatus();
    }

    function renderStatus() {
        if (!pollStatus) return;

        let stateLabel = 'Connecting...';
        if (connectionState === 'LIVE') stateLabel = 'Live';
        if (connectionState === 'DEGRADED') stateLabel = 'Live fallback';
        if (connectionState === 'RECONNECTING') stateLabel = 'Reconnecting...';

        let presenceLabel = 'status unknown';
        if (peerOnline === true) presenceLabel = 'user online';
        if (peerOnline === false) presenceLabel = 'user offline';

        pollStatus.textContent = `${stateLabel} • ${presenceLabel}`;
    }

    function clearEmptyHint() {
        const hint = area.querySelector('.empty-inline');
        if (hint) hint.remove();
    }

    function seedSeen() {
        area.querySelectorAll('[data-id][data-type]').forEach(node => {
            seen.add(`${node.dataset.type}-${node.dataset.id}`);
        });
    }

    function appendMessageIfNew(msg) {
        const key = `msg-${msg.id}`;
        if (seen.has(key)) return false;
        if (area.querySelector(`[data-id="${msg.id}"][data-type="msg"]`)) {
            seen.add(key);
            return false;
        }
        clearEmptyHint();
        area.appendChild(buildMsgBubble(msg, CURRENT_UID));
        seen.add(key);
        if (msg.id > lastMsgId) lastMsgId = msg.id;
        return true;
    }

    function appendFileIfNew(file) {
        const key = `file-${file.id}`;
        if (seen.has(key)) return false;
        if (area.querySelector(`[data-id="${file.id}"][data-type="file"]`)) {
            seen.add(key);
            return false;
        }
        clearEmptyHint();
        area.appendChild(buildFileBubble(file, CURRENT_UID));
        seen.add(key);
        if (file.id > lastFileId) lastFileId = file.id;
        return true;
    }

    function stopPolling() {
        if (pollTimer) {
            clearTimeout(pollTimer);
            pollTimer = null;
        }
    }

    function schedulePoll(delay) {
        stopPolling();
        pollTimer = setTimeout(pollOnce, delay);
    }

    function pollOnce() {
        if (connectionState === 'LIVE') return;
        if (inFlight) {
            schedulePoll(pollDelay);
            return;
        }

        if (document.hidden) {
            schedulePoll(8000);
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

                (data.messages || []).forEach(msg => {
                    if (appendMessageIfNew(msg)) updated = true;
                });
                (data.files || []).forEach(file => {
                    if (appendFileIfNew(file)) updated = true;
                });

                if (updated && shouldStickToBottom) scrollDown();
                pollDelay = 2000;
                setState('DEGRADED');
            })
            .catch(() => {
                pollDelay = Math.min(pollDelay * 1.8, 12000);
                setState('RECONNECTING');
            })
            .finally(() => {
                inFlight = false;
                schedulePoll(pollDelay);
            });
    }

    function startPollingFallback() {
        if (connectionState !== 'LIVE') {
            setState('DEGRADED');
        }
        pollDelay = 1200;
        pollOnce();
    }

    function parseEventData(evt) {
        try {
            return JSON.parse(evt.data);
        } catch (_) {
            return null;
        }
    }

    function clearReconnectTimer() {
        if (reconnectTimer) {
            clearTimeout(reconnectTimer);
            reconnectTimer = null;
        }
    }

    function scheduleReconnect() {
        clearReconnectTimer();
        const delay = Math.min(1000 * (2 ** Math.min(sseFailures, 5)), 20000);
        reconnectTimer = setTimeout(connectSSE, delay);
    }

    function connectSSE() {
        clearReconnectTimer();
        if (sse) {
            sse.close();
            sse = null;
        }

        setState('CONNECTING');
        const stream = new EventSource(`/api/events/${RECEIVER_ID}`);
        sse = stream;

        stream.addEventListener('open', () => {
            if (sse !== stream) return;
            sseFailures = 0;
            stopPolling();
            setState('LIVE');
        });

        stream.addEventListener('message', evt => {
            if (sse !== stream) return;
            const payload = parseEventData(evt);
            if (!payload) return;
            const stickToBottom = isNearBottom(area);
            if (appendMessageIfNew(payload) && stickToBottom) {
                scrollDown();
            }
        });

        stream.addEventListener('file', evt => {
            if (sse !== stream) return;
            const payload = parseEventData(evt);
            if (!payload) return;
            const stickToBottom = isNearBottom(area);
            if (appendFileIfNew(payload) && stickToBottom) {
                scrollDown();
            }
        });

        stream.addEventListener('presence', evt => {
            if (sse !== stream) return;
            const payload = parseEventData(evt);
            if (!payload) return;
            if (payload.user_id === RECEIVER_ID) {
                peerOnline = !!payload.online;
                renderStatus();
            }
        });

        stream.addEventListener('presence_snapshot', evt => {
            if (sse !== stream) return;
            const payload = parseEventData(evt);
            if (!payload) return;
            peerOnline = !!payload.peer_online;
            renderStatus();
        });

        stream.onerror = () => {
            if (sse !== stream) return;
            stream.close();
            sse = null;
            sseFailures += 1;
            setState('RECONNECTING');

            if (sseFailures >= 3) {
                startPollingFallback();
            }
            scheduleReconnect();
        };
    }

    seedSeen();
    renderStatus();
    connectSSE();

    document.addEventListener('visibilitychange', () => {
        if (!document.hidden && connectionState !== 'LIVE') {
            pollDelay = 1200;
            pollOnce();
        }
    });

    window.addEventListener('beforeunload', () => {
        clearReconnectTimer();
        stopPolling();
        if (sse) {
            sse.close();
            sse = null;
        }
    });
})();


/* ---- 3b. SESSION WATCHER (cross-device logout sync) ---- */
(function setupSessionWatcher() {
    const path = window.location.pathname;
    const isAuthPage = path === '/login' || path === '/register';
    if (isAuthPage) return;

    let checkTimer = null;
    let inFlight = false;

    function computeDelay() {
        return document.hidden ? 25000 : 8000;
    }

    function schedule() {
        if (checkTimer) clearTimeout(checkTimer);
        checkTimer = setTimeout(checkSession, computeDelay());
    }

    function redirectToLoginExpired() {
        const next = encodeURIComponent(`${window.location.pathname}${window.location.search}`);
        window.location.href = `/login?expired=1&next=${next}`;
    }

    function checkSession() {
        if (inFlight) {
            schedule();
            return;
        }

        inFlight = true;
        fetch('/api/session/status', {
            method: 'GET',
            headers: { 'X-Requested-With': 'XMLHttpRequest' },
            credentials: 'same-origin'
        })
            .then(res => {
                if (res.status === 401) {
                    redirectToLoginExpired();
                    return null;
                }
                if (!res.ok) {
                    throw new Error('session check failed');
                }
                return res.json();
            })
            .catch(() => {
                // Ignore transient errors and retry on next interval.
            })
            .finally(() => {
                inFlight = false;
                schedule();
            });
    }

    schedule();
    document.addEventListener('visibilitychange', schedule);
    window.addEventListener('beforeunload', () => {
        if (checkTimer) clearTimeout(checkTimer);
    });
})();


/* ---- 4. FILE LABEL UPDATE ---- */
function updateFileLabel() {}

