"""
Top-level python API for the ``core`` app.
"""
import logging

import git

logger = logging.getLogger(__name__)


def current_commit_hash():
    """
    Returns the current hex SHA for this codebase.
    """
    try:
        breakpoint()
        repo = git.Repo(search_parent_directories=True)
        return repo.git.rev_parse("HEAD")
        # return repo.head.object.hexsha
    except Exception:
        logger.exception('Could not fetch current commit hash')
        return None
