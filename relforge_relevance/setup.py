from setuptools import setup

requirements = [
    'relforge',
    'matplotlib',
    'numpy',
]

test_requirements = [
]

setup(
    name='relforge_relevance',
    version='0.0.1',
    author='Wikimedia Search Team',
    author_email='discovery@lists.wikimedia.org',
    description='Evaluation of search result sets from CirrusSearch',
    license='GPLv2',
    packages=['relforge_relevance'],
    entry_points={
        'console_scripts': [
            'jsondiff.py = relforge_relevance.jsondiff:main',
            'relcomp.py = relforge_relevance.relcomp:main',
            'relevancyRunner.py = relforge_relevance.relevancyRunner:main',
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
        'Programming Language :: Python :: 2',
    ],
)
