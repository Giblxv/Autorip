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
    monkeypatch.setattr(net,'time',SimpleNamespace(monotonic=net.time.monotonic,sleep=lambda *_:None))
    assert net.discover_receivers()==[{'host':'192.168.0.215','port':9100,'name':'Host'}]
    assert calls==['cancelled']


def test_standalone_discovery_waits_for_network_without_loading_production_config(monkeypatch):
    from agent import print_agent
    import sys
    monkeypatch.setattr(sys, 'argv', ['PrintExpAgent', '--network-discovery'])
    monkeypatch.setattr(print_agent, 'advertise_receiver', lambda *_:nullcontext(False))
    def interrupt(*_):raise KeyboardInterrupt()
    monkeypatch.setattr(print_agent, 'time', SimpleNamespace(sleep=interrupt))
    monkeypatch.setattr(print_agent.Config, 'load', lambda *_:pytest.fail('must not load production config'))
    assert print_agent.main()==0


@pytest.mark.parametrize('action', ['update', 'remove', 'remove-during-resolve'])
def test_discovery_drops_stale_or_removed_addresses(monkeypatch, action):
    import zeroconf
    handler=[];address=['192.168.0.215'];resolve=[0]
    def lookup(*_,**__):
        resolve[0]+=1
        if action=='remove-during-resolve':
            handler[0](connection,net.SERVICE_TYPE,'Host',zeroconf.ServiceStateChange.Removed)
        value=address[0]
        return SimpleNamespace(properties={b'protocol':b'autorip-discovery-1'},port=9100,
            name='Host.'+net.SERVICE_TYPE,parsed_addresses=lambda *_:[value])
    connection=SimpleNamespace(get_service_info=lookup)
    monkeypatch.setattr(zeroconf,'Zeroconf',lambda **_:nullcontext(connection))
    class Browser:
        def __init__(self,network,service_type,handlers):
            handler.extend(handlers)
            handlers[0](network,service_type,'Host',zeroconf.ServiceStateChange.Added)
            if action=='update':
                address[0]='192.168.0.99'
                handlers[0](network,service_type,'Host',zeroconf.ServiceStateChange.Updated)
            elif action=='remove':handlers[0](network,service_type,'Host',zeroconf.ServiceStateChange.Removed)
        def cancel(self):pass
    monkeypatch.setattr(zeroconf,'ServiceBrowser',Browser)
    monkeypatch.setattr(net,'time',SimpleNamespace(monotonic=net.time.monotonic,sleep=lambda *_:None))
    result=net.discover_receivers()
    assert [x['host'] for x in result]==(['192.168.0.99'] if action=='update' else [])


@pytest.fixture
def fake_network(monkeypatch):
    import zeroconf
    events=[];instances=[]
    class Fake:
        def __init__(self):instances.append(self)
        def register_service(self,info,**kwargs):events.append(('register',info.parsed_addresses(),self))
        def unregister_service(self,info):events.append(('unregister',info.parsed_addresses(),self))
        def close(self):events.append(('close',self))
    monkeypatch.setattr(zeroconf,'Zeroconf',lambda **_:Fake())
    return events,instances


def test_dhcp_change_rebinds_sockets_and_unchanged_interfaces_do_not(fake_network,monkeypatch):
    events,instances=fake_network
    interfaces=[{'address':'192.168.0.215','interface':'LAN'}]
    monkeypatch.setattr(net,'local_ipv4s',lambda:list(interfaces))
    advertisement=net.ReceiverAdvertisement()
    try:
        advertisement.refresh();advertisement.refresh()
        assert len(instances)==1
        interfaces[0]={'address':'192.168.0.99','interface':'LAN'}
        advertisement.refresh()
        assert len(instances)==2
        assert [x[0] for x in events]==['register','unregister','close','register']
        assert events[-1][1]==['192.168.0.99']
    finally:advertisement.close()


def test_network_loss_and_recovery_retire_old_advertisement(fake_network,monkeypatch):
    events,instances=fake_network
    addresses=[{'address':'192.168.0.215'}]
    monkeypatch.setattr(net,'local_ipv4s',lambda:list(addresses))
    advertisement=net.ReceiverAdvertisement()
    try:
        advertisement.refresh();assert advertisement.active
        addresses.clear();advertisement.refresh();assert not advertisement.active
        assert events[-1][0]=='close'
        addresses.append({'address':'192.168.0.51'});advertisement.refresh()
        assert advertisement.active and events[-1][1]==['192.168.0.51']
    finally:advertisement.close()


def test_registration_failure_retries_without_interface_change(monkeypatch):
    import zeroconf
    calls=[]
    class Fake:
        def register_service(self,info,**kwargs):
            calls.append('register')
            if calls.count('register')==1:raise OSError('network unavailable')
        def unregister_service(self,*_):calls.append('unregister')
        def close(self):calls.append('close')
    monkeypatch.setattr(zeroconf,'Zeroconf',lambda **_:Fake())
    monkeypatch.setattr(net,'local_ipv4s',lambda:[{'address':'192.168.0.215'}])
    advertisement=net.ReceiverAdvertisement()
    try:
        advertisement.refresh();assert not advertisement.active
        advertisement.refresh();assert advertisement.active
        assert calls==['register','close','register']
    finally:advertisement.close()


def test_monitor_recovers_after_starting_without_ipv4_and_stops(monkeypatch):
    import zeroconf
    registered=threading.Event();closed=threading.Event();addresses=[]
    class Fake:
        def register_service(self,*_,**__):registered.set()
        def unregister_service(self,*_):pass
        def close(self):closed.set()
    monkeypatch.setattr(zeroconf,'Zeroconf',lambda **_:Fake())
    monkeypatch.setattr(net,'local_ipv4s',lambda:list(addresses))
    advertisement=net.ReceiverAdvertisement(refresh_seconds=.02)
    advertisement.start()
    try:
        assert not advertisement.active
        addresses.append({'address':'192.168.0.215'})
        assert registered.wait(3)
    finally:advertisement.close()
    assert closed.is_set() and not advertisement._thread.is_alive()
    advertisement.refresh()
    assert not advertisement.active


def test_interface_replacement_rebinds_even_with_same_ipv4(fake_network,monkeypatch):
    events,instances=fake_network
    interface=['Ethernet']
    monkeypatch.setattr(net,'local_ipv4s',lambda:[{'address':'192.168.0.215','interface':interface[0]}])
    advertisement=net.ReceiverAdvertisement()
    try:
        advertisement.refresh();interface[0]='Wi-Fi';advertisement.refresh()
        assert len(instances)==2
    finally:advertisement.close()


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
