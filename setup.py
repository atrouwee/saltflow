"""Only a build hook; everything else is in pyproject.toml. It puts examples/saltpos into the package as
saltflow/example, so `saltflow demo` works from a wheel and from `pip install git+...`, not only from a clone."""
import os
import shutil

from setuptools import setup
from setuptools.command.build_py import build_py

EXAMPLE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "examples", "saltpos")


class build_with_example(build_py):
    def run(self):
        super().run()
        if os.path.isdir(EXAMPLE):
            dst = os.path.join(self.build_lib, "saltflow", "example")
            shutil.rmtree(dst, ignore_errors=True)
            shutil.copytree(EXAMPLE, dst, ignore=shutil.ignore_patterns("runs.json", "__pycache__", ".gitignore"))


setup(cmdclass={"build_py": build_with_example})
