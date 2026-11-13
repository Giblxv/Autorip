"""IPv4 configuration and opt-in LAN discovery; never transfers print data."""
from contextlib import contextmanager
import ipaddress
import re
import socket
import threading
import time

SERVICE_TYPE = '_autorip-pe._tcp.local.'
LAN_NETWORKS = tuple(ipaddress.ip_network(n) for n in ('10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16'))


def lan_ipv4(value):
    if not isinstance(value, str):
        raise ValueError('Informe um IPv4 da rede local.')
    try:
        address = ipaddress.IPv4Address(value)
    except ipaddress.AddressValueError as exc:
        raise ValueError('Informe um IPv4 válido da rede local.') from exc
    if not any(address in network for network in LAN_NETWORKS):
        raise ValueError('Use o IPv4 privado da rede local do computador PrintExp.')
    return str(address)


def validate_endpoint(host, port):
    host = lan_ipv4(host)
    if type(port) is not int or not 1 <= port <= 65535:
        raise ValueError('A porta precisa ser um inteiro entre 1 e 65535.')
    return host, port


def local_ipv4s():
    import ifaddr
    result = {}
    for adapter in ifaddr.get_adapters():
        for entry in adapter.ips:
            try:
                address = lan_ipv4(entry.ip)
            except ValueError:
                continue
            result.setdefault(address, {'address': address, 'interface': str(adapter.nice_name)})
    return sorted(result.values(), key=lambda item: int(ipaddress.IPv4Address(item['address'])))


def check_connection(host, port):
    host, port = validate_endpoint(host, port)
    try:
        with socket.create_connection((host, port), timeout=1.0):
            pass
        return {'host': host, 'port': port, 'reachable': True,
                'message': 'Conexão TCP estabelecida. O envio e a aceitação do PRT ainda precisam de validação.'}
    except OSError:
        return {'host': host, 'port': port, 'reachable': False,
                'message': 'Sem conexão TCP. Confira o IP, o receptor e o firewall da rede local.'}


def receivers_from_info(info):
    """Advertisements are hints, not authenticated printer identities."""
    from zeroconf import IPVersion
    if not info or info.properties.get(b'protocol') != b'autorip-discovery-1':
        return []
    if type(info.port) is not int or not 1 <= info.port <= 65535:
        return []
    name = info.name.removesuffix('.' + SERVICE_TYPE)[:120]
    result = []
    for value in info.parsed_addresses(IPVersion.V4Only)[:16]:
        try:
            host = lan_ipv4(value)
        except ValueError:
            continue
        result.append({'name': name, 'host': host, 'port': info.port})
    return result


def discover_receivers():
    from zeroconf import IPVersion, ServiceBrowser, ServiceStateChange, Zeroconf
    results = {}
    lock = threading.Lock()
    deadline = time.monotonic() + 1.8
    def changed(zeroconf, service_type, name, state_change):
        if state_change == ServiceStateChange.Removed or time.monotonic() >= deadline:
            return
        info = zeroconf.get_service_info(service_type, name, timeout=150)
        with lock:
            for item in receivers_from_info(info):
                if len(results) < 32:
                    results[(item['host'], item['port'])] = item
    with Zeroconf(ip_version=IPVersion.V4Only) as network:
        browser = ServiceBrowser(network, SERVICE_TYPE, handlers=[changed])
        try:
            time.sleep(max(0, deadline - time.monotonic()))
        finally:
            browser.cancel()
    with lock:
        return sorted(results.values(), key=lambda item: (int(ipaddress.IPv4Address(item['host'])), item['port']))


@contextmanager
def advertise_receiver(port=9100, log=None):
    """Advertise this agent's candidate PrintExp endpoint, not a print server."""
    from zeroconf import IPVersion, ServiceInfo, Zeroconf
    network = None
    info = None
    registered = False
    try:
        addresses = local_ipv4s()
        if not addresses:
            raise OSError('Nenhum IPv4 privado encontrado neste computador.')
        validate_endpoint(addresses[0]['address'], port)
        hostname = re.sub(r'[^A-Za-z0-9-]', '-', socket.gethostname())[:40] or 'PrintExp'
        info = ServiceInfo(SERVICE_TYPE, f'AutoRIP-{hostname}.{SERVICE_TYPE}',
                           addresses=[socket.inet_aton(x['address']) for x in addresses], port=port,
                           properties={b'protocol': b'autorip-discovery-1'}, server=hostname + '.local.')
        network = Zeroconf(ip_version=IPVersion.V4Only)
        network.register_service(info, allow_name_change=True)
        registered = True
        if log:
            log.info('Descoberta IPv4 local ativa para o agente PrintExp (porta candidata %s).', port)
    except Exception as exc:
        if log:
            log.warning('Descoberta IPv4 indisponível; configuração manual continua disponível: %s', exc)
    try:
        yield registered
    finally:
        if network is not None:
            try:
                if registered:
                    network.unregister_service(info)
            finally:
                network.close()
