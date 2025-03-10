from setuptools import setup, find_packages

setup(
    name="STservo_sdk",
    version="0.1",
    packages=find_packages(),
    install_requires=[
        'pyserial>=3.4',
    ],
    description="Waveshare ST Serial Bus Servo Control Library",
    author="Waveshare",
    author_email="",
    url="https://www.waveshare.com/wiki/ST_Bus_Servo"
) 