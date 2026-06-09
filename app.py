from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import random
import os

# ==================== إعدادات التطبيق ====================
app = Flask(__name__)
app.config['SECRET_KEY'] = 'graduation-project-2024-secret-key'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///project.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# ==================== نماذج قاعدة البيانات ====================
class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    balance = db.Column(db.Float, default=0.0)
    total_deposited = db.Column(db.Float, default=0.0)
    total_withdrawn = db.Column(db.Float, default=0.0)
    total_won = db.Column(db.Float, default=0.0)
    total_lost = db.Column(db.Float, default=0.0)
    is_admin = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class PaymentMethod(db.Model):
    __tablename__ = 'payment_methods'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    account_number = db.Column(db.String(100))
    holder_name = db.Column(db.String(100))
    payment_link = db.Column(db.String(500))
    instructions = db.Column(db.Text)
    min_deposit = db.Column(db.Float, default=10.0)
    max_deposit = db.Column(db.Float, default=10000.0)
    is_active = db.Column(db.Integer, default=1)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Transaction(db.Model):
    __tablename__ = 'transactions'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    type = db.Column(db.String(50), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    game = db.Column(db.String(50))
    result = db.Column(db.String(200))
    balance_before = db.Column(db.Float)
    balance_after = db.Column(db.Float)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    user = db.relationship('User', backref='transactions')

class WithdrawRequest(db.Model):
    __tablename__ = 'withdraw_requests'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    payment_method = db.Column(db.String(100))
    account_number = db.Column(db.String(100))
    status = db.Column(db.String(20), default='pending')
    admin_note = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    processed_at = db.Column(db.DateTime)
    user = db.relationship('User', backref='withdraw_requests')

class Game(db.Model):
    __tablename__ = 'games'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    min_bet = db.Column(db.Float, default=1.0)
    max_bet = db.Column(db.Float, default=1000.0)
    is_active = db.Column(db.Integer, default=1)

class Promotion(db.Model):
    __tablename__ = 'promotions'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    bonus_percent = db.Column(db.Float)
    is_active = db.Column(db.Integer, default=1)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class SystemSettings(db.Model):
    __tablename__ = 'system_settings'
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(100), unique=True, nullable=False)
    value = db.Column(db.String(500), nullable=False)
    description = db.Column(db.String(300))

class Log(db.Model):
    __tablename__ = 'logs'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer)
    action = db.Column(db.String(100), nullable=False)
    details = db.Column(db.Text)
    ip_address = db.Column(db.String(50))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

# ==================== الدوال المساعدة ====================
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

def get_setting(key, default=None):
    setting = SystemSettings.query.filter_by(key=key).first()
    return setting.value if setting else default

def set_setting(key, value, description=None):
    setting = SystemSettings.query.filter_by(key=key).first()
    if setting:
        setting.value = value
        if description: setting.description = description
    else:
        setting = SystemSettings(key=key, value=value, description=description)
        db.session.add(setting)
    db.session.commit()

def add_log(user_id, action, details=None):
    log = Log(user_id=user_id, action=action, details=details, ip_address=request.remote_addr)
    db.session.add(log)
    db.session.commit()

def add_transaction(user_id, type, amount, game=None, result=None):
    user = User.query.get(user_id)
    balance_before = user.balance
    if type in ['win', 'deposit', 'cashback']:
        user.balance += amount
        if type == 'deposit': user.total_deposited += amount
        elif type == 'win': user.total_won += amount
    elif type in ['loss', 'withdraw']:
        user.balance -= amount
        if type == 'withdraw': user.total_withdrawn += amount
        elif type == 'loss': user.total_lost += amount
    balance_after = user.balance
    transaction = Transaction(user_id=user_id, type=type, amount=amount, game=game, result=result, balance_before=balance_before, balance_after=balance_after)
    db.session.add(transaction)
    db.session.commit()
    return transaction

class RNG:
    @staticmethod
    def dice_roll(): return random.randint(1, 6)
    @staticmethod
    def slots_spin():
        symbols = ['🍒', '🍋', '🍊', '💎', '7️⃣', '⭐']
        return [random.choice(symbols) for _ in range(3)]
    @staticmethod
    def crash_multiplier(): return round(random.uniform(1.1, 10.0), 2)

