from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify, make_response, send_file
from flask_session import Session
import unicodedata
from math import ceil
import google.generativeai as genai
from datetime import datetime, timezone, timedelta
import os
from dotenv import load_dotenv
import mysql.connector
from flask_bcrypt import Bcrypt
from functools import wraps
import random
from flask_mail import Mail, Message
import secrets
import smtplib
import string
from itsdangerous import URLSafeTimedSerializer
import uuid
import requests
from time import time
import base64
import re
import json
import math
from bs4 import BeautifulSoup

from radicals import radicals
from utils import remove_accents, get_sets, generate_choices, process_meanings, format_number
from database import execute_query, update_whitelist_status, is_whitelisted, get_new_sentence, check_transaction, mycursor, mydb
from api_handlers import translate_and_analyze, get_combined_info
from dictionary import get_stroke_order, get_hannom_info
from login import login_required, admin_required
from test_handlers import test_set_handler, test_random_handler
from translate import translate
from speech_recognition import recognize_speech, get_feedback

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY')
app.jinja_env.filters['format_number'] = format_number
app.config['SESSION_TYPE'] = 'filesystem'
Session(app)
bcrypt = Bcrypt(app)
app.config['SECURITY_PASSWORD_SALT'] = 'your-security-password-salt'  # Thay đổi giá trị này
serializer = URLSafeTimedSerializer(app.config['SECRET_KEY'])

app.config['MAIL_SERVER'] = os.getenv('MAIL_SERVER')
app.config['MAIL_PORT'] = int(os.getenv('MAIL_PORT', 587))
app.config['MAIL_USE_TLS'] = os.getenv('MAIL_USE_TLS') == 'True'
app.config['MAIL_USERNAME'] = os.getenv('MAIL_USERNAME')
app.config['MAIL_PASSWORD'] = os.getenv('MAIL_PASSWORD')
app.config['MAIL_DEFAULT_SENDER'] = os.getenv('MAIL_DEFAULT_SENDER')

mail = Mail(app)

# Lưu trữ token xác minh tạm thời
verification_tokens = {}
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

radical_sets = get_sets(radicals)

# Trang chủ
@app.route('/')
def home():
    sentence = get_new_sentence()
    contact_info = {
        #'facebook': 'facebook.com/GrazT.2106',
        'email': 'tiengtrungtg@gmail.com',
        #'phone': '0948388213'
    }
    return render_template('home.html', sentence=sentence, contact_info=contact_info)


@app.route('/history')
def history():
    # Lấy tất cả câu từ cơ sở dữ liệu, sắp xếp theo ngày giảm dần
    mycursor.execute(
        "SELECT *, DATE(created_at) as date FROM sentences ORDER BY created_at DESC")
    sentences = mycursor.fetchall()

    return render_template('history.html', sentences=sentences)


# ================== Phần Học ==================


@app.route('/radicals', methods=['GET'])
def all_radicals():
    query = request.args.get('q', '').strip()
    page = request.args.get('page', 1, type=int)
    per_page = 20  # Số bộ thủ mỗi trang

    if query:
        query_no_accents = remove_accents(query.lower())
        # Tìm kiếm theo bộ thủ, nghĩa hoặc Pinyin (không phân biệt dấu)
        filtered_radicals = [
            r for r in radicals
            if query in r['radical'] or
            query_no_accents in remove_accents(r['meaning'].lower()) or
            query_no_accents in remove_accents(r['pinyin'].lower())
        ]
    else:
        filtered_radicals = radicals

    total = len(filtered_radicals)
    pages = ceil(total / per_page)
    start = (page - 1) * per_page
    end = start + per_page
    paginated_radicals = filtered_radicals[start:end]

    return render_template('radicals.html', radicals=paginated_radicals, query=query, page=page, pages=pages, per_page=per_page)


# Đặt tên cho route để sử dụng trong url_for
app.add_url_rule('/radicals', 'all_radicals', all_radicals)

