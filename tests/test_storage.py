from tms_vision import storage


def test_connect_creates_both_tables(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "test.duckdb")

    conn = storage._connect()
    try:
        table_names = {
            row[0]
            for row in conn.execute(
                "SELECT table_name FROM information_schema.tables"
            ).fetchall()
        }
    finally:
        conn.close()

    assert {"analyses", "analysis_frames"} <= table_names


def test_connect_is_idempotent(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "test.duckdb")

    conn1 = storage._connect()
    conn1.close()
    conn2 = storage._connect()
    conn2.close()
