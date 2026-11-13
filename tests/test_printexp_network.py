from contextlib import nullcontext
import json
import socket
import threading
from types import SimpleNamespace

import pytest
from autorip import printexp_network as net
from autorip.config import Settings
from test_server import panel, request


@pytest.mark.parametrize('host', ['127.0.0.1', '0.0.0.0', '169.254.1.2', '8.8.8.8', '::1', 'localhost', '192.168.1.2:9100', '', None, True])
def test_only_explicit_private_lan_ipv4_is_accepted(host):
    with pytest.raises(ValueError):
        net.validate_endpoint(host, 9100)


@pytest.mark.parametrize('port', [0, 65536, True, 9100.0, '9100', None])
def test_port_requires_a_bounded_integer(port):
    with pytest.raises(ValueError):
        net.validate_endpoint('192.168.0.215', port)


def test_lists_all_private_adapter_addresses_without_guessing_a_receiver(monkeypatch):
    import ifaddr
    adapters = [SimpleNamespace(nice_name='LAN', ips=[SimpleNamespace(ip=x) for x in
                ['192.168.0.215', '127.0.0.1', '169.254.2.3', ('::1', 0, 0)]]),
                SimpleNamespace(nice_name='Printer', ips=[SimpleNamespace(ip='192.168.127.11')]),
                SimpleNamespace(nice_name='VPN', ips=[SimpleNamespace(ip='10.5.1.8')])]
    monkeypatch.setattr(ifaddr, 'get_adapters', lambda: adapters)
    assert [x['address'] for x in net.local_ipv4s()] == ['10.5.1.8', '192.168.0.215', '192.168.127.11']


def test_tcp_probe_closes_connection_without_sending_print_bytes(monkeypatch):
    # Only this test maps the already-validated example to an owned loopback
    # server. Production validation continues to require a private LAN address.
    validate = net.validate_endpoint
    def local_endpoint(host, port):
        validate(host, port)
        return '127.0.0.1', port
    monkeypatch.setattr(net, 'validate_endpoint', local_endpoint)
    received = []
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0)); listener.listen(); listener.settimeout(3)
        def accept():
            connection, _ = listener.accept()
            with connection:
                connection.settimeout(3)
                received.append(connection.recv(16))
        thread = threading.Thread(target=accept); thread.start()
        result = net.check_connection('192.168.0.215', listener.getsockname()[1])
        thread.join(timeout=4)
    assert result['reachable'] and received == [b'']


def test_refused_probe_preserves_destination_and_reports_failure(monkeypatch):
    def refused(*_, **__):raise ConnectionRefusedError()
    monkeypatch.setattr(socket, 'create_connection', refused)
    result = net.check_connection('192.168.0.215', 9100)
    assert result['reachable'] is False and result['host'] == '192.168.0.215'


def test_advertisement_identity_and_private_ipv4_are_required():
    info = SimpleNamespace(properties={b'protocol': b'unknown'}, port=9100,
                           name='Host.'+net.SERVICE_TYPE,
                           parsed_addresses=lambda *_: ['192.168.0.215', '8.8.8.8', '127.0.0.1'])
    assert net.receivers_from_info(info) == []
    info.properties={b'protocol': b'autorip-discovery-1'}
    assert net.receivers_from_info(info) == [{'host': '192.168.0.215', 'port': 9100, 'name': 'Host'}]


def test_announcer_advertises_multiple_interfaces_and_releases_resources(monkeypatch):
    import zeroconf
    calls=[]
    class Fake:
        def register_service(self, info, **kwargs):calls.append(('register', info))
        def unregister_service(self, info):calls.append(('unregister', info))
        def close(self):calls.append(('close',))
    monkeypatch.setattr(zeroconf, 'Zeroconf', lambda **_: Fake())
    monkeypatch.setattr(net, 'local_ipv4s', lambda: [{'address':'192.168.0.215'}, {'address':'192.168.127.11'}])
    with pytest.raises(RuntimeError):
        with net.advertise_receiver(9200) as active:
            assert active is True
            raise RuntimeError('caller failure')
    assert [x[0] for x in calls] == ['register', 'unregister', 'close']
    info=calls[0][1]
    assert info.port==9200 and set(info.parsed_addresses())=={'192.168.0.215','192.168.127.11'}


def test_advertisement_failure_does_not_stop_print_agent(monkeypatch):
    import zeroconf
    closed=[]
    class Fake:
        def register_service(self,*_,**__):raise ValueError('multicast unavailable')
        def close(self):closed.append(True)
    monkeypatch.setattr(zeroconf, 'Zeroconf', lambda **_: Fake())
    monkeypatch.setattr(net, 'local_ipv4s', lambda: [{'address':'192.168.0.215'}])
    with net.advertise_receiver() as active:assert active is False
    assert closed == [True]


def test_discovery_deduplicates_service_updates_and_cancels_browser(monkeypatch):
    import zeroconf
    calls=[]
    info=SimpleNamespace(properties={b'protocol':b'autorip-discovery-1'}, port=9100,
                         name='Host.'+net.SERVICE_TYPE,parsed_addresses=lambda *_:['192.168.0.215'])
    connection=SimpleNamespace(get_service_info=lambda *_,**__:info)
    monkeypatch.setattr(zeroconf,'Zeroconf',lambda **_:nullcontext(connection))
    class Browser:
        def __init__(self, network, service_type, handlers):
            for _ in range(2):handlers[0](network,service_type,'Host',zeroconf.ServiceStateChange.Added)
        def cancel(self):calls.append('cancelled')
    monkeypatch.setattr(zeroconf,'ServiceBrowser',Browser)
    monkeypatch.setattr(net.time,'sleep',lambda *_:None)
    assert net.discover_receivers()==[{'host':'192.168.0.215','port':9100,'name':'Host'}]
    assert calls==['cancelled']


def test_standalone_discovery_needs_no_production_config_and_reports_failure(monkeypatch):
    from agent import print_agent
    import sys
    monkeypatch.setattr(sys, 'argv', ['PrintExpAgent', '--network-discovery'])
    monkeypatch.setattr(print_agent, 'advertise_receiver', lambda *_:nullcontext(False))
    assert print_agent.main()==1


def test_endpoint_settings_are_optional_and_persisted(app):
    assert Settings().validate().printexp_host == ''
    app.apply_settings({'printexp_host':'192.168.0.215','printexp_port':9200})
    settings=Settings.load(app.cfg_path, base=app.home)
    assert settings.printexp_host=='192.168.0.215' and settings.printexp_port==9200


@pytest.mark.parametrize('path,method', [('/api/printexp/network','GET'),('/api/printexp/discover','POST'),('/api/printexp/check','POST')])
def test_network_endpoints_require_authentication(panel,path,method):
    assert request(panel,path,method,data=b'{}' if method=='POST' else None)[0]==401


def test_network_api_validation_and_single_flight(panel,app,monkeypatch):
    app.tokens.add('network-test');headers={'X-Token':'network-test'}
    called=[];monkeypatch.setattr(net,'discover_receivers',lambda:called.append(True) or [])
    assert request(panel,'/api/printexp/check','POST',b'{"host":"8.8.8.8","port":9100}',headers)[0]==400
    assert request(panel,'/api/printexp/discover','POST',b'{}',headers)[0]==200
    assert called==[True]
    app.printexp_network_lock.acquire()
    try:assert request(panel,'/api/printexp/discover','POST',b'{}',headers)[0]==429
    finally:app.printexp_network_lock.release()
    assert called==[True]
