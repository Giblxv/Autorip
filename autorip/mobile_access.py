"""Listener LAN opt-in para o celular, sem reiniciar o motor ou a fila."""
import ipaddress
import socket
import threading
from http.server import ThreadingHTTPServer

NETWORKS = tuple(ipaddress.ip_network(value) for value in
                 ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"))


def private_ipv4(value):
    try:
        address = ipaddress.IPv4Address(value)
    except (ipaddress.AddressValueError, TypeError) as exc:
        raise ValueError("Escolha um IPv4 privado deste computador.") from exc
    if not any(address in network for network in NETWORKS):
        raise ValueError("Escolha um IPv4 privado deste computador.")
    return str(address)


def local_interfaces():
    result = {}
    try:
        import ifaddr
        for adapter in ifaddr.get_adapters():
            for entry in adapter.ips:
                try:
                    host = private_ipv4(entry.ip)
                    result[host] = {"address": host, "interface": str(adapter.nice_name)}
                except ValueError:
                    pass
    except (ImportError, OSError):
        pass
    try:
        for value in socket.gethostbyname_ex(socket.gethostname())[2]:
            try:
                host = private_ipv4(value)
                result.setdefault(host, {"address": host, "interface": "Rede local"})
            except ValueError:
                pass
    except OSError:
        pass
    preferred = None
    try:
        # Consulta a rota do SO; não envia nenhum datagrama.
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            probe.connect(("192.0.2.1", 9))
            preferred = probe.getsockname()[0]
    except OSError:
        pass
    return sorted(result.values(), key=lambda item: (item["address"] != preferred,
                  int(ipaddress.IPv4Address(item["address"]))))


class MobileAccess:
    def __init__(self, primary, handler, discover=local_interfaces, server_factory=ThreadingHTTPServer):
        self.primary, self.handler = primary, handler
        self.discover, self.server_factory = discover, server_factory
        self.lock = threading.RLock()
        self.host = ""
        self.server = self.thread = None

    def interfaces(self):
        return self.discover()

    def enable(self, value):
        host = private_ipv4(value)
        if host not in {item["address"] for item in self.interfaces()}:
            raise ValueError("Esse IPv4 não pertence às interfaces locais. Atualize a lista.")
        with self.lock:
            if self.host == host:
                return self.url()
            port = self.primary.server_address[1]
            primary_host = self.primary.server_address[0]
            server = thread = None
            if primary_host not in (host, "0.0.0.0"):
                try:
                    server = self.server_factory((host, port), self.handler)
                    server.daemon_threads = True
                    thread = threading.Thread(target=server.serve_forever, daemon=True,
                                              name="autorip-mobile")
                    thread.start()
                except (OSError, RuntimeError) as exc:
                    if server is not None:
                        server.server_close()
                    raise ValueError("Não foi possível abrir esse IPv4/porta. Confira a interface e a porta em uso.") from exc
            previous, previous_thread = self.server, self.thread
            self.host, self.server, self.thread = host, server, thread
        self._close(previous, previous_thread)
        return self.url()

    def url(self):
        with self.lock:
            return f"http://{self.host}:{self.primary.server_address[1]}/" if self.host else None

    def allowed_hosts(self):
        with self.lock:
            return {self.host} if self.host else set()

    @staticmethod
    def _close(server, thread):
        if server is not None:
            server.shutdown()
            server.server_close()
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=2)

    def close(self):
        with self.lock:
            server, thread = self.server, self.thread
            self.host, self.server, self.thread = "", None, None
        self._close(server, thread)
