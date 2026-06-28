import pytest
from unittest.mock import Mock
from src.throttle import check_circuit_breaker, CircuitBreakerTripped

def test_circuit_breaker_healthy():
    resp = Mock()
    resp.status_code = 200
    resp.headers = {"Content-Type": "application/json"}
    resp.text = '{"users": []}'
    # Should not raise
    check_circuit_breaker(resp)

def test_circuit_breaker_rate_limit():
    resp = Mock()
    resp.status_code = 429
    resp.headers = {"Content-Type": "application/json"}
    resp.text = "{}"
    with pytest.raises(CircuitBreakerTripped, match="HTTP 429 — Rate limited"):
        check_circuit_breaker(resp)

def test_circuit_breaker_html_challenge():
    resp = Mock()
    resp.status_code = 200
    resp.headers = {"Content-Type": "text/html"}
    resp.text = "<html>Challenge Required</html>"
    with pytest.raises(CircuitBreakerTripped, match="Received HTML"):
        check_circuit_breaker(resp)

def test_circuit_breaker_json_error():
    resp = Mock()
    resp.status_code = 200
    resp.headers = {"Content-Type": "application/json"}
    resp.text = '{"message": "checkpoint_url"}'
    with pytest.raises(CircuitBreakerTripped, match="Response body contains 'checkpoint_url'"):
        check_circuit_breaker(resp)
