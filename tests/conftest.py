"""Make "the suite never touches the network" enforced rather than assumed.

walkthru's design already points this way: the core is pure, every vendor sits
behind an injected port, and each adapter test supplies a fake seam. So no test
*should* reach out. The gap this file closes is that nothing *stopped* one —
and one of the ports costs money. ``walkthru.adapters.synth.mixing_synth`` is
ElevenLabs TTS; today every test injects ``synth_fn``, but that is a convention
a future test can forget, and forgetting it spends real money rather than
failing.

:func:`_no_outbound_network` is autouse, so a test that starts reaching out
fails on the spot, naming the host it tried to reach. A test that genuinely
must talk to the real world marks itself ``live`` (nothing does today).
"""

import ipaddress
import socket

import pytest

#: Hostnames that mean "this machine" without a DNS round-trip.
LOCAL_HOSTNAMES = frozenset(
    {"", "localhost", "localhost.localdomain", "ip6-localhost", "ip6-loopback"}
)


class OutboundNetworkAttempt(BaseException):
    """An offline test tried to talk to a non-local host.

    Derived from :class:`BaseException` on purpose. The engine collects command
    failures rather than propagating them, and adapters degrade instead of
    raising, so anything catchable could be swallowed on the way out and the
    attempt would vanish — leaving a green test that quietly hit the network.
    """


def _is_local_address(address) -> bool:
    """True when ``address`` is loopback, unspecified, or not an IP endpoint.

    Non-tuple addresses (``AF_UNIX`` paths) are local by construction. A bare
    hostname that is not a known loopback alias counts as outbound: resolving
    it is itself a network round-trip.
    """
    if not isinstance(address, (tuple, list)) or not address:
        return True
    host = address[0]
    if host is None:
        return True
    host = str(host)
    if host in LOCAL_HOSTNAMES:
        return True
    try:
        ip = ipaddress.ip_address(host.split("%", 1)[0])
    except ValueError:
        return False  # an unresolved name — looking it up is already outbound
    return ip.is_loopback or ip.is_unspecified


@pytest.fixture(autouse=True)
def _no_outbound_network(request, monkeypatch):
    """Fail the test if it tries to reach a non-local host.

    Both halves matter. Refusing the connection stops the spend; asserting the
    *record* at teardown stops a degrade-on-error path from hiding that the
    attempt happened at all.
    """
    if request.node.get_closest_marker("live") is not None:
        yield []
        return

    attempts: list[str] = []
    real_connect = socket.socket.connect
    real_connect_ex = socket.socket.connect_ex
    real_getaddrinfo = socket.getaddrinfo

    def refuse(what: str, target: str):
        attempts.append(f"{what} {target}")
        raise OutboundNetworkAttempt(
            f"Offline test attempted {what} to {target!r}. walkthru's suite is "
            "hermetic: every vendor sits behind an injected port, so pass a "
            "fake seam (see tests/fakes.py) instead of the real adapter. Mark "
            "the test `live` only if it really must reach the real world — and "
            "note that the synth port costs money per call."
        )

    def connect(self, address, *args, **kwargs):
        if not _is_local_address(address):
            refuse("connect", str(address))
        return real_connect(self, address, *args, **kwargs)

    def connect_ex(self, address, *args, **kwargs):
        if not _is_local_address(address):
            refuse("connect", str(address))
        return real_connect_ex(self, address, *args, **kwargs)

    def getaddrinfo(host, port, *args, **kwargs):
        if not _is_local_address((host, port)):
            refuse("DNS lookup", str(host))
        return real_getaddrinfo(host, port, *args, **kwargs)

    monkeypatch.setattr(socket.socket, "connect", connect)
    monkeypatch.setattr(socket.socket, "connect_ex", connect_ex)
    monkeypatch.setattr(socket, "getaddrinfo", getaddrinfo)

    yield attempts

    if attempts:
        pytest.fail(
            "Offline test performed outbound network I/O: "
            + "; ".join(sorted(set(attempts)))
        )