# ==================== الصفحات العامة ====================
@app.route('/')
def index():
    promotions = Promotion.query.filter_by(is_active=1).all()
    games = Game.query.filter_by(is_active=1).all()
    return render_template('index.html', promotions=promotions, games=games)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        errors = []
        if len(username) < 3: errors.append('اسم المستخدم 3 أحرف على الأقل')
        if len(password) < 6: errors.append('كلمة المرور 6 أحرف على الأقل')
        if User.query.filter_by(username=username).first(): errors.append('اسم المستخدم موجود')
        if User.query.filter_by(email=email).first(): errors.append('البريد مستخدم')
        if errors:
            for e in errors: flash(e, 'danger')
            return render_template('login.html', register_mode=True)
        welcome_bonus = float(get_setting('welcome_bonus', '1000'))
        user = User(username=username, email=email, password_hash=generate_password_hash(password), balance=welcome_bonus)
        db.session.add(user)
        db.session.commit()
        add_transaction(user.id, 'deposit', welcome_bonus, result='🎁 رصيد ترحيبي')
        add_log(user.id, 'تسجيل', f'انضم {username}')
        flash(f'✅ تم التسجيل! {welcome_bonus} نقطة ترحيبية', 'success')
        return redirect(url_for('login'))
    return render_template('login.html', register_mode=True)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password_hash, password):
            login_user(user)
            add_log(user.id, 'دخول', 'تم')
            if user.is_admin: return redirect(url_for('admin_panel'))
            return redirect(url_for('dashboard'))
        flash('❌ بيانات خاطئة', 'danger')
    return render_template('login.html', register_mode=False)

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))

# ==================== لوحة تحكم المستخدم ====================
@app.route('/dashboard')
@login_required
def dashboard():
    transactions = Transaction.query.filter_by(user_id=current_user.id).order_by(Transaction.created_at.desc()).limit(15).all()
    promotions = Promotion.query.filter_by(is_active=1).all()
    stats = {
        'total_deposited': current_user.total_deposited,
        'total_withdrawn': current_user.total_withdrawn,
        'total_won': current_user.total_won,
        'total_lost': current_user.total_lost,
    }
    return render_template('dashboard.html', transactions=transactions, promotions=promotions, stats=stats)

# ==================== الألعاب ====================
@app.route('/games')
@login_required
def games():
    return render_template('games.html', games=Game.query.filter_by(is_active=1).all())

@app.route('/game/dice', methods=['GET', 'POST'])
@login_required
def game_dice():
    if request.method == 'POST':
        data = request.get_json()
        bet = float(data.get('bet', 0))
        guess = int(data.get('guess', 0))
        if current_user.balance < bet: return jsonify({'error': 'رصيد غير كافي'}), 400
        if bet < 1 or bet > 500: return jsonify({'error': 'حدود 1-500'}), 400
        result = RNG.dice_roll()
        win_rate = float(get_setting('win_rate', '45'))
        profit_margin = float(get_setting('profit_margin', '10'))
        if random.randint(1,100) <= win_rate and guess == result:
            win = round(bet * 5 * (1 - profit_margin/100), 2)
            add_transaction(current_user.id, 'win', win, '🎲 نرد', f'ربح {win}')
            return jsonify({'result': result, 'won': True, 'win_amount': win, 'new_balance': round(current_user.balance + win, 2)})
        else:
            add_transaction(current_user.id, 'loss', bet, '🎲 نرد', f'خسارة {bet}')
            return jsonify({'result': result, 'won': False, 'new_balance': round(current_user.balance - bet, 2)})
    return render_template('games/dice.html')

@app.route('/game/slots', methods=['GET', 'POST'])
@login_required
def game_slots():
    if request.method == 'POST':
        data = request.get_json()
        bet = float(data.get('bet', 0))
        if current_user.balance < bet: return jsonify({'error': 'رصيد غير كافي'}), 400
        result = RNG.slots_spin()
        if result[0] == result[1] == result[2]:
            win = bet * 10; won = True
            add_transaction(current_user.id, 'win', win, '🎰 سلوتس', 'جاكبوت')
        elif result[0] == result[1] or result[1] == result[2] or result[0] == result[2]:
            win = bet * 2; won = True
            add_transaction(current_user.id, 'win', win, '🎰 سلوتس', 'اثنان')
        else:
            win = 0; won = False
            add_transaction(current_user.id, 'loss', bet, '🎰 سلوتس', 'لا تطابق')
        return jsonify({'result': result, 'won': won, 'win_amount': win, 'new_balance': round(current_user.balance + win if won else current_user.balance - bet, 2)})
    return render_template('games/slots.html')

