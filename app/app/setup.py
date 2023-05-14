from setuptools import setup, find_packages

with open('/usr/app/requirements.txt') as f:
    requirements = f.read().splitlines()

setup(
    name='freshdoc',
    version='0.1.0',
    packages=find_packages(),
    install_requires=requirements,
)
