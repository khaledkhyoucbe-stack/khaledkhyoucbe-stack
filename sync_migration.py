import sqlite3
import uuid

DB_FILE = 'maarif.db'

def setup_sync_columns():
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    
    tables = [
        'schools', 'users', 'classes', 'students', 'grades', 
        'attendance', 'fees', 'payments', 'expenses', 'messages', 
        'homework', 'archives', 'school_settings'
    ]
    
    for table in tables:
        print(f"Migrating table {table}...")
        
        # Get existing columns
        cur.execute(f"PRAGMA table_info({table})")
        columns = [info[1] for info in cur.fetchall()]
        
        try:
            # Add sync_id
            if 'sync_id' not in columns:
                cur.execute(f"ALTER TABLE {table} ADD COLUMN sync_id TEXT")
                
                # Populate existing rows with a UUID
                cur.execute(f"SELECT id FROM {table} WHERE sync_id IS NULL")
                rows = cur.fetchall()
                for row in rows:
                    sync_id = str(uuid.uuid4())
                    cur.execute(f"UPDATE {table} SET sync_id = ? WHERE id = ?", (sync_id, row[0]))
                
                print(f"  --> Added sync_id to {table}")

            # Add sync_status
            if 'sync_status' not in columns:
                cur.execute(f"ALTER TABLE {table} ADD COLUMN sync_status TEXT DEFAULT 'pending'")
                print(f"  --> Added sync_status to {table}")
                
            # Add last_modified
            if 'last_modified' not in columns:
                cur.execute(f"ALTER TABLE {table} ADD COLUMN last_modified TEXT")
                # Set default timestamp
                cur.execute(f"UPDATE {table} SET last_modified = datetime('now') WHERE last_modified IS NULL")
                print(f"  --> Added last_modified to {table}")
                
            # Add is_deleted
            if 'is_deleted' not in columns:
                cur.execute(f"ALTER TABLE {table} ADD COLUMN is_deleted INTEGER DEFAULT 0")
                print(f"  --> Added is_deleted to {table}")
        
        except Exception as e:
            print(f"  --> Error on table {table}: {e}")
            
    conn.commit()
    conn.close()
    print("\nMigration to Support Sync finished successfully!")

if __name__ == '__main__':
    setup_sync_columns()
