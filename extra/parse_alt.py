# import os
# import sys
import shutil
import json
# import pathlib
import requests


def parse_text(f, deck_name):
    ret = {}
    ret['action'] = 'addNotes'
    ret['version'] = 6
    ret['params'] = {}
    ret['params']['notes'] = []
    text = open(f, 'r', encoding='latin-1').read().splitlines()
    remove = ['']
    text = [x for x in text if x not in remove]
    indices = [i for i, s in enumerate(text) if '~~' in s]
    for idx, val in enumerate(indices):
        try:
            start = indices[idx]
            end = indices[idx + 1]
            problem = text[start:end]
            del problem[0]
            tag = problem[0][0:3]
            answer = problem[0]
            answer = problem[0].split(' ')[1][1]
            del problem[0]
            question_text = problem[0]
            answers = problem[1:]
            answer_text = [i for i in answers if i.startswith(answer)][0]
            answer_index = answers.index(answer_text)
            answer_text = '<b>' + answer_text + '</b>'
            answers[answer_index] = answer_text
            problem_new = [question_text] + answers
            notes = {}
            notes['deckName'] = deck_name
            notes['modelName'] = 'Basic'
            notes['tags'] = [tag]
            notes['fields'] = {}
            notes['fields']['Front'] = '<br /><br />'.join(problem_new)
            notes['fields']['Back'] = answer
            ret['params']['notes'].append(notes)
        except IndexError:
            continue
    return ret


if __name__ == "__main__":
    # fname = sys.argv[1]
    # deck = sys.argv[2]
    url = 'http://localhost:8765'
    fname = './extra.txt'
    deck_name = 'extra_license'
    fname_copy = fname.rstrip('.txt') + '_parsed.txt'
    shutil.copy(fname, fname_copy)
    payload = parse_text(fname_copy, deck_name)
    response = requests.post(url, data=json.dumps(payload)).json()
