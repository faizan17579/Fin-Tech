import subprocess
import sys
import os


def test_frontend_build_present():
    # Sanity check for frontend structure
    assert os.path.exists('frontend/package.json')
    assert os.path.exists('frontend/src')