# Chọn chế độ học
@app.route('/learn')
def learn():
    return render_template('learn.html')

# Học theo thứ tự
@app.route('/learn/sequential', methods=['GET'])
def learn_sequential():
    index = request.args.get('index', default=1, type=int) - 1
    if index < 0:
        index = 0
    elif index >= len(radicals):
        index = len(radicals) - 1

    radical = radicals[index]
    total_radicals = len(radicals)

    prev_index = index if index > 0 else None
    next_index = index + 2 if index < total_radicals - 1 else None

    return render_template('flashcard_sequential.html', radical=radical, index=index + 1, total=total_radicals, prev_index=prev_index, next_index=next_index)


@app.route('/learn/sequential/next')
def next_flashcard_sequential():
    index = session.get('learn_index', 0) + 1
    if index >= len(radicals):
        index = 0
    session['learn_index'] = index
    return redirect(url_for('learn_sequential'))

# Học ngẫu nhiên
@app.route('/learn/random')
def learn_random():
    go_back = request.args.get('back') == '1'
    current_radical = session.get('current_radical')
    prev_radical = session.get('previous_radical')
    
    if go_back and prev_radical:
        # Nếu quay lại, đổi chỗ current và previous
        current_radical, prev_radical = prev_radical, current_radical
    elif not go_back:
        # Nếu không quay lại, chọn radical mới và cập nhật previous
        prev_radical = current_radical
        current_radical = random.choice(radicals)
    
    # Cập nhật session
    session['current_radical'] = current_radical
    session['previous_radical'] = prev_radical

    next_url = url_for('learn_random')
    back_url = url_for('learn_random', back=1) if prev_radical else None

    return render_template('flashcard.html',
                           radical=current_radical,
                           next_url=next_url,
                           back_url=back_url)

# ================== Phần Kiểm Tra ==================

# Chọn chế độ kiểm tra
@app.route('/test')
def test():
    return render_template('test.html', total_sets=len(radical_sets))

# Kiểm tra theo bộ đề
@app.route('/test/set/<int:set_number>', methods=['GET', 'POST'])
def test_set(set_number):
    return test_set_handler(set_number, radical_sets)



# Review
@app.route('/review')
def review():
    import json
    answers = request.args.get('answers')
    answers = json.loads(answers)
    test_type = request.args.get('test_type', 'meaning')
    return render_template('review.html', answers=answers, test_type=test_type)

# Kiểm tra ngẫu nhiên
@app.route('/test/random', methods=['GET', 'POST'])
def test_random():
    return test_random_handler()

# Gửi email xác minh
def send_verification_email(email, token):
    msg = Message('Xác minh tài khoản', recipients=[email])
    verification_link = url_for("verify_email", token=token, _external=True)
    msg.body = f"""Vui lòng nhấp vào liên kết sau để xác minh tài khoản của bạn:
    {verification_link}"""
    mail.send(msg)

def send_verification_code(email, code):
    msg = Message('Mã xác minh tài khoản', recipients=[email])
    msg.body = f"""Mã xác minh của bạn là: {code}
    Mã này có hiệu lực trong vòng 5 phút."""
    mail.send(msg)

# Lấy mã xác minh
@app.route('/get_verification_code', methods=['POST'])
def get_verification_code():
    email = request.json.get('email')
    if not email:
        return jsonify({'success': False, 'message': 'Email không được để trống'}), 400

    # Kiểm tra xem email đã tồn tại chưa
    mycursor.execute("SELECT * FROM users WHERE email = %s", (email,))
    if mycursor.fetchone():
        return jsonify({'success': False, 'message': 'Email đã được sử dụng'}), 400

    # Tạo mã xác minh
    verification_code = ''.join(random.choices(string.digits, k=6))
    expiration_time = datetime.now() + timedelta(minutes=5)

    # Lưu mã xác minh vào session
    session['verification'] = {
        'email': email,
        'code': verification_code,
        'expiration_time': expiration_time
    }

    try:
        # Gửi email xác minh
        send_verification_code(email, verification_code)
        return jsonify({'success': True, 'message': 'Mã xác nhận đã được gửi'})
    except Exception as e:
        app.logger.error(f"Lỗi khi gửi email: {str(e)}")
        return jsonify({'success': False, 'message': 'Có lỗi xảy ra khi gửi mã xác nhận. Vui lòng thử lại.'}), 500

