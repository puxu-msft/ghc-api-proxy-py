"""Facts shared across domains, owned by none of them.

Generation and release ids are parsed here rather than under `lifecycle.rolling`, because
`tokenization.snapshot_store` names them too: a module that several domains depend on cannot live
inside one of them without making that one a dependency of the others.
"""
