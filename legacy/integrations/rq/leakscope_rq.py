"""Explicit RQ lifecycle adapter. The caller supplies a function label, not a Job."""
def job_started(function_name):
    return _mark('job_started', function_name)


def job_finished(function_name):
    return _mark('job_finished', function_name)


def job_failed(function_name):
    return _mark('job_failed', function_name)


def worker_started():
    return _mark('worker_started', 'rq.worker')


def worker_exited():
    return _mark('worker_exited', 'rq.worker')


def _mark(event, function_name):
    try:
        import leakscope_agent
        return leakscope_agent.mark(event, {'operation': function_name, 'worker_type': 'rq'})
    except (ImportError, RuntimeError, ValueError, OSError):
        return False


def job_operation(function_name, profile=False):
    """Use around the existing job executor; never pass a Job or its arguments."""
    import leakscope_agent
    return leakscope_agent.safe_operation(function_name, module='rq', profile=profile)
