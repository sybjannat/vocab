// App State
const state = {
    words: [],
    categories: [],
    backupReminderShown: false,
    currentFilter: 'all',
    currentSort: 'newest',
    searchQuery: '',
    quizHistory: [],
    quizStats: null
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
    loadQuizStats();
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
            
            // Load tab-specific data
            if (tabId === 'collection') {
                renderCollection();
            } else if (tabId === 'analytics') {
                renderAnalytics();
            } else if (tabId === 'quiz') {
                loadQuizHistory();
                loadQuizStats();
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
        } else if (id === 'edit-word-modal') {
            // Populate category dropdown for edit modal
            const select = document.getElementById('edit-word-category');
            if (select) {
                select.innerHTML = state.categories.map(c => 
                    `<option value="${c}">${c}</option>`
                ).join('');
            }
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
        // Load status
        const statusRes = await fetch('/api/status');
        const statusData = await statusRes.json();
        updateStats(statusData);

        // Load all words
        const wordsRes = await fetch('/api/download_all');
        const wordsData = await wordsRes.json();
        if (wordsData.words) {
            state.words = wordsData.words;
            renderRecentWords(state.words.slice(0, 6));
            populateCategoryFilter();
            renderCollection();
            renderAnalytics();
        }
        
        // Load quiz history
        await loadQuizHistory();
        
        // Load quiz stats
        await loadQuizStats();
        
    } catch (error) {
        console.error('Failed to load data:', error);
        showToast('Failed to load data. Please refresh the page.', 'error');
    }
}

// ---------------------------------------------------------
// RENDERING & HELPERS
// ---------------------------------------------------------

function populateCategoryFilter() {
    const categories = [...new Set(state.words.map(w => w.category || 'General Vocabulary'))];
    state.categories = categories.sort();
    
    // Update category filter dropdown
    const filterSelect = document.getElementById('category-filter');
    if (filterSelect) {
        const currentVal = filterSelect.value;
        filterSelect.innerHTML = '<option value="all">All Categories</option>' + 
            categories.map(c => `<option value="${c}">${c}</option>`).join('');
        if (categories.includes(currentVal)) filterSelect.value = currentVal;
    }

    // Update add word category dropdown
    const addCatSelect = document.getElementById('add-word-category');
    if (addCatSelect) {
        addCatSelect.innerHTML = categories.map(c => `<option value="${c}">${c}</option>`).join('');
    }

    // Update edit word category dropdown
    const editCatSelect = document.getElementById('edit-word-category');
    if (editCatSelect) {
        editCatSelect.innerHTML = categories.map(c => `<option value="${c}">${c}</option>`).join('');
    }

    // Render manage categories list
    renderManageCategories();
}

function renderRecentWords(words) {
    const grid = document.getElementById('recent-words-grid');
    if (!grid) return;
    
    if (words.length === 0) {
        grid.innerHTML = `
            <div class="empty-state">
                <span class="material-icons-round">book</span>
                <p>No words added yet. Start by adding your first word!</p>
            </div>
        `;
        return;
    }

    grid.innerHTML = words.map(word => `
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
            <div class="card-footer">
                <div class="date-added">
                    <span class="material-icons-round" style="font-size: 14px;">schedule</span>
                    ${new Date(word.date_added).toLocaleDateString()}
                </div>
            </div>
        </div>
    `).join('');
}

