let cart = [];
let inventory = [];
let categories = [];
let activeCategory = 'All';
let searchTerm = '';
let editingItemId = null;

// ─── Init ─────────────────────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', () => {
    // Tab switching
    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
            document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
            btn.classList.add('active');
            const tab = btn.dataset.tab;
            document.getElementById(tab).classList.add('active');
            if (tab === 'history') loadSalesHistory();
        });
    });

    // Cart
    document.getElementById('btnClear').addEventListener('click', clearCart);
    document.getElementById('btnCheckout').addEventListener('click', checkout);

    // Search
    document.getElementById('searchInput').addEventListener('input', e => {
        searchTerm = e.target.value.toLowerCase();
        renderProductsGrid();
    });

    // Inventory form
    document.getElementById('addInventoryForm').addEventListener('submit', handleInventorySubmit);
    document.getElementById('invCancelBtn').addEventListener('click', resetInventoryForm);

    // Category management
    document.getElementById('btnAddCategory').addEventListener('click', addCategory);

    // Bluetooth
    document.getElementById('btnBluetoothPicker').addEventListener('click', openBluetoothModal);
    document.getElementById('closeBluetoothModalBtn').addEventListener('click', () =>
        document.getElementById('bluetoothModal').classList.add('hidden'));

    // Receipt modal
    document.getElementById('closeModalBtn').addEventListener('click', () =>
        document.getElementById('receiptModal').classList.add('hidden'));
    document.getElementById('printModalBtn').addEventListener('click', () => window.print());

    // MISC quick entry
    document.getElementById('miscToggle').addEventListener('click', () => {
        const form = document.getElementById('miscForm');
        const chevron = document.getElementById('miscChevron');
        form.classList.toggle('hidden');
        chevron.textContent = form.classList.contains('hidden') ? '▶' : '▼';
    });
    document.getElementById('btnAddMisc').addEventListener('click', addMiscItem);

    // History refresh
    document.getElementById('btnRefreshHistory').addEventListener('click', loadSalesHistory);

    // Initial data load
    loadCategories().then(() => loadInventory());
});

// ─── Categories ───────────────────────────────────────────────────────────────

async function loadCategories() {
    try {
        const res = await fetch('/api/categories');
        const data = await res.json();
        categories = data.categories;
        renderCategoryDropdown();
        renderCategoryManager();
    } catch (e) {
        console.error('Error loading categories:', e);
    }
}

function renderCategoryDropdown() {
    const sel = document.getElementById('invCategory');
    const current = sel.value;
    sel.innerHTML = '';
    categories.forEach(cat => {
        const opt = document.createElement('option');
        opt.value = cat.name;
        opt.textContent = cat.name;
        if (cat.name === current) opt.selected = true;
        sel.appendChild(opt);
    });
}

function renderCategoryManager() {
    const list = document.getElementById('categoryList');
    list.innerHTML = '';
    categories.forEach(cat => {
        const li = document.createElement('li');
        li.className = 'cat-item';
        li.innerHTML = `
            <span class="cat-name" id="catLabel-${cat.id}">${cat.name}</span>
            <div class="cat-actions">
                <button class="cat-edit-btn" onclick="startEditCategory(${cat.id}, '${cat.name.replace(/'/g, "\\'")}')">✏️</button>
                <button class="cat-delete-btn" onclick="deleteCategory(${cat.id})">🗑️</button>
            </div>
        `;
        list.appendChild(li);
    });
}

async function addCategory() {
    const input = document.getElementById('newCategoryName');
    const name = input.value.trim();
    if (!name) return;
    try {
        const res = await fetch('/api/categories', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name })
        });
        if (res.ok) {
            input.value = '';
            await loadCategories();
            await loadInventory();
        } else {
            alert('Category already exists.');
        }
    } catch (e) { console.error(e); }
}

