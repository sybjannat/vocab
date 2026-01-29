from flask import Flask, request, jsonify, send_file, render_template
from flask_cors import CORS
import pandas as pd
import sqlite3
from datetime import datetime, timedelta
import os
import json
import uuid
import numpy as np
import time
import threading
from contextlib import contextmanager

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*", "allow_headers": "*", "methods": "*"}})

DB_FILE = 'vocabulary.db'
EXCEL_FILE = 'vocabulary_all.xlsx'
UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'xlsx', 'xls'}

# Database lock for thread safety
db_lock = threading.RLock()

# Create uploads folder if it doesn't exist
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

@contextmanager
def get_db_connection():
    """Context manager for database connections with timeout and retry"""
    conn = None
    retries = 3
    for attempt in range(retries):
        try:
            conn = sqlite3.connect(
                DB_FILE, 
                timeout=30,
                check_same_thread=False
            )
            conn.execute('PRAGMA journal_mode=WAL')
            conn.execute('PRAGMA busy_timeout=5000')
            conn.row_factory = sqlite3.Row
            yield conn
            break
        except sqlite3.OperationalError as e:
            if "locked" in str(e) and attempt < retries - 1:
                time.sleep(0.1 * (attempt + 1))
                continue
            else:
                raise e
        finally:
            if conn:
                conn.close()

