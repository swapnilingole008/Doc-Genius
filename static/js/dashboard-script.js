// Doc Genius — Dashboard Controller

let stagedFiles = [];
let isProcessed = false;

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

// Toast Notifications
function showToast(message, type = 'info') {
    const container = document.getElementById('toast-container');
    if (!container) return;

    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.textContent = message;

    container.appendChild(toast);
    setTimeout(() => {
        toast.style.opacity = '0';
        toast.style.transform = 'translateX(100%)';
        toast.style.transition = 'all 0.25s ease';
        setTimeout(() => toast.remove(), 250);
    }, 4000);
}

// Initialize Dashboard
document.addEventListener('DOMContentLoaded', () => {
    initTheme();
    setupDropzone();
    refreshStagedFiles();
    checkProcessedStatus();
});

// Staged Files & Status
async function refreshStagedFiles() {
    try {
        const res = await fetch('/staged_files');
        if (!res.ok) throw new Error('Failed to load documents');
        stagedFiles = await res.json();
        renderStagedFiles();
        updateProcessButton();
    } catch (e) {
        console.error('Error fetching staged files:', e);
    }
}

function renderStagedFiles() {
    const list = document.getElementById('staged-list');
    const clearBtn = document.getElementById('clear-all-btn');

    if (!list) return;

    if (!stagedFiles || stagedFiles.length === 0) {
        list.innerHTML = '<div class="empty-staged">No documents added yet. Upload a PDF above to begin.</div>';
        if (clearBtn) clearBtn.style.display = 'none';
        return;
    }

    if (clearBtn) clearBtn.style.display = 'block';

    list.innerHTML = stagedFiles.map(file => `
        <div class="staged-item">
            <div class="staged-item-info">
                <div class="staged-file-icon">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="18" height="18">
                        <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
                        <polyline points="14 2 14 8 20 8"></polyline>
                    </svg>
                </div>
                <span class="staged-filename" title="${file.filename}">${file.title || file.filename}</span>
                <span class="staged-source-badge">${file.source === 'book' ? 'Library' : 'Upload'}</span>
            </div>
            <button class="delete-btn" onclick="removeFile('${file.filename}')" title="Remove document">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="16" height="16">
                    <line x1="18" y1="6" x2="6" y2="18"></line>
                    <line x1="6" y1="6" x2="18" y2="18"></line>
                </svg>
            </button>
        </div>
    `).join('');
}

async function removeFile(filename) {
    try {
        const res = await fetch(`/staged_files/${encodeURIComponent(filename)}`, { method: 'DELETE' });
        if (res.ok) {
            showToast(`Removed '${filename}'`, 'info');
            refreshStagedFiles();
            checkProcessedStatus();
        } else {
            showToast('Failed to remove file', 'error');
        }
    } catch (e) {
        showToast('Error removing file', 'error');
    }
}

async function clearAllFiles() {
    if (!confirm('Remove all selected documents?')) return;
    try {
        const res = await fetch('/staged_files', { method: 'DELETE' });
        if (res.ok) {
            showToast('All documents removed', 'info');
            refreshStagedFiles();
            checkProcessedStatus();
        }
    } catch (e) {
        showToast('Error clearing documents', 'error');
    }
}

async function checkProcessedStatus() {
    const pill = document.getElementById('status-pill');
    const text = document.getElementById('status-text');
    if (!pill || !text) return;

    try {
        const res = await fetch('/processed_status');
        const data = await res.json();
        isProcessed = data.ready;

        if (data.ready) {
            pill.className = 'status-pill ready';
            pill.innerHTML = `
                <span class="status-icon">✓</span>
                <span>Active Document Ready (${data.staged_files_count || 1} file indexed)</span>
            `;
        } else if (data.staged_files_count > 0) {
            pill.className = 'status-pill unready';
            pill.innerHTML = `
                <span class="status-icon">⚠️</span>
                <span>${data.staged_files_count} document(s) staged — Click "Process &amp; Index Document" to activate</span>
            `;
        } else {
            pill.className = 'status-pill unready';
            pill.innerHTML = `
                <span class="status-icon">📄</span>
                <span>No document active. Upload or pick a PDF below to start learning.</span>
            `;
        }
    } catch (e) {
        pill.className = 'status-pill unready';
        pill.innerHTML = `<span>⚠️ Offline or connecting...</span>`;
    }
}

