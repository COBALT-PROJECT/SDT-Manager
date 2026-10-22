import importlib.util
import json
from pathlib import Path
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from performance_http import original_requests
from sdt_manager_core import SDT_ManagerCore
from sdt_manager_interface import SDT_Manager_Interface


@pytest.fixture
def core(tmp_path, monkeypatch):
    for key, value in {
        "MQTT_FAILURE_REPORTING_ENABLED": "false", "MQTT_FAILURE_HOST": "test",
        "MQTT_FAILURE_PORT": "1883", "CREDENTIAL_DB_PATH": str(tmp_path / "creds.db"),
        "PERFORMANCE_LOG_PATH": str(tmp_path / "events.jsonl"),
    }.items():
        monkeypatch.setenv(key, value)
    instance = SDT_ManagerCore()
    yield instance
    instance.stop()


def test_current_routes_validation_and_disabled_watchtower_are_preserved(core):
    source = Path(__file__).resolve().parents[2] / "SDT-Manager" / "sdt_manager_interface.py"
    spec = importlib.util.spec_from_file_location("baseline_interface", source)
    baseline = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(baseline)
    original = baseline.SDT_Manager_Interface(core).app
    updated = core.sdt_manager.app
    paths = lambda app: {(r.path, tuple(sorted(r.methods))) for r in app.routes}
    assert paths(original) <= paths(updated)
    assert not hasattr(core, "watchtower_manager")
    with TestClient(original) as old, TestClient(updated) as new:
        for path in ["/health", "/ready"]:
            assert old.get(path).json() == new.get(path).json()
        for payload_type in ["BOMS", "OSCAL", "ARM", "MUD"]:
            path = f"/api/SDTM/adapt?payload_type={payload_type}"
            a, b = old.post(path, json={}), new.post(path, json={})
            assert a.status_code == b.status_code == 400
            assert a.json() == b.json()
        assert new.get("/api/SDTM/performance?category=invalid").status_code == 400
        assert new.get("/api/SDTM/performance/missing").status_code == 404
        assert new.get("/api/SDTM/performance/export").headers["content-type"].startswith("text/csv")
        assert "api_endpoint" in new.get("/api/SDTM/performance/summary").json()
    assert any(r["status"] == "failed" and r["category"] == "api_endpoint"
               for r in core.perf_tracker.get_all_records())


def test_authentication_token_template_and_ids_delivery_are_all_timed(core, monkeypatch):
    calls = []
    def post(url, **kwargs):
        calls.append(url)
        body = ({"client": {"client_id": "client", "client_secret": "secret-value"}}
                if url.endswith("/wallet/digital-twins") else {"access_token": "token-value"})
        return Mock(status_code=200, json=lambda: body, text="ok")
    monkeypatch.setattr(original_requests, "post", post)
    monkeypatch.setattr(original_requests, "get", Mock(return_value=Mock(
        status_code=200, json=lambda: {"status": "issued"})))
    monkeypatch.setattr(core.sdt_manager, "_get_service_cluster_ip", lambda name: "127.0.0.1")
    monkeypatch.setattr(core.sdt_manager, "_get_sdt_service_name", lambda: "sdt-service")
    monkeypatch.setattr(core.sdt_manager, "_get_ids_sdt_service_name", lambda: "ids-service")
    core.sdt_manager._run_auth_flow_async("twin-1", "ids-1")
    assert core.credential_store.get_access_token("twin-1") == "token-value"
    assert core.credential_store.get_access_token("ids-1") == "token-value"
    assert any(url.endswith("/api/SDT/upload-template") for url in calls)
    assert any(url.endswith("/api/IDSconnector/SDT/configauth") for url in calls)
    records = core.perf_tracker.get_records_by_sdt_id("twin-1")
    categories = {r["category"] for r in records}
    assert {"auth_token_acquisition", "token_distribution", "template_delivery",
            "credential_store", "http_client"} <= categories
    assert "secret-value" not in json.dumps(records)
    assert "token-value" not in json.dumps(records)
    assert all(r["status"] == "completed" for r in records)


def test_failed_token_delivery_is_timed_and_still_reports_mqtt(core, monkeypatch):
    monkeypatch.setattr(core.sdt_manager, "_get_service_cluster_ip", lambda name: "127.0.0.1")
    monkeypatch.setattr(core.sdt_manager, "_get_sdt_service_name", lambda: "sdt-service")
    monkeypatch.setattr(original_requests, "post", Mock(return_value=Mock(status_code=503, text="down")))
    core.sdt_manager._distribute_token("twin-1", "token-value", None)
    records = core.perf_tracker.get_all_records()
    assert any(r["label"].endswith("._send_token_to_service") and r["status"] == "failed"
               for r in records)
    assert any(r["label"] == "MQTTFailureReporter.report_failure" for r in records)
