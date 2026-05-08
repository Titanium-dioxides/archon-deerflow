# Archon Lean4 Knowledge

Lean 4 theorem proving best practices.

## Search Priority
1. `lean_local_search` — exact symbol/lemma name
2. `lean_leansearch` — semantic search by mathematical content
3. `lean_loogle` — simple type-pattern search only

## Common Tactics by Goal Shape
| Goal | Tactic |
|------|--------|
| `A → B` | `intro h` |
| `A ∧ B` | `constructor` / `apply And.intro` |
| `A ∨ B` | `left` / `right` |
| `∃ x, P x` | `use x` |
| `∀ x, P x` | `intro x` |
| `a = b` | `rfl`, `simp`, `calc` |
| `¬ A` | `intro h; exfalso; apply h` |
| `a ≠ b` | `intro h; apply h` → `rfl` after deriving contradiction |

## Induction Patterns
- `Nat`: `induction n with | zero => ... | succ n ih => ...`
- `List`: `induction xs with | nil => ... | cons x xs ih => ...`
- `inductive` types: `cases` / `induction` + `rename_i` / `case`

## Compilation Check
After any proof change, run `lake build` and parse errors fully before retrying.
If a direction fails 3+ times identically, switch strategy.
