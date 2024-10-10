from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify, make_response, send_file
from radicals import radicals
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

load_dotenv()  # Load biến môi trường từ .env

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY')
# Sử dụng server-side session để lưu trữ dữ liệu lớn
app.config['SESSION_TYPE'] = 'filesystem'
Session(app)
bcrypt = Bcrypt(app)

app.config['MAIL_SERVER'] = os.getenv('MAIL_SERVER')
app.config['MAIL_PORT'] = int(os.getenv('MAIL_PORT', 587))
app.config['MAIL_USE_TLS'] = os.getenv('MAIL_USE_TLS') == 'True'
app.config['MAIL_USERNAME'] = os.getenv('MAIL_USERNAME')
app.config['MAIL_PASSWORD'] = os.getenv('MAIL_PASSWORD')
app.config['MAIL_DEFAULT_SENDER'] = os.getenv('MAIL_DEFAULT_SENDER')

mail = Mail(app)

# Lưu trữ token xác minh tạm thời
verification_tokens = {}
api_key=os.getenv("GOOGLE_API_KEY")

genai.configure(api_key=api_key)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

mydb = mysql.connector.connect(
    host=os.getenv('DB_CLOUD_HOST'),
    user=os.getenv('DB_CLOUD_USER'),
    password=os.getenv('DB_CLOUD_PASSWORD'),
    database=os.getenv('DB_CLOUD_NAME'),
    buffered=True
)


def execute_query(query, params=None):
    with mydb.cursor(dictionary=True) as cursor:
        cursor.execute(query, params)
        return cursor.fetchall()

mycursor = mydb.cursor(dictionary=True)



def get_sets(radicals, radicals_per_set=20):
    sets = []
    for i in range(0, len(radicals), radicals_per_set):
        sets.append(radicals[i:i+radicals_per_set])
    return sets


radical_sets = get_sets(radicals)


def remove_accents(input_str):
    # Hàm loại bỏ dấu tiếng Việt và dấu trong Pinyin
    nfkd_form = unicodedata.normalize('NFKD', input_str)
    return ''.join([c for c in nfkd_form if not unicodedata.combining(c)])

utc_plus_7 = timezone(timedelta(hours=7))

def update_whitelist_status(user_id):
    now = datetime.now(utc_plus_7)
    mycursor.execute("SELECT expiration_date, is_permanent FROM whitelist WHERE user_id = %s", (user_id,))
    result = mycursor.fetchone()
    if result:
        if result['is_permanent']:
            return True
        expiration_date = result['expiration_date']
        if expiration_date and now.date() > expiration_date:
            # Xóa khỏi whitelist nếu đã hết hạn
            mycursor.execute("DELETE FROM whitelist WHERE user_id = %s", (user_id,))
            mydb.commit()
            return False
        return now.date() <= expiration_date if expiration_date else False
    return False

# Cập nhật hàm is_whitelisted
def is_whitelisted(user_id):
    return update_whitelist_status(user_id)

