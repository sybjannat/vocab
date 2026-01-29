import sqlite3
import os
from datetime import datetime

def erase_all_words_from_server():
    """Completely erase ALL words from the server database"""
    DB_FILE = 'vocabulary.db'
    
    print("=" * 60)
    print("⚠️  WORD ERASURE TOOL - SERVER DATABASE CLEANUP")
    print("=" * 60)
    print("\nWARNING: This will DELETE ALL WORDS from the server!")
    print("This action cannot be undone!")
    print("-" * 60)
    
    # First confirmation
    confirmation = input("\nType 'DELETE ALL WORDS' to confirm: ")
    
    if confirmation != "DELETE ALL WORDS":
        print("\n❌ Operation cancelled.")
        return
    
    print("\n" + "=" * 60)
    print("🚨 PREPARING TO ERASE ALL WORDS...")
    print("=" * 60)
    
    try:
        # Create a backup first (just in case)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_file = f"vocabulary_backup_{timestamp}.db"
        
        if os.path.exists(DB_FILE):
            with open(DB_FILE, 'rb') as f:
                with open(backup_file, 'wb') as backup:
                    backup.write(f.read())
            print(f"\n✅ Backup created: {backup_file}")
        else:
            print(f"\n❌ Database file not found: {DB_FILE}")
            return
        
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        
        # Get counts before deletion
        c.execute("SELECT COUNT(*) FROM words")
        total_words = c.fetchone()[0]
        
        c.execute("SELECT COUNT(*) FROM words WHERE is_deleted = 0")
        active_words = c.fetchone()[0]
        
        c.execute("SELECT COUNT(DISTINCT device_id) FROM words WHERE is_deleted = 0")
        device_count = c.fetchone()[0]
        
        print(f"\n📊 DATABASE STATISTICS:")
        print(f"   • Total words (including deleted): {total_words}")
        print(f"   • Active words: {active_words}")
        print(f"   • Devices with words: {device_count}")
        
        if active_words == 0:
            print("\n📭 Database is already empty!")
            conn.close()
            return
        
        # Show sample of what will be deleted
        if active_words > 0:
            c.execute("SELECT word, device_id FROM words WHERE is_deleted = 0 LIMIT 5")
            sample_words = c.fetchall()
            print(f"\n📝 Sample words to be deleted (first 5):")
            for word, device in sample_words:
                device_short = device[:8] + "..." if len(device) > 8 else device
                print(f"   • '{word}' (Device: {device_short})")
        
        # Second confirmation
        print("\n" + "-" * 60)
        print("⚠️  FINAL CONFIRMATION REQUIRED")
        print("-" * 60)
        final_confirmation = input(f"\nDelete {active_words} words from {device_count} devices? (yes/no): ")
        
        if final_confirmation.lower() != 'yes':
            print("\n❌ Operation cancelled.")
            conn.close()
            return
        
        print("\n" + "=" * 60)
        print("🗑️  STARTING DELETION PROCESS...")
        print("=" * 60)
        
        # Delete ALL words completely
        print("\n1. Deleting ALL words from database...")
        c.execute("DELETE FROM words")
        deleted_count = c.rowcount
        print(f"   ✓ Deleted {deleted_count} words")
        
        # Clear logs
        print("\n2. Clearing sync logs...")
        c.execute("DELETE FROM sync_log")
        sync_logs_deleted = c.rowcount
        print(f"   ✓ Deleted {sync_logs_deleted} sync logs")
        
        print("\n3. Clearing import logs...")
        c.execute("DELETE FROM import_log")
        import_logs_deleted = c.rowcount
        print(f"   ✓ Deleted {import_logs_deleted} import logs")
        
        # Reset auto-increment counters
        print("\n4. Resetting auto-increment counters...")
        c.execute("DELETE FROM sqlite_sequence WHERE name IN ('words', 'sync_log', 'import_log')")
        
        conn.commit()
        
        # Verify deletion
        print("\n5. Verifying deletion...")
        c.execute("SELECT COUNT(*) FROM words")
        remaining_words = c.fetchone()[0]
        
        c.execute("SELECT COUNT(*) FROM sync_log")
        remaining_logs = c.fetchone()[0]
        
        c.execute("SELECT COUNT(*) FROM import_log")
        remaining_imports = c.fetchone()[0]
        
        # Vacuum to reclaim space
        print("\n6. Compacting database...")
        c.execute("VACUUM")
        
        conn.commit()
        conn.close()
        
        print("\n" + "=" * 60)
        print("✅ DELETION COMPLETE!")
        print("=" * 60)
        
        print(f"\n📊 FINAL RESULTS:")
        print(f"   ✓ Words deleted: {deleted_count}")
        print(f"   ✓ Sync logs deleted: {sync_logs_deleted}")
        print(f"   ✓ Import logs deleted: {import_logs_deleted}")
        print(f"   ✓ Remaining words: {remaining_words}")
        
        # FIXED: Changed 'backfile_file' to 'backup_file'
        if os.path.exists(backup_file):
            backup_size = os.path.getsize(backup_file) / 1024
            print(f"\n💾 BACKUP INFORMATION:")
            print(f"   • Backup file: {backup_file}")
            print(f"   • Backup size: {backup_size:.1f} KB")
            print(f"\n💡 To restore, rename '{backup_file}' to 'vocabulary.db'")
        
        print("\n" + "=" * 60)
        print("🎯 NEXT STEPS:")
        print("=" * 60)
        print("1. Start your server: python server.py")
        print("2. Check your app - all word counts should be 0")
        print("3. You can now add fresh words")
        
    except sqlite3.OperationalError as e:
        print(f"\n❌ DATABASE ERROR: {e}")
        print("\n💡 TROUBLESHOOTING:")
        print("   • Make sure the server is NOT running")
        print("   • Check if vocabulary.db file exists")
        print("   • Try closing all programs that might be using the database")
        
    except Exception as e:
        print(f"\n❌ UNEXPECTED ERROR: {e}")
        import traceback
        traceback.print_exc()  # This will show the exact error location

if __name__ == "__main__":
    erase_all_words_from_server()