function renderCollection() {
    const container = document.getElementById('collection-list');
    if (!container) return;

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
            (w.meaning_bangla && w.meaning_bangla.toLowerCase().includes(state.searchQuery)) ||
            (w.synonyms && w.synonyms.toLowerCase().includes(state.searchQuery))
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
        container.innerHTML = `
            <div class="empty-state">
                <span class="material-icons-round">search_off</span>
                <p>No words found matching your criteria.</p>
                <button class="secondary-btn" onclick="openModal('add-word-modal')" style="margin-top: 20px;">
                    <span class="material-icons-round">add</span>
                    Add New Word
                </button>
            </div>
        `;
        return;
    }

    container.innerHTML = `
        <div class="word-grid">
            ${filtered.map(word => `
                <div class="word-card">
                    <div class="card-header">
                        <h3>${word.word}</h3>
                        <span class="category-tag">${word.category || 'General'}</span>
                    </div>
                    <div class="card-body">
                        <p><strong>🇧🇩</strong> ${word.meaning_bangla || '-'}</p>
                        <p><strong>🇬🇧</strong> ${word.meaning_english || '-'}</p>
                        ${word.synonyms ? `<p class="synonyms"><em>Synonyms: ${word.synonyms}</em></p>` : ''}
                        ${word.example_sentence ? `<div class="example-sentence">"${word.example_sentence}"</div>` : ''}
                    </div>
                    <div class="card-footer">
                        <div class="date-added">
                            <span class="material-icons-round" style="font-size: 14px;">schedule</span>
                            ${new Date(word.date_added).toLocaleDateString()}
                        </div>
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
            `).join('')}
        </div>
    `;
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
    if (!list || !modal || !modal.classList.contains('open')) return;

    list.innerHTML = state.categories.map(c => `
        <div class="category-item">
            <span>${c}</span>
            ${c !== 'General Vocabulary' ? `
                <div style="display: flex; gap: 5px;">
                    <button onclick="handleEditCategory('${c.replace(/'/g, "\\'")}')" class="icon-btn small" title="Edit">
                        <span class="material-icons-round" style="font-size: 18px;">edit</span>
                    </button>
                    <button onclick="handleDeleteCategory('${c.replace(/'/g, "\\'")}')" class="icon-btn small danger" title="Delete">
                        <span class="material-icons-round" style="font-size: 18px;">delete</span>
                    </button>
                </div>
            ` : '<span class="default-badge">Default</span>'}
        </div>
    `).join('');
}

// ---------------------------------------------------------
// WORD MANAGEMENT
// ---------------------------------------------------------

async function handleAddWord(e) {
    e.preventDefault();
    const btn = e.target.querySelector('button[type="submit"]');
    const originalText = btn.textContent;
    btn.disabled = true;
    btn.innerHTML = '<span class="material-icons-round">pending</span> Adding...';
    
    const formData = new FormData(e.target);
    const data = Object.fromEntries(formData.entries());
    
    // Validate required fields
    const requiredFields = ['word', 'meaning_bangla', 'meaning_english', 'synonyms', 'example_sentence'];
    const missingFields = requiredFields.filter(field => !data[field]?.trim());
    
    if (missingFields.length > 0) {
        showToast(`Please fill in all required fields: ${missingFields.join(', ')}`, 'error');
        btn.disabled = false;
        btn.textContent = originalText;
        return;
    }
    
    data.device_id = localStorage.getItem('device_id') || 'cloud_user';

    try {
        const response = await fetch('/api/words/add', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });

        const result = await response.json();

        if (response.ok) {
            showToast('Word added successfully!', 'success');
            e.target.reset();
            closeModal('add-word-modal');
            await loadInitialData();
        } else {
            showToast('Error: ' + result.message, 'error');
        }
    } catch (error) {
        console.error('Error adding word:', error);
        showToast('Failed to connect to server.', 'error');
    } finally {
        btn.disabled = false;
        btn.innerHTML = originalText;
    }
}

async function handleEditWord(e) {
    e.preventDefault();
    const btn = e.target.querySelector('button[type="submit"]');
    const originalText = btn.textContent;
    btn.disabled = true;
    btn.innerHTML = '<span class="material-icons-round">pending</span> Updating...';

    const formData = new FormData(e.target);
    const data = Object.fromEntries(formData.entries());
    
    try {
        const response = await fetch('/api/words/edit', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });

        if (response.ok) {
            showToast('Word updated successfully!', 'success');
            closeModal('edit-word-modal');
            await loadInitialData();
            renderCollection();
        } else {
            const res = await response.json();
            showToast('Failed: ' + res.message, 'error');
        }
    } catch (err) {
        console.error(err);
        showToast('Error updating word', 'error');
    } finally {
        btn.disabled = false;
        btn.innerHTML = originalText;
    }
}

