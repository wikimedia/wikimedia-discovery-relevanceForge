from setuptools import setup

requirements = [
    'relforge',
]

test_requirements = [
]

setup(
    name='relforge_engine_score',
    version='0.0.1',
    author='Wikimedia Search Team',
    author_email='discovery@lists.wikimedia.org',
    description='Score result sets from CirrusSearch',
    license='GPLv2',
    packages=['relforge_engine_score'],
    entry_points={
        'console_scripts': [
            'relforge_engine_score = relforge_engine_score.__main__:main',
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
