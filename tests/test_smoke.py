import importlib

PACKAGE = "smart_meter_peak_prediction"


def test_package_imports() -> None:
    module = importlib.import_module(PACKAGE)
    assert module.__version__
