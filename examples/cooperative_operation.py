from __future__ import print_function
import leakscope_agent

leakscope_agent.initialize()
leakscope_agent.snapshot('before')
with leakscope_agent.operation('generate_invoices', model='account.invoice', method='generate'):
    # Execute the application's existing operation here; never include arguments.
    pass
leakscope_agent.snapshot('after')
leakscope_agent.shutdown()