function startEditCategory(id, currentName) {
    const li = document.getElementById(`catLabel-${id}`).parentElement.parentElement;
    li.innerHTML = `
        <input type="text" class="cat-edit-input" value="${currentName}" id="catEditInput-${id}">
        <div class="cat-actions">
            <button class="cat-save-btn" onclick="saveCategory(${id})">✔️</button>
            <button class="cat-cancel-btn" onclick="renderCategoryManager()">✖️</button>
        </div>
    `;
}

async function saveCategory(id) {
    const input = document.getElementById(`catEditInput-${id}`);
    const name = input.value.trim();
    if (!name) return;
    try {
        const res = await fetch(`/api/categories/${id}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name })
        });
        if (res.ok) {
            await loadCategories();
            await loadInventory();
        }
    } catch (e) { console.error(e); }
}

async function deleteCategory(id) {
    const li = document.getElementById(`catLabel-${id}`);
    const name = li ? li.textContent : '';
    // Inline confirm
    const confirmDiv = document.createElement('span');
    confirmDiv.innerHTML = ` Delete "<b>${name}</b>"? <button onclick="confirmDeleteCategory(${id})">Yes</button> <button onclick="renderCategoryManager()">No</button>`;
    li.parentElement.parentElement.appendChild(confirmDiv);
    li.parentElement.parentElement.querySelector('.cat-actions').style.display = 'none';
}

async function confirmDeleteCategory(id) {
    try {
        const res = await fetch(`/api/categories/${id}`, { method: 'DELETE' });
        if (res.ok) { await loadCategories(); await loadInventory(); }
    } catch (e) { console.error(e); }
}

// ─── Inventory ────────────────────────────────────────────────────────────────

async function loadInventory() {
    try {
        const res = await fetch('/api/inventory');
        const data = await res.json();
        inventory = data.inventory;
        renderCategoryPills();
        renderProductsGrid();
        renderInventoryList();
    } catch (e) { console.error('Error loading inventory:', e); }
}

function renderCategoryPills() {
    const container = document.getElementById('categoryPills');
    const unique = ['All', ...new Set(inventory.map(i => i.category).filter(Boolean))];
    container.innerHTML = '';
    unique.forEach(cat => {
        const btn = document.createElement('button');
        btn.className = 'pill' + (cat === activeCategory ? ' active' : '');
        btn.dataset.category = cat;
        btn.textContent = cat;
        btn.addEventListener('click', () => {
            activeCategory = cat;
            container.querySelectorAll('.pill').forEach(p => p.classList.remove('active'));
            btn.classList.add('active');
            renderProductsGrid();
        });
        container.appendChild(btn);
    });
}

function renderProductsGrid() {
    const grid = document.getElementById('productsGrid');
    grid.innerHTML = '';

    const filtered = inventory.filter(item => {
        const matchCat = activeCategory === 'All' || item.category === activeCategory;
        const matchSearch = item.name.toLowerCase().includes(searchTerm);
        return matchCat && matchSearch;
    });

    if (filtered.length === 0) {
        grid.innerHTML = '<p class="no-results">No items found.</p>';
        return;
    }

    filtered.forEach(item => {
        const outOfStock = item.stock !== 999 && item.stock <= 0;
        const lowStock = item.stock !== 999 && item.stock > 0 && item.stock < 10;
        const card = document.createElement('div');
        card.className = 'product-card' + (outOfStock ? ' out-of-stock' : '');
        card.innerHTML = `
            <div class="card-badge-area">
                ${lowStock ? `<span class="stock-badge low">⚠️ ${item.stock} left</span>` : ''}
                ${outOfStock ? `<span class="stock-badge out">Out of Stock</span>` : ''}
            </div>
            <img src="${item.image_url}" alt="${item.name}" class="product-img" onerror="this.src='/static/logo.png'">
            <div class="product-info">
                <span class="product-category">${item.category || ''}</span>
                <h3>${item.name}</h3>
                <div class="product-price">₹${item.price.toFixed(2)}</div>
            </div>
        `;
        if (!outOfStock) card.addEventListener('click', () => addToCart(item));
        grid.appendChild(card);
    });
}

function renderInventoryList() {
    const list = document.getElementById('inventoryList');
    list.innerHTML = '';
    inventory.forEach(item => {
        const tr = document.createElement('tr');
        const stockDisplay = item.stock === 999 ? '∞' : item.stock;
        const stockClass = item.stock !== 999 && item.stock < 10 ? 'stock-low' : '';
        tr.innerHTML = `
            <td><img src="${item.image_url}" alt="${item.name}" onerror="this.src='/static/logo.png'"></td>
            <td>${item.name}</td>
            <td><span class="category-tag">${item.category || 'General'}</span></td>
            <td>₹${item.price.toFixed(2)}</td>
            <td class="${stockClass}">${stockDisplay}</td>
            <td class="action-cell">
                <button class="edit-btn">Edit</button>
                <button class="delete-btn">Delete</button>
                <span class="confirm-delete hidden">
                    Sure? 
                    <button class="confirm-yes-btn">Yes</button>
                    <button class="confirm-no-btn">No</button>
                </span>
            </td>
        `;
        tr.querySelector('.edit-btn').addEventListener('click', () => startEditItem(item));
        const deleteBtn = tr.querySelector('.delete-btn');
        const confirmSpan = tr.querySelector('.confirm-delete');
        const yesBtn = tr.querySelector('.confirm-yes-btn');
        const noBtn = tr.querySelector('.confirm-no-btn');
        deleteBtn.addEventListener('click', () => {
            deleteBtn.classList.add('hidden');
            confirmSpan.classList.remove('hidden');
        });
        noBtn.addEventListener('click', () => {
            deleteBtn.classList.remove('hidden');
            confirmSpan.classList.add('hidden');
        });
        yesBtn.addEventListener('click', () => deleteInventoryItem(item.id));
        list.appendChild(tr);
    });
}

function startEditItem(item) {
    editingItemId = item.id;
    document.getElementById('inventoryFormTitle').textContent = 'Edit Item';
    document.getElementById('invSubmitBtn').textContent = 'Save Changes';
    document.getElementById('invCancelBtn').classList.remove('hidden');
    document.getElementById('editItemId').value = item.id;
    document.getElementById('invName').value = item.name;
    document.getElementById('invPrice').value = item.price;
    document.getElementById('invCategory').value = item.category;
    document.getElementById('invStock').value = item.stock;
    document.getElementById('invImage').value = item.image_url;
    // Scroll to form
    document.querySelector('.inventory-card').scrollIntoView({ behavior: 'smooth' });
    // Switch to inventory tab if not already there
    document.querySelector('[data-tab="inventory"]').click();
}

function resetInventoryForm() {
    editingItemId = null;
    document.getElementById('inventoryFormTitle').textContent = 'Add New Item';
    document.getElementById('invSubmitBtn').textContent = 'Add to Inventory';
    document.getElementById('invCancelBtn').classList.add('hidden');
    document.getElementById('addInventoryForm').reset();
    document.getElementById('invStock').value = 999;
}

async function handleInventorySubmit(e) {
    e.preventDefault();
    const payload = {
        name: document.getElementById('invName').value,
        price: parseFloat(document.getElementById('invPrice').value),
        category: document.getElementById('invCategory').value,
        stock: parseInt(document.getElementById('invStock').value),
        image_url: document.getElementById('invImage').value,
    };
    try {
        const method = editingItemId ? 'PUT' : 'POST';
        const url = editingItemId ? `/api/inventory/${editingItemId}` : '/api/inventory';
        const res = await fetch(url, {
            method,
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        if (res.ok) {
            resetInventoryForm();
            loadInventory();
        } else {
            alert('Failed to save item.');
        }
    } catch (e) { console.error(e); }
}

async function deleteInventoryItem(id) {
    try {
        const res = await fetch(`/api/inventory/${id}`, { method: 'DELETE' });
        if (res.ok) loadInventory();
        else alert('Failed to delete item.');
    } catch (e) { console.error(e); }
}

// ─── Cart ─────────────────────────────────────────────────────────────────────

function addToCart(product) {
    const existing = cart.find(i => i.id === product.id);
    if (existing) {
        // Check stock limit
        if (product.stock !== 999 && existing.quantity >= product.stock) {
            alert(`Only ${product.stock} units available.`);
            return;
        }
        existing.quantity += 1;
    } else {
        cart.push({ ...product, quantity: 1 });
    }
    updateCartUI();
}

function addMiscItem() {
    const nameEl = document.getElementById('miscName');
    const priceEl = document.getElementById('miscPrice');
    const qtyEl = document.getElementById('miscQty');
    const name = nameEl.value.trim();
    const price = parseFloat(priceEl.value);
    const qty = parseInt(qtyEl.value) || 1;

    if (!name) { alert('Please enter an item name.'); return; }
    if (isNaN(price) || price <= 0) { alert('Please enter a valid price.'); return; }

    // Use a unique negative ID so it doesn't collide with real inventory
    const miscId = 'misc_' + Date.now();
    cart.push({
        id: miscId,
        name: name,
        price: price,
        quantity: qty,
        category: 'MISC',
        stock: 999,
        image_url: ''
    });
    updateCartUI();

    // Reset form
    nameEl.value = '';
    priceEl.value = '';
    qtyEl.value = '1';
}

function updateQuantity(index, delta) {
    cart[index].quantity += delta;
    if (cart[index].quantity <= 0) cart.splice(index, 1);
    updateCartUI();
}

function clearCart() { cart = []; updateCartUI(); }

function updateCartUI() {
    const cartItemsDiv = document.getElementById('cartItems');
    cartItemsDiv.innerHTML = '';
    if (cart.length === 0) {
        cartItemsDiv.innerHTML = '<div class="empty-cart-msg">Your cart is empty</div>';
        document.getElementById('cartTotal').textContent = '₹0.00';
        return;
    }
    let total = 0;
    cart.forEach((item, index) => {
        total += item.price * item.quantity;
        const div = document.createElement('div');
        div.className = 'cart-item';
        div.innerHTML = `
            <div class="cart-item-details">
                <span class="cart-item-title">${item.name}</span>
                <span class="cart-item-price">₹${item.price.toFixed(2)} each</span>
            </div>
            <div class="cart-item-controls">
                <button class="qty-btn" onclick="updateQuantity(${index}, -1)">-</button>
                <span class="cart-item-qty">${item.quantity}</span>
                <button class="qty-btn" onclick="updateQuantity(${index}, 1)">+</button>
            </div>
        `;
        cartItemsDiv.appendChild(div);
    });
    document.getElementById('cartTotal').textContent = `₹${total.toFixed(2)}`;
}

// ─── Checkout ─────────────────────────────────────────────────────────────────

async function checkout() {
    if (cart.length === 0) { alert('Cart is empty!'); return; }
    const total = cart.reduce((s, i) => s + i.price * i.quantity, 0);
    const payload = {
        items: cart.map(i => ({ name: i.name, price: i.price, quantity: i.quantity })),
        total
    };
    try {
        const res = await fetch('/api/checkout', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        if (res.ok) {
            const result = await res.json();
            showReceiptModal(result.sale_id, payload);
            clearCart();
            loadInventory(); // refresh stock
        } else {
            const err = await res.json();
            alert(err.detail || 'Checkout failed');
        }
    } catch (e) { console.error(e); alert('An error occurred during checkout'); }
}

function showReceiptModal(saleId, payload) {
    document.getElementById('receiptId').textContent = 'Sale ID: #' + saleId;
    document.getElementById('receiptDate').textContent = new Date().toLocaleString();
    const list = document.getElementById('receiptItems');
    list.innerHTML = '';
    payload.items.forEach(item => {
        const row = document.createElement('div');
        row.className = 'receipt-item-row';
        row.innerHTML = `<span>${item.name} (x${item.quantity})</span><span>₹${(item.price * item.quantity).toFixed(2)}</span>`;
        list.appendChild(row);
    });
    document.getElementById('receiptTotalAmount').textContent = `₹${payload.total.toFixed(2)}`;
    document.getElementById('receiptModal').classList.remove('hidden');
}

// ─── Sales History ────────────────────────────────────────────────────────────

async function loadSalesHistory() {
    try {
        const res = await fetch('/api/sales/detailed');
        const data = await res.json();
        renderSalesHistory(data.sales);
    } catch (e) { console.error('Error loading sales history:', e); }
}

function renderSalesHistory(sales) {
    const tbody = document.getElementById('historyList');
    tbody.innerHTML = '';
    if (sales.length === 0) {
        tbody.innerHTML = '<tr><td colspan="5" style="text-align:center;color:var(--text-muted)">No sales recorded yet.</td></tr>';
        return;
    }
    sales.forEach(sale => {
        const itemCount = sale.items.reduce((s, i) => s + i.quantity, 0);
        const tr = document.createElement('tr');
        tr.innerHTML = `
            <td>#${sale.id}</td>
            <td>${new Date(sale.timestamp + 'Z').toLocaleString()}</td>
            <td>${itemCount} item(s)</td>
            <td>₹${sale.total.toFixed(2)}</td>
            <td><button class="detail-btn" data-id="${sale.id}">▶ Show</button></td>
        `;
        tbody.appendChild(tr);

        // Detail row (hidden by default)
        const detailRow = document.createElement('tr');
        detailRow.className = 'detail-row hidden';
        detailRow.id = `detail-${sale.id}`;
        detailRow.innerHTML = `
            <td colspan="5">
                <table class="detail-table">
                    <thead><tr><th>Item</th><th>Qty</th><th>Price</th><th>Subtotal</th></tr></thead>
                    <tbody>
                        ${sale.items.map(i => `
                            <tr>
                                <td>${i.name}</td>
                                <td>${i.quantity}</td>
                                <td>₹${i.price.toFixed(2)}</td>
                                <td>₹${(i.price * i.quantity).toFixed(2)}</td>
                            </tr>
                        `).join('')}
                    </tbody>
                </table>
            </td>
        `;
        tbody.appendChild(detailRow);

        tr.querySelector('.detail-btn').addEventListener('click', () => {
            const isHidden = detailRow.classList.contains('hidden');
            detailRow.classList.toggle('hidden', !isHidden);
            tr.querySelector('.detail-btn').textContent = isHidden ? '▼ Hide' : '▶ Show';
        });
    });
}

// ─── Bluetooth ────────────────────────────────────────────────────────────────

async function openBluetoothModal() {
    const grid = document.getElementById('bluetoothImagesGrid');
    grid.innerHTML = '<p>Loading...</p>';
    document.getElementById('bluetoothModal').classList.remove('hidden');
    try {
        const res = await fetch('/api/bluetooth-images');
        const data = await res.json();
        if (!data.images || data.images.length === 0) {
            grid.innerHTML = '<p style="color:var(--text-muted)">No images in Bluetooth inbox.</p>';
            return;
        }
        grid.innerHTML = '';
        data.images.forEach(filename => {
            const item = document.createElement('div');
            item.className = 'bluetooth-item';
            item.innerHTML = `
                <div style="height:100px;display:flex;align-items:center;justify-content:center;background:#ddd;font-size:2rem;">📱</div>
                <div class="bluetooth-filename">${filename}</div>
            `;
            item.addEventListener('click', () => claimBluetoothImage(filename));
            grid.appendChild(item);
        });
    } catch (e) {
        grid.innerHTML = '<p style="color:var(--danger)">Failed to load images.</p>';
    }
}

async function claimBluetoothImage(filename) {
    try {
        const res = await fetch('/api/bluetooth-images/claim', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ filename })
        });
        if (res.ok) {
            const data = await res.json();
            document.getElementById('invImage').value = data.image_url;
            document.getElementById('bluetoothModal').classList.add('hidden');
        } else { alert('Failed to claim image.'); }
    } catch (e) { console.error(e); }
}
