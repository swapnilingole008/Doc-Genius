// Doc Genius — Q&A Chat Controller

let currentMode = 'normal';
let currentVibe = 'default';
let isWaitingResponse = false;

// Theme Controller
function initTheme() {
    const isLight = localStorage.getItem('docgenius-theme') === 'light';
    if (isLight) {
        document.body.classList.add('light');
    }
}

function toggleTheme() {
    const isLight = document.body.classList.toggle('light');
    localStorage.setItem('docgenius-theme', isLight ? 'light' : 'dark');
}

// Toast
function showToast(message, type = 'info') {
    const container = document.getElementById('toast-container');
    if (!container) return;

    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.textContent = message;

    container.appendChild(toast);
    setTimeout(() => {
        toast.style.opacity = '0';
        toast.style.transition = 'all 0.25s ease';
        setTimeout(() => toast.remove(), 250);
    }, 3500);
}

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    initTheme();
    loadActiveDocument();
});

// Load active document metadata
async function loadActiveDocument() {
    const badgeText = document.getElementById('active-doc-name');
    const sidebarDetails = document.getElementById('sidebar-doc-details');

    try {
        const res = await fetch('/processed_status');
        const data = await res.json();

        if (data.ready && data.files && data.files.length > 0) {
            const names = data.files.map(f => f.title || f.filename).join(', ');
            if (badgeText) badgeText.textContent = names;
            if (sidebarDetails) {
                sidebarDetails.innerHTML = `
                    <p style="font-weight: 600; color: var(--text-primary); margin-bottom: 4px;">✓ ${data.files.length} Document(s) Active</p>
                    <p>${names}</p>
                `;
            }
        } else if (data.files && data.files.length > 0) {
            if (badgeText) badgeText.textContent = "Unindexed Document";
            if (sidebarDetails) {
                sidebarDetails.innerHTML = `
                    <p style="color: var(--accent-amber);">⚠️ Uploaded but not indexed</p>
                    <p>Go to Dashboard and click 'Process &amp; Index' first.</p>
                `;
            }
        } else {
            if (badgeText) badgeText.textContent = "No document loaded";
            if (sidebarDetails) {
                sidebarDetails.innerHTML = `
                    <p style="color: var(--text-muted);">No document uploaded yet.</p>
                    <p>Upload notes or pick a book from the dashboard.</p>
                `;
            }
        }
    } catch (e) {
        if (badgeText) badgeText.textContent = "Offline";
    }
}

// Mode Selection
function selectStudyMode(mode) {
    currentMode = mode;
    const cards = document.querySelectorAll('.mode-card');
    cards.forEach(c => {
        const input = c.querySelector('input');
        if (input.value === mode) {
            c.classList.add('active');
            input.checked = true;
        } else {
            c.classList.remove('active');
        }
    });

    const vibeSub = document.getElementById('vibe-suboptions');
    if (vibeSub) {
        vibeSub.style.display = (mode === 'vibe') ? 'block' : 'none';
    }
}

async function applyModeSettings() {
    const vibeSelect = document.getElementById('vibe-select');
    if (currentMode === 'vibe' && vibeSelect) {
        currentVibe = vibeSelect.value;
    } else {
        currentVibe = 'default';
    }

    try {
        const res = await fetch('/mode-change', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                study_mode: currentMode,
                vibe_type: currentVibe
            })
        });
        const data = await res.json();
        if (res.ok) {
            let label = currentMode.toUpperCase();
            if (currentMode === 'vibe' && vibeSelect) {
                label = vibeSelect.options[vibeSelect.selectedIndex].text;
            }
            showToast(`Mode set to: ${label}`, 'success');
        }
    } catch (e) {
        showToast('Error applying mode settings', 'error');
    }
}

// Simple Markdown Formatter
function renderMarkdown(text) {
    if (!text) return "";
    let html = text
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;');

    // Bold
    html = html.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
    // Italic
    html = html.replace(/\*(.*?)\*/g, '<em>$1</em>');
    // Inline code
    html = html.replace(/`([^`]+)`/g, '<code>$1</code>');
    // Bullet points
    html = html.replace(/^\s*[-*]\s+(.*)$/gm, '<li>$1</li>');
    html = html.replace(/(<li>.*<\/li>)/s, '<ul>$1</ul>');
    // Line breaks
    html = html.replace(/\n\n/g, '</p><p>').replace(/\n/g, '<br>');

    return `<p>${html}</p>`;
}

// Chat Flow
function handleKeyDown(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        handleChatSubmit(e);
    }
}

function askPreset(prompt) {
    const input = document.getElementById('chat-input');
    if (input) {
        input.value = prompt;
        handleChatSubmit(new Event('submit'));
    }
}

async function handleChatSubmit(e) {
    if (e && e.preventDefault) e.preventDefault();
    if (isWaitingResponse) return;

    const input = document.getElementById('chat-input');
    const query = input.value.trim();
    if (!query) return;

    // Hide welcome box on first message
    const welcome = document.getElementById('welcome-box');
    if (welcome) welcome.style.display = 'none';

    // Append user message
    appendMessage(query, 'user');
    input.value = '';

    // Show AI typing placeholder
    const typingId = appendTypingIndicator();
    isWaitingResponse = true;

    try {
        const res = await fetch('/ask', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ question: query })
        });
        const data = await res.json();

        removeTypingIndicator(typingId);
        appendMessage(data.answer || 'No answer received from server.', 'ai');
    } catch (err) {
        removeTypingIndicator(typingId);
        appendMessage('Connection error. Please check server or provide API keys.', 'ai');
    } finally {
        isWaitingResponse = false;
    }
}

function appendMessage(text, role) {
    const container = document.getElementById('chat-messages');
    if (!container) return;

    const bubble = document.createElement('div');
    bubble.className = `message-bubble ${role}`;

    const avatar = document.createElement('div');
    avatar.className = `avatar ${role === 'user' ? 'user-av' : 'ai-av'}`;
    avatar.textContent = role === 'user' ? 'You' : 'DG';

    const content = document.createElement('div');
    content.className = 'bubble-content';

    if (role === 'ai') {
        content.innerHTML = renderMarkdown(text);
    } else {
        content.textContent = text;
    }

    bubble.appendChild(avatar);
    bubble.appendChild(content);

    container.appendChild(bubble);
    container.scrollTop = container.scrollHeight;
}

function appendTypingIndicator() {
    const container = document.getElementById('chat-messages');
    if (!container) return null;

    const id = 'typing-' + Date.now();
    const bubble = document.createElement('div');
    bubble.className = 'message-bubble ai';
    bubble.id = id;

    bubble.innerHTML = `
        <div class="avatar ai-av">DG</div>
        <div class="bubble-content">
            <div class="typing-dots">
                <span class="typing-dot"></span>
                <span class="typing-dot"></span>
                <span class="typing-dot"></span>
            </div>
        </div>
    `;

    container.appendChild(bubble);
    container.scrollTop = container.scrollHeight;
    return id;
}

function removeTypingIndicator(id) {
    if (!id) return;
    const el = document.getElementById(id);
    if (el) el.remove();
}

function clearChat() {
    const container = document.getElementById('chat-messages');
    if (!container) return;

    container.innerHTML = `
        <div class="welcome-box" id="welcome-box">
            <div class="welcome-icon">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path>
                </svg>
            </div>
            <h2>Chat Cleared</h2>
            <p>Ask a new question from your document below.</p>
        </div>
    `;
    showToast('Conversation reset', 'info');
}
