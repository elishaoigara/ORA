#!/usr/bin/env python3
"""Trigger the authenticated companion tick and report secret-safe diagnostics.

Uses only the Python standard library so the GitHub runner needs no extra setup.
Does not follow redirects or retry a POST: either could leak credentials or
duplicate an alert after an ambiguous timeout.
"""
import json
import os
import sys
import urllib.error
import urllib.request
from urllib.parse import urlsplit

TIMEOUT_SECONDS = 360
MAX_RESPONSE_BYTES = 65536


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def configuration():
    base = os.getenv('ORA_BACKEND_URL', '').strip().rstrip('/')
    token = os.getenv('ORA_CRON_TOKEN', '')
    if not base or not token:
        raise ValueError('Set ORA_BACKEND_URL and ORA_CRON_TOKEN repository secrets to enable dispatch.')
    try:
        parsed = urlsplit(base)
        valid = (parsed.scheme == 'https' and parsed.hostname and not parsed.username
                 and not parsed.password and parsed.port in (None, 443)
                 and not parsed.path and not parsed.query and not parsed.fragment)
    except ValueError:
        valid = False
    if not valid:
        raise ValueError('ORA_BACKEND_URL must be the HTTPS backend origin, without a path, query, credentials, or fragment.')
    if len(token) < 32 or token != token.strip():
        raise ValueError('ORA_CRON_TOKEN must be at least 32 characters, without surrounding whitespace, and match Render exactly.')
    return base + '/api/companion/tick', token


def safe_summary(payload):
    """Only emit known scheduler fields; never echo an arbitrary upstream body."""
    if not isinstance(payload, dict):
        return None
    summary = {}
    for key in ('processed', 'weather_failures'):
        if type(payload.get(key)) is int and payload[key] >= 0:
            summary[key] = payload[key]
    if type(payload.get('busy')) is bool:
        summary['busy'] = payload['busy']
    if type(payload.get('ok')) is bool:
        summary['ok'] = payload['ok']
    stages = payload.get('failed_stages')
    if isinstance(stages, list):
        summary['failed_stages'] = [s for s in stages if isinstance(s, str) and len(s) <= 40][:10]
    errors = payload.get('error_types')
    if isinstance(errors, dict):
        summary['error_types'] = {
            k: v for k, v in errors.items()
            if isinstance(k, str) and len(k) <= 40 and isinstance(v, str) and len(v) <= 80
        }
    # Do not echo upstream 'detail' or arbitrary fields: they may contain secrets.
    return summary


def read_json(response):
    try:
        raw = response.read(MAX_RESPONSE_BYTES + 1)
        if len(raw) > MAX_RESPONSE_BYTES:
            return None
        return json.loads(raw.decode('utf-8'))
    except (ValueError, UnicodeError, OSError):
        return None


def main():
    try:
        url, token = configuration()
    except ValueError as exc:
        print(f'::error::{exc}')
        return 1

    request = urllib.request.Request(url, data=b'', method='POST', headers={
        'Authorization': 'Bearer ' + token,
        'Accept': 'application/json',
        'User-Agent': 'ORA-companion-scheduler/1',
    })
    opener = urllib.request.build_opener(NoRedirect)
    try:
        with opener.open(request, timeout=TIMEOUT_SECONDS) as response:
            status = response.status
            payload = read_json(response)
    except urllib.error.HTTPError as exc:
        status = exc.code
        payload = read_json(exc)
        exc.close()
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        reason = getattr(exc, 'reason', exc)
        print(f'::error::Companion backend request failed ({type(reason).__name__}). '
              'Check ORA_BACKEND_URL, DNS/TLS, and Render availability. The POST was not retried.')
        return 3

    summary = safe_summary(payload)
    if 200 <= status < 300 and summary is not None:
        if summary.get('busy') is True:
            print('Companion tick skipped: another tick holds the backend lease.')
            return 0
        if summary.get('ok') is not False and 'processed' in summary:
            if summary.get('weather_failures', 0) > 0:
                print('::error::Companion tick completed with weather failures. Check the weather provider and backend logs.')
                print(json.dumps(summary, sort_keys=True))
                return 2
            print('Companion tick completed: ' + json.dumps(summary, sort_keys=True))
            return 0

    guidance = {
        401: 'ORA_CRON_TOKEN does not match the Render backend. Set the same secret in both places.',
        403: 'The backend rejected the scheduler credentials. Check ORA_CRON_TOKEN in Actions and Render.',
        404: 'The companion endpoint was not found. Use the backend origin and deploy the current backend.',
        405: 'The endpoint rejected POST. Check ORA_BACKEND_URL and the deployed backend release.',
        500: 'The backend raised an unhandled error. Deploy the scheduler diagnostics fix and inspect Render logs.',
        502: 'The backend gateway failed. Check Render deployment and availability.',
        503: 'The backend or one scheduler stage is unavailable. Inspect the safe stage diagnostics and Render logs.',
        504: 'The backend gateway timed out. The tick may still be running; it was not retried.',
    }.get(status, 'Unexpected backend response. Check the deployment and scheduler configuration.')
    print(f'::error::Companion tick failed with HTTP {status}. {guidance}')
    if summary:
        print(json.dumps(summary, sort_keys=True))
    return 2


if __name__ == '__main__':
    sys.exit(main())
