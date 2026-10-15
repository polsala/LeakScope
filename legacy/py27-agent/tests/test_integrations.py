import imp
import os
import sys
import types
import unittest


class IntegrationTest(unittest.TestCase):
    def test_erp_diagnostics_do_not_change_business_results(self):
        root=os.path.abspath(os.path.join(os.path.dirname(__file__),'..','..','..'))
        adapter=imp.load_source('leakscope_test_erp',os.path.join(root,'legacy/integrations/erp/leakscope_erp.py'))
        original=sys.modules.get('leakscope_agent')
        fake=types.ModuleType('leakscope_agent')
        def unavailable(*args,**kwargs):
            raise OSError('collector unavailable')
        fake.mark=unavailable
        sys.modules['leakscope_agent']=fake
        try:
            result=[]
            with adapter.erp_operation('example.model','write'):
                result.append('completed')
            self.assertEqual(result,['completed'])
            with self.assertRaises(ValueError):
                with adapter.erp_operation('example.model','write'):
                    raise ValueError('business failure')
        finally:
            if original is None:
                del sys.modules['leakscope_agent']
            else:
                sys.modules['leakscope_agent']=original
