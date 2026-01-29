// App State
const state = {
    words: [],
    categories: [],
    backupReminderShown: false,
    currentFilter: 'all',
    searchQuery: ''
};

// DOM Elements
document.addEventListener('DOMContentLoaded', () => {
    initApp();
});

async function initApp() {
    setupNavigation();
    setupModals();
    setupSearchAndFilter();
    await loadInitialData();
    checkBackupReminder();
}

function setupNavigation() {
    const navBtns = document.querySelectorAll('.nav-btn[data-tab]');
    navBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            // Remove active class from all
            navBtns.forEach(b => b.classList.remove('active'));
            document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
            
            // Activate current
            btn.classList.add('active');
            const tabId = btn.getAttribute('data-tab');
            document.getElementById(`${tabId}-tab`).classList.add('active');
            
            if (tabId === 'collection') {
                renderCollection();
            }
        });
    });

    // Backup button
    const backupBtn = document.querySelector('.nav-btn[data-action="backup"]');
    if (backupBtn) {
        backupBtn.addEventListener('click', () => {
            openModal('backup-modal');
        });
    }
}

function setupModals() {
    window.closeModal = (id) => {
        document.getElementById(id).classList.remove('open');
    };

    window.openModal = (id) => {
        document.getElementById(id).classList.add('open');
    };

    const addWordForm = document.getElementById('add-word-form');
    if (addWordForm) {
        addWordForm.addEventListener('submit', handleAddWord);
    }

    const importForm = document.getElementById('import-form');
    if (importForm) {
        importForm.addEventListener('submit', handleImport);
    }
}

function setupSearchAndFilter() {
    const searchInput = document.getElementById('search-input');
    const categoryFilter = document.getElementById('category-filter');

    if (searchInput) {
        searchInput.addEventListener('input', (e) => {
            state.searchQuery = e.target.value.toLowerCase();
            renderCollection();
        });
    }

    if (categoryFilter) {
        categoryFilter.addEventListener('change', (e) => {
            state.currentFilter = e.target.value;
            renderCollection();
        });
    }
}

async function loadInitialData() {
    try {
        const statusRes = await fetch('/api/status');
        const statusData = await statusRes.json();
        updateStats(statusData);

        // Load all words
        const wordsRes = await fetch('/api/download_all');
        const wordsData = await wordsRes.json();
        if (wordsData.words) {
            state.words = wordsData.words;
            renderRecentWords(state.words.slice(0, 6)); // Show 6 recent
            populateCategoryFilter();
        }
        
    } catch (error) {
        console.error('Failed to load data:', error);
    }
}

function populateCategoryFilter() {
    const categories = [...new Set(state.words.map(w => w.category || 'General Vocabulary'))];
    state.categories = categories;
    
    const filterSelect = document.getElementById('category-filter');
    if (filterSelect) {
        filterSelect.innerHTML = '<option value="all">All Categories</option>' + 
            categories.map(c => `<option value="${c}">${c}</option>`).join('');
    }
}

function renderRecentWords(words) {
    const grid = document.getElementById('recent-words-grid');
    if (!grid) return;
    
    grid.innerHTML = words.map(word => `
        <div class="word-card">
            <h3>${word.word}</h3>
            <p>${word.meaning_bangla || word.meaning_english}</p>
        </div>
    `).join('');
}

function renderCollection() {
    const list = document.getElementById('collection-list');
    if (!list) return;

    let filtered = state.words;

    // Filter by Category
    if (state.currentFilter !== 'all') {
        filtered = filtered.filter(w => w.category === state.currentFilter);
    }

    // Filter by Search
    if (state.searchQuery) {
        filtered = filtered.filter(w => 
            w.word.toLowerCase().includes(state.searchQuery) || 
            (w.meaning_english && w.meaning_english.toLowerCase().includes(state.searchQuery)) ||
            (w.meaning_bangla && w.meaning_bangla.toLowerCase().includes(state.searchQuery))
        );
    }

    if (filtered.length === 0) {
        list.innerHTML = `<div class="empty-state"><p>No words found.</p></div>`;
        return;
    }

    list.innerHTML = `<div class="word-grid">` + filtered.map(word => `
        <div class="word-card">
            <div class="card-header">
                <h3>${word.word}</h3>
                <span class="category-tag">${word.category || 'General'}</span>
            </div>
            <div class="card-body">
                <p><strong>🇧🇩</strong> ${word.meaning_bangla || '-'}</p>
                <p><strong>🇬🇧</strong> ${word.meaning_english || '-'}</p>
                ${word.synonyms ? `<p class="synonyms"><em>Syn: ${word.synonyms}</em></p>` : ''}
            </div>
        </div>
    `).join('') + `</div>`;
}

