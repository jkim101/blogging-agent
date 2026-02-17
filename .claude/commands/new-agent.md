Guide for adding a new agent to the pipeline.

Steps:
1. Create prompt file: `prompts/<agent_name>.py` with SYSTEM_PROMPT and TOOLS
2. Create agent file: `agents/<agent_name>.py` inheriting from BaseAgent
3. Add model mapping in `config/settings.py` AGENT_MODELS dict
4. Register as a node in `core/graph.py`
5. Update `core/state.py` PipelineState if new fields are needed
6. Add tests in `tests/test_agents.py`
7. Update CLAUDE.md agent table

Reference: 설계서 §3 for agent specification patterns, §7 for state design.
