import json
import os
from pathlib import Path
import subprocess
import sys

import pytest
import yaml

from render_manifest import render

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def commands(tmp_path):
    binary = tmp_path / "bin"
    binary.mkdir()
    log = tmp_path / "commands.jsonl"
    executable = f"#!{sys.executable}\n" + '''import json, os, sys
name = os.path.basename(sys.argv[0])
args = sys.argv[1:]
data = sys.stdin.read() if "-f" in args and "-" in args else ""
with open(os.environ["COMMAND_LOG"], "a") as stream:
    stream.write(json.dumps({"name": name, "args": args, "stdin": data}) + "\\n")
if name == "kubectl" and args[:2] == ["create", "secret"]:
    print("apiVersion: v1\\nkind: Secret\\nmetadata: {name: sdt-manager-timestamps-secret}")
if name == "kubectl" and args[:2] == ["rollout", "status"]:
    sys.exit(int(os.environ.get("ROLLOUT_RESULT", "0")))
'''
    for name in ["docker", "kubectl", "k3s", "sudo"]:
        path = binary / name
        path.write_text(executable)
        path.chmod(0o755)
    env_file = tmp_path / ".env"
    env_file.write_text("MQTT_FAILURE_HOST=test\nMQTT_FAILURE_PORT=1883\n")
    env = dict(os.environ, PATH=f"{binary}:{os.environ['PATH']}",
               COMMAND_LOG=str(log), ENV_FILE=str(env_file))
    return env, log, tmp_path


def run_script(name, commands, *args):
    env, log, cwd = commands
    return subprocess.run(["bash", str(ROOT / name), *args], env=env, cwd=cwd,
                          capture_output=True, text=True)


def test_rendered_manifest_has_isolated_resources_and_persistent_storage():
    docs = list(yaml.safe_load_all(render("test-1", 30112)))
    assert all(d["metadata"]["name"].startswith("sdt-manager-timestamps-") for d in docs)
    deployment = next(d for d in docs if d["kind"] == "Deployment")
    pod = deployment["spec"]["template"]["spec"]
    assert deployment["spec"]["strategy"]["type"] == "Recreate"
    assert pod["containers"][0]["image"] == "docker.io/library/sdt-manager-timestamps:test-1"
    assert pod["volumes"][0]["persistentVolumeClaim"]["claimName"] == "sdt-manager-timestamps-data-pvc"
    assert deployment["spec"]["template"]["metadata"]["annotations"]
    service = next(d for d in docs if d["kind"] == "Service")
    assert service["spec"]["ports"][0]["nodePort"] == 30112
    assert not any(d["kind"] == "Secret" for d in docs)
    with pytest.raises(ValueError):
        render("bad:tag")
    with pytest.raises(ValueError):
        render(node_port=80)


def test_build_uses_script_directory_and_matching_tag(commands):
    result = run_script("build.sh", commands, "experiment-1")
    assert result.returncode == 0, result.stderr
    calls = [json.loads(line) for line in commands[1].read_text().splitlines()]
    build = calls[0]
    assert build["args"] == ["build", "--tag", "sdt-manager-timestamps:experiment-1", str(ROOT)]
    assert any(c["name"] == "docker" and c["args"][0] == "save" for c in calls)
    assert any("import" in c["args"] for c in calls)
    assert not any("rm" in c["args"] for c in calls)


def test_deploy_dry_run_never_calls_kubectl(commands):
    result = run_script("deploy.sh", commands, "experiment-2", "--dry-run")
    assert result.returncode == 0, result.stderr
    assert "sdt-manager-timestamps:experiment-2" in result.stdout
    assert not commands[1].exists()


def test_deploy_applies_expected_image_and_propagates_rollout_failure(commands):
    commands[0]["ROLLOUT_RESULT"] = "17"
    result = run_script("deploy.sh", commands, "experiment-3")
    assert result.returncode == 17
    calls = [json.loads(line) for line in commands[1].read_text().splitlines()]
    assert any("sdt-manager-timestamps:experiment-3" in c["stdin"] for c in calls)
    assert "Timestamp API:" not in result.stdout


@pytest.mark.parametrize("purge", [False, True])
def test_destroy_targets_only_timestamp_manager_and_preserves_data_by_default(commands, purge):
    result = run_script("destroy.sh", commands, *(["--purge-data"] if purge else []))
    assert result.returncode == 0, result.stderr
    calls = [json.loads(line) for line in commands[1].read_text().splitlines()]
    targets = [arg for call in calls for arg in call["args"] if "/" in arg]
    assert targets
    assert all(arg.split("/", 1)[1].startswith("sdt-manager-timestamps-") for arg in targets)
    assert any(arg.startswith("pvc/") for arg in targets) == purge
