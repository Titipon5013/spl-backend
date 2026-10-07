def test_create_entry_record_uploads_image_and_persists_record(
    client, db_session, monkeypatch
):
    class FakeS3CloudFront:
        def __init__(self, *args, **kwargs):
            pass

        def upload_file(self, file, file_name, prefix, content_type=None):
            assert file.read() == b"fake-image"
            assert file_name == "plate.jpg"
            assert prefix == "entry-records/"
            assert content_type == "image/jpeg"
            return "https://cdn.example/entry-records/plate.jpg"

    monkeypatch.setattr(
        "services.entry_record_service.S3CloudFront", FakeS3CloudFront
    )

    response = client.post(
        "/api/entry-records",
        data={"plate_number": "TEST123"},
        files={"file": ("plate.jpg", b"fake-image", "image/jpeg")},
    )

    assert response.status_code == 201, response.text
    record = response.json()
    assert record["id"] > 0
    assert record["plate_number"] == "TEST123"
    assert record["plate_image_url"] == "https://cdn.example/entry-records/plate.jpg"
    assert record["timestamp"]
