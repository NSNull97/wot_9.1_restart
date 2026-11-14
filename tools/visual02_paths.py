"""Constrain VISUAL-02 output to this project's local evidence directory."""
from pathlib import Path
from tools.destructible_catalog import no_links

# The owner-authorized project location for this research run. Deliberately do
# not infer this from a checked-out worktree or accept a caller-supplied root.
EVIDENCE_ROOT = Path('D:/WoT_9.1_Server/local/evidence')


def safe_evidence_output(path, root=EVIDENCE_ROOT):
    evidence = no_links(root).resolve(strict=True)
    if not evidence.is_dir():
        raise ValueError('evidence root is not a directory')
    candidate = no_links(Path(path).absolute())
    resolved = candidate.resolve(strict=False)
    if resolved == evidence or not resolved.is_relative_to(evidence):
        raise ValueError('output must be inside the authorized local/evidence directory')
    return resolved
