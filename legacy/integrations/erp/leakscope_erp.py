"""Explicit ERP RPC/model/wizard boundaries. No argument or record inspection."""
import contextlib
import sys


@contextlib.contextmanager
def erp_operation(model, method, module=None, profile=False):
    manager = None
    try:
        import leakscope_agent
        manager = leakscope_agent.safe_operation(model+'.'+method, model=model,
                      method=method, module=module, profile=profile)
        manager.__enter__()
    except Exception:
        manager = None
    try:
        yield
    except BaseException:
        if manager is not None:
            manager.__exit__(*sys.exc_info())
        raise
    else:
        if manager is not None:
            manager.__exit__(None,None,None)
