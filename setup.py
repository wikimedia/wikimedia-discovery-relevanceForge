import os
from setuptools import find_packages, setup

requirements = [
    'jsonpath-rw',
    'matplotlib',
    'numpy',
    'pyyaml',
    'scipy',
    'requests',
    'termcolor',
    'tensorflow',
]

test_requirements = [
    'pytest',
]

setup(
    name='relforge',
    version='0.0.1',
    author='Wikimedia Search Team',
    author_email='discovery@lists.wikimedia.org',
    description='Evaluation of search result sets from CirrusSearch',
    license='GPLv2',
    entry_points={
        'console_scripts': [
            'engineScore.py = relforge.cli.engineScore:main',
            'jsondiff.py = relforge.cli.jsondiff:main',
            'relcomp.py = relforge.cli.relcomp:main',
            'relevancyRunner.py = relforge.cli.relevancyRunner:main',
            'sanityCheck.py = relforge.cli.sanityCheck.py:main',
        ]
    },
    packages=find_packages(),
    include_package_data=True,
    data_files=['README.md', 'LICENSE'],
    install_requires=requirements,
    test_requires=test_requirements,
    extras_require={
        'test': test_requirements,
    },
    classifiers=[
        'Development Status :: 3 - Alpha',
        'Programming Language :: Python :: 2',
    ],
)
