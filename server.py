from flask import Flask, request, jsonify, send_file, render_template
from flask_cors import CORS
import pandas as pd
import sqlite3
from datetime import datetime
import os
import json
import uuid
import numpy as np
import time
import threading
from contextlib import contextmanager

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*", "allow_headers": "*", "methods": "*"}})

# Modern Config
@app.route('/')
def serve_index():
    return render_template('index.html')

@app.route('/legacy')
def serve_legacy():
    return send_file('vocabulary_app.html')

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
                timeout=30,  # 30 second timeout
                check_same_thread=False  # Allow multi-threaded access
            )
            # Enable WAL mode for better concurrency
            conn.execute('PRAGMA journal_mode=WAL')
            conn.execute('PRAGMA busy_timeout=5000')  # 5 second busy timeout
            conn.row_factory = sqlite3.Row
            yield conn
            break
        except sqlite3.OperationalError as e:
            if "locked" in str(e) and attempt < retries - 1:
                time.sleep(0.1 * (attempt + 1))  # Exponential backoff
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
        # Words table with unique constraint
        c.execute('''
            CREATE TABLE IF NOT EXISTS words (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                word TEXT NOT NULL,
                meaning_bangla TEXT,
                meaning_english TEXT,
                synonyms TEXT,
                example_sentence TEXT,
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
        
        c.execute('''
            CREATE TABLE IF NOT EXISTS devices (
                device_id TEXT PRIMARY KEY,
                device_name TEXT,
                last_sync TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_ip TEXT
            )
        ''')
        
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
            ('Transitional Words', '#10b981', 1)
        ]
        
        for name, color, is_default in default_categories:
            c.execute('''
                INSERT OR IGNORE INTO categories (name, color, is_default)
                VALUES (?, ?, ?)
            ''', (name, color, is_default))
        
        # Create sync_log table
        c.execute('''
            CREATE TABLE IF NOT EXISTS sync_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                device_id TEXT,
                action TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                details TEXT
            )
        ''')
        
        # Create import_log table
        c.execute('''
            CREATE TABLE IF NOT EXISTS import_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                filename TEXT,
                device_id TEXT,
                total_rows INTEGER,
                imported_rows INTEGER,
                skipped_rows INTEGER,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                status TEXT,
                error_message TEXT
            )
        ''')
        
        # Create quiz tables
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
            CREATE TABLE IF NOT EXISTS quiz_settings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                device_id TEXT,
                quiz_type TEXT DEFAULT 'multiple_choice',
                question_count INTEGER DEFAULT 10,
                difficulty TEXT DEFAULT 'mixed',
                categories TEXT DEFAULT 'all',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(device_id, quiz_type)
            )
        ''')
        
        c.execute('''
            CREATE TABLE IF NOT EXISTS quiz_statistics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                device_id TEXT,
                total_quizzes INTEGER DEFAULT 0,
                total_correct INTEGER DEFAULT 0,
                total_questions INTEGER DEFAULT 0,
                total_time_seconds INTEGER DEFAULT 0,
                best_score INTEGER DEFAULT 0,
                best_accuracy REAL DEFAULT 0,
                last_quiz_date TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(device_id)
            )
        ''')
        
        # Create temp tables for better performance
        c.execute('PRAGMA optimize')
        
    print("✅ Database initialized with thread-safe connections")

# Quiz Results Database Table - REMOVE THIS SEPARATE FUNCTION
# The init_quiz_tables() function is not needed anymore since tables are created in init_db()














@app.after_request
def after_request(response):
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type, Authorization, Accept')
    response.headers.add('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, OPTIONS')
    response.headers.add('Access-Control-Allow-Credentials', 'true')
    response.headers.add('Access-Control-Max-Age', '86400')
    return response



@app.route('/favicon.ico')
def favicon():
    return '', 204

@app.route('/api/download_all', methods=['GET', 'OPTIONS'])
def download_all_words():
    if request.method == 'OPTIONS':
        return '', 200
    
    try:
        with get_db_cursor() as (c, conn):
            c.execute("SELECT * FROM words WHERE is_deleted = 0 ORDER BY date_added DESC")
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
@app.route('/api/test', methods=['GET', 'OPTIONS'])
def test_connection():
    if request.method == 'OPTIONS':
        return '', 200
    
    return jsonify({
        "status": "success",
        "message": "Vocabulary Pro Server is running!",
        "timestamp": datetime.now().isoformat(),
        "timestamp": datetime.now().isoformat(),
        "version": "4.3",
        "database": "thread-safe"
    })

@app.route('/api/status', methods=['GET', 'OPTIONS'])
def get_status():
    if request.method == 'OPTIONS':
        return '', 200
    
    try:
        with get_db_cursor() as (c, conn):
            c.execute("SELECT COUNT(*) FROM words WHERE is_deleted = 0")
            total_words = c.fetchone()[0]
            
            c.execute("SELECT COUNT(DISTINCT device_id) FROM devices")
            device_count = c.fetchone()[0]
            
            c.execute("SELECT COUNT(*) FROM categories")
            category_count = c.fetchone()[0]
            
            # Get last sync time
            c.execute("SELECT MAX(last_sync) FROM devices")
            last_sync = c.fetchone()[0]
            
            return jsonify({
                "status": "online",
                "total_words": total_words,
                "device_count": device_count,
                "category_count": category_count,
                "last_sync": last_sync,
                "server_time": datetime.now().isoformat(),
                "thread_safe": True
            })
            
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