async function handleDeleteWord(id) {
    if (!confirm('Are you sure you want to delete this word? This action cannot be undone.')) return;
    
    try {
        const response = await fetch('/api/words/delete', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ id: id })
        });

        if (response.ok) {
            showToast('Word deleted successfully!', 'success');
            state.words = state.words.filter(w => w.id !== id);
            renderCollection();
            updateStats({ total_words: state.words.length, category_count: state.categories.length });
            await loadInitialData();
        } else {
            const res = await response.json();
            showToast('Error: ' + res.message, 'error');
        }
    } catch (err) {
        console.error(err);
        showToast('Error deleting word', 'error');
    }
}

async function handleAddCategory(e) {
    e.preventDefault();
    const input = e.target.querySelector('[name="name"]');
    const name = input.value.trim();
    
    if (!name) {
        showToast('Please enter a category name', 'error');
        return;
    }
    
    if (state.categories.includes(name)) {
        showToast('Category already exists', 'error');
        return;
    }

    try {
        const response = await fetch('/api/categories/add', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name: name })
        });

        if (response.ok) {
            input.value = '';
            await loadInitialData();
            renderManageCategories();
            showToast(`Category "${name}" added!`, 'success');
        } else {
            const res = await response.json();
            showToast(res.message, 'error');
        }
    } catch(err) { 
        console.error(err);
        showToast('Error adding category', 'error');
    }
}

async function handleEditCategory(oldName) {
    const newName = prompt('Enter new category name:', oldName);
    if (!newName || newName.trim() === oldName) return;
    
    if (state.categories.includes(newName)) {
        showToast('Category already exists', 'error');
        return;
    }

    try {
        const response = await fetch('/api/categories/edit', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ old_name: oldName, new_name: newName })
        });

        if (response.ok) {
            await loadInitialData();
            renderManageCategories();
            showToast('Category updated!', 'success');
        } else {
            const res = await response.json();
            showToast(res.message, 'error');
        }
    } catch(err) { 
        console.error(err);
        showToast('Error updating category', 'error');
    }
}

async function handleDeleteCategory(name) {
    if (!confirm(`Delete category "${name}"? All words in this category will be moved to "General Vocabulary".`)) return;

    try {
        const response = await fetch('/api/categories/delete', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name: name })
        });

        if (response.ok) {
            await loadInitialData();
            renderManageCategories();
            showToast('Category deleted.', 'success');
        } else {
            const res = await response.json();
            showToast(res.message, 'error');
        }
    } catch(err) { 
        console.error(err);
        showToast('Error deleting category', 'error');
    }
}

function openEditModal(id) {
    const word = state.words.find(w => w.id === id);
    if (!word) {
        showToast('Word not found', 'error');
        return;
    }

    const form = document.getElementById('edit-word-form');
    const fields = ['id', 'word', 'meaning_bangla', 'meaning_english', 'synonyms', 'example_sentence'];
    
    fields.forEach(f => {
        const input = form.querySelector(`[name="${f}"]`);
        if (input) input.value = word[f] || '';
    });
    
    const catSelect = form.querySelector('[name="category"]');
    if (catSelect) {
        catSelect.value = word.category || 'General Vocabulary';
        // Ensure the current category is in the options
        if (!Array.from(catSelect.options).some(opt => opt.value === catSelect.value)) {
            const option = document.createElement('option');
            option.value = catSelect.value;
            option.textContent = catSelect.value;
            catSelect.appendChild(option);
        }
    }

    openModal('edit-word-modal');
}

// ---------------------------------------------------------
// QUIZ SYSTEM
// ---------------------------------------------------------

const quizState = {
    active: false,
    questions: [],
    currentQuestionIndex: 0,
    score: 0,
    timer: null,
    seconds: 0,
    correctWords: [],
    incorrectWords: []
};

