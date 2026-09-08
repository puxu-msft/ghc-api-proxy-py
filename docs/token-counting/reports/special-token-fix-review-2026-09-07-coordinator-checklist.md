# Special-token ordinary-text fix review coordinator checklist

性质：未提交代码修复的独立评审核查清单，不是living行为权威。权威条款见`../spec.md` §4.3、A24、A25与§13。

## 固定范围

本轮只评审以下七个working-tree路径相对当前main HEAD的diff：

- `src/app/tokenization/estimators.py`
- `tests/unit/tokenization/test_estimator_metrics.py`
- `tests/unit/tokenization/test_local_token_worker.py`
- `tests/unit/tokenization/prompt_admission_process_helper.py`
- `tests/unit/tokenization/test_responses_estimator.py`
- `tests/unit/tokenization/test_token_counting.py`
- `tests/int/test_pipeline_app.py`

## 可核验claims

- C1．根因修复发生在estimator的共同文本编码边界：Anthropic与Responses估算器的system／instructions、messages、tool JSON、function-call arguments／output和fallback JSON均不再调用带默认special-token guard的`Encoding.encode()`。
- C2．生产实现使用`encode_ordinary()`保留客户端字符串的字面语义；没有使用`allowed_special`、单spelling denylist、HTTP catch／fallback或Responses-only特判。
- C3．unit oracle使用与production helper不同的`tiktoken.encode(..., disallowed_special=())`入口，枚举configured tokenizer的全部`special_tokens_set`且显式确认`<|endoftext|>`属于集合；exact count断言能区别ordinary encoding与control-token encoding。
- C4．Anthropic unit矩阵覆盖top-level system、message和tool schema；Responses unit矩阵覆盖instructions、message、tool schema、function-call arguments和function-call output。每个surface遍历全部configured special spellings。
- C5．production ASGI回归分别覆盖direct Anthropic local-only与Anthropic→Responses local，输入包含用户报告的`<|endoftext|>`，要求HTTP 200、严格只有`input_tokens`与`estimated`、正整数、`estimated is True`且remote transport 0 calls。
- C6．旧worker metrics测试不再把产品缺陷当失败触发器；synthetic child-process result仍证明lookup／estimate timing与failure identity传播，且`test_estimator_metrics.py`的fake tokenizer实现当前`encode_ordinary()` contract。
- C7．修复不改变provider顺序、calibration、public错误分类、估算公式或framing常量；七路径外没有production／test改动属于本切片。
- C8．正向证据：136个相关unit、14个count-token integration、七路径Ruff和Pyright均通过。反向证据：把helper恢复为default `encode()`时16项surface矩阵全红；改为`allowed_special=encoding.special_tokens_set`时同16项均因exact count差异全红；两次变异都在`finally`逐字恢复。

## Reviewer重点失效面

1. 沿真实ASGI→driver→worker process→estimator调用链确认修复可达，不能只看helper存在。
2. 对测试oracle检查是否与production helper同源到会共享同一错误；是否真的比较ordinary sequence／exact delta而非只断言非500。
3. 查任一仍使用默认`encoding.encode()`的estimator路径，或非字符串／structured serialization路径遗漏。
4. 查synthetic failure helper是否绕过了worker process、parent metrics或原异常identity，导致旧测试保护失效。
5. 查新增参数矩阵是否有vacuous parameter、空集合、错误selector或expected由被测函数自产。
6. 只报blocker／major，最多6条；只剩minor／nit则直接判pass，不扩成全库重构建议。

## 收件核查

Coordinator将核对报告尾部哨兵、finding计数、七路径diff digest与base HEAD；逐条独立处置finding。报告通过后仍需运行最终验证并按共享工作树pathspec提交，不能把review pass冒充commit或全库回归。