# Đăng ký
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        confirm_password = request.form['confirm_password']

        # Kiểm tra xem username đã tồn tại chưa
        mycursor.execute("SELECT * FROM users WHERE username = %s", (username,))
        if mycursor.fetchone():
            flash('Tên người dùng đã tồn tại', 'error')
            return redirect(url_for('register'))

        # Kiểm tra xem email đã tồn tại chưa
        mycursor.execute("SELECT * FROM users WHERE email = %s", (email,))
        if mycursor.fetchone():
            flash('Email đã được sử dụng', 'error')
            return redirect(url_for('register'))

        # Kiểm tra mật khẩu xác nhận
        if password != confirm_password:
            flash('Mật khẩu xác nhận không khớp', 'error')
            return redirect(url_for('register'))

        # Mã hóa mật khẩu
        hashed_password = bcrypt.generate_password_hash(password).decode('utf-8')

        # Thêm người dùng mới vào cơ sở dữ liệu
        sql = "INSERT INTO users (username, email, password) VALUES (%s, %s, %s)"
        val = (username, email, hashed_password)
        mycursor.execute(sql, val)
        mydb.commit()

        # Lấy ID của người dùng mới đăng ký
        new_user_id = mycursor.lastrowid

        # Tạo các yêu cầu thanh toán cho người dùng mới
        mycursor.execute("CALL create_payment_requests(%s)", (new_user_id,))
        mydb.commit()

        flash('Đăng ký thành công! Bạn có thể đăng nhập ngay bây giờ.', 'success')
        return redirect(url_for('login'))

    return render_template('register.html')


# Xác minh email
@app.route('/verify_email/<token>')
def verify_email(token):
    if token in verification_tokens:
        user_data = verification_tokens[token]

        # Thêm người dùng vào cơ sở dữ liệu với mật khẩu đã mã hóa
        sql = "INSERT INTO users (username, email, password, is_admin, translation_count, last_translation_reset) VALUES (%s, %s, %s, %s, %s, %s)"
        val = (user_data['username'], user_data['email'],
               user_data['password'], False, 0, datetime.now())
        mycursor.execute(sql, val)
        mydb.commit()

        # Xóa token sau khi sử dụng
        del verification_tokens[token]

        flash('Tài khoản của bạn đã được xác minh thành công. Bạn có thể đăng nhập ngay bây giờ.', 'success')
        return redirect(url_for('login'))
    else:
        flash('Liên kết xác minh không hợp lệ hoặc đã hết hạn.', 'error')
        return redirect(url_for('register'))

# Đăng nhập
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username_or_email = request.form['username']
        password = request.form['password']

        # Kiểm tra xem đầu vào là email hay username
        if '@' in username_or_email:
            # Nếu là email
            mycursor.execute(
                "SELECT * FROM users WHERE email = %s", (username_or_email,))
        else:
            # Nếu là username
            mycursor.execute(
                "SELECT * FROM users WHERE username = %s", (username_or_email,))
        
        user = mycursor.fetchone()

        if user and bcrypt.check_password_hash(user['password'], password):
            session['user_id'] = user['id']
            session['is_admin'] = user['is_admin']
            
            # Truy vấn lại địa chỉ email từ cột email của bảng users
            mycursor.execute("SELECT email FROM users WHERE id = %s", (user['id'],))
            email_result = mycursor.fetchone()
            if email_result:
                session['user_email'] = email_result['email']

            # Reset translation count and last reset time
            now = datetime.now()
            mycursor.execute(
                "UPDATE users SET translation_count = 0, last_translation_reset = %s WHERE id = %s", (now, user['id']))
            mydb.commit()

            flash('Đăng nhập thành công!', 'success')
            return redirect(url_for('home'))
        else:
            flash('Đăng nhập thất bại. Vui lòng kiểm tra lại thông tin.', 'error')

    return render_template('login.html')

