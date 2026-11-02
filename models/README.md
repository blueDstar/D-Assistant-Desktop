# Model assets

GGUF weights are not committed. Modelfiles use relative paths to data/models; run them from the repository using the commands in docs/INSTALLATION.md. The app uses text inference only; these templates do not import a vision projector.

- 4B GGUF: unsloth/Qwen3.5-4B-GGUF, revision e87f176479d0855a907a41277aca2f8ee7a09523.
- 2B GGUF: unsloth/Qwen3.5-2B-GGUF, revision f6d5376be1edb4d416d56da11e5397a961aca8ae.
- Download scripts verify upstream size and LFS SHA256 or Git blob hash, and write local manifests. Tokenizer revisions are in those scripts.
- Ollama import adds a model tag; merely downloading GGUF is insufficient.
- Runtime versions and hardware can change behavior; validate both quality and resources before changing defaults.
- Dependencies, model weights and voices have separate licenses; see docs/THIRD_PARTY_NOTICES.md.
