import sqlite3

DB_FILE = "bot_data.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS testers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            has_tested BOOLEAN NOT NULL DEFAULT 0,
            group_id INTEGER NOT NULL DEFAULT 0,
            last_tested_at DATETIME
        )
    ''')
    # 尝试为旧表添加字段
    try:
        cursor.execute("ALTER TABLE testers ADD COLUMN last_tested_at DATETIME")
    except sqlite3.OperationalError:
        pass # 字段已存在
        
    conn.commit()
    conn.close()

def add_tester(name):
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("INSERT INTO testers (name, has_tested, group_id, last_tested_at) VALUES (?, 0, 0, NULL)", (name,))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()

def remove_tester(name):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM testers WHERE name = ?", (name,))
    deleted = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return deleted

def set_group(name, group_id):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("UPDATE testers SET group_id = ? WHERE name = ?", (group_id, name))
    updated = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return updated

def get_all_testers_with_group():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT name, has_tested, group_id, last_tested_at FROM testers ORDER BY group_id, name")
    results = cursor.fetchall()
    conn.close()
    return results

def get_untested_with_group():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    # 核心：按 last_tested_at 升序排，NULL（从未测过）排在最前
    cursor.execute("SELECT name, group_id, last_tested_at FROM testers WHERE has_tested = 0 ORDER BY last_tested_at ASC")
    results = cursor.fetchall()
    conn.close()
    return results

def get_all_testers():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT name, has_tested FROM testers")
    results = cursor.fetchall()
    conn.close()
    return results

def get_untested():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM testers WHERE has_tested = 0")
    results = [row[0] for row in cursor.fetchall()]
    conn.close()
    return results

def set_tested_status(names, status):
    if not names:
        return
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    placeholders = ",".join(["?"] * len(names))
    if status == 1:
        # 如果标记为已测，更新最后测试时间为当前 UTC 时间
        cursor.execute(f"UPDATE testers SET has_tested = ?, last_tested_at = datetime('now') WHERE name IN ({placeholders})", (status, *names))
    else:
        cursor.execute(f"UPDATE testers SET has_tested = ? WHERE name IN ({placeholders})", (status, *names))
    conn.commit()
    conn.close()

def reset_all_status():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("UPDATE testers SET has_tested = 0")
    conn.commit()
    conn.close()

if __name__ == "__main__":
    init_db()