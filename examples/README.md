# Examples

These are runnable scripts that show NWT in action.

## `demo_project/`

A self-contained walkthrough. It seeds a fake project timeline (a tiny
memory engine) so you can poke at the CLI, the graph, and the evolution
summary without setting up a real repo.

```bash
python examples/demo_project/seed.py /tmp/nwt-demo
cd /tmp/nwt-demo
nwt history
nwt graph
nwt story
nwt explain activation.py
```
