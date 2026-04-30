import sqlite3
import os
from contextlib import contextmanager

DB_DIR = os.path.join(os.getcwd(), "data")
DB_PATH = os.path.join(DB_DIR, "pos.db")

def init_db():
    if not os.path.exists(DB_DIR):
        os.makedirs(DB_DIR)
        
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sales (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                total REAL NOT NULL
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sale_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sale_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                quantity INTEGER NOT NULL,
                price REAL NOT NULL,
                FOREIGN KEY (sale_id) REFERENCES sales (id)
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS categories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS inventory (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                price REAL NOT NULL,
                image_url TEXT NOT NULL,
                category TEXT NOT NULL DEFAULT 'General',
                stock INTEGER NOT NULL DEFAULT 999
            )
        """)

        # Add columns if they don't exist yet (for existing databases)
        existing_cols = [row[1] for row in cursor.execute("PRAGMA table_info(inventory)").fetchall()]
        if 'category' not in existing_cols:
            cursor.execute("ALTER TABLE inventory ADD COLUMN category TEXT NOT NULL DEFAULT 'General'")
        if 'stock' not in existing_cols:
            cursor.execute("ALTER TABLE inventory ADD COLUMN stock INTEGER NOT NULL DEFAULT 999")

        # Seed default categories if empty
        cursor.execute("SELECT COUNT(*) FROM categories")
        if cursor.fetchone()[0] == 0:
            default_categories = [("Dairy",), ("Bakery",), ("Produce",), ("Drinks",), ("General",)]
            cursor.executemany("INSERT INTO categories (name) VALUES (?)", default_categories)

        # Populate default mock data if inventory is empty
        cursor.execute("SELECT COUNT(*) FROM inventory")
        if cursor.fetchone()[0] == 0:
            default_items = [
                ("Fresh Milk", 2.99, "/static/images/milk.png", "Dairy", 50),
                ("Whole Wheat Bread", 3.49, "/static/images/bread.png", "Bakery", 30),
                ("Red Apples", 1.99, "/static/images/apples.png", "Produce", 100),
                ("Bananas", 0.99, "/static/images/bananas.png", "Produce", 80),
            ]
            cursor.executemany(
                "INSERT INTO inventory (name, price, image_url, category, stock) VALUES (?, ?, ?, ?, ?)",
                default_items
            )
            
        conn.commit()

@contextmanager
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()
