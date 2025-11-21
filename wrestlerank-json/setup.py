from setuptools import setup, find_packages

setup(
    name="wrestlerank",
    version="0.1.0",
    packages=find_packages(),
    install_requires=[
        # CLI interface
        "click",
        # Web scraping
        "requests",
        "beautifulsoup4",
        # Use simpler dependencies for now
        # We'll add the more complex ones later with pre-built wheels
    ],
    entry_points={
        "console_scripts": [
            "wrestlerank=wrestlerank.cli:main",
        ],
    },
    python_requires=">=3.8",
    author="Gator Bacon",
    author_email="your.email@example.com",
    description="A wrestling ranking system with advanced algorithms",
    keywords="wrestling, rankings, sports",
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Sports Enthusiasts",
        "Programming Language :: Python :: 3",
        "Topic :: Sports :: Wrestling",
    ],
)