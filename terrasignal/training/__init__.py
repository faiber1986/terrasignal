"""Training pipelines: local stand-ins for the SageMaker Pipelines described in
the design doc (§5). Same gates, same registry semantics, no cloud.

Production path: each `train_*` module becomes a SageMaker Pipeline step;
`registry.py` maps 1:1 onto the SageMaker Model Registry approval flow.
"""
