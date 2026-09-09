import os
import unittest
from unittest.mock import patch
from uuid import uuid4
import test_mini as fixtures
import next_api as api
from mini.tools import calculate, execute_read, prepare, Runtime, catalog
from fastapi import HTTPException

class ToolTests(unittest.TestCase):
 setUp=fixtures.MiniTests.setUp
 tearDown=fixtures.MiniTests.tearDown
 phone=fixtures.MiniTests.phone
 state=fixtures.MiniTests.state
 def run_tool(self,name,args,rid=None,auth=None):
  return self.client.post('/api/v2/tools/run',headers=auth or self.owner,json={'name':name,'args':args,'request_id':rid or uuid4().hex})
 def approve(self,rid,auth=None):return self.client.post('/api/v2/tools/actions/'+rid,headers=auth or self.owner,json={'reject':False})
 def test_calculator_cannot_execute_code(self):
  self.assertEqual(calculate('(12+4)*3'),48)
  for expr in ['__import__("os").system("pwd")','2**99999999','1/0','[1,2]','float("inf")']:
   with self.assertRaises(HTTPException):calculate(expr)
 def test_task_requires_review_and_approval_is_idempotent(self):
  rid=uuid4().hex;r=self.run_tool('tasks.create',{'title':'Write tests'},rid).json()
  self.assertEqual(r['status'],'awaiting_approval');self.assertEqual(self.state()['tasks'],[])
  self.assertEqual(self.run_tool('tasks.create',{'title':'Different'},rid).json()['id'],r['id'])
  self.assertEqual(self.approve(r['id']).json()['status'],'completed')
  self.approve(r['id']);self.assertEqual(len(self.state()['tasks']),1)
 def test_disabled_tool_blocks_execution_and_pending_approval(self):
  r=self.run_tool('tasks.create',{'title':'Test'}).json()
  self.client.post('/api/v2/tools/settings',headers=self.owner,json={'name':'tasks.create','enabled':False})
  self.assertEqual(self.run_tool('tasks.create',{'title':'No'}).status_code,403)
  self.assertEqual(self.approve(r['id']).json()['status'],'needs_review');self.assertEqual(self.state()['tasks'],[])
 def test_device_cannot_review_other_phone_action(self):
  first,_,_=self.phone();second,_,_=self.phone()
  r=self.run_tool('tasks.create',{'title':'Private phone action'},auth=first).json()
  self.assertEqual(self.approve(r['id'],second).status_code,404)
 def test_repository_scope_cannot_be_expanded(self):
  with patch.dict(os.environ,{'GITHUB_TOKEN':'dummy','ORA_GITHUB_REPOS':'owner/allowed'}),patch('mini.tools.gh') as gh:
   r=self.run_tool('github.file',{'repo':'owner/other','path':'README.md'}).json()
   self.assertEqual(r['status'],'failed');gh.assert_not_called()
 def test_stale_patch_never_creates_branch(self):
  with patch.dict(os.environ,{'GITHUB_TOKEN':'dummy','ORA_GITHUB_REPOS':'owner/allowed'}),patch('mini.tools.gh',return_value={'object':{'sha':'current'}}) as gh:
   r=self.run_tool('github.change',{'repo':'owner/allowed','base':'main','base_sha':'old','title':'Fix','body':'Review','files':[{'path':'app.py','content':'pass\n'}]}).json()
   self.assertEqual(r['status'],'failed');self.assertEqual(gh.call_count,1)
 def test_external_failure_is_not_automatically_retried(self):
  with patch.dict(os.environ,{'GITHUB_TOKEN':'dummy','ORA_GITHUB_REPOS':'owner/allowed'}):
   r=self.run_tool('github.issue.create',{'repo':'owner/allowed','title':'Issue','body':'Details'}).json()
   with patch('mini.tools.gh',side_effect=HTTPException(502,'Ambiguous timeout')) as gh:
    self.approve(r['id']);self.approve(r['id']);self.assertEqual(gh.call_count,1)
 def test_document_download_is_authenticated(self):
  r=self.run_tool('documents.create',{'title':'Plan','text':'A useful plan'}).json();self.approve(r['id'])
  self.assertEqual(self.client.get('/api/v2/documents/'+r['id']+'/download').status_code,401)
  self.assertEqual(self.client.get('/api/v2/documents/'+r['id']+'/download',headers=self.owner).text,'A useful plan')
 def test_routines_cannot_include_writes(self):
  r=self.run_tool('routines.save',{'name':'Unsafe','steps':[{'tool':'email.send','args':{}}]}).json();self.assertEqual(r['status'],'failed')
 def test_phone_action_never_claims_message_sent(self):
  r=self.run_tool('phone.action',{'kind':'sms','target':'+254700000000','body':'Hello'}).json();self.assertEqual(r['result']['status'],'prepared');self.assertTrue(r['result']['handoff_url'].startswith('sms:'))
 def test_csv_summary(self):
  r=self.run_tool('data.analyze',{'csv':'item,cost\na,10\nb,20\n'}).json();self.assertEqual(r['result']['columns']['cost']['sum'],30)
 def test_github_change_preserves_base_and_creates_only_draft(self):
  args={'repo':'owner/allowed','base':'main','base_sha':'head','title':'Add note','body':'Review','files':[{'path':'note.md','content':'hello\n'}]}
  answers=[{'object':{'sha':'head'}},{'tree':[]},{'object':{'sha':'head'}},{'tree':{'sha':'base-tree'}},{'sha':'new-tree'},{'sha':'new-commit'},{'ref':'refs/heads/ora/new'},{'html_url':'https://github.com/owner/allowed/pull/1','draft':True}]
  with patch.dict(os.environ,{'GITHUB_TOKEN':'dummy','ORA_GITHUB_REPOS':'owner/allowed'}),patch('mini.tools.gh',side_effect=answers) as gh:
   r=self.run_tool('github.change',args).json();self.assertIn('+hello',r['preview']['diff'])
   out=self.approve(r['id']).json();self.assertEqual(out['status'],'completed');self.assertTrue(out['result']['draft'])
   tree_call=gh.call_args_list[4];self.assertEqual(tree_call.args[2]['base_tree'],'base-tree')
   self.assertTrue(gh.call_args_list[-1].args[2]['draft'])

 def test_routine_obeys_disabled_tools(self):
  r=self.run_tool('routines.save',{'name':'Plan','steps':[{'tool':'tasks.list','args':{}}]}).json();self.approve(r['id'])
  self.client.post('/api/v2/tools/settings',headers=self.owner,json={'name':'tasks.list','enabled':False})
  self.assertEqual(self.run_tool('routines.run',{'id':r['id']}).json()['status'],'failed')
 def test_chat_receives_real_tool_evidence(self):
  import json
  from mini.intelligence import respond
  from unittest.mock import Mock
  first=Mock(ok=True);first.json.return_value={'choices':[{'message':{'role':'assistant','content':None,'tool_calls':[{'id':'call_1','type':'function','function':{'name':'use_tool','arguments':json.dumps({'name':'calculator','arguments':json.dumps({'expression':'2+2'})})}}]}}]}
  last=Mock(ok=True);last.json.return_value={'choices':[{'message':{'role':'assistant','content':'The result is 4.'}}]}
  with patch.dict(os.environ,{'GROQ_API_KEY':'test'}),patch('mini.intelligence.requests.post',side_effect=[first,last]) as provider:
   reply,_=respond(api.db().read(),'What is 2+2?',execute=lambda name,args,call_id:api.tool_runtime().run(name,args,{'id':'test-auth'},call_id))
   self.assertIn('4',reply)
   messages=provider.call_args.kwargs['json']['messages']
   evidence=next(m for m in messages if m['role']=='tool')
   self.assertEqual(json.loads(evidence['content'])['result']['result'],4)