async function startQuiz(mode, count = 10) {
    if (state.words.length < 5) {
        showToast('Not enough words to start a quiz! Add at least 5 words.', 'error');
        return;
    }

    let pool = [...state.words];
    
    // Filter pool based on mode
    if (mode === 'hard') {
        pool = pool.filter(w => w.word.length > 6);
    } else if (mode === 'new') {
        // Get words added in the last 7 days
        const sevenDaysAgo = new Date();
        sevenDaysAgo.setDate(sevenDaysAgo.getDate() - 7);
        pool = pool.filter(w => new Date(w.date_added) > sevenDaysAgo);
    }
    
    // Ensure we have enough words
    if (pool.length < count) {
        pool = [...state.words];
    }
    
    // Shuffle and select words
    const shuffled = [...pool].sort(() => Math.random() - 0.5);
    const selectedWords = shuffled.slice(0, Math.min(count, shuffled.length));

    // Generate questions
    quizState.questions = selectedWords.map((word, index) => {
        // Get 3 other words for distractors
        const otherWords = state.words.filter(w => w.id !== word.id);
        const shuffledOthers = [...otherWords].sort(() => Math.random() - 0.5).slice(0, 3);
        
        // Create options (correct answer + 3 distractors)
        const options = [
            word.meaning_bangla || word.meaning_english,
            ...shuffledOthers.map(w => w.meaning_bangla || w.meaning_english)
        ];
        
        // Shuffle options
        options.sort(() => Math.random() - 0.5);
        
        return {
            id: index + 1,
            word: word.word,
            correctAnswer: word.meaning_bangla || word.meaning_english,
            options: options,
            category: word.category,
            type: 'multiple_choice'
        };
    });

    // Reset quiz state
    quizState.active = true;
    quizState.currentQuestionIndex = 0;
    quizState.score = 0;
    quizState.seconds = 0;
    quizState.correctWords = [];
    quizState.incorrectWords = [];
    
    // Show quiz interface
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
            <h1 class="highlight-text">"${q.word}"</h1>
            <p style="color: var(--text-muted); margin-top: 10px;">Category: ${q.category || 'General'}</p>
        </div>
        <div class="options-grid">
            ${q.options.map((opt, i) => `
                <button class="option-btn" onclick="handleAnswer(${i}, '${opt.replace(/'/g, "\\'")}', '${q.correctAnswer.replace(/'/g, "\\'")}')">
                    ${opt}
                </button>
            `).join('')}
        </div>
    `;
}

function handleAnswer(optionIndex, selectedOption, correctAnswer) {
    const buttons = document.querySelectorAll('.option-btn');
    buttons.forEach(b => b.disabled = true);

    const q = quizState.questions[quizState.currentQuestionIndex];
    const isCorrect = selectedOption === correctAnswer;
    
    // Highlight correct/incorrect answers
    buttons.forEach((btn, idx) => {
        if (btn.textContent === correctAnswer) {
            btn.classList.add('correct');
        } else if (idx === optionIndex && !isCorrect) {
            btn.classList.add('wrong');
        }
    });
    
    // Update score and track words
    if (isCorrect) {
        quizState.score++;
        quizState.correctWords.push(q.word);
    } else {
        quizState.incorrectWords.push(q.word);
    }
    
    // Move to next question after delay
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
    quizState.seconds = 0;
    document.getElementById('quiz-timer').textContent = "00:00";
    
    quizState.timer = setInterval(() => {
        quizState.seconds++;
        const m = Math.floor(quizState.seconds / 60).toString().padStart(2, '0');
        const s = (quizState.seconds % 60).toString().padStart(2, '0');
        document.getElementById('quiz-timer').textContent = `${m}:${s}`;
    }, 1000);
}

async function endQuiz() {
    clearInterval(quizState.timer);
    quizState.active = false;
    
    const accuracy = Math.round((quizState.score / quizState.questions.length) * 100);
    const timeTaken = quizState.seconds;
    
    // Save quiz result
    try {
        const deviceId = localStorage.getItem('device_id') || 'cloud_user';
        const response = await fetch('/api/save_quiz_result', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                device_id: deviceId,
                quiz_type: 'multiple_choice',
                score: quizState.score,
                total_questions: quizState.questions.length,
                accuracy: accuracy,
                time_taken_seconds: timeTaken,
                correct_words: quizState.correctWords,
                incorrect_words: quizState.incorrectWords,
                details: {
                    categories: [...new Set(quizState.questions.map(q => q.category))],
                    difficulty: 'mixed'
                }
            })
        });
        
        if (response.ok) {
            await loadQuizHistory();
            await loadQuizStats();
        }
    } catch (err) {
        console.error('Error saving quiz result:', err);
    }
    
    // Show results
    document.getElementById('quiz-active').classList.add('hidden');
    document.getElementById('quiz-results').classList.remove('hidden');
    
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
                    <span>Correct Answers</span>
                </div>
                <div class="stat">
                    <strong>${Math.floor(timeTaken / 60)}:${(timeTaken % 60).toString().padStart(2, '0')}</strong>
                    <span>Time Taken</span>
                </div>
                <div class="stat">
                    <strong>${quizState.correctWords.length}</strong>
                    <span>Words Mastered</span>
                </div>
            </div>
            
            <div style="margin: 30px 0; text-align: left;">
                <h4 style="margin-bottom: 10px;">Words to Review:</h4>
                ${quizState.incorrectWords.length > 0 ? 
                    `<ul style="text-align: left; padding-left: 20px; color: var(--danger);">
                        ${quizState.incorrectWords.map(word => `<li>${word}</li>`).join('')}
                    </ul>` :
                    '<p style="color: var(--success);">Perfect! No words to review.</p>'
                }
            </div>
            
            <div style="display: flex; gap: 10px; justify-content: center; flex-wrap: wrap;">
                <button class="primary-btn" onclick="resetQuiz()">
                    <span class="material-icons-round">replay</span>
                    Play Again
                </button>
                <button class="secondary-btn" onclick="exportQuizResults()">
                    <span class="material-icons-round">download</span>
                    Export Results
                </button>
            </div>
        </div>
    `;
}

