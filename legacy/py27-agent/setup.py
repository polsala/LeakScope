from distutils.core import setup, Extension
import sys

if sys.version_info[:3] != (2, 7, 18):
    raise RuntimeError('This extension supports CPython 2.7.18 only')

setup(name='leakscope-agent', version='0.1.0',
      package_dir={'': 'src'}, py_modules=['leakscope_agent'],
      ext_modules=[Extension('_leakscope_native', ['src/native.c'],
                             libraries=['dl'], depends=['src/profile.h', 'src/lab_snapshot.h', 'include/lab_protocol.h'],
                             extra_compile_args=['-std=c99', '-Wall', '-Wextra'])])
