import setuptools

with open('README.md', 'r') as fh:
    long_description = fh.read()

setuptools.setup(
    name='LVZero',
    version='0.0.1',
    author='cosmicc',
    author_email='perezgemeinschaft@gmail.com',
    description='Telegram bot crawling lvz.de to find open LVZ+ articles.',
    long_description=long_description,
    long_description_content_type='text/markdown',
    packages=setuptools.find_packages(include=['src']),
    install_requires=[
        'python-telegram-bot',
        'scrapy',
    ],
    python_requires='>=3.6',
    licence='MIT',
    entry_points={
        'console_scripts': ['lvzero=src.main:main']
    }
)