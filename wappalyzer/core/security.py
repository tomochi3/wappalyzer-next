import asyncio
import ipaddress
import re
import socket
from urllib.parse import urlparse

# C0/C1 control characters (keeps nothing that a terminal could interpret)
CONTROL_CHARS = re.compile(r'[\x00-\x1f\x7f-\x9f]')
CSV_FORMULA_PREFIXES = ('=', '+', '-', '@', '\t', '\r')


def strip_control_chars(value):
    """Remove characters that could inject terminal escape sequences."""
    return CONTROL_CHARS.sub('', str(value))


def csv_safe(value):
    """Prevent spreadsheet formula injection in CSV cells."""
    value = '' if value is None else str(value)
    if value.startswith(CSV_FORMULA_PREFIXES):
        return "'" + value
    return value


def _is_public_ip(address):
    try:
        ip = ipaddress.ip_address(address.split('%', 1)[0])
    except ValueError:
        return False
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    return ip.is_global and not ip.is_multicast


def _literal_ip(hostname):
    try:
        return ipaddress.ip_address(hostname.strip('[]'))
    except ValueError:
        return None


def _addresses_are_public(infos):
    addresses = {info[4][0] for info in infos}
    return bool(addresses) and all(_is_public_ip(address) for address in addresses)


def host_is_public(hostname):
    """True if the hostname only resolves to globally routable addresses.

    Returns None when the name cannot be resolved locally (e.g. behind a
    proxy that does the resolution), so callers can decide what to do.
    """
    if not hostname:
        return False
    if _literal_ip(hostname) is not None:
        return _is_public_ip(hostname.strip('[]'))
    if hostname.lower().rstrip('.') == 'localhost' or hostname.lower().endswith('.localhost'):
        return False
    try:
        infos = socket.getaddrinfo(hostname, None, proto=socket.IPPROTO_TCP)
    except (socket.gaierror, UnicodeError, OSError):
        return None
    return _addresses_are_public(infos)


async def host_is_public_async(hostname):
    if not hostname:
        return False
    if _literal_ip(hostname) is not None or hostname.lower().rstrip('.') == 'localhost' or hostname.lower().endswith('.localhost'):
        return host_is_public(hostname)
    try:
        infos = await asyncio.get_running_loop().getaddrinfo(hostname, None, proto=socket.IPPROTO_TCP)
    except (socket.gaierror, UnicodeError, OSError):
        return None
    return _addresses_are_public(infos)


class NetworkPolicy:
    """Decides which URLs may be requested while scanning a target.

    When the scan target is a public site, anything it makes us request
    (scripts, redirects, robots.txt, page sub-resources) must also be public,
    so a hostile page cannot reach the scanning machine's internal network.
    When the user deliberately scans an internal target, no such restriction
    applies.
    """

    def __init__(self, target_url):
        self.target_host = (urlparse(target_url).hostname or '').lower()
        self.target_is_public = host_is_public(self.target_host) is not False
        self._cache = {}

    def _decide(self, hostname, public):
        if not self.target_is_public:
            return True
        # unresolvable locally: the request can only succeed through a proxy,
        # which resolves the name itself; let it through
        return public is not False

    def allows(self, url):
        parsed = urlparse(url)
        if parsed.scheme not in ('http', 'https'):
            return False
        hostname = (parsed.hostname or '').lower()
        if hostname not in self._cache:
            self._cache[hostname] = self._decide(hostname, host_is_public(hostname))
        return self._cache[hostname]

    async def allows_async(self, url):
        parsed = urlparse(url)
        if parsed.scheme not in ('http', 'https'):
            return False
        hostname = (parsed.hostname or '').lower()
        if hostname not in self._cache:
            self._cache[hostname] = self._decide(hostname, await host_is_public_async(hostname))
        return self._cache[hostname]
