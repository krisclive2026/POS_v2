import sys
import os
import shutil

# Ensure terminal output handles UTF-8 characters (e.g. ₹ symbol on Windows)
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from fastapi import FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime
from app.database import init_db, get_db

app = FastAPI(title="POS PoC")

# Initialize DB on startup
init_db()

# Pydantic models
class Item(BaseModel):
    name: str
    price: float
    quantity: int

class Cart(BaseModel):
    items: List[Item]
    total: float

class InventoryItem(BaseModel):
    name: str
    price: float
    image_url: str
    category: Optional[str] = "General"
    stock: Optional[int] = 999

class CategoryCreate(BaseModel):
    name: str

class ClaimImageRequest(BaseModel):
    filename: str

if getattr(sys, 'frozen', False):
    base_path = sys._MEIPASS
else:
    base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

static_dir = os.path.join(base_path, 'app', 'static')
bluetooth_inbox_dir = os.path.join(os.path.dirname(base_path), 'data', 'bluetooth_inbox') if getattr(sys, 'frozen', False) else os.path.join(base_path, 'data', 'bluetooth_inbox')
os.makedirs(bluetooth_inbox_dir, exist_ok=True)
os.makedirs(os.path.join(static_dir, 'images'), exist_ok=True)

# Serve static files
app.mount("/static", StaticFiles(directory=static_dir), name="static")

# Middleware to ensure JS/CSS files are served with UTF-8 charset
@app.middleware("http")
async def add_utf8_charset(request: Request, call_next):
    response = await call_next(request)
    if request.url.path.endswith('.js'):
        response.headers['Content-Type'] = 'application/javascript; charset=utf-8'
    elif request.url.path.endswith('.css'):
        response.headers['Content-Type'] = 'text/css; charset=utf-8'
    return response

@app.get("/")
def read_root():
    return FileResponse(os.path.join(static_dir, "index.html"))

# ─── Checkout ────────────────────────────────────────────────────────────────

