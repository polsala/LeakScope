"""Wrap explicit operation boundaries; never inspect parameters or record values."""
import contextlib


@contextlib.contextmanager
def erp_operation(model, method):
    try:
        import leakscope_agent
    except ImportError:
        yield
        return
    metadata = {'operation': model + '.' + method, 'model': model, 'method': method}
    def diagnostic(name):
        try:
            leakscope_agent.mark(name, metadata)
        except Exception:
            # Profiling/validation failures must never change a business operation.
            return False
        return True
    diagnostic('operation_started')
    failed = False
    try:
        yield
    except BaseException:
        failed = True
        raise
    finally:
        diagnostic('operation_failed' if failed else 'operation_finished')