@app.route('/api/categories', methods=['GET', 'OPTIONS'])
def get_categories():
    if request.method == 'OPTIONS':
        return '', 200
    
    try:
        with get_db_cursor() as (c, conn):
            c.execute("SELECT name, color, is_default FROM categories ORDER BY name")
            categories = [{"name": row[0], "color": row[1], "is_default": bool(row[2])} 
                         for row in c.fetchall()]
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
        color = data.get('color', '#6366f1')
        
        if not name:
            return jsonify({"status": "error", "message": "Category name required"}), 400
        
        with get_db_cursor() as (c, conn):
            c.execute('''
                INSERT OR IGNORE INTO categories (name, color, is_default)
                VALUES (?, ?, 0)
            ''', (name, color))
            
            if c.rowcount == 0:
                return jsonify({"status": "error", "message": "Category already exists"}), 400
            
            return jsonify({"status": "success", "message": f"Category '{name}' added"})
        
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
            return jsonify({"status": "error", "message": "Category name required"}), 400
        
        with get_db_cursor() as (c, conn):
            # Check if it's a default category
            c.execute("SELECT is_default FROM categories WHERE name = ?", (name,))
            result = c.fetchone()
            
            if not result:
                return jsonify({"status": "error", "message": "Category not found"}), 404
            
            if result[0] == 1:
                return jsonify({"status": "error", "message": "Cannot delete default categories"}), 400
            
            # Move words to General Vocabulary
            c.execute('''
                UPDATE words 
                SET category = 'General Vocabulary', sync_status = 'pending'
                WHERE category = ? AND is_deleted = 0
            ''', (name,))
            
            moved_count = c.rowcount
            
            # Delete category
            c.execute("DELETE FROM categories WHERE name = ?", (name,))
            
            return jsonify({
                "status": "success", 
                "message": f"Category deleted. {moved_count} words moved to General Vocabulary."
            })
        
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/deleted_words', methods=['GET', 'OPTIONS'])
def get_deleted_words():
    """Get list of deleted word IDs"""
    if request.method == 'OPTIONS':
        return '', 200
    
    try:
        with get_db_cursor() as (c, conn):
            c.execute('''
                SELECT id, word, device_id, last_synced 
                FROM words 
                WHERE is_deleted = 1
                ORDER BY last_synced DESC
            ''')
            
            deleted_words = []
            for row in c.fetchall():
                deleted_words.append({
                    'server_id': row[0],
                    'word': row[1],
                    'device_id': row[2],
                    'deleted_at': row[3]
                })
            
            return jsonify(deleted_words)
        
    except Exception as e:
        print(f"Error getting deleted words: {e}")
        return jsonify({"error": str(e)}), 500











