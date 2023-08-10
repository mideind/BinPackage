#!/usr/bin/env bash
# Build the reynir wheels on the CentOS5/6 base manylinux1/manylinux2010 platform
# This script should be executed inside the Docker container!
# It is invoked indirectly from wheels.sh

# Stop execution upon error; show executed commands
set -e -x

yum install -y libffi-devel

# Create wheels for Python >= 3.8 (note: cp311 is not supported yet)
for PYBIN in cp38 cp39 cp310; do
	"/opt/python/${PYBIN}-${PYBIN}/bin/pip" wheel /io/ -w wheelhouse/
done
# Create wheels for PyPy3 (>=3.8)
for PYBIN in /opt/pypy/pypy3.*/bin; do
    # If PyPy 3.6 or PyPy 3.7, skip
    if [[ $PYBIN == *"pypy3.6"* ]] || [[ $PYBIN == *"pypy3.7"* ]]; then
        continue
    fi
    "${PYBIN}/pip" wheel /io/ -w wheelhouse/
done

# Bundle external shared libraries into the wheels
for whl in wheelhouse/islenska-*.whl; do
    auditwheel repair "$whl" --plat $PLAT -w /io/wheelhouse/
done

# Set read/write permissions on the wheels
chmod 666 /io/wheelhouse/*
