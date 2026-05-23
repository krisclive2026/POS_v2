import sys
import os
import shutil
 
# Ensure terminal output handles UTF-8 characters (e.g. ₹ symbol on Windows)
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
 
from fastapi import FastAPI, HTTPException, Request, UploadFile, File
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import List, Optional
import uuid
from datetime import datetime
from database import init_db, get_db
 
# ─── Pydantic models (defined early so printer functions can reference them) ──
 
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
 
# ─── Printer Setup ────────────────────────────────────────────────────────────
 
# ESC/POS commands (matching the proven working implementation)
ESC_INIT          = b"\x1b@"
ESC_CUT           = b"\x1dV\x00"
ESC_BOLD_ON       = b"\x1bE\x01"
ESC_BOLD_OFF      = b"\x1bE\x00"
ESC_ALIGN_CENTER  = b"\x1ba\x01"
ESC_ALIGN_LEFT    = b"\x1ba\x00"
ESC_ALIGN_RIGHT   = b"\x1ba\x02"
ESC_DOUBLE_HEIGHT = b"\x1b!\x10"   # tall text for store name
ESC_DOUBLE_WIDTH  = b"\x1b!\x20"   # wide text for TOTAL line
ESC_NORMAL_SIZE   = b"\x1b!\x00"
ESC_UNDERLINE_ON  = b"\x1b-\x01"
ESC_UNDERLINE_OFF = b"\x1b-\x00"
ESC_FEED_LINES    = lambda n: bytes([0x1b, 0x64, n])
 
# Receipt width — 80mm paper on RP3200 Lite fits 42 chars at standard font
RECEIPT_WIDTH = 42
 
STORE_NAME = "FreshMarket POS"
 
 
def _write(h, data: bytes):
    """Helper: write raw bytes to a win32print printer handle."""
    import win32print
    win32print.WritePrinter(h, data)
 
 
def _wline(h, text: str):
    """Encode text as UTF-8 + newline and write to printer handle."""
    _write(h, (text + "\n").encode("utf-8", errors="replace"))
 
 
def _find_thermal_printer_win32() -> str:
    """
    Scan all Windows printers and return the best thermal/POS printer name.
    Priority:
      1. Any printer whose name contains thermal/pos/receipt/tsp/rp/xp keywords
      2. Any non-virtual, non-PDF printer as last resort
    Returns empty string if nothing useful found.
    """
    try:
        import win32print
        # EnumPrinters(2) returns all local+network printers
        printers = [p[2] for p in win32print.EnumPrinters(2)]
    except Exception as e:
        print(f"[PRINTER] Could not enumerate printers: {e}")
        return ""
 
    # keywords that strongly suggest a thermal/POS printer
    thermal_keywords = ("thermal", "pos", "receipt", "tsp", "rp", "xp", "80mm", "58mm", "escpos")
    # names that are definitely NOT real printers
    virtual_keywords = ("pdf", "xps", "fax", "onenote", "print to", "microsoft", "adobe")
 
    print(f"[PRINTER] Installed printers: {printers}")
 
    for name in printers:
        lower = name.lower()
        if any(k in lower for k in thermal_keywords):
            print(f"[PRINTER] Matched thermal printer: {name}")
            return name
 
    # fallback: first non-virtual printer
    for name in printers:
        lower = name.lower()
        if not any(k in lower for k in virtual_keywords):
            print(f"[PRINTER] No thermal keyword match; using: {name}")
            return name
 
    print("[PRINTER] All printers appear virtual. Check Windows printer settings.")
    return ""
 
 
