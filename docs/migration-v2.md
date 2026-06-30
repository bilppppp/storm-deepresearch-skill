# Migration to Governed 2.0.0

The migration sequence is:

1. [0.1.0 to 0.2.0](migration-v0.1-to-v0.2.md)
2. [0.2.0 to 0.3.0](migration-v0.2-to-v0.3.md)
3. [0.3.0 to 0.4.0](migration-v0.3-to-v0.4.md)
4. [0.4.0 to 1.0.0](migration-v0.4-to-v1.0.md)
5. [1.1.0 to 2.0.0](migration-v1.1-to-v2.0.md)

This compatibility entry exists so release tooling can resolve the stable
`docs/migration-v2.md` path. Version 2.0.0 makes the net-body, external-review,
P4 closure, temporal-causality, evidence-ceiling, P2-disposition,
source/query-many-to-many, and absence-search gates mandatory for every new
full dossier. Existing runs remain governed by the package version that created
them and are not silently upgraded.