def get_new_sentence():
    utc_plus_7 = timezone(timedelta(hours=7))
    current_date = datetime.now(utc_plus_7).date()
    current_datetime = datetime.now(utc_plus_7)

    # Kiểm tra xem đã có câu nào được tạo cho ngày hôm nay chưa
    mycursor.execute(
        "SELECT * FROM sentences WHERE DATE(created_at) = %s", (current_date,))
    today_sentence = mycursor.fetchone()

    if today_sentence:
        return today_sentence

    # Nếu chưa có câu cho ngày hôm nay, tạo câu mới
    mycursor.execute("SELECT chinese FROM sentences")
    existing_sentences = set(row['chinese'] for row in mycursor.fetchall())
    result = None

    while True:
        prompt = f"""Bạn là 1 người trung. Tôi là người Việt và tôi đặt câu hỏi như sau: Hãy tạo một câu tiếng Trung ngắn, hoàn toàn ngẫu nhiên và không giới hạn trong bất kỳ chủ đề nào nhưng dành cho người Việt học tiếng Trung, bao gồm:

- Chữ Hán
- Pinyin
- Âm Hán Việt (phiên âm Hán Việt của câu chữ Hán)
- Nghĩa tiếng Việt (dịch nghĩa của câu sang tiếng Việt)

Hãy đảm bảo rằng:

- Câu trả lời chỉ bao gồm các thông tin trên, không thêm nội dung khác.
- Định dạng kết quả chính xác như sau:

Chữ Hán: ...
Pinyin: ...
Âm Hán Việt: ...
Nghĩa tiếng Việt: ...

Không thêm bất kỳ văn bản nào khác.

Lưu ý: Câu được tạo ra phải khác với các câu sau đây:
{', '.join(existing_sentences)}
"""
        try:
            model = genai.GenerativeModel("gemini-1.5-flash")
            response = model.generate_content(prompt, generation_config=genai.types.GenerationConfig(
                temperature=1),)
            text = response.text
            lines = text.strip().split('\n')
            temp_result = {}
            for line in lines:
                if 'Chữ Hán:' in line:
                    temp_result['chinese'] = line.replace(
                        'Chữ Hán:', '').strip()
                elif 'Pinyin:' in line:
                    temp_result['pinyin'] = line.replace('Pinyin:', '').strip()
                elif 'Âm Hán Việt:' in line:
                    temp_result['sino_vietnamese'] = line.replace(
                        'Âm Hán Việt:', '').strip()
                elif 'Nghĩa tiếng Việt:' in line:
                    temp_result['vietnamese_meaning'] = line.replace(
                        'Nghĩa tiếng Việt:', '').strip()

            # Kiểm tra định dạng kết quả
            if len(temp_result) < 4:
                continue  # Nếu thiếu thông tin, chạy lại prompt

            # Kiểm tra xem câu đã tồn tại chưa
            if temp_result['chinese'] in existing_sentences:
                continue  # Nếu đã tồn tại, chạy lại prompt
            else:
                result = temp_result
                break  # Thoát khỏi vòng lặp khi có câu mới
        except Exception as e:
            print(f"Lỗi khi gọi Google Generative AI API: {e}")
            result = None
            break  # Thoát khỏi vòng lặp nếu có lỗi

    if result:
        # Lưu câu mới vào cơ sở dữ liệu
        sql = """INSERT INTO sentences 
                 (chinese, pinyin, sino_vietnamese, vietnamese_meaning, created_at, created_date) 
                 VALUES (%s, %s, %s, %s, %s, %s)"""
        values = (result['chinese'], result['pinyin'], result['sino_vietnamese'],
                  result['vietnamese_meaning'], current_datetime, current_date)
        mycursor.execute(sql, values)
        mydb.commit()

    return result


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


# ... Các import và khai báo khác ...


