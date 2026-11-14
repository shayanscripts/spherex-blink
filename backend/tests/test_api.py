from fastapi.testclient import TestClient

from backend import main


def client_for(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "DATA_DIR", tmp_path / "cache")
    main.load.cache_clear()
    main.metadata.cache_clear()
    return TestClient(main.app)


def test_upload_render_inspect_and_cached_restore(fixture_fits, tmp_path, monkeypatch):
    client = client_for(tmp_path, monkeypatch)
    response = client.post("/observations", files={"file": ("test.fits", fixture_fits.read_bytes())})
    assert response.status_code == 200, response.text
    obs = response.json()
    assert len(obs["id"]) == 64
    assert client.get(f"/observations/{obs['id']}").json()["id"] == obs["id"]
    assert client.get(f"/observations/{obs['id']}/image").headers["content-type"] == "image/png"
    pixel = client.get(f"/observations/{obs['id']}/pixel?x=2&y=2").json()
    assert pixel["brightness"] == 14
    assert client.get(f"/observations/{obs['id']}/locate?ra=180&dec=45").json() == dict(x=2, y=2)
    assert client.get(f"/observations/{obs['id']}/locate?ra=400&dec=45").status_code == 422
    assert client.get(f"/observations/{obs['id']}/pixel?x=7&y=2").status_code == 422
    assert client.get(f"/observations/{obs['id']}/image?low=10&high=5").status_code == 422


def test_bad_file_and_path_rejected(tmp_path, monkeypatch):
    client = client_for(tmp_path, monkeypatch)
    assert client.post("/observations", files={"file": ("test.png", b"notfits")}).status_code == 415
    assert client.post("/observations", files={"file": ("test.fits", b"notfits")}).status_code == 422
    assert client.get("/observations/not-an-id").status_code == 404


def test_missing_default_has_no_generated_data(tmp_path, monkeypatch):
    client = client_for(tmp_path, monkeypatch)
    monkeypatch.setenv("SPHEREX_FITS_PATH", str(tmp_path / "absent.fits"))
    result = client.get("/observations/default").json()
    assert result["observation"] is None