function resetQuiz() {
    document.getElementById('quiz-results').classList.add('hidden');
    document.getElementById('quiz-welcome').classList.remove('hidden');
}

async function loadQuizHistory() {
    try {
        const deviceId = localStorage.getItem('device_id') || 'cloud_user';
        const response = await fetch(`/api/quiz_results?device_id=${deviceId}&limit=10`);
        if (response.ok) {
            const data = await response.json();
            state.quizHistory = data.results || [];
            updateQuizHistoryUI();
        }
    } catch (err) {
        console.error('Error loading quiz history:', err);
    }
}

async function loadQuizStats() {
    try {
        const deviceId = localStorage.getItem('device_id') || 'cloud_user';
        const response = await fetch(`/api/quiz_statistics?device_id=${deviceId}`);
        if (response.ok) {
            const data = await response.json();
            state.quizStats = data.statistics || null;
            updateQuizStatsUI();
        }
    } catch (err) {
        console.error('Error loading quiz stats:', err);
    }
}

function updateQuizHistoryUI() {
    const container = document.querySelector('#quiz-tab .quiz-history');
    if (!container) return;
    
    if (state.quizHistory.length === 0) {
        container.innerHTML = `
            <div class="empty-state">
                <span class="material-icons-round">quiz</span>
                <p>No quiz history yet. Take your first quiz!</p>
            </div>
        `;
        return;
    }
    
    container.innerHTML = `
        <div style="margin-top: 30px;">
            <h3>Recent Quizzes</h3>
            <div class="quiz-stats-grid">
                ${state.quizHistory.slice(0, 5).map(quiz => `
                    <div class="quiz-stat-card">
                        <div class="quiz-stat-value">${quiz.accuracy}%</div>
                        <div class="quiz-stat-label">
                            ${quiz.score}/${quiz.total_questions}<br>
                            ${new Date(quiz.timestamp).toLocaleDateString()}
                        </div>
                    </div>
                `).join('')}
            </div>
        </div>
    `;
}

