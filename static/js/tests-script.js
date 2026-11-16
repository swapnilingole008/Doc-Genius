// Doc Genius — Exam Mode Controller

let selectedDifficulty = 'medium';
let selectedCount = 10;
let currentExam = null;
let currentQuestionIndex = 0;
let userAnswers = {}; // { question_id: "a" }
let examTimer = null;
let secondsElapsed = 0;

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
        toast.style.transform = 'translateX(100%)';
        toast.style.transition = 'all 0.25s ease';
        setTimeout(() => toast.remove(), 250);
    }, 3500);
}

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    initTheme();
    loadSetupDocument();
});

async function loadSetupDocument() {
    const titleEl = document.getElementById('setup-doc-title');
    try {
        const res = await fetch('/processed_status');
        const data = await res.json();

        if (data.ready && data.files && data.files.length > 0) {
            const names = data.files.map(f => f.title || f.filename).join(', ');
            if (titleEl) titleEl.textContent = names;
        } else if (data.files && data.files.length > 0) {
            if (titleEl) titleEl.innerHTML = `<span style="color: var(--accent-amber);">⚠️ Notes added but not indexed — go to Dashboard &amp; click 'Process Document'</span>`;
        } else {
            if (titleEl) titleEl.innerHTML = `<span style="color: var(--accent-rose);">No PDF loaded. Please upload or choose a book from the Dashboard first.</span>`;
        }
    } catch (e) {
        if (titleEl) titleEl.textContent = "Offline or connecting...";
    }
}

// Selection Handlers
function selectDifficulty(diff) {
    selectedDifficulty = diff;
    const btns = document.querySelectorAll('#difficulty-pills .pill-btn');
    btns.forEach(b => {
        if (b.getAttribute('data-diff') === diff) {
            b.classList.add('active');
        } else {
            b.classList.remove('active');
        }
    });
}

function selectCount(count) {
    selectedCount = count;
    const btns = document.querySelectorAll('#count-pills .count-btn');
    btns.forEach(b => {
        if (parseInt(b.getAttribute('data-count')) === count) {
            b.classList.add('active');
        } else {
            b.classList.remove('active');
        }
    });
}

// Generate Exam
async function generateExam() {
    const btn = document.getElementById('generate-btn');
    if (btn) {
        btn.disabled = true;
        btn.innerHTML = `<span>Generating exam questions from your document...</span>`;
    }

    try {
        const res = await fetch('/generate_test', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                difficulty: selectedDifficulty,
                num_questions: selectedCount
            })
        });

        const data = await res.json();

        if (!res.ok) {
            showToast(data.error || 'Failed to generate test. Ensure document is processed.', 'error');
            return;
        }

        currentExam = data;
        userAnswers = {};
        currentQuestionIndex = 0;
        startExamRunner();
    } catch (e) {
        showToast('Error connecting to exam service. Please try again.', 'error');
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = `
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="18" height="18"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"></polygon></svg>
                <span>Generate &amp; Start Exam</span>
            `;
        }
    }
}

// Quiz Runner
function startExamRunner() {
    document.getElementById('setup-view').style.display = 'none';
    document.getElementById('results-view').style.display = 'none';
    document.getElementById('runner-view').style.display = 'block';

    secondsElapsed = 0;
    startTimer();
    renderNavigatorStrip();
    renderCurrentQuestion();
}

function startTimer() {
    if (examTimer) clearInterval(examTimer);
    examTimer = setInterval(() => {
        secondsElapsed++;
        const mins = String(Math.floor(secondsElapsed / 60)).padStart(2, '0');
        const secs = String(secondsElapsed % 60).padStart(2, '0');
        const timerEl = document.getElementById('elapsed-time');
        if (timerEl) timerEl.textContent = `${mins}:${secs}`;
    }, 1000);
}

function stopTimer() {
    if (examTimer) {
        clearInterval(examTimer);
        examTimer = null;
    }
}

function renderNavigatorStrip() {
    const strip = document.getElementById('nav-strip');
    if (!strip || !currentExam) return;

    strip.innerHTML = currentExam.questions.map((q, idx) => `
        <button type="button" class="nav-pill ${idx === currentQuestionIndex ? 'active' : ''} ${userAnswers[q.id] ? 'answered' : ''}" 
                onclick="jumpToQuestion(${idx})">
            ${idx + 1}
        </button>
    `).join('');
}

function renderCurrentQuestion() {
    if (!currentExam || !currentExam.questions[currentQuestionIndex]) return;

    const q = currentExam.questions[currentQuestionIndex];
    const total = currentExam.questions.length;

    // Meta & Progress
    document.getElementById('q-topic-tag').textContent = q.topic || 'Core Concept';
    document.getElementById('q-progress-text').textContent = `Question ${currentQuestionIndex + 1} of ${total}`;
    document.getElementById('runner-fill').style.width = `${((currentQuestionIndex + 1) / total) * 100}%`;

    // Question Text
    document.getElementById('question-text').textContent = q.question;

    // Options
    const grid = document.getElementById('options-grid');
    const opts = q.options || {};
    const selected = userAnswers[q.id];

    grid.innerHTML = ['a', 'b', 'c', 'd'].map(optKey => {
        const text = opts[optKey];
        if (!text) return '';
        const isSelected = selected === optKey;
        return `
            <div class="option-card ${isSelected ? 'selected' : ''}" onclick="selectAnswer(${q.id}, '${optKey}')">
                <div class="option-letter">${optKey.toUpperCase()}</div>
                <div class="option-text">${text}</div>
            </div>
        `;
    }).join('');

    // Navigation buttons
    document.getElementById('prev-btn').disabled = currentQuestionIndex === 0;

    const nextBtn = document.getElementById('next-btn');
    const submitBtn = document.getElementById('submit-btn');

    if (currentQuestionIndex === total - 1) {
        nextBtn.style.display = 'none';
        submitBtn.style.display = 'inline-flex';
    } else {
        nextBtn.style.display = 'inline-flex';
        submitBtn.style.display = 'none';
    }

    renderNavigatorStrip();
}

