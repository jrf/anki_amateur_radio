import sys
import shutil
import json
import requests


def request(action, **params):
    return {'action': action, 'params': params, 'version': 6}


def invoke(action, url, **params):
    url = 'http://localhost:8765'
    payload = json.dumps(request(action, **params))
    print(payload)
    response = requests.post(url, data=payload).json()
    if len(response) != 2:
        raise Exception('response has an unexpected number of fields')
    if 'error' not in response:
        raise Exception('response is missing required error field')
    if 'result' not in response:
        raise Exception('response is missing required result field')
    if response['error'] is not None:
        raise Exception(response['error'])
    return response['result']


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
    for idx, _ in enumerate(indices):
        try:
            start = indices[idx]
            end = indices[idx + 1]
            problem = text[start:end]
            del problem[0]
            tag = problem[0][0:3]
            answer = problem[0]
            answer = problem[0].split(' ')[1][1]
            del problem[0]
            notes = {}
            notes['deckName'] = deck_name
            notes['modelName'] = 'Basic'
            notes['tags'] = [tag]
            notes['fields'] = {}
            notes['fields']['Front'] = '<br /><br />'.join(problem)
            notes['fields']['Back'] = answer
            ret['params']['notes'].append(notes)
        except IndexError:
            continue
    return ret


if __name__ == "__main__":
    # create deck
    url = 'http://localhost:8765'
    deck_name = 'technician_class'
    invoke('createDeck', url, deck=deck_name)
    result = invoke('deckNames', url)
    print('got list of decks: {}'.format(result))

    # parse text
    fname = './technician_2018-2022.txt'
    payload = parse_text(fname, deck_name)
    response = requests.post(url, data=json.dumps(payload)).json()