@contextmanager
def get_db_cursor():
    """Context manager for database operations with thread safety"""
    with db_lock:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            try:
                yield cursor, conn
                conn.commit()
            except Exception as e:
                conn.rollback()
                raise e

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def init_db():
    """Initialize database with proper table creation"""
    with get_db_cursor() as (c, conn):
        # Words table
        c.execute('''
            CREATE TABLE IF NOT EXISTS words (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                word TEXT NOT NULL,
                meaning_bangla TEXT NOT NULL,
                meaning_english TEXT NOT NULL,
                synonyms TEXT NOT NULL,
                example_sentence TEXT NOT NULL,
                category TEXT DEFAULT 'General Vocabulary',
                date_added TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                device_id TEXT,
                last_synced TIMESTAMP,
                is_deleted INTEGER DEFAULT 0,
                is_edited INTEGER DEFAULT 0,
                original_id INTEGER,
                sync_status TEXT DEFAULT 'pending',
                UNIQUE(word, device_id) ON CONFLICT REPLACE
            )
        ''')
        
        # Add unique constraint if not exists
        try:
            c.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_word_device ON words (word, device_id)")
        except:
            pass
        
        # Categories table
        c.execute('''
            CREATE TABLE IF NOT EXISTS categories (
                name TEXT PRIMARY KEY,
                color TEXT DEFAULT '#6366f1',
                is_default INTEGER DEFAULT 0
            )
        ''')
        
        # Insert default categories
        default_categories = [
            ('General Vocabulary', '#6366f1', 1),
            ('Phrase and Idioms', '#8b5cf6', 1),
            ('Transitional Words', '#10b981', 1),
            ('Academic Vocabulary', '#f59e0b', 1),
            ('Business Vocabulary', '#ef4444', 1),
            ('Technical Terms', '#3b82f6', 1)
        ]
        
        for name, color, is_default in default_categories:
            c.execute('''
                INSERT OR IGNORE INTO categories (name, color, is_default)
                VALUES (?, ?, ?)
            ''', (name, color, is_default))
        
        # Quiz tables
        c.execute('''
            CREATE TABLE IF NOT EXISTS quiz_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                device_id TEXT,
                quiz_type TEXT,
                score INTEGER,
                total_questions INTEGER,
                accuracy REAL,
                time_taken_seconds INTEGER,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                correct_words TEXT,
                incorrect_words TEXT,
                details TEXT
            )
        ''')
        
        c.execute('''
            CREATE TABLE IF NOT EXISTS quiz_statistics (
                device_id TEXT PRIMARY KEY,
                total_quizzes INTEGER DEFAULT 0,
                total_correct INTEGER DEFAULT 0,
                total_questions INTEGER DEFAULT 0,
                total_time_seconds INTEGER DEFAULT 0,
                best_score INTEGER DEFAULT 0,
                best_accuracy REAL DEFAULT 0,
                last_quiz_date TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Analytics cache table
        c.execute('''
            CREATE TABLE IF NOT EXISTS analytics_cache (
                key TEXT PRIMARY KEY,
                data TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # User progress table
        c.execute('''
            CREATE TABLE IF NOT EXISTS user_progress (
                device_id TEXT,
                word_id INTEGER,
                times_tested INTEGER DEFAULT 0,
                times_correct INTEGER DEFAULT 0,
                last_tested TIMESTAMP,
                mastered INTEGER DEFAULT 0,
                PRIMARY KEY (device_id, word_id)
            )
        ''')
        
        c.execute('PRAGMA optimize')
    
    print("✅ Database initialized with all tables")

# Routes
@app.route('/')
def home():
    return render_template('index.html')

@app.route('/api/status', methods=['GET', 'OPTIONS'])
def get_status():
    if request.method == 'OPTIONS':
        return '', 200
    
    try:
        with get_db_cursor() as (c, conn):
            c.execute("SELECT COUNT(*) FROM words WHERE is_deleted = 0")
            total_words = c.fetchone()[0]
            
            c.execute("SELECT COUNT(DISTINCT category) FROM words WHERE is_deleted = 0")
            category_count = c.fetchone()[0]
            
            c.execute("SELECT COUNT(DISTINCT device_id) FROM devices")
            device_count = c.fetchone()[0] if c.fetchone() else 0
            
            # Get today's activity
            today = datetime.now().strftime('%Y-%m-%d')
            c.execute("SELECT COUNT(*) FROM words WHERE DATE(date_added) = ? AND is_deleted = 0", (today,))
            words_today = c.fetchone()[0]
            
            return jsonify({
                "status": "online",
                "total_words": total_words,
                "category_count": category_count,
                "device_count": device_count,
                "words_today": words_today,
                "server_time": datetime.now().isoformat()
            })
            
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

@app.route('/api/download_all', methods=['GET', 'OPTIONS'])
def download_all_words():
    if request.method == 'OPTIONS':
        return '', 200
    
    try:
        with get_db_cursor() as (c, conn):
            c.execute('''
                SELECT id, word, meaning_bangla, meaning_english, synonyms, 
                       example_sentence, category, date_added
                FROM words 
                WHERE is_deleted = 0 
                ORDER BY date_added DESC
            ''')
            words = []
            columns = [column[0] for column in c.description]
            for row in c.fetchall():
                words.append(dict(zip(columns, row)))
            
            return jsonify({
                "status": "success",
                "words": words,
                "count": len(words)
            })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/words/add', methods=['POST', 'OPTIONS'])
def add_word():
    if request.method == 'OPTIONS':
        return '', 200
    
    try:
        data = request.json
        
        # Validate required fields
        required_fields = ['word', 'meaning_bangla', 'meaning_english', 'synonyms', 'example_sentence']
        for field in required_fields:
            if not data.get(field, '').strip():
                return jsonify({
                    "status": "error", 
                    "message": f"Field '{field}' is required"
                }), 400
        
        word = data['word'].strip().title()
        meaning_bangla = data['meaning_bangla'].strip()
        meaning_english = data['meaning_english'].strip()
        synonyms = data['synonyms'].strip()
        example_sentence = data['example_sentence'].strip()
        category = data.get('category', 'General Vocabulary').strip()
        device_id = data.get('device_id', 'unknown')
        current_time = datetime.now().isoformat()
        
        with get_db_cursor() as (c, conn):
            # Check if word exists for this device
            c.execute('''
                SELECT id FROM words 
                WHERE word = ? AND device_id = ? AND is_deleted = 0
            ''', (word, device_id))
            
            if c.fetchone():
                return jsonify({
                    "status": "error", 
                    "message": f"Word '{word}' already exists for this device"
                }), 400
            
            # Insert new word
            c.execute('''
                INSERT INTO words 
                (word, meaning_bangla, meaning_english, synonyms, example_sentence, 
                 category, date_added, device_id, last_synced, sync_status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending')
            ''', (
                word,
                meaning_bangla,
                meaning_english,
                synonyms,
                example_sentence,
                category,
                current_time,
                device_id,
                current_time
            ))
            
            word_id = c.lastrowid
            
            # Update analytics cache
            c.execute('DELETE FROM analytics_cache WHERE key = "category_stats"')
            
            return jsonify({
                "status": "success",
                "message": "Word added successfully",
                "word_id": word_id,
                "word": {
                    "id": word_id,
                    "word": word,
                    "meaning_bangla": meaning_bangla,
                    "meaning_english": meaning_english,
                    "category": category,
                    "date_added": current_time
                }
            })
            
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/words/edit', methods=['POST', 'OPTIONS'])
def edit_word():
    if request.method == 'OPTIONS':
        return '', 200
    
    try:
        data = request.json
        word_id = data.get('id')
        
        if not word_id:
            return jsonify({"status": "error", "message": "Word ID is required"}), 400
        
        # Validate required fields
        required_fields = ['word', 'meaning_bangla', 'meaning_english', 'synonyms', 'example_sentence']
        for field in required_fields:
            if not data.get(field, '').strip():
                return jsonify({
                    "status": "error", 
                    "message": f"Field '{field}' is required"
                }), 400

        with get_db_cursor() as (c, conn):
            # Check if word exists
            c.execute('SELECT device_id FROM words WHERE id = ?', (word_id,))
            existing = c.fetchone()
            
            if not existing:
                return jsonify({"status": "error", "message": "Word not found"}), 404
            
            # Update word
            c.execute('''
                UPDATE words
                SET word = ?, meaning_bangla = ?, meaning_english = ?, synonyms = ?, 
                    example_sentence = ?, category = ?, is_edited = 1, last_synced = ?
                WHERE id = ?
            ''', (
                data['word'].strip().title(),
                data['meaning_bangla'].strip(),
                data['meaning_english'].strip(),
                data['synonyms'].strip(),
                data['example_sentence'].strip(),
                data.get('category', 'General Vocabulary').strip(),
                datetime.now().isoformat(),
                word_id
            ))
            
            # Update analytics cache
            c.execute('DELETE FROM analytics_cache WHERE key = "category_stats"')
            
            return jsonify({
                "status": "success", 
                "message": "Word updated successfully"
            })
            
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/words/delete', methods=['POST', 'OPTIONS'])
def delete_word():
    if request.method == 'OPTIONS':
        return '', 200
    
    try:
        data = request.json
        word_id = data.get('id')
        
        if not word_id:
            return jsonify({"status": "error", "message": "Word ID is required"}), 400

        with get_db_cursor() as (c, conn):
            # Soft delete
            c.execute('''
                UPDATE words 
                SET is_deleted = 1, last_synced = ? 
                WHERE id = ?
            ''', (datetime.now().isoformat(), word_id))
            
            # Update analytics cache
            c.execute('DELETE FROM analytics_cache WHERE key = "category_stats"')
            
            return jsonify({
                "status": "success", 
                "message": "Word deleted successfully"
            })
            
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/analytics', methods=['GET', 'OPTIONS'])
def get_analytics():
    if request.method == 'OPTIONS':
        return '', 200
        
    try:
        with get_db_cursor() as (c, conn):
            # Check cache first
            c.execute('SELECT data FROM analytics_cache WHERE key = ?', ('category_stats',))
            cache = c.fetchone()
            
            if cache:
                try:
                    data = json.loads(cache[0])
                    # Check if cache is fresh (less than 5 minutes old)
                    c.execute('SELECT updated_at FROM analytics_cache WHERE key = ?', ('category_stats',))
                    updated_at = datetime.fromisoformat(c.fetchone()[0])
                    if (datetime.now() - updated_at).total_seconds() < 300:  # 5 minutes
                        return jsonify(data)
                except:
                    pass  # Cache corrupted, recalculate
            
            # Calculate fresh analytics
            # Total Words
            c.execute("SELECT COUNT(*) FROM words WHERE is_deleted = 0")
            total_words = c.fetchone()[0]
            
            # Words per Category
            c.execute('''
                SELECT category, COUNT(*) as count 
                FROM words 
                WHERE is_deleted = 0 
                GROUP BY category
                ORDER BY count DESC
            ''')
            category_stats = [{"name": row[0], "count": row[1]} for row in c.fetchall()]
            
            # Recent activity (last 7 days)
            seven_days_ago = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
            c.execute('''
                SELECT DATE(date_added) as date, COUNT(*) as count
                FROM words 
                WHERE is_deleted = 0 AND date_added >= ?
                GROUP BY DATE(date_added)
                ORDER BY date DESC
            ''', (seven_days_ago,))
            
            recent_activity = []
            for row in c.fetchall():
                recent_activity.append({
                    "date": row[0],
                    "count": row[1]
                })
            
            # Quiz statistics
            try:
                c.execute('SELECT AVG(accuracy), COUNT(*) FROM quiz_results')
                quiz_row = c.fetchone()
                avg_accuracy = float(quiz_row[0] or 0)
                total_quizzes = quiz_row[1] or 0
            except:
                avg_accuracy = 0
                total_quizzes = 0
            
            # Compile data
            analytics_data = {
                "total_words": total_words,
                "category_breakdown": category_stats,
                "avg_accuracy": round(avg_accuracy, 1),
                "total_quizzes": total_quizzes,
                "recent_activity": recent_activity,
                "updated_at": datetime.now().isoformat()
            }
            
            # Cache the results
            c.execute('''
                INSERT OR REPLACE INTO analytics_cache (key, data, updated_at)
                VALUES (?, ?, ?)
            ''', ('category_stats', json.dumps(analytics_data), datetime.now().isoformat()))
            
            return jsonify(analytics_data)
            
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/categories', methods=['GET', 'OPTIONS'])
def get_categories():
    if request.method == 'OPTIONS':
        return '', 200
    
    try:
        with get_db_cursor() as (c, conn):
            c.execute('''
                SELECT name, color, is_default 
                FROM categories 
                ORDER BY name
            ''')
            categories = [
                {
                    "name": row[0], 
                    "color": row[1], 
                    "is_default": bool(row[2])
                } 
                for row in c.fetchall()
            ]
            return jsonify(categories)
    except Exception as e:
        return jsonify({"error": str(e)})

@app.route('/api/categories/add', methods=['POST', 'OPTIONS'])
def add_category():
    if request.method == 'OPTIONS':
        return '', 200
    
    try:
        data = request.json
        name = data.get('name', '').strip()
        
        if not name:
            return jsonify({
                "status": "error", 
                "message": "Category name is required"
            }), 400
        
        with get_db_cursor() as (c, conn):
            # Check if category exists
            c.execute('SELECT name FROM categories WHERE name = ?', (name,))
            if c.fetchone():
                return jsonify({
                    "status": "error", 
                    "message": f"Category '{name}' already exists"
                }), 400
            
            # Add category
            c.execute('''
                INSERT INTO categories (name, color, is_default)
                VALUES (?, ?, 0)
            ''', (name, data.get('color', '#6366f1')))
            
            return jsonify({
                "status": "success", 
                "message": f"Category '{name}' added successfully"
            })
        
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/categories/edit', methods=['POST', 'OPTIONS'])
def edit_category():
    if request.method == 'OPTIONS':
        return '', 200
        
    try:
        data = request.json
        old_name = data.get('old_name')
        new_name = data.get('new_name')
        
        if not old_name or not new_name:
            return jsonify({
                "status": "error", 
                "message": "Both old and new names are required"
            }), 400
        
        if old_name == new_name:
            return jsonify({
                "status": "error", 
                "message": "New name must be different from old name"
            }), 400

        with get_db_cursor() as (c, conn):
            # Check if old category exists
            c.execute('SELECT is_default FROM categories WHERE name = ?', (old_name,))
            old_cat = c.fetchone()
            
            if not old_cat:
                return jsonify({
                    "status": "error", 
                    "message": f"Category '{old_name}' not found"
                }), 404
            
            # Check if new category already exists
            c.execute('SELECT name FROM categories WHERE name = ?', (new_name,))
            if c.fetchone():
                return jsonify({
                    "status": "error", 
                    "message": f"Category '{new_name}' already exists"
                }), 400
            
            # Check if trying to edit default category
            if old_cat[0] == 1:
                return jsonify({
                    "status": "error", 
                    "message": "Cannot edit default categories"
                }), 400
            
            # Update category name
            c.execute('UPDATE categories SET name = ? WHERE name = ?', (new_name, old_name))
            
            # Update all words with old category name
            c.execute('''
                UPDATE words 
                SET category = ?, sync_status = 'pending'
                WHERE category = ? AND is_deleted = 0
            ''', (new_name, old_name))
            
            return jsonify({
                "status": "success", 
                "message": f"Category '{old_name}' updated to '{new_name}'"
            })
            
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/categories/delete', methods=['POST', 'OPTIONS'])
def delete_category():
    if request.method == 'OPTIONS':
        return '', 200
    
    try:
        data = request.json
        name = data.get('name', '').strip()
        
        if not name:
            return jsonify({
                "status": "error", 
                "message": "Category name is required"
            }), 400
        
        with get_db_cursor() as (c, conn):
            # Check if category exists
            c.execute('SELECT is_default FROM categories WHERE name = ?', (name,))
            result = c.fetchone()
            
            if not result:
                return jsonify({
                    "status": "error", 
                    "message": f"Category '{name}' not found"
                }), 404
            
            # Check if it's a default category
            if result[0] == 1:
                return jsonify({
                    "status": "error", 
                    "message": "Cannot delete default categories"
                }), 400
            
            # Move words to General Vocabulary
            c.execute('''
                UPDATE words 
                SET category = 'General Vocabulary', sync_status = 'pending'
                WHERE category = ? AND is_deleted = 0
            ''', (name,))
            
            moved_count = c.rowcount
            
            # Delete category
            c.execute('DELETE FROM categories WHERE name = ?', (name,))
            
            # Update analytics cache
            c.execute('DELETE FROM analytics_cache WHERE key = "category_stats"')
            
            return jsonify({
                "status": "success", 
                "message": f"Category deleted. {moved_count} words moved to General Vocabulary."
            })
        
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/save_quiz_result', methods=['POST', 'OPTIONS'])
def save_quiz_result():
    """Save quiz result to database"""
    if request.method == 'OPTIONS':
        return '', 200
    
    try:
        data = request.json
        if not data:
            return jsonify({"status": "error", "message": "No data"}), 400
        
        device_id = data.get('device_id', 'unknown')
        quiz_type = data.get('quiz_type', 'multiple_choice')
        score = int(data.get('score', 0))
        total_questions = int(data.get('total_questions', 10))
        accuracy = float(data.get('accuracy', 0.0))
        time_taken_seconds = int(data.get('time_taken_seconds', 0))
        correct_words = json.dumps(data.get('correct_words', []))
        incorrect_words = json.dumps(data.get('incorrect_words', []))
        details = json.dumps(data.get('details', {}))
        timestamp = datetime.now().isoformat()
        
        # Calculate accuracy if not provided
        if accuracy == 0 and total_questions > 0:
            accuracy = (score / total_questions) * 100
        
        with get_db_cursor() as (c, conn):
            # Save quiz result
            c.execute('''
                INSERT INTO quiz_results 
                (device_id, quiz_type, score, total_questions, accuracy, 
                 time_taken_seconds, correct_words, incorrect_words, details, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                device_id,
                quiz_type,
                score,
                total_questions,
                accuracy,
                time_taken_seconds,
                correct_words,
                incorrect_words,
                details,
                timestamp
            ))
            
            result_id = c.lastrowid
            
            # Update or create quiz statistics
            c.execute('''
                INSERT INTO quiz_statistics 
                (device_id, total_quizzes, total_correct, total_questions, 
                 total_time_seconds, best_score, best_accuracy, last_quiz_date)
                VALUES (?, 1, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(device_id) DO UPDATE SET
                    total_quizzes = total_quizzes + 1,
                    total_correct = total_correct + ?,
                    total_questions = total_questions + ?,
                    total_time_seconds = total_time_seconds + ?,
                    best_score = CASE WHEN ? > best_score THEN ? ELSE best_score END,
                    best_accuracy = CASE WHEN ? > best_accuracy THEN ? ELSE best_accuracy END,
                    last_quiz_date = ?
            ''', (
                device_id, score, total_questions, time_taken_seconds, score, accuracy, timestamp,
                score, total_questions, time_taken_seconds,
                score, score, accuracy, accuracy, timestamp
            ))
            
            # Log the action
            c.execute('''
                INSERT INTO sync_log (device_id, action, details)
                VALUES (?, ?, ?)
            ''', (device_id, 'quiz_completed', 
                  f'Quiz completed: {score}/{total_questions} ({accuracy:.1f}%) in {time_taken_seconds}s'))
        
        return jsonify({
            "status": "success",
            "message": "Quiz result saved",
            "result_id": result_id,
            "accuracy": accuracy
        })
        
    except Exception as e:
        print(f"❌ Error saving quiz result: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/quiz_results', methods=['GET', 'OPTIONS'])
def get_quiz_results():
    """Get quiz results for a device"""
    if request.method == 'OPTIONS':
        return '', 200
    
    try:
        device_id = request.args.get('device_id', '')
        limit = int(request.args.get('limit', 10))
        
        if not device_id:
            return jsonify({"status": "error", "message": "device_id required"}), 400
        
        with get_db_cursor() as (c, conn):
            # Get results for specific device
            c.execute('''
                SELECT id, quiz_type, score, total_questions, accuracy, 
                       time_taken_seconds, timestamp, correct_words, incorrect_words
                FROM quiz_results 
                WHERE device_id = ?
                ORDER BY timestamp DESC
                LIMIT ?
            ''', (device_id, limit))
            
            results = []
            for row in c.fetchall():
                try:
                    correct_words = json.loads(row[7]) if row[7] else []
                    incorrect_words = json.loads(row[8]) if row[8] else []
                except:
                    correct_words = []
                    incorrect_words = []
                
                results.append({
                    "id": row[0],
                    "quiz_type": row[1],
                    "score": row[2],
                    "total_questions": row[3],
                    "accuracy": float(row[4]),
                    "time_taken_seconds": row[5],
                    "timestamp": row[6],
                    "correct_words": correct_words,
                    "incorrect_words": incorrect_words
                })
            
            return jsonify({
                "status": "success",
                "results": results,
                "total_count": len(results)
            })
        
    except Exception as e:
        print(f"❌ Error getting quiz results: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/quiz_statistics', methods=['GET', 'OPTIONS'])
def get_quiz_statistics():
    """Get quiz statistics for a device"""
    if request.method == 'OPTIONS':
        return '', 200
    
    try:
        device_id = request.args.get('device_id', '')
        
        if not device_id:
            return jsonify({"status": "error", "message": "device_id required"}), 400
        
        with get_db_cursor() as (c, conn):
            # Get statistics for specific device
            c.execute('''
                SELECT total_quizzes, total_correct, total_questions, 
                       total_time_seconds, best_score, best_accuracy, last_quiz_date
                FROM quiz_statistics 
                WHERE device_id = ?
            ''', (device_id,))
            
            stats_row = c.fetchone()
            
            if not stats_row:
                # Return default statistics
                return jsonify({
                    "status": "success",
                    "statistics": {
                        "device_id": device_id,
                        "total_quizzes": 0,
                        "total_correct": 0,
                        "total_questions": 0,
                        "total_time_seconds": 0,
                        "best_score": 0,
                        "best_accuracy": 0,
                        "last_quiz_date": None,
                        "overall_accuracy": 0,
                        "average_time_per_question": 0,
                        "quizzes_today": 0
                    }
                })
            
            # Calculate statistics
            total_quizzes = stats_row[0] or 0
            total_correct = stats_row[1] or 0
            total_questions = stats_row[2] or 0
            total_time_seconds = stats_row[3] or 0
            best_score = stats_row[4] or 0
            best_accuracy = float(stats_row[5] or 0)
            last_quiz_date = stats_row[6]
            
            overall_accuracy = 0
            if total_questions > 0:
                overall_accuracy = (total_correct / total_questions) * 100
            
            average_time_per_question = 0
            if total_questions > 0:
                average_time_per_question = total_time_seconds / total_questions
            
            # Get quizzes today
            today = datetime.now().strftime('%Y-%m-%d')
            c.execute('''
                SELECT COUNT(*) 
                FROM quiz_results 
                WHERE device_id = ? AND DATE(timestamp) = ?
            ''', (device_id, today))
            
            quizzes_today = c.fetchone()[0] or 0
            
            statistics = {
                "device_id": device_id,
                "total_quizzes": total_quizzes,
                "total_correct": total_correct,
                "total_questions": total_questions,
                "total_time_seconds": total_time_seconds,
                "best_score": best_score,
                "best_accuracy": best_accuracy,
                "last_quiz_date": last_quiz_date,
                "overall_accuracy": round(overall_accuracy, 1),
                "average_time_per_question": round(average_time_per_question, 1),
                "quizzes_today": quizzes_today
            }
            
            return jsonify({
                "status": "success",
                "statistics": statistics
            })
        
    except Exception as e:
        print(f"❌ Error getting quiz statistics: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/export_excel', methods=['GET', 'OPTIONS'])
def export_excel():
    if request.method == 'OPTIONS':
        return '', 200
    
    try:
        with get_db_connection() as conn:
            query = '''
                SELECT 
                    word,
                    meaning_bangla,
                    meaning_english,
                    synonyms,
                    example_sentence,
                    category,
                    date_added
                FROM words 
                WHERE is_deleted = 0
                ORDER BY date_added DESC
            '''
            
            df = pd.read_sql_query(query, conn)
            
            if df.empty:
                df = pd.DataFrame(columns=['word', 'meaning_bangla', 'meaning_english', 'category', 'date_added'])
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"vocabulary_export_{timestamp}.xlsx"
            
            df.to_excel(EXCEL_FILE, index=False)
            
            return send_file(
                EXCEL_FILE,
                mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                as_attachment=True,
                download_name=filename
            )
        
    except Exception as e:
        print(f"Excel export error: {e}")
        return jsonify({"error": str(e)}), 500

# Import Excel endpoint (same as before, but enhanced)
@app.route('/api/import_excel', methods=['POST', 'OPTIONS'])
def import_excel():
    if request.method == 'OPTIONS':
        return '', 200
    
    try:
        if 'file' not in request.files:
            return jsonify({"status": "error", "message": "No file uploaded"}), 400
        
        file = request.files['file']
        
        if file.filename == '':
            return jsonify({"status": "error", "message": "No file selected"}), 400
        
        if not allowed_file(file.filename):
            return jsonify({"status": "error", "message": "Only Excel files (.xlsx, .xls) are allowed"}), 400
        
        device_id = request.form.get('device_id', 'unknown')
        
        # Save and read file
        filename = f"{uuid.uuid4().hex}_{file.filename}"
        filepath = os.path.join(UPLOAD_FOLDER, filename)
        file.save(filepath)
        
        try:
            df = pd.read_excel(filepath, keep_default_na=False)
            df = df.replace([np.nan, pd.NaT], '')
        except Exception as e:
            if os.path.exists(filepath):
                os.remove(filepath)
            return jsonify({"status": "error", "message": f"Failed to read Excel file: {str(e)}"}), 400
        
        # Clean up uploaded file
        if os.path.exists(filepath):
            os.remove(filepath)
        
        # Process the file (simplified version)
        total_rows = len(df)
        imported_rows = 0
        skipped_rows = 0
        current_time = datetime.now().isoformat()
        
        with get_db_cursor() as (c, conn):
            for index, row in df.iterrows():
                try:
                    # Extract data from row (assuming specific column names)
                    word = str(row.get('word', row.get('Word', ''))).strip()
                    if not word:
                        skipped_rows += 1
                        continue
                    
                    meaning_bangla = str(row.get('meaning_bangla', row.get('Bangla', ''))).strip()
                    meaning_english = str(row.get('meaning_english', row.get('English', ''))).strip()
                    synonyms = str(row.get('synonyms', row.get('Synonyms', ''))).strip()
                    example_sentence = str(row.get('example_sentence', row.get('Example', ''))).strip()
                    category = str(row.get('category', row.get('Category', 'General Vocabulary'))).strip()
                    
                    word = word.title()
                    
                    # Check if word exists
                    c.execute('''
                        SELECT id FROM words 
                        WHERE word = ? AND device_id = ? AND is_deleted = 0
                    ''', (word, device_id))
                    
                    existing = c.fetchone()
                    
                    if existing:
                        # Update existing word
                        c.execute('''
                            UPDATE words SET
                                meaning_bangla = ?,
                                meaning_english = ?,
                                synonyms = ?,
                                example_sentence = ?,
                                category = ?,
                                last_synced = ?,
                                sync_status = 'pending',
                                is_edited = 1
                            WHERE id = ?
                        ''', (
                            meaning_bangla,
                            meaning_english,
                            synonyms,
                            example_sentence,
                            category,
                            current_time,
                            existing[0]
                        ))
                    else:
                        # Insert new word
                        c.execute('''
                            INSERT INTO words 
                            (word, meaning_bangla, meaning_english, synonyms, example_sentence, 
                             category, date_added, device_id, last_synced, sync_status)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending')
                        ''', (
                            word,
                            meaning_bangla,
                            meaning_english,
                            synonyms,
                            example_sentence,
                            category,
                            current_time,
                            device_id,
                            current_time
                        ))
                    
                    imported_rows += 1
                    
                except Exception as e:
                    print(f"Error importing row {index}: {e}")
                    skipped_rows += 1
                    continue
        
        # Clear analytics cache
        with get_db_cursor() as (c, conn):
            c.execute('DELETE FROM analytics_cache WHERE key = "category_stats"')
        
        return jsonify({
            "status": "success",
            "message": f"Excel file imported successfully",
            "details": {
                "total_rows": total_rows,
                "imported": imported_rows,
                "skipped": skipped_rows,
                "timestamp": current_time
            }
        })
        
    except Exception as e:
        print(f"❌ Import error: {e}")
        return jsonify({"status": "error", "message": f"Import failed: {str(e)}"}), 500

if __name__ == '__main__':
    init_db()
    
    print("\n" + "="*70)
    print("📚 VOCABULARY PRO SERVER - ENHANCED EDITION")
    print("="*70)
    print("✅ All features implemented:")
    print("   - Complete word management (CRUD operations)")
    print("   - Category management (add, edit, delete)")
    print("   - Advanced collection with search, filter, sort")
    print("   - Pronunciation feature")
    print("   - Comprehensive quiz system")
    print("   - Detailed analytics dashboard")
    print("   - Excel import/export")
    print("="*70)
    
    app.run(
        host='0.0.0.0',
        port=8000,
        debug=True
    )