function selectAnswer(questionId, optionKey) {
    userAnswers[questionId] = optionKey;
    renderCurrentQuestion();
}

function goToPrevQuestion() {
    if (currentQuestionIndex > 0) {
        currentQuestionIndex--;
        renderCurrentQuestion();
    }
}

function goToNextQuestion() {
    if (currentExam && currentQuestionIndex < currentExam.questions.length - 1) {
        currentQuestionIndex++;
        renderCurrentQuestion();
    }
}

function jumpToQuestion(idx) {
    if (currentExam && idx >= 0 && idx < currentExam.questions.length) {
        currentQuestionIndex = idx;
        renderCurrentQuestion();
    }
}

function confirmQuitExam() {
    if (confirm('Are you sure you want to quit this exam? Your progress will be lost.')) {
        stopTimer();
        resetToSetup();
    }
}

// Submit Exam & Scoring
async function submitExam() {
    if (!currentExam) return;

    const total = currentExam.questions.length;
    const answeredCount = Object.keys(userAnswers).length;

    if (answeredCount < total) {
        if (!confirm(`You have answered ${answeredCount} of ${total} questions. Do you want to submit anyway?`)) {
            return;
        }
    }

    stopTimer();

    // Calculate score locally
    let score = 0;
    currentExam.questions.forEach(q => {
        if (userAnswers[q.id] && userAnswers[q.id].toLowerCase() === q.correct_option.toLowerCase()) {
            score++;
        }
    });

    try {
        await fetch('/submit_test', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                test_id: currentExam.test_id,
                score: score,
                total: total,
                answers: userAnswers
            })
        });
    } catch (e) {
        console.error('Failed to save score to server:', e);
    }

    renderResults(score, total);
}

function renderResults(score, total) {
    document.getElementById('runner-view').style.display = 'none';
    document.getElementById('results-view').style.display = 'block';

    const percentage = Math.round((score / total) * 100);
    document.getElementById('score-percentage').textContent = `${percentage}%`;

    let headline = 'Great Job!';
    if (percentage >= 90) headline = 'Outstanding Mastery! 🏆';
    else if (percentage >= 75) headline = 'Solid Performance! ✨';
    else if (percentage >= 50) headline = 'Good Effort — Keep Reviewing! 📖';
    else headline = 'Review the Explanations Below! 💡';

    document.getElementById('results-headline').textContent = headline;
    document.getElementById('results-summary-text').textContent = 
        `You scored ${score} out of ${total} (${percentage}%) in ${document.getElementById('elapsed-time').textContent}.`;

    // Render detailed question-by-question review
    const reviewList = document.getElementById('review-list');
    reviewList.innerHTML = currentExam.questions.map((q, idx) => {
        const userChoice = userAnswers[q.id];
        const correctChoice = q.correct_option ? q.correct_option.toLowerCase() : '';
        const isCorrect = userChoice && userChoice.toLowerCase() === correctChoice;

        return `
            <div class="review-card ${isCorrect ? 'correct' : 'incorrect'}">
                <div class="review-card-head">
                    <span class="badge-tag">${q.topic || 'Topic'}</span>
                    <span class="review-badge">${isCorrect ? '✓ Correct' : (userChoice ? '✗ Incorrect' : '⊘ Skipped')}</span>
                </div>
                <div class="review-q-text">${idx + 1}. ${q.question}</div>
                <div class="review-options">
                    ${['a', 'b', 'c', 'd'].map(optKey => {
                        const optText = q.options[optKey];
                        if (!optText) return '';
                        const isUser = userChoice === optKey;
                        const isRight = correctChoice === optKey;
                        let cls = '';
                        if (isRight) cls = 'correct-choice';
                        else if (isUser && !isRight) cls = 'user-choice';

                        return `
                            <div class="review-opt-line ${cls}">
                                <strong>${optKey.toUpperCase()}:</strong> ${optText}
                                ${isUser && isRight ? ' (Your choice - Correct!)' : ''}
                                ${isUser && !isRight ? ' (Your choice)' : ''}
                                ${!isUser && isRight ? ' (Correct Answer)' : ''}
                            </div>
                        `;
                    }).join('')}
                </div>
                ${q.explanation ? `
                    <div class="review-explanation">
                        <strong>Explanation from Document:</strong> ${q.explanation}
                    </div>
                ` : ''}
            </div>
        `;
    }).join('');
}

function resetToSetup() {
    document.getElementById('runner-view').style.display = 'none';
    document.getElementById('results-view').style.display = 'none';
    document.getElementById('setup-view').style.display = 'block';
    currentExam = null;
    userAnswers = {};
    currentQuestionIndex = 0;
}