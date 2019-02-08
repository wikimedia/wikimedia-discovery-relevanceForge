from setuptools import setup

requirements = [
    'elasticsearch>=5.0.0,<6.0.0',
    'pandas',
    'pyyaml',
]

test_requirements = [
    'pytest',
    'pytest_mock',
]

setup(
    name='relforge',
    version='0.0.1',
    author='Wikimedia Search Team',
    author_email='discovery@lists.wikimedia.org',
    description='Utility library for relforge_* packages',
    license='GPLv2',
    packages=['relforge'],
    include_package_data=True,
    data_files=['README.md', 'LICENSE'],
    install_requires=requirements,
    test_requires=test_requirements,
    extras_require={
        'test': requirements + test_requirements,
    },
    classifiers=[
        'Development Status :: 3 - Alpha',
        'Programming Language :: Python :: 2',
    ],
)
