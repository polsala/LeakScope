"""Call configure_after_fork from a uWSGI postfork hook, or after lazy app load."""
def configure_after_fork():
    try:
        import leakscope_agent
        leakscope_agent.after_fork()
        leakscope_agent.initialize()
        leakscope_agent.mark('worker_started', {'worker_type': 'uwsgi'})
        return True
    except (ImportError, RuntimeError, OSError):
        return False


def request_operation(handler_name, profile=False):
    """Explicit request handler label, never a URL, request body or user ID."""
    import leakscope_agent
    return leakscope_agent.safe_operation(handler_name, module='uwsgi', profile=profile)
