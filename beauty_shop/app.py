from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
import sqlite3, os, hashlib, secrets
from werkzeug.utils import secure_filename
from datetime import datetime
from functools import wraps

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'beauty_shop_default_secret_7722')
UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), 'static', 'uploads')
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
DB_PATH = os.path.join(os.path.dirname(__file__), 'shop.db')

# ── helpers ──────────────────────────────────────────────────────────────────

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def hash_password(pw): return hashlib.sha256(pw.encode()).hexdigest()

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            flash('يجب تسجيل الدخول أولاً', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('is_admin'):
            flash('غير مصرح لك بالدخول', 'danger')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated

def cart_count():
    if 'user_id' in session:
        db = get_db()
        r = db.execute('SELECT SUM(quantity) FROM cart WHERE user_id=?', (session['user_id'],)).fetchone()
        db.close()
        return r[0] or 0
    return session.get('cart_count', 0)

@app.context_processor
def inject_globals():
    return dict(cart_count=cart_count(), current_year=datetime.now().year)

# ── init db ───────────────────────────────────────────────────────────────────

def init_db():
    db = get_db()
    db.executescript('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            phone TEXT,
            address TEXT,
            is_admin INTEGER DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            name_ar TEXT NOT NULL,
            icon TEXT DEFAULT '🛍️'
        );
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT,
            price REAL NOT NULL,
            old_price REAL,
            category_id INTEGER,
            image TEXT DEFAULT 'default.jpg',
            stock INTEGER DEFAULT 0,
            is_featured INTEGER DEFAULT 0,
            is_new INTEGER DEFAULT 1,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (category_id) REFERENCES categories(id)
        );
        CREATE TABLE IF NOT EXISTS cart (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            product_id INTEGER,
            quantity INTEGER DEFAULT 1,
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (product_id) REFERENCES products(id)
        );
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            total REAL,
            status TEXT DEFAULT 'pending',
            address TEXT,
            phone TEXT,
            notes TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        );
        CREATE TABLE IF NOT EXISTS order_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER,
            product_id INTEGER,
            quantity INTEGER,
            price REAL,
            FOREIGN KEY (order_id) REFERENCES orders(id),
            FOREIGN KEY (product_id) REFERENCES products(id)
        );
        CREATE TABLE IF NOT EXISTS wishlist (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            product_id INTEGER,
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (product_id) REFERENCES products(id)
        );
    ''')
    # Seed categories
    cats = db.execute('SELECT COUNT(*) FROM categories').fetchone()[0]
    if cats == 0:
        db.executemany('INSERT INTO categories (name, name_ar, icon) VALUES (?,?,?)', [
            ('cosmetics', 'مستحضرات التجميل', '💄'),
            ('bags',      'الشنط والحقائب',   '👜'),
            ('skincare',  'العناية بالبشرة',   '✨'),
            ('perfumes',  'العطور',            '🌸'),
        ])
        # Admin
        db.execute('''INSERT OR IGNORE INTO users (name,email,password,is_admin)
                      VALUES (?,?,?,1)''',
                   ('kareem', 'kareem@beauty.com', hash_password('01227418106')))
        # Sample products
        db.executemany('''INSERT INTO products
            (name,description,price,old_price,category_id,stock,is_featured,is_new)
            VALUES (?,?,?,?,?,?,?,?)''', [
            ('أحمر شفاه روزي', 'أحمر شفاه فاخر يدوم طويلاً بألوان رائعة', 89, 120, 1, 50, 1, 1),
            ('فاونديشن ناعم', 'كريم أساس خفيف التركيبة تغطية كاملة', 150, 200, 1, 30, 1, 1),
            ('باليت ظلال عيون', 'باليت 18 لون من أجمل الدرجات', 199, 280, 1, 25, 1, 0),
            ('ماسكارا فولوم', 'ماسكارا تضفي حجم وكثافة مذهلة للرموش', 75, 100, 1, 40, 0, 1),
            ('كريم مرطب مكثف', 'مرطب للبشرة الجافة والمختلطة برائحة خفيفة', 120, None, 3, 60, 1, 1),
            ('سيروم فيتامين سي', 'سيروم مضيء للبشرة يقلل البقع الداكنة', 180, 250, 3, 20, 1, 1),
            ('شنطة جلد كبيرة', 'حقيبة يد أنيقة من الجلد الإيطالي الفاخر', 650, 900, 2, 15, 1, 1),
            ('كلتش سهرة ذهبي', 'كلتش صغير مناسب لحفلات السهرة والمناسبات', 320, None, 2, 20, 1, 0),
            ('حقيبة كروس بودي', 'حقيبة عملية للاستخدام اليومي - عدة ألوان', 420, 550, 2, 18, 0, 1),
            ('شنطة ظهر أنيقة', 'باك باك بتصميم عصري مناسب للشغل والإطلالات اليومية', 380, 480, 2, 22, 1, 1),
            ('عطر رود باريس', 'عطر فرنسي فاخر برائحة زهرية مميزة يدوم 12 ساعة', 450, 600, 4, 30, 1, 1),
            ('عطر لالي', 'عطر شرقي فاخر يجمع بين العود والورد', 380, None, 4, 25, 0, 1),
        ])
        db.commit()
    db.close()

# ── PUBLIC ROUTES ─────────────────────────────────────────────────────────────

@app.route('/')
def index():
    db = get_db()
    featured = db.execute('''SELECT p.*, c.name_ar as cat_name 
                              FROM products p JOIN categories c ON p.category_id=c.id
                              WHERE p.is_featured=1 LIMIT 8''').fetchall()
    new_products = db.execute('''SELECT p.*, c.name_ar as cat_name 
                                 FROM products p JOIN categories c ON p.category_id=c.id
                                 WHERE p.is_new=1 LIMIT 4''').fetchall()
    categories = db.execute('SELECT * FROM categories').fetchall()
    db.close()
    return render_template('index.html', featured=featured, new_products=new_products, categories=categories)

@app.route('/shop')
def shop():
    db = get_db()
    cat_id   = request.args.get('category', '')
    search   = request.args.get('search', '').strip()
    sort     = request.args.get('sort', 'newest')
    page     = int(request.args.get('page', 1))
    per_page = 9
    offset   = (page - 1) * per_page

    query  = 'SELECT p.*, c.name_ar as cat_name FROM products p JOIN categories c ON p.category_id=c.id WHERE 1=1'
    params = []
    if cat_id:
        query += ' AND p.category_id=?'; params.append(cat_id)
    if search:
        query += ' AND (p.name LIKE ? OR p.description LIKE ?)'; params += [f'%{search}%', f'%{search}%']

    order_map = {'newest':'p.id DESC','price_asc':'p.price ASC','price_desc':'p.price DESC','name':'p.name ASC'}
    query += f' ORDER BY {order_map.get(sort,"p.id DESC")}'

    total   = db.execute(query.replace('SELECT p.*, c.name_ar as cat_name', 'SELECT COUNT(*)', 1), params).fetchone()[0]
    products = db.execute(query + f' LIMIT {per_page} OFFSET {offset}', params).fetchall()
    categories = db.execute('SELECT * FROM categories').fetchall()
    total_pages = (total + per_page - 1) // per_page
    db.close()
    return render_template('shop.html', products=products, categories=categories,
                           current_cat=cat_id, search=search, sort=sort,
                           page=page, total_pages=total_pages, total=total)

@app.route('/product/<int:pid>')
def product(pid):
    db = get_db()
    p = db.execute('''SELECT p.*, c.name_ar as cat_name 
                      FROM products p JOIN categories c ON p.category_id=c.id WHERE p.id=?''', (pid,)).fetchone()
    if not p: db.close(); return redirect(url_for('shop'))
    related = db.execute('''SELECT * FROM products WHERE category_id=? AND id!=? LIMIT 4''',
                         (p['category_id'], pid)).fetchall()
    in_wishlist = False
    if 'user_id' in session:
        r = db.execute('SELECT id FROM wishlist WHERE user_id=? AND product_id=?',
                       (session['user_id'], pid)).fetchone()
        in_wishlist = r is not None
    db.close()
    return render_template('product.html', product=p, related=related, in_wishlist=in_wishlist)

# ── CART ──────────────────────────────────────────────────────────────────────

@app.route('/cart')
@login_required
def cart():
    db = get_db()
    items = db.execute('''SELECT c.id, c.quantity, p.name, p.price, p.image, p.id as pid
                          FROM cart c JOIN products p ON c.product_id=p.id
                          WHERE c.user_id=?''', (session['user_id'],)).fetchall()
    total = sum(i['price'] * i['quantity'] for i in items)
    db.close()
    return render_template('cart.html', items=items, total=total)

@app.route('/cart/add/<int:pid>', methods=['POST'])
@login_required
def add_to_cart(pid):
    qty = int(request.form.get('quantity', 1))
    db = get_db()
    existing = db.execute('SELECT id, quantity FROM cart WHERE user_id=? AND product_id=?',
                          (session['user_id'], pid)).fetchone()
    if existing:
        db.execute('UPDATE cart SET quantity=? WHERE id=?', (existing['quantity']+qty, existing['id']))
    else:
        db.execute('INSERT INTO cart (user_id, product_id, quantity) VALUES (?,?,?)',
                   (session['user_id'], pid, qty))
    db.commit(); db.close()
    flash('✅ تم إضافة المنتج للسلة', 'success')
    return redirect(request.referrer or url_for('shop'))

@app.route('/cart/remove/<int:cid>')
@login_required
def remove_from_cart(cid):
    db = get_db()
    db.execute('DELETE FROM cart WHERE id=? AND user_id=?', (cid, session['user_id']))
    db.commit(); db.close()
    return redirect(url_for('cart'))

@app.route('/cart/update', methods=['POST'])
@login_required
def update_cart():
    cid = request.form.get('cart_id')
    qty = int(request.form.get('quantity', 1))
    db = get_db()
    if qty <= 0:
        db.execute('DELETE FROM cart WHERE id=? AND user_id=?', (cid, session['user_id']))
    else:
        db.execute('UPDATE cart SET quantity=? WHERE id=? AND user_id=?', (qty, cid, session['user_id']))
    db.commit(); db.close()
    return redirect(url_for('cart'))

# ── CHECKOUT ──────────────────────────────────────────────────────────────────

@app.route('/checkout', methods=['GET','POST'])
@login_required
def checkout():
    db = get_db()
    items = db.execute('''SELECT c.id, c.quantity, p.name, p.price, p.id as pid
                          FROM cart c JOIN products p ON c.product_id=p.id
                          WHERE c.user_id=?''', (session['user_id'],)).fetchall()
    if not items:
        flash('السلة فارغة!', 'warning')
        return redirect(url_for('cart'))
    total = sum(i['price'] * i['quantity'] for i in items)
    user  = db.execute('SELECT * FROM users WHERE id=?', (session['user_id'],)).fetchone()

    if request.method == 'POST':
        addr  = request.form.get('address')
        phone = request.form.get('phone')
        notes = request.form.get('notes', '')
        cur   = db.execute('INSERT INTO orders (user_id,total,address,phone,notes) VALUES (?,?,?,?,?)',
                           (session['user_id'], total, addr, phone, notes))
        oid   = cur.lastrowid
        for i in items:
            db.execute('INSERT INTO order_items (order_id,product_id,quantity,price) VALUES (?,?,?,?)',
                       (oid, i['pid'], i['quantity'], i['price']))
            db.execute('UPDATE products SET stock=stock-? WHERE id=?', (i['quantity'], i['pid']))
        db.execute('DELETE FROM cart WHERE user_id=?', (session['user_id'],))
        db.commit(); db.close()
        flash(f'🎉 تم استلام طلبك بنجاح! رقم الطلب #{oid}', 'success')
        return redirect(url_for('orders'))
    db.close()
    return render_template('checkout.html', items=items, total=total, user=user)

# ── ORDERS ────────────────────────────────────────────────────────────────────

@app.route('/orders')
@login_required
def orders():
    db = get_db()
    my_orders = db.execute('''SELECT * FROM orders WHERE user_id=? ORDER BY id DESC''',
                           (session['user_id'],)).fetchall()
    db.close()
    return render_template('orders.html', orders=my_orders)

# ── WISHLIST ──────────────────────────────────────────────────────────────────

@app.route('/wishlist/toggle/<int:pid>')
@login_required
def toggle_wishlist(pid):
    db = get_db()
    r = db.execute('SELECT id FROM wishlist WHERE user_id=? AND product_id=?',
                   (session['user_id'], pid)).fetchone()
    if r:
        db.execute('DELETE FROM wishlist WHERE id=?', (r['id'],))
        msg = 'تم الحذف من المفضلة'
    else:
        db.execute('INSERT INTO wishlist (user_id, product_id) VALUES (?,?)', (session['user_id'], pid))
        msg = '❤️ تم الإضافة للمفضلة'
    db.commit(); db.close()
    flash(msg, 'info')
    return redirect(request.referrer or url_for('shop'))

@app.route('/wishlist')
@login_required
def wishlist():
    db = get_db()
    items = db.execute('''SELECT p.* FROM wishlist w JOIN products p ON w.product_id=p.id
                          WHERE w.user_id=?''', (session['user_id'],)).fetchall()
    db.close()
    return render_template('wishlist.html', items=items)

# ── AUTH ──────────────────────────────────────────────────────────────────────

@app.route('/register', methods=['GET','POST'])
def register():
    if request.method == 'POST':
        name  = request.form.get('name','').strip()
        email = request.form.get('email','').strip().lower()
        pw    = request.form.get('password','')
        phone = request.form.get('phone','').strip()
        if not name or not email or not pw:
            flash('يرجى ملء جميع الحقول المطلوبة', 'danger')
            return render_template('register.html')
        db = get_db()
        if db.execute('SELECT id FROM users WHERE email=?', (email,)).fetchone():
            flash('البريد الإلكتروني مسجل مسبقاً', 'danger')
            db.close(); return render_template('register.html')
        db.execute('INSERT INTO users (name,email,password,phone) VALUES (?,?,?,?)',
                   (name, email, hash_password(pw), phone))
        db.commit()
        user = db.execute('SELECT * FROM users WHERE email=?', (email,)).fetchone()
        session['user_id'] = user['id']
        session['user_name'] = user['name']
        session['is_admin']  = bool(user['is_admin'])
        db.close()
        flash(f'🎉 أهلاً {name}! تم إنشاء حسابك بنجاح', 'success')
        return redirect(url_for('index'))
    return render_template('register.html')

@app.route('/login', methods=['GET','POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email','').strip().lower()
        pw    = request.form.get('password','')
        db    = get_db()
        user  = db.execute('SELECT * FROM users WHERE email=? AND password=?',
                           (email, hash_password(pw))).fetchone()
        db.close()
        if user:
            session['user_id']   = user['id']
            session['user_name'] = user['name']
            session['is_admin']  = bool(user['is_admin'])
            flash(f'أهلاً {user["name"]}! 👋', 'success')
            return redirect(url_for('admin_dashboard') if user['is_admin'] else url_for('index'))
        flash('البريد الإلكتروني أو كلمة المرور غير صحيحة', 'danger')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('تم تسجيل الخروج', 'info')
    return redirect(url_for('index'))

@app.route('/profile', methods=['GET','POST'])
@login_required
def profile():
    db = get_db()
    user = db.execute('SELECT * FROM users WHERE id=?', (session['user_id'],)).fetchone()
    if request.method == 'POST':
        name    = request.form.get('name','').strip()
        phone   = request.form.get('phone','').strip()
        address = request.form.get('address','').strip()
        db.execute('UPDATE users SET name=?,phone=?,address=? WHERE id=?',
                   (name, phone, address, session['user_id']))
        db.commit()
        session['user_name'] = name
        flash('✅ تم تحديث البيانات', 'success')
        return redirect(url_for('profile'))
    db.close()
    return render_template('profile.html', user=user)

# ── ADMIN ─────────────────────────────────────────────────────────────────────

@app.route('/admin')
@login_required
@admin_required
def admin_dashboard():
    db = get_db()
    stats = {
        'products': db.execute('SELECT COUNT(*) FROM products').fetchone()[0],
        'orders':   db.execute('SELECT COUNT(*) FROM orders').fetchone()[0],
        'users':    db.execute('SELECT COUNT(*) FROM users WHERE is_admin=0').fetchone()[0],
        'revenue':  db.execute("SELECT COALESCE(SUM(total),0) FROM orders WHERE status!='cancelled'").fetchone()[0],
    }
    recent_orders = db.execute('''SELECT o.*, u.name as uname FROM orders o
                                  JOIN users u ON o.user_id=u.id ORDER BY o.id DESC LIMIT 5''').fetchall()
    db.close()
    return render_template('admin/dashboard.html', stats=stats, recent_orders=recent_orders)

@app.route('/admin/products')
@login_required
@admin_required
def admin_products():
    db = get_db()
    products = db.execute('''SELECT p.*, c.name_ar as cat_name FROM products p
                             JOIN categories c ON p.category_id=c.id ORDER BY p.id DESC''').fetchall()
    categories = db.execute('SELECT * FROM categories').fetchall()
    db.close()
    return render_template('admin/products.html', products=products, categories=categories)

@app.route('/admin/products/add', methods=['POST'])
@login_required
@admin_required
def admin_add_product():
    name      = request.form.get('name','').strip()
    desc      = request.form.get('description','').strip()
    price     = float(request.form.get('price', 0))
    old_price = request.form.get('old_price') or None
    cat_id    = request.form.get('category_id')
    stock     = int(request.form.get('stock', 0))
    featured  = 1 if request.form.get('is_featured') else 0
    is_new    = 1 if request.form.get('is_new') else 0
    image_name = 'default.jpg'
    if 'image' in request.files:
        f = request.files['image']
        if f and f.filename and allowed_file(f.filename):
            image_name = secrets.token_hex(8) + '.' + f.filename.rsplit('.',1)[1].lower()
            f.save(os.path.join(app.config['UPLOAD_FOLDER'], image_name))
    db = get_db()
    db.execute('''INSERT INTO products (name,description,price,old_price,category_id,stock,is_featured,is_new,image)
                  VALUES (?,?,?,?,?,?,?,?,?)''',
               (name, desc, price, old_price, cat_id, stock, featured, is_new, image_name))
    db.commit(); db.close()
    flash('✅ تم إضافة المنتج بنجاح', 'success')
    return redirect(url_for('admin_products'))

@app.route('/admin/products/delete/<int:pid>')
@login_required
@admin_required
def admin_delete_product(pid):
    db = get_db()
    db.execute('DELETE FROM products WHERE id=?', (pid,))
    db.commit(); db.close()
    flash('🗑️ تم حذف المنتج', 'info')
    return redirect(url_for('admin_products'))

@app.route('/admin/products/edit/<int:pid>', methods=['GET','POST'])
@login_required
@admin_required
def admin_edit_product(pid):
    db = get_db()
    p  = db.execute('SELECT * FROM products WHERE id=?', (pid,)).fetchone()
    categories = db.execute('SELECT * FROM categories').fetchall()
    if request.method == 'POST':
        name      = request.form.get('name','').strip()
        desc      = request.form.get('description','').strip()
        price     = float(request.form.get('price', 0))
        old_price = request.form.get('old_price') or None
        cat_id    = request.form.get('category_id')
        stock     = int(request.form.get('stock', 0))
        featured  = 1 if request.form.get('is_featured') else 0
        is_new    = 1 if request.form.get('is_new') else 0
        image_name = p['image']
        if 'image' in request.files:
            f = request.files['image']
            if f and f.filename and allowed_file(f.filename):
                image_name = secrets.token_hex(8) + '.' + f.filename.rsplit('.',1)[1].lower()
                f.save(os.path.join(app.config['UPLOAD_FOLDER'], image_name))
        db.execute('''UPDATE products SET name=?,description=?,price=?,old_price=?,
                      category_id=?,stock=?,is_featured=?,is_new=?,image=? WHERE id=?''',
                   (name, desc, price, old_price, cat_id, stock, featured, is_new, image_name, pid))
        db.commit(); db.close()
        flash('✅ تم تحديث المنتج', 'success')
        return redirect(url_for('admin_products'))
    db.close()
    return render_template('admin/edit_product.html', product=p, categories=categories)

@app.route('/admin/orders')
@login_required
@admin_required
def admin_orders():
    db = get_db()
    orders = db.execute('''SELECT o.*, u.name as uname, u.email 
                           FROM orders o JOIN users u ON o.user_id=u.id ORDER BY o.id DESC''').fetchall()
    db.close()
    return render_template('admin/orders.html', orders=orders)

@app.route('/admin/orders/status/<int:oid>', methods=['POST'])
@login_required
@admin_required
def update_order_status(oid):
    status = request.form.get('status')
    db = get_db()
    db.execute('UPDATE orders SET status=? WHERE id=?', (status, oid))
    db.commit(); db.close()
    flash('✅ تم تحديث حالة الطلب', 'success')
    return redirect(url_for('admin_orders'))

@app.route('/admin/users')
@login_required
@admin_required
def admin_users():
    db = get_db()
    users = db.execute('SELECT * FROM users ORDER BY id DESC').fetchall()
    db.close()
    return render_template('admin/users.html', users=users)

if __name__ == '__main__':
    init_db()
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
