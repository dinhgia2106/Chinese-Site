from flask import request, session, jsonify, redirect, url_for, render_template
from utils import generate_choices
import random
from radicals import radicals

def test_set_handler(set_number, radical_sets):
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
                'choices': generate_choices(correct_answer, test_type, radicals),
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

def test_random_handler():
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
                'choices': generate_choices(correct_answer, test_type, radicals),
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