function updateStats(data) {
    document.getElementById('total-words').textContent = data.total_words || 0;
    document.getElementById('total-categories').textContent = data.category_count || 0;
}

async function handleAddWord(e) {
    e.preventDefault();
    const formData = new FormData(e.target);
    const data = Object.fromEntries(formData.entries());
    
    // Default device ID
    data.device_id = localStorage.getItem('device_id') || 'cloud_user';

    try {
        const response = await fetch('/api/words/add', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });

        if (response.ok) {
            alert('Word added successfully!');
            e.target.reset();
            closeModal('add-word-modal');
            loadInitialData(); // Reload data
        } else {
            const err = await response.json();
            alert('Error: ' + err.message);
        }
    } catch (error) {
        console.error('Error adding word:', error);
        alert('Failed to connect to server.');
    }
}

async function handleImport(e) {
    e.preventDefault();
    const formData = new FormData(e.target);
    const deviceId = localStorage.getItem('device_id') || 'cloud_user';
    formData.append('device_id', deviceId);

    const btn = e.target.querySelector('button[type="submit"]');
    const status = document.getElementById('import-status');
    
    try {
        btn.disabled = true;
        btn.textContent = 'Importing...';
        status.textContent = 'Uploading...';

        const response = await fetch('/api/import_excel', {
            method: 'POST',
            body: formData
        });

        const result = await response.json();

        if (response.ok) {
            status.textContent = 'Success! Reloading...';
            status.style.color = 'green';
            setTimeout(() => {
                closeModal('import-modal');
                e.target.reset();
                loadInitialData(); // This will re-fetch words and update Collection/Stats
                renderCollection();
                status.textContent = '';
                btn.disabled = false;
                btn.textContent = 'Import';
                alert(result.message || 'Import successful!');
            }, 1000);
        } else {
            throw new Error(result.message || 'Import failed');
        }
    } catch (error) {
        console.error('Import error:', error);
        status.textContent = 'Error: ' + error.message;
        status.style.color = 'red';
        btn.disabled = false;
        btn.textContent = 'Import';
    }
}

function checkBackupReminder() {
    if (window.innerWidth > 768 && !state.backupReminderShown) {
        setTimeout(() => {
            openModal('backup-modal');
            state.backupReminderShown = true;
        }, 5000);
    }
}


// ==========================================
// QUIZ LOGIC
// ==========================================

const quizState = {
    active: false,
    questions: [],
    currentQuestionIndex: 0,
    score: 0,
    timer: null,
    seconds: 0
};

