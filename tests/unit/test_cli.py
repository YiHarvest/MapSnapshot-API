from main import parse_args


def test_parse_args_enables_reload() -> None:
    args = parse_args(["--reload"])

    assert args.reload is True


def test_parse_args_disables_reload_by_default() -> None:
    args = parse_args([])

    assert args.reload is False
