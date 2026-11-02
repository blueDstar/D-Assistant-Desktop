"""Download only the pinned tokenizer for context-budget tests, not LLM weights."""
import prepare_models_v6 as assets

assets.ASSETS = [
    ('Qwen/Qwen3.5-4B', '851bf6e806efd8d0a36b00ddf55e13ccb7b8cd0a',
     'tokenizer.json', 'qwen35-tokenizer.json'),
    # Older model tags remain in regression fixtures; no legacy weights needed.
    ('Qwen/Qwen3-1.7B', '70d244cc86ccca08cf5af4e1e306ecf908b1ad5e',
     'tokenizer.json', 'qwen3-tokenizer.json'),
]

if __name__ == '__main__':
    assets.prepare(manifest_name='test-tokenizer-manifest.json')
