from setuptools import setup

requirements = [
    'requests',
]

test_requirements = [
]

setup(
    name='relforge_sanity_check',
    version='0.0.1',
    author='Wikimedia Search Team',
    author_email='discovery@lists.wikimedia.org',
    description='Sanity checker for newly deployed rankers',
    license='GPLv2',
    packages=['relforge_sanity_check'],
    entry_points={
        'console_scripts': [
            'sanity_check = relforge_sanity_check.__main__:main',
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