function updateQuizStatsUI() {
    if (!state.quizStats) return;
    
    // Update quiz stats in the Learning tab
    const quizScoreEl = document.getElementById('quiz-score');
    if (quizScoreEl) {
        quizScoreEl.textContent = `${state.quizStats.overall_accuracy || 0}%`;
    }
    
    // Update quiz stats in Quiz tab
    const statsContainer = document.querySelector('#quiz-tab .quiz-overall-stats');
    if (statsContainer) {
        statsContainer.innerHTML = `
            <div class="quiz-stats-grid">
                <div class="quiz-stat-card">
                    <div class="quiz-stat-value">${state.quizStats.total_quizzes || 0}</div>
                    <div class="quiz-stat-label">Total Quizzes</div>
                </div>
                <div class="quiz-stat-card">
                    <div class="quiz-stat-value">${state.quizStats.overall_accuracy || 0}%</div>
                    <div class="quiz-stat-label">Overall Accuracy</div>
                </div>
                <div class="quiz-stat-card">
                    <div class="quiz-stat-value">${state.quizStats.best_accuracy || 0}%</div>
                    <div class="quiz-stat-label">Best Score</div>
                </div>
                <div class="quiz-stat-card">
                    <div class="quiz-stat-value">${state.quizStats.quizzes_today || 0}</div>
                    <div class="quiz-stat-label">Today's Quizzes</div>
                </div>
            </div>
        `;
    }
}

function exportQuizResults() {
    const data = {
        score: quizState.score,
        total: quizState.questions.length,
        accuracy: Math.round((quizState.score / quizState.questions.length) * 100),
        time: quizState.seconds,
        date: new Date().toISOString(),
        correctWords: quizState.correctWords,
        incorrectWords: quizState.incorrectWords
    };
    
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `quiz-results-${new Date().toISOString().split('T')[0]}.json`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
    
    showToast('Quiz results exported!', 'success');
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
        if(accEl) accEl.textContent = `${data.avg_accuracy || 0}%`;
        
        // Render Category Bars
        const container = document.getElementById('analytics-category-bars');
        if (container && data.category_breakdown) {
            const max = Math.max(...data.category_breakdown.map(d => d.count)) || 1;
            
            container.innerHTML = data.category_breakdown.map(cat => `
                <div class="chart-row">
                    <div class="chart-label">
                        ${cat.name}
                        <span class="chart-count">${cat.count}</span>
                    </div>
                    <div class="chart-bar-container">
                        <div class="chart-bar" style="width: ${(cat.count / max) * 100}%"></div>
                    </div>
                </div>
            `).join('');
        }
        
        // Add more analytics data if available
        renderAdvancedAnalytics(data);
        
    } catch(err) { 
        console.error("Analytics error", err);
        showToast('Failed to load analytics', 'error');
    }
}

function renderAdvancedAnalytics(data) {
    const container = document.getElementById('advanced-analytics');
    if (!container) return;
    
    // Calculate additional stats
    const totalWords = data.total_words || 0;
    const categories = data.category_breakdown || [];
    const avgWordLength = calculateAverageWordLength();
    const recentActivity = getRecentActivity();
    
    container.innerHTML = `
        <div class="analytics-grid">
            <div class="analytics-card">
                <h3>Word Distribution</h3>
                <p>Total words: <strong>${totalWords}</strong></p>
                <p>Categories: <strong>${categories.length}</strong></p>
                <p>Average word length: <strong>${avgWordLength}</strong> letters</p>
            </div>
            <div class="analytics-card">
                <h3>Recent Activity</h3>
                ${recentActivity.map(activity => `
                    <p>${activity}</p>
                `).join('')}
            </div>
            <div class="analytics-card">
                <h3>Top Categories</h3>
                ${categories.slice(0, 3).map(cat => `
                    <p>${cat.name}: <strong>${cat.count}</strong> words</p>
                `).join('')}
            </div>
        </div>
    `;
}