@app.route('/test/set/<int:set_number>', methods=['GET', 'POST'])
def test_set(set_number):
    test_type = request.args.get('test_type', 'meaning')
    selected_radicals = radical_sets[set_number - 1]
    total_questions = len(selected_radicals)

    session_key = f'test_data_set_{set_number}_{test_type}'

    if session.get('current_set') != set_number or session.get('test_type') != test_type or session_key not in session:
        session['current_set'] = set_number
        session['test_type'] = test_type
        test_data = {
            'questions': [],
            'answers': {},
            'marked_questions': []
        }
        for idx, radical in enumerate(selected_radicals):
            if test_type == 'meaning':
                correct_answer = radical['meaning']
            else:
                correct_answer = radical['pinyin']
            question = {
                'index': idx + 1,
                'radical': radical['radical'],
                'correct_answer': correct_answer,
                'choices': generate_choices(correct_answer, test_type),
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
            session[session_key] = test_data
            if request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({'status': 'success', 'question_index': question_index + 1})
            else:
                return redirect(url_for('test_set', set_number=set_number, test_type=test_type))
        elif action == 'mark_question':
            test_data['questions'][question_index]['is_marked'] = not test_data['questions'][question_index]['is_marked']
            session[session_key] = test_data
            if request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({'status': 'success', 'question_index': question_index + 1, 'is_marked': test_data['questions'][question_index]['is_marked']})
            else:
                return redirect(url_for('test_set', set_number=set_number, q=question_index+1, test_type=test_type))
        elif action == 'submit_test':
            score = 0
            answers = []
            for q in test_data['questions']:
                is_correct = q['selected_choice'] == q['correct_answer']
                if is_correct:
                    score += 1
                answers.append({
                    'radical': q['radical'],
                    'selected': q['selected_choice'],
                    'correct': q['correct_answer'],
                    'is_correct': is_correct
                })
            session.pop(session_key, None)
            session.pop('current_set', None)
            session.pop('test_type', None)
            return render_template('result.html', score=score, total=total_questions, answers=answers, test_type=test_type)

    current_question_index = int(request.args.get('q', 1)) - 1
    if current_question_index < 0 or current_question_index >= total_questions:
        current_question_index = 0
    current_question = test_data['questions'][current_question_index]

    return render_template('test_navigation.html', test_data=test_data, set_number=set_number, current_question=current_question, total_questions=total_questions, test_type=test_type)


def generate_choices(correct_answer, test_type):
    choices = [correct_answer]
    if test_type == 'meaning':
        other_options = [r['meaning']
                         for r in radicals if r['meaning'] != correct_answer]
    elif test_type == 'pinyin':
        other_options = [r['pinyin']
                         for r in radicals if r['pinyin'] != correct_answer]
    choices.extend(random.sample(other_options, min(3, len(other_options))))
    random.shuffle(choices)
    return choices


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
    test_type = request.args.get('test_type', 'meaning')
    total_questions = 20
    session_key = f'test_data_random_{test_type}'

    if session_key not in session:
        test_data = {
            'questions': [],
            'answers': {},
            'marked_questions': []
        }
        selected_radicals = random.sample(radicals, total_questions)
        for idx, radical in enumerate(selected_radicals):
            if test_type == 'meaning':
                correct_answer = radical['meaning']
            else:
                correct_answer = radical['pinyin']
            question = {
                'index': idx + 1,
                'radical': radical['radical'],
                'correct_answer': correct_answer,
                'choices': generate_choices(correct_answer, test_type),
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
            session[session_key] = test_data
            return redirect(url_for('test_random', q=question_index+1, test_type=test_type))
        elif action == 'mark_question':
            test_data['questions'][question_index]['is_marked'] = not test_data['questions'][question_index]['is_marked']
            session[session_key] = test_data
            return redirect(url_for('test_random', q=question_index+1, test_type=test_type))
        elif action == 'submit_test':
            score = 0
            answers = []
            for q in test_data['questions']:
                is_correct = q['selected_choice'] == q['correct_answer']
                if is_correct:
                    score += 1
                answers.append({
                    'radical': q['radical'],
                    'selected': q['selected_choice'],
                    'correct': q['correct_answer'],
                    'is_correct': is_correct
                })
            session.pop(session_key, None)
            return render_template('result.html', score=score, total=total_questions, answers=answers, test_type=test_type)

    current_question_index = int(request.args.get('q', 1)) - 1
    if current_question_index < 0 or current_question_index >= total_questions:
        current_question_index = 0
    current_question = test_data['questions'][current_question_index]

    return render_template('test_navigation.html', test_data=test_data, current_question=current_question, total_questions=total_questions, set_number=None, test_type=test_type)


def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function


def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session or not session.get('is_admin'):
            flash('Bạn không có quyền truy cập trang này.', 'error')
            return redirect(url_for('home'))
        return f(*args, **kwargs)
    return decorated_function


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


@app.route('/logout')
def logout():
    session.clear()
    flash('Đã đăng xuất thành công!', 'success')
    return redirect(url_for('home'))


def is_whitelisted(user_id):
    mycursor.execute("SELECT expiration_date, is_permanent FROM whitelist WHERE user_id = %s", (user_id,))
    result = mycursor.fetchone()
    if result:
        if result['is_permanent']:
            return True
        expiration_date = result['expiration_date']
        return datetime.now().date() <= expiration_date if expiration_date else False
    return False

@app.route('/translate', methods=['GET', 'POST'])
def translate():
    user_id = session.get('user_id')
    is_admin = session.get('is_admin', False)

    if user_id:
        is_whitelisted = update_whitelist_status(user_id)
    else:
        is_whitelisted = False

    if request.method == 'POST':
        if not user_id:
            if session.get('anonymous_translations', 0) >= 3:
                flash(
                    'Bạn đã sử dụng hết số lần dịch. Vui lòng đăng nhập để tiếp tục.', 'error')
                return redirect(url_for('login'))
            session['anonymous_translations'] = session.get(
                'anonymous_translations', 0) + 1
        elif not is_whitelisted and not is_admin:
            mycursor.execute(
                "SELECT translation_count, last_translation_reset FROM users WHERE id = %s", (user_id,))
            user_data = mycursor.fetchone()
            translation_count = user_data['translation_count']
            last_reset = user_data['last_translation_reset']

            now = datetime.now()
            if last_reset is None or (now - last_reset) > timedelta(hours=24):
                # Reset translation count after 24 hours
                translation_count = 0
                mycursor.execute(
                    "UPDATE users SET translation_count = 0, last_translation_reset = %s WHERE id = %s", (now, user_id))
                mydb.commit()

            if translation_count >= 10:
                flash(
                    'Bạn đã sử dụng hết số lần dịch trong 24 giờ. Vui lòng thử lại sau hoặc liên lạc với admin bằng thông tin ở trang chủ.', 'error')
                return redirect(url_for('home'))

            # Increment translation count
            mycursor.execute(
                "UPDATE users SET translation_count = translation_count + 1 WHERE id = %s", (user_id,))
            mydb.commit()

        input_text = request.form['input_text']
        translation_result = translate_and_analyze(input_text)
        
        if 'error' in translation_result:
            flash(translation_result['error'], 'error')
            return redirect(url_for('translate'))
        
        return render_template('translate.html', 
                               result=translation_result['result'], 
                               input_text=input_text,
                               audio_url=translation_result.get('audio_url'))

    return render_template('translate.html')

@admin_required
def admin_dashboard():
    mycursor.execute(
        "SELECT * FROM translation_history ORDER BY created_at DESC")
    history = mycursor.fetchall()

    mycursor.execute(
        "SELECT u.*, CASE WHEN w.id IS NOT NULL THEN 1 ELSE 0 END AS is_whitelisted FROM users u LEFT JOIN whitelist w ON u.id = w.user_id")
    users = mycursor.fetchall()

    return render_template('admin_dashboard.html', history=history, users=users)


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


def translate_and_analyze(text):
    prompt = f"""
        Bạn là một chuyên gia ngôn ngữ Trung - Việt, hãy thực hiện các yêu cầu sau:

        Đọc đoạn văn bản sau:
        {text}

        Phân tích đoạn văn và câu văn tiếng Trung:

        Nếu đoạn văn bản nhiều hơn 10 từ thì chỉ cần trả về bản dịch với cấu trúc sau (nếu là tiếng Trung, nếu không phải thì trả về kết quả: "Vui lòng nhập tiếng Trung"):

        Đây là nội dung bản dịch:
        - [Bản dịch tiếng Việt]

        Nếu đoạn văn bản có 10 từ trở xuống thì thực hiện các bước sau:

        Dịch toàn bộ đoạn văn bản sang tiếng Việt.
        Phân tích từng chữ Hán theo các yêu cầu sau:
        Nghĩa Hán Việt
        Bộ thủ tạo thành chữ đó
        Pinyin
        Ý nghĩa tiếng Việt
        Gợi ý cách nhớ
        Cách sử dụng
        Các từ liên quan
        Sau đó hãy kiểm tra kết quả step by step và trả về kết quả cuối cùng.
        Trình bày kết quả theo định dạng sau:

        Bản dịch: [Bản dịch tiếng Việt]
        Phân tích từng chữ:
        Chữ [Chữ Hán]:
        - Nghĩa Hán Việt: [Nghĩa]
        - Bộ thủ: [Danh sách bộ thủ]
        - Pinyin: [Cách đọc]
        - Ý nghĩa tiếng Việt: [Ý nghĩa]
        - Gợi ý cách nhớ: [Gợi ý]
        - Cách sử dụng: [Cách sử dụng]
        - Các từ liên quan: [Các từ liên quan]
        [Chữ Hán tiếp theo]
        Chỉ cung cấp thông tin được yêu cầu, không thêm bất kỳ giải thích nào khác.
    """

    try:
        model = genai.GenerativeModel("gemini-1.5-pro")
        response = model.generate_content(prompt)
        
        # Kiểm tra xem response có thuộc tính text không
        if hasattr(response, 'text'):
            result = response.text
        else:
            # Nếu không có thuộc tính text, thử lấy nội dung từ parts
            result = ''.join([part.text for part in response.parts])

        # Lưu kết quả vào cơ sở dữ liệu
        sql = "INSERT INTO translation_history (input_text, result, created_at) VALUES (%s, %s, %s)"
        values = (text, result, datetime.now())
        mycursor.execute(sql, values)
        mydb.commit()

        # Thêm chức năng nghe cho đoạn văn gốc
        api_key = os.getenv("GOOGLE_TEXT_TO_SPEECH_API_KEY")
        url = f'https://texttospeech.googleapis.com/v1/text:synthesize?key={api_key}'
        
        # Loại bỏ nội dung trong dấu ngoặc
        clean_text = re.sub(r'\s*\(.*?\)', '', text)
        
        payload = {
            'input': {
                'text': clean_text
            },
            'voice': {
                'languageCode': 'cmn-CN',
                'name': 'cmn-CN-Standard-A'
            },
            'audioConfig': {
                'audioEncoding': 'MP3'
            }
        }
        
        headers = {'Content-Type': 'application/json'}
        
        try:
            tts_response = requests.post(url, json=payload, headers=headers)
            tts_response.raise_for_status()
            
            audio_content = tts_response.json().get('audioContent')
            if audio_content:
                filename = f"audio_{uuid.uuid4()}.mp3"
                file_path = os.path.join('static', 'audio', filename)
                
                audio_data = base64.b64decode(audio_content)
                with open(file_path, 'wb') as f:
                    f.write(audio_data)
                
                audio_url = f'/static/audio/{filename}'
                return {
                    'audio_url': audio_url,
                    'result': result
                }
            else:
                print("Không nhận được dữ liệu âm thanh từ API")
                return {'result': result}
        except requests.RequestException as e:
            print(f"Lỗi khi gọi API Text-to-Speech: {str(e)}")
            return {'result': result}

    except Exception as e:
        return {'error': f"Đang lỗi, vui lòng thử lại sau. Chi tiết lỗi: {str(e)}"}

# Thêm vào phần cấu hình
app.config['SECURITY_PASSWORD_SALT'] = 'your-security-password-salt'  # Thay đổi giá trị này
serializer = URLSafeTimedSerializer(app.config['SECRET_KEY'])

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

def check_transaction(reference_code):
    url = "https://my.sepay.vn/userapi/transactions/list"
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        data = response.json()
        
        for transaction in data.get('transactions', []):
            if f"TTGP {reference_code}" in transaction['transaction_content']:
                return float(transaction['amount_in'])
        return None
    except requests.exceptions.RequestException as e:
        print(f"Lỗi khi gọi API: {e}")
        return None
    
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

@app.template_filter('format_number')
def format_number(value):
    try:
        # Chuyển đổi giá trị thành số nguyên
        number = int(float(value))
        # Định dạng số với dấu phẩy ngăn cách hàng nghìn
        return "{:,}".format(number)
    except ValueError:
        # Nếu không thể chuyển đổi thành số, trả về giá trị gốc
        return value

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
        
        # Read and encode the audio file
        audio_content = base64.b64encode(audio_file.read()).decode('utf-8')
        
        # Prepare data for Speech-to-Text API
        api_key = os.getenv("GOOGLE_TEXT_TO_SPEECH_API_KEY")
        url = f'https://speech.googleapis.com/v1/speech:recognize?key={api_key}'
        
        request_data = {
            'config': {
                'languageCode': 'zh-CN',
                'encoding': 'MP3',
                'sampleRateHertz': 16000
            },
            'audio': {
                'content': audio_content
            }
        }
        
        # Send request to Speech-to-Text API
        response = requests.post(url, json=request_data)
        
        if response.status_code == 200:
            result = response.json()
            if 'results' in result:
                transcript = result['results'][0]['alternatives'][0]['transcript']
                
                # Use Gemini API to check and correct errors
                prompt = f""" 
                Bạn là một giáo viên tiếng Trung thân thiện. Hãy kiểm tra xem người học đã đọc đúng chưa và đưa ra phản hồi như trong một cuộc hội thoại.

                Câu yêu cầu đọc: "{text_to_read}"
                Câu người học đã đọc: "{transcript}"
                Chuyển cả 2 sang pinyin vì chỉ kiểm tra phát âm ví dụ như "他" và "她" đều đọc là "tā" nên người học đọc vẫn đúng (Lưu ý: pinyin là để bạn kiểm tra, sau khi kiểm tra xong thì không cần dùng pinyin nữa)
                Hãy kiểm tra và đưa ra phản hồi theo mẫu sau:

                Nếu đọc sai:
                Bạn đã đọc chưa chính xác. Hãy cùng xem lại nhé!
                Nhận xét: 
                [Nhận xét về cách đọc, chỉ ra lỗi cụ thể]
                
                Cách sửa: 
                [Hướng dẫn cách đọc đúng, giải thích rõ ràng]
                
                Đừng nản chí nhé! Hãy thử lại lần nữa. Bạn có thể làm được!

                Ví dụ cho trường hợp đọc sai: 
                'Bạn đã đọc chưa chính xác. Hãy cùng xem lại nhé!
                Nhận xét:
                Bạn đã đọc "立场" (lìchăng) thay vì "你好" (nǐ hǎo). Hai chữ này có cách đọc rất khác nhau.
                Cách sửa:
                Khi đọc "你好", bạn cần chú ý phát âm nhẹ âm sắc ở vần thứ hai ("-ǎo"). Âm "h" cũng được phát âm rất nhẹ, gần như không nghe thấy. Hãy thử đọc lại "你好" và chú ý đến cách phát âm này.'
                
                Nếu đọc đúng:
                Tuyệt vời! Bạn đã đọc rất chuẩn.
                
                Nhận xét: 
                [Nhận xét tích cực về cách đọc của người học]
                
                Hãy tiếp tục phát huy nhé! Bạn đang tiến bộ rất nhanh đấy.

                Ví dụ cho trường hợp đọc đúng:
                'Tuyệt vời! Bạn đã đọc rất chuẩn.
                Nhận xét:
                Bạn đã phát âm rõ ràng và chính xác từng âm tiết. Giọng điệu cũng rất tự nhiên.'
                
                Hãy tiếp tục phát huy nhé! Bạn đang tiến bộ rất nhanh đấy.
                Chỉ trả lời theo đúng định dạng trên, không thêm nội dung khác.
                """
                
                model = genai.GenerativeModel("gemini-pro")
                response = model.generate_content(prompt)
                feedback = response.text
                
                return jsonify({'transcript': transcript, 'feedback': feedback})
            else:
                return jsonify({'error': 'Speech could not be recognized, please try again.'}), 400
        else:
            return jsonify({'error': f'API Error: {response.status_code} - {response.text}'}), 400
    
    # GET request: display the page
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
        # Lấy dữ liệu từ vựng và thứ tự viết từ file JSON
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
        
        return render_template('vocabulary_learn_result.html', words=combined_data)
    return render_template('vocabulary_learn.html')

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
    with open('static/vocab.json', 'r', encoding='utf-8') as f:
        vocab_data = json.load(f)
    
    hsk_vocab = [word for word in vocab_data if word['HSK'] == hsk_level]
    
    # Chọn chính xác 30 từ cho bộ đề hiện tại
    start_index = (set_number - 1) * 30
    test_words = hsk_vocab[start_index:start_index + 30]
    
    # Tạo câu hỏi cho mỗi từ
    questions = []
    for i, word in enumerate(test_words):
        correct_answer = word['VietnameseMeaning']
        wrong_answers = random.sample([w['VietnameseMeaning'] for w in hsk_vocab if w != word], 3)
        answers = wrong_answers + [correct_answer]
        random.shuffle(answers)
        
        questions.append({
            'id': i,  # Thêm id để dễ dàng xác định câu hỏi
            'word': word['Chinese'],
            'pinyin': word['Pinyin'],
            'answers': answers,
            'correct_answer': correct_answer
        })
    
    return render_template('vocabulary_test_questions.html', questions=questions, hsk_level=hsk_level, set_number=set_number)

@app.route('/vocabulary/test/result', methods=['POST'])
def vocabulary_test_result():
    user_answers = request.form
    correct_count = 0
    total_questions = 30

    results = []
    for i in range(total_questions):
        word = user_answers.get(f'word_{i}')
        user_answer = user_answers.get(f'answer_{i}')
        correct_answer = user_answers.get(f'correct_answer_{i}')
        
        is_correct = user_answer == correct_answer
        if is_correct:
            correct_count += 1
        
        results.append({
            'word': word,
            'user_answer': user_answer,
            'correct_answer': correct_answer,
            'is_correct': is_correct
        })

    score = (correct_count / total_questions) * 100
    return render_template('vocabulary_test_result.html', results=results, score=score, total_questions=total_questions)

@app.route('/dictionary', methods=['GET', 'POST'])
def dictionary():
    if request.method == 'POST':
        character = request.form['character']
        combined_info = get_combined_info(character)
        return render_template('dictionary_result.html', info=combined_info)
    return render_template('dictionary.html')

def process_meanings(raw_meaning):
  # Remove newlines and extra spaces
  raw_meaning = raw_meaning.replace('\n', '').strip()
  
  # Use a regular expression to split based on numbers followed by a period
  # Ensure that the period is followed by a non-digit character
  main_meanings = re.split(r'\d+\.\s*', raw_meaning)
  
  processed_meanings = []
  for meaning in main_meanings:
      if meaning.strip():
          # Strip leading and trailing spaces
          meaning = meaning.strip()
          processed_meanings.append(meaning)
  
  return processed_meanings

def get_hannom_info(character):
  url = f"https://hvdic.thivien.net/whv/{character}"
  response = requests.get(url)
  soup = BeautifulSoup(response.content, 'html.parser')

  result = {
      'character': character,
      'han_viet': None,
      'pinyin': None,  # Add Pinyin field
      'total_strokes': None,
      'radical': None,
      'meanings': None,
      'found': False
  }

  # Check if there is a result
  info_div = soup.find('div', class_='info')
  if info_div and "Có 1 kết quả:" in info_div.text:
      result['found'] = True
      hvres_div = soup.find('div', class_='hvres')
      if hvres_div:
          # Get Han Viet reading
          han_viet = hvres_div.find('a', class_='hvres-goto-link')
          if han_viet:
              result['han_viet'] = han_viet.text.strip()

          # Get Pinyin
          pinyin_tag = hvres_div.find(string=lambda x: x and 'Âm Pinyin:' in x)
          if pinyin_tag:
              pinyin_element = pinyin_tag.find_next('a')
              if pinyin_element:
                  result['pinyin'] = pinyin_element.text.strip()

          # Get meanings
          meaning_div = hvres_div.find('div', class_='hvres-meaning')
          if meaning_div:
              raw_meaning = meaning_div.text.strip()
              result['meanings'] = process_meanings(raw_meaning)

  elif soup.find('div', class_='hvres'):
      result['found'] = True
      hvres_divs = soup.find_all('div', class_='hvres')
      main_hvres = hvres_divs[0]
      main_details = main_hvres.find('div', class_='hvres-details')
      if main_details:
          # Find "Âm Hán Việt:"
          av_tag = main_details.find(string=lambda x: x and 'Âm Hán Việt:' in x)
          if av_tag:
              parent = av_tag.parent
              spans = parent.find_all('span', class_='hvres-goto-link')
              readings = [span.get_text(strip=True) for span in spans]
              result['han_viet'] = ', '.join(readings)

          # Find "Pinyin:"
          pinyin_tag = main_details.find(string=lambda x: x and 'Âm Pinyin:' in x)
          if pinyin_tag:
              pinyin_element = pinyin_tag.find_next('a')
              if pinyin_element:
                  result['pinyin'] = pinyin_element.text.strip()

          # Find "Tổng nét:"
          tn_tag = main_details.find(string=lambda x: x and 'Tổng nét:' in x)
          if tn_tag:
              tn_text = tn_tag.strip()
              tn = tn_text.split('Tổng nét:')[-1].strip()
              result['total_strokes'] = tn

          # Find "Bộ:"
          b_tag = main_details.find(string=lambda x: x and 'Bộ:' in x)
          if b_tag:
              a_tag = b_tag.find_next('a')
              if a_tag:
                  radical = a_tag.get_text(strip=True)
                  extra_info = a_tag.next_sibling
                  if extra_info:
                      radical += ' ' + extra_info.strip()
                  result['radical'] = radical

      # Process meanings
      meanings = []
      for hvres in hvres_divs:
          details = hvres.find('div', class_='hvres-details')
          if details:
              sources = details.find_all('p', class_='hvres-source')
              for p in sources:
                  p_text = p.get_text(strip=True)
                  if 'Từ điển' in p_text:
                      meaning_div = p.find_next_sibling('div', class_='hvres-meaning')
                      if meaning_div and 'han-clickable' in meaning_div.get('class', []):
                          meaning_text = meaning_div.get_text(strip=True)
                          meanings.extend(process_meanings(meaning_text))
                          if len(meanings) >= 2:  # Adjust if you want more meanings
                              break
              if len(meanings) >= 2:
                  break
      
      if meanings:
          result['meanings'] = meanings

  return result

def get_stroke_order(character):
  url = f"https://www.strokeorder.com/chinese/{character}"
  response = requests.get(url)
  soup = BeautifulSoup(response.content, 'html.parser')

  result = {
      'character': character,
      'wubi': '',
      'cangjie': '',
      'zhengma': '',
      'four_corner': '',
      'unicode': '',
      'stroke_order_animation': '',
      'stroke_order_diagrams': []
  }

  # Extract input method information
  input_method_items = soup.find_all('div', class_='stroke-hanzi-item')
  for item in input_method_items:
      left = item.find('span', class_='stroke-hanzi-info-left')
      right = item.find('span', class_='stroke-hanzi-info-right')
      if left and right:
          key = left.text.strip().lower()
          value = right.text.strip()
          if key in result:
              result[key] = value

  # Extract stroke order animation
  animation = soup.find('img', alt=f"{character} Stroke Order Animation")
  if animation:
      result['stroke_order_animation'] = 'https://www.strokeorder.com' + animation['src']

  # Extract stroke order diagrams
  diagrams = soup.find_all('img', alt=f"{character} Stroke Order Diagrams")
  for diagram in diagrams:
      result['stroke_order_diagrams'].append('https://www.strokeorder.com' + diagram['src'])

  return result

def get_combined_info(character):
    hannom_info = get_hannom_info(character)
    stroke_order_info = get_stroke_order(character)
    
    combined_info = {**hannom_info, **stroke_order_info}
    return combined_info

if __name__ == '__main__':
    app.run(debug=False)
