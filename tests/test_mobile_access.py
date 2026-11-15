from http.server import BaseHTTPRequestHandler
from types import SimpleNamespace

import pytest

from autorip.mobile_access import MobileAccess, private_ipv4


@pytest.mark.parametrize("host", ["127.0.0.1", "0.0.0.0", "8.8.8.8", "::1", "example.com", "169.254.1.1", None])
def test_acesso_celular_rejeita_ips_fora_da_lan(host):
    with pytest.raises(ValueError, match="IPv4 privado"):
        private_ipv4(host)


class FakeServer:
    def __init__(self, address, handler):
        self.server_address = address
        self.closed = False
        self.stopped = False

    def serve_forever(self):
        pass

    def shutdown(self):
        self.stopped = True

    def server_close(self):
        self.closed = True


def manager(primary="127.0.0.1"):
    return MobileAccess(SimpleNamespace(server_address=(primary, 8766)), BaseHTTPRequestHandler,
                        discover=lambda: [{"address": "192.168.1.20", "interface": "Wi-Fi"},
                                          {"address": "10.0.0.20", "interface": "Ethernet"}],
                        server_factory=FakeServer)


def test_ativacao_mesma_porta_ip_explicito_troca_e_liberacao():
    access = manager()
    try:
        assert access.url() is None
        assert access.enable("192.168.1.20") == "http://192.168.1.20:8766/"
        previous = access.server
        assert previous.server_address == ("192.168.1.20", 8766)
        assert previous.daemon_threads
        access.enable("192.168.1.20")
        assert access.server is previous
        access.enable("10.0.0.20")
        assert previous.stopped and previous.closed
        assert access.allowed_hosts() == {"10.0.0.20"}
    finally:
        current = access.server
        access.close()
    assert current.closed and current.stopped and access.url() is None


def test_falha_de_bind_preserva_acesso_anterior_e_ip_alheio_rejeitado():
    access = manager()
    access.enable("192.168.1.20")
    previous = access.server
    def fail(*args):
        raise OSError("porta em uso")
    access.server_factory = fail
    try:
        with pytest.raises(ValueError, match="IPv4/porta"):
            access.enable("10.0.0.20")
        with pytest.raises(ValueError, match="interfaces locais"):
            access.enable("192.168.1.99")
        assert access.server is previous and not previous.closed
    finally:
        access.close()


@pytest.mark.parametrize("primary", ["192.168.1.20", "0.0.0.0"])
def test_listener_existente_e_reutilizado(primary):
    access = manager(primary)
    assert access.enable("192.168.1.20") == "http://192.168.1.20:8766/"
    assert access.server is None
    access.close()