function startQuiz(mode, count) {
    // 1. Filter words based on mode
    let pool = [];
    if (mode === 'all' || mode === 'mixed') {
        pool = [...state.words];
    } else if (mode === 'hard') {
        // Mock hard logic: words with long length or specific category
        pool = state.words.filter(w => w.word.length > 6); 
    }
    
    // Fallback if pool is too small
    if (pool.length < 5) {
        pool = [...state.words];
        if (pool.length < 5) {
            alert("Not enough words to start a quiz! Add more words first.");
            return;
        }
    }

    // 2. Select random words
    const selectedWords = [];
    const usedIndices = new Set();
    while (selectedWords.length < count && selectedWords.length < pool.length) {
        const idx = Math.floor(Math.random() * pool.length);
        if (!usedIndices.has(idx)) {
            usedIndices.add(idx);
            selectedWords.push(pool[idx]);
        }
    }

    // 3. Generate Questions (Multiple Choice)
    quizState.questions = selectedWords.map(word => {
        // Generate distractors
        const distractors = [];
        const distractorIndices = new Set();
        distractorIndices.add(state.words.indexOf(word)); // Exclude correct answer

        while (distractors.length < 3) {
            const idx = Math.floor(Math.random() * state.words.length);
            if (!distractorIndices.has(idx)) {
                distractorIndices.add(idx);
                distractors.push(state.words[idx].meaning_bangla || state.words[idx].meaning_english);
            }
        }

        const options = [word.meaning_bangla || word.meaning_english, ...distractors];
        // Shuffle options
        options.sort(() => Math.random() - 0.5);

        return {
            question: word.word,
            correctAnswer: word.meaning_bangla || word.meaning_english,
            options: options,
            type: 'mcq'
        };
    });

    // 4. Initialize State
    quizState.active = true;
    quizState.currentQuestionIndex = 0;
    quizState.score = 0;
    quizState.seconds = 0;

    // 5. Update UI
    document.getElementById('quiz-welcome').classList.add('hidden');
    document.getElementById('quiz-active').classList.remove('hidden');
    document.getElementById('quiz-results').classList.add('hidden');
    
    renderQuestion();
    startTimer();
}

function renderQuestion() {
    const q = quizState.questions[quizState.currentQuestionIndex];
    if (!q) {
        endQuiz();
        return;
    }

    // Update Counter
    document.getElementById('question-counter').textContent = 
        `${quizState.currentQuestionIndex + 1}/${quizState.questions.length}`;
    
    // Update Progress Bar
    const percent = ((quizState.currentQuestionIndex) / quizState.questions.length) * 100;
    document.getElementById('quiz-progress').style.width = `${percent}%`;

    // Render Card
    const card = document.getElementById('question-card');
    card.innerHTML = `
        <div class="question-text">
            <h3>What is the meaning of:</h3>
            <h1 class="highlight-text">${q.question}</h1>
        </div>
        <div class="options-grid">
            ${q.options.map((opt, i) => `
                <button class="option-btn" onclick="handleAnswer(this, '${opt.replace(/'/g, "\\'")}')">
                    ${opt}
                </button>
            `).join('')}
        </div>
    `;
}

function handleAnswer(btn, selectedOption) {
    if (btn.disabled) return; // Prevent double clicking

    // Disable all buttons
    const buttons = document.querySelectorAll('.option-btn');
    buttons.forEach(b => b.disabled = true);

    const q = quizState.questions[quizState.currentQuestionIndex];
    const isCorrect = selectedOption === q.correctAnswer;

    if (isCorrect) {
        btn.classList.add('correct');
        quizState.score++;
    } else {
        btn.classList.add('wrong');
        // Highlight correct answer
        buttons.forEach(b => {
             // Remove escaped single quotes for comparison if needed, or simple string match
             // Assuming simple text content match for now
             if (b.innerText.trim() === q.correctAnswer.trim()) {
                 b.classList.add('correct');
             }
        });
    }

    // Auto advance
    setTimeout(() => {
        quizState.currentQuestionIndex++;
        if (quizState.currentQuestionIndex < quizState.questions.length) {
            renderQuestion();
        } else {
            endQuiz();
        }
    }, 1500);
}

function startTimer() {
    if (quizState.timer) clearInterval(quizState.timer);
    document.getElementById('quiz-timer').textContent = "00:00";
    
    quizState.timer = setInterval(() => {
        quizState.seconds++;
        const m = Math.floor(quizState.seconds / 60).toString().padStart(2, '0');
        const s = (quizState.seconds % 60).toString().padStart(2, '0');
        document.getElementById('quiz-timer').textContent = `${m}:${s}`;
    }, 1000);
}

