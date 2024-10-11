from flask import request, session, render_template, flash, redirect, url_for
from database import update_whitelist_status
from datetime import datetime, timedelta

from api_handlers import translate_and_analyze
from database import mydb, mycursor

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