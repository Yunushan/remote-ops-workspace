from remote_ops_workspace.features import load_feature_manifest


def test_feature_manifest_covers_requested_products() -> None:
    manifest = load_feature_manifest()
    products = set(manifest["products"])
    assert {"MobaXterm", "Remmina", "mRemoteNG", "Terminator", "Termius"}.issubset(products)
    feature_ids = {item["id"] for item in manifest["features"]}
    assert "protocol.ssh" in feature_ids
    assert "protocol.rdp" in feature_ids
    assert "terminal.splits" in feature_ids
    assert "security.vault" in feature_ids
    assert "web.pwa" in feature_ids
