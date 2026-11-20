import json
from contextlib import closing

from app.db import connect, init_db
from app.partners.registry import install_registrations
from tests.test_vertical_slice import create_case


def discover(client, **overrides):
    return client.get("/api/integrations/partners", params={
        "region": "Aachen", "category": "internet", "trigger": "tenant.move_in", **overrides}).json()


def test_internet_registration_is_durable_and_category_specific(client):
    init_db()
    partner, = discover(client)
    caps = client.get(partner["base_url"] + "/connector/capabilities").json()
    assert caps == partner["capabilities"]
    assert (caps["partner_id"], caps["kind"], caps["categories"]) == ("p_fibrenet", "offer", ["internet"])
    assert discover(client, region="Berlin") == discover(client, trigger="maintenance.case_created") == []
    heat, = discover(client, category="heating_repair", trigger="maintenance.case_created")
    heat_caps = client.get(heat["base_url"] + "/connector/capabilities").json()
    assert heat_caps == heat["capabilities"] | {"service_types": ["heating_repair"]}
    assert client.get("/partners/unknown/connector/capabilities").status_code == 404
    with closing(connect()) as conn, conn:
        conn.execute("UPDATE partners SET active=0 WHERE id='p_fibrenet'")
    init_db()
    assert discover(client) == []
    assert create_case(client)["partner_id"] == "p_heatfix"


def test_installation_preserves_preexisting_partner_endpoint_and_regions(client):
    with closing(connect()) as conn, conn:
        conn.execute("DELETE FROM partner_capabilities WHERE partner_id='p_heatfix'")
        conn.execute("UPDATE partners SET base_url='/custom/heatfix',regions='[\"Berlin\"]' WHERE id='p_heatfix'")
    init_db()
    cap = client.get("/partners/heatfix/connector/capabilities").json()
    assert cap["regions"] == ["Berlin"]
    partner, = discover(client, region="Berlin", category="heating_repair", trigger="maintenance.case_created")
    assert partner["base_url"] == "/custom/heatfix"


def test_new_simulated_category_only_requires_a_manifest(client, tmp_path):
    registration, = discover(client)
    registration["name"] = "Demo Solar"
    registration["base_url"] = "/partners/demo-solar"
    registration["capabilities"].update(partner_id="p_solar", categories=["solar"], regions=["Berlin"])
    (tmp_path / "solar.json").write_text(json.dumps(registration), encoding="utf-8")
    with closing(connect()) as conn, conn:
        install_registrations(conn, tmp_path)
        install_registrations(conn, tmp_path)
    assert discover(client, category="solar", region="Berlin") == [registration]
    assert client.get("/partners/demo-solar/connector/capabilities").json() == registration["capabilities"]