@app.post("/api/checkout")
def checkout(cart: Cart):
    if not cart.items:
        raise HTTPException(status_code=400, detail="Cart is empty")

    with get_db() as db:
        cursor = db.cursor()

        # Check and decrement stock
        for item in cart.items:
            row = cursor.execute(
                "SELECT stock FROM inventory WHERE name = ?", (item.name,)
            ).fetchone()
            if row and row['stock'] != 999:  # 999 = unlimited
                if row['stock'] < item.quantity:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Insufficient stock for {item.name}. Available: {row['stock']}"
                    )
                cursor.execute(
                    "UPDATE inventory SET stock = stock - ? WHERE name = ?",
                    (item.quantity, item.name)
                )

        cursor.execute("INSERT INTO sales (total) VALUES (?)", (cart.total,))
        sale_id = cursor.lastrowid
        
        for item in cart.items:
            cursor.execute(
                "INSERT INTO sale_items (sale_id, name, quantity, price) VALUES (?, ?, ?, ?)",
                (sale_id, item.name, item.quantity, item.price)
            )
        db.commit()

    # Print receipt
    print("\n" + "="*30)
    print("=== CUSTOMER RECEIPT ===")
    print("="*30)
    print(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("Sale ID: #" + str(sale_id))
    print("-" * 30)
    for item in cart.items:
        print(f"{item.name[:15]:<15} {item.quantity}x @ \u20b9{item.price:.2f}")
        print(f"{'':<15}     \u20b9{(item.quantity * item.price):.2f}")
    print("-" * 30)
    print(f"TOTAL:           \u20b9{cart.total:.2f}")
    print("="*30 + "\n")

    return {"status": "success", "sale_id": sale_id, "message": "Receipts printed"}

# ─── Sales ───────────────────────────────────────────────────────────────────

@app.get("/api/sales")
def get_sales():
    with get_db() as db:
        cursor = db.cursor()
        cursor.execute("SELECT * FROM sales ORDER BY timestamp DESC")
        sales = [dict(row) for row in cursor.fetchall()]
    return {"sales": sales}

@app.get("/api/sales/detailed")
def get_sales_detailed():
    with get_db() as db:
        cursor = db.cursor()
        cursor.execute("SELECT * FROM sales ORDER BY timestamp DESC")
        sales = [dict(row) for row in cursor.fetchall()]
        for sale in sales:
            cursor.execute(
                "SELECT * FROM sale_items WHERE sale_id = ?", (sale['id'],)
            )
            sale['items'] = [dict(row) for row in cursor.fetchall()]
    return {"sales": sales}

# ─── Inventory ───────────────────────────────────────────────────────────────

@app.get("/api/inventory")
def get_inventory():
    with get_db() as db:
        cursor = db.cursor()
        cursor.execute("SELECT * FROM inventory")
        inventory = [dict(row) for row in cursor.fetchall()]
    return {"inventory": inventory}

@app.post("/api/inventory")
def add_inventory(item: InventoryItem):
    with get_db() as db:
        cursor = db.cursor()
        cursor.execute(
            "INSERT INTO inventory (name, price, image_url, category, stock) VALUES (?, ?, ?, ?, ?)",
            (item.name, item.price, item.image_url, item.category, item.stock)
        )
        db.commit()
    return {"status": "success", "message": "Item added to inventory"}

@app.put("/api/inventory/{item_id}")
def update_inventory(item_id: int, item: InventoryItem):
    with get_db() as db:
        cursor = db.cursor()
        cursor.execute(
            "UPDATE inventory SET name=?, price=?, image_url=?, category=?, stock=? WHERE id=?",
            (item.name, item.price, item.image_url, item.category, item.stock, item_id)
        )
        db.commit()
    return {"status": "success", "message": "Item updated"}

@app.delete("/api/inventory/{item_id}")
def delete_inventory(item_id: int):
    with get_db() as db:
        cursor = db.cursor()
        cursor.execute("DELETE FROM inventory WHERE id = ?", (item_id,))
        db.commit()
    return {"status": "success", "message": "Item deleted from inventory"}

# ─── Categories ──────────────────────────────────────────────────────────────

@app.get("/api/categories")
def get_categories():
    with get_db() as db:
        cursor = db.cursor()
        cursor.execute("SELECT * FROM categories ORDER BY name")
        categories = [dict(row) for row in cursor.fetchall()]
    return {"categories": categories}

@app.post("/api/categories")
def add_category(cat: CategoryCreate):
    try:
        with get_db() as db:
            cursor = db.cursor()
            cursor.execute("INSERT INTO categories (name) VALUES (?)", (cat.name,))
            db.commit()
        return {"status": "success", "message": "Category added"}
    except Exception:
        raise HTTPException(status_code=400, detail="Category already exists")

@app.put("/api/categories/{cat_id}")
def update_category(cat_id: int, cat: CategoryCreate):
    with get_db() as db:
        cursor = db.cursor()
        cursor.execute("UPDATE categories SET name=? WHERE id=?", (cat.name, cat_id))
        db.commit()
    return {"status": "success", "message": "Category updated"}

@app.delete("/api/categories/{cat_id}")
def delete_category(cat_id: int):
    with get_db() as db:
        cursor = db.cursor()
        # Move items in this category to General
        cursor.execute(
            "UPDATE inventory SET category='General' WHERE category=(SELECT name FROM categories WHERE id=?)",
            (cat_id,)
        )
        cursor.execute("DELETE FROM categories WHERE id = ?", (cat_id,))
        db.commit()
    return {"status": "success", "message": "Category deleted"}

# ─── Bluetooth ───────────────────────────────────────────────────────────────

@app.get("/api/bluetooth-images")
def get_bluetooth_images():
    images = []
    if os.path.exists(bluetooth_inbox_dir):
        for file in os.listdir(bluetooth_inbox_dir):
            if file.lower().endswith(('.png', '.jpg', '.jpeg', '.webp', '.gif')):
                images.append(file)
    images.sort(key=lambda x: os.path.getmtime(os.path.join(bluetooth_inbox_dir, x)), reverse=True)
    return {"images": images}

@app.post("/api/bluetooth-images/claim")
def claim_bluetooth_image(req: ClaimImageRequest):
    src_path = os.path.join(bluetooth_inbox_dir, req.filename)
    if not os.path.exists(src_path):
        raise HTTPException(status_code=404, detail="Image not found in inbox")
    
    dest_path = os.path.join(static_dir, 'images', req.filename)
    base, ext = os.path.splitext(req.filename)
    counter = 1
    while os.path.exists(dest_path):
        new_filename = f"{base}_{counter}{ext}"
        dest_path = os.path.join(static_dir, 'images', new_filename)
        req.filename = new_filename
        counter += 1
        
    shutil.move(src_path, dest_path)
    return {"status": "success", "image_url": f"/static/images/{req.filename}"}

# ─── Entry Point ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    import multiprocessing
    multiprocessing.freeze_support()
    print("Starting POS Server at http://localhost:8000")
    uvicorn.run(app, host="0.0.0.0", port=8000)
