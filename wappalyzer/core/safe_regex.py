"""Regex helpers for matching untrusted page content.

Patterns run against content a scanned site controls, so a crafted page
could make backtracking take forever (ReDoS). Every call here has a time
limit, and all calls made while scanning one URL share a total budget.
A pattern that runs out of time counts as "no match".
"""
import contextvars
import time

import regex

MULTILINE = regex.MULTILINE
error = regex.error

PER_CALL_TIMEOUT = 1.0
SCAN_BUDGET = 60.0

_deadline = contextvars.ContextVar('regex_deadline', default=None)


def start_budget(seconds=SCAN_BUDGET):
    return _deadline.set(time.monotonic() + seconds)


def end_budget(token):
    _deadline.reset(token)


def _timeout():
    deadline = _deadline.get()
    if deadline is None:
        return PER_CALL_TIMEOUT
    return min(PER_CALL_TIMEOUT, deadline - time.monotonic())


def search(pattern, string, flags=0):
    timeout = _timeout()
    if timeout <= 0:
        return None
    try:
        return regex.search(pattern, string, flags, timeout=timeout)
    except TimeoutError:
        return None


def findall(pattern, string, flags=0):
    timeout = _timeout()
    if timeout <= 0:
        return []
    try:
        return regex.findall(pattern, string, flags, timeout=timeout)
    except TimeoutError:
        return []


def finditer(pattern, string, flags=0):
    timeout = _timeout()
    if timeout <= 0:
        return []
    try:
        return list(regex.finditer(pattern, string, flags, timeout=timeout))
    except TimeoutError:
        return []
