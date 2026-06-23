from scribe.cli import main


def test_cli_writes_output(tmp_path, capsys):
    src = tmp_path / "a.txt"
    src.write_text("hello cli")
    rc = main([str(src)])
    assert rc == 0
    assert "hello cli" in capsys.readouterr().out


def test_cli_to_file(tmp_path):
    src = tmp_path / "a.txt"
    src.write_text("hello file")
    out = tmp_path / "a.md"
    assert main([str(src), "-o", str(out)]) == 0
    assert "hello file" in out.read_text()


def test_cli_bad_input_returns_1(tmp_path, capsys):
    src = tmp_path / "x.pdf"
    src.write_bytes(b"not a pdf")
    rc = main([str(src)])
    assert rc == 1
    assert "error" in capsys.readouterr().err
