import os
from typing import List


def resource_paths(*args: str) -> List[str]:
    """Absolute paths to test data. Usage: resource_pths('f1.shp', 'f2.shp').
    :param args: files or not
    :return:
    """
    return [
        os.path.abspath(os.path.join(os.path.dirname(__file__), "test_data", f))
        for f in args
    ]
