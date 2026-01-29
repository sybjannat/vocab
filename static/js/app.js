// App State
const state = {
    words: [],
    categories: [],
    backupReminderShown: false,
    currentFilter: 'all',
    currentSort: 'newest',
    searchQuery: ''
};

// DOM Elements & Init
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

// ---------------------------------------------------------
// SETUP & NAVIGATION
// ---------------------------------------------------------

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
            if (tabId === 'analytics') {
                renderAnalytics();
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
        if (id === 'manage-categories-modal') {
            renderManageCategories();
        }
    };

    const addWordForm = document.getElementById('add-word-form');
    if (addWordForm) {
        addWordForm.addEventListener('submit', handleAddWord);
    }

    const editWordForm = document.getElementById('edit-word-form');
    if (editWordForm) {
        editWordForm.addEventListener('submit', handleEditWord);
    }

    const importForm = document.getElementById('import-form');
    if (importForm) {
        importForm.addEventListener('submit', handleImport);
    }

    const addCategoryForm = document.getElementById('add-category-form');
    if (addCategoryForm) {
        addCategoryForm.addEventListener('submit', handleAddCategory);
    }
}

function setupSearchAndFilter() {
    const searchInput = document.getElementById('search-input');
    const categoryFilter = document.getElementById('category-filter');
    const sortSelect = document.getElementById('sort-select');

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

    if (sortSelect) {
        sortSelect.addEventListener('change', (e) => {
            state.currentSort = e.target.value;
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
            renderAnalytics(); 
        }
        
    } catch (error) {
        console.error('Failed to load data:', error);
    }
}

// ---------------------------------------------------------
// RENDERING & HELPERS
// ---------------------------------------------------------

function populateCategoryFilter() {
    const categories = [...new Set(state.words.map(w => w.category || 'General Vocabulary'))];
    state.categories = categories;
    
    // 1. Filter Dropdown
    const filterSelect = document.getElementById('category-filter');
    if (filterSelect) {
        // Keep current selection if possible
        const currentVal = filterSelect.value;
        filterSelect.innerHTML = '<option value="all">All Categories</option>' + 
            categories.map(c => `<option value="${c}">${c}</option>`).join('');
        if (categories.includes(currentVal)) filterSelect.value = currentVal;
    }

    // 2. Add/Edit Modal Dropdowns
    const addCatSelect = document.getElementById('add-word-category');
    const editCatSelect = document.getElementById('edit-word-category');
    
    [addCatSelect, editCatSelect].forEach(select => {
        if (select) {
            select.innerHTML = categories.map(c => `<option value="${c}">${c}</option>`).join('');
        }
    });

    // 3. Manage Categories List
    renderManageCategories();
}

function renderRecentWords(words) {
    const grid = document.getElementById('recent-words-grid');
    if (!grid) return;
    
    if (words.length === 0) {
        grid.innerHTML = '<p class="text-muted">No words added yet.</p>';
        return;
    }

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

    let filtered = [...state.words];

    // Filter by Category
    if (state.currentFilter && state.currentFilter !== 'all') {
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

    // Sort
    const sortMode = state.currentSort || 'newest';
    filtered.sort((a, b) => {
        if (sortMode === 'newest') return new Date(b.date_added) - new Date(a.date_added);
        if (sortMode === 'oldest') return new Date(a.date_added) - new Date(b.date_added);
        if (sortMode === 'az') return a.word.localeCompare(b.word);
        if (sortMode === 'za') return b.word.localeCompare(a.word);
        return 0;
    });

    if (filtered.length === 0) {
        list.innerHTML = `<div class="empty-state"><p>No words found matching your criteria.</p></div>`;
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
            <div class="card-actions">
                <button onclick="handlePronounce('${word.word}')" class="icon-btn" title="Pronounce">
                    <span class="material-icons-round">volume_up</span>
                </button>
                <button onclick="openEditModal(${word.id})" class="icon-btn" title="Edit">
                    <span class="material-icons-round">edit</span>
                </button>
                <button onclick="handleDeleteWord(${word.id})" class="icon-btn danger" title="Delete">
                    <span class="material-icons-round">delete</span>
                </button>
            </div>
        </div>
    `).join('') + `</div>`;
}

function updateStats(data) {
    const totalEl = document.getElementById('total-words');
    const catEl = document.getElementById('total-categories');
    if(totalEl) totalEl.textContent = data.total_words || 0;
    if(catEl) catEl.textContent = data.category_count || 0;
}

function renderManageCategories() {
    const list = document.getElementById('manage-category-list');
    const modal = document.getElementById('manage-categories-modal');
    // Only render if modal exists and is open (or just exists)
    if (!list || !modal || !modal.classList.contains('open')) return;

    list.innerHTML = state.categories.map(c => `
        <div class="category-item" style="display: flex; justify-content: space-between; align-items: center; padding: 10px; border-bottom: 1px solid #eee;">
            <span>${c}</span>
            ${c !== 'General Vocabulary' ? `
                <button onclick="handleDeleteCategory('${c.replace(/'/g, "\\'")}')" class="icon-btn small danger">
                    <span class="material-icons-round" style="font-size: 18px; color: var(--danger);">delete</span>
                </button>
            ` : '<span class="default-badge" style="font-size: 0.8rem; color: #888;">Default</span>'}
        </div>
    `).join('');
}

// ---------------------------------------------------------
// HANDLERS
// ---------------------------------------------------------

async function handleAddWord(e) {
    e.preventDefault();
    const btn = e.target.querySelector('button[type="submit"]');
    btn.disabled = true;
    
    const formData = new FormData(e.target);
    const data = Object.fromEntries(formData.entries());
    
    data.device_id = localStorage.getItem('device_id') || 'cloud_user';

    try {
        const response = await fetch('/api/words/add', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });

        const result = await response.json();

        if (response.ok) {
            alert('Word added successfully!');
            e.target.reset();
            closeModal('add-word-modal');
            loadInitialData(); 
        } else {
            alert('Error: ' + result.message);
        }
    } catch (error) {
        console.error('Error adding word:', error);
        alert('Failed to connect to server.');
    } finally {
        btn.disabled = false;
    }
}

async function handleEditWord(e) {
    e.preventDefault();
    const btn = e.target.querySelector('button[type="submit"]');
    btn.disabled = true;

    const formData = new FormData(e.target);
    const data = Object.fromEntries(formData.entries());
    
    try {
        const response = await fetch('/api/words/edit', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });

        if (response.ok) {
            alert('Word updated!');
            closeModal('edit-word-modal');
            await loadInitialData(); 
            renderCollection(); // Ensure collection is refreshed
        } else {
            const res = await response.json();
            alert('Failed: ' + res.message);
        }
    } catch (err) {
        console.error(err);
        alert('Error updating word');
    } finally {
        btn.disabled = false;
    }
}

async function handleDeleteWord(id) {
    if (!confirm('Are you sure you want to delete this word?')) return;
    
    try {
        const response = await fetch('/api/words/delete', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ id: id })
        });

        if (response.ok) {
            // Optimistically remove from state or reload
            state.words = state.words.filter(w => w.id !== id);
            renderCollection();
            updateStats({ total_words: state.words.length, category_count: state.categories.length }); // Approx update
            loadInitialData(); // Full sync
        } else {
            const res = await response.json();
            alert('Error: ' + res.message);
        }
    } catch (err) {
        console.error(err);
    }
}

async function handleAddCategory(e) {
    e.preventDefault();
    const input = e.target.querySelector('[name="name"]');
    const name = input.value.trim();
    if (!name) return;

    try {
        const response = await fetch('/api/categories/add', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name: name })
        });

        if (response.ok) {
            input.value = '';
            await loadInitialData(); // Refresh everything
            renderManageCategories(); // Refresh list
            alert(`Category "${name}" added!`);
        } else {
            const res = await response.json();
            alert(res.message);
        }
    } catch(err) { console.error(err); }
}

async function handleDeleteCategory(name) {
    if (!confirm(`Delete category "${name}"? Words will be moved to "General Vocabulary".`)) return;

    try {
        const response = await fetch('/api/categories/delete', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name: name })
        });

        if (response.ok) {
            await loadInitialData();
            renderManageCategories();
            alert('Category deleted.');
        } else {
            const res = await response.json();
            alert(res.message);
        }
    } catch(err) { console.error(err); }
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
                loadInitialData();
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

function handlePronounce(text) {
    if ('speechSynthesis' in window) {
        const utterance = new SpeechSynthesisUtterance(text);
        utterance.lang = 'en-US';
        window.speechSynthesis.speak(utterance);
    } else {
        alert("Browser doesn't support Text-to-Speech");
    }
}

function openEditModal(id) {
    const word = state.words.find(w => w.id === id);
    if (!word) return;

    const form = document.getElementById('edit-word-form');
    // Populate fields
    const fields = ['id', 'word', 'meaning_bangla', 'meaning_english', 'synonyms', 'example_sentence'];
    fields.forEach(f => {
        if(form.querySelector(`[name="${f}"]`)) 
            form.querySelector(`[name="${f}"]`).value = word[f] || '';
    });
    
    // Category select
    const catSelect = form.querySelector('[name="category"]');
    if(catSelect) catSelect.value = word.category || 'General Vocabulary';

    openModal('edit-word-modal');
}


// ---------------------------------------------------------
// ANALYTICS
// ---------------------------------------------------------

async function renderAnalytics() {
    try {
        const res = await fetch('/api/analytics');
        const data = await res.json();
        
        // Update stats
        const totalEl = document.getElementById('analytics-total-words');
        const accEl = document.getElementById('analytics-accuracy');
        if(totalEl) totalEl.textContent = data.total_words;
        if(accEl) accEl.textContent = `${data.avg_accuracy}%`;
        
        // Render Category Bars
        const container = document.getElementById('analytics-category-bars');
        if (container && data.category_breakdown) {
            const max = Math.max(...data.category_breakdown.map(d => d.count)) || 1;
            
            container.innerHTML = data.category_breakdown.map(cat => `
                <div class="chart-row" style="margin-bottom: 12px;">
                    <div style="display:flex; justify-content:space-between; font-size: 0.9rem; margin-bottom: 4px;">
                        <span>${cat.name}</span>
                        <span>${cat.count}</span>
                    </div>
                    <div class="chart-bar-container" style="background: rgba(255,255,255,0.1); height: 8px; border-radius: 4px; overflow: hidden;">
                        <div class="chart-bar" style="width: ${(cat.count / max) * 100}%; background: var(--success); height: 100%;"></div>
                    </div>
                </div>
            `).join('');
        }
    } catch(err) { console.error("Analytics error", err); }
}

// ---------------------------------------------------------
// QUIZ LOGIC
// ---------------------------------------------------------

const quizState = {
    active: false,
    questions: [],
    currentQuestionIndex: 0,
    score: 0,
    timer: null,
    seconds: 0
};

function startQuiz(mode, count) {
    let pool = [];
    if (mode === 'all' || mode === 'mixed') {
        pool = [...state.words];
    } else if (mode === 'hard') {
        pool = state.words.filter(w => w.word.length > 6);
    }
    
    if (pool.length < 5) {
        // Try fallback to all words if filter returned too few
        pool = [...state.words];
        if (pool.length < 5) {
            alert("Not enough words to start a quiz! Add at least 5 words.");
            return;
        }
    }

    // Select random words
    const selectedWords = [];
    const usedIndices = new Set();
    // Cap count at pool length
    if (count > pool.length) count = pool.length;

    while (selectedWords.length < count) {
        const idx = Math.floor(Math.random() * pool.length);
        if (!usedIndices.has(idx)) {
            usedIndices.add(idx);
            selectedWords.push(pool[idx]);
        }
    }

    // Generate Questions
    quizState.questions = selectedWords.map(word => {
        // Distractors
        const distractors = [];
        const distractorIndices = new Set();
        distractorIndices.add(state.words.indexOf(word)); 

        while (distractors.length < 3) {
            const idx = Math.floor(Math.random() * state.words.length);
            // Avoid duplicate text answers
            const txt = state.words[idx].meaning_bangla || state.words[idx].meaning_english;
            const correctTxt = word.meaning_bangla || word.meaning_english;

            if (!distractorIndices.has(idx) && txt !== correctTxt) {
                distractorIndices.add(idx);
                distractors.push(txt);
            }
            // Break loop if not enough unique words
            if (distractorIndices.size >= state.words.length) break; 
        }

        // Fill with placeholders if not enough distractors
        while (distractors.length < 3) {
             distractors.push("Incorrect Answer " + (distractors.length + 1));
        }

        const options = [word.meaning_bangla || word.meaning_english, ...distractors];
        options.sort(() => Math.random() - 0.5);

        return {
            question: word.word,
            correctAnswer: word.meaning_bangla || word.meaning_english,
            options: options,
            type: 'mcq'
        };
    });

    quizState.active = true;
    quizState.currentQuestionIndex = 0;
    quizState.score = 0;
    quizState.seconds = 0;

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

    document.getElementById('question-counter').textContent = 
        `${quizState.currentQuestionIndex + 1}/${quizState.questions.length}`;
    
    const percent = ((quizState.currentQuestionIndex) / quizState.questions.length) * 100;
    document.getElementById('quiz-progress').style.width = `${percent}%`;

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
    if (btn.disabled) return; 

    const buttons = document.querySelectorAll('.option-btn');
    buttons.forEach(b => b.disabled = true);

    const q = quizState.questions[quizState.currentQuestionIndex];
    const isCorrect = selectedOption === q.correctAnswer;

    if (isCorrect) {
        btn.classList.add('correct');
        quizState.score++;
    } else {
        btn.classList.add('wrong');
        buttons.forEach(b => {
             if (b.innerText.trim() === q.correctAnswer.trim()) {
                 b.classList.add('correct');
             }
        });
    }

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

    document.getElementById('quiz-score').textContent = `${accuracy}%`;
}

function resetQuiz() {
    document.getElementById('quiz-results').classList.add('hidden');
    document.getElementById('quiz-welcome').classList.remove('hidden');
}

// ---------------------------------------------------------
// EXPORTS & BACKUP
// ---------------------------------------------------------

function checkBackupReminder() {
    if (window.innerWidth > 768 && !state.backupReminderShown) {
        setTimeout(() => {
            openModal('backup-modal');
            state.backupReminderShown = true;
        }, 5000);
    }
}

window.downloadBackup = function() {
    window.location.href = '/api/backup/download?format=json';
}

// Export for onclicks
window.handlePronounce = handlePronounce;
window.openEditModal = openEditModal;
window.handleEditWord = handleEditWord;
window.handleDeleteWord = handleDeleteWord;
window.handleAddCategory = handleAddCategory;
window.handleDeleteCategory = handleDeleteCategory;
window.startQuiz = startQuiz;
window.handleAnswer = handleAnswer;
window.resetQuiz = resetQuiz;
