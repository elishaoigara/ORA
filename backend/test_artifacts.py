"""Exercise the approved artifact workflow and inspect the exported file bytes."""
import io
import os
import unittest
from unittest.mock import patch
from uuid import uuid4

from docx import Document
from openpyxl import load_workbook
from pptx import Presentation
from pypdf import PdfReader

import test_mini as fixtures


class ArtifactTests(unittest.TestCase):
    setUp = fixtures.MiniTests.setUp
    tearDown = fixtures.MiniTests.tearDown
    phone = fixtures.MiniTests.phone
    state = fixtures.MiniTests.state

    def run_tool(self, name, args):
        return self.client.post('/api/v2/tools/run', headers=self.owner,
                                json={'name': name, 'args': args, 'request_id': uuid4().hex}).json()

    def approve(self, run):
        return self.client.post('/api/v2/tools/actions/' + run['id'], headers=self.owner,
                                json={'reject': False}).json()

    def download(self, id, auth=None):
        return self.client.get('/api/v2/documents/' + id + '/download', headers=auth if auth is not None else self.owner)

    def test_document_exports_and_versioned_edit(self):
        source = '# Launch plan\n- Build the MVP\n- Review the budget'
        docx = self.run_tool('documents.create', {'title': 'Launch plan', 'text': source, 'format': 'docx'})
        self.assertEqual(docx['status'], 'awaiting_approval')
        self.assertEqual(self.state()['documents'], [])
        saved = self.approve(docx)
        self.assertEqual(saved['status'], 'completed')
        self.assertNotIn('text', saved['result'])
        self.assertEqual(self.download(docx['id'], {}).status_code, 401)
        file = self.download(docx['id'])
        self.assertIn('wordprocessingml', file.headers['content-type'])
        self.assertIn('Build the MVP', ' '.join(p.text for p in Document(io.BytesIO(file.content)).paragraphs))
        self.assertEqual(self.run_tool('documents.read', {'id': docx['id']})['result']['text'], source)
        edit = self.run_tool('documents.edit', {'id': docx['id'], 'version': 1,
                                                'text': '# Updated plan\n- Ship', 'format': 'pdf'})
        self.assertEqual(edit['status'], 'awaiting_approval')
        self.assertIn('Ship', edit['preview']['diff'])
        self.assertEqual(self.approve(edit)['result']['version'], 2)
        self.assertIn('Ship', PdfReader(io.BytesIO(self.download(docx['id']).content)).pages[0].extract_text())
        stale = self.run_tool('documents.edit', {'id': docx['id'], 'version': 1, 'text': 'Overwritten'})
        self.assertEqual(stale['status'], 'failed')
        self.assertEqual(self.state()['documents'][0]['version'], 2)

    def test_powerpoint_and_edit_are_real_files(self):
        slides = [{'title': 'Problem', 'bullets': ['Slow handoffs', 'High costs']},
                  {'title': 'Plan', 'bullets': ['Pilot in Nairobi']}]
        run = self.run_tool('presentations.create', {'title': 'ORA pitch', 'slides': slides})
        self.assertEqual(run['preview']['slides'], slides)
        self.approve(run)
        prs = Presentation(io.BytesIO(self.download(run['id']).content))
        self.assertEqual(len(prs.slides), 2)
        self.assertIn('Pilot in Nairobi', ' '.join(sh.text for sh in prs.slides[1].shapes if sh.has_text_frame))
        revised = self.run_tool('presentations.edit', {'id': run['id'], 'version': 1,
                                                      'slides': [{'title': 'Revised', 'bullets': ['New direction']}]})
        self.approve(revised)
        self.assertEqual(len(Presentation(io.BytesIO(self.download(run['id']).content)).slides), 1)

    def test_spreadsheet_escapes_formula_strings(self):
        run = self.run_tool('spreadsheets.create', {'title': 'Costs',
                                                    'headers': ['=HYPERLINK("bad")', 'Amount'],
                                                    'rows': [['=2+2', 1500], ['+cmd', 2000]]})
        self.assertEqual(run['status'], 'awaiting_approval')
        self.approve(run)
        wb = load_workbook(io.BytesIO(self.download(run['id']).content))
        ws = wb.active
        self.assertEqual(ws['A1'].data_type, 's')
        self.assertEqual(ws['A2'].data_type, 's')
        self.assertEqual(ws['A2'].value, '=2+2')
        self.assertEqual(ws['B2'].value, 1500)
        self.assertEqual(self.run_tool('spreadsheets.create', {'title': 'Bad', 'headers': ['One'], 'rows': [[1, 2]]})['status'], 'failed')
        edit = self.run_tool('spreadsheets.edit', {'id': run['id'], 'version': 1,
                                                   'headers': ['Amount'], 'rows': [[3000]]})
        self.assertEqual(self.approve(edit)['result']['version'], 2)

    def test_research_returns_bounded_attributed_sources(self):
        results = {'results': [{'title': 'Primary', 'url': 'https://example.org/report', 'content': 'Evidence'},
                               {'title': 'Duplicate', 'url': 'https://example.org/report'},
                               {'title': 'Unsafe', 'url': 'http://example.org/file'}]}
        with patch.dict(os.environ, {'TAVILY_API_KEY': 'fake'}), patch('mini.tools.http', return_value=results) as provider:
            run = self.run_tool('research.sources', {'query': 'solar costs'})
        self.assertEqual(run['status'], 'completed')
        self.assertEqual(len(run['result']['sources']), 1)
        self.assertEqual(run['result']['sources'][0]['url'], 'https://example.org/report')
        self.assertEqual(provider.call_args.args[0], 'https://api.tavily.com/search')

    def test_phone_can_download_shared_file_without_public_url(self):
        run = self.run_tool('documents.create', {'title': 'Shared', 'text': 'Owner approved'})
        self.approve(run)
        phone, _, _ = self.phone()
        listing = self.client.get('/api/v2/tools', headers=phone).json()['documents']
        self.assertEqual(listing[0]['format'], 'md')
        self.assertEqual(self.download(run['id'], phone).content, b'Owner approved')


if __name__ == '__main__':
    unittest.main()
