"""Local filtering proxy for the scanning browser.

Chromium sends every request (including redirect hops, WebSockets and the
extension's own fetches) through this proxy, which checks the destination
against the current scan's network policy. For direct connections it
resolves the name itself and connects to the very address it checked, so a
DNS answer that changes in between (DNS rebinding) cannot reach a blocked
address. When the system has an upstream proxy configured, requests are
forwarded to it; the upstream proxy then does the name resolution.
"""
import asyncio
import base64
import socket
import urllib.request
from urllib.parse import unquote, urlsplit


CONNECT_TIMEOUT = 30
MAX_HEADER_BYTES = 64 * 1024
HOP_BY_HOP = {'connection', 'keep-alive', 'proxy-connection', 'proxy-authorization', 'te', 'trailer', 'upgrade'}

FORBIDDEN = b'HTTP/1.1 403 Forbidden\r\nContent-Length: 0\r\nConnection: close\r\n\r\n'
BAD_GATEWAY = b'HTTP/1.1 502 Bad Gateway\r\nContent-Length: 0\r\nConnection: close\r\n\r\n'


class Blocked(Exception):
    pass


def _split_host_port(value, default_port):
    host, sep, port = value.rpartition(':')
    if not sep or not port.isdigit() or (host.startswith('[') != host.endswith(']')):
        return value.strip('[]'), default_port
    return host.strip('[]'), int(port)


class FilteringProxy:
    def __init__(self, get_policy, blocked_hosts=()):
        self.get_policy = get_policy
        self.blocked_hosts = {host.lower() for host in blocked_hosts}
        self.proxies = urllib.request.getproxies()
        self.server = None
        self.port = None
        self.connections = set()

    async def start(self):
        self.server = await asyncio.start_server(self._handle, '127.0.0.1', 0, limit=MAX_HEADER_BYTES)
        self.port = self.server.sockets[0].getsockname()[1]
        return self.port

    async def close(self):
        if self.server:
            self.server.close()
        for writer in list(self.connections):
            writer.close()
        self.connections.clear()

    def _upstream(self, host, tunnel):
        if urllib.request.proxy_bypass(host):
            return None
        proxy = self.proxies.get('https' if tunnel else 'http') or self.proxies.get('http')
        if not proxy:
            return None
        parsed = urlsplit(proxy if '://' in proxy else 'http://' + proxy)
        auth = None
        if parsed.username:
            credentials = f'{unquote(parsed.username)}:{unquote(parsed.password or "")}'
            auth = 'Basic ' + base64.b64encode(credentials.encode()).decode()
        return parsed.hostname, parsed.port or 8080, auth

    async def _addresses(self, host, port):
        policy = self.get_policy()
        infos = await asyncio.get_running_loop().getaddrinfo(host, port, type=socket.SOCK_STREAM)
        addresses = list(dict.fromkeys(info[4][0] for info in infos))
        if policy and not all(policy.allows_peer(a) for a in addresses):
            raise Blocked(host)
        return addresses

    async def _open(self, host, port, tunnel):
        if host.lower().rstrip('.') in self.blocked_hosts:
            raise Blocked(host)

        upstream = self._upstream(host, tunnel)
        if upstream:
            policy = self.get_policy()
            if policy and not await policy.allows_async(f'http://{host}/'):
                raise Blocked(host)
            proxy_host, proxy_port, auth = upstream
            reader, writer = await asyncio.wait_for(asyncio.open_connection(proxy_host, proxy_port), CONNECT_TIMEOUT)
            if tunnel:
                target = f'[{host}]:{port}' if ':' in host else f'{host}:{port}'
                request = f'CONNECT {target} HTTP/1.1\r\nHost: {target}\r\n'
                if auth:
                    request += f'Proxy-Authorization: {auth}\r\n'
                writer.write((request + '\r\n').encode('latin-1'))
                await writer.drain()
                head = await asyncio.wait_for(reader.readuntil(b'\r\n\r\n'), CONNECT_TIMEOUT)
                if head.split(b' ', 2)[1:2] != [b'200']:
                    writer.close()
                    raise ConnectionError('upstream proxy refused CONNECT')
            return reader, writer, auth, True

        last_error = None
        for address in await self._addresses(host, port):
            try:
                reader, writer = await asyncio.wait_for(asyncio.open_connection(address, port), CONNECT_TIMEOUT)
                return reader, writer, None, False
            except (OSError, asyncio.TimeoutError) as e:
                last_error = e
        raise ConnectionError(str(last_error))

    async def _handle(self, client_reader, client_writer):
        self.connections.add(client_writer)
        remote_writer = None
        try:
            try:
                head = await asyncio.wait_for(client_reader.readuntil(b'\r\n\r\n'), CONNECT_TIMEOUT)
            except (asyncio.IncompleteReadError, asyncio.LimitOverrunError, asyncio.TimeoutError, ConnectionError):
                return

            request_line, *header_lines = head.decode('latin-1').split('\r\n')
            method, target, version = request_line.split(' ', 2)
            headers = [line for line in header_lines if line]

            try:
                if method.upper() == 'CONNECT':
                    host, port = _split_host_port(target, 443)
                    remote_reader, remote_writer, _, _ = await self._open(host, port, tunnel=True)
                    client_writer.write(b'HTTP/1.1 200 Connection Established\r\n\r\n')
                else:
                    url = urlsplit(target)
                    if url.scheme != 'http' or not url.hostname:
                        raise Blocked(target)
                    remote_reader, remote_writer, auth, via_upstream = await self._open(url.hostname, url.port or 80, tunnel=False)
                    path = url.path or '/'
                    if url.query:
                        path += '?' + url.query
                    forwarded = [f'{method} {target if via_upstream else path} {version}']
                    forwarded += [h for h in headers if h.split(':', 1)[0].strip().lower() not in HOP_BY_HOP]
                    if auth:
                        forwarded.append(f'Proxy-Authorization: {auth}')
                    # one request per connection, so a reused connection can
                    # never carry a request for another host past the check
                    forwarded.append('Connection: close')
                    remote_writer.write(('\r\n'.join(forwarded) + '\r\n\r\n').encode('latin-1'))
            except Blocked:
                client_writer.write(FORBIDDEN)
                return
            except (OSError, ConnectionError, asyncio.TimeoutError, asyncio.IncompleteReadError, socket.gaierror):
                client_writer.write(BAD_GATEWAY)
                return

            await self._relay(client_reader, client_writer, remote_reader, remote_writer)
        except Exception:
            pass
        finally:
            self.connections.discard(client_writer)
            for writer in (remote_writer, client_writer):
                if writer:
                    writer.close()

    async def _relay(self, client_reader, client_writer, remote_reader, remote_writer):
        async def pipe(reader, writer):
            try:
                while data := await reader.read(65536):
                    writer.write(data)
                    await writer.drain()
            except (OSError, ConnectionError):
                pass

        tasks = [
            asyncio.create_task(pipe(client_reader, remote_writer)),
            asyncio.create_task(pipe(remote_reader, client_writer)),
        ]
        # either side closing ends the exchange (requests carry Connection: close)
        _, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in pending:
            task.cancel()
