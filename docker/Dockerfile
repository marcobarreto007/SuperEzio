FROM nvidia/cuda:12.4.1-cudnn-devel-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive
ENV HF_HOME=/workspace/.cache/huggingface
ENV TRANSFORMERS_CACHE=/workspace/.cache/huggingface
ENV WANDB_DISABLED=true
ENV PYTHONUNBUFFERED=1

WORKDIR /workspace

RUN apt-get update && apt-get install -y \
    git curl wget build-essential cmake ninja-build \
    python3 python3-pip python3-venv \
    libcurl4-openssl-dev pciutils htop tmux nano \
    && rm -rf /var/lib/apt/lists/*

RUN pip3 install --upgrade pip

RUN pip3 install \
    torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu124

RUN pip3 install \
    unsloth unsloth_zoo \
    transformers datasets accelerate peft trl bitsandbytes \
    huggingface_hub sentencepiece protobuf scipy

RUN git clone https://github.com/ggml-org/llama.cpp /opt/llama.cpp && \
    cmake /opt/llama.cpp -B /opt/llama.cpp/build \
      -DBUILD_SHARED_LIBS=OFF -DGGML_CUDA=ON -DLLAMA_CURL=ON && \
    cmake --build /opt/llama.cpp/build --config Release -j

COPY onstart.sh /workspace/onstart.sh
COPY train_unsloth.py /workspace/train_unsloth.py
RUN chmod +x /workspace/onstart.sh

CMD ["/bin/bash"]
