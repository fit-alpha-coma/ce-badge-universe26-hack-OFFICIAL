"""Compatibility metadata for Python environments with older build frontends."""

from setuptools import find_packages, setup


setup(
    name="copilot-pager",
    version="0.1.0",
    description=(
        "Encrypted BLE bridge from GitHub Copilot permission hooks "
        "to the Universe badge"
    ),
    python_requires=">=3.11",
    package_dir={"": "src"},
    packages=find_packages("src"),
    install_requires=["bleak>=0.22,<4", "cryptography>=42,<47"],
    entry_points={"console_scripts": ["copilot-pager=copilot_pager_host.cli:main"]},
)

