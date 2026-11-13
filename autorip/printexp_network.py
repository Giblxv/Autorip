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
    services = {}
    lock = threading.Lock()
    deadline = time.monotonic() + 1.8
    def changed(zeroconf, service_type, name, state_change):
        if state_change == ServiceStateChange.Removed:
            with lock:
                services.pop(name, None)
            return
        if time.monotonic() >= deadline:
            return
        with lock:
            if name not in services and len(services) >= 32:
                return
            # A distinct entry invalidates an older, still resolving update.
            entry = {'receivers': []}
            services[name] = entry
        info = zeroconf.get_service_info(service_type, name, timeout=150)
        receivers = receivers_from_info(info)
        with lock:
            if services.get(name) is entry:
                entry['receivers'] = receivers
    with Zeroconf(ip_version=IPVersion.V4Only) as network:
        browser = ServiceBrowser(network, SERVICE_TYPE, handlers=[changed])
        try:
            time.sleep(max(0, deadline - time.monotonic()))
        finally:
            browser.cancel()
    with lock:
        results = {(item['host'], item['port']): item
                   for entry in services.values() for item in entry['receivers']}
        return sorted(results.values(), key=lambda item: (int(ipaddress.IPv4Address(item['host'])), item['port']))[:32]


class ReceiverAdvertisement:
    """Rebind mDNS when DHCP/interfaces change; retry transient network failures."""

    def __init__(self, port=9100, log=None, refresh_seconds=5.0):
        if type(port) is not int or not 1 <= port <= 65535:
            raise ValueError('A porta precisa ser um inteiro entre 1 e 65535.')
        if refresh_seconds <= 0:
            raise ValueError('O intervalo de atualização precisa ser positivo.')
        self.port, self.log = port, log
        self.refresh_seconds = refresh_seconds
        self.active = False
        self._network = self._info = self._fingerprint = None
        self._last_error = None
        self._stop = threading.Event()
        self._thread = None
        self._name = (re.sub(r'[^A-Za-z0-9-]', '-', socket.gethostname())[:40].strip('-') or 'PrintExp')

    def _warning(self, error):
        message = str(error)
        if self.log and message != self._last_error:
            self.log.warning('Descoberta IPv4 aguardando rede; nova tentativa automática: %s', message)
        self._last_error = message

    def _close_network(self):
        network, info = self._network, self._info
        self._network = self._info = None
        self.active = False
        if network is None:
            return
        try:
            network.unregister_service(info)
        except Exception as exc:
            self._warning(exc)
        finally:
            try:
                network.close()
            except Exception as exc:
                self._warning(exc)

    def refresh(self):
        from zeroconf import IPVersion, ServiceInfo, Zeroconf
        if self._stop.is_set():
            return
        try:
            interfaces = tuple(sorted({(lan_ipv4(x['address']), x.get('interface', '')) for x in local_ipv4s()}))
            if self.active and interfaces == self._fingerprint:
                self._last_error = None
                return
            # Recreate sockets too: an announcement update alone can leave
            # Zeroconf listening on an address removed by DHCP.
            self._close_network()
            if not interfaces:
                raise OSError('Nenhum IPv4 privado disponível neste computador.')
            addresses = sorted({address for address, _ in interfaces})
            info = ServiceInfo(SERVICE_TYPE, f'AutoRIP-{self._name}.{SERVICE_TYPE}',
                               addresses=[socket.inet_aton(x) for x in addresses], port=self.port,
                               properties={b'protocol': b'autorip-discovery-1'}, server=self._name + '.local.')
            network = Zeroconf(ip_version=IPVersion.V4Only)
            try:
                network.register_service(info, allow_name_change=True)
            except BaseException:
                network.close()
                raise
            self._network, self._info, self._fingerprint = network, info, interfaces
            self.active = True
            self._last_error = None
            if self.log:
                self.log.info('Descoberta IPv4 atualizada: %s (porta %s).', ', '.join(addresses), self.port)
        except Exception as exc:
            self._warning(exc)

    def start(self):
        if self._thread is not None or self._stop.is_set():
            raise RuntimeError('Este anúncio de rede já foi iniciado ou encerrado.')
        self.refresh()
        def monitor():
            try:
                while not self._stop.wait(self.refresh_seconds):
                    self.refresh()
            finally:
                self._close_network()
        self._thread = threading.Thread(target=monitor, name='autorip-ipv4', daemon=True)
        self._thread.start()

    def close(self):
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=3)
        else:
            self._close_network()


@contextmanager
def advertise_receiver(port=9100, log=None):
    """Advertise the candidate endpoint; discovery never transfers print data."""
    advertisement = ReceiverAdvertisement(port, log)
    try:
        advertisement.start()
        yield advertisement.active
    finally:
        advertisement.close()
