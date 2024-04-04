from setuptools import setup, find_packages
import package

setup(
    name=package.NAME,
    version=package.VERSION,
    description=package.DESCRIPTION,
    author=package.AUTHOR,
    license=package.LICENSE,
    packages=find_packages(),
)
