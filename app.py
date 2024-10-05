from flask import Flask, render_template, redirect, url_for, session, request, jsonify, flash
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

genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

mydb = mysql.connector.connect(
    host=os.getenv('DB_CLOUD_HOST'),
    user=os.getenv('DB_CLOUD_USER'),
    password=os.getenv('DB_CLOUD_PASSWORD'),
    database=os.getenv('DB_CLOUD_NAME'),

)

mycursor = mydb.cursor(dictionary=True)

# Lấy tất cả người dùng
mycursor.execute("SELECT id, username, password FROM users")
users = mycursor.fetchall()

for user in users:
    # Giả sử mật khẩu hiện tại là plain text, chúng ta sẽ mã hóa nó
    hashed_password = bcrypt.generate_password_hash(
        user['password']).decode('utf-8')

    # Cập nhật mật khẩu đã mã hóa vào cơ sở dữ liệu
    sql = "UPDATE users SET password = %s WHERE id = %s"
    val = (hashed_password, user['id'])
    mycursor.execute(sql, val)

mydb.commit()

print(f"{mycursor.rowcount} record(s) affected")


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
        prompt = """Bạn là 1 người trung. Tôi là người Việt và tôi đặt câu hỏi như sau: Hãy tạo một câu tiếng Trung ngắn, hoàn toàn ngẫu nhiên và không giới hạn trong bất kỳ chủ đề nào nhưng dành cho người Việt học tiếng Trung, bao gồm:

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
    sentence_data = get_new_sentence()
    return render_template('home.html', sentence=sentence_data)


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
    radical = random.choice(radicals)
    return render_template('flashcard.html', radical=radical, next_url=url_for('learn_random'))

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


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        confirm_password = request.form['confirm_password']

        mycursor.execute(
            "SELECT * FROM users WHERE username = %s", (username,))
        existing_user = mycursor.fetchone()

        if existing_user:
            flash('Tên đăng nhập đã tồn tại. Vui lòng chọn tên khác.', 'error')
        elif password != confirm_password:
            flash('Mật khẩu không khớp. Vui lòng thử lại.', 'error')
        else:
            # Kiểm tra xem email đã tồn tại chưa
            mycursor.execute(
                "SELECT * FROM users WHERE email = %s", (email,))
            if mycursor.fetchone():
                flash('Email đã được sử dụng. Vui lòng chọn email khác.', 'error')
                return redirect(url_for('register'))

            # Tạo token xác minh
            token = secrets.token_urlsafe(32)
            verification_tokens[token] = {
                'username': username,
                'email': email,
                'password': password
            }

            # Gửi email xác minh
            send_verification_email(email, token)

            flash('Một email xác minh đã được gửi đến địa chỉ email của bạn. Vui lòng kiểm tra và xác nhận để hoàn tất đăng ký.', 'info')
            return redirect(url_for('login'))

    return render_template('register.html')


@app.route('/verify_email/<token>')
def verify_email(token):
    if token in verification_tokens:
        user_data = verification_tokens[token]

        # Thêm người dùng vào cơ sở dữ liệu
        hashed_password = bcrypt.generate_password_hash(
            user_data['password']).decode('utf-8')
        sql = "INSERT INTO users (username, email, password, is_admin, translation_count, last_translation_reset) VALUES (%s, %s, %s, %s, %s, %s)"
        val = (user_data['username'], user_data['email'],
               hashed_password, False, 0, datetime.now())
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
        username = request.form['username']
        password = request.form['password']

        mycursor.execute(
            "SELECT * FROM users WHERE username = %s", (username,))
        user = mycursor.fetchone()

        if user and bcrypt.check_password_hash(user['password'], password):
            session['user_id'] = user['id']
            session['is_admin'] = user['is_admin']

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


@app.route('/translate', methods=['GET', 'POST'])
def translate():
    user_id = session.get('user_id')
    is_admin = session.get('is_admin', False)

    if user_id:
        mycursor.execute(
            "SELECT * FROM whitelist WHERE user_id = %s", (user_id,))
        is_whitelisted = mycursor.fetchone() is not None
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
                    'Bạn đã sử dụng hết số lần dịch trong 24 giờ. Vui lòng thử lại sau.', 'error')
                return redirect(url_for('home'))

            # Increment translation count
            mycursor.execute(
                "UPDATE users SET translation_count = translation_count + 1 WHERE id = %s", (user_id,))
            mydb.commit()

        input_text = request.form['input_text']
        result = translate_and_analyze(input_text)

        return render_template('translate.html', result=result, input_text=input_text)

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
           CASE WHEN w.id IS NOT NULL THEN 1 ELSE 0 END AS is_whitelisted,
           CASE 
               WHEN u.is_admin = 1 THEN 'Không giới hạn'
               WHEN w.id IS NOT NULL THEN 'Không giới hạn'
               WHEN u.last_translation_reset IS NULL OR TIMESTAMPDIFF(HOUR, u.last_translation_reset, NOW()) > 24 THEN '10'
               ELSE CAST(10 - u.translation_count AS CHAR)
           END AS remaining_translations
    FROM users u 
    LEFT JOIN whitelist w ON u.id = w.user_id
    """)
    users = mycursor.fetchall()

    return render_template('admin_dashboard.html', history=history, users=users)


@app.route('/admin/whitelist/<int:user_id>', methods=['POST'])
@admin_required
def toggle_whitelist(user_id):
    action = request.form['action']

    if action == 'add':
        mycursor.execute(
            "INSERT INTO whitelist (user_id) VALUES (%s)", (user_id,))
    elif action == 'remove':
        mycursor.execute(
            "DELETE FROM whitelist WHERE user_id = %s", (user_id,))

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
        result = response.text.replace(". ", ".\n")

        # Lưu kết quả vào cơ sở dữ liệu
        sql = "INSERT INTO translation_history (input_text, result, created_at) VALUES (%s, %s, %s)"
        values = (text, result, datetime.now())
        mycursor.execute(sql, values)
        mydb.commit()

        return result
    except Exception as e:
        return "Đang lỗi, vui lòng thử lại sau"


if __name__ == '__main__':
    app.run(debug=False)
