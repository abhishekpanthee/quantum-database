from setuptools import setup, find_packages
import os

# Check if we're building on a CI system (for wheel building)
CI_BUILD = os.environ.get('CI_BUILD', False)

# Handle optional dependencies
extras_require = {
    'full': [
        "memory_profiler>=0.60.0,<0.62.0",
        "pytest>=7.0.0,<8.0.0",
    ],
    'dev': [
        "pytest>=7.0.0,<8.0.0",
        "pytest-cov",
        "black",
        "isort",
        "flake8",
    ],
}

setup(
    name="qndb",
    version="1.0.0",  
    author="Abhishek Panthee",
    author_email="contact@abhishekpanthee.com.np",
    description="A quantum database implementation",
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    license="MIT",
    url="https://github.com/abhishekpanthee/quantum-database",
    packages=find_packages(),
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Development Status :: 3 - Alpha",
        "Topic :: Database",
        "Topic :: Scientific/Engineering :: Physics",
    ],
    python_requires=">=3.8",  # Updated minimum Python version
    install_requires=[
        "cirq-core", 
        "numpy",
        "pandas",
        "matplotlib",
    ],
    extras_require=extras_require,
    include_package_data=True,
    package_data={
        "": ["examples/*.py"],
    },
    zip_safe=False,
    options={
        'bdist_wheel': {'universal': False}  # Build platform-specific wheels
    },
    # Updated dependency links to a more relevant source for pandas
    dependency_links=[
        "https://www.lfd.uci.edu/~gohlke/pythonlibs/#pandas",  # Provide a custom pandas .whl file location (Gohlke's unofficial binaries)
    ],
)