# Đăng xuất
@app.route('/logout')
def logout():
    session.clear()
    flash('Đã đăng xuất thành công!', 'success')
    return redirect(url_for('home'))

# Dịch văn bản
@app.route('/translate', methods=['GET', 'POST'])
def translate_route():
    return translate()

# Trang quản lý
@admin_required
def admin_dashboard():
    mycursor.execute(
        "SELECT * FROM translation_history ORDER BY created_at DESC")
    history = mycursor.fetchall()

    mycursor.execute(
        "SELECT u.*, CASE WHEN w.id IS NOT NULL THEN 1 ELSE 0 END AS is_whitelisted FROM users u LEFT JOIN whitelist w ON u.id = w.user_id")
    users = mycursor.fetchall()

    return render_template('admin_dashboard.html', history=history, users=users)

# Quản lý
@app.route('/admin')
@admin_required
def admin_dashboard():
    mycursor.execute(
        "SELECT * FROM translation_history ORDER BY created_at DESC")
    history = mycursor.fetchall()

    mycursor.execute("""
    SELECT u.*, 
           w.id AS whitelist_id,
           w.expiration_date,
           w.is_permanent,
           CASE 
               WHEN u.is_admin = 1 THEN 'Admin'
               WHEN w.id IS NOT NULL THEN 
                   CASE
                       WHEN w.is_permanent = 1 THEN 'Vĩnh viễn'
                       ELSE CONCAT('Đến hết ', DATE_FORMAT(w.expiration_date, '%d-%m-%Y'))
                   END
               WHEN u.last_translation_reset IS NULL OR TIMESTAMPDIFF(HOUR, u.last_translation_reset, NOW()) > 24 THEN '10'
               ELSE CAST(10 - u.translation_count AS CHAR)
           END AS remaining_translations
    FROM users u 
    LEFT JOIN whitelist w ON u.id = w.user_id
    """)
    users = mycursor.fetchall()

    return render_template('admin_dashboard.html', history=history, users=users)

@app.route('/admin/remove_from_whitelist/<int:whitelist_id>', methods=['POST'])
@admin_required
def remove_from_whitelist(whitelist_id):
    mycursor.execute("DELETE FROM whitelist WHERE id = %s", (whitelist_id,))
    mydb.commit()
    flash('Đã xóa người dùng khỏi whitelist', 'success')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/whitelist/<int:user_id>', methods=['POST'])
@admin_required
def add_to_whitelist(user_id):
    duration_type = request.form['duration_type']

    if duration_type == 'permanent':
        expiration_date = None
        is_permanent = True
    else:
        duration = int(request.form['duration'])
        duration_unit = request.form['duration_unit']
        is_permanent = False

        if duration_unit == 'days':
            expiration_date = datetime.now() + timedelta(days=duration)
        elif duration_unit == 'months':
            expiration_date = datetime.now() + timedelta(days=duration*30)
        elif duration_unit == 'years':
            expiration_date = datetime.now() + timedelta(days=duration*365)

    # Kiểm tra xem user_id đã tồn tại trong whitelist chưa
    mycursor.execute("SELECT id FROM whitelist WHERE user_id = %s", (user_id,))
    existing = mycursor.fetchone()

    if existing:
        # Cập nhật nếu đã tồn tại
        mycursor.execute("UPDATE whitelist SET expiration_date = %s, is_permanent = %s WHERE user_id = %s", 
                         (expiration_date, is_permanent, user_id))
    else:
        # Thêm mới nếu chưa tồn tại
        mycursor.execute("INSERT INTO whitelist (user_id, expiration_date, is_permanent) VALUES (%s, %s, %s)", 
                         (user_id, expiration_date, is_permanent))
    mydb.commit()

    flash('Đã cập nhật whitelist thành công!', 'success')
    return redirect(url_for('admin_dashboard'))