function updateProcessButton() {
    const btn = document.getElementById('process-btn');
    if (btn) {
        btn.disabled = stagedFiles.length === 0;
    }
}

// Dropzone & File Upload
function setupDropzone() {
    const dropzone = document.getElementById('pdf-dropzone');
    if (!dropzone) return;

    ['dragenter', 'dragover'].forEach(eventName => {
        dropzone.addEventListener(eventName, (e) => {
            e.preventDefault();
            e.stopPropagation();
            dropzone.classList.add('dragover');
        });
    });

    ['dragleave', 'drop'].forEach(eventName => {
        dropzone.addEventListener(eventName, (e) => {
            e.preventDefault();
            e.stopPropagation();
            dropzone.classList.remove('dragover');
        });
    });

    dropzone.addEventListener('drop', (e) => {
        const files = e.dataTransfer.files;
        if (files.length > 0) uploadFiles(files);
    });
}

function handleFileSelect(e) {
    const files = e.target.files;
    if (files.length > 0) uploadFiles(files);
}

async function uploadFiles(files) {
    const formData = new FormData();
    let hasPdf = false;

    for (let i = 0; i < files.length; i++) {
        if (files[i].name.toLowerCase().endsWith('.pdf')) {
            formData.append('pdf_files', files[i]);
            hasPdf = true;
        }
    }

    if (!hasPdf) {
        showToast('Please upload PDF documents only (.pdf)', 'error');
        return;
    }

    showToast('Uploading PDF document(s)...', 'info');

    try {
        const res = await fetch('/upload_stage', {
            method: 'POST',
            body: formData
        });
        const data = await res.json();
        if (res.ok) {
            showToast(data.message || 'PDF uploaded successfully!', 'success');
            refreshStagedFiles();
            checkProcessedStatus();
        } else {
            showToast(data.error || 'Failed to upload document', 'error');
        }
    } catch (e) {
        showToast('Upload error. Please try again.', 'error');
    }
}

// Processing Content
async function processDocuments() {
    const btn = document.getElementById('process-btn');
    const progress = document.getElementById('process-progress');
    const statusText = document.getElementById('progress-status-text');

    if (btn) btn.disabled = true;
    if (progress) progress.style.display = 'block';
    if (statusText) statusText.textContent = 'Extracting text and building vector search index...';

    try {
        const res = await fetch('/process', { method: 'POST' });
        const data = await res.json();

        if (res.ok) {
            showToast('Document processed & indexed! Ready for Q&A and Exams.', 'success');
            checkProcessedStatus();
        } else {
            showToast(data.error || 'Processing failed.', 'error');
        }
    } catch (e) {
        showToast('Error during document processing.', 'error');
    } finally {
        if (btn) btn.disabled = false;
        if (progress) progress.style.display = 'none';
    }
}

// Books Modal
async function openBooksModal() {
    const modal = document.getElementById('books-modal');
    const grid = document.getElementById('books-grid');
    if (!modal || !grid) return;

    modal.style.display = 'flex';

    try {
        const res = await fetch('/api/books');
        const books = await res.json();

        grid.innerHTML = books.map(b => `
            <div class="book-card" onclick="selectBook('${b.id}')">
                <div>
                    <div class="book-title">${b.title}</div>
                    <div class="book-meta">By ${b.author}</div>
                </div>
                <div>
                    <span class="book-subject">${b.subject}</span>
                </div>
            </div>
        `).join('');
    } catch (e) {
        grid.innerHTML = '<div class="empty-staged">Could not load library books.</div>';
    }
}

function closeBooksModal() {
    const modal = document.getElementById('books-modal');
    if (modal) modal.style.display = 'none';
}

async function selectBook(bookId) {
    showToast('Loading book into your documents...', 'info');
    closeBooksModal();

    try {
        const res = await fetch('/select_book', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ book_id: bookId })
        });
        const data = await res.json();
        if (res.ok) {
            showToast(data.message || 'Book added!', 'success');
            refreshStagedFiles();
            checkProcessedStatus();
        } else {
            showToast(data.error || 'Failed to select book', 'error');
        }
    } catch (e) {
        showToast('Error selecting book', 'error');
    }
}
