from flask import Flask, render_template, redirect, url_for, session, request, jsonify
import random
from radicals import radicals
from flask_session import Session
import unicodedata
from math import ceil
from urllib.parse import quote
import google.generativeai as genai
from datetime import datetime
import os
from dotenv import load_dotenv
import json
import subprocess
from github import Github
from datetime import datetime, timezone, timedelta

load_dotenv()  # Load biến môi trường từ .env

app = Flask(__name__)
app.secret_key = 'your_secret_key'
# Sử dụng server-side session để lưu trữ dữ liệu lớn
app.config['SESSION_TYPE'] = 'filesystem'
Session(app)

genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))
BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def get_sets(radicals, radicals_per_set=20):
    sets = []
    for i in range(0, len(radicals), radicals_per_set):
        sets.append(radicals[i:i+radicals_per_set])
    return sets


radical_sets = get_sets(radicals)


def push_changes_to_github():
    GITHUB_TOKEN = os.getenv('GITHUB_TOKEN')
    if not GITHUB_TOKEN:
        print("GITHUB_TOKEN không được thiết lập.")
        return

    try:
        # Kết nối tới GitHub
        g = Github(GITHUB_TOKEN)

        repo = g.get_user().get_repo('radicals')

        # Đường dẫn tới tệp trong kho
        file_path = 'sentences.json'

        # Nội dung mới của tệp
        with open(file_path, 'r', encoding='utf-8') as file:
            content = file.read()

        # Kiểm tra xem tệp đã tồn tại trong kho chưa
        try:
            contents = repo.get_contents(file_path)
            # Cập nhật tệp
            repo.update_file(
                contents.path, "Cập nhật sentences.json", content, contents.sha)
        except Exception as e:
            # Nếu tệp chưa tồn tại, tạo mới
            repo.create_file(file_path, "Tạo sentences.json", content)

        print("Thay đổi đã được đẩy lên GitHub thành công.")
    except Exception as e:
        print(f"Lỗi khi đẩy thay đổi lên GitHub: {e}")


def remove_accents(input_str):
    # Hàm loại bỏ dấu tiếng Việt và dấu trong Pinyin
    nfkd_form = unicodedata.normalize('NFKD', input_str)
    return ''.join([c for c in nfkd_form if not unicodedata.combining(c)])


def get_new_sentence():
    utc_plus_7 = timezone(timedelta(hours=7))
    current_date = datetime.now(utc_plus_7).date()

    # Đường dẫn đến tệp JSON
    json_path = os.path.join(BASE_DIR, 'sentences.json')

    # Kiểm tra xem tệp JSON có tồn tại không
    if os.path.exists(json_path):
        with open(json_path, 'r', encoding='utf-8') as f:
            sentences = json.load(f)
    else:
        sentences = {}

    # Kiểm tra xem đã có câu nào được tạo cho ngày hôm nay chưa
    today_sentence = next((sentence for date, sentence in sentences.items()
                           if datetime.strptime(date, "%Y-%m-%d %H:%M:%S").date() == current_date), None)

    if today_sentence:
        return today_sentence

    # Nếu chưa có câu cho ngày hôm nay, tạo câu mới
    existing_sentences = set(sentence['chinese']
                             for sentence in sentences.values())
    result = None

    while True:
        prompt = """Hãy tạo một câu tiếng Trung ngắn, hoàn toàn ngẫu nhiên và không giới hạn trong bất kỳ chủ đề nào nhưng dành cho người Việt học tiếng Trung, bao gồm:

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
        # Tạo một khóa duy nhất cho câu mới, sử dụng timestamp
        timestamp = datetime.now(utc_plus_7).strftime("%Y-%m-%d %H:%M:%S")
        sentences[timestamp] = result

        # Ghi lại tệp JSON
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(sentences, f, ensure_ascii=False, indent=4)
        push_changes_to_github()

    return result


# Trang chủ


@app.route('/')
def home():
    sentence_data = get_new_sentence()
    return render_template('home.html', sentence=sentence_data)


@app.route('/history')
def history():
    # Đường dẫn đến tệp JSON
    json_path = os.path.join(BASE_DIR, 'sentences.json')

    # Đọc dữ liệu từ tệp JSON
    if os.path.exists(json_path):
        with open(json_path, 'r', encoding='utf-8') as f:
            sentences_dict = json.load(f)
    else:
        sentences_dict = {}

    # Chuyển đổi sang danh sách và sắp xếp
    sentences = [
        {'date': date, **data} for date, data in sentences_dict.items()
    ]
    sentences.sort(key=lambda x: x['date'], reverse=True)

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


@app.route('/translate', methods=['GET', 'POST'])
def translate():
    input_text = ''
    result = None
    if request.method == 'POST':
        input_text = request.form['input_text']
        result = translate_and_analyze(input_text)
    return render_template('translate.html', result=result, input_text=input_text)


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
        return response.text.replace(". ", ".\n")
    except Exception as e:
        return "Đang lỗi, vui lòng thử lại sau"


if __name__ == '__main__':
    app.run(debug=False)