@app.route('/forgot_password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form['email']
        mycursor.execute("SELECT * FROM users WHERE email = %s", (email,))
        user = mycursor.fetchone()
        if user:
            token = serializer.dumps(email, salt=app.config['SECURITY_PASSWORD_SALT'])
            reset_url = url_for('reset_password', token=token, _external=True)
            msg = Message('Đặt lại mật khẩu', recipients=[email])
            msg.body = f'Để đặt lại mật khẩu, vui lòng truy cập liên kết sau: {reset_url}'
            mail.send(msg)
            flash('Hướng dẫn đặt lại mật khẩu đã được gửi đến email của bạn.', 'info')
            return redirect(url_for('login'))
        else:
            flash('Không tìm thấy tài khoản với email này.', 'error')
    return render_template('forgot_password.html')

@app.route('/reset_password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    try:
        email = serializer.loads(token, salt=app.config['SECURITY_PASSWORD_SALT'], max_age=3600)
    except:
        flash('Liên kết đặt lại mật khẩu không hợp lệ hoặc đã hết hạn.', 'error')
        return redirect(url_for('forgot_password'))
    
    if request.method == 'POST':
        new_password = request.form['new_password']
        confirm_password = request.form['confirm_password']
        if new_password != confirm_password:
            flash('Mật khẩu không khớp.', 'error')
        else:
            hashed_password = bcrypt.generate_password_hash(new_password).decode('utf-8')
            mycursor.execute("UPDATE users SET password = %s WHERE email = %s", (hashed_password, email))
            mydb.commit()
            flash('Mật khẩu của bạn đã được đặt lại thành công.', 'success')
            return redirect(url_for('login'))
    return render_template('reset_password.html')

# Check transaction
api_token = os.getenv('SEPAY_API_TOKEN')
headers = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {api_token}"
}

@app.route('/premium')
@login_required
def premium():
    if 'user_id' not in session:
        flash('Vui lòng đăng nhập để truy cập trang Premium.', 'error')
        return redirect(url_for('login'))
    
    # Kiểm tra và cập nhật trạng thái whitelist
    is_whitelisted = update_whitelist_status(session['user_id'])
    
    if is_whitelisted:
        mycursor.execute("SELECT * FROM whitelist WHERE user_id = %s", (session['user_id'],))
        whitelist_info = mycursor.fetchone()
        return render_template('premium_status.html', whitelist_info=whitelist_info)
    
    plans = [
        {'name': '1 tuần', 'price': 15000, 'duration': 7},
        {'name': '1 tháng', 'price': 49000, 'duration': 30},
        {'name': '1 năm', 'price': 499000, 'duration': 365}
    ]
    return render_template('premium.html', plans=plans)

@app.route('/payment/<int:plan_id>')
@login_required
def payment(plan_id):
    if is_whitelisted(session['user_id']):
        flash('Bạn đã là thành viên Premium.', 'info')
        return redirect(url_for('home'))
    
    mycursor.execute("""
    SELECT * FROM payment_requests 
    WHERE user_id = %s AND plan_id = %s AND is_active = TRUE
    """, (session['user_id'], plan_id))
    payment_request = mycursor.fetchone()
    
    if not payment_request:
        flash('Không tìm thấy yêu cầu thanh toán hợp lệ.', 'error')
        return redirect(url_for('premium'))
    
    plans = [
        {'id': 0, 'name': '1 tuần', 'price': 15000, 'duration': 7},
        {'id': 1, 'name': '1 tháng', 'price': 49000, 'duration': 30},
        {'id': 2, 'name': '1 năm', 'price': 499000, 'duration': 365}
    ]
    selected_plan = plans[plan_id]
    
    so_tai_khoan = os.getenv('SEPAY_ACCOUNT_NUMBER')
    ngan_hang = os.getenv('SEPAY_BANK_NAME')
    noi_dung = f"TTGP {payment_request['reference_code']}"
    
    qr_link = f"https://qr.sepay.vn/img?acc={so_tai_khoan}&bank={ngan_hang}&amount={payment_request['amount']}&des={noi_dung}"
    
    payment_info = {
        'account_number': so_tai_khoan,
        'bank': ngan_hang,
        'amount': payment_request['amount'],
        'reference_code': payment_request['reference_code'],
        'qr_link': qr_link
    }
    
    response = make_response(render_template('payment.html', plan=selected_plan, payment_info=payment_info))
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response

@app.route('/check_payment_status')
@login_required
def check_payment_status():
    mycursor.execute("""
    SELECT * 
    FROM payment_requests 
    WHERE user_id = %s AND is_active = TRUE 
    ORDER BY id DESC LIMIT 1
    """, (session['user_id'],))
    payment_request = mycursor.fetchone()
    if payment_request:
        plans = [
            {'id': 0, 'name': '1 tuần', 'price': 15000, 'duration': 7},
            {'id': 1, 'name': '1 tháng', 'price': 49000, 'duration': 30},
            {'id': 2, 'name': '1 năm', 'price': 499000, 'duration': 365}
        ]
        plan = plans[payment_request['plan_id']]
        return jsonify({
            'plan_id': payment_request['plan_id'],
            'plan_name': plan['name'],
            'amount': payment_request['amount'],
            'reference_code': payment_request['reference_code']
        })
    return jsonify({}), 404

@app.route('/verify_payment')
@login_required
def verify_payment():
    if is_whitelisted(session['user_id']):
        flash('Bạn đã là thành viên Premium.', 'info')
        return redirect(url_for('home'))
    
    mycursor.execute("""
    SELECT * FROM payment_requests 
    WHERE user_id = %s AND is_active = TRUE
    """, (session['user_id'],))
    payment_requests = mycursor.fetchall()
    
    plans = [
        {'id': 0, 'name': '1 tuần', 'price': 15000, 'duration': 7},
        {'id': 1, 'name': '1 tháng', 'price': 49000, 'duration': 30},
        {'id': 2, 'name': '1 năm', 'price': 499000, 'duration': 365}
    ]
    
    for payment_request in payment_requests:
        actual_amount = check_transaction(payment_request['reference_code'])
        if actual_amount is not None:
            selected_plan = next((plan for plan in plans if plan['price'] <= actual_amount), None)
            if selected_plan:
                expiration_date = datetime.now() + timedelta(days=selected_plan['duration'])
                
                mycursor.execute("""
                INSERT INTO whitelist (user_id, expiration_date, is_permanent) 
                VALUES (%s, %s, 0) 
                ON DUPLICATE KEY UPDATE expiration_date = %s, is_permanent = 0
                """, (session['user_id'], expiration_date, expiration_date))
                
                # Cập nhật reference code mới cho tất cả các payment requests của user
                for plan in plans:
                    new_reference_code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
                    mycursor.execute("""
                    UPDATE payment_requests 
                    SET reference_code = %s
                    WHERE user_id = %s AND plan_id = %s
                    """, (new_reference_code, session['user_id'], plan['id']))
                
                mydb.commit()
                
                flash(f'Thanh toán thành công! Bạn đã được nâng cấp lên gói {selected_plan["name"]}.', 'success')
                return redirect(url_for('home'))
            else:
                flash('Số tiền thanh toán không đúng. Vui lòng liên hệ hỗ trợ.', 'error')
                
    flash('Không tìm thấy giao dịch hoặc số tiền không đúng. Vui lòng thử lại.', 'error')
    return redirect(request.referrer or url_for('premium'))


@app.context_processor
def utility_processor():
    def user_is_whitelisted():
        if 'user_id' in session:
            return update_whitelist_status(session['user_id'])
        return False
    return dict(user_is_whitelisted=user_is_whitelisted, user_is_authenticated='user_id' in session)

@app.route('/speaking-practice', methods=['GET', 'POST'])
@login_required
def speaking_practice():
    if not update_whitelist_status(session['user_id']) and not session.get('is_admin'):
        flash('Vui lòng đăng ký Premium để có thể sử dụng chức năng này', 'error')
        return redirect(url_for('premium'))

    if request.method == 'POST':
        audio_file = request.files['audio']
        text_to_read = request.form['text_to_read']
        
        # Nhận dạng giọng nói
        transcript = recognize_speech(audio_file)
        if isinstance(transcript, dict) and 'error' in transcript:
            return jsonify(transcript), 400
        
        # Lấy phản hồi từ Gemini API
        feedback = get_feedback(text_to_read, transcript)
        
        return jsonify({'transcript': transcript, 'feedback': feedback})
    
    # GET request: hiển thị trang
    return render_template('speaking_practice.html')

@app.route('/static/speaking.json')
def serve_vocab():
    return send_file('static/speaking.json')

@app.route('/vocabulary')
def vocabulary_menu():
    return render_template('vocabulary_menu.html')

@app.route('/vocabulary/learn', methods=['GET', 'POST'])
def vocabulary_learn():
    if request.method == 'POST':
        hsk_level = request.form['hsk_level']
        # Chuyển hướng đến URL với tham số GET
        return redirect(url_for('vocabulary_learn', hsk_level=hsk_level, page=1))
    
    # Xử lý yêu cầu GET
    hsk_level = request.args.get('hsk_level')
    page = request.args.get('page', 1, type=int)
    
    if not hsk_level:
        # Nếu không có hsk_level, hiển thị form chọn cấp độ
        return render_template('vocabulary_learn.html')
    
    # Đọc dữ liệu từ file JSON
    with open('static/vocab.json', 'r', encoding='utf-8') as f:
        vocab_data = json.load(f)
    with open(f'static/hsk{hsk_level}_stroke_orders.json', 'r', encoding='utf-8') as f:
        stroke_order_data = json.load(f)
    
    # Lọc từ vựng theo bậc HSK
    hsk_vocab = [word for word in vocab_data if word['HSK'] == int(hsk_level)]
    
    # Kết hợp dữ liệu từ vựng và thứ tự viết
    combined_data = []
    for word in hsk_vocab:
        word_data = word.copy()
        for char in word['Chinese']:
            stroke_order = next((item for item in stroke_order_data if item['character'] == char), None)
            if stroke_order:
                word_data[f'stroke_order_{char}'] = stroke_order
        combined_data.append(word_data)
    
    # Phân trang
    per_page = 10
    total = len(combined_data)
    pages = ceil(total / per_page)
    start = (page - 1) * per_page
    end = start + per_page
    words = combined_data[start:end]
    
    return render_template('vocabulary_learn_result.html', words=words, page=page, pages=pages, hsk_level=hsk_level)

@app.route('/vocabulary/test', methods=['GET', 'POST'])
def vocabulary_test():
    if request.method == 'POST':
        hsk_level = request.form['hsk_level']
        # Lấy dữ liệu từ vựng từ file JSON
        with open('static/vocab.json', 'r', encoding='utf-8') as f:
            vocab_data = json.load(f)
        
        # Lọc từ vựng theo bậc HSK
        hsk_vocab = [word for word in vocab_data if word['HSK'] == int(hsk_level)]
        
        # Tính số bộ đề có thể tạo ra
        num_sets = math.floor(len(hsk_vocab) / 30)
        
        return render_template('vocabulary_test_sets.html', hsk_level=hsk_level, num_sets=num_sets)
    return render_template('vocabulary_test.html')

@app.route('/vocabulary/test/<int:hsk_level>/<int:set_number>', methods=['GET', 'POST'])
def vocabulary_test_set(hsk_level, set_number):
    session_key = f'vocab_test_data_set_{hsk_level}_{set_number}'

    if session.get('current_vocab_set') != set_number or session.get('current_hsk_level') != hsk_level or session_key not in session:
        session['current_vocab_set'] = set_number
        session['current_hsk_level'] = hsk_level
        
        with open('static/vocab.json', 'r', encoding='utf-8') as f:
            vocab_data = json.load(f)
        
        hsk_vocab = [word for word in vocab_data if word['HSK'] == hsk_level]
        
        # Chọn chính xác 30 từ cho bộ đề hiện tại
        start_index = (set_number - 1) * 30
        test_words = hsk_vocab[start_index:start_index + 30]
        
        # Tạo câu hỏi cho mỗi từ
        test_data = {
            'questions': [],
            'answers': {},
            'marked_questions': []
        }
        for i, word in enumerate(test_words):
            correct_answer = word['VietnameseMeaning']
            wrong_answers = random.sample([w['VietnameseMeaning'] for w in hsk_vocab if w != word], 3)
            choices = [correct_answer] + wrong_answers
            random.shuffle(choices)
            
            question = {
                'index': i + 1,
                'word': word['Chinese'],
                'pinyin': word['Pinyin'],
                'correct_answer': correct_answer,
                'choices': choices,
                'selected_choice': None,
                'is_marked': False
            }
            test_data['questions'].append(question)
        
        session[session_key] = test_data

    test_data = session[session_key]

    if request.method == 'POST':
        action = request.form.get('action')
        question_index = int(request.form.get('question_index', 1)) - 1
        
        if action == 'save_answer':
            selected_choice = request.form.get('selected_choice')
            test_data['questions'][question_index]['selected_choice'] = selected_choice
        elif action == 'mark_question':
            test_data['questions'][question_index]['is_marked'] = not test_data['questions'][question_index]['is_marked']
        elif action == 'clear_answer':
            test_data['questions'][question_index]['selected_choice'] = None
        elif action == 'submit_test':
            # Xử lý nộp bài thi ở đây
            return redirect(url_for('vocabulary_test_result', hsk_level=hsk_level, set_number=set_number))
        
        session[session_key] = test_data
        return jsonify({'success': True})

    current_question_index = int(request.args.get('q', 1)) - 1
    if current_question_index < 0 or current_question_index >= len(test_data['questions']):
        current_question_index = 0
    current_question = test_data['questions'][current_question_index]

    return render_template('vocabulary_test_questions.html', 
                           test_data=test_data,
                           current_question=current_question, 
                           hsk_level=hsk_level, 
                           set_number=set_number)

@app.route('/vocabulary/test/result/<int:hsk_level>/<int:set_number>', methods=['GET', 'POST'])
def vocabulary_test_result(hsk_level, set_number):
    session_key = f'vocab_test_data_set_{hsk_level}_{set_number}'
    test_data = session.get(session_key)
    
    if not test_data:
        flash('Không tìm thấy dữ liệu bài kiểm tra.', 'error')
        return redirect(url_for('vocabulary_test'))
    
    # Tính điểm
    correct_count = 0
    results = []
    for question in test_data['questions']:
        is_correct = question['selected_choice'] == question['correct_answer']
        if is_correct:
            correct_count += 1
        results.append({
            'word': question['word'],
            'pinyin': question['pinyin'],
            'user_answer': question['selected_choice'],
            'correct_answer': question['correct_answer'],
            'is_correct': is_correct
        })
    
    total_questions = len(test_data['questions'])
    score = (correct_count / total_questions) * 100
    
    # Xóa dữ liệu bài kiểm tra khỏi session
    session.pop(session_key, None)
    
    return render_template('vocabulary_test_result.html', 
                           results=results, 
                           score=score, 
                           correct_count=correct_count,
                           total_questions=total_questions,
                           hsk_level=hsk_level,
                           set_number=set_number)

@app.route('/dictionary', methods=['GET', 'POST'])
def dictionary():
    if request.method == 'POST':
        character = request.form['character']
        combined_info = get_combined_info(character)
        return render_template('dictionary_result.html', info=combined_info)
    return render_template('dictionary.html')

if __name__ == '__main__':
    app.run(debug=False)
