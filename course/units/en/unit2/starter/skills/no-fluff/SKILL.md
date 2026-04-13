---
name: no-fluff
description: Strip disclaimers, warnings, and filler from generated code and UI. Use when building demos or writing code — keeps output focused on what matters.
---

# No Fluff

When generating code or UI copy:

## Don't add

- "⚠️ Note: this is a demo" footers
- "For production use, consider..." disclaimers
- Excessive inline comments explaining obvious code
- "TODO" or "FIXME" placeholders unless the user asked
- Error handling for conditions that can't happen in the demo context

## Do

- Trust the user knows it's a demo
- Let the code speak for itself
- One-line docstrings if any
- Comments only where the logic is non-obvious

## Example

Before:
```python
# ⚠️ WARNING: This is a mock function for demonstration purposes only.
# In a production environment, you would replace this with a real model.
def predict(text):
    # TODO: implement real inference
    return {"positive": 0.8}  # mock result
```

After:
```python
def predict(text):
    return {"positive": 0.8}
```
