from flask import Flask, render_template_string, request, redirect, url_for, session, flash, jsonify
import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash
import random
import os
import smtplib
import re
import time
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from functools import wraps
import threading

app = Flask(__name__)
app.secret_key = "tk_worldwide_secret_2026"

# Admin Configuration
ADMIN_EMAIL = "atilolaayodele80@gmail.com"
CUSTOMER_CARE_NUMBER = "+2348036454804"

# OTP Storage (in production, use Redis or database)
otp_storage = {}
live_chat_sessions = {}
admin_chat_sessions = {}

def get_db():
    db = sqlite3.connect('tk_worldwide.db')
    db.row_factory = sqlite3.Row
    return db

def init_db():
    db = get_db()
    db.executescript('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            email TEXT UNIQUE NOT NULL,
            phone TEXT UNIQUE,
            password TEXT NOT NULL,
            is_admin INTEGER DEFAULT 0,
            email_verified INTEGER DEFAULT 0,
            phone_verified INTEGER DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            last_login TEXT,
            is_active INTEGER DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            designer TEXT NOT NULL,
            price REAL NOT NULL,
            category TEXT NOT NULL,
            sizes TEXT NOT NULL,
            colors TEXT NOT NULL,
            stock INTEGER NOT NULL,
            description TEXT,
            image_url TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS cart (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            product_id INTEGER,
            quantity INTEGER DEFAULT 1,
            UNIQUE(user_id, product_id)
        );
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            total REAL,
            status TEXT DEFAULT 'Processing',
            tracking_number TEXT,
            estimated_delivery TEXT,
            date TEXT DEFAULT CURRENT_TIMESTAMP,
            address TEXT,
            payment_method TEXT
        );
        CREATE TABLE IF NOT EXISTS order_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER,
            product_id INTEGER,
            quantity INTEGER,
            price REAL
        );
        CREATE TABLE IF NOT EXISTS reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER,
            user_id INTEGER,
            rating INTEGER CHECK(rating >= 1 AND rating <= 5),
            comment TEXT,
            date TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS chat_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT,
            user_id INTEGER,
            message TEXT,
            sender TEXT,
            is_read INTEGER DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS admin_notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            type TEXT,
            message TEXT,
            is_read INTEGER DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS user_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            session_token TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            expires_at TEXT
        );
    ''')
    db.commit()

    # Admin account
    if not db.execute("SELECT 1 FROM users WHERE username = 'atilola'").fetchone():
        db.execute("INSERT INTO users (username, email, password, is_admin, email_verified) VALUES (?, ?, ?, 1, 1)",
                   ('atilola', ADMIN_EMAIL, generate_password_hash('admin123')))
        db.commit()

    # Sample products
    if not db.execute("SELECT COUNT(*) FROM products").fetchone()[0]:
        samples = [
            ("Adire Silk Maxi Gown", "Tosin Fashola", 45000, "Women", "S,M,L,XL", "Indigo,Coral,Gold", 15, "Elegant hand-dyed adire silk with modern tailoring.", "https://images.unsplash.com/photo-1595777457583-95e059d581b8?w=800"),
            ("Beaded Lace Boubou", "Lisa Folawiyo", 65000, "Women", "M,L", "Teal,Magenta", 10, "Luxurious beaded lace boubou perfect for special occasions.", "https://images.unsplash.com/photo-1594633313593-bab3825d0caf?w=800"),
            ("Luxury Senator Set", "Mai Atafo", 85000, "Men", "M,L,XL", "Navy,Gold", 8, "Modern senator wear with exquisite embroidery.", "https://images.unsplash.com/photo-1507679799987-c73779587ccf?w=800"),
            ("Grand Agbada", "Onalaja", 95000, "Men", "L,XL,XXL", "Black,Burgundy", 6, "Premium embroidered agbada for traditional events.", "https://images.unsplash.com/photo-1593032465175-d529cb1e790e?w=800"),
            ("Premium Adire Fabric (6 yards)", "Traditional Weavers", 12000, "Materials", "One Size", "Indigo,White", 50, "Authentic hand-dyed adire fabric from Abeokuta.", "https://images.unsplash.com/photo-1558171813-4c088753af8f?w=800"),
            ("Mini Ankara Gown", "Vivelle Kids", 8500, "Kids", "2-12 years", "Pink,Yellow", 20, "Cute Ankara gown for young fashionistas.", "https://images.unsplash.com/photo-1519238263530-99bdd11df2ea?w=800"),
            ("Aso-Oke Bridal Set", "Deola Sagoe", 125000, "Women", "S,M,L", "Gold,Cream", 5, "Luxurious traditional bridal aso-oke with beadwork.", "https://images.unsplash.com/photo-1594552072238-b8a33785b261?w=800"),
            ("Modern Danshiki", "Orange Culture", 35000, "Men", "S,M,L,XL", "White,Black,Red", 12, "Contemporary danshiki with African print accents.", "https://images.unsplash.com/photo-1596755094514-f87e34085b2c?w=800"),
        ]
        for p in samples:
            db.execute("""INSERT INTO products 
                          (name, designer, price, category, sizes, colors, stock, description, image_url) 
                          VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""", p)
        db.commit()

init_db()

def get_current_user():
    if 'user_id' in session:
        return get_db().execute("SELECT * FROM users WHERE id = ?", (session['user_id'],)).fetchone()
    return None

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('is_admin'):
            flash("Admin access only!", "danger")
            return redirect(url_for('home'))
        return f(*args, **kwargs)
    return decorated_function

def send_email(to_email, subject, body):
    try:
        # Configure your SMTP settings here
        # For Gmail: smtp.gmail.com, port 587
        msg = MIMEMultipart()
        msg['From'] = ADMIN_EMAIL
        msg['To'] = to_email
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'html'))
        
        # Uncomment and configure with your SMTP credentials
        # server = smtplib.SMTP('smtp.gmail.com', 587)
        # server.starttls()
        # server.login(ADMIN_EMAIL, 'your_app_password')
        # server.send_message(msg)
        # server.quit()
        
        print(f"Email sent to {to_email}: {subject}")
        return True
    except Exception as e:
        print(f"Email error: {e}")
        return False

def generate_otp():
    return str(random.randint(100000, 999999))

def send_otp_email(email, otp):
    subject = "TK Worldwide - Your Verification Code"
    body = f"""
    <html>
    <body style="font-family: Arial, sans-serif; background: #fff0f5; padding: 20px;">
        <div style="max-width: 600px; margin: 0 auto; background: white; padding: 30px; border-radius: 10px; border: 2px solid #ff69b4;">
            <h2 style="color: #ff1493; text-align: center;">TK Worldwide Clothing</h2>
            <p style="color: #333;">Hello,</p>
            <p style="color: #333;">Your verification code is:</p>
            <h1 style="color: #ff1493; text-align: center; font-size: 48px; letter-spacing: 10px;">{otp}</h1>
            <p style="color: #666; text-align: center;">This code will expire in 10 minutes.</p>
            <p style="color: #999; font-size: 12px; text-align: center;">If you didn't request this code, please ignore this email.</p>
        </div>
    </body>
    </html>
    """
    return send_email(email, subject, body)

def send_otp_sms(phone, otp):
    # Integrate with SMS provider (Twilio, Africa's Talking, etc.)
    print(f"SMS OTP {otp} sent to {phone}")
    return True

def get_fashion_advice(query, conversation_history=None):
    query_lower = query.lower()
    
    # Enhanced conversational responses
    greetings = ["hello", "hi", "hey", "good morning", "good afternoon", "good evening"]
    if any(g in query_lower for g in greetings):
        return "Hello there! 👋 Welcome to TK Worldwide! I'm your personal AI stylist. How can I help you look fabulous today? 💕"
    
    thanks = ["thank", "thanks", "appreciate"]
    if any(t in query_lower for t in thanks):
        return "You're so welcome! 😊 I'm here whenever you need fashion advice. Enjoy shopping with us! 💖"
    
    bye = ["bye", "goodbye", "see you", "talk later"]
    if any(b in query_lower for b in bye):
        return "Goodbye! 👋 Come back anytime for more style tips. Have a wonderful day! ✨"
    
    help_words = ["help", "assist", "support"]
    if any(h in query_lower for h in help_words):
        return "I'd love to help! 💕 I can suggest outfits for weddings, work, casual outings, or help you find the perfect fabric. What do you need?"
    
    if any(word in query_lower for word in ["wedding", "party", "occasion", "event", "ceremony"]):
        return "Ooh, a special occasion! 💃✨ For weddings and parties, I'd recommend our Beaded Lace Boubou or Grand Agbada! They're absolutely stunning and will make you the center of attention. The bold colors and luxurious fabrics like Adire or Lace are perfect for making a statement. Would you like me to suggest colors based on your skin tone? 😊"
    
    elif any(word in query_lower for word in ["work", "office", "professional", "business", "corporate"]):
        return "Looking professional yet stylish! 👔💼 Our Senator sets and modern Danshiki styles are perfect for the office. They offer sophistication while maintaining that beautiful cultural elegance. Navy, black, and cream colors work best for corporate settings. Want me to show you some options? ✨"
    
    elif any(word in query_lower for word in ["casual", "everyday", "simple", "comfortable", "relaxed"]):
        return "Casual chic is always in! 🌸 For everyday wear, our Adire fabrics made into simple gowns or shirts are perfect. They're super comfortable, breathable, and stylish! You can dress them up or down depending on your mood. What colors do you usually gravitate towards? 💕"
    
    elif any(word in query_lower for word in ["kids", "children", "child", "daughter", "son"]):
        return "Aww, shopping for the little ones! 🧒👧 Our Mini Ankara Gowns for kids are absolutely adorable! They're comfortable, culturally vibrant, and perfect for any occasion. The kids always look so cute in them! What age are we shopping for? 😍"
    
    elif any(word in query_lower for word in ["fabric", "material", "cloth", "textile", "adire", "ankara", "aso-oke"]):
        return "Ah, a fabric lover! 🎨 Our Premium Adire Fabric (6 yards) is hand-dyed by traditional weavers from Abeokuta - authentic and beautiful! Perfect for custom designs that tell a story. Ankara and Aso-Oke are also stunning choices. Are you planning to sew something specific? I'd love to hear about your design ideas! ✨"
    
    elif any(word in query_lower for word in ["price", "cost", "expensive", "cheap", "affordable", "budget"]):
        return "Great question! 💰 We have pieces ranging from ₦8,500 to ₦125,000, so there's something for every budget. Our Mini Ankara Gowns start at ₦8,500, while our premium bridal Aso-Oke is ₦125,000. What's your budget range? I can suggest the perfect pieces within your price range! 😊"
    
    elif any(word in query_lower for word in ["size", "fit", "measurement", "sizing"]):
        return "Fit is everything! 📏 Each product page has a detailed size guide. We offer sizes from S to XXL, and for kids, ages 2-12 years. If you need custom sizing, just give us a call at +2348036454804 and we'll take care of you! What's your usual size? 💕"
    
    elif any(word in query_lower for word in ["color", "colour", "shade", "tone"]):
        return "Colors make all the difference! 🌈 We have beautiful Indigo, Coral, Gold, Teal, Magenta, Navy, Burgundy, and more! For weddings, gold and coral are stunning. For work, navy and black are classic. What's the occasion, and do you have any favorite colors? ✨"
    
    elif any(word in query_lower for word in ["delivery", "shipping", "ship", "receive", "how long"]):
        return "We deliver nationwide within 3-5 business days! 🚚✨ And guess what? Shipping is FREE! International shipping is also available on request. Once you place your order, you'll get a tracking number to follow your package. Excited to get your new pieces? 😊"
    
    elif any(word in query_lower for word in ["return", "exchange", "refund", "money back"]):
        return "Shop with confidence! 🛍️ We accept returns within 14 days of delivery. If something doesn't fit right or you change your mind, just check your order details to initiate a return. We want you to love everything you buy from us! 💕"
    
    elif any(word in query_lower for word in ["designer", "brand", "who made", "tosin", "lisa", "mai", "deola"]):
        return "We work with amazing Nigerian designers! 🌟 Tosin Fashola creates stunning Adire pieces, Lisa Folawiyo's beaded work is iconic, Mai Atafo's Senator sets are legendary, and Deola Sagoe's bridal pieces are dream-worthy! Each piece is crafted with love and expertise. Do you have a favorite designer? ✨"
    
    return "That's a great question! 💕 I'd love to help you find the perfect outfit. Tell me more about what you're looking for - is it for a special occasion, work, or just treating yourself? Also, what's your style preference - traditional, modern, or a mix of both? 😊"

def get_admin_stats():
    db = get_db()
    stats = {
        'total_users': db.execute("SELECT COUNT(*) FROM users").fetchone()[0],
        'total_orders': db.execute("SELECT COUNT(*) FROM orders").fetchone()[0],
        'total_revenue': db.execute("SELECT COALESCE(SUM(total), 0) FROM orders").fetchone()[0],
        'total_products': db.execute("SELECT COUNT(*) FROM products").fetchone()[0],
        'pending_orders': db.execute("SELECT COUNT(*) FROM orders WHERE status = 'Processing'").fetchone()[0],
        'today_orders': db.execute("SELECT COUNT(*) FROM orders WHERE date(date) = date('now')").fetchone()[0],
        'unread_chats': db.execute("SELECT COUNT(*) FROM chat_messages WHERE is_read = 0 AND sender = 'user'").fetchone()[0],
        'low_stock': db.execute("SELECT * FROM products WHERE stock < 5").fetchall(),
        'recent_users': db.execute("SELECT * FROM users ORDER BY created_at DESC LIMIT 5").fetchall(),
        'recent_orders': db.execute('''
            SELECT o.*, u.username FROM orders o 
            JOIN users u ON o.user_id = u.id 
            ORDER BY o.date DESC LIMIT 5
        ''').fetchall()
    }
    return stats

# ====================== HOME ======================
@app.route('/')
def home():
    db = get_db()
    products = db.execute("SELECT * FROM products ORDER BY id DESC").fetchall()
    return render_template_string(HTML_TEMPLATE, page='home', products=products, user=get_current_user())

# ====================== AUTH WITH OTP ======================
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        step = request.form.get('step', '1')
        
        if step == '1':
            # Initial registration
            username = request.form.get('username')
            email = request.form.get('email')
            phone = request.form.get('phone')
            password = request.form.get('password')
            otp_method = request.form.get('otp_method', 'email')
            
            if not username or not email or not password:
                flash("All fields are required.", "danger")
                return render_template_string(HTML_TEMPLATE, page='register', step='1')
            
            # Store temp data
            session['temp_reg'] = {
                'username': username,
                'email': email,
                'phone': phone,
                'password': password,
                'otp_method': otp_method
            }
            
            # Generate and send OTP
            otp = generate_otp()
            otp_storage[email] = {'otp': otp, 'timestamp': time.time(), 'phone': phone}
            
            if otp_method == 'email':
                send_otp_email(email, otp)
                flash(f"Verification code sent to {email}. Please check your inbox (and spam folder).", "info")
            else:
                if phone:
                    send_otp_sms(phone, otp)
                    flash(f"Verification code sent to {phone}.", "info")
                else:
                    flash("Phone number required for SMS verification.", "danger")
                    return render_template_string(HTML_TEMPLATE, page='register', step='1')
            
            return render_template_string(HTML_TEMPLATE, page='register', step='2', email=email, otp_method=otp_method)
        
        elif step == '2':
            # Verify OTP
            email = request.form.get('email')
            otp = request.form.get('otp')
            temp = session.get('temp_reg')
            
            if not temp or temp['email'] != email:
                flash("Session expired. Please start again.", "danger")
                return render_template_string(HTML_TEMPLATE, page='register', step='1')
            
            stored = otp_storage.get(email)
            if not stored or stored['otp'] != otp:
                flash("Invalid verification code.", "danger")
                return render_template_string(HTML_TEMPLATE, page='register', step='2', email=email, otp_method=temp['otp_method'])
            
            if time.time() - stored['timestamp'] > 600:  # 10 minutes expiry
                flash("Verification code expired. Please request a new one.", "danger")
                return render_template_string(HTML_TEMPLATE, page='register', step='2', email=email, otp_method=temp['otp_method'])
            
            # Create user
            db = get_db()
            try:
                db.execute("""INSERT INTO users 
                           (username, email, phone, password, email_verified, phone_verified) 
                           VALUES (?, ?, ?, ?, ?, ?)""",
                          (temp['username'], temp['email'], temp['phone'], 
                           generate_password_hash(temp['password']), 1, 1 if temp['otp_method'] == 'phone' else 0))
                db.commit()
                
                # Clean up
                del otp_storage[email]
                session.pop('temp_reg', None)
                
                flash("Registration successful! Please login.", "success")
                return redirect(url_for('login'))
            except sqlite3.IntegrityError:
                flash("Username or email already exists.", "danger")
                return render_template_string(HTML_TEMPLATE, page='register', step='1')
    
    return render_template_string(HTML_TEMPLATE, page='register', step='1')

@app.route('/resend-otp', methods=['POST'])
def resend_otp():
    email = request.form.get('email')
    otp_method = request.form.get('otp_method', 'email')
    temp = session.get('temp_reg')
    
    if not temp or temp['email'] != email:
        return jsonify({'success': False, 'message': 'Session expired'})
    
    otp = generate_otp()
    otp_storage[email] = {'otp': otp, 'timestamp': time.time(), 'phone': temp.get('phone')}
    
    if otp_method == 'email':
        send_otp_email(email, otp)
    else:
        send_otp_sms(temp.get('phone'), otp)
    
    return jsonify({'success': True, 'message': 'New code sent!'})

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        db = get_db()
        user = db.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        if user and check_password_hash(user['password'], password):
            if user['is_active'] == 0:
                flash("Your account has been suspended. Contact support.", "danger")
                return render_template_string(HTML_TEMPLATE, page='login')
            
            session['user_id'] = user['id']
            session['is_admin'] = bool(user['is_admin'])
            
            # Update last login
            db.execute("UPDATE users SET last_login = CURRENT_TIMESTAMP WHERE id = ?", (user['id'],))
            db.commit()
            
            flash("Login successful!", "success")
            
            if user['is_admin']:
                return redirect(url_for('admin_panel'))
            return redirect(url_for('home'))
        flash("Invalid username or password.", "danger")
    return render_template_string(HTML_TEMPLATE, page='login')

@app.route('/logout')
def logout():
    session.clear()
    flash("Logged out successfully.", "success")
    return redirect(url_for('home'))

# ====================== CART ======================
@app.route('/add_to_cart/<int:product_id>', methods=['POST'])
def add_to_cart(product_id):
    if 'user_id' not in session:
        flash("Please login to add to cart.", "danger")
        return redirect(url_for('login'))
    quantity = int(request.form.get('quantity', 1))
    db = get_db()
    existing = db.execute("SELECT * FROM cart WHERE user_id = ? AND product_id = ?", 
                         (session['user_id'], product_id)).fetchone()
    if existing:
        db.execute("UPDATE cart SET quantity = quantity + ? WHERE id = ?", 
                  (quantity, existing['id']))
    else:
        db.execute("INSERT INTO cart (user_id, product_id, quantity) VALUES (?, ?, ?)",
                  (session['user_id'], product_id, quantity))
    db.commit()
    flash("Added to cart!", "success")
    return redirect(url_for('view_cart'))

@app.route('/cart')
def view_cart():
    if 'user_id' not in session:
        flash("Please login to view cart.", "danger")
        return redirect(url_for('login'))
    db = get_db()
    items = db.execute('''SELECT c.id as cart_id, p.*, c.quantity 
                          FROM cart c JOIN products p ON c.product_id = p.id 
                          WHERE c.user_id = ?''', (session['user_id'],)).fetchall()
    total = sum(float(item['price']) * item['quantity'] for item in items)
    return render_template_string(HTML_TEMPLATE, page='cart', cart_items=items, total=total, user=get_current_user())

@app.route('/remove_from_cart/<int:cart_id>')
def remove_from_cart(cart_id):
    if 'user_id' in session:
        db = get_db()
        db.execute("DELETE FROM cart WHERE id = ? AND user_id = ?", (cart_id, session['user_id']))
        db.commit()
        flash("Item removed from cart.", "success")
    return redirect(url_for('view_cart'))

# ====================== PAYMENT + ORDER ======================
@app.route('/checkout', methods=['POST'])
def checkout():
    if 'user_id' not in session:
        flash("Please login to checkout.", "danger")
        return redirect(url_for('login'))
    db = get_db()
    items = db.execute('''SELECT p.id, p.name, p.price, c.quantity, p.stock
                          FROM cart c JOIN products p ON c.product_id = p.id 
                          WHERE c.user_id = ?''', (session['user_id'],)).fetchall()
    if not items:
        flash("Your cart is empty.", "danger")
        return redirect(url_for('view_cart'))
    
    total = sum(float(item['price']) * item['quantity'] for item in items)
    
    for item in items:
        if item['quantity'] > item['stock']:
            flash(f"Sorry, only {item['stock']} units of {item['name']} available.", "danger")
            return redirect(url_for('view_cart'))
    
    tracking = f"TK{random.randint(100000,999999)}"
    estimated = (datetime.now() + timedelta(days=5)).strftime("%Y-%m-%d")
    
    db.execute("INSERT INTO orders (user_id, total, status, tracking_number, estimated_delivery, address) VALUES (?, ?, 'Processing', ?, ?, 'Lagos, Nigeria')",
               (session['user_id'], total, tracking, estimated))
    order_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]
    
    for item in items:
        db.execute("INSERT INTO order_items (order_id, product_id, quantity, price) VALUES (?, ?, ?, ?)",
                   (order_id, item['id'], item['quantity'], item['price']))
        db.execute("UPDATE products SET stock = stock - ? WHERE id = ?", 
                  (item['quantity'], item['id']))
    
    db.execute("DELETE FROM cart WHERE user_id = ?", (session['user_id'],))
    db.commit()
    
    # Notify admin
    db.execute("INSERT INTO admin_notifications (type, message) VALUES (?, ?)",
               ('new_order', f'New order #{order_id} placed for ₦{total:,.0f}'))
    db.commit()
    
    # Send email notification
    user = db.execute("SELECT email FROM users WHERE id = ?", (session['user_id'],)).fetchone()
    if user:
        send_email(user['email'], "Order Confirmation - TK Worldwide", 
                  f"<h2>Thank you for your order!</h2><p>Order #{order_id} has been placed successfully.</p>")
    
    flash(f"Order #{order_id} placed successfully! Tracking: {tracking}.", "success")
    return redirect(url_for('orders'))

@app.route('/orders')
def orders():
    if 'user_id' not in session:
        flash("Please login to view orders.", "danger")
        return redirect(url_for('login'))
    db = get_db()
    user_orders = db.execute('''
        SELECT o.*, GROUP_CONCAT(p.name, ', ') as items 
        FROM orders o 
        LEFT JOIN order_items oi ON o.id = oi.order_id 
        LEFT JOIN products p ON oi.product_id = p.id 
        WHERE o.user_id = ? GROUP BY o.id ORDER BY o.date DESC
    ''', (session['user_id'],)).fetchall()
    return render_template_string(HTML_TEMPLATE, page='orders', orders=user_orders, user=get_current_user())

# ====================== ADMIN PANEL ======================
@app.route('/admin')
@admin_required
def admin_panel():
    db = get_db()
    stats = get_admin_stats()
    products = db.execute("SELECT * FROM products").fetchall()
    users_list = db.execute("SELECT * FROM users ORDER BY created_at DESC").fetchall()
    orders_list = db.execute('''SELECT o.*, u.username, u.email FROM orders o 
                                JOIN users u ON o.user_id = u.id ORDER BY o.date DESC''').fetchall()
    notifications = db.execute("SELECT * FROM admin_notifications WHERE is_read = 0 ORDER BY created_at DESC").fetchall()
    
    # Get chat messages grouped by session
    chat_sessions = db.execute('''
        SELECT session_id, user_id, COUNT(*) as msg_count, 
               MAX(CASE WHEN sender = 'user' AND is_read = 0 THEN 1 ELSE 0 END) as has_unread
        FROM chat_messages 
        GROUP BY session_id 
        ORDER BY MAX(created_at) DESC
    ''').fetchall()
    
    return render_template_string(HTML_TEMPLATE, page='admin', stats=stats, products=products, 
                                   users=users_list, orders=orders_list, notifications=notifications,
                                   chat_sessions=chat_sessions, user=get_current_user())

@app.route('/admin/user/<int:user_id>', methods=['GET', 'POST'])
@admin_required
def admin_user_detail(user_id):
    db = get_db()
    user_detail = db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    user_orders = db.execute('''SELECT o.* FROM orders o WHERE o.user_id = ? ORDER BY o.date DESC''', (user_id,)).fetchall()
    
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'toggle_admin':
            new_status = 0 if user_detail['is_admin'] else 1
            db.execute("UPDATE users SET is_admin = ? WHERE id = ?", (new_status, user_id))
            db.commit()
            flash(f"User admin status updated.", "success")
        elif action == 'toggle_active':
            new_status = 0 if user_detail['is_active'] else 1
            db.execute("UPDATE users SET is_active = ? WHERE id = ?", (new_status, user_id))
            db.commit()
            flash(f"User account {'activated' if new_status else 'suspended'}.", "success")
        elif action == 'reset_password':
            new_pass = request.form.get('new_password')
            if new_pass:
                db.execute("UPDATE users SET password = ? WHERE id = ?", (generate_password_hash(new_pass), user_id))
                db.commit()
                flash("Password reset successfully.", "success")
        elif action == 'delete':
            db.execute("DELETE FROM users WHERE id = ?", (user_id,))
            db.commit()
            flash("User deleted.", "success")
            return redirect(url_for('admin_panel'))
        
        return redirect(url_for('admin_user_detail', user_id=user_id))
    
    return render_template_string(HTML_TEMPLATE, page='admin_user_detail', user_detail=user_detail, 
                                   user_orders=user_orders, user=get_current_user())

@app.route('/admin/add_product', methods=['POST'])
@admin_required
def admin_add_product():
    db = get_db()
    db.execute("""INSERT INTO products (name, designer, price, category, sizes, colors, stock, description, image_url) 
                  VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
               (request.form['name'], request.form['designer'], float(request.form['price']),
                request.form['category'], request.form['sizes'], request.form['colors'],
                int(request.form['stock']), request.form['description'], request.form['image_url']))
    db.commit()
    flash("Product added successfully!", "success")
    return redirect(url_for('admin_panel'))

@app.route('/admin/edit_product/<int:product_id>', methods=['POST'])
@admin_required
def admin_edit_product(product_id):
    db = get_db()
    db.execute("""UPDATE products SET name=?, designer=?, price=?, category=?, 
                  sizes=?, colors=?, stock=?, description=?, image_url=? WHERE id=?""",
               (request.form['name'], request.form['designer'], float(request.form['price']),
                request.form['category'], request.form['sizes'], request.form['colors'],
                int(request.form['stock']), request.form['description'], request.form['image_url'], product_id))
    db.commit()
    flash("Product updated!", "success")
    return redirect(url_for('admin_panel'))

@app.route('/admin/delete_product/<int:product_id>')
@admin_required
def admin_delete_product(product_id):
    db = get_db()
    db.execute("DELETE FROM products WHERE id = ?", (product_id,))
    db.commit()
    flash("Product deleted!", "success")
    return redirect(url_for('admin_panel'))

@app.route('/admin/update_order/<int:order_id>', methods=['POST'])
@admin_required
def admin_update_order(order_id):
    status = request.form.get('status')
    db = get_db()
    db.execute("UPDATE orders SET status = ? WHERE id = ?", (status, order_id))
    
    # Get user email for notification
    order = db.execute('''SELECT o.*, u.email FROM orders o JOIN users u ON o.user_id = u.id 
                          WHERE o.id = ?''', (order_id,)).fetchone()
    if order:
        send_email(order['email'], f"Order Update - TK Worldwide",
                  f"<h2>Order #{order_id} Update</h2><p>Your order status has been updated to: <strong>{status}</strong></p>")
    
    db.commit()
    flash(f"Order #{order_id} updated to {status}", "success")
    return redirect(url_for('admin_panel'))

@app.route('/admin/mark_notification_read/<int:notif_id>')
@admin_required
def mark_notification_read(notif_id):
    db = get_db()
    db.execute("UPDATE admin_notifications SET is_read = 1 WHERE id = ?", (notif_id,))
    db.commit()
    return jsonify({'success': True})

# ====================== LIVE CHAT ======================
@app.route('/chat/send', methods=['POST'])
def chat_send():
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Please login'})
    
    message = request.form.get('message')
    session_id = session.get('chat_session_id', f"user_{session['user_id']}_{int(time.time())}")
    session['chat_session_id'] = session_id
    
    db = get_db()
    db.execute("INSERT INTO chat_messages (session_id, user_id, message, sender) VALUES (?, ?, ?, ?)",
               (session_id, session['user_id'], message, 'user'))
    db.commit()
    
    # Notify admin
    db.execute("INSERT INTO admin_notifications (type, message) VALUES (?, ?)",
               ('new_chat', f'New message from user {session["user_id"]}'))
    db.commit()
    
    return jsonify({'success': True})

@app.route('/chat/history')
def chat_history():
    if 'user_id' not in session:
        return jsonify({'messages': []})
    
    session_id = session.get('chat_session_id')
    if not session_id:
        return jsonify({'messages': []})
    
    db = get_db()
    messages = db.execute('''SELECT * FROM chat_messages WHERE session_id = ? ORDER BY created_at''',
                         (session_id,)).fetchall()
    
    # Mark as read
    db.execute("UPDATE chat_messages SET is_read = 1 WHERE session_id = ? AND sender = 'admin'", (session_id,))
    db.commit()
    
    return jsonify({'messages': [{'sender': m['sender'], 'text': m['message'], 'time': m['created_at']} for m in messages]})

@app.route('/admin/chat/<session_id>')
@admin_required
def admin_chat_detail(session_id):
    db = get_db()
    messages = db.execute('''SELECT c.*, u.username FROM chat_messages c 
                              LEFT JOIN users u ON c.user_id = u.id 
                              WHERE c.session_id = ? ORDER BY c.created_at''', (session_id,)).fetchall()
    
    # Mark as read
    db.execute("UPDATE chat_messages SET is_read = 1 WHERE session_id = ? AND sender = 'user'", (session_id,))
    db.commit()
    
    return render_template_string(HTML_TEMPLATE, page='admin_chat', messages=messages, 
                                   session_id=session_id, user=get_current_user())

@app.route('/admin/chat/send', methods=['POST'])
@admin_required
def admin_chat_send():
    session_id = request.form.get('session_id')
    message = request.form.get('message')
    
    db = get_db()
    db.execute("INSERT INTO chat_messages (session_id, user_id, message, sender) VALUES (?, ?, ?, ?)",
               (session_id, 0, message, 'admin'))
    db.commit()
    
    return jsonify({'success': True})

@app.route('/admin/chat/sessions')
@admin_required
def admin_chat_sessions():
    db = get_db()
    sessions = db.execute('''
        SELECT session_id, user_id, COUNT(*) as msg_count,
               SUM(CASE WHEN sender = 'user' AND is_read = 0 THEN 1 ELSE 0 END) as unread
        FROM chat_messages 
        GROUP BY session_id 
        ORDER BY MAX(created_at) DESC
    ''').fetchall()
    return jsonify({'sessions': [{'id': s['session_id'], 'user_id': s['user_id'], 
                                  'unread': s['unread']} for s in sessions]})

# ====================== CUSTOMER CARE ======================
@app.route('/customer-care')
def customer_care():
    return render_template_string(HTML_TEMPLATE, page='customer_care', user=get_current_user())

# ====================== AI STYLIST ======================
@app.route('/ai-stylist', methods=['GET', 'POST'])
def ai_stylist():
    if 'ai_conversation' not in session:
        session['ai_conversation'] = []
    
    if request.method == 'POST':
        user_query = request.form.get('query', '').strip()
        if user_query:
            response = get_fashion_advice(user_query, session['ai_conversation'])
            session['ai_conversation'].append({'user': user_query, 'bot': response})
            session.modified = True
            return jsonify({'response': response, 'conversation': session['ai_conversation']})
    
    return render_template_string(HTML_TEMPLATE, page='ai_stylist', 
                                   conversation=session['ai_conversation'], user=get_current_user())

@app.route('/ai-stylist/clear', methods=['POST'])
def clear_ai_conversation():
    session['ai_conversation'] = []
    return jsonify({'success': True})

# ====================== PRODUCT DETAIL ======================
@app.route('/product/<int:product_id>', methods=['GET', 'POST'])
def product_detail(product_id):
    db = get_db()
    product = db.execute("SELECT * FROM products WHERE id = ?", (product_id,)).fetchone()
    if not product:
        flash("Product not found", "danger")
        return redirect(url_for('home'))

    if request.method == 'POST' and 'user_id' in session:
        rating = int(request.form.get('rating', 5))
        comment = request.form.get('comment', '')
        existing = db.execute("SELECT * FROM reviews WHERE product_id = ? AND user_id = ?", 
                             (product_id, session['user_id'])).fetchone()
        if existing:
            flash("You have already reviewed this product.", "warning")
        else:
            db.execute("INSERT INTO reviews (product_id, user_id, rating, comment) VALUES (?,?,?,?)",
                       (product_id, session['user_id'], rating, comment))
            db.commit()
            flash("Thank you for your review!", "success")
        return redirect(url_for('product_detail', product_id=product_id))

    reviews = db.execute('''SELECT r.*, u.username FROM reviews r 
                            JOIN users u ON r.user_id = u.id 
                            WHERE r.product_id = ? ORDER BY r.date DESC''', (product_id,)).fetchall()
    avg_rating = db.execute("SELECT AVG(rating) FROM reviews WHERE product_id = ?", (product_id,)).fetchone()[0] or 0
    avg_rating = round(float(avg_rating), 1)

    return render_template_string(HTML_TEMPLATE, page='product_detail', product=product, 
                                   reviews=reviews, avg_rating=avg_rating, user=get_current_user())

# ====================== PROFILE ======================
@app.route('/profile', methods=['GET', 'POST'])
def profile():
    if 'user_id' not in session:
        flash("Please login first.", "danger")
        return redirect(url_for('login'))
    db = get_db()
    user = db.execute("SELECT * FROM users WHERE id = ?", (session['user_id'],)).fetchone()
    if request.method == 'POST':
        new_username = request.form.get('username', user['username'])
        new_email = request.form.get('email', user['email'])
        new_phone = request.form.get('phone', user['phone'])
        new_password = request.form.get('new_password')
        try:
            db.execute("UPDATE users SET username = ?, email = ?, phone = ? WHERE id = ?", 
                       (new_username, new_email, new_phone, session['user_id']))
            if new_password:
                db.execute("UPDATE users SET password = ? WHERE id = ?", 
                           (generate_password_hash(new_password), session['user_id']))
            db.commit()
            flash("Profile updated successfully!", "success")
        except sqlite3.IntegrityError:
            flash("Username or email already taken.", "danger")
    return render_template_string(HTML_TEMPLATE, page='profile', user=user)

# ====================== HTML TEMPLATE ======================
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>TK Worldwide Clothing • Global Style, Timeless Fashion</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
    <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.1/css/all.min.css" rel="stylesheet">
    <link href="https://fonts.googleapis.com/css2?family=Playfair+Display:wght@400;700&family=Inter:wght@300;400;600&display=swap" rel="stylesheet">
    <style>
        :root { 
            --bg: #ffffff; 
            --card: #fff5f8; 
            --pink: #ff69b4; 
            --pink-dark: #ff1493;
            --pink-light: #ffb6c1;
            --text: #333333;
            --text-muted: #666666;
        }
        body { 
            background: var(--bg); 
            color: var(--text); 
            font-family: 'Inter', sans-serif;
        }
        h1, h2, h3, h4, h5, .navbar-brand {
            font-family: 'Playfair Display', serif;
        }
        .navbar { 
            background: rgba(255,255,255,0.98) !important; 
            backdrop-filter: blur(10px);
            border-bottom: 2px solid var(--pink-light);
            box-shadow: 0 2px 20px rgba(255,105,180,0.1);
        }
        .navbar-brand {
            color: var(--pink-dark) !important;
            font-size: 1.5rem;
            font-weight: 700;
        }
        .nav-link {
            color: var(--text) !important;
            transition: all 0.3s;
            font-weight: 500;
        }
        .nav-link:hover {
            color: var(--pink-dark) !important;
        }
        .product-card { 
            background: white; 
            transition: all 0.3s ease;
            border: 1px solid #ffe4ec;
            border-radius: 15px;
            overflow: hidden;
        }
        .product-card:hover { 
            transform: translateY(-10px); 
            box-shadow: 0 20px 40px rgba(255,105,180,0.15);
            border-color: var(--pink);
        }
        .btn-pink { 
            background: linear-gradient(135deg, var(--pink), var(--pink-dark)); 
            color: white; 
            font-weight: 600;
            border: none;
            transition: all 0.3s;
            border-radius: 25px;
            padding: 10px 25px;
        }
        .btn-pink:hover {
            transform: translateY(-2px);
            box-shadow: 0 5px 20px rgba(255,105,180,0.4);
            color: white;
        }
        .btn-outline-pink {
            border: 2px solid var(--pink);
            color: var(--pink);
            background: transparent;
            transition: all 0.3s;
            border-radius: 25px;
        }
        .btn-outline-pink:hover {
            background: var(--pink);
            color: white;
        }
        .chat-box { 
            height: 400px; 
            overflow-y: auto; 
            background: white; 
            padding: 20px; 
            border-radius: 15px;
            border: 2px solid #ffe4ec;
        }
        .chat-message {
            margin-bottom: 15px;
            padding: 12px 18px;
            border-radius: 20px;
            max-width: 80%;
            animation: fadeIn 0.3s ease;
        }
        @keyframes fadeIn {
            from { opacity: 0; transform: translateY(10px); }
            to { opacity: 1; transform: translateY(0); }
        }
        .chat-message.user {
            background: linear-gradient(135deg, var(--pink), var(--pink-dark));
            color: white;
            margin-left: auto;
            text-align: right;
        }
        .chat-message.bot {
            background: #fff5f8;
            color: var(--text);
            border: 1px solid #ffe4ec;
        }
        .chat-message.admin {
            background: #e8f5e9;
            color: #2e7d32;
            border: 1px solid #c8e6c9;
        }
        .hero-section {
            background: linear-gradient(135deg, rgba(255,240,245,0.95), rgba(255,255,255,0.95)), url('https://images.unsplash.com/photo-1558171813-4c088753af8f?w=1600');
            background-size: cover;
            background-position: center;
            padding: 120px 0 80px;
            margin-top: -20px;
        }
        .form-control, .form-select {
            background: white !important;
            border: 2px solid #ffe4ec;
            color: var(--text) !important;
            border-radius: 10px;
        }
        .form-control:focus, .form-select:focus {
            border-color: var(--pink);
            box-shadow: 0 0 0 0.2rem rgba(255,105,180,0.25);
        }
        .badge-pink {
            background: var(--pink);
            color: white;
        }
        .text-pink {
            color: var(--pink-dark);
        }
        .border-pink {
            border-color: var(--pink) !important;
        }
        .table-light {
            background: white;
        }
        .table-light th {
            border-color: #ffe4ec;
            color: var(--pink-dark);
            background: #fff5f8;
        }
        .alert {
            border: none;
            border-radius: 10px;
        }
        .alert-success {
            background: rgba(40,167,69,0.1);
            color: #28a745;
            border: 1px solid rgba(40,167,69,0.2);
        }
        .alert-danger {
            background: rgba(220,53,69,0.1);
            color: #dc3545;
            border: 1px solid rgba(220,53,69,0.2);
        }
        .alert-warning {
            background: rgba(255,193,7,0.1);
            color: #856404;
            border: 1px solid rgba(255,193,7,0.2);
        }
        .rating-stars {
            color: #ffc107;
        }
        .review-card {
            background: white;
            border-left: 4px solid var(--pink);
            padding: 20px;
            margin-bottom: 15px;
            border-radius: 0 10px 10px 0;
            box-shadow: 0 2px 10px rgba(0,0,0,0.05);
        }
        .stat-card {
            background: white;
            border-radius: 15px;
            padding: 25px;
            box-shadow: 0 5px 20px rgba(255,105,180,0.1);
            border: 1px solid #ffe4ec;
            transition: transform 0.3s;
        }
        .stat-card:hover {
            transform: translateY(-5px);
        }
        .stat-icon {
            width: 60px;
            height: 60px;
            background: linear-gradient(135deg, var(--pink), var(--pink-dark));
            border-radius: 15px;
            display: flex;
            align-items: center;
            justify-content: center;
            color: white;
            font-size: 24px;
            margin-bottom: 15px;
        }
        .notification-badge {
            position: absolute;
            top: -5px;
            right: -5px;
            background: #dc3545;
            color: white;
            border-radius: 50%;
            width: 20px;
            height: 20px;
            font-size: 12px;
            display: flex;
            align-items: center;
            justify-content: center;
        }
        .typing-indicator {
            display: none;
            padding: 10px;
            color: var(--pink);
        }
        .typing-indicator.active {
            display: block;
        }
        .fade-in {
            animation: fadeIn 0.5s ease;
        }
        .smooth-scroll {
            scroll-behavior: smooth;
        }
        /* Custom scrollbar */
        ::-webkit-scrollbar {
            width: 8px;
        }
        ::-webkit-scrollbar-track {
            background: #f1f1f1;
        }
        ::-webkit-scrollbar-thumb {
            background: var(--pink);
            border-radius: 4px;
        }
        ::-webkit-scrollbar-thumb:hover {
            background: var(--pink-dark);
        }
    </style>
</head>
<body class="smooth-scroll">

<nav class="navbar navbar-expand-lg fixed-top">
    <div class="container">
        <a class="navbar-brand" href="/"><i class="fas fa-gem me-2"></i>TK Worldwide</a>
        <button class="navbar-toggler" type="button" data-bs-toggle="collapse" data-bs-target="#navbarNav">
            <span class="navbar-toggler-icon"></span>
        </button>
        <div class="collapse navbar-collapse" id="navbarNav">
            <ul class="navbar-nav me-auto">
                <li class="nav-item"><a class="nav-link" href="/"><i class="fas fa-home me-1"></i> Home</a></li>
                <li class="nav-item"><a class="nav-link" href="/ai-stylist"><i class="fas fa-magic me-1"></i> AI Stylist</a></li>
                <li class="nav-item"><a class="nav-link" href="/customer-care"><i class="fas fa-headset me-1"></i> Support</a></li>
                <li class="nav-item"><a class="nav-link" href="/cart"><i class="fas fa-shopping-cart me-1"></i> Cart</a></li>
                <li class="nav-item"><a class="nav-link" href="/orders"><i class="fas fa-box me-1"></i> My Orders</a></li>
            </ul>
            <div class="d-flex align-items-center">
                {% if user and user['is_admin'] %}
                <a href="/admin" class="btn btn-warning me-2 position-relative">
                    <i class="fas fa-cog"></i> Admin
                    {% if notifications and notifications|length > 0 %}
                    <span class="notification-badge">{{ notifications|length }}</span>
                    {% endif %}
                </a>
                {% endif %}
                {% if user %}
                <a href="/profile" class="btn btn-outline-dark me-2"><i class="fas fa-user"></i> {{ user['username'] }}</a>
                <a href="/logout" class="btn btn-outline-danger"><i class="fas fa-sign-out-alt"></i> Logout</a>
                {% else %}
                <a href="/login" class="btn btn-outline-dark me-2">Login</a>
                <a href="/register" class="btn btn-pink">Register</a>
                {% endif %}
            </div>
        </div>
    </div>
</nav>

<div class="container mt-5 pt-4">
    {% with messages = get_flashed_messages(with_categories=true) %}
        {% if messages %}
            {% for cat, msg in messages %}
            <div class="alert alert-{{ 'success' if cat=='success' else 'danger' if cat=='danger' else 'warning' if cat=='warning' else 'info' }} alert-dismissible fade show mt-3">
                {{ msg }}
                <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
            </div>
            {% endfor %}
        {% endif %}
    {% endwith %}

    {% if page == 'home' %}
    <div class="hero-section text-center mb-5 rounded">
        <h1 class="display-4 mb-3 text-pink">Global Style, Timeless Fashion</h1>
        <p class="lead mb-4 text-muted">Discover authentic Nigerian fashion crafted by world-renowned designers</p>
        <a href="#collection" class="btn btn-pink btn-lg px-5">Shop Now</a>
    </div>
    
    <h2 id="collection" class="text-center mb-5 text-pink">
        <i class="fas fa-heart me-2"></i>Featured Collection
    </h2>
    <div class="row g-4 mb-5">
        {% for p in products %}
        <div class="col-md-6 col-lg-3 fade-in">
            <div class="product-card card h-100">
                <div style="height:300px; overflow:hidden;">
                    <img src="{{ p['image_url'] }}" class="card-img-top" style="height:100%; width:100%; object-fit:cover; transition:transform 0.3s;" onmouseover="this.style.transform='scale(1.05)'" onmouseout="this.style.transform='scale(1)'">
                </div>
                <div class="card-body d-flex flex-column">
                    <span class="badge bg-secondary mb-2" style="width:fit-content;">{{ p['category'] }}</span>
                    <h5 class="card-title">{{ p['name'] }}</h5>
                    <p class="text-muted mb-1"><i class="fas fa-user-tie me-1"></i> {{ p['designer'] }}</p>
                    <p class="fw-bold fs-5 mt-auto text-pink">₦{{ "{:,.0f}".format(p['price']) }}</p>
                    <a href="/product/{{ p['id'] }}" class="btn btn-outline-pink w-100">View Details</a>
                </div>
            </div>
        </div>
        {% endfor %}
    </div>
    
    <div class="row text-center py-5 my-5 border-top border-bottom border-pink">
        <div class="col-md-4 mb-4">
            <i class="fas fa-shipping-fast fa-3x mb-3 text-pink"></i>
            <h4>Fast Delivery</h4>
            <p class="text-muted">3-5 business days nationwide</p>
        </div>
        <div class="col-md-4 mb-4">
            <i class="fas fa-shield-alt fa-3x mb-3 text-pink"></i>
            <h4>Secure Payment</h4>
            <p class="text-muted">100% secure checkout</p>
        </div>
        <div class="col-md-4 mb-4">
            <i class="fas fa-undo fa-3x mb-3 text-pink"></i>
            <h4>Easy Returns</h4>
            <p class="text-muted">14-day return policy</p>
        </div>
    </div>
    {% endif %}

    {% if page == 'product_detail' %}
    <div class="row mt-4 fade-in">
        <div class="col-md-6 mb-4">
            <div class="position-sticky" style="top:100px;">
                <img src="{{ product['image_url'] }}" class="img-fluid rounded shadow" style="width:100%; max-height:600px; object-fit:cover; border-radius:15px;">
            </div>
        </div>
        <div class="col-md-6">
            <span class="badge bg-secondary mb-2">{{ product['category'] }}</span>
            <h2>{{ product['name'] }}</h2>
            <p class="text-muted"><i class="fas fa-user-tie me-1"></i> Designed by {{ product['designer'] }}</p>
            <h3 class="mb-3 text-pink">₦{{ "{:,.0f}".format(product['price']) }}</h3>
            
            <div class="card p-4 mb-4" style="background:#fff5f8; border:none; border-radius:15px;">
                <h5>Description</h5>
                <p class="mb-0">{{ product['description'] or 'Beautiful fashion piece crafted with premium materials.' }}</p>
                <hr style="border-color:#ffe4ec;">
                <p class="mb-1"><strong>Available Sizes:</strong> {{ product['sizes'] }}</p>
                <p class="mb-1"><strong>Colors:</strong> {{ product['colors'] }}</p>
                <p class="mb-0"><strong>Stock:</strong> {{ product['stock'] }} units available</p>
            </div>
            
            {% if product['stock'] > 0 %}
            <form action="/add_to_cart/{{ product['id'] }}" method="post" class="mb-5">
                <div class="row g-2 align-items-center">
                    <div class="col-auto">
                        <label class="form-label mb-0">Quantity:</label>
                    </div>
                    <div class="col-auto">
                        <input type="number" name="quantity" value="1" min="1" max="{{ product['stock'] }}" class="form-control" style="width:80px;">
                    </div>
                    <div class="col">
                        <button type="submit" class="btn btn-pink btn-lg w-100"><i class="fas fa-cart-plus me-2"></i>Add to Cart</button>
                    </div>
                </div>
            </form>
            {% else %}
            <div class="alert alert-warning mb-5">Out of Stock</div>
            {% endif %}
            
            <div class="mb-4">
                <h4 class="mb-3">Customer Reviews <span class="fs-5 text-muted">({{ reviews|length }})</span></h4>
                <div class="d-flex align-items-center mb-3">
                    <h2 class="mb-0 me-2">{{ avg_rating }}</h2>
                    <div class="rating-stars fs-4">
                        {% for i in range(5) %}
                            {% if i < avg_rating|int %}
                                <i class="fas fa-star"></i>
                            {% else %}
                                <i class="far fa-star"></i>
                            {% endif %}
                        {% endfor %}
                    </div>
                </div>
                
                {% for r in reviews %}
                <div class="review-card">
                    <div class="d-flex justify-content-between align-items-start">
                        <strong><i class="fas fa-user-circle me-1 text-pink"></i> {{ r['username'] }}</strong>
                        <small class="text-muted">{{ r['date'][:10] }}</small>
                    </div>
                    <div class="rating-stars mb-2">
                        {% for i in range(5) %}
                            {% if i < r['rating'] %}
                                <i class="fas fa-star"></i>
                            {% else %}
                                <i class="far fa-star"></i>
                            {% endif %}
                        {% endfor %}
                    </div>
                    <p class="mb-0">{{ r['comment'] }}</p>
                </div>
                {% else %}
                <p class="text-muted">No reviews yet. Be the first to review!</p>
                {% endfor %}
            </div>
            
            {% if user %}
            <div class="card p-4" style="background:#fff5f8; border:none; border-radius:15px;">
                <h5>Write a Review</h5>
                <form method="POST">
                    <div class="mb-3">
                        <label class="form-label">Rating</label>
                        <select name="rating" class="form-select">
                            <option value="5">5 Stars - Excellent</option>
                            <option value="4">4 Stars - Very Good</option>
                            <option value="3">3 Stars - Good</option>
                            <option value="2">2 Stars - Fair</option>
                            <option value="1">1 Star - Poor</option>
                        </select>
                    </div>
                    <div class="mb-3">
                        <label class="form-label">Your Review</label>
                        <textarea name="comment" class="form-control" rows="3" placeholder="Share your experience..." required></textarea>
                    </div>
                    <button type="submit" class="btn btn-pink">Submit Review</button>
                </form>
            </div>
            {% else %}
            <div class="alert alert-info">
                <a href="/login" class="alert-link">Login</a> to write a review.
            </div>
            {% endif %}
        </div>
    </div>
    {% endif %}

    {% if page == 'cart' %}
    <h2 class="mb-4 text-pink"><i class="fas fa-shopping-cart me-2"></i>Your Shopping Cart</h2>
    {% if cart_items %}
    <div class="row fade-in">
        <div class="col-lg-8">
            {% for item in cart_items %}
            <div class="d-flex align-items-center p-3 rounded mb-3" style="background:white; border:1px solid #ffe4ec;">
                <img src="{{ item['image_url'] }}" style="width:100px;height:100px;object-fit:cover; border-radius:10px;" class="me-3">
                <div class="flex-grow-1">
                    <h5 class="mb-1">{{ item['name'] }}</h5>
                    <p class="text-muted mb-1">{{ item['designer'] }}</p>
                    <p class="mb-0">₦{{ "{:,.0f}".format(item['price']) }} × {{ item['quantity'] }} = <strong class="text-pink">₦{{ "{:,.0f}".format(item['price'] * item['quantity']) }}</strong></p>
                </div>
                <a href="/remove_from_cart/{{ item['cart_id'] }}" class="btn btn-outline-danger btn-sm"><i class="fas fa-trash"></i></a>
            </div>
            {% endfor %}
        </div>
        <div class="col-lg-4">
            <div class="card p-4 sticky-top" style="top:100px; background:#fff5f8; border:none; border-radius:15px;">
                <h4 class="mb-3">Order Summary</h4>
                <div class="d-flex justify-content-between mb-2">
                    <span>Subtotal</span>
                    <span>₦{{ "{:,.0f}".format(total) }}</span>
                </div>
                <div class="d-flex justify-content-between mb-2">
                    <span>Shipping</span>
                    <span class="text-success">Free</span>
                </div>
                <hr style="border-color:#ffe4ec;">
                <div class="d-flex justify-content-between mb-4">
                    <strong>Total</strong>
                    <strong class="fs-4 text-pink">₦{{ "{:,.0f}".format(total) }}</strong>
                </div>
                <form action="/checkout" method="post">
                    <button type="submit" class="btn btn-pink w-100 btn-lg"><i class="fas fa-credit-card me-2"></i>Checkout</button>
                </form>
                <a href="/" class="btn btn-outline-dark w-100 mt-2">Continue Shopping</a>
            </div>
        </div>
    </div>
    {% else %}
    <div class="text-center py-5 fade-in">
        <i class="fas fa-shopping-basket fa-4x mb-3 text-muted"></i>
        <h3>Your cart is empty</h3>
        <p class="text-muted">Looks like you haven't added anything yet.</p>
        <a href="/" class="btn btn-pink btn-lg mt-3">Start Shopping</a>
    </div>
    {% endif %}
    {% endif %}

    {% if page == 'orders' %}
    <h2 class="mb-4 text-pink"><i class="fas fa-box me-2"></i>My Orders & Tracking</h2>
    {% if orders %}
        {% for o in orders %}
        <div class="card mb-4 fade-in" style="border:1px solid #ffe4ec; border-radius:15px;">
            <div class="card-header d-flex justify-content-between align-items-center" style="background:#fff5f8; border-bottom:1px solid #ffe4ec;">
                <div>
                    <strong>Order #{{ o['id'] }}</strong>
                    <span class="text-muted ms-2">{{ o['date'][:10] }}</span>
                </div>
                <span class="badge bg-{{ 'success' if o['status']=='Delivered' else 'info' if o['status']=='Shipped' else 'warning' }}">
                    {{ o['status'] }}
                </span>
            </div>
            <div class="card-body">
                <div class="row">
                    <div class="col-md-6">
                        <p class="mb-1"><strong>Items:</strong> {{ o['items'] or 'N/A' }}</p>
                        <p class="mb-1"><strong>Total:</strong> <span class="text-pink">₦{{ "{:,.0f}".format(o['total']) }}</span></p>
                    </div>
                    <div class="col-md-6">
                        <p class="mb-1"><strong>Tracking #:</strong> <code>{{ o['tracking_number'] or 'Pending' }}</code></p>
                        <p class="mb-0"><strong>Est. Delivery:</strong> {{ o['estimated_delivery'] or 'TBD' }}</p>
                    </div>
                </div>
            </div>
        </div>
        {% endfor %}
    {% else %}
    <div class="text-center py-5 fade-in">
        <i class="fas fa-box-open fa-4x mb-3 text-muted"></i>
        <h3>No orders yet</h3>
        <p class="text-muted">Your order history will appear here.</p>
        <a href="/" class="btn btn-pink btn-lg mt-3">Shop Now</a>
    </div>
    {% endif %}
    {% endif %}

    {% if page == 'customer_care' %}
    <h2 class="text-center mb-5 text-pink"><i class="fas fa-headset me-2"></i>Customer Care</h2>
    <div class="row fade-in">
        <div class="col-md-4 mb-4">
            <div class="card p-4 text-center h-100" style="border:1px solid #ffe4ec; border-radius:15px;">
                <i class="fas fa-phone-alt fa-3x mb-3 text-pink"></i>
                <h4>Call Us</h4>
                <p class="text-muted">Mon-Fri, 9am-6pm WAT</p>
                <a href="tel:+2348036454804" class="btn btn-success btn-lg">
                    <i class="fas fa-phone me-2"></i>+2348036454804
                </a>
            </div>
        </div>
        <div class="col-md-8 mb-4">
            <div class="card p-4 h-100" style="border:1px solid #ffe4ec; border-radius:15px;">
                <h4 class="text-center mb-3"><i class="fas fa-comments me-2 text-pink"></i>Live Chat</h4>
                <div id="chat-box" class="chat-box mb-3">
                    <div class="text-center text-muted mt-5" id="empty-chat">
                        <i class="fas fa-comments fa-2x mb-2 text-pink"></i>
                        <p>Start a conversation with our support team...</p>
                    </div>
                </div>
                <div class="typing-indicator" id="typing-indicator">
                    <i class="fas fa-spinner fa-spin me-2"></i>Support is typing...
                </div>
                <form id="chat-form" class="d-flex gap-2">
                    <input type="text" id="chat-input" class="form-control" placeholder="Type your message..." required>
                    <button type="submit" class="btn btn-pink"><i class="fas fa-paper-plane"></i></button>
                </form>
            </div>
        </div>
    </div>
    
    <script>
    let chatInterval;
    const chatBox = document.getElementById('chat-box');
    const chatForm = document.getElementById('chat-form');
    const chatInput = document.getElementById('chat-input');
    
    function loadMessages() {
        fetch('/chat/history')
            .then(r => r.json())
            .then(data => {
                if (data.messages.length > 0) {
                    document.getElementById('empty-chat').style.display = 'none';
                    chatBox.innerHTML = '';
                    data.messages.forEach(msg => {
                        const div = document.createElement('div');
                        div.className = `chat-message ${msg.sender}`;
                        div.innerHTML = `<div>${msg.text}</div><small class="opacity-50">${msg.time}</small>`;
                        chatBox.appendChild(div);
                    });
                    chatBox.scrollTop = chatBox.scrollHeight;
                }
            });
    }
    
    chatForm.addEventListener('submit', function(e) {
        e.preventDefault();
        const msg = chatInput.value.trim();
        if (!msg) return;
        
        fetch('/chat/send', {
            method: 'POST',
            headers: {'Content-Type': 'application/x-www-form-urlencoded'},
            body: 'message=' + encodeURIComponent(msg)
        }).then(() => {
            chatInput.value = '';
            loadMessages();
        });
    });
    
    // Auto-refresh chat every 3 seconds
    chatInterval = setInterval(loadMessages, 3000);
    loadMessages();
    </script>
    {% endif %}

    {% if page == 'ai_stylist' %}
    <div class="text-center mb-5 fade-in">
        <h2 class="text-pink"><i class="fas fa-magic me-2"></i>AI Fashion Stylist</h2>
        <p class="lead text-muted">Your personal fashion companion 💕</p>
    </div>
    <div class="row justify-content-center fade-in">
        <div class="col-md-8 col-lg-6">
                        <div class="card p-4" style="border:1px solid #ffe4ec; border-radius:15px;">
                <div id="ai-chat-box" class="chat-box mb-3" style="height: 400px;">
                    {% if not conversation %}
                    <div class="text-center text-muted mt-5">
                        <i class="fas fa-robot fa-3x mb-3 text-pink"></i>
                        <p>Hi there! 👋 I'm your AI stylist. Ask me anything about fashion!</p>
                        <div class="mt-3">
                            <button onclick="quickAsk('What should I wear to a wedding?')" class="btn btn-outline-pink btn-sm m-1">Wedding outfit? 💒</button>
                            <button onclick="quickAsk('Office wear suggestions')" class="btn btn-outline-pink btn-sm m-1">Office wear? 👔</button>
                            <button onclick="quickAsk('Casual weekend look')" class="btn btn-outline-pink btn-sm m-1">Casual look? 👗</button>
                            <button onclick="quickAsk('Kids fashion ideas')" class="btn btn-outline-pink btn-sm m-1">Kids fashion? 🧒</button>
                        </div>
                    </div>
                    {% else %}
                        {% for conv in conversation %}
                        <div class="chat-message user">
                            <div>{{ conv.user }}</div>
                        </div>
                        <div class="chat-message bot">
                            <div>{{ conv.bot }}</div>
                        </div>
                        {% endfor %}
                    {% endif %}
                </div>
                <div class="typing-indicator" id="ai-typing">
                    <i class="fas fa-spinner fa-spin me-2"></i>AI Stylist is thinking...
                </div>
                <form id="ai-form" class="d-flex gap-2">
                    <input type="text" id="ai-input" class="form-control" placeholder="Ask me anything about fashion..." required>
                    <button type="submit" class="btn btn-pink"><i class="fas fa-paper-plane"></i></button>
                </form>
                <button onclick="clearConversation()" class="btn btn-outline-secondary btn-sm mt-2 w-100">
                    <i class="fas fa-trash me-1"></i>Clear Conversation
                </button>
            </div>
        </div>
    </div>
    
    <script>
    const aiChatBox = document.getElementById('ai-chat-box');
    const aiForm = document.getElementById('ai-form');
    const aiInput = document.getElementById('ai-input');
    const aiTyping = document.getElementById('ai-typing');
    
    function quickAsk(question) {
        aiInput.value = question;
        aiForm.dispatchEvent(new Event('submit'));
    }
    
    function clearConversation() {
        fetch('/ai-stylist/clear', {method: 'POST'})
            .then(() => location.reload());
    }
    
    function scrollToBottom() {
        aiChatBox.scrollTop = aiChatBox.scrollHeight;
    }
    
    aiForm.addEventListener('submit', function(e) {
        e.preventDefault();
        const msg = aiInput.value.trim();
        if (!msg) return;
        
        // Add user message
        const userDiv = document.createElement('div');
        userDiv.className = 'chat-message user';
        userDiv.innerHTML = '<div>' + msg + '</div>';
        aiChatBox.appendChild(userDiv);
        aiInput.value = '';
        scrollToBottom();
        
        // Show typing
        aiTyping.classList.add('active');
        
        // Get AI response
        fetch('/ai-stylist', {
            method: 'POST',
            headers: {'Content-Type': 'application/x-www-form-urlencoded'},
            body: 'query=' + encodeURIComponent(msg)
        })
        .then(r => r.json())
        .then(data => {
            aiTyping.classList.remove('active');
            const botDiv = document.createElement('div');
            botDiv.className = 'chat-message bot';
            botDiv.innerHTML = '<div>' + data.response + '</div>';
            aiChatBox.appendChild(botDiv);
            scrollToBottom();
        });
    });
    
    // Smooth scroll on load
    window.onload = scrollToBottom;
    </script>
    {% endif %}

    {% if page == 'profile' %}
    <div class="row justify-content-center fade-in">
        <div class="col-md-8 col-lg-6">
            <h2 class="mb-4 text-center text-pink"><i class="fas fa-user-circle me-2"></i>My Profile</h2>
            <div class="card p-4" style="border:1px solid #ffe4ec; border-radius:15px;">
                <form method="POST">
                    <div class="mb-3">
                        <label class="form-label">Username</label>
                        <div class="input-group">
                            <span class="input-group-text bg-white border-pink"><i class="fas fa-user text-pink"></i></span>
                            <input type="text" name="username" value="{{ user['username'] }}" class="form-control" required>
                        </div>
                    </div>
                    <div class="mb-3">
                        <label class="form-label">Email</label>
                        <div class="input-group">
                            <span class="input-group-text bg-white border-pink"><i class="fas fa-envelope text-pink"></i></span>
                            <input type="email" name="email" value="{{ user['email'] }}" class="form-control" required>
                        </div>
                    </div>
                    <div class="mb-3">
                        <label class="form-label">Phone Number</label>
                        <div class="input-group">
                            <span class="input-group-text bg-white border-pink"><i class="fas fa-phone text-pink"></i></span>
                            <input type="tel" name="phone" value="{{ user['phone'] or '' }}" class="form-control" placeholder="+234...">
                        </div>
                    </div>
                    <div class="mb-4">
                        <label class="form-label">New Password <small class="text-muted">(leave blank to keep current)</small></label>
                        <div class="input-group">
                            <span class="input-group-text bg-white border-pink"><i class="fas fa-lock text-pink"></i></span>
                            <input type="password" name="new_password" class="form-control" placeholder="••••••••">
                        </div>
                    </div>
                    <button type="submit" class="btn btn-pink w-100"><i class="fas fa-save me-2"></i>Update Profile</button>
                </form>
            </div>
        </div>
    </div>
    {% endif %}

    {% if page == 'register' %}
    <div class="row justify-content-center mt-5 fade-in">
        <div class="col-md-6 col-lg-5">
            <div class="card p-4" style="border:1px solid #ffe4ec; border-radius:15px;">
                {% if step == '1' %}
                <h2 class="text-center mb-4 text-pink"><i class="fas fa-user-plus me-2"></i>Create Account</h2>
                <form method="POST">
                    <input type="hidden" name="step" value="1">
                    <div class="mb-3">
                        <label class="form-label">Username</label>
                        <input type="text" name="username" class="form-control" required>
                    </div>
                    <div class="mb-3">
                        <label class="form-label">Email</label>
                        <input type="email" name="email" class="form-control" required>
                    </div>
                    <div class="mb-3">
                        <label class="form-label">Phone Number <small class="text-muted">(optional)</small></label>
                        <input type="tel" name="phone" class="form-control" placeholder="+234...">
                    </div>
                    <div class="mb-3">
                        <label class="form-label">Password</label>
                        <input type="password" name="password" class="form-control" required minlength="6">
                    </div>
                    <div class="mb-3">
                        <label class="form-label">Verification Method</label>
                        <div class="d-flex gap-3">
                            <div class="form-check">
                                <input class="form-check-input" type="radio" name="otp_method" value="email" checked>
                                <label class="form-check-label"><i class="fas fa-envelope me-1"></i>Email</label>
                            </div>
                            <div class="form-check">
                                <input class="form-check-input" type="radio" name="otp_method" value="phone">
                                <label class="form-check-label"><i class="fas fa-sms me-1"></i>SMS</label>
                            </div>
                        </div>
                    </div>
                    <button type="submit" class="btn btn-pink w-100 mb-3">Continue</button>
                    <p class="text-center mb-0">Already have an account? <a href="/login" class="text-pink">Login</a></p>
                </form>
                
                {% elif step == '2' %}
                <h2 class="text-center mb-4 text-pink"><i class="fas fa-shield-alt me-2"></i>Verify Account</h2>
                <p class="text-center text-muted mb-4">Enter the 6-digit code sent to {{ email }}</p>
                <form method="POST" id="otp-form">
                    <input type="hidden" name="step" value="2">
                    <input type="hidden" name="email" value="{{ email }}">
                    <div class="mb-4">
                        <input type="text" name="otp" class="form-control form-control-lg text-center" 
                               style="letter-spacing: 10px; font-size: 24px;" maxlength="6" placeholder="000000" required>
                    </div>
                    <button type="submit" class="btn btn-pink w-100 mb-3">Verify Account</button>
                </form>
                <form method="POST" action="/resend-otp" id="resend-form">
                    <input type="hidden" name="email" value="{{ email }}">
                    <input type="hidden" name="otp_method" value="{{ otp_method }}">
                    <button type="submit" class="btn btn-outline-pink w-100" id="resend-btn">
                        Resend Code <span id="timer"></span>
                    </button>
                </form>
                <script>
                let timeLeft = 60;
                const timerSpan = document.getElementById('timer');
                const resendBtn = document.getElementById('resend-btn');
                resendBtn.disabled = true;
                
                const timer = setInterval(() => {
                    timerSpan.textContent = '(' + timeLeft + 's)';
                    timeLeft--;
                    if (timeLeft < 0) {
                        clearInterval(timer);
                        resendBtn.disabled = false;
                        timerSpan.textContent = '';
                    }
                }, 1000);
                
                document.getElementById('resend-form').addEventListener('submit', function(e) {
                    e.preventDefault();
                    fetch('/resend-otp', {
                        method: 'POST',
                        body: new FormData(this)
                    }).then(r => r.json()).then(data => {
                        alert(data.message);
                        location.reload();
                    });
                });
                </script>
                {% endif %}
            </div>
        </div>
    </div>
    {% endif %}

    {% if page == 'login' %}
    <div class="row justify-content-center mt-5 fade-in">
        <div class="col-md-6 col-lg-4">
            <div class="card p-4" style="border:1px solid #ffe4ec; border-radius:15px;">
                <h2 class="text-center mb-4 text-pink"><i class="fas fa-sign-in-alt me-2"></i>Welcome Back</h2>
                <form method="POST">
                    <div class="mb-3">
                        <label class="form-label">Username</label>
                        <input type="text" name="username" class="form-control" required>
                    </div>
                    <div class="mb-4">
                        <label class="form-label">Password</label>
                        <input type="password" name="password" class="form-control" required>
                    </div>
                    <button type="submit" class="btn btn-pink w-100 mb-3">Login</button>
                    <p class="text-center mb-0">Don't have an account? <a href="/register" class="text-pink">Register</a></p>
                </form>
            </div>
        </div>
    </div>
    {% endif %}

    {% if page == 'admin' %}
    <h2 class="mb-4 text-pink"><i class="fas fa-cog me-2"></i>Admin Dashboard</h2>
    
    <!-- Stats Cards -->
    <div class="row mb-4">
        <div class="col-md-3 mb-3">
            <div class="stat-card">
                <div class="stat-icon"><i class="fas fa-users"></i></div>
                <h3 class="mb-1">{{ stats.total_users }}</h3>
                <p class="text-muted mb-0">Total Users</p>
            </div>
        </div>
        <div class="col-md-3 mb-3">
            <div class="stat-card">
                <div class="stat-icon"><i class="fas fa-shopping-bag"></i></div>
                <h3 class="mb-1">{{ stats.total_orders }}</h3>
                <p class="text-muted mb-0">Total Orders</p>
            </div>
        </div>
        <div class="col-md-3 mb-3">
            <div class="stat-card">
                <div class="stat-icon"><i class="fas fa-naira-sign"></i></div>
                <h3 class="mb-1">₦{{ "{:,.0f}".format(stats.total_revenue) }}</h3>
                <p class="text-muted mb-0">Total Revenue</p>
            </div>
        </div>
        <div class="col-md-3 mb-3">
            <div class="stat-card">
                <div class="stat-icon"><i class="fas fa-box"></i></div>
                <h3 class="mb-1">{{ stats.total_products }}</h3>
                <p class="text-muted mb-0">Products</p>
            </div>
        </div>
    </div>
    
    <div class="row mb-4">
        <div class="col-md-4 mb-3">
            <div class="stat-card" style="border-left: 4px solid #ffc107;">
                <h4 class="text-warning">{{ stats.pending_orders }}</h4>
                <p class="text-muted mb-0">Pending Orders</p>
            </div>
        </div>
        <div class="col-md-4 mb-3">
            <div class="stat-card" style="border-left: 4px solid #17a2b8;">
                <h4 class="text-info">{{ stats.today_orders }}</h4>
                <p class="text-muted mb-0">Today's Orders</p>
            </div>
        </div>
        <div class="col-md-4 mb-3">
            <div class="stat-card" style="border-left: 4px solid #dc3545;">
                <h4 class="text-danger">{{ stats.unread_chats }}</h4>
                <p class="text-muted mb-0">Unread Messages</p>
            </div>
        </div>
    </div>
    
    <!-- Low Stock Alert -->
    {% if stats.low_stock %}
    <div class="alert alert-warning mb-4">
        <h5><i class="fas fa-exclamation-triangle me-2"></i>Low Stock Alert</h5>
        <ul class="mb-0">
            {% for item in stats.low_stock %}
            <li>{{ item['name'] }} - Only {{ item['stock'] }} left!</li>
            {% endfor %}
        </ul>
    </div>
    {% endif %}
    
    <ul class="nav nav-tabs mb-4" id="adminTab" role="tablist">
        <li class="nav-item" role="presentation">
            <button class="nav-link active text-pink" id="products-tab" data-bs-toggle="tab" data-bs-target="#products" type="button">Products</button>
        </li>
        <li class="nav-item" role="presentation">
            <button class="nav-link text-pink" id="orders-tab" data-bs-toggle="tab" data-bs-target="#orders" type="button">Orders</button>
        </li>
        <li class="nav-item" role="presentation">
            <button class="nav-link text-pink" id="users-tab" data-bs-toggle="tab" data-bs-target="#users" type="button">Users</button>
        </li>
        <li class="nav-item" role="presentation">
            <button class="nav-link text-pink" id="chats-tab" data-bs-toggle="tab" data-bs-target="#chats" type="button">
                Live Chats {% if stats.unread_chats > 0 %}<span class="badge bg-danger">{{ stats.unread_chats }}</span>{% endif %}
            </button>
        </li>
    </ul>
    
    <div class="tab-content" id="adminTabContent">
        <!-- Products Tab -->
        <div class="tab-pane fade show active" id="products" role="tabpanel">
            <div class="card p-4 mb-4" style="border:1px solid #ffe4ec;">
                <h5 class="mb-3">Add New Product</h5>
                <form action="/admin/add_product" method="post" class="row g-3">
                    <div class="col-md-6">
                        <input type="text" name="name" class="form-control" placeholder="Product Name" required>
                    </div>
                    <div class="col-md-6">
                        <input type="text" name="designer" class="form-control" placeholder="Designer Name" required>
                    </div>
                    <div class="col-md-3">
                        <input type="number" name="price" class="form-control" placeholder="Price (₦)" required>
                    </div>
                    <div class="col-md-3">
                        <select name="category" class="form-select" required>
                            <option value="Women">Women</option>
                            <option value="Men">Men</option>
                            <option value="Kids">Kids</option>
                            <option value="Materials">Materials</option>
                        </select>
                    </div>
                    <div class="col-md-3">
                        <input type="text" name="sizes" class="form-control" placeholder="Sizes (e.g., S,M,L)" required>
                    </div>
                    <div class="col-md-3">
                        <input type="number" name="stock" class="form-control" placeholder="Stock Qty" required>
                    </div>
                    <div class="col-md-6">
                        <input type="text" name="colors" class="form-control" placeholder="Colors" required>
                    </div>
                    <div class="col-md-6">
                        <input type="url" name="image_url" class="form-control" placeholder="Image URL" required>
                    </div>
                    <div class="col-12">
                        <textarea name="description" class="form-control" rows="2" placeholder="Description"></textarea>
                    </div>
                    <div class="col-12">
                        <button type="submit" class="btn btn-pink"><i class="fas fa-plus me-2"></i>Add Product</button>
                    </div>
                </form>
            </div>
            
            <div class="table-responsive">
                <table class="table table-hover">
                    <thead class="table-light">
                        <tr>
                            <th>ID</th>
                            <th>Image</th>
                            <th>Name</th>
                            <th>Designer</th>
                            <th>Price</th>
                            <th>Stock</th>
                            <th>Actions</th>
                        </tr>
                    </thead>
                    <tbody>
                        {% for p in products %}
                        <tr>
                            <td>{{ p['id'] }}</td>
                            <td><img src="{{ p['image_url'] }}" style="width:50px;height:50px;object-fit:cover;border-radius:8px;"></td>    
