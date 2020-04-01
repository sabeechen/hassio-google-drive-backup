from setuptools import setup, find_packages
setup(
    name="hgdb",
    packages=find_packages(),
    package_data={
        'backup': ['static/*', 'static/*/*', 'static/*/*/*']
    }
)
