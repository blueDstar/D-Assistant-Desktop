"""Explicit pinned download for fast chat; does not activate, train, or upload data."""
import prepare_models_v6 as assets
assets.ASSETS = [
 ('unsloth/Qwen3.5-2B-GGUF','f6d5376be1edb4d416d56da11e5397a961aca8ae','Qwen3.5-2B-Q4_K_M.gguf','qwen35-2b/Qwen3.5-2B-Q4_K_M.gguf'),
 ('Qwen/Qwen3.5-2B','15852e8c16360a2fea060d615a32b45270f8a8fc','tokenizer.json','qwen35-tokenizer.json'),
]
if __name__=='__main__':
 assets.prepare(manifest_name='upgrade-v6.2-fast-manifest.json')