function endQuiz() {
    clearInterval(quizState.timer);
    quizState.active = false;

    // Hide Active, Show Results
    document.getElementById('quiz-active').classList.add('hidden');
    document.getElementById('quiz-results').classList.remove('hidden');

    const accuracy = Math.round((quizState.score / quizState.questions.length) * 100);
    
    const resultsContainer = document.getElementById('quiz-results');
    resultsContainer.innerHTML = `
        <div class="results-card">
            <span class="material-icons-round result-icon">emoji_events</span>
            <h2>Quiz Complete!</h2>
            <div class="score-display">
                <span class="score-value">${accuracy}%</span>
                <span class="score-label">Accuracy</span>
            </div>
            <div class="results-stats">
                <div class="stat">
                    <strong>${quizState.score}/${quizState.questions.length}</strong>
                    <span>Correct</span>
                </div>
                <div class="stat">
                    <strong>${Math.floor(quizState.seconds / 60)}:${(quizState.seconds % 60).toString().padStart(2, '0')}</strong>
                    <span>Time</span>
                </div>
            </div>
            <button class="primary-btn" onclick="resetQuiz()">
                <span class="material-icons-round">replay</span>
                Play Again
            </button>
        </div>
    `;

    // Update avg score on dashboard (simple implementation)
    document.getElementById('quiz-score').textContent = `${accuracy}%`;
}

function resetQuiz() {
    document.getElementById('quiz-results').classList.add('hidden');
    document.getElementById('quiz-welcome').classList.remove('hidden');
}

// Global scope export for HTML onclick handlers
window.startQuiz = startQuiz;
window.handleAnswer = handleAnswer;
window.resetQuiz = resetQuiz;


async function initApp() {
    setupNavigation();
    setupModals();
    await loadInitialData();
    checkBackupReminder();
}

function setupNavigation() {
    const navBtns = document.querySelectorAll('.nav-btn[data-tab]');
    navBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            // Remove active class from all
            navBtns.forEach(b => b.classList.remove('active'));
            document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
            
            // Activate current
            btn.classList.add('active');
            const tabId = btn.getAttribute('data-tab');
            document.getElementById(`${tabId}-tab`).classList.add('active');
        });
    });

    // Backup button
    const backupBtn = document.querySelector('.nav-btn[data-action="backup"]');
    if (backupBtn) {
        backupBtn.addEventListener('click', () => {
            openModal('backup-modal');
        });
    }
}

function setupModals() {
    // Generic modal closing
    window.closeModal = (id) => {
        document.getElementById(id).classList.remove('open');
    };

    window.openModal = (id) => {
        document.getElementById(id).classList.add('open');
    };

    // Form handling
    const addWordForm = document.getElementById('add-word-form');
    if (addWordForm) {
        addWordForm.addEventListener('submit', handleAddWord);
    }
}

async function loadInitialData() {
    try {
        const statusRes = await fetch('/api/status');
        const statusData = await statusRes.json();
        updateStats(statusData);

        // Load recent words
        const wordsRes = await fetch('/api/download_all');
        const wordsData = await wordsRes.json();
        if (wordsData.words) {
            state.words = wordsData.words;
            renderRecentWords(state.words.slice(0, 6)); // Show 6 recent
        }
        
    } catch (error) {
        console.error('Failed to load data:', error);
    }
}

function renderRecentWords(words) {
    const grid = document.getElementById('recent-words-grid');
    grid.innerHTML = words.map(word => `
        <div class="word-card">
            <h3>${word.word}</h3>
            <p>${word.meaning_bangla || word.meaning_english}</p>
        </div>
    `).join('');
}

function updateStats(data) {
    document.getElementById('total-words').textContent = data.total_words || 0;
    document.getElementById('total-categories').textContent = data.category_count || 0;
}

async function handleAddWord(e) {
    e.preventDefault();
    const formData = new FormData(e.target);
    const data = Object.fromEntries(formData.entries()); // Simple data for now
    
    // In a real app, you'd send this to the server
    // await fetch('/api/words/add', { ... })
    
    console.log('Adding word:', data);
    closeModal('add-word-modal');
    alert('Word added! (This is a simplified demo callback)');
}

function checkBackupReminder() {
    // Only show on desktop version if not shown before
    if (window.innerWidth > 768 && !state.backupReminderShown) {
        // Show backup modal after 5 seconds
        setTimeout(() => {
            openModal('backup-modal');
            state.backupReminderShown = true;
        }, 5000);
    }
}

window.downloadBackup = function() {
    window.location.href = '/api/backup/download?format=json'; // Adjust endpoint as needed
}
