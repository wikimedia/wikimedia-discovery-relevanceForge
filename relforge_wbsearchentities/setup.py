from setuptools import setup

requirements = [
    'relforge',
    'elasticsearch>=5.0.0,<6.0.0',
    'hyperopt==0.2.3',
    'jsonpath-rw',
    'numba',
    'numpy',
    'pandas',
    'protobuf<4.0.0',
    'pyyaml',
    'requests',
    'tensorflow<2.0.0',
    'tqdm',
    # only for reporting
    'bokeh',
    'jupyter',
    'matplotlib',
]

test_requirements = [
    'pytest',
    'pytest_mock',
]

setup(
    name='relforge_wbsearchentities',
    version='0.0.1',
    author='Wikimedia Search Team',
    author_email='discovery@lists.wikimedia.org',
    description='Numerical optimization over lucene explains.',
    license='GPLv2',
    packages=['relforge_wbsearchentities'],
    entry_points={
        'console_scripts': [
            'relforge_wbsearchentities = relforge_wbsearchentities.__main__:main',
        ]
    },
    include_package_data=True,
    data_files=['README.md', 'LICENSE'],
    install_requires=requirements,
    test_requires=test_requirements,
    extras_require={
        'test': requirements + test_requirements,
    },
    classifiers=[
        'Development Status :: 3 - Alpha',
        'Programming Language :: Python :: 3',
    ],
)
