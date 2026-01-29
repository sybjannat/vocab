import sqlite3

def clean_nan_values_in_database():
    """Clean up existing 'nan' values in the database"""
    conn = sqlite3.connect('vocabulary.db')
    c = conn.cursor()
    
    # Count affected records first
    print("Scanning for 'nan' values in database...")
    
    # Fields to check and clean
    fields_to_clean = [
        ('meaning_bangla', 'Bangla meaning'),
        ('meaning_english', 'English meaning'),
        ('synonyms', 'Synonyms'),
        ('example_sentence', 'Example sentence'),
        ('category', 'Category')
    ]
    
    total_cleaned = 0
    
    for field, field_name in fields_to_clean:
        # Count records with 'nan' in this field
        c.execute(f"SELECT COUNT(*) FROM words WHERE {field} LIKE '%nan%'")
        count = c.fetchone()[0]
        
        if count > 0:
            print(f"Found {count} records with 'nan' in {field_name}")
            
            # Clean the 'nan' values
            c.execute(f"""
                UPDATE words 
                SET {field} = ''
                WHERE {field} LIKE '%nan%' AND {field} != ''
            """)
            
            # Also clean 'None' values
            c.execute(f"""
                UPDATE words 
                SET {field} = ''
                WHERE {field} LIKE '%None%' AND {field} != ''
            """)
            
            # Also clean '<NA>' values
            c.execute(f"""
                UPDATE words 
                SET {field} = ''
                WHERE {field} LIKE '%<NA>%' AND {field} != ''
            """)
            
            total_cleaned += count
            print(f"Cleaned {field_name}")
    
    # Commit changes
    conn.commit()
    
    # Verify cleanup
    print("\nVerification scan after cleanup:")
    for field, field_name in fields_to_clean:
        c.execute(f"SELECT COUNT(*) FROM words WHERE {field} LIKE '%nan%' OR {field} LIKE '%None%' OR {field} LIKE '%<NA>%'")
        remaining = c.fetchone()[0]
        print(f"Remaining 'nan' in {field_name}: {remaining}")
    
    # Also clean empty 'nan' strings that might be exactly 'nan'
    c.execute("""
        UPDATE words 
        SET meaning_bangla = ''
        WHERE meaning_bangla = 'nan'
    """)
    
    c.execute("""
        UPDATE words 
        SET meaning_english = ''
        WHERE meaning_english = 'nan'
    """)
    
    c.execute("""
        UPDATE words 
        SET synonyms = ''
        WHERE synonyms = 'nan'
    """)
    
    c.execute("""
        UPDATE words 
        SET example_sentence = ''
        WHERE example_sentence = 'nan'
    """)
    
    c.execute("""
        UPDATE words 
        SET category = 'General Vocabulary'
        WHERE category = 'nan'
    """)
    
    conn.commit()
    conn.close()
    
    print(f"\n✅ Cleanup complete! Total records cleaned: {total_cleaned}")

if __name__ == "__main__":
    clean_nan_values_in_database()