@app.route('/game/crash', methods=['GET', 'POST'])
@login_required
def game_crash():
    if request.method == 'POST':
        data = request.get_json()
        bet = float(data.get('bet', 0))
        cashout = float(data.get('cashout_at', 0))
        if current_user.balance < bet: return jsonify({'error': 'رصيد غير كافي'}), 400
        crash = RNG.crash_multiplier()
        if cashout <= crash:
            win = round(bet * cashout, 2)
            add_transaction(current_user.id, 'win', win, '📈 كراش', f'سحب {cashout}x')
            return jsonify({'crash_point': crash, 'won': True, 'win_amount': win, 'new_balance': round(current_user.balance + win, 2)})
        else:
            add_transaction(current_user.id, 'loss', bet, '📈 كراش', f'انهيار {crash}x')
            return jsonify({'crash_point': crash, 'won': False, 'new_balance': round(current_user.balance - bet, 2)})
    return render_template('games/crash.html')

# ==================== إيداع وسحب ====================
@app.route('/deposit', methods=['GET', 'POST'])
@login_required
def deposit():
    methods = PaymentMethod.query.filter_by(is_active=1).all()
    if request.method == 'POST':
        amount = float(request.form.get('amount', 0))
        method = PaymentMethod.query.get(request.form.get('method_id'))
        if not method or amount <= 0 or amount < method.min_deposit or amount > method.max_deposit:
            flash('❌ خطأ في البيانات', 'danger')
            return redirect(url_for('deposit'))
        add_transaction(current_user.id, 'deposit', amount, result=f'💳 {method.name}')
        flash(f'✅ تم إيداع {amount} نقطة', 'success')
        return redirect(url_for('dashboard'))
    return render_template('deposit.html', payment_methods=methods)

@app.route('/withdraw', methods=['GET', 'POST'])
@login_required
def withdraw():
    methods = PaymentMethod.query.filter_by(is_active=1).all()
    if request.method == 'POST':
        amount = float(request.form.get('amount', 0))
        method_name = request.form.get('method_name', '')
        account = request.form.get('account_number', '')
        if amount <= 0 or amount > current_user.balance or not method_name or not account:
            flash('❌ خطأ في البيانات', 'danger')
            return redirect(url_for('withdraw'))
        req = WithdrawRequest(user_id=current_user.id, amount=amount, payment_method=method_name, account_number=account)
        db.session.add(req)
        db.session.commit()
        add_log(current_user.id, 'طلب سحب', f'{amount} نقطة')
        flash('✅ تم إرسال طلب السحب', 'success')
        return redirect(url_for('dashboard'))
    return render_template('withdraw.html', payment_methods=methods)

@app.route('/transactions')
@login_required
def transactions():
    page = request.args.get('page', 1, type=int)
    trans = Transaction.query.filter_by(user_id=current_user.id).order_by(Transaction.created_at.desc()).paginate(page=page, per_page=20, error_out=False)
    cashback_percent = float(get_setting('cashback_percent', '20'))
    cashback = round(current_user.total_lost * cashback_percent / 100, 2)
    return render_template('transactions.html', transactions=trans, available_cashback=cashback)

@app.route('/claim-cashback', methods=['POST'])
@login_required
def claim_cashback():
    cashback_percent = float(get_setting('cashback_percent', '20'))
    amount = round(current_user.total_lost * cashback_percent / 100, 2)
    if amount <= 0:
        flash('❌ لا يوجد كاش باك', 'danger')
        return redirect(url_for('dashboard'))
    add_transaction(current_user.id, 'cashback', amount, result=f'💵 استرداد {cashback_percent}%')
    flash(f'🎉 استرداد {amount} نقطة!', 'success')
    return redirect(url_for('dashboard'))

