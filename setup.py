import os
from setuptools import find_packages, setup


d = os.path.dirname(os.path.realpath(__file__))
with open(os.path.join(d, "README.md"), "r") as f:
    long_description = f.read()


setup(
    name="iafisher-precommit",
    version="0.1",
    description="Manage git pre-commit hooks",
    long_description=long_description,
    long_description_content_type="text/markdown",
    license="MIT",
    author="Ian Fisher",
    author_email="iafisher@protonmail.com",
    entry_points={"console_scripts": ["precommit = precommitlib.main:main"]},
    packages=find_packages(exclude=["tests"]),
    package_data={"": ["precommit.py.template"]},
    project_urls={"Source": "https://github.com/iafisher/precommit"},
)
