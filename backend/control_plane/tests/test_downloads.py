"""Keep old release URLs stable and serve the current fixed artifact safely."""

import pytest


@pytest.mark.parametrize("version", ["0.2.0", "0.3.0", "0.3.1", "0.3.2"])
def test_current_and_previous_worker_downloads(client, context, tmp_path, version):
    context.config.WORKER_RELEASE_DIR = tmp_path
    name = f"lattice-{version}-py3-none-any.whl"
    (tmp_path / name).write_bytes(b"fixture-release")
    response = client.get("/downloads/" + name)
    assert response.status_code == 200
    assert response.content == b"fixture-release"
    assert response.headers["cache-control"] == "no-cache"


def test_release_route_rejects_symlink_and_unknown_files(client, context, tmp_path):
    context.config.WORKER_RELEASE_DIR = tmp_path
    target = tmp_path / "private"
    target.write_bytes(b"private")
    (tmp_path / "lattice-0.3.2-py3-none-any.whl").symlink_to(target)
    assert (
        client.get("/downloads/lattice-0.3.2-py3-none-any.whl").status_code == 404
    )
    assert client.get("/downloads/private").status_code == 404
