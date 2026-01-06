from setuptools import setup, find_packages

with open("requirements.txt") as f:
    install_requires = f.read().strip().split("\n")

setup(
    name="raven_ai_agent",
    version="1.0.0",
    description="Raymond-Lucy AI Agent for ERPNext with Raven Integration",
    author="Your Company",
    author_email="your@email.com",
    packages=find_packages(),
    zip_safe=False,
    include_package_data=True,
    install_requires=install_requires,
)