# ==================== لوحة الإدارة ====================
@app.route('/admin')
@login_required
def admin_panel():
    if not current_user.is_admin: return redirect(url_for('dashboard'))
    total_users = User.query.count()
    total_transactions = Transaction.query.count()
    total_deposits = sum(t.amount for t in Transaction.query.filter_by(type='deposit').all())
    total_withdraws = sum(t.amount for t in Transaction.query.filter_by(type='withdraw').all())
    pending_withdraws = WithdrawRequest.query.filter_by(status='pending').count()
    recent_users = User.query.order_by(User.created_at.desc()).limit(10).all()
    return render_template('admin/panel.html', total_users=total_users, total_transactions=total_transactions, total_deposits=total_deposits, total_withdraws=total_withdraws, pending_withdraws=pending_withdraws, recent_users=recent_users)

@app.route('/admin/settings', methods=['GET', 'POST'])
@login_required
def admin_settings():
    if not current_user.is_admin: return redirect(url_for('dashboard'))
    if request.method == 'POST':
        for key in ['win_rate', 'loss_rate', 'welcome_bonus', 'profit_margin', 'referral_bonus', 'cashback_percent', 'min_deposit', 'max_deposit']:
            val = request.form.get(key)
            if val is not None: set_setting(key, val)
        flash('✅ تم تحديث الإعدادات', 'success')
        return redirect(url_for('admin_settings'))
    settings = {k: get_setting(k, '0') for k in ['win_rate', 'loss_rate', 'welcome_bonus', 'profit_margin', 'referral_bonus', 'cashback_percent', 'min_deposit', 'max_deposit']}
    return render_template('admin/settings.html', settings=settings)

@app.route('/admin/payment-methods')
@login_required
def admin_payment_methods():
    if not current_user.is_admin: return redirect(url_for('dashboard'))
    return render_template('admin/payment_methods.html', methods=PaymentMethod.query.all())

@app.route('/admin/payment-methods/add', methods=['POST'])
@login_required
def admin_add_payment_method():
    if not current_user.is_admin: return jsonify({'error': 'غير مصرح'}), 403
    m = PaymentMethod(name=request.form.get('name'), account_number=request.form.get('account_number'), holder_name=request.form.get('holder_name'), payment_link=request.form.get('payment_link'), instructions=request.form.get('instructions'), min_deposit=float(request.form.get('min_deposit', 10)), max_deposit=float(request.form.get('max_deposit', 10000)))
    db.session.add(m); db.session.commit()
    flash('✅ تمت الإضافة', 'success')
    return redirect(url_for('admin_payment_methods'))

@app.route('/admin/payment-methods/<int:id>/edit', methods=['POST'])
@login_required
def admin_edit_payment_method(id):
    if not current_user.is_admin: return jsonify({'error': 'غير مصرح'}), 403
    m = PaymentMethod.query.get_or_404(id)
    m.name = request.form.get('name', m.name)
    m.account_number = request.form.get('account_number', m.account_number)
    m.holder_name = request.form.get('holder_name', m.holder_name)
    m.payment_link = request.form.get('payment_link', m.payment_link)
    m.instructions = request.form.get('instructions', m.instructions)
    m.min_deposit = float(request.form.get('min_deposit', m.min_deposit))
    m.max_deposit = float(request.form.get('max_deposit', m.max_deposit))
    db.session.commit()
    flash('✅ تم التحديث', 'success')
    return redirect(url_for('admin_payment_methods'))

@app.route('/admin/payment-methods/<int:id>/toggle', methods=['POST'])
@login_required
def admin_toggle_payment_method(id):
    if not current_user.is_admin: return jsonify({'error': 'غير مصرح'}), 403
    m = PaymentMethod.query.get(id)
    m.is_active = 1 if m.is_active == 0 else 0
    db.session.commit()
    return jsonify({'success': True})

@app.route('/admin/payment-methods/<int:id>/delete', methods=['POST'])
@login_required
def admin_delete_payment_method(id):
    if not current_user.is_admin: return jsonify({'error': 'غير مصرح'}), 403
    db.session.delete(PaymentMethod.query.get(id))
    db.session.commit()
    return jsonify({'success': True})

@app.route('/admin/withdraw-requests')
@login_required
def admin_withdraw_requests():
    if not current_user.is_admin: return redirect(url_for('dashboard'))
    pending = WithdrawRequest.query.filter_by(status='pending').order_by(WithdrawRequest.created_at.desc()).all()
    processed = WithdrawRequest.query.filter(WithdrawRequest.status != 'pending').order_by(WithdrawRequest.processed_at.desc()).limit(20).all()
    return render_template('admin/withdraw_requests.html', pending=pending, processed=processed)

