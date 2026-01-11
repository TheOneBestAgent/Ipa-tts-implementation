## 1. Implementation
- [ ] Update settings to include phoneme mode + autolearn config and ensure dirs exist
- [ ] Implement DictLearner with buffered writes to auto_learn.json
- [ ] Update eSpeak fallback helper to return canonical phoneme strings
- [ ] Refactor resolver to use eSpeak phonemes, phrase overrides, and autolearn hooks
- [ ] Update dict routes to support override, learn, and lookup endpoints
- [ ] Add manifest debug fields for resolution summaries

## 2. Tests
- [ ] Add tests for phrase override greedy matching
- [ ] Add tests for pack priority (local_overrides vs anime_en)
- [ ] Add tests for autolearn persistence + lower priority
- [ ] Add tests for eSpeak fallback output (mocked phonemizer)