@app.route('/api/import_excel', methods=['POST', 'OPTIONS'])
def import_excel():
    """Import words from Excel file"""
    if request.method == 'OPTIONS':
        return '', 200
    
    try:
        # Check if file was uploaded
        if 'file' not in request.files:
            return jsonify({
                "status": "error", 
                "message": "No file uploaded"
            }), 400
        
        file = request.files['file']
        
        # Check if file has a name
        if file.filename == '':
            return jsonify({
                "status": "error", 
                "message": "No file selected"
            }), 400
        
        # Check file extension
        if not allowed_file(file.filename):
            return jsonify({
                "status": "error", 
                "message": "Only Excel files (.xlsx, .xls) are allowed"
            }), 400
        
        # Get device ID from request
        device_id = request.form.get('device_id', 'unknown')
        device_name = request.form.get('device_name', f"Device-{device_id[:8]}")
        
        # Save file temporarily
        filename = f"{uuid.uuid4().hex}_{file.filename}"
        filepath = os.path.join(UPLOAD_FOLDER, filename)
        file.save(filepath)
        
        # Read Excel file with proper NaN handling
        try:
            df = pd.read_excel(filepath, keep_default_na=False)
            # Replace any remaining NaN or NaT with empty string
            df = df.replace([np.nan, pd.NaT], '')
        except Exception as e:
            # Clean up file
            if os.path.exists(filepath):
                os.remove(filepath)
            return jsonify({
                "status": "error", 
                "message": f"Failed to read Excel file: {str(e)}"
            }), 400
        
        # Clean up uploaded file
        if os.path.exists(filepath):
            os.remove(filepath)
        
        # Standardize column names - remove extra spaces, convert to lowercase for matching
        df.columns = [str(col).strip() for col in df.columns]
        
        # Debug: Print column names
        print(f"📊 Excel columns found: {list(df.columns)}")
        print(f"📊 First few rows for debugging:")
        print(df.head())
        
        # Find word column - more flexible matching
        word_column = None
        possible_word_columns = ['word', 'Word', 'WORD', 'Vocabulary', 'vocabulary', 
                                'Term', 'term', 'English Word', 'english word', 'Word/Phrase',
                                'word/phrase', 'Words', 'words']
        
        for col in df.columns:
            col_lower = col.lower().strip()
            for possible in possible_word_columns:
                if possible.lower() in col_lower or col_lower in possible.lower():
                    word_column = col
                    print(f"✅ Found word column: '{col}' (matched as '{word_column}')")
                    break
            if word_column:
                break
        
        if not word_column:
            return jsonify({
                "status": "error", 
                "message": f"Excel file must have a 'Word' column. Found columns: {list(df.columns)}"
            }), 400
        
        # SIMPLIFIED COLUMN MAPPING - Use exact column names since we know them
        column_mapping = {}
        
        # Look for EXACT column matches first (case-insensitive)
        column_names_lower = [col.lower() for col in df.columns]
        
        # Define priority mappings - exact matches first
        exact_mappings = {
            'meaning_bangla': ['meaning_bangla', 'bangla', 'bengali', 'bangla meaning', 'meaning in bangla'],
            'meaning_english': ['meaning_english', 'english', 'english meaning', 'meaning in english', 'definition'],
            'synonyms': ['synonyms', 'synonym'],
            'example_sentence': ['example_sentence', 'example', 'sentence'],
            'category': ['category', 'categories']
        }
        
        # First pass: Look for exact column name matches
        for col in df.columns:
            col_lower = col.lower()
            
            if col_lower == 'meaning_bangla' or col_lower == 'bangla' or 'bangla' in col_lower:
                if 'meaning_bangla' not in column_mapping:
                    column_mapping['meaning_bangla'] = col
                    print(f"✅ Mapped Bangla: '{col}' → 'meaning_bangla'")
            
            if col_lower == 'meaning_english' or col_lower == 'english' or ('english' in col_lower and 'bangla' not in col_lower):
                if 'meaning_english' not in column_mapping:
                    column_mapping['meaning_english'] = col
                    print(f"✅ Mapped English: '{col}' → 'meaning_english'")
            
            if col_lower == 'synonyms':
                if 'synonyms' not in column_mapping:
                    column_mapping['synonyms'] = col
                    print(f"✅ Mapped Synonyms: '{col}' → 'synonyms'")
            
            if col_lower == 'example_sentence' or 'example' in col_lower:
                if 'example_sentence' not in column_mapping:
                    column_mapping['example_sentence'] = col
                    print(f"✅ Mapped Example: '{col}' → 'example_sentence'")
            
            if col_lower == 'category':
                if 'category' not in column_mapping:
                    column_mapping['category'] = col
                    print(f"✅ Mapped Category: '{col}' → 'category'")
        
        # Second pass: If we didn't find exact matches, try other patterns
        if 'meaning_bangla' not in column_mapping:
            for col in df.columns:
                col_lower = col.lower()
                if any(term in col_lower for term in ['bangla', 'bengali', 'translation', 'মানে']):
                    column_mapping['meaning_bangla'] = col
                    print(f"🔄 Alternative Bangla mapping: '{col}' → 'meaning_bangla'")
                    break
        
        if 'meaning_english' not in column_mapping:
            for col in df.columns:
                col_lower = col.lower()
                if any(term in col_lower for term in ['english', 'definition', 'meaning', 'explanation']) and 'bangla' not in col_lower:
                    column_mapping['meaning_english'] = col
                    print(f"🔄 Alternative English mapping: '{col}' → 'meaning_english'")
                    break
        
        print(f"📊 Final column mapping: {column_mapping}")
        
        # Process each row
        total_rows = len(df)
        imported_rows = 0
        skipped_rows = 0
        current_time = datetime.now().isoformat()
        
        # Process each row with batch commit
        batch_size = 50
        for i in range(0, len(df), batch_size):
            batch = df.iloc[i:i+batch_size]
            
            with get_db_cursor() as (c, conn):
                for index, row in batch.iterrows():
                    try:
                        # Get word (required)
                        word = str(row[word_column]).strip()
                        if not word:
                            skipped_rows += 1
                            continue
                        
                        # Get other fields - with default empty values
                        meaning_bangla = ''
                        if 'meaning_bangla' in column_mapping:
                            meaning_bangla = str(row[column_mapping['meaning_bangla']]).strip()
                        
                        meaning_english = ''
                        if 'meaning_english' in column_mapping:
                            meaning_english = str(row[column_mapping['meaning_english']]).strip()
                        
                        synonyms = ''
                        if 'synonyms' in column_mapping:
                            synonyms = str(row[column_mapping['synonyms']]).strip()
                        
                        example = ''
                        if 'example_sentence' in column_mapping:
                            example = str(row[column_mapping['example_sentence']]).strip()
                        
                        category = ''
                        if 'category' in column_mapping:
                            category = str(row[column_mapping['category']]).strip()
                        
                        if not category:
                            category = 'General Vocabulary'
                        
                        # Capitalize word
                        word = word.title()
                        
                        # Debug first few
                        if imported_rows < 3:
                            print(f"🔍 Debug row {index}:")
                            print(f"   Word: '{word}'")
                            print(f"   Bangla from col '{column_mapping.get('meaning_bangla')}': '{meaning_bangla}'")
                            print(f"   English from col '{column_mapping.get('meaning_english')}': '{meaning_english}'")
                        
                        # Check if word already exists from this device
                        c.execute('''
                            SELECT id, is_deleted FROM words 
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
                                example,
                                category,
                                current_time,
                                existing[0]
                            ))
                        else:
                            # Insert new word
                            c.execute('''
                                INSERT INTO words 
                                (word, meaning_bangla, meaning_english, synonyms, example_sentence, 
                                 category, date_added, device_id, last_synced, is_deleted, sync_status)
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            ''', (
                                word,
                                meaning_bangla,
                                meaning_english,
                                synonyms,
                                example,
                                category,
                                current_time,
                                device_id,
                                current_time,
                                0,  # is_deleted
                                'pending'
                            ))
                        
                        imported_rows += 1
                        
                    except Exception as e:
                        print(f"❌ Error importing row {index}: {e}")
                        skipped_rows += 1
                        continue
        
        # Finalize with device update
        with get_db_cursor() as (c, conn):
            # Update device info
            c.execute('''
                INSERT OR REPLACE INTO devices 
                (device_id, device_name, last_sync, last_ip)
                VALUES (?, ?, ?, ?)
            ''', (device_id, device_name, current_time, request.remote_addr))
            
            # Log import
            c.execute('''
                INSERT INTO import_log 
                (filename, device_id, total_rows, imported_rows, skipped_rows, status, error_message)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                file.filename,
                device_id,
                total_rows,
                imported_rows,
                skipped_rows,
                'success',
                ''
            ))
            
            # Log sync
            c.execute('''
                INSERT INTO sync_log (device_id, action, details)
                VALUES (?, ?, ?)
            ''', (device_id, 'import', f'Imported {imported_rows} words from Excel file'))
        
        print(f"✅ Import completed: {imported_rows} imported, {skipped_rows} skipped")
        
        return jsonify({
            "status": "success",
            "message": f"Excel file imported successfully",
            "details": {
                "total_rows": total_rows,
                "imported": imported_rows,
                "skipped": skipped_rows,
                "filename": file.filename,
                "timestamp": current_time,
                "column_mapping": column_mapping
            }
        })
        
    except Exception as e:
        print(f"❌ Import error: {e}")
        
        # Log error
        try:
            with get_db_cursor() as (c, conn):
                c.execute('''
                    INSERT INTO import_log 
                    (filename, device_id, total_rows, imported_rows, skipped_rows, status, error_message)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (
                    file.filename if 'file' in locals() else 'unknown',
                    device_id if 'device_id' in locals() else 'unknown',
                    0, 0, 0,
                    'error',
                    str(e)
                ))
        except:
            pass
        
        return jsonify({
            "status": "error", 
            "message": f"Import failed: {str(e)}"
        }), 500











@app.route('/api/import_history', methods=['GET', 'OPTIONS'])
def get_import_history():
    """Get import history for a device"""
    if request.method == 'OPTIONS':
        return '', 200
    
    try:
        device_id = request.args.get('device_id', '')
        
        with get_db_cursor() as (c, conn):
            if device_id:
                c.execute('''
                    SELECT id, filename, device_id, total_rows, imported_rows, skipped_rows, 
                           timestamp, status, error_message
                    FROM import_log 
                    WHERE device_id = ?
                    ORDER BY timestamp DESC
                    LIMIT 50
                ''', (device_id,))
            else:
                c.execute('''
                    SELECT id, filename, device_id, total_rows, imported_rows, skipped_rows, 
                           timestamp, status, error_message
                    FROM import_log 
                    ORDER BY timestamp DESC
                    LIMIT 50
                ''')
            
            imports = []
            for row in c.fetchall():
                imports.append({
                    "id": row[0],
                    "filename": row[1],
                    "device_id": row[2],
                    "total_rows": row[3],
                    "imported_rows": row[4],
                    "skipped_rows": row[5],
                    "timestamp": row[6],
                    "status": row[7],
                    "error_message": row[8]
                })
            
            return jsonify({
                "status": "success",
                "imports": imports
            })
        
    except Exception as e:
        print(f"Get import history error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/import_template', methods=['GET', 'OPTIONS'])
def download_import_template():
    """Download Excel import template"""
    if request.method == 'OPTIONS':
        return '', 200
    
    try:
        # Create template dataframe
        template_data = {
            'Word': ['Example', 'Another Word', 'Test Word'],
            'Meaning Bangla': ['উদাহরণ', 'অন্য শব্দ', 'পরীক্ষা শব্দ'],
            'Meaning English': ['An illustration', 'Another term', 'Test term'],
            'Synonyms': ['Sample, Instance', 'Alternative, Different', 'Trial, Experiment'],
            'Example Sentence': ['This is an example sentence.', 'Here is another example.', 'Let\'s test this feature.'],
            'Category': ['General Vocabulary', 'Phrase and Idioms', 'Technical Terms']
        }
        
        df = pd.DataFrame(template_data)
        
        # Save to file
        template_path = os.path.join(UPLOAD_FOLDER, 'import_template.xlsx')
        df.to_excel(template_path, index=False)
        
        return send_file(
            template_path,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name='vocabulary_import_template.xlsx'
        )
        
    except Exception as e:
        print(f"Template download error: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/sync', methods=['POST', 'OPTIONS'])
def sync_words():
    if request.method == 'OPTIONS':
        return '', 200
    
    try:
        data = request.json
        if not data:
            return jsonify({"status": "error", "message": "No data"}), 400
            
        device_id = data.get('device_id', 'unknown')
        device_name = data.get('device_name', f"Device-{device_id[:8]}")
        words = data.get('words', [])
        
        current_time = datetime.now().isoformat()
        synced_count = 0
        server_ids = []
        
        # Process words in smaller batches to avoid long transactions
        batch_size = 20
        for i in range(0, len(words), batch_size):
            batch = words[i:i+batch_size]
            
            with get_db_cursor() as (c, conn):
                for word in batch:
                    try:
                        server_id = word.get('server_id')
                        is_deleted = word.get('is_deleted', False)
                        is_edited = word.get('is_edited', False)
                        word_text = word.get('word', '').strip()
                        
                        if not word_text:
                            continue
                        
                        # Handle deletions from ANY device
                        if is_deleted:
                            if server_id:
                                # Mark specific word as deleted by server_id
                                c.execute('''
                                    UPDATE words 
                                    SET is_deleted = 1,
                                        last_synced = ?,
                                        sync_status = 'synced'
                                    WHERE (id = ? OR original_id = ?) AND is_deleted = 0
                                ''', (current_time, server_id, server_id))
                            else:
                                # Mark word as deleted by content and device_id
                                c.execute('''
                                    UPDATE words 
                                    SET is_deleted = 1,
                                        last_synced = ?,
                                        sync_status = 'synced'
                                    WHERE word = ? AND device_id = ? AND is_deleted = 0
                                ''', (current_time, word_text, device_id))
                            
                            if c.rowcount > 0:
                                synced_count += 1
                            continue
                        
                        # For edited words - IMPORTANT FIX
                        if is_edited:
                            original_id = word.get('original_id')
                            if original_id:
                                # Mark original word as deleted and edited
                                c.execute('''
                                    UPDATE words 
                                    SET is_deleted = 1,
                                        is_edited = 1,
                                        last_synced = ?,
                                        sync_status = 'synced'
                                    WHERE id = ? AND is_deleted = 0
                                ''', (current_time, original_id))
                        
                        # For new/edited words - check if exists from this device
                        c.execute('''
                            SELECT id, is_deleted, is_edited, original_id FROM words 
                            WHERE word = ? AND device_id = ? AND is_deleted = 0
                        ''', (word_text, device_id))
                        
                        existing = c.fetchone()
                        
                        if existing:
                            word_id = existing[0]
                            is_existing_edited = existing[2]
                            existing_original_id = existing[3]
                            
                            # For edited words, create a new entry
                            if is_edited and not is_existing_edited:
                                # Insert as new edited word with original_id reference
                                c.execute('''
                                    INSERT INTO words 
                                    (word, meaning_bangla, meaning_english, synonyms, example_sentence, 
                                     category, date_added, device_id, last_synced, is_deleted, is_edited, 
                                     original_id, sync_status)
                                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                                ''', (
                                    word_text,
                                    word.get('meaning_bangla', ''),
                                    word.get('meaning_english', ''),
                                    word.get('synonyms', ''),
                                    word.get('example_sentence', ''),
                                    word.get('category', 'General Vocabulary'),
                                    word.get('timestamp', current_time),
                                    device_id,
                                    current_time,
                                    0,  # is_deleted
                                    1,  # is_edited
                                    original_id or word_id,  # original_id
                                    'synced'
                                ))
                                server_ids.append(c.lastrowid)
                            else:
                                # Update existing word
                                c.execute('''
                                    UPDATE words SET
                                        meaning_bangla = ?,
                                        meaning_english = ?,
                                        synonyms = ?,
                                        example_sentence = ?,
                                        category = ?,
                                        is_edited = ?,
                                        last_synced = ?,
                                        sync_status = 'synced'
                                    WHERE id = ?
                                ''', (
                                    word.get('meaning_bangla', ''),
                                    word.get('meaning_english', ''),
                                    word.get('synonyms', ''),
                                    word.get('example_sentence', ''),
                                    word.get('category', 'General Vocabulary'),
                                    word.get('is_edited', 0),
                                    current_time,
                                    word_id
                                ))
                                server_ids.append(word_id)
                        else:
                            # Insert new word (could be edited from another device)
                            c.execute('''
                                INSERT INTO words 
                                (word, meaning_bangla, meaning_english, synonyms, example_sentence, 
                                 category, date_added, device_id, last_synced, is_edited, 
                                 original_id, is_deleted, sync_status)
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            ''', (
                                word_text,
                                word.get('meaning_bangla', ''),
                                word.get('meaning_english', ''),
                                word.get('synonyms', ''),
                                word.get('example_sentence', ''),
                                word.get('category', 'General Vocabulary'),
                                word.get('timestamp', current_time),
                                device_id,
                                current_time,
                                word.get('is_edited', 0),
                                word.get('original_id'),
                                0,  # is_deleted
                                'synced'
                            ))
                            server_ids.append(c.lastrowid)
                        
                        synced_count += 1
                        
                    except Exception as e:
                        print(f"Error syncing word {word_text}: {e}")
                        continue
        
        # Final device update
        with get_db_cursor() as (c, conn):
            # Update device info
            c.execute('''
                INSERT OR REPLACE INTO devices 
                (device_id, device_name, last_sync, last_ip)
                VALUES (?, ?, ?, ?)
            ''', (device_id, device_name, current_time, request.remote_addr))
            
            # Log sync
            c.execute('''
                INSERT INTO sync_log (device_id, action, details)
                VALUES (?, ?, ?)
            ''', (device_id, 'sync', f'Synced {synced_count} items'))
        
        return jsonify({
            "status": "success",
            "synced": synced_count,
            "server_ids": server_ids,
            "timestamp": current_time,
            "message": f"Synced {synced_count} items"
        })
        
    except Exception as e:
        print(f"Sync error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/download', methods=['GET', 'OPTIONS'])
def download_all_words():
    if request.method == 'OPTIONS':
        return '', 200
    
    try:
        with get_db_connection() as conn:
            query = '''
                SELECT 
                    id as server_id,
                    word,
                    meaning_bangla,
                    meaning_english,
                    synonyms,
                    example_sentence,
                    category,
                    date_added,
                    device_id,
                    is_deleted,
                    is_edited,
                    original_id
                FROM words 
                WHERE is_deleted = 0
                ORDER BY date_added DESC
            '''
            
            df = pd.read_sql_query(query, conn)
            words = df.to_dict('records')
            
            return jsonify(words)
        
    except Exception as e:
        print(f"Download error: {e}")
        return jsonify({"error": str(e), "message": "Failed to download words"}), 500

@app.route('/api/last_sync', methods=['GET', 'OPTIONS'])
def get_last_sync():
    if request.method == 'OPTIONS':
        return '', 200
    
    try:
        with get_db_cursor() as (c, conn):
            c.execute("SELECT MAX(last_sync) FROM devices")
            result = c.fetchone()
            
            return jsonify({
                "last_sync": result[0] if result[0] else "Never"
            })
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

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
                    date_added,
                    device_id
                FROM words 
                WHERE is_deleted = 0
                ORDER BY date_added DESC
            '''
            
            df = pd.read_sql_query(query, conn)
            
            if df.empty:
                df = pd.DataFrame(columns=['word', 'meaning_bangla', 'meaning_english', 'category', 'device_id'])
            
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

@app.route('/')
def home():
    ip_address = get_ip_address()
    return f'''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Vocabulary Pro Server v4.3</title>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>
            body {{
                font-family: Arial, sans-serif;
                padding: 20px;
                max-width: 800px;
                margin: 0 auto;
                background: linear-gradient(135deg, #f0f4ff 0%, #f8fafc 100%);
            }}
            .container {{
                background: white;
                padding: 30px;
                border-radius: 20px;
                box-shadow: 0 10px 30px rgba(0,0,0,0.1);
            }}
            h1 {{ 
                color: #6366f1; 
                margin-bottom: 10px;
                display: flex;
                align-items: center;
                gap: 10px;
            }}
            .btn {{
                background: linear-gradient(135deg, #6366f1 0%, #4f46e5 100%);
                color: white;
                padding: 12px 24px;
                border: none;
                border-radius: 10px;
                text-decoration: none;
                display: inline-flex;
                align-items: center;
                gap: 8px;
                margin: 10px 5px;
                cursor: pointer;
                font-weight: 600;
                transition: all 0.3s;
            }}
            .btn:hover {{
                transform: translateY(-2px);
                box-shadow: 0 5px 15px rgba(99, 102, 241, 0.3);
            }}
            .info {{
                background: #e0f2fe;
                padding: 20px;
                border-radius: 12px;
                margin: 25px 0;
                border-left: 4px solid #3b82f6;
            }}
            .url {{
                background: #f3f4f6;
                padding: 12px;
                border-radius: 8px;
                font-family: monospace;
                margin: 8px 0;
                word-break: break-all;
                border: 1px solid #e5e7eb;
            }}
            .status {{
                display: inline-flex;
                align-items: center;
                gap: 8px;
                padding: 8px 16px;
                background: #d1fae5;
                color: #065f46;
                border-radius: 20px;
                font-weight: 600;
            }}
            .feature {{
                background: #f0fdf4;
                padding: 15px;
                border-radius: 10px;
                margin: 15px 0;
                border-left: 4px solid #10b981;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>
                <span style="font-size: 32px;">📚</span>
                Vocabulary Pro Server v4.3
            </h1>
            
            <div style="margin-bottom: 20px;">
                <span class="status">✅ Online - Thread Safe Database</span>
            </div>
            
            <div class="info">
                <p><strong>Server IP:</strong> {ip_address}</p>
                <p><strong>Port:</strong> 8000</p>
                
                <p><strong style="color: #6366f1;">Access URLs:</strong></p>
                <div class="url">💻 On this computer: http://localhost:8000/app-full</div>
                <div class="url">📱 On your phone: http://{ip_address}:8000/app-full</div>
            </div>
            
            <div class="feature">
                <p><strong>✨ Enhanced Features:</strong></p>
                <p>✓ Thread-safe database connections</p>
                <p>✓ No more "database is locked" errors</p>
                <p>✓ Batch processing for better performance</p>
                <button class="btn" onclick="window.location.href='/api/import_template'" style="background: linear-gradient(135deg, #10b981 0%, #0da271 100%);">
                    <span>📥</span> Download Import Template
                </button>
            </div>
            
            <div style="margin: 30px 0;">
                <a href="/app-full" class="btn">
                    <span>📱</span> Open App
                </a>
                <button class="btn" onclick="window.location.href='/api/test'">
                    <span>🔧</span> Test API
                </button>
                <button class="btn" onclick="window.location.href='/api/download'">
                    <span>📥</span> Download Words
                </button>
            </div>
            
            <div style="margin-top: 30px; padding: 20px; background: #f0fdf4; border-radius: 12px;">
                <p><strong>Debug Info:</strong></p>
                <p><button class="btn" onclick="testConnection()" style="background: linear-gradient(135deg, #10b981 0%, #0da271 100%);">
                    <span>🔍</span> Test Connection
                </button></p>
                <div id="debugResult" style="margin-top: 15px;"></div>
            </div>
        </div>
        
        <script>
            async function testConnection() {{
                const result = document.getElementById('debugResult');
                result.innerHTML = '<div style="color: #f59e0b;">Testing connection...</div>';
                
                try {{
                    const response = await fetch('/api/test');
                    if (response.ok) {{
                        const data = await response.json();
                        result.innerHTML = `
                            <div style="color: #10b981;">
                                <p>✅ Connection successful!</p>
                                <p><strong>Server:</strong> ${{data.server_ip}}</p>
                                <p><strong>Time:</strong> ${{data.timestamp}}</p>
                                <p><strong>Version:</strong> ${{data.version}}</p>
                                <p><strong>Database:</strong> ${{data.database}}</p>
                            </div>
                        `;
                    }} else {{
                        result.innerHTML = '<div style="color: #ef4444;">❌ Connection failed</div>';
                    }}
                }} catch (error) {{
                    result.innerHTML = '<div style="color: #ef4444;">❌ Connection error: ' + error.message + '</div>';
                }}
            }}
            
            // Auto-test on load
            setTimeout(testConnection, 1000);
        </script>
    </body>
    </html>
    '''

@app.route('/app-full')
def serve_app():
    try:
        with open('vocabulary_app.html', 'r', encoding='utf-8') as f:
            return f.read()
    except FileNotFoundError:
        return '''
        <!DOCTYPE html>
        <html>
        <body style="padding: 50px; font-family: Arial; text-align: center;">
            <h1 style="color: #ef4444;">⚠️ App File Not Found</h1>
            <p>Please make sure 'vocabulary_app.html' is in the same folder as server.py</p>
            <a href="/" style="color: #6366f1; text-decoration: none; font-weight: bold;">← Go Back</a>
        </body>
        </html>
        ''', 404
    






# ==============================================
# QUIZ ENDPOINTS
# ==============================================


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
            
            # Update quiz statistics - SIMPLIFIED VERSION
            # First, try to update existing record
            c.execute('''
                UPDATE quiz_statistics 
                SET total_quizzes = total_quizzes + 1,
                    total_correct = total_correct + ?,
                    total_questions = total_questions + ?,
                    total_time_seconds = total_time_seconds + ?,
                    best_score = CASE WHEN ? > best_score THEN ? ELSE best_score END,
                    best_accuracy = CASE WHEN ? > best_accuracy THEN ? ELSE best_accuracy END,
                    last_quiz_date = ?
                WHERE device_id = ?
            ''', (
                score, total_questions, time_taken_seconds,
                score, score, accuracy, accuracy, timestamp, device_id
            ))
            
            # If no rows were updated, insert a new record
            if c.rowcount == 0:
                c.execute('''
                    INSERT INTO quiz_statistics 
                    (device_id, total_quizzes, total_correct, total_questions, 
                     total_time_seconds, best_score, best_accuracy, last_quiz_date)
                    VALUES (?, 1, ?, ?, ?, ?, ?, ?)
                ''', (
                    device_id,
                    score, total_questions, time_taken_seconds,
                    score, accuracy, timestamp
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
        import traceback
        traceback.print_exc()
        return jsonify({"status": "error", "message": str(e)}), 500











@app.route('/api/quiz_results', methods=['GET', 'OPTIONS'])
def get_quiz_results():
    """Get quiz results for a device or all devices"""
    if request.method == 'OPTIONS':
        return '', 200
    
    try:
        device_id = request.args.get('device_id', '')
        show_all = request.args.get('show_all', 'false').lower() == 'true'
        limit = int(request.args.get('limit', 20))
        
        with get_db_cursor() as (c, conn):
            if device_id and not show_all:
                # Get results for specific device
                c.execute('''
                    SELECT id, quiz_type, score, total_questions, accuracy, 
                           time_taken_seconds, timestamp, correct_words, incorrect_words
                    FROM quiz_results 
                    WHERE device_id = ?
                    ORDER BY timestamp DESC
                    LIMIT ?
                ''', (device_id, limit))
            else:
                # Get results from ALL devices
                c.execute('''
                    SELECT qr.id, qr.quiz_type, qr.score, qr.total_questions, qr.accuracy, 
                           qr.time_taken_seconds, qr.timestamp, 
                           qr.correct_words, qr.incorrect_words,
                           qr.device_id, d.device_name
                    FROM quiz_results qr
                    LEFT JOIN devices d ON qr.device_id = d.device_id
                    ORDER BY qr.timestamp DESC
                    LIMIT ?
                ''', (limit,))
            
            results = []
            for row in c.fetchall():
                if device_id and not show_all:
                    # Single device format
                    result = {
                        "id": row[0],
                        "quiz_type": row[1],
                        "score": row[2],
                        "total_questions": row[3],
                        "accuracy": float(row[4]),
                        "time_taken_seconds": row[5],
                        "timestamp": row[6],
                        "correct_words": json.loads(row[7]) if row[7] else [],
                        "incorrect_words": json.loads(row[8]) if row[8] else []
                    }
                else:
                    # All devices format (includes device info)
                    result = {
                        "id": row[0],
                        "quiz_type": row[1],
                        "score": row[2],
                        "total_questions": row[3],
                        "accuracy": float(row[4]),
                        "time_taken_seconds": row[5],
                        "timestamp": row[6],
                        "correct_words": json.loads(row[7]) if row[7] else [],
                        "incorrect_words": json.loads(row[8]) if row[8] else [],
                        "device_id": row[9],
                        "device_name": row[10] or f"Device-{row[9][:8]}"
                    }
                results.append(result)
            
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
    """Get quiz statistics for a device or overall"""
    if request.method == 'OPTIONS':
        return '', 200
    
    try:
        device_id = request.args.get('device_id', '')
        global_stats = request.args.get('global', 'false').lower() == 'true'
        
        with get_db_cursor() as (c, conn):
            if device_id and not global_stats:
                # Get statistics for specific device
                c.execute('''
                    SELECT total_quizzes, total_correct, total_questions, 
                           total_time_seconds, best_score, best_accuracy, last_quiz_date
                    FROM quiz_statistics 
                    WHERE device_id = ?
                ''', (device_id,))
                
                stats_row = c.fetchone()
                
                if not stats_row:
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
                            "quizzes_today": 0,
                            "is_global": False
                        }
                    })
                
                # Calculate derived statistics for single device
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
                
                # Get quizzes today for this device
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
                    "quizzes_today": quizzes_today,
                    "is_global": False
                }
                
            else:
                # Get GLOBAL statistics across all devices
                c.execute('''
                    SELECT 
                        COUNT(DISTINCT device_id) as total_devices,
                        SUM(total_quizzes) as total_quizzes,
                        SUM(total_correct) as total_correct,
                        SUM(total_questions) as total_questions,
                        SUM(total_time_seconds) as total_time_seconds,
                        MAX(best_score) as global_best_score,
                        MAX(best_accuracy) as global_best_accuracy
                    FROM quiz_statistics
                ''')
                
                global_row = c.fetchone()
                
                total_devices = global_row[0] or 0
                total_quizzes = global_row[1] or 0
                total_correct = global_row[2] or 0
                total_questions = global_row[3] or 0
                total_time_seconds = global_row[4] or 0
                global_best_score = global_row[5] or 0
                global_best_accuracy = float(global_row[6] or 0)
                
                # Get today's quizzes across all devices
                today = datetime.now().strftime('%Y-%m-%d')
                c.execute('''
                    SELECT COUNT(DISTINCT device_id), COUNT(*) 
                    FROM quiz_results 
                    WHERE DATE(timestamp) = ?
                ''', (today,))
                
                today_row = c.fetchone()
                devices_active_today = today_row[0] or 0
                quizzes_today = today_row[1] or 0
                
                # Get recent quizzes
                c.execute('''
                    SELECT qr.score, qr.total_questions, qr.accuracy, qr.timestamp,
                           qr.device_id, d.device_name
                    FROM quiz_results qr
                    LEFT JOIN devices d ON qr.device_id = d.device_id
                    ORDER BY qr.timestamp DESC
                    LIMIT 5
                ''')
                
                recent_quizzes = []
                for row in c.fetchall():
                    recent_quizzes.append({
                        "score": row[0],
                        "total_questions": row[1],
                        "accuracy": float(row[2]),
                        "timestamp": row[3],
                        "device_id": row[4],
                        "device_name": row[5] or f"Device-{row[4][:8]}"
                    })
                
                overall_accuracy = 0
                if total_questions > 0:
                    overall_accuracy = (total_correct / total_questions) * 100
                
                average_time_per_question = 0
                if total_questions > 0:
                    average_time_per_question = total_time_seconds / total_questions
                
                statistics = {
                    "total_devices": total_devices,
                    "total_quizzes": total_quizzes,
                    "total_correct": total_correct,
                    "total_questions": total_questions,
                    "total_time_seconds": total_time_seconds,
                    "global_best_score": global_best_score,
                    "global_best_accuracy": global_best_accuracy,
                    "overall_accuracy": round(overall_accuracy, 1),
                    "average_time_per_question": round(average_time_per_question, 1),
                    "devices_active_today": devices_active_today,
                    "quizzes_today": quizzes_today,
                    "recent_quizzes": recent_quizzes,
                    "is_global": True
                }
            
            return jsonify({
                "status": "success",
                "statistics": statistics
            })
        
    except Exception as e:
        print(f"❌ Error getting quiz statistics: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500














@app.route('/api/save_quiz_settings', methods=['POST', 'OPTIONS'])
def save_quiz_settings():
    """Save quiz settings for a device"""
    if request.method == 'OPTIONS':
        return '', 200
    
    try:
        data = request.json
        if not data:
            return jsonify({"status": "error", "message": "No data"}), 400
        
        device_id = data.get('device_id', 'unknown')
        quiz_type = data.get('quiz_type', 'multiple_choice')
        question_count = int(data.get('question_count', 10))
        difficulty = data.get('difficulty', 'mixed')
        categories = json.dumps(data.get('categories', ['all']))
        
        with get_db_cursor() as (c, conn):
            c.execute('''
                INSERT OR REPLACE INTO quiz_settings 
                (device_id, quiz_type, question_count, difficulty, categories)
                VALUES (?, ?, ?, ?, ?)
            ''', (device_id, quiz_type, question_count, difficulty, categories))
            
            # Log the action
            c.execute('''
                INSERT INTO sync_log (device_id, action, details)
                VALUES (?, ?, ?)
            ''', (device_id, 'quiz_settings_updated', 
                  f'Quiz settings updated: {quiz_type}, {question_count} questions'))
        
        return jsonify({
            "status": "success",
            "message": "Quiz settings saved"
        })
        
    except Exception as e:
        print(f"❌ Error saving quiz settings: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/get_quiz_settings', methods=['GET', 'OPTIONS'])
def get_quiz_settings():
    """Get quiz settings for a device"""
    if request.method == 'OPTIONS':
        return '', 200
    
    try:
        device_id = request.args.get('device_id', '')
        
        if not device_id:
            return jsonify({"status": "error", "message": "device_id required"}), 400
        
        with get_db_cursor() as (c, conn):
            c.execute('''
                SELECT quiz_type, question_count, difficulty, categories
                FROM quiz_settings 
                WHERE device_id = ?
            ''', (device_id,))
            
            settings_row = c.fetchone()
            
            if not settings_row:
                # Return default settings
                return jsonify({
                    "status": "success",
                    "settings": {
                        "quiz_type": "multiple_choice",
                        "question_count": 10,
                        "difficulty": "mixed",
                        "categories": ["all"]
                    }
                })
            
            # Parse categories from JSON string
            try:
                categories = json.loads(settings_row[3])
            except:
                categories = ["all"]
            
            settings = {
                "quiz_type": settings_row[0],
                "question_count": settings_row[1],
                "difficulty": settings_row[2],
                "categories": categories
            }
            
            return jsonify({
                "status": "success",
                "settings": settings
            })
        
    except Exception as e:
        print(f"❌ Error getting quiz settings: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/quiz_leaderboard', methods=['GET', 'OPTIONS'])
def get_quiz_leaderboard():
    """Get quiz leaderboard"""
    if request.method == 'OPTIONS':
        return '', 200
    
    try:
        limit = int(request.args.get('limit', 10))
        
        with get_db_cursor() as (c, conn):
            # Get best scores per device
            c.execute('''
                SELECT 
                    qr.device_id,
                    d.device_name,
                    MAX(qr.score) as best_score,
                    MAX(qr.accuracy) as best_accuracy,
                    COUNT(qr.id) as total_quizzes,
                    MAX(qr.timestamp) as last_quiz
                FROM quiz_results qr
                LEFT JOIN devices d ON qr.device_id = d.device_id
                GROUP BY qr.device_id
                ORDER BY best_score DESC, best_accuracy DESC
                LIMIT ?
            ''', (limit,))
            
            leaderboard = []
            for row in c.fetchall():
                leaderboard.append({
                    "device_id": row[0],
                    "device_name": row[1] or f"Device-{row[0][:8]}",
                    "best_score": row[2] or 0,
                    "best_accuracy": float(row[3] or 0),
                    "total_quizzes": row[4] or 0,
                    "last_quiz": row[5]
                })
            
            return jsonify({
                "status": "success",
                "leaderboard": leaderboard,
                "updated": datetime.now().isoformat()
            })
        
    except Exception as e:
        print(f"❌ Error getting leaderboard: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/clear_quiz_data', methods=['POST', 'OPTIONS'])
def clear_quiz_data():
    """Clear quiz data for a device"""
    if request.method == 'OPTIONS':
        return '', 200
    
    try:
        data = request.json
        device_id = data.get('device_id', '')
        
        if not device_id:
            return jsonify({"status": "error", "message": "device_id required"}), 400
        
        with get_db_cursor() as (c, conn):
            # Delete quiz results
            c.execute('DELETE FROM quiz_results WHERE device_id = ?', (device_id,))
            results_deleted = c.rowcount
            
            # Delete quiz statistics
            c.execute('DELETE FROM quiz_statistics WHERE device_id = ?', (device_id,))
            stats_deleted = c.rowcount
            
            # Delete quiz settings
            c.execute('DELETE FROM quiz_settings WHERE device_id = ?', (device_id,))
            settings_deleted = c.rowcount
            
            # Log the action
            c.execute('''
                INSERT INTO sync_log (device_id, action, details)
                VALUES (?, ?, ?)
            ''', (device_id, 'quiz_data_cleared', 
                  f'Cleared {results_deleted} results, {stats_deleted} stats, {settings_deleted} settings'))
        
        return jsonify({
            "status": "success",
            "message": "Quiz data cleared",
            "details": {
                "results_deleted": results_deleted,
                "stats_deleted": stats_deleted,
                "settings_deleted": settings_deleted
            }
        })
        
    except Exception as e:
        print(f"❌ Error clearing quiz data: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500








@app.route('/api/devices', methods=['GET', 'OPTIONS'])
def get_devices():
    """Get list of all devices"""
    if request.method == 'OPTIONS':
        return '', 200
    
    try:
        with get_db_cursor() as (c, conn):
            c.execute('''
                SELECT device_id, device_name, last_sync, last_ip, created_at,
                       (SELECT COUNT(*) FROM words WHERE device_id = devices.device_id AND is_deleted = 0) as word_count,
                       (SELECT COUNT(*) FROM quiz_results WHERE device_id = devices.device_id) as quiz_count
                FROM devices
                ORDER BY last_sync DESC
            ''')
            
            devices = []
            for row in c.fetchall():
                devices.append({
                    "device_id": row[0],
                    "device_name": row[1],
                    "last_sync": row[2],
                    "last_ip": row[3],
                    "created_at": row[4],
                    "word_count": row[5] or 0,
                    "quiz_count": row[6] or 0
                })
            
            return jsonify({
                "status": "success",
                "devices": devices,
                "total_devices": len(devices)
            })
        
    except Exception as e:
        print(f"❌ Error getting devices: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500










if __name__ == '__main__':
    init_db()
    
    print("\n" + "="*70)
    print("📚 VOCABULARY PRO SERVER - CLOUD READY v5.0")
    print("="*70)
    
    # Set threading options
    app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max upload
    app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{DB_FILE}'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    
    app.run(
        host='0.0.0.0',
        port=8000,
        debug=True
    )