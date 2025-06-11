import os

from setuptools import setup, find_packages

here = os.path.abspath(os.path.dirname(__file__))
def read_requirements():
    with open(os.path.join(here, 'requirements.txt'), encoding='utf-8') as f:
        return f.read().splitlines()

setup(
    name='nacos-mcp-wrapper-python',
    version='1.0.1',  # 项目的版本号
	packages=find_packages(
			exclude=["test", "*.tests", "*.tests.*", "tests.*", "tests"]), # 自动发现所有包
	url="https://github.com/nacos-group/nacos-mcp-wrapper-python",
    license="Apache License 2.0",
	install_requires=read_requirements(),
    author='nacos',
    description='Python sdk support mcp server auto register to nacos',  # 项目的简短描述
    long_description=open('README.md').read(),  # 项目的详细描述
    long_description_content_type='text/markdown',  # 描述的格式
    classifiers=[
		"Topic :: Software Development :: Libraries :: Python Modules",
		"Operating System :: OS Independent",
		"Programming Language :: Python",
		"Programming Language :: Python :: 3.10"
    ],
    python_requires='>=3.10',
)