@app.route('/admin/withdraw-requests/<int:id>/approve', methods=['POST'])
@login_required
def admin_approve_withdraw(id):
    if not current_user.is_admin: return jsonify({'error': 'غير مصرح'}), 403
    req = WithdrawRequest.query.get_or_404(id)
    user = User.query.get(req.user_id)
    if user.balance < req.amount: return jsonify({'error': 'رصيد غير كافي'}), 400
    req.status = 'approved'; req.processed_at = datetime.utcnow(); req.admin_note = request.form.get('note', 'تمت الموافقة')
    add_transaction(user.id, 'withdraw', req.amount, result=f'✅ سحب {req.payment_method}')
    db.session.commit()
    flash('✅ تمت الموافقة', 'success')
    return redirect(url_for('admin_withdraw_requests'))

@app.route('/admin/withdraw-requests/<int:id>/reject', methods=['POST'])
@login_required
def admin_reject_withdraw(id):
    if not current_user.is_admin: return jsonify({'error': 'غير مصرح'}), 403
    req = WithdrawRequest.query.get_or_404(id)
    req.status = 'rejected'; req.processed_at = datetime.utcnow(); req.admin_note = request.form.get('note', 'تم الرفض')
    db.session.commit()
    flash('❌ تم الرفض', 'warning')
    return redirect(url_for('admin_withdraw_requests'))

@app.route('/admin/users')
@login_required
def admin_users():
    if not current_user.is_admin: return redirect(url_for('dashboard'))
    return render_template('admin/users.html', users=User.query.order_by(User.created_at.desc()).all())

@app.route('/admin/users/<int:id>/add-balance', methods=['POST'])
@login_required
def admin_add_balance(id):
    if not current_user.is_admin: return jsonify({'error': 'غير مصرح'}), 403
    user = User.query.get_or_404(id)
    amount = float(request.form.get('amount', 0))
    note = request.form.get('note', 'إضافة رصيد')
    if amount <= 0:
        flash('❌ خطأ', 'danger')
        return redirect(url_for('admin_users'))
    add_transaction(user.id, 'deposit', amount, result=f'👨‍💼 {note}')
    flash(f'✅ {amount} نقطة لـ {user.username}', 'success')
    return redirect(url_for('admin_users'))

# ==================== بدء التشغيل ====================
def init_db():
    with app.app_context():
        db.create_all()
        defaults = {'win_rate': '45', 'loss_rate': '55', 'welcome_bonus': '1000', 'profit_margin': '10', 'referral_bonus': '100', 'cashback_percent': '20', 'min_deposit': '10', 'max_deposit': '10000'}
        for k, v in defaults.items():
            if not SystemSettings.query.filter_by(key=k).first():
                set_setting(k, v)
        if not User.query.filter_by(username='admin').first():
            admin = User(username='admin', email='admin@grad.edu', password_hash=generate_password_hash('admin123'), balance=999999, is_admin=1)
            db.session.add(admin)
            for g in [Game(name='نرد', description='خمن الرقم من 1-6', min_bet=1, max_bet=500), Game(name='سلوتس', description='3 بكرات', min_bet=2, max_bet=1000), Game(name='كراش', description='اسحب قبل الانهيار', min_bet=5, max_bet=500)]:
                db.session.add(g)
            for p in [PaymentMethod(name='FastPay', account_number='0770000000', holder_name='اسم المستلم', instructions='حول المبلغ'), PaymentMethod(name='Zain Cash', account_number='0770000000', holder_name='اسم المستلم'), PaymentMethod(name='FIB', account_number='123456', holder_name='اسم المستلم'), PaymentMethod(name='SuperQi', account_number='0770000000', holder_name='اسم المستلم')]:
                db.session.add(p)
            db.session.add(Promotion(title='مكافأة ترحيبية', description='1000 نقطة عند التسجيل', bonus_percent=100, is_active=1))
            db.session.commit()
            print('✅ تم تهيئة قاعدة البيانات!')
            print('👤 الأدمن: admin | كلمة المرور: admin123')

if __name__ == '__main__':
    init_db()
    app.run(debug=True, host='0.0.0.0', port=5000)
  
