from flask import Flask, render_template, redirect, url_for, session, request, jsonify
import random
from radicals import radicals
from flask_session import Session

from math import ceil

app = Flask(__name__)
app.secret_key = 'your_secret_key'
# Sử dụng server-side session để lưu trữ dữ liệu lớn
app.config['SESSION_TYPE'] = 'filesystem'
Session(app)

# Chia các bộ thủ thành các bộ đề, mỗi bộ đề 20 bộ thủ


def get_sets(radicals, radicals_per_set=20):
    sets = []
    for i in range(0, len(radicals), radicals_per_set):
        sets.append(radicals[i:i+radicals_per_set])
    return sets


radical_sets = get_sets(radicals)

# Trang chủ


@app.route('/')
def home():
    return render_template('home.html')

# ================== Phần Học ==================


@app.route('/radicals', methods=['GET'])
def all_radicals():
    query = request.args.get('q', '').strip()
    page = request.args.get('page', 1, type=int)
    per_page = 20  # Số bộ thủ mỗi trang

    if query:
        # Tìm kiếm theo bộ thủ hoặc nghĩa
        filtered_radicals = [
            r for r in radicals if query in r['radical'] or query.lower() in r['meaning'].lower()]
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
    selected_radicals = radical_sets[set_number - 1]  # Lấy bộ đề tương ứng
    total_questions = len(selected_radicals)

    # Khởi tạo dữ liệu bài kiểm tra trong session nếu chưa có
    if 'test_data' not in session or session.get('current_set') != set_number:
        session['current_set'] = set_number
        test_data = {
            'questions': [],
            'answers': {},
            'marked_questions': []
        }
        for idx, radical in enumerate(selected_radicals):
            question = {
                'index': idx + 1,
                'radical': radical['radical'],
                'meaning': radical['meaning'],
                'choices': generate_choices(radical['meaning']),
                'selected_choice': None,
                'is_marked': False
            }
            test_data['questions'].append(question)
        session['test_data'] = test_data

    test_data = session['test_data']

    if request.method == 'POST':
        action = request.form.get('action')
        question_index = int(request.form.get('question_index', 1)) - 1
        if action == 'save_answer':
            selected_choice = request.form.get('selected_choice')
            test_data['questions'][question_index]['selected_choice'] = selected_choice
            session['test_data'] = test_data
            if request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({'status': 'success', 'question_index': question_index + 1})
            else:
                return redirect(url_for('test_set', set_number=set_number))
        elif action == 'mark_question':
            test_data['questions'][question_index]['is_marked'] = not test_data['questions'][question_index]['is_marked']
            session['test_data'] = test_data
            if request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({'status': 'success', 'question_index': question_index + 1, 'is_marked': test_data['questions'][question_index]['is_marked']})
            else:
                return redirect(url_for('test_set', set_number=set_number, q=question_index+1))
        elif action == 'submit_test':
            # Tính điểm và hiển thị kết quả
            score = 0
            answers = []
            for q in test_data['questions']:
                is_correct = q['selected_choice'] == q['meaning']
                if is_correct:
                    score += 1
                answers.append({
                    'radical': q['radical'],
                    'selected': q['selected_choice'],
                    'correct': q['meaning'],
                    'is_correct': is_correct
                })
            # Xóa dữ liệu bài kiểm tra trong session
            session.pop('test_data', None)
            session.pop('current_set', None)
            return render_template('result.html', score=score, total=total_questions, answers=answers)

    # Lấy câu hỏi hiện tại dựa trên tham số 'q' trên URL
    current_question_index = int(request.args.get('q', 1)) - 1
    if current_question_index < 0 or current_question_index >= total_questions:
        current_question_index = 0
    current_question = test_data['questions'][current_question_index]

    return render_template('test_navigation.html', test_data=test_data, set_number=set_number, current_question=current_question, total_questions=total_questions)


def generate_choices(correct_meaning):
    choices = [correct_meaning]
    meanings = [r['meaning']
                for r in radicals if r['meaning'] != correct_meaning]
    choices.extend(random.sample(meanings, min(3, len(meanings))))
    random.shuffle(choices)
    return choices


# Review


@app.route('/review')
def review():
    import json
    answers = request.args.get('answers')
    answers = json.loads(answers)
    return render_template('review.html', answers=answers)

# Kiểm tra ngẫu nhiên


@app.route('/test/random', methods=['GET', 'POST'])
def test_random():
    total_questions = 20  # Bạn có thể điều chỉnh số lượng câu hỏi ngẫu nhiên
    # Khởi tạo dữ liệu bài kiểm tra trong session nếu chưa có
    if 'test_data_random' not in session:
        test_data = {
            'questions': [],
            'answers': {},
            'marked_questions': []
        }
        selected_radicals = random.sample(radicals, total_questions)
        for idx, radical in enumerate(selected_radicals):
            question = {
                'index': idx + 1,
                'radical': radical['radical'],
                'meaning': radical['meaning'],
                'choices': generate_choices(radical['meaning']),
                'selected_choice': None,
                'is_marked': False
            }
            test_data['questions'].append(question)
        session['test_data_random'] = test_data

    test_data = session['test_data_random']

    if request.method == 'POST':
        action = request.form.get('action')
        question_index = int(request.form.get('question_index', 1)) - 1
        if action == 'save_answer':
            selected_choice = request.form.get('selected_choice')
            test_data['questions'][question_index]['selected_choice'] = selected_choice
            session['test_data_random'] = test_data
            return redirect(url_for('test_random', q=question_index+1))
        elif action == 'mark_question':
            test_data['questions'][question_index]['is_marked'] = not test_data['questions'][question_index]['is_marked']
            session['test_data_random'] = test_data
            return redirect(url_for('test_random', q=question_index+1))
        elif action == 'submit_test':
            # Tính điểm và hiển thị kết quả
            score = 0
            answers = []
            for q in test_data['questions']:
                is_correct = q['selected_choice'] == q['meaning']
                if is_correct:
                    score += 1
                answers.append({
                    'radical': q['radical'],
                    'selected': q['selected_choice'],
                    'correct': q['meaning'],
                    'is_correct': is_correct
                })
            # Xóa dữ liệu bài kiểm tra trong session
            session.pop('test_data_random', None)
            return render_template('result.html', score=score, total=total_questions, answers=answers)

    # Lấy câu hỏi hiện tại dựa trên tham số 'q' trên URL
    current_question_index = int(request.args.get('q', 1)) - 1
    if current_question_index < 0 or current_question_index >= total_questions:
        current_question_index = 0
    current_question = test_data['questions'][current_question_index]

    return render_template('test_navigation.html', test_data=test_data, current_question=current_question, total_questions=total_questions, set_number=None)


if __name__ == '__main__':
    app.run(debug=False)
