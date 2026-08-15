"""The offline guard has to bite, not just exist.

A guard nobody exercises is indistinguishable from a guard that silently stopped
working, so these tests drive it directly: an outbound attempt must raise, and
loopback must stay usable (several tests bind local sockets).
"""

import socket

import pytest

from .conftest import LOCAL_HOSTNAMES, OutboundNetworkAttempt, _is_local_address


@pytest.mark.parametrize(
    "address",
    [
        ("example.com", 443),  # unresolved name — the lookup is itself outbound
        ("93.184.216.34", 80),  # public IPv4
        ("2606:2800:220:1:248:1893:25c8:1946", 443, 0, 0),  # public IPv6
    ],
)
def test_public_addresses_are_outbound(address):
    assert not _is_local_address(address)


@pytest.mark.parametrize(
    "address",
    [
        ("127.0.0.1", 8080),
        ("::1", 8080, 0, 0),
        ("0.0.0.0", 0),
        ("localhost", 5000),
        "/tmp/some.sock",  # AF_UNIX path — local by construction
        (),
    ],
)
def test_local_addresses_are_local(address):
    assert _is_local_address(address)


def test_every_declared_loopback_alias_counts_as_local():
    for name in LOCAL_HOSTNAMES:
        assert _is_local_address((name, 80)), name


# The three tests below deliberately trip the guard, so each takes the fixture
# and clears the record it just created — otherwise the teardown assertion (the
# half that stops a swallowed attempt from passing unnoticed) fails the test
# for doing exactly what it set out to do.


def test_outbound_connect_is_refused(_no_outbound_network):
    """The guard is active in this very test — reaching out must raise."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    with pytest.raises(OutboundNetworkAttempt) as excinfo:
        sock.connect(("example.com", 80))
    assert "example.com" in str(excinfo.value)
    sock.close()
    assert _no_outbound_network, "the attempt should have been recorded"
    _no_outbound_network.clear()


def test_outbound_dns_lookup_is_refused(_no_outbound_network):
    with pytest.raises(OutboundNetworkAttempt) as excinfo:
        socket.getaddrinfo("example.com", 80)
    assert "example.com" in str(excinfo.value)
    assert _no_outbound_network, "the attempt should have been recorded"
    _no_outbound_network.clear()


def test_loopback_still_works():
    """The guard must not break local sockets — other tests rely on them."""
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        client.connect(server.getsockname())  # must NOT raise
    finally:
        client.close()
        server.close()


def test_guard_is_not_swallowable_by_a_bare_except(_no_outbound_network):
    """Why OutboundNetworkAttempt derives from BaseException.

    Adapters degrade instead of raising and the engine collects command
    failures, so a catchable error could be absorbed on the way out — leaving a
    green test that quietly hit the network.
    """
    assert issubclass(OutboundNetworkAttempt, BaseException)
    assert not issubclass(OutboundNetworkAttempt, Exception)

    with pytest.raises(OutboundNetworkAttempt):
        try:
            socket.getaddrinfo("example.com", 80)
        except Exception:  # noqa: BLE001 — the point of the test
            pytest.fail("a bare `except Exception` swallowed the guard")
    _no_outbound_network.clear()
