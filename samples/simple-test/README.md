# Simple Test — Archon Workflow 演示

`eq_refl_test` 包含一个 `sorry`，用于验证完整工作流。

```bash
# 在工作流上运行
cd deer-flow/backend
uv run python3 -c "
from deerflow.archon_workflow import run_archon_workflow
result = run_archon_workflow('/samples/simple-test')
print(result['current_stage'])
"
```
