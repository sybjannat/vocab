// App State
const state = {
    words: [],
    categories: [],
    backupReminderShown: false
};

// DOM Elements
document.addEventListener('DOMContentLoaded', () => {
    initApp();
});

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
