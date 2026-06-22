import sqlite3
import os
import shutil

db_path = os.path.join(os.path.dirname(__file__), 'backend', 'data.db')
backup_path = os.path.join(os.path.dirname(__file__), 'backend', 'data_backup.db')

print(f"DB path: {db_path}")
print(f"DB exists: {os.path.exists(db_path)}")
print(f"DB size: {os.path.getsize(db_path)} bytes")

shutil.copy2(db_path, backup_path)
print(f"Backup created: {backup_path}")

conn = sqlite3.connect(db_path)
print("\nIntegrity check...")
result = conn.execute('PRAGMA integrity_check').fetchall()
for r in result:
    print(f"  {r}")

print("\nTrying to read page_elements...")
try:
    count = conn.execute('SELECT COUNT(*) FROM page_elements').fetchone()[0]
    print(f"  Elements count: {count}")
except Exception as e:
    print(f"  Error: {e}")

print("\nTrying to update...")
try:
    conn.execute("UPDATE page_elements SET translated_content = 'test' WHERE id = 1080")
    conn.rollback()
    print("  Update test OK (rolled back)")
except Exception as e:
    print(f"  Error: {e}")

conn.close()

print("\nAttempting recovery via dump...")
os.system(f"cd {os.path.dirname(db_path)} && sqlite3 data.db .dump > data_dump.sql 2>&1")
os.system(f"cd {os.path.dirname(db_path)} && mv data.db data_old.db && sqlite3 data.db < data_dump.sql 2>&1")

conn2 = sqlite3.connect(db_path)
result2 = conn2.execute('PRAGMA integrity_check').fetchone()
print(f"New DB integrity: {result2}")
try:
    count2 = conn2.execute('SELECT COUNT(*) FROM page_elements').fetchone()[0]
    print(f"New DB elements count: {count2}")
except Exception as e:
    print(f"Error reading new DB: {e}")
conn2.close()

print("Done!")