def print_thermal_receipt(sale_id: int, cart) -> bool:
    """
    Print a formatted receipt via win32print (Windows spooler / RAW mode).
    Uses the same ESC/POS sequence as the proven BillSoft desktop app:
      - Double-height bold store name (centred)
      - Normal-size date / sale-ID header
      - Item lines: name  qty  unit-price  line-total
      - Separator, tax/total block
      - Double-width bold TOTAL line
      - Feed + full cut
    Returns True on success, False on any failure.
    """
    try:
        import win32print
    except ImportError:
        print("[PRINTER] win32print not available — falling back to serial.")
        return _print_serial_fallback(sale_id, cart)
 
    printer_name = _find_thermal_printer_win32()
    if not printer_name:
        print("[PRINTER] No thermal printer found via win32print — falling back to serial.")
        return _print_serial_fallback(sale_id, cart)
 
    W = RECEIPT_WIDTH
 
    try:
        hPrinter = win32print.OpenPrinter(printer_name)
        try:
            win32print.StartDocPrinter(hPrinter, 1, ("FreshMarket Receipt", None, "RAW"))
            win32print.StartPagePrinter(hPrinter)
 
            # ── Init ──────────────────────────────────────────
            _write(hPrinter, ESC_INIT)
 
            # ── Store name: centred, bold, double-height ──────
            _write(hPrinter, ESC_ALIGN_CENTER + ESC_BOLD_ON + ESC_DOUBLE_HEIGHT)
            _wline(hPrinter, STORE_NAME)
 
            # ── Sub-header: normal size ────────────────────────
            _write(hPrinter, ESC_NORMAL_SIZE + ESC_BOLD_OFF + ESC_ALIGN_CENTER)
            _wline(hPrinter, "=" * W)
            _wline(hPrinter, datetime.now().strftime("%d-%m-%Y  %H:%M:%S"))
            _wline(hPrinter, f"Sale ID: #{sale_id}")
            _wline(hPrinter, "-" * W)
 
            # ── Column header ─────────────────────────────────
            _write(hPrinter, ESC_ALIGN_LEFT + ESC_BOLD_ON)
            _wline(hPrinter, f"{'ITEM':<20} {'QTY':>4} {'PRICE':>7} {'TOTAL':>8}")
            _write(hPrinter, ESC_BOLD_OFF)
            _wline(hPrinter, "-" * W)
 
            # ── Item lines ────────────────────────────────────
            for item in cart.items:
                item_total = item.quantity * item.price
                name = item.name[:20]
                line = f"{name:<20} {item.quantity:>4} {item.price:>7.2f} {item_total:>8.2f}"
                _wline(hPrinter, line)
 
            _wline(hPrinter, "-" * W)
 
            # ── Total block ───────────────────────────────────
            _write(hPrinter, ESC_ALIGN_LEFT)
            _wline(hPrinter, f"{'SUBTOTAL:':<30} {cart.total:>10.2f}")
            _wline(hPrinter, "=" * W)
 
            # TOTAL — double-width bold so it stands out
            _write(hPrinter, ESC_BOLD_ON + ESC_DOUBLE_WIDTH)
            _wline(hPrinter, f"TOTAL: Rs:{cart.total:>8.2f}")
            _write(hPrinter, ESC_NORMAL_SIZE + ESC_BOLD_OFF)
            _wline(hPrinter, "=" * W)
 
            # ── Footer ────────────────────────────────────────
            _write(hPrinter, ESC_ALIGN_CENTER)
            _wline(hPrinter, "")
            _wline(hPrinter, "Thank you for shopping!")
            _wline(hPrinter, "Please come again :)")
            _wline(hPrinter, "")
 
            # ── Feed + cut ────────────────────────────────────
            _write(hPrinter, ESC_FEED_LINES(4) + ESC_CUT)
 
            win32print.EndPagePrinter(hPrinter)
            win32print.EndDocPrinter(hPrinter)
 
        finally:
            win32print.ClosePrinter(hPrinter)
 
        print(f"[PRINTER] Receipt sent to '{printer_name}' via win32print.")
        return True
 
    except Exception as e:
        print(f"[PRINTER] win32print error: {e} — trying serial fallback.")
        return _print_serial_fallback(sale_id, cart)
 
 
def _print_serial_fallback(sale_id: int, cart) -> bool:
    """
    Fallback: send receipt over a serial/COM USB port.
    Used when win32print is unavailable (non-Windows) or fails.
    """
    port = _find_serial_printer()
    if not port:
        print("[PRINTER] No USB printer port found — receipt shown on screen only.")
        return False
    try:
        import serial
        receipt = _build_receipt_text(sale_id, cart)
        with serial.Serial(port, baudrate=9600, timeout=2) as ser:
            ser.write(ESC_INIT)
            ser.write(ESC_ALIGN_LEFT)
            ser.write(ESC_BOLD_ON)
            ser.write(receipt.encode("cp437", errors="replace"))
            ser.write(ESC_BOLD_OFF)
            ser.write(ESC_FEED_LINES(4))
            ser.write(ESC_CUT)
        print(f"[PRINTER] Receipt sent to serial port {port}.")
        return True
    except Exception as e:
        print(f"[PRINTER] Serial fallback failed on {port}: {e}")
        return False
 
 
