#!/bin/bash
set -e
apt-get update
apt-get install -y build-essential cmake git wget
git clone --depth 1 https://github.com/ggerganov/llama.cpp
cd llama.cpp
cmake -B build -DCMAKE_CUDA_ARCHITECTURES=native
cmake --build build --config Release
echo "llama.cpp build complete"
