# Training Studio

Feedback, corrected answers and explicitly reviewed examples can become scoped memory, few-shot context and JSONL datasets. This release does not include a LoRA/QLoRA trainer or change model weights.

Conversation learning is off on a fresh installation. Enabling it creates pending candidates; it does not approve model answers automatically. Review privacy, context and correctness before approving. Exclude or revoke examples at any time.

Exported datasets, split manifests and evaluation outputs stay in local data/ or training/exports and training/results; none are included here. evaluations/v1_holdout.json contains generic evaluation prompts, not private conversations.
