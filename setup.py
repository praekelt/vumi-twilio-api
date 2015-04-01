from setuptools import setup, find_packages

setup(
    name="vxtwinio",
    version="0.0.1a",
    url="https://github.com/praekelt/vumi-twilio-api",
    license="BSD",
    description="Provides a REST API to Vumi that emulates the Twilio API",
    long_description=open("README.rst", "r").read(),
    author="Praekelt Foundation",
    author_email="dev@praekeltfoundation.org",
    packages=find_packages(),
    scripts=[],
    install_requires=[
        'vumi',
        'klein',
        'treq',
    ],
    classifiers=[
        'Development Status :: 4 - Beta',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: BSD License',
        'Operating System :: POSIX',
        'Programming Language :: Python',
        'Programming Language :: Python :: 2.6',
        'Programming Language :: Python :: 2.7',
        'Topic :: Software Development :: Libraries :: Python Modules',
        'Topic :: System :: Networking',
    ],
)
