"""Bounded Google Workspace operations. Mutations run only through tool approval."""
import re
import math
from urllib.parse import quote
from fastapi import HTTPException
from mini import google_workspace

BASES = {'drive': 'https://www.googleapis.com/drive/v3',
         'docs': 'https://docs.googleapis.com/v1',
         'sheets': 'https://sheets.googleapis.com/v4'}


def call(service, path, method='GET', body=None, params=None):
    from mini.tools import http
    return http(BASES[service] + path, method, body,
                {'Authorization': 'Bearer ' + google_workspace.access_token()}, params)


def file_id(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_-]{5,200}', value):
        raise HTTPException(422, 'Use the Google file ID from its URL or Drive search.')
    return value


def rows(value):
    from mini.tools import json_value
    value = json_value(value)
    if (not isinstance(value, list) or not 1 <= len(value) <= 200
            or any(not isinstance(row, list) or not 1 <= len(row) <= 30 for row in value)
            or any(type(cell) not in (str, int, float, bool) and cell is not None for row in value for cell in row)):
        raise HTTPException(422, 'Use 1–200 rows of up to 30 simple cell values each.')
    if any(type(cell) is float and not math.isfinite(cell) for row in value for cell in row):
        raise HTTPException(422, 'Cell numbers must be finite.')
    return value


def bounded_range(value):
    # Explicit rectangular ranges keep reads and overwrite previews bounded.
    if not isinstance(value, str) or len(value) > 200:
        raise HTTPException(422, 'Use a bounded A1 range such as Sheet1!A1:F50.')
    match = re.fullmatch(r"(?:[^!]+!)?([A-Za-z]{1,3})([1-9][0-9]{0,6}):([A-Za-z]{1,3})([1-9][0-9]{0,6})", value)
    if not match:
        raise HTTPException(422, 'Use a bounded A1 range such as Sheet1!A1:F50.')
    def col(s):
        n = 0
        for c in s.upper():
            n = n * 26 + ord(c) - 64
        return n
    c1, r1, c2, r2 = match.groups()
    height, width = int(r2) - int(r1) + 1, col(c2) - col(c1) + 1
    if not 1 <= height <= 200 or not 1 <= width <= 30:
        raise HTTPException(422, 'Choose up to 200 rows and 30 columns.')
    return value, height, width


def read(name, a):
    from mini.tools import text
    if name == 'google.drive.search':
        query = text(a.get('query'), 200).replace('\\', '\\\\').replace("'", "\\'")
        return call('drive', '/files', params={'q': "trashed = false and name contains '" + query + "'",
                    'pageSize': 30, 'fields': 'nextPageToken,files(id,name,mimeType,webViewLink,modifiedTime)'})
    if name == 'google.docs.read':
        return call('docs', '/documents/' + file_id(a.get('id')), params={'includeTabsContent': 'true'})
    if name == 'google.sheets.read':
        target, _, _ = bounded_range(a.get('range'))
        return call('sheets', '/spreadsheets/' + file_id(a.get('id')) + '/values/' + quote(target, safe=''))
    raise HTTPException(422, 'Unknown Google read tool.')


def prepare(name, a):
    from mini.tools import text
    clean = {}
    if name in ('google.docs.create', 'google.sheets.create'):
        clean['title'] = text(a.get('title'), 200)
    if name in ('google.docs.create', 'google.docs.append'):
        clean['text'] = text(a.get('text'), 20000)
    if name in ('google.sheets.create', 'google.sheets.write'):
        clean['rows'] = rows(a.get('rows'))
    if name == 'google.docs.append':
        clean['id'] = file_id(a.get('id'))
        original = call('docs', '/documents/' + clean['id'])
        clean['revision'] = original['revisionId']
        clean['title'] = original.get('title', '')
    if name == 'google.sheets.write':
        clean['id'] = file_id(a.get('id'))
        clean['range'], height, width = bounded_range(a.get('range'))
        if len(clean['rows']) != height or any(len(row) != width for row in clean['rows']):
            raise HTTPException(422, 'Provide exactly one value for every cell in the target range.')
        # Capture the exact current cells, and refuse approval if they changed.
        clean['before'] = read('google.sheets.read', clean)
    return clean, {'changes': clean, 'note': 'Changes Google account data after approval. Sheet values are literal text (RAW). Creation can leave an empty file if a later content request fails; inspect Google before retrying.'}


def write(name, a):
    if name == 'google.docs.create':
        doc = call('docs', '/documents', 'POST', {'title': a['title']})
        doc_id = file_id(doc['documentId'])
        call('docs', '/documents/' + doc_id + ':batchUpdate', 'POST',
             {'requests': [{'insertText': {'endOfSegmentLocation': {}, 'text': a['text']}}]})
        return {'id': doc_id, 'url': 'https://docs.google.com/document/d/' + doc_id + '/edit'}
    if name == 'google.docs.append':
        return call('docs', '/documents/' + a['id'] + ':batchUpdate', 'POST',
                    {'writeControl': {'requiredRevisionId': a['revision']},
                     'requests': [{'insertText': {'endOfSegmentLocation': {}, 'text': '\n' + a['text']}}]})
    if name == 'google.sheets.create':
        cells = [[{'userEnteredValue': ({'boolValue': cell} if type(cell) is bool else
                  {'numberValue': cell} if type(cell) in (int, float) else {'stringValue': '' if cell is None else str(cell)})}
                  for cell in row] for row in a['rows']]
        return call('sheets', '/spreadsheets', 'POST',
                    {'properties': {'title': a['title']}, 'sheets': [{'properties': {'title': 'Sheet1'},
                     'data': [{'rowData': [{'values': row} for row in cells]}]}]})
    if name == 'google.sheets.write':
        current = read('google.sheets.read', a)
        if current != a['before']:
            raise HTTPException(409, 'Sheet cells changed since the preview. Prepare the edit again.')
        return call('sheets', '/spreadsheets/' + a['id'] + '/values/' + quote(a['range'], safe=''),
                    'PUT', {'values': a['rows']}, {'valueInputOption': 'RAW'})
    raise HTTPException(422, 'Unknown Google write tool.')
