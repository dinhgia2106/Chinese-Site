import unicodedata
from datetime import datetime, timezone, timedelta
import random
import string
import re
def remove_accents(input_str):
    nfkd_form = unicodedata.normalize('NFKD', input_str)
    return ''.join([c for c in nfkd_form if not unicodedata.combining(c)])

utc_plus_7 = timezone(timedelta(hours=7))

def get_sets(radicals, radicals_per_set=20):
    sets = []
    for i in range(0, len(radicals), radicals_per_set):
        sets.append(radicals[i:i+radicals_per_set])
    return sets

def generate_choices(correct_answer, test_type, radicals):
    choices = [correct_answer]
    if test_type == 'meaning':
        other_options = [r['meaning'] for r in radicals if r['meaning'] != correct_answer]
    elif test_type == 'pinyin':
        other_options = [r['pinyin'] for r in radicals if r['pinyin'] != correct_answer]
    choices.extend(random.sample(other_options, min(3, len(other_options))))
    random.shuffle(choices)
    return choices

def process_meanings(raw_meaning):
    raw_meaning = raw_meaning.replace('\n', '').strip()
    main_meanings = re.split(r'\d+\.\s*', raw_meaning)
    processed_meanings = [meaning.strip() for meaning in main_meanings if meaning.strip()]
    return processed_meanings

def format_number(value):
    try:
        number = int(float(value))
        return "{:,}".format(number)
    except ValueError:
        return value