def _find_serial_printer() -> str | None:
    """Return the first COM port that looks like a thermal printer."""
    try:
        import serial.tools.list_ports
        ports = list(serial.tools.list_ports.comports())
        for p in ports:
            desc = (p.description or "").lower()
            if any(k in desc for k in ("printer", "thermal", "pos", "receipt")):
                return p.device
        for p in ports:
            if "USB" in (p.description or "") or "USB" in (p.hwid or ""):
                return p.device
    except Exception:
        pass
    return None
 
 
def _build_receipt_text(sale_id: int, cart) -> str:
    """Plain-text receipt for the serial fallback path."""
    W = RECEIPT_WIDTH
    lines = [
        "=" * W,
        STORE_NAME.center(W),
        "CUSTOMER RECEIPT".center(W),
        "=" * W,
        f"Date: {datetime.now().strftime('%d-%m-%Y %H:%M:%S')}",
        f"Sale ID: #{sale_id}",
        "-" * W,
        f"{'ITEM':<20} {'QTY':>4} {'PRICE':>7} {'TOTAL':>8}",
        "-" * W,
    ]
    for item in cart.items:
        item_total = item.quantity * item.price
        name = item.name[:20]
        lines.append(f"{name:<20} {item.quantity:>4} {item.price:>7.2f} {item_total:>8.2f}")
    lines += [
        "-" * W,
        f"{'TOTAL:':<30} Rs:{cart.total:>8.2f}",
        "=" * W,
        "Thank you for shopping!".center(W),
        "Please come again :)".center(W),
        "",
    ]
    return "\n".join(lines)
 
app = FastAPI(title="POS PoC")
 
# Initialize DB on startup
init_db()
 
 
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
 
    # Generate plain-text receipt (for logging / web response)
    receipt_text = _build_receipt_text(sale_id, cart)
    print("[CHECKOUT] Sale completed. Receipt:\n" + receipt_text)
    # Send to thermal printer via win32print (falls back to serial if unavailable)
    printed = print_thermal_receipt(sale_id, cart)
 
    return {
        "status": "success",
        "sale_id": sale_id,
        "message": "Receipt printed" if printed else "Receipt ready (printer not detected)",
        "printer_ok": printed,
        "receipt": receipt_text,
        "items": [{"name": i.name, "price": i.price, "quantity": i.quantity} for i in cart.items],
        "total": cart.total
    }
 
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
 
# ─── Bluetooth Receive ───────────────────────────────────────────────────────
 
@app.post("/api/bluetooth-receive")
def open_bluetooth_receive():
    """Launch the Windows Bluetooth File Transfer wizard (fsquirt /receive)."""
    import subprocess
    try:
        subprocess.Popen(["fsquirt.exe", "/receive"])
        return {"status": "success", "message": "Bluetooth receive wizard opened"}
    except FileNotFoundError:
        raise HTTPException(status_code=500, detail="fsquirt.exe not found — is Bluetooth enabled on this PC?")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
 
# ─── Image Upload ────────────────────────────────────────────────────────────
 
ALLOWED_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.webp', '.gif'}
 
@app.post("/api/upload-image")
async def upload_image(file: UploadFile = File(...)):
    ext = os.path.splitext(file.filename or '')[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {ext}")
    # Give it a unique name to avoid collisions
    unique_name = f"{uuid.uuid4().hex}{ext}"
    dest_path = os.path.join(static_dir, 'images', unique_name)
    contents = await file.read()
    with open(dest_path, 'wb') as f:
        f.write(contents)
    return {"status": "success", "image_url": f"/static/images/{unique_name}"}
 
# ─── Entry Point ─────────────────────────────────────────────────────────────
 
if __name__ == "__main__":
    import uvicorn
    import multiprocessing
    multiprocessing.freeze_support()
    print("Starting POS Server at http://localhost:8000")
    uvicorn.run(app, host="0.0.0.0", port=8000)
