# Operations

The first local runtime is deliberately small:

1. Validate manifests before activating a pipeline.
2. Run a named pipeline partition from the CLI.
3. Inspect quality results before treating a materialization as current.
4. Keep `.data/` outside Git and preserve raw captures for replay.

The CLI returns a non-zero status when a required quality check blocks publication. Production scheduling, alert routing, and object-store credentials remain deployment decisions for the approved runtime.