function calculateAverageWordLength() {
    if (state.words.length === 0) return 0;
    const totalLength = state.words.reduce((sum, word) => sum + word.word.length, 0);
    return (totalLength / state.words.length).toFixed(1);
}

function getRecentActivity() {
    const activities = [];
    const today = new Date();
    const yesterday = new Date(today);
    yesterday.setDate(yesterday.getDate() - 1);
    
    // Words added today
    const wordsToday = state.words.filter(w => {
        const wordDate = new Date(w.date_added);
        return wordDate.toDateString() === today.toDateString();
    }).length;
    
    if (wordsToday > 0) {
        activities.push(`Added ${wordsToday} word(s) today`);
    }
    
    // Recent quizzes
    if (state.quizHistory.length > 0) {
        const latestQuiz = state.quizHistory[0];
        activities.push(`Latest quiz: ${latestQuiz.accuracy}% accuracy`);
    }
    
    if (activities.length === 0) {
        activities.push('No recent activity');
    }
    
    return activities.slice(0, 3);
}

// ---------------------------------------------------------
// UTILITIES
// ---------------------------------------------------------

function handlePronounce(text) {
    if ('speechSynthesis' in window) {
        const utterance = new SpeechSynthesisUtterance(text);
        utterance.lang = 'en-US';
        utterance.rate = 0.8;
        utterance.pitch = 1;
        utterance.volume = 1;
        window.speechSynthesis.speak(utterance);
    } else {
        showToast("Browser doesn't support Text-to-Speech", 'warning');
    }
}

function showToast(message, type = 'success') {
    // Remove existing toasts
    const existingToasts = document.querySelectorAll('.toast');
    existingToasts.forEach(toast => toast.remove());
    
    // Create new toast
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.innerHTML = `
        <span class="material-icons-round">
            ${type === 'success' ? 'check_circle' : type === 'error' ? 'error' : 'warning'}
        </span>
        <span>${message}</span>
    `;
    
    document.body.appendChild(toast);
    
    // Remove toast after 3 seconds
    setTimeout(() => {
        if (toast.parentNode) {
            toast.style.opacity = '0';
            toast.style.transform = 'translateX(100%)';
            setTimeout(() => {
                if (toast.parentNode) {
                    toast.parentNode.removeChild(toast);
                }
            }, 300);
        }
    }, 3000);
}

function checkBackupReminder() {
    if (window.innerWidth > 768 && !state.backupReminderShown) {
        setTimeout(() => {
            openModal('backup-modal');
            state.backupReminderShown = true;
        }, 5000);
    }
}

window.downloadBackup = function() {
    window.location.href = '/api/export_excel';
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
        btn.innerHTML = '<span class="material-icons-round">pending</span> Importing...';
        status.textContent = 'Uploading and processing file...';

        const response = await fetch('/api/import_excel', {
            method: 'POST',
            body: formData
        });

        const result = await response.json();

        if (response.ok) {
            showToast('Import successful!', 'success');
            setTimeout(() => {
                closeModal('import-modal');
                e.target.reset();
                loadInitialData();
                status.textContent = '';
                btn.disabled = false;
                btn.textContent = 'Import';
            }, 1000);
        } else {
            throw new Error(result.message || 'Import failed');
        }
    } catch (error) {
        console.error('Import error:', error);
        showToast('Error: ' + error.message, 'error');
        btn.disabled = false;
        btn.textContent = 'Import';
    }
}

// Export functions to window
window.handlePronounce = handlePronounce;
window.openEditModal = openEditModal;
window.handleEditWord = handleEditWord;
window.handleDeleteWord = handleDeleteWord;
window.handleAddCategory = handleAddCategory;
window.handleEditCategory = handleEditCategory;
window.handleDeleteCategory = handleDeleteCategory;
window.startQuiz = startQuiz;
window.handleAnswer = handleAnswer;
window.resetQuiz = resetQuiz;
window.downloadBackup = downloadBackup;