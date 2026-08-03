# Community GPU grants

When a user has a good use case (open research demo, hobbyist project, educational tool, institutional showcase) and can't pay for the hardware it needs, they can request a free community grant from Hugging Face.

Free personal accounts already get 2 ZeroGPU Spaces, so a grant is now for the cases that go past that:

- a **dedicated GPU** ZeroGPU can't cover (non-PyTorch main model with heavy init, model too big for 96 GB, always-on serving);
- a **Gradio Space beyond the free 2-ZeroGPU cap**, without subscribing to PRO.

## The flow

1. **Build the Space.** If the user still has a free ZeroGPU slot, create it as `--flavor zero-a10g` and iterate normally with real inference before applying.

   If they're out of slots, create a **Static** Space instead (`--space-sdk static` — free for everyone) and push the app there; the SDK can be switched to `gradio` in the README frontmatter once the grant lands. Code the app for ZeroGPU anyway — `import spaces`, `@spaces.GPU`, module-scope `.to("cuda")`. In this mode you **can't iterate-with-real-inference** before the grant, so just get the code in place and submit.

   For a dedicated-GPU grant, get the app to BUILD cleanly and reach `RUNNING` (even if the runtime would OOM on real input), then submit.

2. **Submit a Community Tab discussion** on the Space. Title:

   ```
   Apply for a GPU community grant: <Personal|Company|Academic> project
   ```

   Pick the closest fit. Body:

   ```
   Description of the app: one paragraph on what it does + who it's for.
   Justification: one paragraph on why this should run on ZeroGPU
   (open-source, research, educational, etc.). 
   ```

   If the user didn't give you a justification, a reasonable default is "Public open-source demo, can't cover the hardware cost — happy to provide more context if helpful."

3. **Wait.** Open and publicly-facing applications by researchers, tinkerers, and institutions are typically approved. Approval can take days.

4. **Once approved**, the hardware is attached automatically — no code change needed (a Static holding Space still needs its `sdk:` flipped to `gradio`). The user comes back and you can iterate / refine with real GPU access.

## When to suggest this

- The use case is a clear public ML demo (not a private tool) and the user is out of free ZeroGPU slots.
- The model needs more than ZeroGPU offers — beyond 48 GB `large` / 96 GB `xlarge`, or a non-PyTorch runtime — and the user can't pay.

## When NOT to suggest this

- The user is on a free account and this is their 1st or 2nd Space — they can create it on ZeroGPU directly; no grant needed.
- Private / commercial / closed-source projects — push the user toward PRO instead.
- `canPay=True` users who just need paid hardware — they can attach it directly.

## Posting the request programmatically

```python
from huggingface_hub import HfApi

api = HfApi(token="hf_...")
api.create_discussion(
    repo_id="<ns>/<space>",
    repo_type="space",
    title="Apply for a GPU community grant: Personal project",
    description="<description and justification>",
)
```

The Community Tab must be enabled on the Space (default — keep it on).
